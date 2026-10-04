"""Checkpointed multi-source collection and a funnel counted by source.

YouTube and Reddit are attempted independently. A skipped or blocked source
is recorded and does not stop the other source. Manual JSONL already on disk
counts toward the corpus. This module does not call a model provider.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.analyze.funnel import build_funnel
from src.core.ids import event_id
from src.models.enums import ReasonCode, Stage, StageEventTargetType, StageStatus
from src.models.stage_event import StageEvent

CORPUS_TARGET = 300
SOURCE_TYPE_TARGET = 4
CONCENTRATION_THRESHOLD = 0.40

BASELINE_COLLECTIONS: tuple[str, ...] = (
    "data/processed/pilot-import/collected_documents.jsonl",
    "data/processed/pilot-import-35/collected_documents.jsonl",
    "data/processed/pilot-import-35-fixed/collected_documents.jsonl",
    "data/processed/youtube-discussion-2026-10-03/collected_documents.jsonl",
    "data/processed/youtube-discovery-2026-10-02/collected_documents.jsonl",
    "data/processed/community-webhook-parser-v2-check-2026-10-04-01/collected_documents.jsonl",
)

SourceRunner = Callable[[], dict[str, object]]


def load_rows(paths: list[Path]) -> list[dict[str, object]]:
    """Read JSONL objects. Missing files contribute nothing."""
    rows: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("doc_id"):
                rows.append(payload)
    return rows


def dedupe(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep the first row for each ``doc_id``."""
    chosen: dict[str, dict[str, object]] = {}
    for row in rows:
        chosen.setdefault(str(row["doc_id"]), row)
    return [chosen[key] for key in sorted(chosen)]


