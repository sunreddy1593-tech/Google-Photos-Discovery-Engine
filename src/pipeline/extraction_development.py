"""Development-split extraction for milestone M1.

Selection and request bounds live here. Completions, cache, evidence gates,
and persistence stay in ``run_extraction``. This module does not call a
provider SDK and does not retain holdout text.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from src.core.versions import EXTRACTION_PROMPT_VERSION, prompt_version
from src.extract.validator import validate_record
from src.models.document_derived import DocumentDerived
from src.models.enums import ValidationState
from src.models.evidence import EvidenceSpan
from src.models.retrieval_case import RetrievalCase
from src.pipeline.extraction import (
    PROMPT_ID,
    ExtractionRunResult,
    extraction_run_id,
    resolve_extraction_inputs,
    run_extraction,
)
from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER, planned_output_dir
from src.relevance.split import SPLIT_DEVELOPMENT, SPLIT_HOLDOUT, doc_ids_for_split, load_split_manifest

CORPUS_MAX_TOKENS = 8192
CORPUS_MAX_RETRIES = 1
DEFAULT_OUTPUT = Path("data/interim/phase5/development-corpus")
DEFAULT_CACHE = Path("data/interim/cache")
SPLIT_MANIFEST = Path("data/interim/phase4/relevance_split_manifest.csv")
DECISIONS_PATH = Path("data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl")
HUMAN_DECISIONS_PATH = Path(
    "data/interim/phase4/development/01455c8aab03/human_relevance_decisions.jsonl"
)
DERIVED_PATH = Path("data/interim/phase3/documents_derived.jsonl")
FUNNEL_SOURCES: tuple[tuple[Path, frozenset[str]], ...] = (
    (Path("data/interim/phase3/stage_events.jsonl"), frozenset({"normalize", "dedupe"})),
    (Path("data/interim/phase4/stage_events.jsonl"), frozenset({"prefilter"})),
    (
        Path("data/interim/phase4/development/01455c8aab03/stage_events.jsonl"),
        frozenset({"relevance"}),
    ),
)


class DevelopmentBoundsError(ValueError):
    """The development corpus would exceed its bounds or read the holdout."""


def development_ids(path: Path | str = SPLIT_MANIFEST) -> tuple[str, ...]:
    """Frozen development document ids. The manifest is not rewritten."""
    return doc_ids_for_split(load_split_manifest(path), SPLIT_DEVELOPMENT)


def holdout_ids(path: Path | str = SPLIT_MANIFEST) -> tuple[str, ...]:
    """Frozen holdout ids, used only to refuse them. Their text is not loaded."""
    return doc_ids_for_split(load_split_manifest(path), SPLIT_HOLDOUT)


def load_derived_for(path: Path | str, wanted: set[str]) -> dict[str, DocumentDerived]:
    """Keep derived rows for ``wanted`` ids and drop every other row."""
    found: dict[str, DocumentDerived] = {}
    source = Path(path)
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        preview = json.loads(line)
        doc_id = preview.get("doc_id")
        if doc_id not in wanted:
            continue
        found[str(doc_id)] = DocumentDerived.model_validate(preview)
    return found


def assert_development_bounds(
    *,
    doc_ids: Sequence[str],
    development: Sequence[str],
    holdout: Sequence[str],
    provider: str,
    model: str,
    max_retries: int,
    max_tokens: int,
    call_budget: int,
    eligible: int,
    split: str,
) -> None:
    """Require the full development split, one attempt, and the 8192-token limit."""
    chosen = set(doc_ids)
    if split != SPLIT_DEVELOPMENT:
        raise DevelopmentBoundsError("Holdout locked: development corpus extraction uses development documents only")
    if chosen & set(holdout):
        raise DevelopmentBoundsError("Holdout locked: a holdout document cannot be extracted")
    if chosen != set(development):
        raise DevelopmentBoundsError("development corpus extraction uses the full development split")
    if len(doc_ids) != len(chosen):
        raise DevelopmentBoundsError("development corpus document ids must be unique")
    if provider != PILOT_PROVIDER:
        raise DevelopmentBoundsError("development corpus extraction uses Groq")
    if model != PILOT_MODEL:
        raise DevelopmentBoundsError(f"development corpus extraction uses {PILOT_MODEL}")
    if max_retries != CORPUS_MAX_RETRIES:
        raise DevelopmentBoundsError("development corpus extraction allows one attempt and no gateway retry")
    if max_tokens != CORPUS_MAX_TOKENS:
        raise DevelopmentBoundsError(
            f"development corpus extraction uses the {CORPUS_MAX_TOKENS}-token completion limit"
        )
    if prompt_version(PROMPT_ID) != EXTRACTION_PROMPT_VERSION:
        raise DevelopmentBoundsError(f"development corpus extraction requires {EXTRACTION_PROMPT_VERSION}")
    if call_budget != eligible:
        raise DevelopmentBoundsError(
            f"development corpus extraction allows {eligible} external requests"
        )


def run_development_extraction(
    *,
    doc_ids: Sequence[str],
    development: Sequence[str],
    holdout: Sequence[str],
    model_decisions,
    human_decisions,
    derived_by_id,
    output_dir: Path | str,
    cache_dir: Path | str,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    max_retries: int,
    call_budget: int,
    split: str = SPLIT_DEVELOPMENT,
    dry_run: bool = False,
    api_key: str | None = None,
    provider=None,
    approved_labels: dict[str, tuple[str, str]] | None = None,
    timeout_seconds: float = 60.0,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    cached_input_usd_per_million: float | None = None,
    project_root: Path | None = None,
    config_hash: str = "",
) -> ExtractionRunResult:
    """Extract the development split through ``run_extraction``.

    Dry-run writes nothing and makes no provider call. A live run refuses an
    occupied destination and a missing key before creating one.
    """
    selected = sorted(doc_ids)
    inputs = resolve_extraction_inputs(selected, model_decisions, human_decisions)
    eligible = sum(1 for item in inputs if item.eligible)
    assert_development_bounds(
        doc_ids=selected,
        development=development,
        holdout=holdout,
        provider=provider_name,
        model=model_name,
        max_retries=max_retries,
        max_tokens=max_tokens,
        call_budget=call_budget,
        eligible=eligible,
        split=split,
    )
    destination = planned_output_dir(
        output_dir,
        selected,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
        offline=False,
    )
    if not dry_run and destination.exists():
        raise DevelopmentBoundsError("development corpus output already exists; refusing to merge into it")
    if not dry_run and provider is None and not api_key:
        raise DevelopmentBoundsError("GROQ_API_KEY is not set")
    if not dry_run:
        missing = [
            item.doc_id
            for item in inputs
            if item.eligible and item.doc_id not in derived_by_id
        ]
        if missing:
            raise DevelopmentBoundsError("derived text is missing for an eligible development document")
    return run_extraction(
        doc_ids=selected,
        model_decisions=list(model_decisions),
        human_decisions=list(human_decisions),
        derived_by_id=derived_by_id,
        approved_labels=approved_labels,
        output_dir=output_dir,
        limit=None,
        dry_run=dry_run,
        offline=False,
        provider_name=provider_name,
        model_name=model_name,
        provider=provider,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
        cached_input_usd_per_million=cached_input_usd_per_million,
        cache_dir=Path(cache_dir),
        call_budget=call_budget,
        config_hash=config_hash,
        project_root=project_root,
    )


def count_stage_events(
    sources: Sequence[tuple[Path, frozenset[str]]],
    document_ids: set[str],
) -> dict[str, dict[str, int]]:
    """Count stage and status for the given documents. Other ids are ignored."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path, stages in sources:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            stage = row.get("stage")
            if stage not in stages:
                continue
            if row.get("target_id") not in document_ids:
                continue
            counts[str(stage)][str(row.get("status"))] += 1
    return {stage: dict(statuses) for stage, statuses in sorted(counts.items())}


