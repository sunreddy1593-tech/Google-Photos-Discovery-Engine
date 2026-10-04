"""Five-document development extraction pilot.

Selection and request bounds live here. Completions, cache, repair, retries,
usage, and persistence stay in ``run_extraction``. This module does not call
a provider SDK.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.core.versions import EXTRACTION_PROMPT_VERSION, prompt_version
from src.models.enums import DecidedBy, ScopeClass, ValidationState
from src.pipeline.extraction import (
    PROMPT_ID,
    ExtractionInput,
    ExtractionRunResult,
    accept_extraction_response,
    extraction_request_identity,
    extraction_run_id,
    run_extraction,
)
from src.relevance.split import SPLIT_DEVELOPMENT

PILOT_CORE_SEATS = 2
PILOT_ADJACENT_SEATS = 3
PILOT_SIZE = PILOT_CORE_SEATS + PILOT_ADJACENT_SEATS
PILOT_CALL_BUDGET = 5
SINGLE_DOCUMENT_CALL_BUDGET = 1
SINGLE_DOCUMENT_MAX_TOKENS = 8192
SINGLE_DOCUMENT_IDS = frozenset({"google_support-d7f386f347b7", "google_support-e1e5277da7e8"})
FIVE_DOCUMENT_LIMIT_BUDGET = 4
CACHED_LIMIT_SEAT = "google_support-d7f386f347b7"
PILOT_MAX_RETRIES = 1
PILOT_PROVIDER = "groq"
PILOT_MODEL = "openai/gpt-oss-120b"
PILOT_COLUMNS: tuple[str, ...] = ("doc_id", "split", "split_version")
REQUIRED_ADJACENT: tuple[str, ...] = (
    "reddit-23be97c93709",
    "reddit-c49086caf891",
)
EXCLUDED: frozenset[str] = frozenset(
    {
        "google_support-3d15a7ae4cd0",
        "google_support-5b2ec98df32b",
    }
)
FORBIDDEN_COLUMNS = frozenset(
    {
        "human_scope_class",
        "human_reason_code",
        "human_notes",
        "expected_label",
        "expected_scope",
        "expected_reason",
        "stratum",
        "scope_class",
        "reason_code",
        "notes",
        "rationale",
        "approval_provenance",
        "privacy_safe_excerpt",
        "raw_text_audit",
        "quote",
    }
)
DEFAULT_MANIFEST = Path("data/interim/phase5/extraction_pilot_manifest.csv")
DEFAULT_OUTPUT = Path("data/interim/phase5/pilot")
DEFAULT_CACHE = Path("data/interim/cache")
CANDIDATE_MANIFEST = Path(
    "data/interim/phase4/development/01455c8aab03/extraction_candidate_manifest.csv"
)
HISTORICAL_OUTPUTS: tuple[Path, ...] = (
    Path("data/interim/phase5/8a6c025fdfce"),
    Path("data/interim/phase4/development/01455c8aab03"),
)
CORE = ScopeClass.core_incomplete_recall.value
ADJACENT = ScopeClass.adjacent_known_item_retrieval.value


class PilotSelectionError(ValueError):
    """The pilot manifest cannot be used."""


class PilotBoundsError(ValueError):
    """The pilot would exceed its request bounds or write into another run."""


def select_pilot_ids(
    inputs: tuple[ExtractionInput, ...] | list[ExtractionInput],
    approved: dict[str, tuple[str, str]],
) -> tuple[str, ...]:
    """Two agreeing core seats and three agreeing adjacent seats, by ``doc_id``.

    The two named adjacent documents must be validated human decisions.
    Excluded documents are never seats, even when a later label would match.
    Approved labels are read only to choose seats. They are not returned.
    """
    by_id = {item.doc_id: item for item in inputs}
    missing = [doc_id for doc_id in EXCLUDED if doc_id not in by_id]
    if missing:
        raise PilotSelectionError("excluded documents are missing: " + ", ".join(missing))
    for doc_id in REQUIRED_ADJACENT:
        if doc_id not in by_id:
            raise PilotSelectionError(f"required adjacent document {doc_id} is missing")

    core: list[str] = []
    adjacent: list[str] = []
    for item in inputs:
        if item.doc_id in EXCLUDED or not item.eligible:
            continue
        label = approved.get(item.doc_id)
        scope = None if item.decision.scope_class is None else item.decision.scope_class.value
        if label is None or scope != label[0]:
            continue
        if scope == CORE:
            core.append(item.doc_id)
        elif scope == ADJACENT:
            adjacent.append(item.doc_id)
    core.sort()
    adjacent.sort()
    if len(core) < PILOT_CORE_SEATS:
        raise PilotSelectionError(
            f"agreeing core documents are {len(core)}; the pilot needs {PILOT_CORE_SEATS}"
        )
    adjacent_ids = set(adjacent)
    for doc_id in REQUIRED_ADJACENT:
        item = by_id[doc_id]
        if doc_id not in adjacent_ids:
            raise PilotSelectionError(f"{doc_id} is not an agreeing adjacent decision")
        if item.decision.decided_by is not DecidedBy.human:
            raise PilotSelectionError(f"{doc_id} is not a human decision")
        if item.decision.validation_state is not ValidationState.valid:
            raise PilotSelectionError(f"{doc_id} is not a validated human decision")
    rest = [doc_id for doc_id in adjacent if doc_id not in REQUIRED_ADJACENT]
    seats = PILOT_ADJACENT_SEATS - len(REQUIRED_ADJACENT)
    if len(rest) < seats:
        raise PilotSelectionError("not enough agreeing adjacent documents for the pilot")
    chosen = tuple(sorted((*core[:PILOT_CORE_SEATS], *REQUIRED_ADJACENT, *rest[:seats])))
    if len(chosen) != PILOT_SIZE or len(set(chosen)) != PILOT_SIZE:
        raise PilotSelectionError("pilot selection is not five unique documents")
    if EXCLUDED.intersection(chosen):
        raise PilotSelectionError("pilot selection includes an excluded document")
    return chosen


def load_split_rows(path: Path | str) -> tuple[dict[str, str], ...]:
    """Candidate rows. Only document id and split metadata are kept."""
    source = Path(path)
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        if columns != PILOT_COLUMNS:
            raise PilotSelectionError("candidate manifest columns are " + ", ".join(columns))
        rows = tuple(dict(row) for row in reader)
    return rows


def ensure_pilot_manifest(
    path: Path | str,
    selected: tuple[str, ...],
    splits: dict[str, tuple[str, str]],
) -> tuple[str, ...]:
    """Write the five ids, or keep a valid manifest already on disk.

    An invalid file is rejected and not rewritten. The candidate manifest is
    not a valid destination.
    """
    destination = Path(path)
    if destination.resolve() == CANDIDATE_MANIFEST.resolve():
        raise PilotSelectionError("pilot manifest must not replace the candidate manifest")
    if destination.is_file():
        existing = load_pilot_manifest(destination, splits)
        if existing != tuple(selected):
            raise PilotSelectionError("existing pilot manifest does not match the selection")
        return existing
    _write_manifest(destination, selected, splits)
    return tuple(selected)


def load_pilot_manifest(
    path: Path | str,
    splits: dict[str, tuple[str, str]],
) -> tuple[str, ...]:
    """Read a classifier-facing manifest. Label columns are rejected."""
    destination = Path(path)
    with destination.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        leaked = FORBIDDEN_COLUMNS.intersection(columns)
        if leaked:
            raise PilotSelectionError(
                "pilot manifest contains label columns: " + ", ".join(sorted(leaked))
            )
        if columns != PILOT_COLUMNS:
            raise PilotSelectionError("pilot manifest columns are " + ", ".join(columns))
        rows = list(reader)
    doc_ids = tuple(row["doc_id"] for row in rows)
    if len(doc_ids) != PILOT_SIZE or len(set(doc_ids)) != PILOT_SIZE:
        raise PilotSelectionError("pilot manifest must contain five unique doc_ids")
    if EXCLUDED.intersection(doc_ids):
        raise PilotSelectionError("pilot manifest includes an excluded document")
    for row in rows:
        expected = splits.get(row["doc_id"])
        if expected is None or expected[0] != SPLIT_DEVELOPMENT:
            raise PilotSelectionError(f"{row['doc_id']} is not a development document")
        if row["split"] != expected[0] or row["split_version"] != expected[1]:
            raise PilotSelectionError(f"{row['doc_id']} split metadata does not match")
    return doc_ids


def five_document_token_limit(
    pilot_doc_id: str | None,
    pilot_max_tokens: int | None,
) -> bool:
    """True when 8192 applies to the full five-seat manifest."""
    return (
        pilot_doc_id is None
        and type(pilot_max_tokens) is int
        and pilot_max_tokens == SINGLE_DOCUMENT_MAX_TOKENS
    )


def assert_pilot_bounds(
    *,
    provider: str,
    model: str,
    max_retries: int,
    call_budget: int,
    doc_ids: tuple[str, ...] | list[str],
    split: str,
    pilot_doc_id: str | None = None,
    pilot_max_tokens: int | None = None,
) -> None:
    """Validate the five-seat selection and its call bounds."""
    if split != SPLIT_DEVELOPMENT:
        raise PilotBoundsError("Holdout locked: the extraction pilot uses development documents only")
    if len(doc_ids) != PILOT_SIZE or len(set(doc_ids)) != PILOT_SIZE:
        raise PilotBoundsError(f"the extraction pilot accepts {PILOT_SIZE} documents")
    if provider != PILOT_PROVIDER:
        raise PilotBoundsError("the extraction pilot uses Groq")
    if model != PILOT_MODEL:
        raise PilotBoundsError(f"the extraction pilot uses {PILOT_MODEL}")
    if max_retries != PILOT_MAX_RETRIES:
        raise PilotBoundsError("the extraction pilot allows one attempt and no gateway retry")
    if pilot_doc_id is not None and (pilot_doc_id not in SINGLE_DOCUMENT_IDS or pilot_doc_id not in doc_ids):
        raise PilotBoundsError("single-document diagnosis is limited to a failed core seat in the pilot manifest")
    if five_document_token_limit(pilot_doc_id, pilot_max_tokens):
        required_budget = FIVE_DOCUMENT_LIMIT_BUDGET
    elif pilot_doc_id is not None:
        required_budget = SINGLE_DOCUMENT_CALL_BUDGET
    else:
        required_budget = PILOT_CALL_BUDGET
    if call_budget != required_budget:
        raise PilotBoundsError(f"the extraction pilot allows {required_budget} external requests")
    if prompt_version(PROMPT_ID) != EXTRACTION_PROMPT_VERSION:
        raise PilotBoundsError(f"the extraction pilot requires {EXTRACTION_PROMPT_VERSION}")


def planned_output_dir(
    output_parent: Path | str,
    doc_ids: tuple[str, ...] | list[str],
    *,
    model_name: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    offline: bool,
    historical: tuple[Path, ...] = HISTORICAL_OUTPUTS,
) -> Path:
    """Run-specific directory. Historical runs are refused and nothing is created."""
    active = "null" if offline or dry_run else PILOT_PROVIDER
    run_id = extraction_run_id(
        doc_ids=list(doc_ids),
        provider_name=active,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        offline=offline or dry_run,
        dry_run=dry_run,
        limit=None,
    )
    destination = Path(output_parent) / run_id
    _refuse_historical(destination, historical)
    return destination


def resolve_pilot_max_tokens(
    configured: int,
    *,
    pilot_doc_id: str | None,
    pilot_max_tokens: int | None,
) -> int:
    """Keep the configured limit unless an explicit 8192-token mode opts in.

    One failed core seat, or the five-seat manifest with no seat selected, may
    opt in. Other values stay refused, so omission keeps the configured limit.
    """
    if pilot_max_tokens is None:
        return configured
    if type(pilot_max_tokens) is not int or pilot_max_tokens != SINGLE_DOCUMENT_MAX_TOKENS:
        raise PilotBoundsError(f"--pilot-max-tokens allows only {SINGLE_DOCUMENT_MAX_TOKENS}")
    if pilot_doc_id is not None and pilot_doc_id not in SINGLE_DOCUMENT_IDS:
        raise PilotBoundsError("--pilot-max-tokens requires a single failed core seat")
    return pilot_max_tokens


def confirm_corrected_schema_cache(
    *,
    doc_ids: tuple[str, ...] | list[str],
    derived_by_id: dict,
    cache_dir: Path | str,
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> None:
    """Require a usable corrected-schema cache hit before any call or output.

    The cached seat is not counted as uncached. A missing, mismatched, or
    locally invalid entry fails closed instead of being requested again.
    """
    from src.llm.cache import ResponseCache

    selected = tuple(doc_ids)
    if CACHED_LIMIT_SEAT not in selected:
        raise PilotBoundsError("the five-document 8192-token pilot requires the cached core seat")
    uncached = len(selected) - 1
    if uncached > FIVE_DOCUMENT_LIMIT_BUDGET:
        raise PilotBoundsError(
            "the five-document 8192-token pilot allows at most four uncached documents"
        )
    derived = derived_by_id.get(CACHED_LIMIT_SEAT)
    if derived is None:
        raise PilotBoundsError("derived text is missing for the cached core seat")
    identity = extraction_request_identity(
        derived,
        provider_name=provider_name,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        prompt_version_value=prompt_version(PROMPT_ID),
    )
    entry = ResponseCache(cache_dir).read(PROMPT_ID, str(identity["cache_key"]))
    if entry is None:
        raise PilotBoundsError("expected corrected-schema cache entry is missing")
    comparable = {
        "cache_key": entry.cache_key,
        "provider": entry.provider,
        "model": entry.model,
        "prompt_id": entry.prompt_id,
        "prompt_version": entry.prompt_version,
        "schema_version": entry.schema_version,
        "content_hash": entry.content_hash,
        "decoding_params": dict(sorted(entry.decoding_params.items())),
        "request_text": entry.request_text,
        "ruleset_version": entry.ruleset_version,
    }
    if comparable != identity:
        raise PilotBoundsError("expected corrected-schema cache entry does not match the request")
    try:
        accept_extraction_response(entry.raw_response, CACHED_LIMIT_SEAT)
    except ValueError:
        raise PilotBoundsError(
            "expected corrected-schema cache entry failed local response validation"
        ) from None


def run_extraction_pilot(
    *,
    doc_ids: tuple[str, ...] | list[str],
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
    pilot_doc_id: str | None = None,
    pilot_max_tokens: int | None = None,
    dry_run: bool = False,
    offline: bool = False,
    api_key: str | None = None,
    provider=None,
    approved_labels: dict[str, tuple[str, str]] | None = None,
    timeout_seconds: float = 60.0,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    cached_input_usd_per_million: float | None = None,
    historical: tuple[Path, ...] = HISTORICAL_OUTPUTS,
    project_root: Path | None = None,
    config_hash: str = "",
) -> ExtractionRunResult:
    """Run the bounded pilot through ``run_extraction``.

    A missing live key is rejected before the output directory is created.
    The five-document 8192-token mode confirms its corrected-schema cache entry
    before any provider call or output write. Dry-run still writes no records.
    """
    selected = tuple(doc_ids)
    limited = five_document_token_limit(pilot_doc_id, pilot_max_tokens)
    if limited and offline:
        raise PilotBoundsError("the five-document 8192-token pilot does not run offline")
    max_tokens = resolve_pilot_max_tokens(
        max_tokens, pilot_doc_id=pilot_doc_id, pilot_max_tokens=pilot_max_tokens,
    )
    assert_pilot_bounds(
        provider=provider_name,
        model=model_name,
        max_retries=max_retries,
        call_budget=call_budget,
        doc_ids=selected,
        split=split,
        pilot_doc_id=pilot_doc_id,
        pilot_max_tokens=pilot_max_tokens,
    )
    if pilot_doc_id is not None:
        selected = (pilot_doc_id,)
    destination = planned_output_dir(
        output_dir,
        selected,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
        offline=offline,
        historical=historical,
    )
    if not dry_run and destination.exists():
        raise PilotBoundsError("pilot output already exists; refusing to merge into it")
    if not dry_run and not offline and provider is None and not api_key:
        raise PilotBoundsError("GROQ_API_KEY is not set")
    if limited:
        confirm_corrected_schema_cache(
            doc_ids=selected,
            derived_by_id=derived_by_id,
            cache_dir=cache_dir,
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return run_extraction(
        doc_ids=list(selected),
        model_decisions=list(model_decisions),
        human_decisions=list(human_decisions),
        derived_by_id=derived_by_id,
        approved_labels=approved_labels,
        output_dir=output_dir,
        limit=None,
        dry_run=dry_run,
        offline=offline,
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


def _write_manifest(
    path: Path,
    doc_ids: tuple[str, ...],
    splits: dict[str, tuple[str, str]],
) -> None:
    rows: list[dict[str, str]] = []
    for doc_id in doc_ids:
        split, version = splits[doc_id]
        if split != SPLIT_DEVELOPMENT:
            raise PilotSelectionError(f"{doc_id} is not a development document")
        rows.append({"doc_id": doc_id, "split": split, "split_version": version})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PILOT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _refuse_historical(destination: Path, historical: tuple[Path, ...]) -> None:
    resolved = destination.resolve()
    for item in historical:
        root = item.resolve()
        if resolved == root or root in resolved.parents:
            raise PilotBoundsError(
                "extraction pilot output must be a new directory, not an existing run"
            )