def run_scaled_collection(
    *,
    output_dir: Path,
    existing_paths: list[Path],
    youtube: SourceRunner | None,
    reddit: SourceRunner | None,
    resume: bool,
    run_id: str,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    """Run the supplied collectors, then write the deduped corpus and funnel.

    A collector is a callable that performs its own I/O and returns a count
    summary. When ``resume`` is set and the checkpoint already records that
    source as finished, the callable is not invoked.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    moment = occurred_at or datetime.now(timezone.utc)
    checkpoint_path = output_dir / "checkpoint.json"
    prior = _read_checkpoint(checkpoint_path) if resume else {}
    outcomes: list[dict[str, object]] = []
    for name, runner in (("youtube", youtube), ("reddit", reddit)):
        outcomes.append(_run_source(name, runner, prior))
    _write_json(checkpoint_path, {"run_id": run_id, "sources": {row["source"]: row for row in outcomes}})

    fresh = [
        output_dir / "youtube" / "collected_documents.jsonl",
        output_dir / "reddit" / "collected_documents.jsonl",
    ]
    rows = dedupe(load_rows([*existing_paths, *fresh]))
    corpus_path = output_dir / "collected_documents.jsonl"
    _write_jsonl(corpus_path, rows)
    events = _events(run_id, rows, outcomes, moment)
    _write_jsonl(output_dir / "stage_events.jsonl", [event.model_dump(mode="json") for event in events])
    report = _report(rows, outcomes, events)
    _write_json(output_dir / "funnel_by_source.json", report)
    return report


def _run_source(
    name: str,
    runner: SourceRunner | None,
    prior: dict[str, object],
) -> dict[str, object]:
    saved = prior.get(name)
    if isinstance(saved, dict) and saved.get("status") in {"collected", "skipped"}:
        return dict(saved)
    if runner is None:
        return {
            "source": name,
            "status": "skipped",
            "reason": "collector not configured",
            "requests_made": 0,
            "documents_written": 0,
            "stopped_reason": None,
        }
    try:
        outcome = runner()
    except Exception as exc:
        return {
            "source": name,
            "status": "failed",
            "reason": "source_blocked",
            "requests_made": 0,
            "documents_written": 0,
            "stopped_reason": exc.__class__.__name__,
        }
    outcome.setdefault("source", name)
    return outcome


def _events(
    run_id: str,
    rows: list[dict[str, object]],
    outcomes: list[dict[str, object]],
    occurred_at: datetime,
) -> list[StageEvent]:
    events: list[StageEvent] = []
    for outcome in outcomes:
        status, reason = _outcome_status(outcome)
        target = str(outcome.get("source") or "source")
        events.append(
            StageEvent(
                event_id=event_id(run_id, Stage.import_.value, target, 1, status.value),
                target_type=StageEventTargetType.batch,
                target_id=target,
                stage=Stage.import_,
                status=status,
                reason_code=reason,
                attempt=1,
                run_id=run_id,
                occurred_at=occurred_at,
                detail={
                    "requests_made": int(outcome.get("requests_made") or 0),
                    "documents_written": int(outcome.get("documents_written") or 0),
                    "stopped_reason": outcome.get("stopped_reason"),
                    "reason": outcome.get("reason"),
                },
            )
        )
    for row in rows:
        doc_id = str(row["doc_id"])
        events.append(
            StageEvent(
                event_id=event_id(run_id, Stage.import_.value, doc_id, 1, StageStatus.succeeded.value),
                target_type=StageEventTargetType.document,
                target_id=doc_id,
                stage=Stage.import_,
                status=StageStatus.succeeded,
                attempt=1,
                run_id=run_id,
                occurred_at=occurred_at,
                detail={"source_platform": row.get("source_platform")},
            )
        )
    events.sort(key=lambda event: event.event_id)
    return events


def _outcome_status(outcome: dict[str, object]) -> tuple[StageStatus, ReasonCode | None]:
    stopped = str(outcome.get("stopped_reason") or "")
    status = str(outcome.get("status") or "")
    if stopped in {"rate_limit", "rate_limited", "quota"} or status == "rate_limited":
        return StageStatus.unavailable, ReasonCode.rate_limited
    if status in {"failed", "source_blocked"} or stopped in {"source_blocked", "api_error", "transport_error"}:
        return StageStatus.failed, ReasonCode.source_blocked
    if status == "skipped":
        return StageStatus.skipped, ReasonCode.source_blocked
    return StageStatus.succeeded, None


def _report(
    rows: list[dict[str, object]],
    outcomes: list[dict[str, object]],
    events: list[StageEvent],
) -> dict[str, object]:
    platforms: Counter[str] = Counter(str(row.get("source_platform") or "unknown") for row in rows)
    kinds: Counter[str] = Counter(str(row.get("source_type") or "unknown") for row in rows)
    methods: Counter[str] = Counter(str(row.get("collection_method") or "unknown") for row in rows)
    total = sum(platforms.values())
    shares = {name: count / total for name, count in platforms.items()} if total else {}
    over = sorted(name for name, share in shares.items() if share > CONCENTRATION_THRESHOLD)
    document_events = [
        event for event in events if event.target_type is StageEventTargetType.document
    ]
    funnel = build_funnel(document_events)
    technical = sum(
        1
        for event in events
        if event.status in {StageStatus.failed, StageStatus.unavailable}
    )
    return {
        "documents": total,
        "by_platform": dict(platforms),
        "by_source_type": dict(kinds),
        "by_collection_method": dict(methods),
        "source_types": len(platforms),
        "item_kinds": len(kinds),
        "concentration_over_threshold": over,
        "concentration_threshold": CONCENTRATION_THRESHOLD,
        "corpus_target": CORPUS_TARGET,
        "source_type_target": SOURCE_TYPE_TARGET,
        "corpus_target_met": total >= CORPUS_TARGET and len(platforms) >= SOURCE_TYPE_TARGET,
        "sources": outcomes,
        "funnel": {
            "stages": funnel["stages"],
            "technical_failures": technical,
        },
        "model_stages_run": False,
    }


def _read_checkpoint(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    return sources if isinstance(sources, dict) else {}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