def format_funnel(counts: dict[str, dict[str, int]]) -> str:
    """One line per stage and status. No document text."""
    lines = ["Stage funnel"]
    if not counts:
        lines.append("  events               0")
        return "\n".join(lines) + "\n"
    for stage, statuses in counts.items():
        for status, count in sorted(statuses.items()):
            lines.append(f"  {stage:<20} {status:<12} {count}")
    return "\n".join(lines) + "\n"


def analysis_evidence_spans(cases: Sequence[dict], ledger: Sequence[dict]) -> list[dict]:
    """Complete field-level union for accepted cases, not the attempt ledger.

    The serialized ``all_evidence_spans`` property contains only inline
    evidence. Scalar-field evidence lives in the external ledger. Reuse the
    record gate's authoritative union to count both, once per evidence id.
    Failed candidates' evidence must not become analysis evidence.
    """
    by_owner: dict[str, list[dict]] = defaultdict(list)
    for row in ledger:
        by_owner[str(row.get("owner_id"))].append(row)
    result: list[dict] = []
    seen_cases: set[str] = set()
    for row in cases:
        case = RetrievalCase.model_validate(row)
        if case.case_id in seen_cases or case.validation_state != ValidationState.valid:
            raise DevelopmentBoundsError("analysis case must be unique and already valid")
        seen_cases.add(case.case_id)
        external = [EvidenceSpan.model_validate(span) for span in by_owner[case.case_id]]
        checked = validate_record(case, external)
        if not checked.ok:
            raise DevelopmentBoundsError(
                f"analysis case {case.case_id} fails the current record gate: "
                + ", ".join(checked.invalid_fields)
            )
        result.extend(span.model_dump(mode="json") for span in checked.all_evidence_spans)
    return result


def verbatim_span_failures(spans: Sequence[dict], texts: dict[str, str]) -> int:
    """Spans whose stored offsets do not reproduce the quote, or are not valid."""
    failures = 0
    for span in spans:
        text = texts.get(str(span.get("doc_id")))
        start = span.get("start_char")
        end = span.get("end_char")
        quote = span.get("quote")
        if (
            not isinstance(text, str)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or text[start:end] != quote
            or span.get("validation_state") != "valid"
        ):
            failures += 1
    return failures


def corpus_run_directory(
    output_parent: Path | str,
    doc_ids: Sequence[str],
    *,
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> Path:
    """The directory a live development-corpus run writes."""
    run_id = extraction_run_id(
        doc_ids=sorted(doc_ids),
        provider_name=PILOT_PROVIDER,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        offline=False,
        dry_run=False,
        limit=None,
    )
    return Path(output_parent) / run_id
