"""Bounded five-document extraction pilot. Completions are mocked. No network."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
from src.core.config import load_settings
from src.core.ids import content_hash
from src.core.versions import prompt_version
from src.llm.gateway import ModelGateway
from src.llm.providers.base import (
    CompletionParams,
    ProviderResponse,
    authentication_failed,
    rate_limited,
)
from src.models.document_derived import DocumentDerived
from src.models.enums import (
    DecidedBy,
    DecisionTechnicalState,
    EvidenceOwnerType,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.models.relevance import RelevanceDecision
from src.pipeline.extraction import resolve_extraction_inputs
from src.pipeline.extraction_pilot import (
    CANDIDATE_MANIFEST,
    EXCLUDED,
    PILOT_CALL_BUDGET,
    PILOT_MODEL,
    PILOT_PROVIDER,
    REQUIRED_ADJACENT,
    PilotBoundsError,
    PilotSelectionError,
    ensure_pilot_manifest,
    load_split_rows,
    planned_output_dir,
    run_extraction_pilot,
    select_pilot_ids,
)
from src.pipeline.human_relevance import load_human_decisions
from tests.synthetic import NOW, make_decision, make_span

PROJECT = Path(__file__).resolve().parents[1]
RUN = PROJECT / "data/interim/phase4/development/01455c8aab03"
SEED = PROJECT / "data/interim/phase4/relevance_seed_review.csv"
EXPECTED = (
    "google_support-2a080da4b930",
    "google_support-d7f386f347b7",
    "google_support-e1e5277da7e8",
    "reddit-23be97c93709",
    "reddit-c49086caf891",
)
LEAK = "NOTE-SHOULD-NOT-LEAK-9f3a"
TEXT = 'I wanted my cake photo. I typed "cake" and found nothing. I forgot the date.'
CORE = ScopeClass.core_incomplete_recall
ADJACENT = ScopeClass.adjacent_known_item_retrieval


class CountingProvider:
    provider_name = "fake"

    def __init__(self, text: str | None = None, failure=None) -> None:
        self.text = text
        self.failure = failure
        self.calls = 0
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def complete_structured(self, prompt: str, schema: dict, params: CompletionParams) -> ProviderResponse:
        self.calls += 1
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if self.failure is not None:
            raise self.failure
        doc_id = schema["properties"]["doc_id"]["enum"][0]
        body = self.text if self.text is not None else json.dumps({"doc_id": doc_id, "cases": []})
        return ProviderResponse(
            text=body,
            input_tokens=4,
            output_tokens=2,
            model=params.model,
            provider=self.provider_name,
        )


def _decision(doc_id: str, scope: ScopeClass, *, human: bool = False) -> RelevanceDecision:
    decision_id = f"decision-{doc_id}"
    reason = (
        ReasonCode.known_item_with_incomplete_recall
        if scope is CORE
        else ReasonCode.known_item_with_precise_recall_failure
    )
    span = make_span(
        "scope_class",
        "I could not remember the exact date",
        owner_id=decision_id,
        owner_type=EvidenceOwnerType.relevance_decision,
        doc_id=doc_id,
    )
    fields: dict[str, object] = {
        "decision_id": decision_id,
        "doc_id": doc_id,
        "scope_class": scope,
        "reason_code": reason,
        "evidence": (span,),
        "validation_state": ValidationState.valid,
    }
    if human:
        fields.update(
            decided_by=DecidedBy.human,
            model_name=None,
            prompt_version=None,
            confidence=None,
        )
    return make_decision(**fields)


def _inputs(decisions: list[RelevanceDecision]):
    return resolve_extraction_inputs(
        [row.doc_id for row in decisions],
        decisions,
        [row for row in decisions if row.decided_by is DecidedBy.human],
    )


def _approved(decisions: list[RelevanceDecision]) -> dict[str, tuple[str, str]]:
    return {
        row.doc_id: (
            row.scope_class.value,
            row.reason_code.value,
        )
        for row in decisions
        if row.scope_class is not None
    }


def _synthetic_pool() -> tuple[list[RelevanceDecision], dict[str, tuple[str, str]]]:
    decisions = [
        _decision("google_support-3d15a7ae4cd0", ADJACENT),
        _decision("google_support-5b2ec98df32b", CORE),
        _decision("core-c", CORE),
        _decision("core-a", CORE),
        _decision("core-b", CORE),
        _decision(REQUIRED_ADJACENT[0], ADJACENT, human=True),
        _decision(REQUIRED_ADJACENT[1], ADJACENT, human=True),
        _decision("adj-z", ADJACENT),
        _decision("adj-a", ADJACENT),
        _decision("conflict", ADJACENT),
    ]
    approved = _approved(decisions)
    approved["google_support-5b2ec98df32b"] = (ADJACENT.value, approved["google_support-5b2ec98df32b"][1])
    approved["conflict"] = (CORE.value, approved["conflict"][1])
    return decisions, approved


def _derived(doc_id: str) -> DocumentDerived:
    return DocumentDerived(
        doc_id=doc_id,
        raw_text_audit=TEXT,
        normalized_text=TEXT.lower(),
        canonical_url="https://example.invalid/synthetic",
        content_hash=content_hash(TEXT),
        simhash="0",
        token_count=len(TEXT.split()),
        normalizer_version="synthetic/v1",
        derived_at=NOW,
    )


def _five(scope: ScopeClass = CORE) -> tuple[list[str], list[RelevanceDecision], dict[str, DocumentDerived]]:
    ids = [f"doc-{index}" for index in range(5)]
    decisions = [_decision(doc_id, scope) for doc_id in ids]
    return ids, decisions, {doc_id: _derived(doc_id) for doc_id in ids}


def _pilot(tmp_path: Path, provider, ids, decisions, derived, **kwargs):
    settings = dict(
        doc_ids=ids,
        model_decisions=decisions,
        human_decisions=[],
        derived_by_id=derived,
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        provider_name=PILOT_PROVIDER,
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=64,
        max_retries=1,
        call_budget=PILOT_CALL_BUDGET,
        provider=provider,
        api_key="not-sent",
        approved_labels={doc_id: (CORE.value, LEAK) for doc_id in ids},
    )
    settings.update(kwargs)
    return run_extraction_pilot(**settings)


def test_selection_keeps_required_human_seats_and_fills_the_rest_by_doc_id() -> None:
    decisions, approved = _synthetic_pool()
    selected = select_pilot_ids(_inputs(decisions), approved)
    assert selected == (
        "adj-a",
        "core-a",
        "core-b",
        "reddit-23be97c93709",
        "reddit-c49086caf891",
    )
    assert EXCLUDED.isdisjoint(selected)
    humans = {row.doc_id for row in decisions if row.decided_by is DecidedBy.human}
    assert set(REQUIRED_ADJACENT) <= humans


def test_development_seats_are_two_core_and_three_adjacent() -> None:
    rows = load_split_rows(CANDIDATE_MANIFEST)
    before = {
        path: path.read_bytes()
        for path in (
            CANDIDATE_MANIFEST,
            SEED,
            RUN / "relevance_decisions.jsonl",
            RUN / "human_relevance_decisions.jsonl",
        )
    }
    models = [
        RelevanceDecision.model_validate_json(line)
        for line in (RUN / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    humans = list(load_human_decisions(RUN / "human_relevance_decisions.jsonl"))
    from src.pipeline.extraction import load_approved_labels

    labels = load_approved_labels(SEED)
    selected = select_pilot_ids(
        resolve_extraction_inputs([row["doc_id"] for row in rows], models, humans),
        labels,
    )
    assert selected == EXPECTED
    resolved = {
        item.doc_id: item
        for item in resolve_extraction_inputs([row["doc_id"] for row in rows], models, humans)
    }
    core = [
        doc_id
        for doc_id in selected
        if labels[doc_id][0] == CORE.value and resolved[doc_id].decision.scope_class is CORE
    ]
    adjacent = [
        doc_id
        for doc_id in selected
        if labels[doc_id][0] == ADJACENT.value
        and resolved[doc_id].decision.scope_class is ADJACENT
    ]
    assert core == ["google_support-d7f386f347b7", "google_support-e1e5277da7e8"]
    assert adjacent == [
        "google_support-2a080da4b930",
        "reddit-23be97c93709",
        "reddit-c49086caf891",
    ]
    for doc_id in REQUIRED_ADJACENT:
        assert resolved[doc_id].decision.decided_by is DecidedBy.human
        assert resolved[doc_id].decision.validation_state is ValidationState.valid
    assert resolved["google_support-3d15a7ae4cd0"].eligible is False
    assert resolved["google_support-5b2ec98df32b"].decision.scope_class is CORE
    assert labels["google_support-5b2ec98df32b"][0] == ADJACENT.value
    assert before == {path: path.read_bytes() for path in before}


def test_manifest_keeps_ids_and_split_metadata_and_preserves_a_valid_file(tmp_path: Path) -> None:
    decisions, approved = _synthetic_pool()
    selected = select_pilot_ids(_inputs(decisions), approved)
    splits = {doc_id: ("development", "relevance-seed-split/v1") for doc_id in selected}
    path = tmp_path / "extraction_pilot_manifest.csv"
    assert ensure_pilot_manifest(path, selected, splits) == selected
    stored = path.read_bytes()
    assert ensure_pilot_manifest(path, selected, splits) == selected
    assert path.read_bytes() == stored
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == ("doc_id", "split", "split_version")
        rows = list(reader)
    assert [row["doc_id"] for row in rows] == list(selected)
    assert {row["split"] for row in rows} == {"development"}
    blob = path.read_text(encoding="utf-8")
    assert LEAK not in blob
    assert "human_" not in blob

    labeled = tmp_path / "labeled.csv"
    labeled.write_text(
        "doc_id,split,split_version,human_notes\nadj-a,development,relevance-seed-split/v1,secret\n",
        encoding="utf-8",
    )
    before = labeled.read_bytes()
    with pytest.raises(PilotSelectionError, match="label columns"):
        ensure_pilot_manifest(labeled, selected, splits)
    assert labeled.read_bytes() == before

    candidate = CANDIDATE_MANIFEST.read_bytes()
    with pytest.raises(PilotSelectionError, match="candidate manifest"):
        ensure_pilot_manifest(CANDIDATE_MANIFEST, selected, splits)
    assert CANDIDATE_MANIFEST.read_bytes() == candidate


def test_pilot_refuses_loose_bounds_and_historical_output(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    with pytest.raises(PilotBoundsError, match="one attempt"):
        _pilot(tmp_path, CountingProvider(), ids, decisions, derived, max_retries=2)
    with pytest.raises(PilotBoundsError, match="5 external"):
        _pilot(tmp_path, CountingProvider(), ids, decisions, derived, call_budget=6)
    with pytest.raises(PilotBoundsError, match="Groq"):
        run_extraction_pilot(
            doc_ids=ids,
            model_decisions=decisions,
            human_decisions=[],
            derived_by_id=derived,
            output_dir=tmp_path / "other",
            cache_dir=tmp_path / "cache",
            provider_name="anthropic",
            model_name=PILOT_MODEL,
            temperature=0.0,
            max_tokens=32,
            max_retries=1,
            call_budget=5,
        )
    historical = tmp_path / "historical"
    with pytest.raises(PilotBoundsError, match="new directory"):
        planned_output_dir(
            historical,
            ids,
            model_name=PILOT_MODEL,
            temperature=0.0,
            max_tokens=32,
            dry_run=True,
            offline=False,
            historical=(historical,),
        )
    assert list(tmp_path.iterdir()) == []


def test_pilot_rejects_partial_existing_output_before_calls(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    output = tmp_path / "pilot"
    destination = planned_output_dir(
        output, ids, model_name=PILOT_MODEL, temperature=0.0,
        max_tokens=64, dry_run=False, offline=False,
    )
    destination.mkdir(parents=True)
    partial = destination / "checkpoints.jsonl"
    partial.write_text("partial run\n", encoding="utf-8")
    provider = CountingProvider()
    with pytest.raises(PilotBoundsError, match="output already exists"):
        _pilot(output, provider, ids, decisions, derived)
    assert provider.calls == 0
    assert partial.read_text(encoding="utf-8") == "partial run\n"


def test_dry_run_makes_no_call_and_writes_no_output(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    provider = CountingProvider()
    result = _pilot(tmp_path / "out", provider, ids, decisions, derived, dry_run=True)
    assert result.dry_run is True
    assert result.provider_calls == 0
    assert result.files_written == ()
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []


def test_missing_key_is_rejected_before_output_creation(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    output = tmp_path / "pilot-out"
    with pytest.raises(PilotBoundsError, match="GROQ_API_KEY"):
        run_extraction_pilot(
            doc_ids=ids,
            model_decisions=decisions,
            human_decisions=[],
            derived_by_id=derived,
            output_dir=output,
            cache_dir=tmp_path / "cache",
            provider_name=PILOT_PROVIDER,
            model_name=PILOT_MODEL,
            temperature=0.0,
            max_tokens=32,
            max_retries=1,
            call_budget=5,
            api_key=None,
        )
    assert not output.exists()
    assert not (tmp_path / "cache").exists()


def test_fatal_authentication_stops_before_the_remaining_documents(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    provider = CountingProvider(failure=authentication_failed("the provider rejected the credentials"))
    result = _pilot(tmp_path, provider, ids, decisions, derived)
    assert provider.calls == 1
    assert result.provider_calls == 1
    inputs = (Path(result.output_dir) / "extraction_inputs.jsonl").read_text(encoding="utf-8")
    assert result.attempted == 1
    assert ids[0] in inputs
    assert ids[1] not in inputs
    assert "provider_error" in inputs


def test_one_attempt_and_the_five_call_budget_do_not_retry(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    provider = CountingProvider(failure=rate_limited("limited"))
    result = _pilot(tmp_path / "pilot", provider, ids, decisions, derived)
    assert provider.calls == PILOT_CALL_BUDGET
    assert result.provider_calls == PILOT_CALL_BUDGET

    from src.pipeline.extraction import run_extraction

    reserved = CountingProvider(failure=rate_limited("limited"))
    run_extraction(
        doc_ids=ids,
        model_decisions=decisions,
        human_decisions=[],
        derived_by_id=derived,
        output_dir=tmp_path / "reserved",
        provider=reserved,
        provider_name="fake",
        model_name=PILOT_MODEL,
        max_retries=2,
        call_budget=PILOT_CALL_BUDGET,
        cache_dir=tmp_path / "reserved-cache",
    )
    assert reserved.calls == PILOT_CALL_BUDGET


def test_gateway_reserves_the_first_attempt_of_each_uncached_document(tmp_path: Path) -> None:
    from src.llm.cache import ResponseCache

    provider = CountingProvider(failure=rate_limited("limited"))
    gateway = ModelGateway(
        provider,
        ResponseCache(tmp_path / "cache"),
        provider_name="fake",
        model=PILOT_MODEL,
        temperature=0.0,
        max_tokens=32,
        timeout_seconds=5,
        max_retries=2,
        input_usd_per_million=0.0,
        output_usd_per_million=0.0,
        call_budget=PILOT_CALL_BUDGET,
        sleeper=lambda _seconds: None,
    )
    result = gateway.complete(
        prompt="extract",
        schema={"type": "object"},
        response_model=type("Payload", (), {}),
        content_hash="hash-1",
        prompt_id="extract",
        prompt_version="extract/v1",
        unattempted_documents=4,
    )
    assert provider.calls == 1
    assert result.technical_state is DecisionTechnicalState.rate_limited


def test_cache_hit_skips_the_provider(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    cache = tmp_path / "cache"
    first = CountingProvider()
    opened = _pilot(tmp_path / "first", first, ids, decisions, derived, cache_dir=cache)
    assert first.calls == 5
    assert opened.cache_misses == 5
    second = CountingProvider()
    again = _pilot(tmp_path / "second", second, ids, decisions, derived, cache_dir=cache)
    assert second.calls == 0
    assert again.cache_hits == 5
    assert again.provider_calls == 0


def test_requests_omit_labels_and_keep_evidence_on_the_target(tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    provider = CountingProvider()
    result = _pilot(tmp_path / "labels", provider, ids, decisions, derived)
    assert provider.prompts
    for prompt in provider.prompts:
        assert LEAK not in prompt
        assert "human_notes" not in prompt
        assert "human_scope_class" not in prompt
    for schema in provider.schemas:
        assert schema["additionalProperties"] is False
        assert schema["properties"]["doc_id"]["enum"] == [schema["properties"]["doc_id"]["enum"][0]]
        assert schema["properties"]["doc_id"]["enum"][0] in ids

    foreign = "doc-from-another-record"
    mismatched = CountingProvider(text=json.dumps({"doc_id": foreign, "cases": []}))
    failed = _pilot(tmp_path / "foreign", mismatched, ids, decisions, derived)
    stored = (Path(failed.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8")
    assert foreign not in stored
    failures = (Path(failed.output_dir) / "extraction_failures.jsonl").read_text(encoding="utf-8")
    assert "schema_validation_failed" in failures
    assert result.valid_cases == 0
    assert prompt_version("extract") == "extract/v2"


def test_groq_pilot_disables_sdk_retries_and_uses_strict_schema(monkeypatch, tmp_path: Path) -> None:
    ids, decisions, derived = _five()
    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["calls"] = int(captured.get("calls", 0)) + 1
        schema = kwargs["response_format"]["json_schema"]["schema"]
        doc_id = schema["properties"]["doc_id"]["enum"][0]
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        assert schema["additionalProperties"] is False
        assert LEAK not in kwargs["messages"][1]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"doc_id": doc_id, "cases": []})))],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
            model=PILOT_MODEL,
        )

    def groq_client(*, api_key, timeout, max_retries=1):
        captured["max_retries"] = max_retries
        captured["api_key"] = api_key
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(
        sys.modules,
        "groq",
        SimpleNamespace(
            Groq=groq_client,
            APITimeoutError=type("APITimeoutError", (Exception,), {}),
            RateLimitError=type("RateLimitError", (Exception,), {}),
            APIConnectionError=type("APIConnectionError", (Exception,), {}),
            APIStatusError=type("APIStatusError", (Exception,), {}),
            APIError=type("APIError", (Exception,), {}),
            AuthenticationError=type("AuthenticationError", (Exception,), {}),
        ),
    )
    result = run_extraction_pilot(
        doc_ids=ids,
        model_decisions=decisions,
        human_decisions=[],
        derived_by_id=derived,
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        provider_name=PILOT_PROVIDER,
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=64,
        max_retries=1,
        call_budget=PILOT_CALL_BUDGET,
        api_key="gsk-test-secret-not-real",
        approved_labels={doc_id: (CORE.value, LEAK) for doc_id in ids},
    )
    assert captured["max_retries"] == 0
    assert captured["calls"] == 5
    assert result.provider_calls == 5
    assert "gsk-test-secret-not-real" not in json.dumps(captured["calls"])


def test_cli_keeps_unrestricted_live_extraction_refused(capsys) -> None:
    code = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--provider",
            "groq",
            "--call-budget",
            "5",
            "--max-retries",
            "1",
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "not authorized" in captured.err


def test_cli_pilot_dry_run_selects_the_five_and_writes_nothing(tmp_path: Path, capsys) -> None:
    output = tmp_path / "pilot-out"
    cache = tmp_path / "cache"
    candidate = CANDIDATE_MANIFEST.read_bytes()
    code = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--pilot",
            "--dry-run",
            "--provider",
            "groq",
            "--split",
            "development",
            "--cache",
            str(cache),
            "--call-budget",
            "5",
            "--max-retries",
            "1",
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "provider calls       0" in captured.out
    assert PILOT_MODEL in captured.out
    assert "extract/v2" in captured.out
    assert "call budget          5" in captured.out
    for doc_id in EXPECTED:
        assert doc_id in captured.out
    assert not output.exists()
    assert not cache.exists()
    assert CANDIDATE_MANIFEST.read_bytes() == candidate
    manifest = PROJECT / "data/interim/phase5/extraction_pilot_manifest.csv"
    with manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == ("doc_id", "split", "split_version")
        assert tuple(row["doc_id"] for row in reader) == EXPECTED


def test_cli_pilot_rejects_holdout_a_larger_budget_and_a_missing_key(
    monkeypatch, tmp_path: Path, empty_env: Path, capsys
) -> None:
    holdout = main.main(["run", "--stages", "extract", "--pilot", "--split", "holdout", "--dry-run"])
    assert holdout == 1
    assert "Holdout locked" in capsys.readouterr().err

    budget = main.main(["run", "--stages", "extract", "--pilot", "--dry-run", "--call-budget", "6"])
    assert budget == 1
    assert "5" in capsys.readouterr().err

    retries = main.main(["run", "--stages", "extract", "--pilot", "--dry-run", "--max-retries", "3"])
    assert retries == 1
    assert "no gateway retry" in capsys.readouterr().err

    other = main.main(["run", "--stages", "extract", "--pilot", "--dry-run", "--provider", "anthropic"])
    assert other == 1
    assert "Groq" in capsys.readouterr().err

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(main, "load_settings", lambda: load_settings(env_file=empty_env))
    output = tmp_path / "live-out"
    missing = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--pilot",
            "--provider",
            "groq",
            "--output",
            str(output),
            "--cache",
            str(tmp_path / "cache"),
        ]
    )
    assert missing == 1
    assert "GROQ_API_KEY" in capsys.readouterr().err
    assert not output.exists()
