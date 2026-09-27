"""Run normalization and deduplication.

The two stages do not import each other. This runner reads collected
documents, derives one row each, then detects links. Outputs are JSONL in
``doc_id`` / ``link_id`` order. Timestamps are the ruleset instant, not the
wall clock, so a second run writes the same bytes.

``data/interim/`` is gitignored. ``duplicate_review.csv`` is the operational
queue and contains only duplicate links. ``duplicate_calibration.csv`` is a
separate sheet for threshold review, including nearest out-of-band pairs.
Those controls are not links. ADR-11 is not amended here.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.core.config import DedupeConfig
from src.core.hashing import artifact_hash
from src.core.ids import event_id, sha1_short
from src.core.versions import DEDUPE_VERSION, NORMALIZER_VERSION
from src.dedupe.detect import PreparedDocument, detect_links
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    DuplicateReviewState,
    Stage,
    StageEventTargetType,
    StageStatus,
)
from src.models.stage_event import StageEvent
from src.normalize.derive import derive_document
from src.pipeline.calibration import select_calibration_rows, write_calibration_csv
from src.review.queue import open_items

#: Not a run timestamp. Re-running this ruleset stamps the same instant, which
#: is what "an identical derived row" requires (spec Section 15.6).
RULESET_INSTANT: datetime = datetime(2026, 9, 27, tzinfo=UTC)

DEFAULT_INPUT: Path = Path("data/processed/pilot-import/collected_documents.jsonl")
DEFAULT_OUTPUT: Path = Path("data/interim/phase3")

_EXCERPT_CHARS: int = 160


@dataclass(frozen=True)
class Phase3Result:
    """Counts safe to print. No document text."""

    document_count: int
    documents_with_redactions: int
    redaction_spans: int
    link_count: int
    auto_confirmed: int
    pending_review: int
    by_kind: dict[str, int]
    hamming_0_to_3: int
    hamming_4_to_6: int
    output_dir: Path
    derived_hash: str
    link_hash: str


def load_collected_documents(path: Path | str) -> list[CollectedDocument]:
    """Read a Phase 2 ``collected_documents.jsonl`` file, ordered by ``doc_id``."""
    source = Path(path)
    documents = [
        CollectedDocument.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    documents.sort(key=lambda document: document.doc_id)
    return documents


def run_normalize_dedupe(
    documents: list[CollectedDocument],
    config: DedupeConfig,
    output_dir: Path | str,
) -> Phase3Result:
    """Normalize every document, detect links, and write the local outputs."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    ordered = sorted(documents, key=lambda document: document.doc_id)
    originals = {document.doc_id: document.raw_text for document in ordered}

    derived = [
        derive_document(document, derived_at=RULESET_INSTANT) for document in ordered
    ]
    for document, row in zip(ordered, derived, strict=True):
        if document.raw_text != originals[document.doc_id]:
            raise RuntimeError(f"normalization mutated raw_text for {document.doc_id}")
        row.check_length_preserved(document.raw_text)

    prepared = [
        PreparedDocument(
            doc_id=document.doc_id,
            source_platform=document.source_platform.value,
            source_item_id=document.source_item_id,
            canonical_url=row.canonical_url,
            author_hash=document.author_hash,
            content_hash=row.content_hash,
            simhash=row.simhash,
            token_count=row.token_count,
            normalized_text=row.normalized_text,
        )
        for document, row in zip(ordered, derived, strict=True)
    ]
    links = detect_links(prepared, config, decided_at=RULESET_INSTANT)
    run_id = _run_id(ordered, config)
    events = _events(ordered, derived, links, run_id)
    queue = open_items(links, opened_at=RULESET_INSTANT)

    derived_path = destination / "documents_derived.jsonl"
    link_path = destination / "duplicate_links.jsonl"
    _write_jsonl(derived_path, derived, "doc_id")
    _write_jsonl(link_path, links, "link_id")
    _write_jsonl(destination / "stage_events.jsonl", events, "event_id")
    _write_jsonl(destination / "review_queue.jsonl", queue, "item_id")
    _write_review_csv(
        destination / "duplicate_review.csv",
        ordered,
        derived,
        links,
    )
    write_calibration_csv(
        destination / "duplicate_calibration.csv",
        select_calibration_rows(
            prepared,
            {row.doc_id: row.raw_text_audit for row in derived},
            links,
            config,
        ),
    )
    derived_rows = _read_rows(derived_path)
    link_rows = _read_rows(link_path)
    result = _result(
        ordered,
        derived,
        links,
        config,
        destination,
        artifact_hash(derived_rows, "doc_id"),
        artifact_hash(link_rows, "link_id"),
    )
    (destination / "phase3_summary.json").write_text(
        json.dumps(
            {
                "document_count": result.document_count,
                "documents_with_redactions": result.documents_with_redactions,
                "redaction_spans": result.redaction_spans,
                "link_count": result.link_count,
                "auto_confirmed": result.auto_confirmed,
                "pending_review": result.pending_review,
                "by_kind": result.by_kind,
                "hamming_0_to_3": result.hamming_0_to_3,
                "hamming_4_to_6": result.hamming_4_to_6,
                "derived_hash": result.derived_hash,
                "link_hash": result.link_hash,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def format_summary(result: Phase3Result) -> str:
    """Count summary. No document text, author names, or salt."""
    kinds = ", ".join(
        f"{name}={count}" for name, count in sorted(result.by_kind.items())
    ) or "none"
    lines = [
        "Normalize and dedupe complete",
        f"  documents            {result.document_count}",
        f"  with redactions      {result.documents_with_redactions}",
        f"  redaction spans      {result.redaction_spans}",
        f"  duplicate links      {result.link_count}",
        f"  auto confirmed       {result.auto_confirmed}",
        f"  pending review       {result.pending_review}",
        f"  hamming 0-3          {result.hamming_0_to_3}",
        f"  hamming 4-6          {result.hamming_4_to_6}",
        f"  kinds                {kinds}",
        f"  output               {result.output_dir}",
    ]
    return "\n".join(lines) + "\n"


def _run_id(documents: list[CollectedDocument], config: DedupeConfig) -> str:
    return sha1_short(
        NORMALIZER_VERSION,
        DEDUPE_VERSION,
        config.min_tokens,
        config.simhash_duplicate_max,
        config.simhash_review_band_max,
        *(document.doc_id for document in documents),
        length=12,
    )


def _events(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: tuple[DuplicateLink, ...],
    run_id: str,
) -> list[StageEvent]:
    link_counts: dict[str, int] = {}
    for link in links:
        link_counts[link.doc_id] = link_counts.get(link.doc_id, 0) + 1
        link_counts[link.canonical_doc_id] = link_counts.get(link.canonical_doc_id, 0) + 1
    events: list[StageEvent] = []
    for document, row in zip(documents, derived, strict=True):
        events.append(
            _event(
                run_id,
                Stage.normalize,
                document.doc_id,
                {
                    "redaction_count": len(row.redaction_spans),
                    "token_count": row.token_count,
                },
            )
        )
        events.append(
            _event(
                run_id,
                Stage.dedupe,
                document.doc_id,
                {"link_count": link_counts.get(document.doc_id, 0)},
            )
        )
    events.sort(key=lambda event: event.event_id)
    return events


def _event(run_id: str, stage: Stage, doc_id: str, detail: dict[str, int]) -> StageEvent:
    status = StageStatus.succeeded
    return StageEvent(
        event_id=event_id(run_id, stage.value, doc_id, 1, status.value),
        target_type=StageEventTargetType.document,
        target_id=doc_id,
        stage=stage,
        status=status,
        attempt=1,
        run_id=run_id,
        occurred_at=RULESET_INSTANT,
        detail=detail,
    )


def _write_jsonl(path: Path, records: list | tuple, key: str) -> None:
    rows = [record.model_dump(mode="json") for record in records]
    rows.sort(key=lambda row: str(row[key]))
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def _read_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_review_csv(
    path: Path,
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: tuple[DuplicateLink, ...],
) -> None:
    platforms = {document.doc_id: document.source_platform.value for document in documents}
    audits = {row.doc_id: row.raw_text_audit for row in derived}
    fieldnames = [
        "left_doc_id",
        "right_doc_id",
        "left_platform",
        "right_platform",
        "proposed_duplicate_kind",
        "hamming_distance",
        "decision_status",
        "left_excerpt",
        "right_excerpt",
        "researcher_decision",
    ]
    rows: list[dict[str, object]] = []
    for link in links:
        left_id = link.canonical_doc_id
        right_id = link.doc_id
        rows.append(
            {
                "left_doc_id": left_id,
                "right_doc_id": right_id,
                "left_platform": platforms.get(left_id, ""),
                "right_platform": platforms.get(right_id, ""),
                "proposed_duplicate_kind": link.duplicate_kind.value,
                "hamming_distance": link.method_detail.get("hamming_distance", ""),
                "decision_status": link.review_state.value,
                "left_excerpt": _excerpt(audits.get(left_id, "")),
                "right_excerpt": _excerpt(audits.get(right_id, "")),
                "researcher_decision": "",
            }
        )
    rows.sort(
        key=lambda row: (
            str(row["left_doc_id"]),
            str(row["right_doc_id"]),
            str(row["proposed_duplicate_kind"]),
        )
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _excerpt(audit: str) -> str:
    collapsed = " ".join(audit.split())
    return collapsed[:_EXCERPT_CHARS]


def _result(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: tuple[DuplicateLink, ...],
    config: DedupeConfig,
    output_dir: Path,
    derived_hash: str,
    link_hash: str,
) -> Phase3Result:
    by_kind: dict[str, int] = {}
    auto = 0
    pending = 0
    low = 0
    band = 0
    for link in links:
        by_kind[link.duplicate_kind.value] = by_kind.get(link.duplicate_kind.value, 0) + 1
        if link.review_state is DuplicateReviewState.auto_confirmed:
            auto += 1
        elif link.review_state is DuplicateReviewState.pending_review:
            pending += 1
        distance = int(link.method_detail.get("hamming_distance", 99))
        if distance <= config.simhash_duplicate_max:
            low += 1
        elif distance <= config.simhash_review_band_max:
            band += 1
    redaction_spans = sum(len(row.redaction_spans) for row in derived)
    with_redactions = sum(1 for row in derived if row.redaction_spans)
    return Phase3Result(
        document_count=len(documents),
        documents_with_redactions=with_redactions,
        redaction_spans=redaction_spans,
        link_count=len(links),
        auto_confirmed=auto,
        pending_review=pending,
        by_kind=by_kind,
        hamming_0_to_3=low,
        hamming_4_to_6=band,
        output_dir=output_dir,
        derived_hash=derived_hash,
        link_hash=link_hash,
    )

