"""Prefilter and relevance stages.

The Phase 3 runner still owns normalize and dedupe. This module adds the next
two stages and does not replace that path. It reads derived rows and duplicate
links. It does not write them back, and it does not send ``raw_text`` to a
provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.hashing import artifact_hash
from src.core.ids import event_id, sha1_short
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION, prompt_version
from src.extract.validator import validate_span
from src.llm.gateway import ModelGateway
from src.llm.providers.base import StructuredProvider
from src.llm.select import select_provider
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    DecisionTechnicalState,
    DuplicateReviewState,
    ReasonCode,
    Stage,
    StageEventTargetType,
    StageStatus,
)
from src.models.relevance import RelevanceDecision
from src.models.stage_event import StageEvent
from src.pipeline.manifest import manifest_payload, write_manifest
from src.relevance.classifier import (
    ClassificationOutcome,
    SpanVerdict,
    assemble_decision,
    failure_outcome,
    pending_span,
)
from src.relevance.prompts import PROMPT_ID, relevance_json_schema, render_relevance_prompt
from src.relevance.rules import PrefilterResult, prefilter_document
from src.relevance.schema import RelevancePayload
from src.relevance.seed import SeedRow, seed_row_from_prefilter, write_seed_review
from src.review.queue import ReviewItem, merge_items, open_relevance_items

#: Same instant Phase 3 stamps, so a rules rerun does not move on the clock.
PHASE_INSTANT = datetime(2026, 9, 27, tzinfo=UTC)

CONFIRMED_DUPLICATE = frozenset(
    {DuplicateReviewState.auto_confirmed, DuplicateReviewState.human_confirmed}
)

_UNAVAILABLE_STATES = frozenset(
    {
        DecisionTechnicalState.provider_unavailable,
        DecisionTechnicalState.provider_error,
        DecisionTechnicalState.timeout,
        DecisionTechnicalState.rate_limited,
    }
)


@dataclass
class Phase4Result:
    """Counts safe to print. No document text and no secrets."""

    run_id: str
    document_count: int
    canonical_count: int
    skipped_non_canonical: int
    classify_count: int
    obvious_exclusion_count: int
    mixed_retained: int
    single_signal_retained: int
    relevance_attempted: int
    relevance_by_state: dict[str, int]
    relevance_by_scope: dict[str, int]
    review_items: int
    provider_calls: int
    cache_hits: int
    cache_misses: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    seed_rows: int
    dry_run: bool
    offline: bool
    output_dir: Path
    files_written: tuple[str, ...] = field(default_factory=tuple)


def non_canonical_map(links: list[DuplicateLink] | tuple[DuplicateLink, ...]) -> dict[str, str]:
    """Confirmed duplicates point at their canonical document. Pending links do not."""
    mapping: dict[str, str] = {}
    for link in links:
        if link.review_state in CONFIRMED_DUPLICATE:
            mapping[link.doc_id] = link.canonical_doc_id
    return mapping


def run_phase4(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: list[DuplicateLink] | tuple[DuplicateLink, ...],
    *,
    output_dir: Path | str,
    stages: list[str],
    limit: int | None = None,
    dry_run: bool = False,
    resume: str | None = None,
    offline: bool = False,
    provider_name: str = "null",
    model_name: str = "",
    api_key: str | None = None,
    author_salt: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    confidence_review_below: float = 0.7,
    config_hash: str = "",
    project_root: Path | None = None,
    provider: StructuredProvider | None = None,
    sleeper=None,
    cache_dir: Path | None = None,
    provider_call_budget: int | None = None,
) -> Phase4Result:
    """Run prefilter, relevance, or both. Dry-run writes nothing and calls no provider."""
    destination = Path(output_dir)
    ordered = sorted(documents, key=lambda document: document.doc_id)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater")
        ordered = ordered[:limit]
    derived_by_id = {row.doc_id: row for row in derived}
    missing = [document.doc_id for document in ordered if document.doc_id not in derived_by_id]
    if missing:
        raise ValueError("derived rows are missing for " + ", ".join(missing[:5]))

    raw_before = {document.doc_id: document.raw_text for document in ordered}
    derived_before = {row.doc_id: row.model_dump_json() for row in derived}

    selected_ids = [document.doc_id for document in ordered]
    run_id = phase4_run_id(
        doc_ids=selected_ids,
        stages=stages,
        limit=limit,
        provider_name="null" if offline or dry_run else provider_name,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        confidence_review_below=confidence_review_below,
        offline=offline,
        dry_run=dry_run,
    )
    skips = non_canonical_map(links)
    prefilter_rows = _prefilter_rows(ordered, derived_by_id, skips)

    cache_dir = Path(cache_dir) if cache_dir is not None else destination.parent / "cache"
    denylist = tuple(secret for secret in (api_key, author_salt) if secret)
    chosen = provider
    if chosen is None:
        chosen = select_provider(
            configured_name=provider_name,
            api_key=api_key,
            offline=offline or dry_run,
        )
    active_provider_name = "null" if offline or dry_run else provider_name
    if provider is not None and not dry_run and not offline:
        active_provider_name = getattr(provider, "provider_name", provider_name)

    relevance_outcomes: list[ClassificationOutcome] = []
    provider_calls = 0
    cache_hits = 0
    cache_misses = 0
    input_tokens = 0
    output_tokens = 0
    estimated_cost = 0.0

    if "relevance" in stages and not dry_run:
        gateway = ModelGateway(
            chosen,
            _cache(cache_dir),
            provider_name=active_provider_name,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            input_usd_per_million=input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
            denylist=denylist,
            sleeper=sleeper,
            call_budget=provider_call_budget,
        )
        done = _succeeded_targets(destination / "checkpoints.jsonl", resume) if resume else set()
        existing = _load_decisions(destination / "relevance_decisions.jsonl")
        kept = [
            decision
            for decision in existing
            if decision.doc_id not in {row.doc_id for row in prefilter_rows if row.passed}
            or (resume and decision.doc_id in done)
        ]
        fresh: list[RelevanceDecision] = []
        for row in prefilter_rows:
            if not row.passed:
                continue
            if resume and row.doc_id in done and any(item.doc_id == row.doc_id for item in existing):
                continue
            outcome = _classify_one(
                gateway,
                ordered_by_id(ordered)[row.doc_id],
                derived_by_id[row.doc_id],
                row,
                model_name=model_name,
                confidence_review_below=confidence_review_below,
                denylist=denylist,
            )
            relevance_outcomes.append(outcome)
            fresh.append(outcome.decision)
        decisions = _merge_decisions(kept, fresh)
        provider_calls = gateway.usage.provider_calls
        cache_hits = gateway.usage.cache_hits
        cache_misses = gateway.usage.cache_misses
        input_tokens = gateway.usage.input_tokens
        output_tokens = gateway.usage.output_tokens
        estimated_cost = gateway.usage.estimated_cost_usd
    else:
        decisions = _load_decisions(destination / "relevance_decisions.jsonl") if not dry_run else []

    _assert_unchanged(ordered, derived, raw_before, derived_before)

    files: list[str] = []
    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)
        if "prefilter" in stages:
            _write_json(destination / "prefilter_results.jsonl", [row.to_json() for row in prefilter_rows])
            files.append("prefilter_results.jsonl")
            seed_rows = [
                _seed_row(ordered_by_id(ordered)[row.doc_id], derived_by_id[row.doc_id], row)
                for row in prefilter_rows
            ]
            write_seed_review(destination / "relevance_seed_review.csv", seed_rows)
            files.append("relevance_seed_review.csv")
        if "relevance" in stages:
            _write_models(destination / "relevance_decisions.jsonl", decisions, "decision_id")
            files.append("relevance_decisions.jsonl")
            _write_failures(destination / "relevance_failures.jsonl", relevance_outcomes, denylist)
            files.append("relevance_failures.jsonl")
            queue = _merge_queue(
                destination / "review_queue.jsonl",
                relevance_outcomes,
            )
            _write_models(destination / "review_queue.jsonl", queue, "item_id")
            files.append("review_queue.jsonl")
        events = _merge_stage_events(
            destination / "stage_events.jsonl",
            _events(run_id, prefilter_rows, relevance_outcomes, stages),
            stages,
        )
        _write_models(destination / "stage_events.jsonl", events, "event_id")
        files.append("stage_events.jsonl")
        _append_checkpoints(destination / "checkpoints.jsonl", run_id, prefilter_rows, relevance_outcomes, stages)
        files.append("checkpoints.jsonl")
        manifest = _manifest(
            run_id=run_id,
            stages=stages,
            dry_run=False,
            offline=offline or active_provider_name == "null",
            config_hash=config_hash,
            project_root=project_root or Path.cwd(),
            prefilter_rows=prefilter_rows,
            decisions=(
                [
                    decision
                    for decision in decisions
                    if decision.doc_id in {row.doc_id for row in prefilter_rows}
                ]
                if "relevance" in stages
                else []
            ),
            provider_calls=provider_calls,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            destination=destination,
        )
        write_manifest(destination / "run_manifest.json", manifest)
        files.append("run_manifest.json")

    counts = _count(prefilter_rows)
    by_state: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    attempted = 0
    if "relevance" in stages and not dry_run:
        attempted = sum(1 for row in prefilter_rows if row.passed)
        for decision in decisions:
            if decision.doc_id not in {row.doc_id for row in prefilter_rows if row.passed}:
                continue
            by_state[decision.technical_state.value] = by_state.get(decision.technical_state.value, 0) + 1
            if decision.scope_class is not None:
                by_scope[decision.scope_class.value] = by_scope.get(decision.scope_class.value, 0) + 1
    review_count = 0
    if not dry_run and "relevance" in stages and (destination / "review_queue.jsonl").is_file():
        review_count = sum(
            1
            for item in _load_reviews(destination / "review_queue.jsonl")
            if item.state == "open" and item.target_type == "relevance_decision"
        )
    seed_count = len(prefilter_rows) if "prefilter" in stages and not dry_run else 0
    return Phase4Result(
        run_id=run_id,
        document_count=len(ordered),
        canonical_count=counts["canonical"],
        skipped_non_canonical=counts["skipped"],
        classify_count=counts["classify"],
        obvious_exclusion_count=counts["obvious"],
        mixed_retained=counts["mixed"],
        single_signal_retained=counts["single"],
        relevance_attempted=attempted,
        relevance_by_state=by_state,
        relevance_by_scope=by_scope,
        review_items=review_count,
        provider_calls=provider_calls,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
        seed_rows=seed_count,
        dry_run=dry_run,
        offline=offline or active_provider_name == "null",
        output_dir=destination,
        files_written=tuple(files),
    )


def classify_with_ladder(
    payload: RelevancePayload,
    *,
    audit: str,
    redactions,
    content_hash: str,
    model_name: str,
    prefilter: PrefilterResult | None,
    confidence_review_below: float,
    decided_at: datetime,
    expected_doc_id: str,
) -> ClassificationOutcome:
    """Validate one payload against ``audit`` only. ``raw_text`` is not accepted."""
    evidence = payload.evidence
    if (evidence.start_char is None) != (evidence.end_char is None):
        return assemble_decision(
            payload,
            None,
            expected_doc_id=expected_doc_id,
            content_hash=content_hash,
            model_name=model_name,
            prefilter=prefilter,
            confidence_review_below=confidence_review_below,
            decided_at=decided_at,
            failure_state=DecisionTechnicalState.schema_validation_failed,
            failure_message="evidence offsets must be supplied together",
        )
    try:
        span = pending_span(payload, "pending")
    except (ValueError, TypeError) as exc:
        return assemble_decision(
            payload,
            None,
            expected_doc_id=expected_doc_id,
            content_hash=content_hash,
            model_name=model_name,
            prefilter=prefilter,
            confidence_review_below=confidence_review_below,
            decided_at=decided_at,
            failure_state=DecisionTechnicalState.schema_validation_failed,
            failure_message=str(exc)[:300],
        )
    checked = validate_span(span, audit, redactions)
    verdict = SpanVerdict(
        ok=checked.ok,
        reason_code=checked.reason_code,
        quote=checked.span.quote,
        start_char=checked.span.start_char,
        end_char=checked.span.end_char,
        offset_state=checked.span.offset_state,
        repair_applied=checked.span.repair_applied,
        validation_state=checked.span.validation_state,
        message=checked.message,
    )
    return assemble_decision(
        payload,
        verdict,
        expected_doc_id=expected_doc_id,
        content_hash=content_hash,
        model_name=model_name,
        prefilter=prefilter,
        confidence_review_below=confidence_review_below,
        decided_at=decided_at,
    )


def format_phase4_summary(result: Phase4Result) -> str:
    """Count summary. No document text, author names, hashes, or paths above the directory name."""
    states = ", ".join(
        f"{name}={count}" for name, count in sorted(result.relevance_by_state.items())
    ) or "none"
    lines = [
        "Phase 4 run",
        f"  run id               {result.run_id}",
        f"  dry run              {str(result.dry_run).lower()}",
        f"  offline              {str(result.offline).lower()}",
        f"  documents            {result.document_count}",
        f"  canonical            {result.canonical_count}",
        f"  skipped duplicates   {result.skipped_non_canonical}",
        f"  prefilter classify   {result.classify_count}",
        f"  prefilter exclusion  {result.obvious_exclusion_count}",
        f"  mixed retained       {result.mixed_retained}",
        f"  single signal kept   {result.single_signal_retained}",
        f"  relevance attempted  {result.relevance_attempted}",
        f"  relevance states     {states}",
        f"  provider calls       {result.provider_calls}",
        f"  cache hits           {result.cache_hits}",
        f"  cache misses         {result.cache_misses}",
        f"  input tokens         {result.input_tokens}",
        f"  output tokens        {result.output_tokens}",
        f"  estimated cost usd   {result.estimated_cost_usd:.6f}",
        f"  seed rows            {result.seed_rows}",
        f"  files written        {len(result.files_written)}",
    ]
    return "\n".join(lines) + "\n"


def phase4_run_id(
    *,
    doc_ids: list[str],
    stages: list[str],
    limit: int | None,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    confidence_review_below: float,
    offline: bool,
    dry_run: bool,
) -> str:
    return sha1_short(
        "phase4",
        RULESET_VERSION,
        prompt_version(PROMPT_ID),
        SCHEMA_VERSION,
        provider_name,
        model_name,
        temperature,
        max_tokens,
        confidence_review_below,
        offline,
        dry_run,
        "" if limit is None else limit,
        *stages,
        *doc_ids,
        length=12,
    )


def ordered_by_id(documents: list[CollectedDocument]) -> dict[str, CollectedDocument]:
    return {document.doc_id: document for document in documents}


def _prefilter_rows(
    documents: list[CollectedDocument],
    derived_by_id: dict[str, DocumentDerived],
    skips: dict[str, str],
) -> list[PrefilterResult]:
    rows: list[PrefilterResult] = []
    for document in documents:
        canonical = skips.get(document.doc_id)
        rows.append(
            prefilter_document(
                document.doc_id,
                derived_by_id[document.doc_id].normalized_text,
                canonical_doc_id=canonical,
            )
        )
    return rows


def _classify_one(
    gateway: ModelGateway,
    document: CollectedDocument,
    derived: DocumentDerived,
    prefilter: PrefilterResult,
    *,
    model_name: str,
    confidence_review_below: float,
    denylist: tuple[str, ...],
) -> ClassificationOutcome:
    prompt = render_relevance_prompt(doc_id=document.doc_id, raw_text_audit=derived.raw_text_audit)
    if any(secret and secret in prompt for secret in denylist):
        return failure_outcome(
            doc_id=document.doc_id,
            content_hash=derived.content_hash,
            model_name=model_name,
            state=DecisionTechnicalState.provider_error,
            decided_at=PHASE_INSTANT,
            message="prompt withheld",
        )
    completed = gateway.complete(
        prompt=prompt,
        schema=relevance_json_schema(),
        response_model=RelevancePayload,
        content_hash=derived.content_hash,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version(PROMPT_ID),
        ruleset_version=RULESET_VERSION,
        discard_keys=("is_relevant",),
    )
    if completed.technical_state is not DecisionTechnicalState.ok or not isinstance(
        completed.validated, RelevancePayload
    ):
        return failure_outcome(
            doc_id=document.doc_id,
            content_hash=derived.content_hash,
            model_name=model_name,
            state=completed.technical_state,
            decided_at=PHASE_INSTANT,
            message=completed.message or completed.technical_state.value,
        )
    return classify_with_ladder(
        completed.validated,
        audit=derived.raw_text_audit,
        redactions=derived.redaction_spans,
        content_hash=derived.content_hash,
        model_name=model_name,
        prefilter=prefilter,
        confidence_review_below=confidence_review_below,
        decided_at=PHASE_INSTANT,
        expected_doc_id=document.doc_id,
    )


def _seed_row(
    document: CollectedDocument,
    derived: DocumentDerived,
    prefilter: PrefilterResult,
) -> SeedRow:
    return seed_row_from_prefilter(
        doc_id=document.doc_id,
        source_platform=document.source_platform.value,
        source_type=document.source_type.value,
        title=document.title,
        raw_text_audit=derived.raw_text_audit,
        prefilter=prefilter,
    )


def _merge_stage_events(
    path: Path,
    new_events: list[StageEvent],
    stages: list[str],
) -> list[StageEvent]:
    """Replace events for the stages this run owns. Leave every other stage."""
    owned = set(stages)
    kept = [
        StageEvent.model_validate(row)
        for row in _read_jsonl(path)
        if str(row.get("stage")) not in owned
    ]
    combined = kept + new_events
    combined.sort(key=lambda event: event.event_id)
    return combined


def _events(
    run_id: str,
    prefilter_rows: list[PrefilterResult],
    outcomes: list[ClassificationOutcome],
    stages: list[str],
) -> list[StageEvent]:
    events: list[StageEvent] = []
    if "prefilter" in stages:
        for row in prefilter_rows:
            events.append(_prefilter_event(run_id, row))
    if "relevance" in stages:
        for outcome in outcomes:
            events.append(_relevance_event(run_id, outcome))
    events.sort(key=lambda event: event.event_id)
    return events


def _prefilter_event(run_id: str, row: PrefilterResult) -> StageEvent:
    detail = {
        "route": row.route,
        "ruleset_version": row.ruleset_version,
        "signal_ids": [hit.signal_id for hit in row.matched_signals],
        "reason_labels": list(row.reason_labels),
    }
    if row.route == "obvious_exclusion_candidate":
        status = StageStatus.dropped
        reason = ReasonCode(row.drop_reason_code or ReasonCode.other_out_of_scope.value)
        detail["drop_reason_code"] = reason.value
    elif row.route == "skipped_non_canonical":
        status = StageStatus.skipped
        reason = None
        detail["canonical_doc_id"] = row.canonical_doc_id or ""
    else:
        status = StageStatus.succeeded
        reason = None
    return StageEvent(
        event_id=event_id(run_id, Stage.prefilter.value, row.doc_id, 1, status.value),
        target_type=StageEventTargetType.document,
        target_id=row.doc_id,
        stage=Stage.prefilter,
        status=status,
        reason_code=reason,
        attempt=1,
        run_id=run_id,
        occurred_at=PHASE_INSTANT,
        detail=detail,
    )


def _relevance_event(run_id: str, outcome: ClassificationOutcome) -> StageEvent:
    state = outcome.decision.technical_state
    if state is DecisionTechnicalState.ok:
        status = StageStatus.succeeded
        reason = None
    elif state in _UNAVAILABLE_STATES:
        status = StageStatus.unavailable
        reason = outcome.decision.reason_code
    else:
        status = StageStatus.failed
        reason = outcome.decision.reason_code
    return StageEvent(
        event_id=event_id(
            run_id, Stage.relevance.value, outcome.decision.doc_id, 1, status.value
        ),
        target_type=StageEventTargetType.document,
        target_id=outcome.decision.doc_id,
        stage=Stage.relevance,
        status=status,
        reason_code=reason,
        attempt=1,
        run_id=run_id,
        occurred_at=PHASE_INSTANT,
        detail={
            "technical_state": state.value,
            "review_reasons": [code.value for code in outcome.review_reasons],
        },
    )


def _append_checkpoints(
    path: Path,
    run_id: str,
    prefilter_rows: list[PrefilterResult],
    outcomes: list[ClassificationOutcome],
    stages: list[str],
) -> None:
    existing = _read_jsonl(path)
    seen = {
        (row.get("run_id"), row.get("stage"), row.get("target_id"), row.get("status"))
        for row in existing
    }
    extra: list[dict[str, str]] = []
    if "prefilter" in stages:
        for row in prefilter_rows:
            item = {
                "run_id": run_id,
                "stage": Stage.prefilter.value,
                "target_id": row.doc_id,
                "status": StageStatus.succeeded.value,
            }
            key = (item["run_id"], item["stage"], item["target_id"], item["status"])
            if key not in seen:
                extra.append(item)
                seen.add(key)
    if "relevance" in stages:
        for outcome in outcomes:
            item = {
                "run_id": run_id,
                "stage": Stage.relevance.value,
                "target_id": outcome.decision.doc_id,
                "status": StageStatus.succeeded.value,
            }
            key = (item["run_id"], item["stage"], item["target_id"], item["status"])
            if key not in seen:
                extra.append(item)
                seen.add(key)
    if not existing and not extra:
        path.write_text("", encoding="utf-8")
        return
    lines = [json.dumps(row, sort_keys=True) for row in existing]
    lines.extend(json.dumps(row, sort_keys=True) for row in extra)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _succeeded_targets(path: Path, run_id: str | None) -> set[str]:
    if not run_id or not path.is_file():
        return set()
    found: set[str] = set()
    for row in _read_jsonl(path):
        if (
            row.get("run_id") == run_id
            and row.get("stage") == Stage.relevance.value
            and row.get("status") == StageStatus.succeeded.value
        ):
            found.add(str(row.get("target_id")))
    return found


def _merge_queue(path: Path, outcomes: list[ClassificationOutcome]) -> list[ReviewItem]:
    pairs = [
        (outcome.decision.decision_id, reason)
        for outcome in outcomes
        for reason in outcome.review_reasons
    ]
    incoming = open_relevance_items(pairs, opened_at=PHASE_INSTANT)
    return list(merge_items(_load_reviews(path), incoming))


def _merge_decisions(
    kept: list[RelevanceDecision],
    fresh: list[RelevanceDecision],
) -> list[RelevanceDecision]:
    by_id = {decision.decision_id: decision for decision in kept}
    for decision in fresh:
        by_id[decision.decision_id] = decision
    return [by_id[key] for key in sorted(by_id)]


def _manifest(
    *,
    run_id: str,
    stages: list[str],
    dry_run: bool,
    offline: bool,
    config_hash: str,
    project_root: Path,
    prefilter_rows: list[PrefilterResult],
    decisions: list[RelevanceDecision],
    provider_calls: int,
    cache_hits: int,
    cache_misses: int,
    input_tokens: int,
    output_tokens: int,
    estimated_cost: float,
    destination: Path,
) -> dict[str, object]:
    counts = _count(prefilter_rows)
    drop_reasons: dict[str, int] = {}
    for row in prefilter_rows:
        if row.drop_reason_code:
            drop_reasons[row.drop_reason_code] = drop_reasons.get(row.drop_reason_code, 0) + 1
    by_state: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    for decision in decisions:
        by_state[decision.technical_state.value] = by_state.get(decision.technical_state.value, 0) + 1
        if decision.scope_class is not None:
            by_scope[decision.scope_class.value] = by_scope.get(decision.scope_class.value, 0) + 1
    hashes: dict[str, str] = {}
    for name, key in (
        ("prefilter_results.jsonl", "doc_id"),
        ("relevance_decisions.jsonl", "decision_id"),
    ):
        path = destination / name
        if path.is_file():
            hashes[name] = artifact_hash(_read_jsonl(path), key)
    return manifest_payload(
        run_id=run_id,
        stages=stages,
        dry_run=dry_run,
        offline=offline,
        config_hash=config_hash,
        project_root=project_root,
        funnel={
            "prefilter": {
                "classify": counts["classify"],
                "obvious_exclusion_candidate": counts["obvious"],
                "skipped_non_canonical": counts["skipped"],
                "mixed_retained": counts["mixed"],
                "single_signal_retained": counts["single"],
                "drop_reasons": drop_reasons,
            },
            "relevance_by_technical_state": by_state,
            "relevance_by_scope_class": by_scope,
        },
        cache={
            "hits": cache_hits,
            "misses": cache_misses,
            "provider_calls": provider_calls,
        },
        tokens={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
        },
        output_hashes=hashes,
        generated_at=PHASE_INSTANT,
    )


def _count(rows: list[PrefilterResult]) -> dict[str, int]:
    return {
        "canonical": sum(1 for row in rows if row.route != "skipped_non_canonical"),
        "skipped": sum(1 for row in rows if row.route == "skipped_non_canonical"),
        "classify": sum(1 for row in rows if row.route == "classify"),
        "obvious": sum(1 for row in rows if row.route == "obvious_exclusion_candidate"),
        "mixed": sum(1 for row in rows if "mixed_retrieval_and_exclusion" in row.reason_labels),
        "single": sum(1 for row in rows if "single_signal_retained" in row.reason_labels),
    }


def _assert_unchanged(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    raw_before: dict[str, str],
    derived_before: dict[str, str],
) -> None:
    for document in documents:
        if document.raw_text != raw_before[document.doc_id]:
            raise RuntimeError(f"raw_text was modified for {document.doc_id}")
    for row in derived:
        if row.model_dump_json() != derived_before[row.doc_id]:
            raise RuntimeError(f"derived record was modified for {row.doc_id}")


def _write_failures(
    path: Path,
    outcomes: list[ClassificationOutcome],
    denylist: tuple[str, ...],
) -> None:
    rows = []
    for outcome in outcomes:
        if outcome.decision.technical_state is DecisionTechnicalState.ok and not outcome.review_reasons:
            continue
        quote = outcome.retained_quote
        message = outcome.failure_message
        if quote and any(secret and secret in quote for secret in denylist):
            quote = None
            message = "withheld"
        if message and any(secret and secret in message for secret in denylist):
            message = "withheld"
        rows.append(
            {
                "doc_id": outcome.decision.doc_id,
                "decision_id": outcome.decision.decision_id,
                "technical_state": outcome.decision.technical_state.value,
                "review_reasons": [code.value for code in outcome.review_reasons],
                "message": message,
                "retained_quote": quote,
            }
        )
    rows.sort(key=lambda row: str(row["decision_id"]))
    _write_json(path, rows)


def _cache(cache_dir: Path):
    from src.llm.cache import ResponseCache

    return ResponseCache(cache_dir)


def _write_json(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_models(path: Path, records: list, key: str) -> None:
    rows = [record.model_dump(mode="json") for record in records]
    rows.sort(key=lambda row: str(row[key]))
    _write_json(path, rows)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_decisions(path: Path) -> list[RelevanceDecision]:
    return [RelevanceDecision.model_validate(row) for row in _read_jsonl(path)]


def _load_reviews(path: Path) -> list[ReviewItem]:
    return [ReviewItem.model_validate(row) for row in _read_jsonl(path)]


__all__ = [
    "PHASE_INSTANT",
    "Phase4Result",
    "classify_with_ladder",
    "format_phase4_summary",
    "run_phase4",
]
