"""Development-only relevance smoke run.

The output directory is run-specific. Decisions are not merged into the
historical null-provider file. The call budget is six. A dry run writes
nothing and calls no provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.ids import sha256_hex
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION, prompt_version
from src.models.document_derived import DocumentDerived
from src.models.duplicate_link import DuplicateLink
from src.models.collected_document import CollectedDocument
from src.pipeline.stages import phase4_run_id, run_phase4
from src.llm.providers.groq import effective_temperature
from src.relevance.prompts import PROMPT_ID
from src.relevance.smoke import SMOKE_CALL_BUDGET, SmokeSelectionError, assert_development_smoke
from src.relevance.split import SplitAssignment

HISTORICAL_DECISIONS = "relevance_decisions.jsonl"


class SmokeRunError(ValueError):
    """The smoke run would mix with another run or exceed its budget."""


@dataclass(frozen=True)
class SmokePlan:
    doc_ids: tuple[str, ...]
    output_dir: Path
    provider_calls: int
    call_budget: int
    prompt_id: str
    prompt_version: str
    provider: str
    model: str
    temperature: float
    max_tokens: int
    cache_dir: Path
    dry_run: bool


def plan_smoke_run(
    doc_ids: tuple[str, ...] | list[str],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    *,
    output_parent: Path | str,
    historical_dir: Path | str,
    cache_dir: Path | str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    offline: bool = False,
) -> SmokePlan:
    """Validate the ids and choose a fresh directory. This does not call a model."""
    selected = assert_development_smoke(doc_ids, assignments)
    run_id = phase4_run_id(
        doc_ids=list(selected),
        stages=["relevance", "smoke"],
        limit=SMOKE_CALL_BUDGET,
        provider_name="null" if offline or dry_run else provider,
        model_name=model,
        temperature=temperature,
        max_tokens=max_tokens,
        confidence_review_below=0.7,
        offline=offline,
        dry_run=dry_run,
    )
    destination = Path(output_parent) / run_id
    _refuse_historical(destination, Path(historical_dir))
    return SmokePlan(
        doc_ids=selected,
        output_dir=destination,
        provider_calls=0,
        call_budget=SMOKE_CALL_BUDGET,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version(PROMPT_ID),
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_dir=Path(cache_dir),
        dry_run=dry_run,
    )


def run_smoke(
    documents: list[CollectedDocument],
    derived: list[DocumentDerived],
    links: list[DuplicateLink] | tuple[DuplicateLink, ...],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    doc_ids: tuple[str, ...] | list[str],
    *,
    output_parent: Path | str,
    historical_dir: Path | str,
    cache_dir: Path | str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    offline: bool = False,
    api_key: str | None = None,
    provider_instance=None,
    project_root: Path | None = None,
    sleeper=None,
    max_retries: int = 3,
    input_usd_per_million: float = 0.0,
    output_usd_per_million: float = 0.0,
    cached_input_usd_per_million: float | None = None,
    list_price_source: str = "",
    list_price_retrieved_on: str = "",
) -> SmokePlan:
    """Classify the smoke ids, or stop before any call when ``dry_run`` is set."""
    plan = plan_smoke_run(
        doc_ids,
        assignments,
        output_parent=output_parent,
        historical_dir=historical_dir,
        cache_dir=cache_dir,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
        offline=offline,
    )
    historical_decisions = Path(historical_dir) / HISTORICAL_DECISIONS
    before = historical_decisions.read_bytes() if historical_decisions.is_file() else None
    if not dry_run and not offline and provider_instance is None and provider != "null" and not api_key:
        raise SmokeRunError(f"{provider} API key is not set")
    if dry_run:
        if before is not None and historical_decisions.read_bytes() != before:
            raise SmokeRunError("dry run changed the historical decisions")
        return plan

    allowed = set(plan.doc_ids)
    chosen_documents = [document for document in documents if document.doc_id in allowed]
    chosen_derived = [row for row in derived if row.doc_id in allowed]
    if {document.doc_id for document in chosen_documents} != allowed:
        raise SmokeSelectionError("smoke documents do not match the development manifest")
    requested, effective = _decoding(provider, temperature)
    model_call = {
        "provider": provider,
        "model": model,
        "requested_temperature": requested,
        "effective_temperature": effective,
        "max_tokens": max_tokens,
        "prompt_id": plan.prompt_id,
        "prompt_version": plan.prompt_version,
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "model_config_hash": _model_config_hash(
            provider=provider,
            model=model,
            requested_temperature=requested,
            effective_temperature=effective,
            max_tokens=max_tokens,
            prompt_id=plan.prompt_id,
            prompt_version=plan.prompt_version,
        ),
        "call_budget": plan.call_budget,
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
    result = run_phase4(
        chosen_documents,
        chosen_derived,
        links,
        output_dir=plan.output_dir,
        stages=["relevance"],
        offline=offline,
        dry_run=False,
        provider_name=provider,
        model_name=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_dir=plan.cache_dir,
        provider_call_budget=plan.call_budget,
        provider=provider_instance,
        project_root=project_root or Path.cwd(),
        model_call=model_call,
        sleeper=sleeper,
        max_retries=max_retries,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
        cached_input_usd_per_million=cached_input_usd_per_million,
    )
    if result.provider_calls > SMOKE_CALL_BUDGET:
        raise SmokeRunError(
            f"smoke made {result.provider_calls} provider calls; the budget is {SMOKE_CALL_BUDGET}"
        )
    _write_smoke_record(plan, result.provider_calls, result.cache_hits, result.cache_misses)
    if before is not None and historical_decisions.read_bytes() != before:
        raise SmokeRunError("smoke run changed the historical decisions")
    return SmokePlan(
        doc_ids=plan.doc_ids,
        output_dir=plan.output_dir,
        provider_calls=result.provider_calls,
        call_budget=plan.call_budget,
        prompt_id=plan.prompt_id,
        prompt_version=plan.prompt_version,
        provider=plan.provider,
        model=plan.model,
        temperature=plan.temperature,
        max_tokens=plan.max_tokens,
        cache_dir=plan.cache_dir,
        dry_run=False,
    )


def _refuse_historical(destination: Path, historical_dir: Path) -> None:
    historical_file = (historical_dir / HISTORICAL_DECISIONS).resolve()
    planned = (destination / HISTORICAL_DECISIONS).resolve()
    if destination.resolve() == historical_dir.resolve() or planned == historical_file:
        raise SmokeRunError(
            "smoke output must be a new directory, not the historical null-provider run"
        )
    if planned.is_file():
        raise SmokeRunError("smoke output already has decisions; refusing to merge")


def _decoding(provider: str, temperature: float) -> tuple[float, float]:
    requested = float(temperature)
    if provider == "groq":
        return requested, effective_temperature(requested)
    return requested, requested


def _model_config_hash(**fields: object) -> str:
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_hex(blob)


def _write_smoke_record(plan: SmokePlan, provider_calls: int, cache_hits: int, cache_misses: int) -> None:
    manifest_path = plan.output_dir / "run_manifest.json"
    model_call = {}
    if manifest_path.is_file():
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(stored.get("model_call"), dict):
            model_call = stored["model_call"]
    payload = {
        "doc_ids": list(plan.doc_ids),
        "prompt_id": plan.prompt_id,
        "prompt_version": plan.prompt_version,
        "provider": plan.provider,
        "model": plan.model,
        "temperature": plan.temperature,
        "max_tokens": plan.max_tokens,
        "cache_dir": plan.cache_dir.name,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "provider_calls": provider_calls,
        "call_budget": plan.call_budget,
        "model_call": model_call,
    }
    path = plan.output_dir / "smoke_run.json"
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
