"""Bounded scheduler for non-n8n collection and the existing research stages.

One run targets 50 new documents and processes them as sub-batches of at most
20, 20, and 10. The 20-document research-batch guard stays in place. n8n is
not called. Frozen split identifiers are excluded and their text is not read.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.collect.youtube import YoutubeCollectionError, collect_youtube_comments
from src.core.config import Settings, load_settings
from src.core.errors import ConfigError
from src.core.ids import cache_key, sha1_short
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION, prompt_version
from src.export.scheduled_status import publish_snapshot
from src.llm.cache import ResponseCache
from src.models.collected_document import CollectedDocument
from src.pipeline.research_batch import (
    MAX_DOCUMENTS,
    REVIEW_CHECKLIST,
    RESEARCH_MODEL,
    RESEARCH_PROVIDER,
    ResearchBatchError,
    assert_output_separate,
    selected_documents,
)

TARGET_DOCUMENTS = 50
SUB_BATCH_CAPS = (20, 20, 10)
COLLECTION_REQUESTS_PER_RUN = 20
MODEL_ATTEMPTS_PER_RUN = 100
COLLECTION_REQUESTS_PER_DAY = 60
MODEL_ATTEMPTS_PER_DAY = 300
SCHEDULE_HOURS = (8, 14, 20)
SCHEDULE_ZONE = ZoneInfo("Asia/Kolkata")
GATEWAY_ATTEMPTS = 1
STALE_LOCK_SECONDS = 6 * 60 * 60

_KNOWN_YOUTUBE_CORPUS = (
    Path("data/processed/youtube-discovery-2026-10-02/collected_documents.jsonl"),
    Path("data/processed/youtube-discussion-2026-10-03/collected_documents.jsonl"),
    Path("data/processed/phase7-corpus-2026-10-04/collected_documents.jsonl"),
)


class ScheduleError(RuntimeError):
    """The run cannot start. No request should be made."""


@dataclass(frozen=True)
class SchedulePaths:
    project_root: Path
    state_dir: Path
    output_root: Path
    snapshot_root: Path
    video_file: Path
    frozen_split: Path
    cache_dir: Path
    known_corpus: tuple[Path, ...] = ()


@dataclass
class ScheduleReport:
    """Counts and status. Document text and secrets stay out of this object."""

    run_id: str
    status: str
    dry_run: bool
    started_at: str
    finished_at: str
    next_run_at: str
    new_documents: int = 0
    duplicates: int = 0
    shortfall: int = TARGET_DOCUMENTS
    partial: bool = True
    sub_batches: tuple[int, ...] = ()
    sources: list[dict[str, Any]] = field(default_factory=list)
    excluded_sources: list[dict[str, str]] = field(default_factory=list)
    in_scope: int = 0
    adjacent: int = 0
    out_of_scope: int = 0
    extracted_cases: int = 0
    automatically_valid_cases: int = 0
    human_approved_cases: int = 0
    stage_failures: list[str] = field(default_factory=list)
    incomplete_work: list[str] = field(default_factory=list)
    collection_requests_used: int = 0
    model_attempts_used: int = 0
    estimated_cost_usd: float | None = None
    usage_known: bool = True
    missing_inputs: list[str] = field(default_factory=list)
    pins: dict[str, Any] = field(default_factory=dict)
    unreviewed_cases: list[dict[str, Any]] = field(default_factory=list)
    output_dir: str = ""
    message: str = ""

    @property
    def exit_code(self) -> int:
        if self.status in {"completed", "partial", "dry_run", "skipped_overlap"}:
            return 0
        return 1


def sub_batch_sizes(count: int) -> list[int]:
    """Split a selected batch into caps of 20, 20, and 10 without padding."""
    if count < 0 or count > TARGET_DOCUMENTS:
        raise ScheduleError(f"a scheduled batch contains 0 to {TARGET_DOCUMENTS} documents")
    sizes: list[int] = []
    remaining = count
    for cap in SUB_BATCH_CAPS:
        if remaining <= 0:
            break
        take = min(cap, remaining)
        if take > MAX_DOCUMENTS:
            raise ScheduleError("a sub-batch exceeds the 20-document runner guard")
        sizes.append(take)
        remaining -= take
    if remaining:
        raise ScheduleError("the sub-batch caps do not cover the selected documents")
    return sizes


def next_scheduled_at(now: datetime) -> datetime:
    """Next 08:00, 14:00, or 20:00 in Asia/Kolkata strictly after ``now``."""
    local = now.astimezone(SCHEDULE_ZONE)
    for hour in SCHEDULE_HOURS:
        candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > local:
            return candidate
    tomorrow = local + timedelta(days=1)
    return tomorrow.replace(hour=SCHEDULE_HOURS[0], minute=0, second=0, microsecond=0)


def default_paths(project_root: Path | None = None) -> SchedulePaths:
    root = (project_root or Path.cwd()).resolve()
    return SchedulePaths(
        project_root=root,
        state_dir=root / "data" / "interim" / "scheduler",
        output_root=root / "data" / "interim" / "scheduled-runs",
        snapshot_root=root / "data" / "exports" / "public" / "scheduled-snapshot",
        video_file=root / "config" / "youtube_seed_videos.txt",
        frozen_split=root / "data" / "interim" / "phase4" / "relevance_split_manifest.csv",
        cache_dir=root / "data" / "interim" / "cache",
        known_corpus=tuple(root / relative for relative in _KNOWN_YOUTUBE_CORPUS),
    )


def run_scheduled(
    paths: SchedulePaths,
    *,
    dry_run: bool,
    now: datetime | None = None,
    settings: Settings | None = None,
    collector: Callable[..., Any] | None = None,
    process_batch: Callable[..., dict[str, Any]] | None = None,
    pid: int | None = None,
    pid_alive: Callable[[int], bool] | None = None,
) -> ScheduleReport:
    """Plan or run one bounded batch. Dry-run writes nothing and calls nothing."""
    moment = now or datetime.now(SCHEDULE_ZONE)
    if moment.tzinfo is None:
        raise ScheduleError("scheduled time must be timezone-aware")
    loaded = settings if settings is not None else load_settings(project_root=paths.project_root)
    report = ScheduleReport(
        run_id=_run_id(moment, pid or os.getpid()),
        status="dry_run" if dry_run else "running",
        dry_run=dry_run,
        started_at=moment.astimezone(SCHEDULE_ZONE).isoformat(),
        finished_at="",
        next_run_at=next_scheduled_at(moment).isoformat(),
        sources=_source_plan(),
        excluded_sources=_excluded_sources(),
        pins=_pins(loaded),
    )
    missing = _missing_inputs(loaded, paths)
    if missing:
        report.missing_inputs = missing
        report.status = "missing_inputs"
        report.message = "Missing required input: " + ", ".join(missing)
        report.finished_at = datetime.now(SCHEDULE_ZONE).isoformat()
        return report
    if dry_run:
        report.shortfall = TARGET_DOCUMENTS
        report.partial = True
        report.estimated_cost_usd = 0.0
        report.usage_known = True
        report.message = (
            "Dry-run. Collection requests 0. Model attempts 0. Records written 0."
        )
        report.finished_at = datetime.now(SCHEDULE_ZONE).isoformat()
        return report

    lock = _Lock(paths.state_dir / "run.lock", pid_alive or _pid_alive)
    acquired = lock.acquire(pid or os.getpid(), moment)
    if not acquired:
        report.status = "skipped_overlap"
        report.message = "Another scheduled run holds the lock. This run made no requests."
        report.finished_at = datetime.now(SCHEDULE_ZONE).isoformat()
        return report
    try:
        _execute(paths, loaded, report, moment, collector, process_batch)
    except Exception as exc:
        report.stage_failures.append(exc.__class__.__name__)
        report.status = "failed"
        report.message = "The scheduled run failed and was not restarted."
    finally:
        lock.release()
        report.finished_at = datetime.now(SCHEDULE_ZONE).isoformat()
        if report.status != "missing_inputs":
            _publish(paths, report)
    return report


def format_schedule_report(report: ScheduleReport) -> str:
    """Operator summary. Shortfall is the first line when the batch is short."""
    lines: list[str] = []
    if report.partial and not report.dry_run and report.status != "skipped_overlap":
        lines.append(
            f"SHORTFALL {report.shortfall} of {TARGET_DOCUMENTS} new documents"
        )
    lines.extend(
        [
            f"Scheduled run {report.status}",
            f"  run id                 {report.run_id}",
            f"  dry run                {str(report.dry_run).lower()}",
            f"  started                {report.started_at}",
            f"  finished               {report.finished_at}",
            f"  next run               {report.next_run_at}",
            f"  new documents          {report.new_documents}",
            f"  duplicates             {report.duplicates}",
            f"  shortfall              {report.shortfall}",
            f"  sub-batches            {','.join(str(size) for size in report.sub_batches) or 'none'}",
            f"  in scope               {report.in_scope}",
            f"  adjacent               {report.adjacent}",
            f"  out of scope           {report.out_of_scope}",
            f"  extracted cases        {report.extracted_cases}",
            f"  automatically valid    {report.automatically_valid_cases}",
            f"  human approved         {report.human_approved_cases}",
            f"  collection requests    {report.collection_requests_used}",
            f"  model attempts         {report.model_attempts_used}",
            f"  estimated cost usd     {'unknown' if report.estimated_cost_usd is None else f'{report.estimated_cost_usd:.6f}'}",
            f"  output                 {report.output_dir or 'none'}",
        ]
    )
    if report.missing_inputs:
        lines.append("Missing inputs")
        lines.extend(f"  - {name}" for name in report.missing_inputs)
    if report.stage_failures:
        lines.append("Stage failures")
        lines.extend(f"  - {item}" for item in report.stage_failures)
    if report.incomplete_work:
        lines.append("Incomplete work")
        lines.extend(f"  - {item}" for item in report.incomplete_work)
    for source in report.sources:
        lines.append(
            "  source {source} status {status} requests {requests} new {documents}".format(
                source=source.get("source"),
                status=source.get("status"),
                requests=source.get("requests", 0),
                documents=source.get("documents_written", 0),
            )
        )
    if report.message:
        lines.append(report.message)
    return "\n".join(lines) + "\n"


def run_scheduled_cli(*, dry_run: bool, project_root: Path | None = None) -> int:
    """Entry point used by ``main.py schedule`` and Windows Task Scheduler."""
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    report = run_scheduled(default_paths(root), dry_run=dry_run)
    print(format_schedule_report(report), end="")
    return report.exit_code


def task_launcher(project_root: Path | None = None) -> Path:
    """Absolute command file the scheduled tasks launch."""
    root = (project_root or Path.cwd()).resolve()
    return root / "scripts" / "run_scheduled_discovery.cmd"


def _execute(
    paths: SchedulePaths,
    settings: Settings,
    report: ScheduleReport,
    now: datetime,
    collector: Callable[..., Any] | None,
    process_batch: Callable[..., dict[str, Any]] | None,
) -> None:
    output = assert_output_separate(paths.output_root / report.run_id)
    if output.exists():
        raise ScheduleError("scheduled run output already exists")
    ledger = _Ledger(paths.state_dir / "budget-ledger.json")
    seen = _ItemIndex(paths.state_dir / "seen_source_items.jsonl")
    processed = _ItemIndex(paths.state_dir / "processed_items.jsonl")
    pending_path = paths.state_dir / "pending_documents.jsonl"
    _seed_seen(seen, paths.known_corpus)
    pending = [
        document
        for document in _load_documents(pending_path)
        if _eligible_new(document, processed, _frozen_ids(paths.frozen_split))
    ]
    room = TARGET_DOCUMENTS - len(pending)
    collected: list[CollectedDocument] = []
    duplicates = 0
    if room > 0:
        collected, duplicates, requests = _collect(
            paths,
            settings,
            report,
            ledger,
            seen,
            output,
            now=now,
            document_limit=room,
            collector=collector or collect_youtube_comments,
        )
        report.collection_requests_used = requests
    else:
        _mark_youtube(report, status="not_needed", requests=0, documents=0, already=0)
    fresh = [
        document
        for document in collected
        if _eligible_new(document, processed, _frozen_ids(paths.frozen_split))
    ]
    blocked = ledger.blocked_doc_ids(_day_key(now))
    for doc_id in sorted(blocked):
        report.incomplete_work.append(
            f"{doc_id} has a reserved model attempt and was not requested again"
        )
    pool = [
        document
        for document in _dedupe([*pending, *fresh])
        if document.doc_id not in blocked
    ]
    selected = pool[:TARGET_DOCUMENTS]
    report.new_documents = len(selected)
    report.duplicates = duplicates
    report.shortfall = max(0, TARGET_DOCUMENTS - len(selected))
    report.partial = report.shortfall > 0
    sizes = sub_batch_sizes(len(selected))
    report.sub_batches = tuple(sizes)
    output.mkdir(parents=True, exist_ok=True)
    report.output_dir = str(output)
    _write_documents(pending_path, pool)
    cursor = 0
    done: set[str] = set()
    outcomes: list[dict[str, Any]] = []
    for index, size in enumerate(sizes, start=1):
        chunk = selected[cursor : cursor + size]
        cursor += size
        if not chunk:
            continue
        sub_output = output / f"sub-{index:02d}"
        sub_input = sub_output / "collected_documents.jsonl"
        sub_output.mkdir(parents=True, exist_ok=True)
        _write_documents(sub_input, chunk)
        try:
            guarded = selected_documents(
                sub_input,
                document_limit=len(chunk),
                frozen_split=paths.frozen_split,
                allow_synthetic=False,
            )
        except ResearchBatchError as exc:
            report.stage_failures.append(str(exc))
            report.status = "failed"
            break
        if len(guarded) > MAX_DOCUMENTS:
            raise ScheduleError("research batch guard returned more than 20 documents")
        processor = process_batch or _process_with_existing_stages
        outcome = processor(
            documents=guarded,
            output_dir=sub_output,
            paths=paths,
            settings=settings,
            ledger=ledger,
            run_id=report.run_id,
            now=now,
        )
        outcomes.append(outcome)
        unprocessed_ids = set(outcome.get("unprocessed_doc_ids") or [])
        processed_now = [document for document in guarded if document.doc_id not in unprocessed_ids]
        done.update(document.doc_id for document in processed_now)
        processed.add_many(
            [
                {
                    "source_platform": document.source_platform.value,
                    "source_item_id": document.source_item_id,
                    "raw_text_sha256": document.raw_text_sha256,
                    "doc_id": document.doc_id,
                    "run_id": report.run_id,
                }
                for document in processed_now
            ]
        )
        if outcome.get("stop"):
            report.stage_failures.extend(outcome.get("failures") or [])
            break
    _fold_outcomes(report, outcomes)
    if report.status != "failed":
        report.status = (
            "partial"
            if report.partial or report.incomplete_work or report.stage_failures
            else "completed"
        )
    if report.partial:
        report.message = (
            f"Partial batch: {report.new_documents} new documents, "
            f"shortfall {report.shortfall}. Limits were not increased."
        )
    _write_parent_manifest(output, report)
    _write_documents(
        pending_path,
        [document for document in pool if document.doc_id not in done],
    )


def _collect(
    paths: SchedulePaths,
    settings: Settings,
    report: ScheduleReport,
    ledger: _Ledger,
    seen: _ItemIndex,
    output: Path,
    *,
    now: datetime,
    document_limit: int,
    collector: Callable[..., Any],
) -> tuple[list[CollectedDocument], int, int]:
    day = _day_key(now)
    grant = ledger.reserve(
        day=day,
        run_id=report.run_id,
        kind="collection",
        count=COLLECTION_REQUESTS_PER_RUN,
        doc_ids=(),
    )
    if grant is None:
        report.incomplete_work.append("collection budget is exhausted")
        _mark_youtube(report, status="budget_exhausted", requests=0, documents=0, already=0)
        return [], 0, 0
    collection_dir = output / "collection"
    collection_dir.mkdir(parents=True, exist_ok=True)
    documents_path = collection_dir / "collected_documents.jsonl"
    _write_stubs(
        documents_path,
        seen.source_ids(),
        _complete_reply_counts(paths.known_corpus),
    )
    try:
        result = collector(
            paths.video_file,
            collection_dir,
            api_key=settings.secrets.youtube_api_key or "",
            author_salt=settings.secrets.author_salt or "",
            document_limit=document_limit,
            request_budget=grant.count,
            dry_run=False,
        )
    except (ConfigError, YoutubeCollectionError, FileNotFoundError):
        ledger.release(grant.reservation_id)
        raise
    except Exception as exc:
        report.stage_failures.append(f"collection failed: {exc.__class__.__name__}")
        _mark_youtube(report, status="failed", requests=grant.count, documents=0, already=0)
        return [], 0, grant.count
    requests = int(getattr(getattr(result, "report", result), "requests_made", 0))
    written = int(getattr(getattr(result, "report", result), "documents_written", 0))
    already = int(getattr(getattr(result, "report", result), "documents_already_present", 0))
    ledger.reconcile_collection(grant.reservation_id, requests)
    documents = _load_documents(documents_path)
    seen.add_many(
        [
            {
                "source_platform": document.source_platform.value,
                "source_item_id": document.source_item_id,
                "raw_text_sha256": document.raw_text_sha256,
                "doc_id": document.doc_id,
            }
            for document in documents
        ]
    )
    _mark_youtube(report, status="collected", requests=requests, documents=written, already=already)
    return documents, already, requests


def _process_with_existing_stages(
    *,
    documents: list[CollectedDocument],
    output_dir: Path,
    paths: SchedulePaths,
    settings: Settings,
    ledger: _Ledger,
    run_id: str,
    now: datetime,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Normalize, classify, extract, and queue review with the existing runners."""
    from src.llm.gateway import ProviderBudgetError
    from src.llm.providers.base import ProviderFatalError
    from src.llm.select import select_provider
    from src.models.document_derived import DocumentDerived
    from src.models.duplicate_link import DuplicateLink
    from src.models.relevance import RelevanceDecision
    from src.pipeline.extraction import resolve_extraction_inputs, run_extraction
    from src.pipeline.runner import RULESET_INSTANT, run_normalize_dedupe
    from src.pipeline.stages import non_canonical_map, run_phase4
    from src.relevance.prompts import PROMPT_ID
    from src.relevance.rules import prefilter_document

    if len(documents) > MAX_DOCUMENTS:
        raise ScheduleError("refusing to process more than 20 documents in one sub-batch")
    phase3 = run_normalize_dedupe(documents, settings.analysis.dedupe, output_dir / "normalize")
    derived_rows = [
        DocumentDerived.model_validate_json(line)
        for line in (output_dir / "normalize" / "documents_derived.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    link_path = output_dir / "normalize" / "duplicate_links.jsonl"
    link_lines = link_path.read_text(encoding="utf-8").splitlines() if link_path.is_file() else []
    links = [
        DuplicateLink.model_validate_json(line)
        for line in link_lines
        if line.strip()
    ]
    derived_by_id = {row.doc_id: row for row in derived_rows}
    skips = non_canonical_map(links)
    classify = []
    for document in documents:
        row = prefilter_document(
            document.doc_id,
            derived_by_id[document.doc_id].normalized_text,
            canonical_doc_id=skips.get(document.doc_id),
        )
        if row.passed:
            classify.append(document)
    cache = ResponseCache(paths.cache_dir)
    model_name = settings.models.groq_relevance_model
    if model_name != RESEARCH_MODEL:
        raise ScheduleError("scheduled relevance uses the configured Groq research model")
    uncached = [
        document
        for document in classify
        if not _relevance_cached(
            cache,
            document,
            derived_by_id[document.doc_id],
            model=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
        )
    ]
    day = _day_key(now)
    grant = None
    if uncached:
        grant = ledger.reserve(
            day=day,
            run_id=run_id,
            kind="model",
            stage="relevance",
            count=len(uncached),
            doc_ids=tuple(document.doc_id for document in uncached),
        )
    unprocessed: list[str] = []
    failures: list[str] = []
    if uncached and grant is None:
        failures.append("relevance budget is exhausted")
        return _empty_outcome(
            phase3.link_count,
            failures,
            [document.doc_id for document in documents],
            usage_known=True,
            estimated_cost_usd=0.0,
        )
    stage_documents = list(documents)
    if grant is not None and grant.count < len(uncached):
        allowed = set(grant.doc_ids)
        stage_documents = [
            document
            for document in documents
            if document.doc_id in allowed or document not in uncached
        ]
        unprocessed.extend(document.doc_id for document in uncached if document.doc_id not in allowed)
    chosen = provider or select_provider(
        configured_name=RESEARCH_PROVIDER,
        api_key=settings.secrets.groq_api_key,
        offline=False,
    )
    probe = _UsageProbe(chosen)
    relevance_dir = output_dir / "relevance"
    try:
        phase4 = run_phase4(
            stage_documents,
            derived_rows,
            links,
            output_dir=relevance_dir,
            stages=["prefilter", "relevance"],
            dry_run=False,
            offline=False,
            provider_name=RESEARCH_PROVIDER,
            model_name=model_name,
            api_key=settings.secrets.groq_api_key,
            author_salt=settings.secrets.author_salt,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            timeout_seconds=settings.models.timeout_seconds,
            max_retries=GATEWAY_ATTEMPTS,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            confidence_review_below=settings.analysis.relevance.confidence_review_below,
            config_hash=settings.config_hash(),
            project_root=settings.project_root,
            cache_dir=paths.cache_dir,
            provider_call_budget=0 if grant is None else grant.count,
            provider=probe,
        )
    except ProviderBudgetError:
        failures.append("relevance stopped when the reserved attempt budget was exhausted")
        return _empty_outcome(
            phase3.link_count,
            failures,
            unprocessed or [document.doc_id for document in documents],
            model_attempts=probe.calls,
        )
    except ProviderFatalError:
        failures.append("relevance authentication failed; no further model call was made")
        return _empty_outcome(
            phase3.link_count,
            failures,
            unprocessed,
            stop=True,
            model_attempts=probe.calls,
        )
    decisions = [
        RelevanceDecision.model_validate_json(line)
        for line in (relevance_dir / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    eligible = [
        item.doc_id
        for item in resolve_extraction_inputs(
            [document.doc_id for document in stage_documents], decisions, []
        )
        if item.eligible
    ]
    extract_uncached = [
        doc_id
        for doc_id in eligible
        if not _extraction_cached(
            cache,
            derived_by_id[doc_id],
            provider_name=RESEARCH_PROVIDER,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
        )
    ]
    extract_grant = None
    if extract_uncached:
        extract_grant = ledger.reserve(
            day=day,
            run_id=run_id,
            kind="model",
            stage="extract",
            count=len(extract_uncached),
            doc_ids=tuple(extract_uncached),
        )
    extract_ids = list(eligible)
    if extract_uncached and extract_grant is None:
        failures.append("extraction budget is exhausted")
        extract_ids = []
        unprocessed.extend(extract_uncached)
    elif extract_grant is not None and extract_grant.count < len(extract_uncached):
        allowed_ids = set(extract_grant.doc_ids)
        extract_ids = [doc_id for doc_id in eligible if doc_id in allowed_ids or doc_id not in extract_uncached]
        unprocessed.extend(doc_id for doc_id in extract_uncached if doc_id not in allowed_ids)
    extracted = 0
    valid = 0
    cases: list[dict[str, Any]] = []
    usage_known = probe.missing_usage == 0
    cost = phase4.estimated_cost_usd if usage_known else None
    attempts = phase4.provider_calls
    if extract_ids:
        try:
            extraction = run_extraction(
                doc_ids=extract_ids,
                model_decisions=decisions,
                human_decisions=[],
                derived_by_id=derived_by_id,
                approved_labels={},
                output_dir=output_dir / "extract",
                dry_run=False,
                offline=False,
                provider_name=RESEARCH_PROVIDER,
                model_name=model_name,
                provider=probe,
                api_key=settings.secrets.groq_api_key,
                temperature=settings.models.temperature,
                max_tokens=settings.models.max_tokens,
                timeout_seconds=settings.models.timeout_seconds,
                max_retries=GATEWAY_ATTEMPTS,
                input_usd_per_million=settings.models.estimated_input_usd_per_million,
                output_usd_per_million=settings.models.estimated_output_usd_per_million,
                cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
                cache_dir=paths.cache_dir,
                call_budget=0 if extract_grant is None else extract_grant.count,
                denylist=tuple(
                    secret
                    for secret in (settings.secrets.groq_api_key, settings.secrets.author_salt)
                    if secret
                ),
                config_hash=settings.config_hash(),
                project_root=settings.project_root,
            )
        except ProviderFatalError:
            failures.append("extraction authentication failed; no further model call was made")
            return _empty_outcome(phase3.link_count, failures, unprocessed, stop=True)
        attempts += extraction.provider_calls
        valid = extraction.valid_cases
        extracted, cases = _cases_from_output(output_dir / "extract", documents)
        manifest_path = output_dir / "extract" / "run_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tokens = manifest.get("tokens") if isinstance(manifest, dict) else None
            if isinstance(tokens, dict) and tokens.get("usage_totals_complete") is False:
                usage_known = False
                cost = None
            elif usage_known and isinstance(tokens, dict):
                recorded = tokens.get("estimated_cost_usd")
                cost = None if cost is None else cost + float(recorded or 0)
        if probe.missing_usage:
            usage_known = False
            cost = None
    elif not extract_ids and probe.missing_usage:
        usage_known = False
        cost = None
    scope = phase4.relevance_by_scope
    return {
        "duplicate_links": phase3.link_count,
        "in_scope": int(scope.get("core_incomplete_recall", 0)),
        "adjacent": int(scope.get("adjacent_known_item_retrieval", 0)),
        "out_of_scope": int(scope.get("out_of_scope", 0)),
        "extracted_cases": extracted,
        "automatically_valid_cases": valid,
        "failures": failures,
        "incomplete": unprocessed,
        "unprocessed_doc_ids": unprocessed,
        "model_attempts": attempts,
        "cache_hits": phase4.cache_hits,
        "estimated_cost_usd": cost,
        "usage_known": attempts == 0 or (usage_known and cost is not None),
        "review_items": phase4.review_items,
        "unreviewed_cases": cases,
        "stop": False,
        "prompt_id": PROMPT_ID,
        "ruleset_version": RULESET_VERSION,
        "ruleset_instant": RULESET_INSTANT.isoformat(),
    }


def _relevance_cached(
    cache: ResponseCache,
    document: CollectedDocument,
    derived: Any,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
) -> bool:
    from src.llm.providers.groq import cache_decoding_params, groq_request_schema
    from src.relevance.prompts import PROMPT_ID, relevance_json_schema

    schema = groq_request_schema(relevance_json_schema(), doc_id=document.doc_id)
    key = cache_key(
        provider=RESEARCH_PROVIDER,
        model=model,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version(PROMPT_ID),
        schema_version=SCHEMA_VERSION,
        content_hash_value=derived.content_hash,
        decoding_params=cache_decoding_params(
            temperature=temperature,
            max_tokens=max_tokens,
            schema=schema,
        ),
        ruleset_version=RULESET_VERSION,
    )
    return cache.read(PROMPT_ID, key) is not None


def _extraction_cached(
    cache: ResponseCache,
    derived: Any,
    *,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> bool:
    from src.pipeline.extraction import PROMPT_ID, extraction_request_identity

    identity = extraction_request_identity(
        derived,
        provider_name=provider_name,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        prompt_version_value=prompt_version(PROMPT_ID),
    )
    return cache.read(PROMPT_ID, str(identity["cache_key"])) is not None


def _cases_from_output(
    extract_dir: Path,
    documents: list[CollectedDocument],
) -> tuple[int, list[dict[str, Any]]]:
    urls = {document.doc_id: str(document.source_url) for document in documents}
    valid_ids = {
        str(row.get("case_id"))
        for row in _read_jsonl(extract_dir / "retrieval_cases.jsonl")
        if row.get("case_id")
    }
    spans_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(extract_dir / "evidence_spans.jsonl"):
        case_id = str(row.get("owner_id") or "")
        spans_by_case.setdefault(case_id, []).append(
            {
                "field_name": row.get("field_name"),
                "quote": row.get("quote"),
                "start_char": row.get("start_char"),
                "end_char": row.get("end_char"),
            }
        )
    cases: list[dict[str, Any]] = []
    for case_id in sorted(valid_ids):
        doc_id = ""
        for row in _read_jsonl(extract_dir / "retrieval_cases.jsonl"):
            if row.get("case_id") == case_id:
                doc_id = str(row.get("doc_id") or "")
                break
        cases.append(
            {
                "case_id": case_id,
                "doc_id": doc_id,
                "source_url": urls.get(doc_id, ""),
                "automatically_valid": True,
                "semantically_approved": False,
                "awaiting_semantic_review": True,
                "enters_approved_comparison": False,
                "evidence": spans_by_case.get(case_id, []),
                "review_checks": list(REVIEW_CHECKLIST),
            }
        )
    for row in _read_jsonl(extract_dir / "extraction_candidates.jsonl"):
        if row.get("case") is None:
            continue
        case_id = str(row.get("case_id") or "")
        if case_id in valid_ids:
            continue
        cases.append(
            {
                "case_id": case_id,
                "doc_id": str(row.get("doc_id") or ""),
                "source_url": urls.get(str(row.get("doc_id") or ""), ""),
                "automatically_valid": False,
                "semantically_approved": False,
                "awaiting_semantic_review": True,
                "enters_approved_comparison": False,
                "evidence": spans_by_case.get(case_id, []),
                "review_checks": list(REVIEW_CHECKLIST),
            }
        )
    return len(cases), cases


def _empty_outcome(
    duplicate_links: int,
    failures: list[str],
    unprocessed: list[str],
    *,
    stop: bool = False,
    model_attempts: int = 0,
    usage_known: bool = False,
    estimated_cost_usd: float | None = None,
) -> dict[str, Any]:
    return {
        "duplicate_links": duplicate_links,
        "in_scope": 0,
        "adjacent": 0,
        "out_of_scope": 0,
        "extracted_cases": 0,
        "automatically_valid_cases": 0,
        "failures": failures,
        "incomplete": unprocessed,
        "unprocessed_doc_ids": unprocessed,
        "model_attempts": model_attempts,
        "cache_hits": 0,
        "estimated_cost_usd": estimated_cost_usd,
        "usage_known": usage_known,
        "review_items": 0,
        "unreviewed_cases": [],
        "stop": stop,
    }


def _fold_outcomes(report: ScheduleReport, outcomes: list[dict[str, Any]]) -> None:
    costs: list[float] = []
    known = True
    for outcome in outcomes:
        report.duplicates += int(outcome.get("duplicate_links") or 0)
        report.in_scope += int(outcome.get("in_scope") or 0)
        report.adjacent += int(outcome.get("adjacent") or 0)
        report.out_of_scope += int(outcome.get("out_of_scope") or 0)
        report.extracted_cases += int(outcome.get("extracted_cases") or 0)
        report.automatically_valid_cases += int(outcome.get("automatically_valid_cases") or 0)
        report.model_attempts_used += int(outcome.get("model_attempts") or 0)
        report.stage_failures.extend(str(item) for item in outcome.get("failures") or [])
        report.incomplete_work.extend(str(item) for item in outcome.get("incomplete") or [])
        report.unreviewed_cases.extend(outcome.get("unreviewed_cases") or [])
        if outcome.get("usage_known") and outcome.get("estimated_cost_usd") is not None:
            costs.append(float(outcome["estimated_cost_usd"]))
        elif int(outcome.get("model_attempts") or 0) == 0 and outcome.get("usage_known", True):
            costs.append(0.0)
        else:
            known = False
    report.human_approved_cases = 0
    for case in report.unreviewed_cases:
        case["semantically_approved"] = False
        case["awaiting_semantic_review"] = True
        case["enters_approved_comparison"] = False
    if known:
        report.estimated_cost_usd = round(sum(costs), 6)
        report.usage_known = True
    else:
        report.estimated_cost_usd = None
        report.usage_known = False


def _publish(paths: SchedulePaths, report: ScheduleReport) -> None:
    payload = {
        "snapshot_version": report.run_id,
        "status": report.status,
        "dry_run": report.dry_run,
        "last_run_at": report.finished_at or report.started_at,
        "next_run_at": report.next_run_at,
        "timezone": "Asia/Kolkata",
        "schedule": [f"{hour:02d}:00" for hour in SCHEDULE_HOURS],
        "sources": report.sources,
        "excluded_sources": report.excluded_sources,
        "new_documents": report.new_documents,
        "duplicates": report.duplicates,
        "target_documents": TARGET_DOCUMENTS,
        "shortfall": report.shortfall,
        "partial": report.partial,
        "sub_batches": list(report.sub_batches),
        "in_scope": report.in_scope,
        "adjacent": report.adjacent,
        "out_of_scope": report.out_of_scope,
        "extracted_cases": report.extracted_cases,
        "automatically_valid_cases": report.automatically_valid_cases,
        "human_approved_cases": 0,
        "stage_failures": report.stage_failures,
        "incomplete_work": report.incomplete_work,
        "missing_inputs": report.missing_inputs,
        "collection_requests_used": report.collection_requests_used,
        "model_attempts_used": report.model_attempts_used,
        "collection_request_limit_per_run": COLLECTION_REQUESTS_PER_RUN,
        "model_attempt_limit_per_run": MODEL_ATTEMPTS_PER_RUN,
        "collection_request_limit_per_day": COLLECTION_REQUESTS_PER_DAY,
        "model_attempt_limit_per_day": MODEL_ATTEMPTS_PER_DAY,
        "estimated_cost_usd": report.estimated_cost_usd,
        "usage_known": report.usage_known,
        "pins": report.pins,
        "review_checks": list(REVIEW_CHECKLIST),
        "unreviewed_cases": report.unreviewed_cases,
        "message": report.message,
    }
    try:
        publish_snapshot(paths.snapshot_root, payload)
    except Exception as exc:
        report.stage_failures.append(f"snapshot publication failed: {exc.__class__.__name__}")


def _write_parent_manifest(output: Path, report: ScheduleReport) -> None:
    payload = {
        "run_id": report.run_id,
        "status": report.status,
        "new_documents": report.new_documents,
        "shortfall": report.shortfall,
        "partial": report.partial,
        "sub_batches": list(report.sub_batches),
        "collection_requests_used": report.collection_requests_used,
        "model_attempts_used": report.model_attempts_used,
        "estimated_cost_usd": report.estimated_cost_usd,
        "usage_known": report.usage_known,
        "pins": report.pins,
        "stage_failures": report.stage_failures,
        "incomplete_work": report.incomplete_work,
        "human_approved_cases": 0,
    }
    (output / "parent_manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _missing_inputs(settings: Settings, paths: SchedulePaths) -> list[str]:
    missing: list[str] = []
    if not settings.secrets.has("youtube_api_key"):
        missing.append("YOUTUBE_API_KEY")
    if not settings.secrets.has("author_salt"):
        missing.append("AUTHOR_SALT")
    if not settings.secrets.has("groq_api_key"):
        missing.append("GROQ_API_KEY")
    if not paths.video_file.is_file():
        missing.append(str(paths.video_file))
    elif not _video_file_has_url(paths.video_file):
        missing.append(f"{paths.video_file} has no YouTube video URL")
    if not paths.frozen_split.is_file():
        missing.append(str(paths.frozen_split))
    return missing


def _video_file_has_url(path: Path) -> bool:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            return True
    return False


def _pins(settings: Settings) -> dict[str, Any]:
    return {
        "provider": RESEARCH_PROVIDER,
        "model": settings.models.groq_relevance_model,
        "relevance_prompt": prompt_version("relevance"),
        "extraction_prompt": prompt_version("extract"),
        "schema_version": SCHEMA_VERSION,
        "temperature": settings.models.temperature,
        "max_tokens": settings.models.max_tokens,
        "gateway_attempts": GATEWAY_ATTEMPTS,
        "sdk_max_retries": 0,
        "configured_max_retries": settings.models.max_retries,
    }


def _source_plan() -> list[dict[str, Any]]:
    return [
        {
            "source": "youtube",
            "status": "planned",
            "requests": 0,
            "documents_written": 0,
            "documents_already_present": 0,
            "reason": "Official commentThreads.list and comments.list for configured video URLs.",
        },
        {
            "source": "reddit",
            "status": "unavailable",
            "requests": 0,
            "documents_written": 0,
            "documents_already_present": 0,
            "reason": (
                "Self-service Reddit API keys are not issued. "
                "This project does not request access."
            ),
        },
        {
            "source": "google_support",
            "status": "unavailable",
            "requests": 0,
            "documents_written": 0,
            "documents_already_present": 0,
            "reason": "No documented API. Automated collection is not enabled.",
        },
        {
            "source": "play_store",
            "status": "unavailable",
            "requests": 0,
            "documents_written": 0,
            "documents_already_present": 0,
            "reason": "Play reviews require publisher ownership. Manual import only.",
        },
        {
            "source": "app_store",
            "status": "unavailable",
            "requests": 0,
            "documents_written": 0,
            "documents_already_present": 0,
            "reason": "App Store reviews require ownership of the app. Manual import only.",
        },
    ]


def _excluded_sources() -> list[dict[str, str]]:
    return [
        {
            "source": "n8n",
            "status": "excluded",
            "reason": "n8n workflows, webhooks, and spreadsheets are outside this scheduler and were not called.",
        }
    ]


def _mark_youtube(
    report: ScheduleReport,
    *,
    status: str,
    requests: int,
    documents: int,
    already: int,
) -> None:
    for source in report.sources:
        if source.get("source") == "youtube":
            source["status"] = status
            source["requests"] = requests
            source["documents_written"] = documents
            source["documents_already_present"] = already


def _eligible_new(
    document: CollectedDocument,
    processed: _ItemIndex,
    frozen: set[str],
) -> bool:
    if document.doc_id in frozen or _is_n8n(document):
        return False
    if document.evidence_tier.value == "synthetic_test":
        return False
    return not processed.contains(document.source_platform.value, document.source_item_id, document.raw_text_sha256)


def _is_n8n(document: CollectedDocument) -> bool:
    collector = ""
    if isinstance(document.metadata, dict):
        collector = str(document.metadata.get("collector") or "")
    return collector == "n8n" or str(document.ingest_batch_id).startswith("n8n-")


def _frozen_ids(path: Path) -> set[str]:
    from src.pipeline.research_batch import load_frozen_ids

    return load_frozen_ids(path)


def _dedupe(documents: list[CollectedDocument]) -> list[CollectedDocument]:
    chosen: dict[str, CollectedDocument] = {}
    for document in documents:
        chosen.setdefault(document.doc_id, document)
    return [chosen[key] for key in sorted(chosen)]


def _seed_seen(index: _ItemIndex, paths: tuple[Path, ...]) -> None:
    rows: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        for row in _read_jsonl(path):
            if row.get("source_platform") not in {None, "youtube"}:
                continue
            item_id = row.get("source_item_id")
            if isinstance(item_id, str) and item_id:
                rows.append(
                    {
                        "source_platform": "youtube",
                        "source_item_id": item_id,
                        "raw_text_sha256": str(row.get("raw_text_sha256") or ""),
                        "doc_id": str(row.get("doc_id") or ""),
                    }
                )
    index.add_many(rows)


def _load_documents(path: Path) -> list[CollectedDocument]:
    documents: list[CollectedDocument] = []
    for row in _read_jsonl(path):
        if "raw_text" not in row:
            continue
        documents.append(CollectedDocument.model_validate(row))
    return documents


def _write_documents(path: Path, documents: list[CollectedDocument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(document.model_dump_json() + "\n" for document in documents),
        encoding="utf-8",
    )


def _complete_reply_counts(paths: tuple[Path, ...]) -> dict[str, int]:
    """Reply totals already stored as complete, keyed by thread id."""
    counts: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            continue
        for row in _read_jsonl(path):
            metadata = row.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("replies_complete") is not True:
                continue
            total = metadata.get("total_reply_count")
            thread_id = metadata.get("thread_id")
            if (
                isinstance(thread_id, str)
                and thread_id
                and isinstance(total, int)
                and not isinstance(total, bool)
                and total >= 0
            ):
                counts[thread_id] = max(counts.get(thread_id, 0), total)
    return counts


def _write_stubs(path: Path, source_ids: set[str], reply_counts: dict[str, int] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = reply_counts or {}
    lines: list[str] = []
    for item_id in sorted(source_ids):
        payload: dict[str, object] = {"source_item_id": item_id}
        if item_id in counts:
            payload["metadata"] = {
                "thread_id": item_id,
                "total_reply_count": counts[item_id],
                "replies_complete": True,
            }
        lines.append(json.dumps(payload, sort_keys=True) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _run_id(now: datetime, pid: int) -> str:
    return sha1_short("scheduled", now.isoformat(), str(pid), length=12)


def _day_key(now: datetime) -> str:
    return now.astimezone(SCHEDULE_ZONE).date().isoformat()


class _UsageProbe:
    """Count calls whose usage was not reported. The provider is not retried here."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.provider_name = getattr(inner, "provider_name", RESEARCH_PROVIDER)
        self.missing_usage = 0
        self.calls = 0

    def complete_structured(self, prompt: str, schema: Any, params: Any) -> Any:
        self.calls += 1
        try:
            response = self._inner.complete_structured(prompt, schema, params)
        except Exception:
            self.missing_usage += 1
            raise
        if not getattr(response, "usage_reported", False):
            self.missing_usage += 1
        return response


@dataclass
class _Reservation:
    reservation_id: str
    count: int
    doc_ids: tuple[str, ...]


class _Ledger:
    """Durable daily reservations. A restart does not clear consumed counts."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def reserve(
        self,
        *,
        day: str,
        run_id: str,
        kind: str,
        count: int,
        doc_ids: tuple[str, ...],
        stage: str = "",
    ) -> _Reservation | None:
        if count < 1:
            return None
        payload = self._load()
        bucket = payload["days"].setdefault(
            day,
            {"collection_requests": 0, "model_attempts": 0, "reservations": []},
        )
        day_limit = COLLECTION_REQUESTS_PER_DAY if kind == "collection" else MODEL_ATTEMPTS_PER_DAY
        run_limit = COLLECTION_REQUESTS_PER_RUN if kind == "collection" else MODEL_ATTEMPTS_PER_RUN
        day_used = _consumed(bucket, kind)
        run_used = _consumed(bucket, kind, run_id=run_id)
        grant = min(count, day_limit - day_used, run_limit - run_used)
        if grant < 1:
            return None
        granted_ids = doc_ids[:grant] if doc_ids else ()
        if doc_ids and len(granted_ids) != grant:
            grant = len(granted_ids)
        if grant < 1:
            return None
        reservation_id = sha1_short("reservation", run_id, kind, stage, day, str(len(bucket["reservations"])))
        bucket["reservations"].append(
            {
                "reservation_id": reservation_id,
                "run_id": run_id,
                "kind": kind,
                "stage": stage,
                "count": grant,
                "doc_ids": list(granted_ids),
                "status": "reserved",
            }
        )
        self._save(payload)
        return _Reservation(reservation_id, grant, granted_ids)

    def release(self, reservation_id: str) -> None:
        payload = self._load()
        for bucket in payload["days"].values():
            for item in bucket["reservations"]:
                if item["reservation_id"] == reservation_id and item["status"] == "reserved":
                    item["status"] = "released"
                    item["count"] = 0
        self._save(payload)

    def reconcile_collection(self, reservation_id: str, requests_made: int) -> None:
        payload = self._load()
        for bucket in payload["days"].values():
            for item in bucket["reservations"]:
                if item["reservation_id"] != reservation_id:
                    continue
                item["count"] = max(0, requests_made)
                item["status"] = "completed" if requests_made else "released"
        self._save(payload)

    def blocked_doc_ids(self, day: str) -> set[str]:
        payload = self._load()
        bucket = payload["days"].get(day) or {}
        blocked: set[str] = set()
        for item in bucket.get("reservations") or []:
            if item.get("kind") == "model" and item.get("status") in {"reserved", "completed", "failed"}:
                blocked.update(str(doc_id) for doc_id in item.get("doc_ids") or [])
        return blocked

    def consumed(self, day: str) -> tuple[int, int]:
        payload = self._load()
        bucket = payload["days"].get(day) or {"reservations": []}
        return _consumed(bucket, "collection"), _consumed(bucket, "model")

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": 1, "timezone": "Asia/Kolkata", "days": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("days"), dict):
            raise ScheduleError("budget ledger is unreadable and was not reset")
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


def _consumed(bucket: dict[str, Any], kind: str, *, run_id: str | None = None) -> int:
    total = 0
    for item in bucket.get("reservations") or []:
        if item.get("kind") != kind or item.get("status") == "released":
            continue
        if run_id is not None and item.get("run_id") != run_id:
            continue
        total += int(item.get("count") or 0)
    return total


class _ItemIndex:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows = _read_jsonl(path)

    def contains(self, platform: str, source_item_id: str, content_hash: str) -> bool:
        for row in self._rows:
            if (
                row.get("source_platform") == platform
                and row.get("source_item_id") == source_item_id
                and row.get("raw_text_sha256") == content_hash
            ):
                return True
        return False

    def source_ids(self) -> set[str]:
        return {
            str(row["source_item_id"])
            for row in self._rows
            if isinstance(row.get("source_item_id"), str) and row.get("source_item_id")
        }

    def add_many(self, rows: list[dict[str, str]]) -> None:
        if not rows:
            return
        known = {
            (row.get("source_platform"), row.get("source_item_id"), row.get("raw_text_sha256"))
            for row in self._rows
        }
        fresh = [
            row
            for row in rows
            if (row.get("source_platform"), row.get("source_item_id"), row.get("raw_text_sha256")) not in known
        ]
        if not fresh:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row) + "\n")
        self._rows.extend(fresh)


class _Lock:
    def __init__(self, path: Path, pid_alive: Callable[[int], bool]) -> None:
        self.path = path
        self._pid_alive = pid_alive
        self._held = False

    def acquire(self, pid: int, now: datetime) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": pid, "acquired_at": now.isoformat()}
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._active(now):
                    return False
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            self._held = True
            return True
        return False

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def _active(self, now: datetime) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
            acquired = datetime.fromisoformat(str(payload["acquired_at"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return False
        if not self._pid_alive(pid):
            return False
        age = now.astimezone(SCHEDULE_ZONE) - acquired.astimezone(SCHEDULE_ZONE)
        return age.total_seconds() < STALE_LOCK_SECONDS


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
