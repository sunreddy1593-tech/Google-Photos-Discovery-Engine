"""Extract stage for the existing pipeline.

``assemble_cases`` stays the validation boundary. This module chooses the
effective relevance decision, asks the gateway for a completion, and writes the
current JSONL artifacts. It does not call a provider SDK itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.ids import event_id, sha1_short, sha256_hex
from src.core.versions import SCHEMA_VERSION, prompt_version
from src.extract.extractor import ExtractionResult, assemble_cases
from src.extract.prompts import build_extraction_prompt
from src.extract.schema import ExtractionPayload, extraction_schema
from src.extract.validator import select_valid_for_analysis
from src.llm.gateway import ModelGateway, ProviderBudgetError
from src.llm.providers.base import ProviderDiagnostic, ProviderFatalError, StructuredProvider
from src.llm.select import select_provider
from src.models.document_derived import DocumentDerived
from src.models.enums import (
    DecisionTechnicalState,
    ReasonCode,
    Stage,
    StageEventTargetType,
    StageStatus,
    ValidationState,
)
from src.models.relevance import RELEVANT_SCOPE_CLASSES, RelevanceDecision
from src.models.retrieval_case import RetrievalCase
from src.models.stage_event import StageEvent
from src.pipeline.manifest import manifest_payload, write_manifest
from src.review.overrides import effective_decision
from src.review.queue import ReviewItem, merge_items, open_extraction_items

PROMPT_ID = "extract"
EXTRACT_INSTANT = datetime(2026, 10, 1, tzinfo=UTC)
_LABEL_FIELDS = (
    "target_subjects",
    "remembered_cues",
    "forgotten_information",
    "query_strategies",
    "system_responses",
    "workarounds",
    "impact_signals",
)


@dataclass(frozen=True)
class ExtractionInput:
    """One manifest document and the decision extraction is allowed to see."""

    doc_id: str
    decision: RelevanceDecision
    eligible: bool


@dataclass(frozen=True)
class LabelDisagreement:
    """Effective decision versus the approved seed label. Neither is changed."""

    doc_id: str
    decided_by: str
    effective_scope: str | None
    effective_reason: str
    approved_scope: str
    approved_reason: str


@dataclass
class ExtractionRunResult:
    run_id: str
    candidates: int
    eligible: int
    blocked: tuple[str, ...]
    attempted: int
    provider_calls: int
    cache_hits: int
    cache_misses: int
    valid_cases: int
    failed_candidates: int
    files_written: tuple[str, ...] = ()
    disagreements: tuple[LabelDisagreement, ...] = ()
    dry_run: bool = False
    offline: bool = False
    output_dir: str = ""
    by_state: dict[str, int] = field(default_factory=dict)


def resolve_extraction_inputs(
    doc_ids: list[str] | tuple[str, ...],
    model_decisions: list[RelevanceDecision] | tuple[RelevanceDecision, ...],
    human_decisions: list[RelevanceDecision] | tuple[RelevanceDecision, ...],
) -> tuple[ExtractionInput, ...]:
    """Effective human decision when it is valid; otherwise the model decision.

    A pending human decision does not replace the model row. Eligibility is the
    extraction gate, not agreement with the approved label.
    """
    models = {row.doc_id: row for row in model_decisions}
    humans = [row for row in human_decisions]
    resolved: list[ExtractionInput] = []
    for doc_id in doc_ids:
        model = models.get(doc_id)
        if model is None:
            continue
        chosen = effective_decision(model, humans)
        eligible = (
            chosen.technical_state is DecisionTechnicalState.ok
            and chosen.validation_state is ValidationState.valid
            and chosen.scope_class in RELEVANT_SCOPE_CLASSES
        )
        resolved.append(ExtractionInput(doc_id=doc_id, decision=chosen, eligible=eligible))
    return tuple(resolved)


def label_disagreements(
    inputs: tuple[ExtractionInput, ...] | list[ExtractionInput],
    approved: dict[str, tuple[str, str]],
) -> tuple[LabelDisagreement, ...]:
    """Compare effective scope and reason with the seed sheet. Labels stay put."""
    found: list[LabelDisagreement] = []
    for item in inputs:
        label = approved.get(item.doc_id)
        if label is None:
            continue
        scope = None if item.decision.scope_class is None else item.decision.scope_class.value
        reason = item.decision.reason_code.value
        if scope != label[0] or reason != label[1]:
            found.append(
                LabelDisagreement(
                    doc_id=item.doc_id,
                    decided_by=item.decision.decided_by.value,
                    effective_scope=scope,
                    effective_reason=reason,
                    approved_scope=label[0],
                    approved_reason=label[1],
                )
            )
    return tuple(found)


def load_approved_labels(path: Path | str) -> dict[str, tuple[str, str]]:
    """Seed scope and reason only. Notes are not loaded."""
    import csv

    labels: dict[str, tuple[str, str]] = {}
    source = Path(path)
    if not source.is_file():
        return labels
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            labels[row["doc_id"]] = (row["human_scope_class"], row["human_reason_code"])
    return labels


def extraction_run_id(
    *,
    doc_ids: list[str],
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    offline: bool,
    dry_run: bool,
    limit: int | None,
    prompt_version_value: str | None = None,
) -> str:
    return sha1_short(
        "extract",
        prompt_version_value or prompt_version(PROMPT_ID),
        SCHEMA_VERSION,
        provider_name,
        model_name,
        temperature,
        max_tokens,
        offline,
        dry_run,
        "" if limit is None else limit,
        *doc_ids,
        length=12,
    )


def transmitted_extraction_schema(
    doc_id: str,
    *,
    provider_name: str,
) -> dict[str, Any]:
    """One schema object for the prompt and the structured-output request."""
    schema = extraction_schema(doc_id)
    if provider_name == "groq":
        from src.llm.providers.groq import groq_request_schema

        schema = groq_request_schema(schema, doc_id=doc_id, nullable_scalars=True)
    return schema


def extraction_request_identity(
    derived: DocumentDerived,
    *,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    prompt_version_value: str,
) -> dict[str, Any]:
    """Cache identity ``ModelGateway.complete`` builds for this document.

    Decoding includes the transmitted schema digest and the target ``doc_id``,
    matching the extraction call. The returned request text is the prompt that
    would be sent; callers compare a stored entry with it and do not call out.
    """
    from src.core.ids import cache_key
    from src.llm.gateway import _decoding_params

    schema = transmitted_extraction_schema(derived.doc_id, provider_name=provider_name)
    prompt = build_extraction_prompt(
        derived,
        prompt_version=prompt_version_value,
        transmitted_schema=schema,
    )
    digest = sha256_hex(json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    params = _decoding_params(
        provider_name,
        temperature=temperature,
        max_tokens=max_tokens,
        schema=schema,
    )
    params.update(doc_id=derived.doc_id, transmitted_schema_sha256=digest)
    key = cache_key(
        provider=provider_name,
        model=model_name,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version_value,
        schema_version=SCHEMA_VERSION,
        content_hash_value=derived.content_hash,
        decoding_params=params,
    )
    return {
        "cache_key": key,
        "provider": provider_name,
        "model": model_name,
        "prompt_id": PROMPT_ID,
        "prompt_version": prompt_version_value,
        "schema_version": SCHEMA_VERSION,
        "content_hash": derived.content_hash,
        "decoding_params": dict(sorted(params.items())),
        "request_text": prompt,
        "ruleset_version": None,
    }


def accept_extraction_response(raw_text: str, doc_id: str) -> ExtractionPayload:
    """Gateway response acceptance for one target, without a provider call.

    Syntax repair matches the gateway. A failure raises ``ValueError`` with a
    fixed message so generated text is not copied into the error.
    """
    from pydantic import ValidationError

    from src.llm.repair import parse_json_document

    try:
        parsed, _repaired = parse_json_document(raw_text)
    except json.JSONDecodeError:
        raise ValueError("response was not JSON after syntax repair") from None
    if not isinstance(parsed, dict):
        raise ValueError("response JSON was not an object")
    try:
        validated = ExtractionPayload.model_validate(parsed)
    except ValidationError:
        raise ValueError("response failed extraction schema validation") from None
    if validated.doc_id != doc_id:
        raise ValueError("response doc_id does not match the target")
    return validated


def run_extraction(
    *,
    doc_ids: list[str],
    model_decisions: list[RelevanceDecision],
    human_decisions: list[RelevanceDecision],
    derived_by_id: dict[str, DocumentDerived],
    output_dir: Path | str,
    approved_labels: dict[str, tuple[str, str]] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    offline: bool = False,
    resume: str | None = None,
    provider_name: str = "null",
    model_name: str = "",
    provider: StructuredProvider | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout_seconds: float = 60.0,
    max_retries: int = 1,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    cached_input_usd_per_million: float | None = None,
    cache_dir: Path | None = None,
    call_budget: int | None = None,
    denylist: tuple[str, ...] = (),
    config_hash: str = "",
    project_root: Path | None = None,
    recorded_at: datetime | None = None,
    prompt_version_value: str | None = None,
) -> ExtractionRunResult:
    """Run extraction for eligible documents. Dry-run writes nothing."""
    recorded_at = recorded_at or (EXTRACT_INSTANT if offline or dry_run else datetime.now(UTC))
    version = prompt_version_value or prompt_version(PROMPT_ID)
    from src.core.versions import EXTRACTION_PROMPT_BASELINE, EXTRACTION_PROMPT_CORRECTION, EXTRACTION_PROMPT_VERSION, EXTRACTION_PROMPT_CANDIDATE, EXTRACTION_PROMPT_DEV_CANDIDATE
    if version not in {EXTRACTION_PROMPT_BASELINE, EXTRACTION_PROMPT_VERSION, EXTRACTION_PROMPT_CORRECTION, EXTRACTION_PROMPT_CANDIDATE, EXTRACTION_PROMPT_DEV_CANDIDATE}:
        raise ValueError("unsupported extraction execution version")
    ordered = sorted(doc_ids)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater")
        ordered = ordered[:limit]
    inputs = resolve_extraction_inputs(ordered, model_decisions, human_decisions)
    disagreements = label_disagreements(inputs, approved_labels or {})
    blocked = tuple(item.doc_id for item in inputs if not item.eligible)
    eligible = [item for item in inputs if item.eligible]
    active_provider = "null" if offline or dry_run else provider_name
    run_id = extraction_run_id(
        doc_ids=ordered,
        provider_name=active_provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        offline=offline or dry_run,
        dry_run=dry_run,
        limit=limit,
        prompt_version_value=version,
    )
    destination = Path(output_dir) / run_id
    if dry_run:
        return ExtractionRunResult(
            run_id=run_id,
            candidates=len(inputs),
            eligible=len(eligible),
            blocked=blocked,
            attempted=0,
            provider_calls=0,
            cache_hits=0,
            cache_misses=0,
            valid_cases=0,
            failed_candidates=0,
            disagreements=disagreements,
            dry_run=True,
            offline=offline,
            output_dir=str(destination),
        )

    chosen = provider
    if chosen is None:
        chosen = select_provider(
            configured_name=provider_name,
            api_key=api_key,
            offline=offline,
        )
    cache_root = Path(cache_dir) if cache_dir is not None else destination.parent / "cache"
    gateway = ModelGateway(
        chosen,
        _cache(cache_root),
        provider_name=active_provider,
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
        cached_input_usd_per_million=cached_input_usd_per_million,
        call_budget=call_budget,
        denylist=tuple(value for value in (api_key, *denylist) if value),
    )
    done = _finished_targets(destination / "checkpoints.jsonl", resume)
    pending = [item for item in eligible if item.doc_id not in done]
    outcomes: list[_DocOutcome] = []
    for index, item in enumerate(pending):
        derived = derived_by_id.get(item.doc_id)
        if derived is None:
            raise ValueError(f"derived text is missing for {item.doc_id}")
        try:
            outcomes.append(
                _extract_one(
                    gateway,
                    item,
                    derived,
                    model_name=model_name,
                    prompt_version_value=version,
                    unattempted_documents=len(pending) - index - 1,
                    recorded_at=recorded_at,
                )
            )
        except ProviderFatalError as exc:
            outcomes.append(
                _DocOutcome(
                    item=item,
                    state=DecisionTechnicalState.provider_error,
                    message="the provider rejected the credentials",
                    diagnostic=exc.diagnostic,
                    request_identity=exc.request_identity,
                    withheld=_withheld_text(derived.raw_text_audit, gateway.denylist),
                )
            )
            break
        except ProviderBudgetError:
            break
    for item in inputs:
        if not item.eligible and item.doc_id not in done:
            cause = _skip_cause(item)
            outcomes.append(
                _DocOutcome(
                    item=item,
                    state=DecisionTechnicalState.evidence_validation_failed,
                    message=(
                        "valid out-of-scope relevance decision; extraction was not attempted"
                        if cause == "out_of_scope" else
                        "effective relevance decision is not valid for extraction"
                    ),
                    blocked=True,
                )
            )

    destination.mkdir(parents=True, exist_ok=True)
    files = _persist(
        destination,
        run_id=run_id,
        outcomes=outcomes,
        disagreements=disagreements,
        gateway=gateway,
        dry_run=False,
        offline=offline,
        config_hash=config_hash,
        project_root=project_root or Path.cwd(),
        candidates=len(inputs),
        eligible=len(eligible),
        blocked=blocked,
        recorded_at=recorded_at,
        prompt_version_value=version,
    )
    valid_cases = sum(1 for outcome in outcomes for result in outcome.results if _is_valid_case(result))
    failed = sum(1 for outcome in outcomes if outcome.blocked or outcome.state is not DecisionTechnicalState.ok or any(result.requires_review for result in outcome.results))
    by_state: dict[str, int] = {}
    for outcome in outcomes:
        by_state[outcome.state.value] = by_state.get(outcome.state.value, 0) + 1
    return ExtractionRunResult(
        run_id=run_id,
        candidates=len(inputs),
        eligible=len(eligible),
        blocked=blocked,
        attempted=sum(1 for outcome in outcomes if not outcome.blocked),
        provider_calls=gateway.usage.provider_calls,
        cache_hits=gateway.usage.cache_hits,
        cache_misses=gateway.usage.cache_misses,
        valid_cases=valid_cases,
        failed_candidates=failed,
        files_written=tuple(files),
        disagreements=disagreements,
        dry_run=False,
        offline=offline,
        output_dir=str(destination),
        by_state=by_state,
    )


def format_extraction_summary(result: ExtractionRunResult) -> str:
    """Counts only. No document text, labels, or notes."""
    lines = [
        "Extraction run",
        f"  run id               {result.run_id}",
        f"  dry run              {str(result.dry_run).lower()}",
        f"  offline              {str(result.offline).lower()}",
        f"  candidates           {result.candidates}",
        f"  eligible             {result.eligible}",
        f"  blocked              {len(result.blocked)}",
        f"  attempted            {result.attempted}",
        f"  provider calls       {result.provider_calls}",
        f"  cache hits           {result.cache_hits}",
        f"  cache misses         {result.cache_misses}",
        f"  valid cases          {result.valid_cases}",
        f"  failed candidates    {result.failed_candidates}",
        f"  disagreements        {len(result.disagreements)}",
        f"  files written        {len(result.files_written)}",
    ]
    lines.extend(f"  state {state:<14} {count}" for state, count in sorted(result.by_state.items()))
    return "\n".join(lines) + "\n"


def extraction_exit_code(result: ExtractionRunResult) -> int:
    """An accepted empty response is success; rejected candidates are failure."""
    return int(result.failed_candidates > 0)


@dataclass
class _DocOutcome:
    item: ExtractionInput
    state: DecisionTechnicalState
    message: str = ""
    results: tuple[ExtractionResult, ...] = ()
    blocked: bool = False
    from_cache: bool = False
    diagnostic: ProviderDiagnostic | None = None
    withheld: tuple[str, ...] = ()
    request_identity: dict[str, object] | None = None
    finish_reason: str | None = None


def _extract_one(
    gateway: ModelGateway,
    item: ExtractionInput,
    derived: DocumentDerived,
    *,
    model_name: str,
    prompt_version_value: str,
    unattempted_documents: int,
    recorded_at: datetime = EXTRACT_INSTANT,
) -> _DocOutcome:
    schema = transmitted_extraction_schema(item.doc_id, provider_name=gateway.provider_name)
    prompt = build_extraction_prompt(
        derived,
        prompt_version=prompt_version_value,
        transmitted_schema=schema,
    )
    digest = sha256_hex(
        json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    request_identity = {
        "provider": gateway.provider_name,
        "model": model_name,
        "prompt_id": PROMPT_ID,
        "prompt_version": prompt_version_value,
        "content_hash": derived.content_hash,
        "transmitted_schema_sha256": digest,
        "prompt_sha256": sha256_hex(prompt),
        "prompt_characters": len(prompt),
        "max_tokens": gateway.max_tokens,
        "requested_temperature": gateway.temperature,
    }
    try:
        completed = gateway.complete(
            prompt=prompt,
            schema=schema,
            response_model=ExtractionPayload,
            content_hash=derived.content_hash,
            prompt_id=PROMPT_ID,
            prompt_version=prompt_version_value,
            ruleset_version=None,
            taxonomy_version=None,
            decoding={"doc_id": item.doc_id, "transmitted_schema_sha256": digest},
            unattempted_documents=unattempted_documents,
        )
    except ProviderFatalError as exc:
        exc.request_identity = request_identity
        raise
    if completed.technical_state is not DecisionTechnicalState.ok or not isinstance(
        completed.validated, ExtractionPayload
    ):
        return _DocOutcome(
            item=item,
            state=completed.technical_state,
            message=completed.message or completed.technical_state.value,
            from_cache=completed.from_cache,
            diagnostic=completed.diagnostic,
            request_identity=request_identity,
            finish_reason=completed.finish_reason,
            withheld=_withheld_text(derived.raw_text_audit, gateway.denylist),
        )
    try:
        results = assemble_cases(
            completed.validated,
            derived,
            item.decision,
            model_name=model_name,
            prompt_version=prompt_version_value,
            extracted_at=recorded_at,
        )
    except ValueError as exc:
        return _DocOutcome(
            item=item,
            state=DecisionTechnicalState.schema_validation_failed,
            message=str(exc)[:300],
            from_cache=completed.from_cache,
            request_identity=request_identity,
            finish_reason=completed.finish_reason,
        )
    state = DecisionTechnicalState.ok
    # A schema failure prevents record validation. Preserve that distinction;
    # for mixed documents schema failures take precedence in the document tally.
    if any(result.technical_state is DecisionTechnicalState.schema_validation_failed
           for result in results):
        state = DecisionTechnicalState.schema_validation_failed
    elif any(result.requires_review for result in results):
        state = DecisionTechnicalState.evidence_validation_failed
    return _DocOutcome(
        item=item,
        state=state,
        results=results,
        from_cache=completed.from_cache,
        withheld=_withheld_text(derived.raw_text_audit, gateway.denylist),
        request_identity=request_identity,
        finish_reason=completed.finish_reason,
    )


def _is_valid_case(result: ExtractionResult) -> bool:
    return (
        result.case is not None
        and result.technical_state is DecisionTechnicalState.ok
        and result.case.validation_state is ValidationState.valid
    )


def _persist(
    destination: Path,
    *,
    run_id: str,
    outcomes: list[_DocOutcome],
    disagreements: tuple[LabelDisagreement, ...],
    gateway: ModelGateway,
    dry_run: bool,
    offline: bool,
    config_hash: str,
    project_root: Path,
    candidates: int,
    eligible: int,
    blocked: tuple[str, ...],
    recorded_at: datetime = EXTRACT_INSTANT,
    prompt_version_value: str | None = None,
) -> list[str]:
    valid_cases = [
        result.case
        for outcome in outcomes
        for result in outcome.results
        if result.case is not None and _is_valid_case(result)
    ]
    analysis_cases = list(select_valid_for_analysis(valid_cases))
    _write_models(destination / "retrieval_cases.jsonl", _merge_cases(destination / "retrieval_cases.jsonl", analysis_cases), "case_id")
    _write_json(destination / "case_labels.jsonl", _label_rows(analysis_cases))
    _write_json(destination / "evidence_spans.jsonl", _span_rows(outcomes))
    _write_json(destination / "span_validations.jsonl", _verdict_rows(outcomes))
    _write_json(destination / "extraction_failures.jsonl", _failure_rows(outcomes, recorded_at=recorded_at))
    _write_json(destination / "extraction_candidates.jsonl", _candidate_rows(destination, outcomes))
    _write_json(destination / "extraction_inputs.jsonl", _input_rows(outcomes))
    reviews = _merge_reviews(destination / "review_queue.jsonl", run_id, outcomes, recorded_at=recorded_at)
    _write_models(destination / "review_queue.jsonl", reviews, "item_id")
    events = _events(run_id, outcomes, recorded_at=recorded_at)
    _append_jsonl(destination / "stage_events.jsonl", [event.model_dump(mode="json") for event in events])
    _append_checkpoints(destination / "checkpoints.jsonl", run_id, outcomes)
    _write_json(
        destination / "label_disagreements.jsonl",
        [
            {
                "doc_id": row.doc_id,
                "decided_by": row.decided_by,
                "effective_scope": row.effective_scope,
                "effective_reason": row.effective_reason,
                "approved_scope": row.approved_scope,
                "approved_reason": row.approved_reason,
            }
            for row in disagreements
        ],
    )
    write_manifest(
        destination / "run_manifest.json",
        _execution_manifest(
            prompt_version_value=prompt_version_value,
            run_id=run_id,
            stages=["extract"],
            dry_run=dry_run,
            offline=offline,
            config_hash=config_hash,
            project_root=project_root,
            funnel={
                "candidates": candidates,
                "eligible": eligible,
                "blocked": list(blocked),
                "valid_cases": len(analysis_cases),
                "by_state": {
                    outcome.state.value: sum(1 for item in outcomes if item.state is outcome.state)
                    for outcome in outcomes
                },
            },
            cache={
                "hits": gateway.usage.cache_hits,
                "misses": gateway.usage.cache_misses,
                "provider_calls": gateway.usage.provider_calls,
            },
            tokens={
                "input_tokens": gateway.usage.input_tokens,
                "output_tokens": gateway.usage.output_tokens,
                "estimated_cost_usd": round(gateway.usage.estimated_cost_usd, 6),
                "usage_scope": "recorded_provider_usage_only",
                "provider_calls_without_recorded_usage": gateway.usage.provider_calls_without_recorded_usage,
                "usage_totals_complete": gateway.usage.provider_calls_without_recorded_usage == 0,
            },
            output_hashes={},
            generated_at=recorded_at,
        ),
    )
    return [
        "retrieval_cases.jsonl",
        "case_labels.jsonl",
        "evidence_spans.jsonl",
        "span_validations.jsonl",
        "extraction_failures.jsonl",
        "extraction_candidates.jsonl",
        "extraction_inputs.jsonl",
        "review_queue.jsonl",
        "stage_events.jsonl",
        "checkpoints.jsonl",
        "label_disagreements.jsonl",
        "run_manifest.json",
    ]


def _execution_manifest(*, prompt_version_value: str | None, **kwargs) -> dict:
    """Record a scoped evaluation version without moving the legacy runner pin."""
    payload = manifest_payload(**kwargs)
    if prompt_version_value is not None:
        payload["versions"]["prompt_versions"]["extract"] = prompt_version_value
    return payload


def _candidate_rows(destination: Path, outcomes: list[_DocOutcome]) -> list[dict[str, object]]:
    """Typed review candidates, separate from analysis and raw response bodies."""
    by_id = {row["case_id"]: row for row in _read_jsonl(destination / "extraction_candidates.jsonl")}
    for outcome in outcomes:
        for result in outcome.results:
            if not result.requires_review:
                by_id.pop(result.case_id, None)
                continue
            by_id[result.case_id] = {
                "case_id": result.case_id,
                "doc_id": outcome.item.doc_id,
                "technical_state": result.technical_state.value,
                "analysis_eligible": False,
                "candidate": result.candidate.model_dump(mode="json"),
                "case": None if result.case is None else result.case.model_dump(mode="json"),
            }
    return [by_id[key] for key in sorted(by_id)]


def _label_rows(cases: list[RetrievalCase]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in cases:
        for name in _LABEL_FIELDS:
            for label in getattr(case, name):
                value = label.value.value if hasattr(label.value, "value") else label.value
                rows.append(
                    {
                        "case_id": case.case_id,
                        "doc_id": case.doc_id,
                        "dimension": name,
                        "value": value,
                        "detail": label.detail,
                        "evidence_id": label.evidence.evidence_id,
                    }
                )
    rows.sort(key=lambda row: (str(row["case_id"]), str(row["dimension"]), str(row["evidence_id"])))
    return rows


def _span_rows(outcomes: list[_DocOutcome]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for outcome in outcomes:
        for result in outcome.results:
            for span in result.all_evidence_spans:
                rows.append(span.model_dump(mode="json"))
    rows.sort(key=lambda row: str(row.get("evidence_id", "")))
    return rows


def _verdict_rows(outcomes: list[_DocOutcome]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for outcome in outcomes:
        for result in outcome.results:
            for verdict in result.span_validations:
                rows.append(
                    {
                        "doc_id": outcome.item.doc_id,
                        "case_id": result.case_id,
                        "field_name": verdict.span.field_name,
                        "ok": verdict.ok,
                        "offset_state": verdict.span.offset_state.value,
                        "validation_state": verdict.span.validation_state.value,
                        "reason_code": None if verdict.reason_code is None else verdict.reason_code.value,
                        "quote": verdict.span.quote,
                        "start_char": verdict.span.start_char,
                        "end_char": verdict.span.end_char,
                        "candidate_quote": verdict.original.quote,
                        "candidate_start_char": verdict.original.start_char,
                        "candidate_end_char": verdict.original.end_char,
                        "candidate_offset_state": verdict.original.offset_state.value,
                        "repair_applied": verdict.repaired,
                    }
                )
    return rows


def _failure_rows(outcomes: list[_DocOutcome], *, recorded_at: datetime = EXTRACT_INSTANT) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for outcome in outcomes:
        if outcome.blocked or (
            outcome.state is not DecisionTechnicalState.ok and not outcome.results
        ):
            row = {
                "doc_id": outcome.item.doc_id,
                "decision_id": outcome.item.decision.decision_id,
                "decided_by": outcome.item.decision.decided_by.value,
                "stage": Stage.extract.value,
                "attempt": 1,
                "error_class": outcome.state.value,
                "validation_errors": [outcome.message] if outcome.message else [],
                "raw_response_ref": None,
                "occurred_at": recorded_at.isoformat(),
                "request_identity": outcome.request_identity,
                "finish_reason": outcome.finish_reason,
            }
            recorded = _recorded_diagnostic(outcome.diagnostic, outcome.withheld)
            if recorded is not None:
                row["provider_diagnostic"] = recorded
            if outcome.blocked:
                row["skip_cause"] = _skip_cause(outcome.item)
            rows.append(row)
        for result in outcome.results:
            if not result.requires_review:
                continue
            row = {
                "doc_id": outcome.item.doc_id,
                "decision_id": outcome.item.decision.decision_id,
                "decided_by": outcome.item.decision.decided_by.value,
                "case_id": result.case_id,
                "stage": Stage.extract.value,
                "attempt": 1,
                "error_class": result.technical_state.value,
                "validation_errors": list(result.error_fields) or [
                    None if result.review_reason_code is None else result.review_reason_code.value
                ],
                "raw_response_ref": None,
                "occurred_at": recorded_at.isoformat(),
                "request_identity": outcome.request_identity,
                "finish_reason": outcome.finish_reason,
            }
            gate = result.record_validation
            if gate is not None:
                row.update(
                    reason_codes=[code.value for code in gate.reason_codes],
                    invalid_fields=list(gate.invalid_fields),
                    retained_span_ids=[span.evidence_id for span in gate.retained_spans],
                    # Bound generated prose and apply the existing source/secret filter
                    # before truncation; machine-readable findings remain complete.
                    gate_errors=[
                        message[:500]
                        for message in gate.errors[:32]
                        if not any(secret in message for secret in outcome.withheld)
                    ],
                )
            rows.append(row)
    return rows


def _input_rows(outcomes: list[_DocOutcome]) -> list[dict[str, object]]:
    rows = [
        {
            "doc_id": outcome.item.doc_id,
            "decision_id": outcome.item.decision.decision_id,
            "decided_by": outcome.item.decision.decided_by.value,
            "scope_class": None
            if outcome.item.decision.scope_class is None
            else outcome.item.decision.scope_class.value,
            "eligible": outcome.item.eligible,
            "technical_state": outcome.state.value,
            "request_identity": outcome.request_identity,
            "finish_reason": outcome.finish_reason,
            "from_cache": outcome.from_cache,
            **({} if not outcome.blocked else {"skip_cause": _skip_cause(outcome.item)}),
        }
        for outcome in outcomes
    ]
    rows.sort(key=lambda row: str(row["doc_id"]))
    return rows


def _events(run_id: str, outcomes: list[_DocOutcome], *, recorded_at: datetime = EXTRACT_INSTANT) -> list[StageEvent]:
    events: list[StageEvent] = []
    for outcome in outcomes:
        if outcome.blocked:
            status = StageStatus.skipped
            reason: ReasonCode | None = ReasonCode.evidence_validation_failed
        elif outcome.state is DecisionTechnicalState.ok:
            status = StageStatus.succeeded
            reason = None
        else:
            status = StageStatus.failed
            reason = _event_reason(outcome)
        detail = {
            "decision_id": outcome.item.decision.decision_id,
            "decided_by": outcome.item.decision.decided_by.value,
            "case_count": len(outcome.results),
            "valid_case_count": sum(1 for result in outcome.results if _is_valid_case(result)),
            "request_identity": outcome.request_identity,
            "finish_reason": outcome.finish_reason,
        }
        if outcome.blocked:
            detail["skip_cause"] = _skip_cause(outcome.item)
        recorded = _recorded_diagnostic(outcome.diagnostic, outcome.withheld)
        if recorded is not None:
            detail["provider_diagnostic"] = recorded
        events.append(
            StageEvent(
                event_id=event_id(run_id, Stage.extract.value, outcome.item.doc_id, 1, status.value),
                target_type=StageEventTargetType.document,
                target_id=outcome.item.doc_id,
                stage=Stage.extract,
                status=status,
                reason_code=reason,
                attempt=1,
                run_id=run_id,
                occurred_at=recorded_at,
                detail=detail,
            )
        )
    return events


def _skip_cause(item: ExtractionInput) -> str:
    """Separate a correct scope exclusion from a rejected relevance decision.

    The stage-event schema still requires a review-group reason on every
    skipped extraction. ``skip_cause`` is the accurate distinction; it does
    not weaken the evidence gate or rewrite a saved run.
    """
    decision = item.decision
    if (
        decision.technical_state is DecisionTechnicalState.ok
        and decision.validation_state is ValidationState.valid
        and decision.scope_class not in RELEVANT_SCOPE_CLASSES
    ):
        return "out_of_scope"
    return "relevance_not_accepted"


def _event_reason(outcome: _DocOutcome) -> ReasonCode:
    if outcome.state is DecisionTechnicalState.schema_validation_failed:
        return ReasonCode.schema_validation_failed
    for result in outcome.results:
        if result.review_reason_code is not None:
            return result.review_reason_code
    mapping = {
        DecisionTechnicalState.provider_unavailable: ReasonCode.provider_unavailable,
        DecisionTechnicalState.provider_error: ReasonCode.provider_unavailable,
        DecisionTechnicalState.timeout: ReasonCode.provider_unavailable,
        DecisionTechnicalState.rate_limited: ReasonCode.rate_limited,
        DecisionTechnicalState.schema_validation_failed: ReasonCode.schema_validation_failed,
        DecisionTechnicalState.response_parse_failed: ReasonCode.response_parse_failed,
        DecisionTechnicalState.evidence_validation_failed: ReasonCode.evidence_validation_failed,
    }
    return mapping.get(outcome.state, ReasonCode.schema_validation_failed)


def _review_pairs(run_id: str, outcomes: list[_DocOutcome]) -> list[tuple[str, str, ReasonCode]]:
    pairs: list[tuple[str, str, ReasonCode]] = []
    for outcome in outcomes:
        if outcome.blocked:
            if _skip_cause(outcome.item) != "out_of_scope":
                pairs.append(
                    ("relevance_decision", outcome.item.decision.decision_id, ReasonCode.evidence_validation_failed)
                )
            continue
        if not outcome.results and outcome.state is not DecisionTechnicalState.ok:
            pairs.append(
                ("extraction_attempt", f"{run_id}:{outcome.item.doc_id}", _event_reason(outcome))
            )
        for result in outcome.results:
            if result.requires_review and result.review_reason_code is not None:
                pairs.append(("retrieval_case", result.case_id, result.review_reason_code))
    return pairs


def _merge_reviews(path: Path, run_id: str, outcomes: list[_DocOutcome], *, recorded_at: datetime = EXTRACT_INSTANT) -> list[ReviewItem]:
    incoming = open_extraction_items(_review_pairs(run_id, outcomes), opened_at=recorded_at)
    existing = [ReviewItem.model_validate(row) for row in _read_jsonl(path)]
    return list(merge_items(existing, incoming))


def _append_checkpoints(path: Path, run_id: str, outcomes: list[_DocOutcome]) -> None:
    existing = _read_jsonl(path)
    seen = {
        (row.get("run_id"), row.get("stage"), row.get("target_id"), row.get("status"))
        for row in existing
    }
    extra: list[dict[str, str]] = []
    for outcome in outcomes:
        if outcome.blocked:
            status = StageStatus.skipped.value
        elif outcome.state is not DecisionTechnicalState.ok:
            status = StageStatus.failed.value
        else:
            status = StageStatus.succeeded.value
        item = {
            "run_id": run_id,
            "stage": Stage.extract.value,
            "target_id": outcome.item.doc_id,
            "status": status,
        }
        key = (item["run_id"], item["stage"], item["target_id"], item["status"])
        if key not in seen:
            extra.append(item)
            seen.add(key)
    lines = [json.dumps(row, sort_keys=True) for row in existing]
    lines.extend(json.dumps(row, sort_keys=True) for row in extra)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _finished_targets(path: Path, resume: str | None) -> set[str]:
    if not resume or not path.is_file():
        return set()
    found: set[str] = set()
    for row in _read_jsonl(path):
        if (
            row.get("run_id") == resume
            and row.get("stage") == Stage.extract.value
            and row.get("status") in {StageStatus.succeeded.value, StageStatus.skipped.value}
        ):
            found.add(str(row.get("target_id")))
    return found


def _merge_cases(path: Path, fresh: list[RetrievalCase]) -> list[RetrievalCase]:
    existing = [RetrievalCase.model_validate(row) for row in _read_jsonl(path)]
    by_id = {case.case_id: case for case in existing}
    for case in fresh:
        by_id[case.case_id] = case
    return [by_id[key] for key in sorted(by_id)]


def _withheld_text(audit: str, denylist: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value for value in (audit, *denylist) if value)


def _recorded_diagnostic(
    diagnostic: ProviderDiagnostic | None,
    withheld: tuple[str, ...],
) -> dict[str, object] | None:
    """Allowlisted diagnostic fields. Strings that repeat source text or a secret are omitted."""
    if diagnostic is None:
        return None
    recorded = diagnostic.as_dict()
    cleaned: dict[str, object] = {}
    for key, value in recorded.items():
        if isinstance(value, str) and any(secret in value for secret in withheld):
            continue
        cleaned[key] = value
    return cleaned


def _cache(cache_dir: Path):
    from src.llm.cache import ResponseCache

    return ResponseCache(cache_dir)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    extra = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(existing + extra, encoding="utf-8")


def _write_models(path: Path, records: list, key: str) -> None:
    rows = [record.model_dump(mode="json") for record in records]
    rows.sort(key=lambda row: str(row[key]))
    _write_json(path, rows)
