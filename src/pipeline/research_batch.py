"""Bounded research batch over documents that are not in the frozen seed split.

The five-document extraction pilot and the seed split stay untouched. This
module reads a collected JSONL, checks provenance, and plans normalize,
dedupe, relevance, and extraction with the existing stage functions. A dry-run
writes nothing and makes no provider call.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.core.config import DedupeConfig
from src.core.ids import doc_id, raw_text_sha256, source_url_key
from src.core.versions import prompt_version
from src.dedupe.detect import PreparedDocument, detect_links
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.models.enums import EvidenceTier
from src.normalize.derive import derive_document
from src.pipeline.runner import RULESET_INSTANT, load_collected_documents
from src.pipeline.stages import run_phase4

MAX_DOCUMENTS: int = 20
FROZEN_SPLIT: Path = Path("data/interim/phase4/relevance_split_manifest.csv")
CACHE_DIR: Path = Path("data/interim/cache")
RESEARCH_MODEL: str = "openai/gpt-oss-120b"
RESEARCH_PROVIDER: str = "groq"

REVIEW_CHECKLIST: tuple[str, ...] = (
    "retrieval_trigger must be the stated reason the item was needed, not the search method",
    "impact and severity need a quote that states that impact or severity",
    "problem_summary evidence must support every factual clause",
    "quotes must be one continuous span; invented or spliced text is invalid",
)

_PROTECTED: tuple[Path, ...] = (
    Path("data/interim/phase3"),
    Path("data/interim/phase4"),
    Path("data/interim/phase5"),
    Path("data/processed/pilot-import"),
    Path("data/processed/pilot-import-35"),
    Path("data/processed/pilot-import-35-fixed"),
)


class ResearchBatchError(ValueError):
    """The batch cannot be planned. No provider call should be made."""


@dataclass(frozen=True)
class ProvenanceFailure:
    doc_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ResearchBatchPlan:
    """Counts for one dry-run. No document text."""

    selected: int
    excluded_frozen: int
    held_back: int
    provenance_failures: tuple[ProvenanceFailure, ...]
    documents_with_redactions: int
    redaction_spans: int
    duplicate_links: int
    prefilter_classify: int
    prefilter_excluded: int
    relevance_requests: int
    extraction_request_ceiling: int
    provider_calls: int
    files_written: int


def load_frozen_ids(path: Path | str = FROZEN_SPLIT) -> set[str]:
    """Read the seed split. The file is not rewritten."""
    source = Path(path)
    if not source.is_file():
        raise ResearchBatchError("frozen split manifest was not found")
    with source.open(encoding="utf-8", newline="") as handle:
        return {row["doc_id"] for row in csv.DictReader(handle) if row.get("doc_id")}


def assert_output_separate(path: Path | str) -> Path:
    """Refuse the historical phase directories and the pilot imports."""
    output = Path(path)
    resolved = output.resolve()
    for protected in _PROTECTED:
        existing = protected.resolve()
        if resolved == existing or _is_inside(resolved, existing):
            raise ResearchBatchError(
                "research batch output must stay outside the frozen phase and pilot directories"
            )
    return output


def plan_research_batch(
    source: Path | str,
    output_dir: Path | str,
    *,
    document_limit: int,
    dedupe_config: DedupeConfig,
    frozen_split: Path | str = FROZEN_SPLIT,
    allow_synthetic: bool = False,
    model_name: str = RESEARCH_MODEL,
) -> ResearchBatchPlan:
    """Verify provenance and count each stage. Writes nothing and calls no model."""
    if document_limit < 1 or document_limit > MAX_DOCUMENTS:
        raise ResearchBatchError(f"document_limit must be from 1 to {MAX_DOCUMENTS}")
    assert_output_separate(output_dir)
    documents = load_collected_documents(source)
    frozen = load_frozen_ids(frozen_split)
    selected, excluded, held_back, failures = _select(
        documents,
        frozen_ids=frozen,
        limit=document_limit,
        allow_synthetic=allow_synthetic,
    )
    if failures:
        return ResearchBatchPlan(
            selected=0,
            excluded_frozen=excluded,
            held_back=0,
            provenance_failures=tuple(failures),
            documents_with_redactions=0,
            redaction_spans=0,
            duplicate_links=0,
            prefilter_classify=0,
            prefilter_excluded=0,
            relevance_requests=0,
            extraction_request_ceiling=0,
            provider_calls=0,
            files_written=0,
        )

    if not selected:
        return ResearchBatchPlan(
            selected=0,
            excluded_frozen=excluded,
            held_back=held_back,
            provenance_failures=(),
            documents_with_redactions=0,
            redaction_spans=0,
            duplicate_links=0,
            prefilter_classify=0,
            prefilter_excluded=0,
            relevance_requests=0,
            extraction_request_ceiling=0,
            provider_calls=0,
            files_written=0,
        )

    derived = [derive_document(document, derived_at=RULESET_INSTANT) for document in selected]
    originals = {document.doc_id: document.raw_text for document in selected}
    for document, row in zip(selected, derived, strict=True):
        if document.raw_text != originals[document.doc_id]:
            raise ResearchBatchError("normalization changed raw text")
        row.check_length_preserved(document.raw_text)
    links = detect_links(
        [_prepared(document, row) for document, row in zip(selected, derived, strict=True)],
        dedupe_config,
        decided_at=RULESET_INSTANT,
    )
    phase4 = run_phase4(
        list(selected),
        derived,
        links,
        output_dir=Path(output_dir) / "relevance",
        stages=["prefilter", "relevance"],
        dry_run=True,
        offline=True,
        provider_name="null",
        model_name=model_name,
        max_retries=1,
        provider_call_budget=0,
    )
    classify = phase4.classify_count
    return ResearchBatchPlan(
        selected=len(selected),
        excluded_frozen=excluded,
        held_back=held_back,
        provenance_failures=(),
        documents_with_redactions=sum(1 for row in derived if row.redaction_spans),
        redaction_spans=sum(len(row.redaction_spans) for row in derived),
        duplicate_links=len(links),
        prefilter_classify=classify,
        prefilter_excluded=phase4.obvious_exclusion_count,
        relevance_requests=classify,
        extraction_request_ceiling=classify,
        provider_calls=phase4.provider_calls,
        files_written=len(phase4.files_written),
    )


def format_research_plan(
    plan: ResearchBatchPlan,
    *,
    output_dir: Path | str,
    model_name: str,
    max_tokens: int,
) -> str:
    """Count summary and the review checklist. No document text."""
    relevance_version = prompt_version("relevance")
    extract_version = prompt_version("extract")
    lines = [
        "Research batch dry-run",
        f"  selected             {plan.selected}",
        f"  excluded frozen      {plan.excluded_frozen}",
        f"  held back            {plan.held_back}",
        f"  provenance failures  {len(plan.provenance_failures)}",
        f"  redacted documents   {plan.documents_with_redactions}",
        f"  redaction spans      {plan.redaction_spans}",
        f"  duplicate links      {plan.duplicate_links}",
        f"  prefilter classify   {plan.prefilter_classify}",
        f"  prefilter exclusion  {plan.prefilter_excluded}",
        f"  relevance requests   {plan.relevance_requests}",
        f"  extraction ceiling   {plan.extraction_request_ceiling}",
        f"  maximum external     {plan.relevance_requests + plan.extraction_request_ceiling}",
        f"  provider calls       {plan.provider_calls}",
        f"  files written        {plan.files_written}",
        f"  provider             {RESEARCH_PROVIDER}",
        f"  model                {model_name}",
        f"  max tokens           {max_tokens}",
        f"  max retries          1",
        f"  relevance prompt     {relevance_version}",
        f"  extraction prompt    {extract_version}",
        f"  cache                {CACHE_DIR}",
        f"  output               {output_dir}",
        "Semantic review checklist",
    ]
    lines.extend(f"  - {item}" for item in REVIEW_CHECKLIST)
    if plan.provenance_failures:
        lines.append("Provenance failures")
        for failure in plan.provenance_failures:
            lines.append(f"  {failure.doc_id} {','.join(failure.reasons)}")
    return "\n".join(lines) + "\n"


def selected_documents(
    source: Path | str,
    *,
    document_limit: int,
    frozen_split: Path | str = FROZEN_SPLIT,
    allow_synthetic: bool = False,
) -> list[CollectedDocument]:
    """Documents that would enter the batch. Provenance failures raise."""
    if document_limit < 1 or document_limit > MAX_DOCUMENTS:
        raise ResearchBatchError(f"document_limit must be from 1 to {MAX_DOCUMENTS}")
    documents = load_collected_documents(source)
    selected, _excluded, _held, failures = _select(
        documents,
        frozen_ids=load_frozen_ids(frozen_split),
        limit=document_limit,
        allow_synthetic=allow_synthetic,
    )
    if failures:
        raise ResearchBatchError("collection records failed provenance checks")
    return selected


def _select(
    documents: list[CollectedDocument],
    *,
    frozen_ids: set[str],
    limit: int,
    allow_synthetic: bool,
) -> tuple[list[CollectedDocument], int, int, list[ProvenanceFailure]]:
    failures: list[ProvenanceFailure] = []
    qualified: list[CollectedDocument] = []
    excluded = 0
    for document in sorted(documents, key=lambda item: item.doc_id):
        reasons = _provenance_reasons(document, allow_synthetic=allow_synthetic)
        if reasons:
            failures.append(ProvenanceFailure(document.doc_id, reasons))
            continue
        if document.doc_id in frozen_ids:
            excluded += 1
            continue
        qualified.append(document)
    held_back = max(0, len(qualified) - limit)
    return qualified[:limit], excluded, held_back, failures


def _provenance_reasons(
    document: CollectedDocument, *, allow_synthetic: bool
) -> tuple[str, ...]:
    reasons: list[str] = []
    if document.evidence_tier is EvidenceTier.synthetic_test and not allow_synthetic:
        reasons.append("synthetic_test")
    if not document.source_item_id:
        reasons.append("source_item_id")
    elif document.doc_id != doc_id(
        document.source_platform.value, source_item_id=document.source_item_id
    ):
        reasons.append("doc_id")
    if document.raw_text_sha256 != raw_text_sha256(document.raw_text):
        reasons.append("raw_text_sha256")
    if document.source_url_key != source_url_key(str(document.source_url)):
        reasons.append("source_url_key")
    if document.collected_at.tzinfo is None:
        reasons.append("collected_at")
    if not document.author_salt_id:
        reasons.append("author_salt_id")
    return tuple(reasons)


def _prepared(document: CollectedDocument, row: DocumentDerived) -> PreparedDocument:
    return PreparedDocument(
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


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
