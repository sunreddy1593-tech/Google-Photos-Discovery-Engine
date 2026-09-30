"""One development document, one external Groq request.

The smoke command always classifies six documents and can retry. This runner
reuses the gateway, the classifier, and the call budget. It does not read
human labels and it does not write the historical Phase 4 files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.core.ids import cache_key
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION, prompt_version
from src.llm.cache import ResponseCache
from src.llm.providers.base import ProviderFatalError
from src.llm.providers.groq import cache_decoding_params, transmitted_schema_sha256
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.models.duplicate_link import DuplicateLink
from src.models.enums import DecisionTechnicalState
from src.pipeline.stages import non_canonical_map, phase4_run_id, run_phase4
from src.relevance.prompts import PROMPT_ID, relevance_json_schema
from src.relevance.rules import prefilter_document
from src.relevance.split import SPLIT_DEVELOPMENT, SplitAssignment

DIAGNOSTIC_CALL_BUDGET = 1
DIAGNOSTIC_MAX_RETRIES = 1
HISTORICAL_FILES = (
    "relevance_decisions.jsonl",
    "relevance_seed_review.csv",
    "relevance_smoke_manifest.csv",
    "relevance_split_manifest.csv",
)


class DiagnosticRunError(ValueError):
    """The one-document run cannot be started safely."""

    def __init__(self, message: str, *, output_dir: Path | None = None) -> None:
        super().__init__(message)
        self.output_dir = output_dir


def relevance_cache_key(
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    content_hash: str,
    schema: dict[str, object],
) -> str:
    """The Groq cache key the gateway will use for this document."""
    return cache_key(
        provider="groq",
        model=model,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version(PROMPT_ID),
        schema_version=SCHEMA_VERSION,
        content_hash_value=content_hash,
        decoding_params=cache_decoding_params(
            temperature=temperature,
            max_tokens=max_tokens,
            schema=schema,
        ),
        ruleset_version=RULESET_VERSION,
    )


def choose_diagnostic_document(
    doc_ids: tuple[str, ...] | list[str],
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: list[DuplicateLink] | tuple[DuplicateLink, ...],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    *,
    cache_dir: Path | str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """First classifiable smoke id whose corrected schema is not cached."""
    by_doc = {document.doc_id: document for document in documents}
    by_derived = {row.doc_id: row for row in derived}
    by_split = {row.doc_id: row for row in assignments}
    skips = non_canonical_map(links)
    schema = relevance_json_schema()
    cache = ResponseCache(cache_dir)
    for doc_id in doc_ids:
        assignment = by_split.get(doc_id)
        if assignment is None or assignment.split != SPLIT_DEVELOPMENT:
            raise DiagnosticRunError(f"{doc_id} is not a development smoke document")
        document = by_doc.get(doc_id)
        derived_row = by_derived.get(doc_id)
        if document is None or derived_row is None:
            continue
        routed = prefilter_document(
            doc_id,
            derived_row.normalized_text,
            canonical_doc_id=skips.get(doc_id),
        )
        if not routed.passed:
            continue
        key = relevance_cache_key(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            content_hash=derived_row.content_hash,
            schema=schema,
        )
        if cache.read(PROMPT_ID, key) is None:
            return doc_id
    raise DiagnosticRunError("no uncached development smoke document is available")


def run_one_document(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: list[DuplicateLink] | tuple[DuplicateLink, ...],
    *,
    doc_id: str,
    output_parent: Path | str,
    historical_dir: Path | str,
    cache_dir: Path | str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    api_key: str | None,
    project_root: Path,
    input_usd_per_million: float,
    output_usd_per_million: float,
    cached_input_usd_per_million: float | None,
    list_price_source: str,
    list_price_retrieved_on: str,
    provider_instance=None,
) -> tuple[Path, object]:
    """Classify ``doc_id`` with one gateway attempt and one SDK attempt."""
    if provider != "groq":
        raise DiagnosticRunError("the diagnostic uses the configured Groq provider")
    chosen = [document for document in documents if document.doc_id == doc_id]
    chosen_derived = [row for row in derived if row.doc_id == doc_id]
    if len(chosen) != 1 or len(chosen_derived) != 1:
        raise DiagnosticRunError(f"{doc_id} is not available as one collected document")
    destination = _unused_output(
        Path(output_parent),
        phase4_run_id(
        doc_ids=[doc_id],
        stages=["relevance", "diagnostic"],
        limit=DIAGNOSTIC_CALL_BUDGET,
        provider_name=provider,
        model_name=model,
        temperature=temperature,
        max_tokens=max_tokens,
        confidence_review_below=0.7,
        offline=False,
        dry_run=False,
    ),
    )
    historical = Path(historical_dir)
    if destination.resolve() == historical.resolve():
        raise DiagnosticRunError("diagnostic output must not be the historical directory")
    schema_hash = transmitted_schema_sha256(relevance_json_schema())
    before = _historical_bytes(historical)
    from src.llm.providers.groq import effective_temperature

    requested = float(temperature)
    model_call = {
        "provider": provider,
        "model": model,
        "requested_temperature": requested,
        "effective_temperature": effective_temperature(requested),
        "max_tokens": max_tokens,
        "prompt_id": PROMPT_ID,
        "prompt_version": prompt_version(PROMPT_ID),
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "transmitted_schema_sha256": schema_hash,
        "call_budget": DIAGNOSTIC_CALL_BUDGET,
        "max_retries": DIAGNOSTIC_MAX_RETRIES,
        "sdk_max_retries": 0,
        "list_price_usd_per_million": {
            "input": input_usd_per_million,
            "cached_input": cached_input_usd_per_million,
            "output": output_usd_per_million,
        },
        "list_price_source": list_price_source,
        "list_price_retrieved_on": list_price_retrieved_on,
        "cost_note": (
            "actual billed cost is unknown; the list price is an estimate, "
            "not an invoice, and usage is not assumed to be free"
        ),
    }
    try:
        result = run_phase4(
            chosen,
            chosen_derived,
            links,
            output_dir=destination,
            stages=["relevance"],
            offline=False,
            dry_run=False,
            provider_name=provider,
            model_name=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=DIAGNOSTIC_MAX_RETRIES,
            input_usd_per_million=input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
            cached_input_usd_per_million=cached_input_usd_per_million,
            cache_dir=Path(cache_dir),
            provider_call_budget=DIAGNOSTIC_CALL_BUDGET,
            provider=provider_instance,
            project_root=project_root,
            model_call=model_call,
        )
    except ProviderFatalError:
        _require_historical(historical, before)
        raise DiagnosticRunError(
            "the provider rejected the credentials",
            output_dir=destination,
        ) from None
    _require_historical(historical, before)
    if result.provider_calls > DIAGNOSTIC_CALL_BUDGET:
        raise DiagnosticRunError(
            f"diagnostic made {result.provider_calls} provider calls"
        )
    return destination, result


def format_diagnostic_summary(output_dir: Path, provider_calls: int) -> str:
    """Counts, state, and safe diagnostics. No request body and no document text."""
    decisions = _read_jsonl(output_dir / "relevance_decisions.jsonl")
    failures = _read_jsonl(output_dir / "relevance_failures.jsonl")
    manifest = {}
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            manifest = payload
    lines = [
        f"doc_id {_first(decisions, 'doc_id')}",
        f"output {output_dir}",
        f"provider_calls {provider_calls}",
    ]
    decision = decisions[0] if decisions else {}
    state = str(decision.get("technical_state") or "")
    lines.append(f"technical_state {state}")
    diagnostic = _diagnostic(failures)
    if diagnostic:
        lines.append(
            "diagnostic "
            + " ".join(
                f"{key}={diagnostic.get(key)}"
                for key in (
                    "category",
                    "sdk_exception_class",
                    "http_status",
                    "provider_error_type",
                    "request_id",
                    "error_code",
                    "error_param",
                )
            )
        )
        lines.append(f"error_message {diagnostic.get('error_message')}")
    if state == DecisionTechnicalState.ok.value:
        lines.append(f"scope_class {decision.get('scope_class')}")
        lines.append(f"reason_code {decision.get('reason_code')}")
        lines.append(f"confidence {decision.get('confidence')}")
        lines.append(f"validation_state {decision.get('validation_state')}")
        for span in decision.get("evidence") or []:
            if isinstance(span, dict):
                lines.append(f"evidence_quote {span.get('quote')}")
                lines.append(f"evidence_validation {span.get('validation_state')}")
                lines.append(f"offset_state {span.get('offset_state')}")
    model_call = manifest.get("model_call") if isinstance(manifest.get("model_call"), dict) else {}
    lines.append(f"input_tokens {model_call.get('input_tokens')}")
    lines.append(f"output_tokens {model_call.get('output_tokens')}")
    lines.append(f"cached_input_tokens {model_call.get('cached_input_tokens')}")
    lines.append(f"estimated_list_price_usd {model_call.get('estimated_list_price_usd')}")
    lines.append(f"actual_billed_cost_usd {model_call.get('actual_billed_cost_usd')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Classify one uncached development smoke document. One external attempt."""
    from src.core.config import ConfigError, load_settings
    from src.models.document_derived import DocumentDerived
    from src.models.duplicate_link import DuplicateLink
    from src.pipeline.runner import DEFAULT_INPUT, load_collected_documents
    from src.relevance.smoke import SmokeSelectionError, load_smoke_manifest
    from src.relevance.split import SplitError, load_split_manifest

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    provider, model, env_name = settings.models.relevance_choice(None)
    if provider != "groq":
        print("Configured relevance provider is not groq.", file=sys.stderr)
        return 1
    api_key = getattr(settings.secrets, env_name.lower(), None)
    if not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1

    root = settings.project_root
    split_path = root / "data/interim/phase4/relevance_split_manifest.csv"
    smoke_path = root / "data/interim/phase4/relevance_smoke_manifest.csv"
    historical = root / "data/interim/phase4"
    derived_path = root / "data/interim/phase3/documents_derived.jsonl"
    links_path = root / "data/interim/phase3/duplicate_links.jsonl"
    source = root / DEFAULT_INPUT
    try:
        assignments = load_split_manifest(split_path)
        doc_ids = load_smoke_manifest(smoke_path, assignments)
    except (SmokeSelectionError, SplitError, OSError) as exc:
        print(f"Diagnostic error: {exc}", file=sys.stderr)
        return 1
    manifest_before = smoke_path.read_bytes()
    if not source.is_file() or not derived_path.is_file():
        print("Collected or derived documents were not found.", file=sys.stderr)
        return 1
    documents = load_collected_documents(source)
    derived = [
        DocumentDerived.model_validate_json(line)
        for line in derived_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    links: list[DuplicateLink] = []
    if links_path.is_file():
        links = [
            DuplicateLink.model_validate_json(line)
            for line in links_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    try:
        doc_id = choose_diagnostic_document(
            doc_ids,
            documents,
            derived,
            links,
            assignments,
            cache_dir=root / "data/interim/cache",
            model=model,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
        )
        output_dir, result = run_one_document(
            documents,
            derived,
            links,
            doc_id=doc_id,
            output_parent=root / "data/interim/phase4/diagnostic",
            historical_dir=historical,
            cache_dir=root / "data/interim/cache",
            provider=provider,
            model=model,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            timeout_seconds=settings.models.timeout_seconds,
            api_key=api_key,
            project_root=root,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            list_price_source=settings.models.list_price_source,
            list_price_retrieved_on=settings.models.list_price_retrieved_on,
        )
    except DiagnosticRunError as exc:
        if exc.output_dir is not None and (exc.output_dir / "relevance_decisions.jsonl").is_file():
            print(format_diagnostic_summary(exc.output_dir, DIAGNOSTIC_CALL_BUDGET), end="")
        print(f"Diagnostic error: {exc}", file=sys.stderr)
        return 1
    if smoke_path.read_bytes() != manifest_before:
        print("Diagnostic error: smoke manifest changed.", file=sys.stderr)
        return 1
    print(format_diagnostic_summary(output_dir, result.provider_calls), end="")
    return 0


def _unused_output(parent: Path, run_id: str) -> Path:
    """A directory with no decisions yet. An occupied id gets a numeric suffix."""
    candidate = parent / run_id
    if not (candidate / "relevance_decisions.jsonl").is_file():
        return candidate
    for number in range(2, 20):
        nxt = parent / f"{run_id}-{number}"
        if not (nxt / "relevance_decisions.jsonl").is_file():
            return nxt
    raise DiagnosticRunError("diagnostic output already has decisions; refusing to merge")


def _historical_bytes(historical: Path) -> dict[str, bytes | None]:
    stored: dict[str, bytes | None] = {}
    for name in HISTORICAL_FILES:
        path = historical / name
        stored[name] = path.read_bytes() if path.is_file() else None
    return stored


def _require_historical(historical: Path, before: dict[str, bytes | None]) -> None:
    after = _historical_bytes(historical)
    if after != before:
        raise DiagnosticRunError("diagnostic changed a historical artifact")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _first(rows: list[dict[str, object]], key: str) -> object:
    if not rows:
        return None
    return rows[0].get(key)


def _diagnostic(failures: list[dict[str, object]]) -> dict[str, object] | None:
    if not failures:
        return None
    recorded = failures[0].get("provider_diagnostic")
    if isinstance(recorded, dict):
        return recorded
    return None


if __name__ == "__main__":
    raise SystemExit(main())
