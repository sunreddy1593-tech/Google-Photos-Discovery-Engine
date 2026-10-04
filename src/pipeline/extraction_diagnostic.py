"""One-request synthetic extraction diagnostic.

Bounds live here. Completions, cache, retries, and diagnostic persistence stay
in ``run_extraction``. This module does not load real documents or approved
labels, and it does not call a provider SDK.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.core.ids import content_hash
from src.core.versions import EXTRACTION_PROMPT_VERSION, RULESET_VERSION, prompt_version
from src.models.document_derived import DocumentDerived
from src.models.enums import (
    DecidedBy,
    EvidenceOwnerType,
    OffsetState,
    ReasonCode,
    ScopeClass,
    Speaker,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.relevance import RelevanceDecision
from src.pipeline.extraction import (
    PROMPT_ID,
    ExtractionRunResult,
    extraction_run_id,
    run_extraction,
)
from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER

DIAGNOSTIC_DOC_ID = "reddit-synthetic-diagnostic"
DIAGNOSTIC_DECISION_ID = "synthetic-diagnostic-decision"
DIAGNOSTIC_TEXT = (
    "Synthetic diagnostic post. I could not remember the exact date "
    "of a fictional cake photo."
)
DIAGNOSTIC_QUOTE = "I could not remember the exact date"
DIAGNOSTIC_CALL_BUDGET = 1
DIAGNOSTIC_MAX_RETRIES = 1
DIAGNOSTIC_INSTANT = datetime(2026, 10, 1, tzinfo=UTC)
DEFAULT_OUTPUT = Path("data/interim/phase5/diagnostic")
DEFAULT_CACHE = Path("data/interim/cache")
PRESERVED_OUTPUTS: tuple[Path, ...] = (
    Path("data/interim/phase5/pilot"),
    Path("data/interim/phase5/8a6c025fdfce"),
    Path("data/interim/phase4/development/01455c8aab03"),
)
_PILOT_DOC_IDS = frozenset(
    {
        "google_support-2a080da4b930",
        "google_support-d7f386f347b7",
        "google_support-e1e5277da7e8",
        "reddit-23be97c93709",
        "reddit-c49086caf891",
    }
)


class DiagnosticBoundsError(ValueError):
    """The diagnostic would exceed one request or touch another run."""


def synthetic_document() -> DocumentDerived:
    """The only document this diagnostic sends. It is not a corpus record."""
    text = DIAGNOSTIC_TEXT
    return DocumentDerived(
        doc_id=DIAGNOSTIC_DOC_ID,
        raw_text_audit=text,
        normalized_text=text.lower(),
        canonical_url="https://example.invalid/synthetic-diagnostic",
        content_hash=content_hash(text),
        simhash="0",
        token_count=len(text.split()),
        normalizer_version="synthetic-diagnostic/v1",
        derived_at=DIAGNOSTIC_INSTANT,
    )


def synthetic_decision() -> RelevanceDecision:
    """A valid in-scope decision whose evidence belongs to the synthetic document."""
    start = DIAGNOSTIC_TEXT.find(DIAGNOSTIC_QUOTE)
    if start < 0:
        raise DiagnosticBoundsError("synthetic evidence quote is missing from the synthetic post")
    end = start + len(DIAGNOSTIC_QUOTE)
    span = EvidenceSpan(
        doc_id=DIAGNOSTIC_DOC_ID,
        owner_type=EvidenceOwnerType.relevance_decision,
        owner_id=DIAGNOSTIC_DECISION_ID,
        field_name="scope_class",
        quote=DIAGNOSTIC_QUOTE,
        start_char=start,
        end_char=end,
        speaker=Speaker.author,
        offset_state=OffsetState.supplied_exact,
        validation_state=ValidationState.valid,
    )
    return RelevanceDecision(
        decision_id=DIAGNOSTIC_DECISION_ID,
        doc_id=DIAGNOSTIC_DOC_ID,
        scope_class=ScopeClass.core_incomplete_recall,
        reason_code=ReasonCode.known_item_with_incomplete_recall,
        reason_summary="Synthetic decision for the one-request extraction diagnostic.",
        confidence=0.8,
        evidence=(span,),
        decided_by=DecidedBy.llm,
        model_name=PILOT_MODEL,
        prompt_version=prompt_version("relevance"),
        ruleset_version=RULESET_VERSION,
        decision_fingerprint="synthetic-diagnostic-fp",
        decided_at=DIAGNOSTIC_INSTANT,
        validation_state=ValidationState.valid,
    )


def planned_output_dir(
    output_parent: Path | str,
    *,
    model_name: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    offline: bool,
    preserved: tuple[Path, ...] = PRESERVED_OUTPUTS,
) -> Path:
    """Run-specific directory. Preserved pilot runs are refused and nothing is created."""
    active = "null" if offline or dry_run else PILOT_PROVIDER
    run_id = extraction_run_id(
        doc_ids=[DIAGNOSTIC_DOC_ID],
        provider_name=active,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        offline=offline or dry_run,
        dry_run=dry_run,
        limit=None,
    )
    destination = Path(output_parent) / run_id
    _refuse_preserved(destination, preserved)
    return destination


def run_extraction_diagnostic(
    *,
    output_dir: Path | str,
    cache_dir: Path | str,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    max_retries: int,
    call_budget: int,
    dry_run: bool = False,
    offline: bool = False,
    api_key: str | None = None,
    provider=None,
    timeout_seconds: float = 60.0,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    cached_input_usd_per_million: float | None = None,
    preserved: tuple[Path, ...] = PRESERVED_OUTPUTS,
    project_root: Path | None = None,
    config_hash: str = "",
) -> ExtractionRunResult:
    """Run one synthetic document through ``run_extraction``.

    A missing live key and an existing output directory are rejected before
    ``run_extraction`` creates anything. Dry-run returns before any provider call.
    """
    if offline:
        raise DiagnosticBoundsError("the extraction diagnostic does not run offline")
    if provider_name != PILOT_PROVIDER:
        raise DiagnosticBoundsError("the extraction diagnostic uses Groq")
    if model_name != PILOT_MODEL:
        raise DiagnosticBoundsError(f"the extraction diagnostic uses {PILOT_MODEL}")
    if max_retries != DIAGNOSTIC_MAX_RETRIES:
        raise DiagnosticBoundsError("the extraction diagnostic allows one attempt and no gateway retry")
    if call_budget != DIAGNOSTIC_CALL_BUDGET:
        raise DiagnosticBoundsError(
            f"the extraction diagnostic allows {DIAGNOSTIC_CALL_BUDGET} external request"
        )
    if prompt_version(PROMPT_ID) != EXTRACTION_PROMPT_VERSION:
        raise DiagnosticBoundsError(f"the extraction diagnostic requires {EXTRACTION_PROMPT_VERSION}")
    if DIAGNOSTIC_DOC_ID in _PILOT_DOC_IDS:
        raise DiagnosticBoundsError("the synthetic diagnostic document must not be a pilot document")

    document = synthetic_document()
    decision = synthetic_decision()
    if decision.doc_id != document.doc_id:
        raise DiagnosticBoundsError("synthetic evidence is not owned by the synthetic document")
    if any(span.doc_id != document.doc_id or span.owner_id != decision.decision_id for span in decision.evidence):
        raise DiagnosticBoundsError("synthetic evidence is not owned by the synthetic document")

    destination = planned_output_dir(
        output_dir,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
        offline=False,
        preserved=preserved,
    )
    if not dry_run and destination.exists():
        raise DiagnosticBoundsError("diagnostic output already exists; refusing to merge into it")
    if not dry_run and provider is None and not api_key:
        raise DiagnosticBoundsError("GROQ_API_KEY is not set")
    return run_extraction(
        doc_ids=[document.doc_id],
        model_decisions=[decision],
        human_decisions=[],
        derived_by_id={document.doc_id: document},
        approved_labels=None,
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


def _refuse_preserved(destination: Path, preserved: tuple[Path, ...]) -> None:
    resolved = destination.resolve()
    for item in preserved:
        root = item.resolve()
        if resolved == root or root in resolved.parents:
            raise DiagnosticBoundsError(
                "extraction diagnostic output must be a new directory, not a preserved run"
            )
