"""Offline extraction stage. Completions are mocked. No network."""

from __future__ import annotations

import ast
import csv
import json
import socket
from pathlib import Path

import pytest

from src.core.ids import content_hash
from src.core.versions import TAXONOMY_VERSION, prompt_version
from src.llm.providers.base import CompletionParams, ProviderResponse
from src.models.document_derived import DocumentDerived
from src.models.enums import (
    DecisionTechnicalState,
    DecidedBy,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.models.relevance import RelevanceDecision
from src.pipeline.extraction import (
    PROMPT_ID,
    label_disagreements,
    resolve_extraction_inputs,
    run_extraction,
    transmitted_extraction_schema,
)
from src.pipeline.human_relevance import build_human_relevance_decision
from src.review.overrides import make_override
from tests.synthetic import DOC_ID, NOW, make_decision

PROJECT = Path(__file__).resolve().parents[1]
RUN = PROJECT / "data/interim/phase4/development/01455c8aab03"
TEXT = 'I wanted my cake photo. I typed "cake" and found nothing. I forgot the date.'
LEAK = "NOTE-SHOULD-NOT-LEAK-9f3a"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Extraction tests must remain offline")

    monkeypatch.setattr(socket, "socket", forbidden)


class FakeProvider:
    provider_name = "fake"

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls = 0
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def complete_structured(self, prompt: str, schema: dict, params: CompletionParams) -> ProviderResponse:
        self.calls += 1
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return ProviderResponse(
            text=self.text,
            input_tokens=4,
            output_tokens=2,
            model=params.model,
            provider=self.provider_name,
        )


def derived(doc_id: str = DOC_ID, text: str = TEXT) -> DocumentDerived:
    return DocumentDerived(
        doc_id=doc_id,
        raw_text_audit=text,
        normalized_text=text.lower(),
        canonical_url="https://example.invalid/synthetic",
        content_hash=content_hash(text),
        simhash="0",
        token_count=len(text.split()),
        normalizer_version="synthetic/v1",
        derived_at=NOW,
    )


def quote(text: str) -> dict:
    return {"quote": text, "start_char": None, "end_char": None, "speaker": "author"}


def case_body(summary: str = "The cake photo search failed.", quote_text: str = "I wanted my cake photo.") -> dict:
    return {
        "problem_summary": summary,
        "field_evidence": [{"field_name": "problem_summary", **quote(quote_text)}],
    }


def response(doc_id: str, cases: list[dict]) -> str:
    return json.dumps({"doc_id": doc_id, "cases": cases})


def valid_decision(**changes) -> RelevanceDecision:
    fields = {"validation_state": ValidationState.valid, "doc_id": DOC_ID}
    fields.update(changes)
    return make_decision(**fields)


def run(tmp_path: Path, provider: FakeProvider, decisions, humans=(), texts=None, **kwargs):
    docs = texts or {DOC_ID: derived()}
    return run_extraction(
        doc_ids=list(docs),
        model_decisions=list(decisions),
        human_decisions=list(humans),
        derived_by_id=docs,
        output_dir=tmp_path,
        provider=provider,
        provider_name="fake",
        model_name="synthetic-extraction-model",
        max_retries=1,
        **{"cache_dir": tmp_path / "cache", **kwargs},
    )


def test_prompt_is_registered_and_schema_identity_is_per_document() -> None:
    assert prompt_version(PROMPT_ID) == "extract/v2"
    left = transmitted_extraction_schema(DOC_ID, provider_name="fake")
    right = transmitted_extraction_schema("reddit-other", provider_name="fake")
    assert left["properties"]["doc_id"]["enum"] == [DOC_ID]
    assert right["properties"]["doc_id"]["enum"] == ["reddit-other"]
    strict = transmitted_extraction_schema(DOC_ID, provider_name="groq")
    assert strict["properties"]["doc_id"]["enum"] == [DOC_ID]
    assert "additionalProperties" in json.dumps(strict)


def test_validated_human_decision_is_selected_and_pending_human_stays_blocked() -> None:
    model = valid_decision(
        decision_id="model-oos",
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.editing_sharing_or_printing,
        confidence=0.9,
    )
    audit = derived().raw_text_audit
    human = build_human_relevance_decision(
        make_override(
            doc_id=DOC_ID,
            target_id=model.decision_id,
            scope_class=ScopeClass.adjacent_known_item_retrieval,
            reason_code=ReasonCode.known_item_with_precise_recall_failure,
            author="researcher",
            rationale="The search failed.",
            approval_provenance="Approved seed label.",
            quote=audit,
            created_at=NOW,
        ),
        audit=audit,
        content_hash="abc",
        decided_at=NOW,
    )
    chosen = resolve_extraction_inputs([DOC_ID], [model], [human])
    assert chosen[0].eligible
    assert chosen[0].decision.decided_by is DecidedBy.human
    assert model.scope_class is ScopeClass.out_of_scope

    pending = build_human_relevance_decision(
        make_override(
            doc_id=DOC_ID,
            target_id=model.decision_id,
            scope_class=ScopeClass.adjacent_known_item_retrieval,
            reason_code=ReasonCode.known_item_retrieval_journey_described,
            author="researcher",
            rationale="Parent context only.",
            approval_provenance="Approved seed label.",
            quote=audit,
            created_at=NOW,
        ),
        audit=audit,
        content_hash="abc",
        decided_at=NOW,
        supports_decision=False,
    )
    blocked = resolve_extraction_inputs([DOC_ID], [model], [pending])
    assert blocked[0].eligible is False
    assert blocked[0].decision.decision_id == model.decision_id
    assert pending.validation_state is ValidationState.pending


def test_development_funnel_is_eighteen_eligible_and_one_blocked() -> None:
    manifest = RUN / "extraction_candidate_manifest.csv"
    with manifest.open(encoding="utf-8", newline="") as handle:
        doc_ids = [row["doc_id"] for row in csv.DictReader(handle)]
    models = [
        RelevanceDecision.model_validate_json(line)
        for line in (RUN / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    humans = [
        RelevanceDecision.model_validate_json(line)
        for line in (RUN / "human_relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    before = (RUN / "relevance_decisions.jsonl").read_bytes()
    resolved = resolve_extraction_inputs(doc_ids, models, humans)
    eligible = [item for item in resolved if item.eligible]
    blocked = [item for item in resolved if not item.eligible]
    assert len(doc_ids) == 19
    assert len(eligible) == 18
    assert [item.doc_id for item in blocked] == ["google_support-3d15a7ae4cd0"]
    assert blocked[0].decision.decided_by is DecidedBy.llm
    assert blocked[0].decision.scope_class is ScopeClass.out_of_scope
    waterfall = next(row for row in humans if row.doc_id == "google_support-3d15a7ae4cd0")
    assert waterfall.validation_state is ValidationState.pending
    assert waterfall.decided_by is DecidedBy.human
    labels = {
        row["doc_id"]: (row["human_scope_class"], row["human_reason_code"])
        for row in csv.DictReader(
            (PROJECT / "data/interim/phase4/relevance_seed_review.csv").open(
                encoding="utf-8", newline=""
            )
        )
    }
    gaps = label_disagreements(resolved, labels)
    assert "google_support-3d15a7ae4cd0" in {row.doc_id for row in gaps}
    assert (RUN / "relevance_decisions.jsonl").read_bytes() == before
    assert all(row.approved_scope for row in gaps)


def test_zero_one_and_many_cases(tmp_path: Path) -> None:
    decision = valid_decision()
    provider = FakeProvider(response(DOC_ID, []))
    empty = run(tmp_path / "zero", provider, [decision])
    assert empty.provider_calls == 1
    assert empty.valid_cases == 0
    assert (Path(empty.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8").strip() == ""

    provider = FakeProvider(response(DOC_ID, [case_body()]))
    one = run(tmp_path / "one", provider, [decision])
    cases = [
        json.loads(line)
        for line in (Path(one.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert one.valid_cases == 1
    assert cases[0]["case_id"] == f"{DOC_ID}#c01"
    assert "taxonomy_version" not in cases[0]
    assert cases[0]["prompt_version"] == "extract/v2"
    assert cases[0]["extractor_type"] == "llm"
    assert "decided_by" not in cases[0]

    provider = FakeProvider(
        response(
            DOC_ID,
            [
                case_body("Later episode.", "I forgot the date."),
                case_body("First episode.", "I wanted my cake photo."),
            ],
        )
    )
    many = run(tmp_path / "many", provider, [decision])
    stored = [
        json.loads(line)["case_id"]
        for line in (Path(many.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert stored == [f"{DOC_ID}#c01", f"{DOC_ID}#c02"]
    assert many.valid_cases == 2


@pytest.mark.parametrize("body,expected_code,state", [
    (response(DOC_ID, []), 0, "ok"),
    (response(DOC_ID, [case_body()]), 0, "ok"),
    (response(DOC_ID, [case_body(quote_text="an invented quote")]), 1, "evidence_validation_failed"),
    (json.dumps({"doc_id": DOC_ID}), 1, "schema_validation_failed"),
    ("not JSON", 1, "response_parse_failed"),
], ids=["accepted-empty", "valid-case", "bad-evidence", "bad-schema", "bad-json"])
def test_failure_summary_and_exit_code_distinguish_empty_success(tmp_path, body, expected_code, state):
    from src.pipeline.extraction import extraction_exit_code, format_extraction_summary

    result = run(tmp_path, FakeProvider(body), [valid_decision()])
    assert extraction_exit_code(result) == expected_code
    printed = format_extraction_summary(result)
    assert f"failed candidates    {expected_code}" in printed
    assert f"state {state:<14} 1" in printed
    assert "invented quote" not in printed


def test_invalid_candidates_remain_reviewable_without_entering_analysis(tmp_path):
    invalid = case_body("Invalid interpretation.", "a fabricated quote...")
    valid = case_body()
    result = run(tmp_path, FakeProvider(response(DOC_ID, [invalid, valid])), [valid_decision()])
    destination = Path(result.output_dir)
    candidate, = jsonl(destination / "extraction_candidates.jsonl")
    assert candidate["analysis_eligible"] is False
    assert candidate["technical_state"] == "evidence_validation_failed"
    assert candidate["candidate"]["problem_summary"] == invalid["problem_summary"]
    assert candidate["case"]["validation_state"] == "pending"
    assert candidate["case"]["needs_human_review"] is True
    analysis, = jsonl(destination / "retrieval_cases.jsonl")
    assert analysis["problem_summary"] == valid["problem_summary"]
    assert analysis["case_id"] != candidate["case_id"]
    reviews = jsonl(destination / "review_queue.jsonl")
    assert any(row["target_id"] == candidate["case_id"] for row in reviews)
    assert "extraction_candidates.jsonl" in result.files_written
    assert len(result.files_written) == 12
    assert jsonl(destination / "extraction_failures.jsonl")[0]["raw_response_ref"] is None


def test_unassembled_schema_candidate_is_retained_without_a_case(tmp_path):
    candidate_body = {**case_body(), "reformulation_count": 1, "reformulation_count_observation": "not_stated"}
    result = run(tmp_path, FakeProvider(response(DOC_ID, [candidate_body])), [valid_decision()])
    destination = Path(result.output_dir)
    candidate, = jsonl(destination / "extraction_candidates.jsonl")
    assert candidate["candidate"]["reformulation_count"] == 1
    assert candidate["case"] is None
    assert candidate["technical_state"] == "schema_validation_failed"
    assert candidate["analysis_eligible"] is False
    assert jsonl(destination / "retrieval_cases.jsonl") == []


def test_schema_evidence_and_observation_failures_are_auditable(tmp_path: Path) -> None:
    decision = valid_decision()
    provider = FakeProvider(json.dumps({"doc_id": DOC_ID}))
    schema_run = run(tmp_path / "schema", provider, [decision])
    assert schema_run.valid_cases == 0
    failures = (Path(schema_run.output_dir) / "extraction_failures.jsonl").read_text(encoding="utf-8")
    assert "schema_validation_failed" in failures
    reviews = (Path(schema_run.output_dir) / "review_queue.jsonl").read_text(encoding="utf-8")
    assert "schema_validation_failed" in reviews
    assert (Path(schema_run.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8").strip() == ""

    provider = FakeProvider(response(DOC_ID, [case_body(quote_text="this quote is not in the target")]))
    evidence_run = run(tmp_path / "evidence", provider, [decision])
    assert evidence_run.valid_cases == 0
    verdicts = (Path(evidence_run.output_dir) / "span_validations.jsonl").read_text(encoding="utf-8")
    assert "rejected" in verdicts or "pending" in verdicts
    assert "evidence_validation_failed" in (Path(evidence_run.output_dir) / "review_queue.jsonl").read_text(encoding="utf-8")

    provider = FakeProvider(
        response(
            DOC_ID,
            [
                {
                    **case_body(),
                    "field_evidence": [
                        {"field_name": "problem_summary", **quote("I wanted my cake photo.")},
                        {"field_name": "forgotten_information", **quote("I forgot the date.")},
                    ],
                }
            ],
        )
    )
    status_run = run(tmp_path / "status", provider, [decision])
    assert status_run.valid_cases == 0
    assert "observation_status_conflict" in (Path(status_run.output_dir) / "review_queue.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "submitted,start,end,offset_state,repaired",
    [
        ("I wanted my cake photo.", None, None, "repaired_unique", True),
        ("I wanted my cake photo.", 1, 23, "repaired_unique", True),
        ("I wanted my  cake photo.", None, None, "repaired_whitespace", True),
        ("I wanted my cake photo.", 0, 23, "supplied_exact", False),
    ],
)
def test_span_verdicts_retain_supplied_quotes_and_offsets(
    tmp_path: Path, submitted: str, start: int | None, end: int | None,
    offset_state: str, repaired: bool,
) -> None:
    body = case_body()
    body["field_evidence"][0].update(quote=submitted, start_char=start, end_char=end)
    result = run(tmp_path, FakeProvider(response(DOC_ID, [body])), [valid_decision()])
    assert result.valid_cases == 1
    row, = jsonl(Path(result.output_dir) / "span_validations.jsonl")
    assert row["candidate_quote"] == submitted
    assert row["candidate_start_char"] == start
    assert row["candidate_end_char"] == end
    assert row["candidate_offset_state"] == (
        "missing_unresolved" if start is None else "supplied_exact"
    )
    assert row["repair_applied"] is repaired
    assert row["offset_state"] == offset_state
    assert row["quote"] == "I wanted my cake photo."
    assert TEXT[row["start_char"]:row["end_char"]] == row["quote"]


def test_failure_retains_all_gate_findings_without_changing_review_priority(tmp_path: Path) -> None:
    body = case_body()
    body["field_evidence"].append(
        {"field_name": "retrieval_trigger", **quote("Two sentences spliced into a fabricated quote.")}
    )
    result = run(tmp_path, FakeProvider(response(DOC_ID, [body])), [valid_decision()])
    destination = Path(result.output_dir)
    assert result.valid_cases == 0
    failure, = jsonl(destination / "extraction_failures.jsonl")
    assert failure["validation_errors"] == ["evidence_validation_failed"]
    assert failure["reason_codes"] == ["evidence_validation_failed", "observation_status_conflict"]
    assert failure["invalid_fields"] == ["retrieval_trigger"]
    rejected, = [row for row in jsonl(destination / "evidence_spans.jsonl") if row["validation_state"] == "rejected"]
    assert failure["retained_span_ids"] == [rejected["evidence_id"]]
    assert any("retrieval_trigger" in error and "forbids evidence" in error for error in failure["gate_errors"])
    review, = jsonl(destination / "review_queue.jsonl")
    assert review["target_type"] == "retrieval_case"
    assert review["target_id"] == failure["case_id"]
    assert review["reason_code"] == "evidence_validation_failed"
    assert jsonl(destination / "retrieval_cases.jsonl") == []


def test_gate_prose_is_bounded_and_source_or_secrets_are_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    from src.pipeline import extraction

    assemble = extraction.assemble_cases
    secret = "synthetic-secret-never-store"

    def extra_messages(*args, **kwargs):
        result, = assemble(*args, **kwargs)
        gate = replace(
            result.record_validation,
            errors=("x" * 700, "x" * 600 + secret, TEXT, *(f"finding {index}" for index in range(36))),
        )
        return (replace(result, record_validation=gate),)

    monkeypatch.setattr(extraction, "assemble_cases", extra_messages)
    result = run(
        tmp_path, FakeProvider(response(DOC_ID, [case_body(quote_text="Fabricated event.")])),
        [valid_decision()], denylist=(secret,),
    )
    failure, = jsonl(Path(result.output_dir) / "extraction_failures.jsonl")
    assert len(failure["gate_errors"]) == 30  # At most 32 messages, with two unsafe ones omitted.
    assert failure["gate_errors"][0] == "x" * 500
    assert all(len(message) <= 500 for message in failure["gate_errors"])
    assert secret not in json.dumps(failure)
    assert TEXT not in json.dumps(failure)
    assert failure["reason_codes"] == ["evidence_validation_failed"]
    assert failure["invalid_fields"] == ["problem_summary"]


@pytest.mark.parametrize(
    "reply,state",
    [
        (response(DOC_ID, [case_body(quote_text="A fabricated quote.")]), "evidence_validation_failed"),
        (json.dumps({"doc_id": DOC_ID}), "schema_validation_failed"),
        ("unparseable reply", "response_parse_failed"),
    ],
)
def test_failed_extraction_checkpoints_agree_with_events_and_resume_reprocesses(
    tmp_path: Path, reply: str, state: str,
) -> None:
    provider = FakeProvider(reply)
    first = run(tmp_path, provider, [valid_decision()])
    destination = Path(first.output_dir)
    assert first.by_state == {state: 1}
    checkpoint, = jsonl(destination / "checkpoints.jsonl")
    event, = jsonl(destination / "stage_events.jsonl")
    assert checkpoint["status"] == event["status"] == "failed"

    # Reprocess the cached response; resume must not treat a failure as complete.
    provider.calls = 0
    second = run(tmp_path, provider, [valid_decision()], resume=first.run_id)
    assert second.attempted == 1
    assert second.cache_hits == 1
    assert second.provider_calls == provider.calls == 0
    assert second.by_state == {state: 1}
    assert second.valid_cases == 0


def test_blocked_relevance_stays_on_decision_and_empty_extraction_succeeds(tmp_path: Path) -> None:
    decision = valid_decision(
        scope_class=ScopeClass.out_of_scope, reason_code=ReasonCode.editing_sharing_or_printing,
    )
    provider = FakeProvider()
    blocked = run(tmp_path / "blocked", provider, [decision])
    event, = jsonl(Path(blocked.output_dir) / "stage_events.jsonl")
    recorded, = jsonl(Path(blocked.output_dir) / "extraction_inputs.jsonl")
    assert provider.calls == 0
    assert jsonl(Path(blocked.output_dir) / "review_queue.jsonl") == []
    assert event["status"] == "skipped"
    assert event["detail"]["skip_cause"] == "out_of_scope"
    assert recorded["eligible"] is False
    assert recorded["skip_cause"] == "out_of_scope"
    assert recorded["technical_state"] == "evidence_validation_failed"
    failure, = jsonl(Path(blocked.output_dir) / "extraction_failures.jsonl")
    assert failure["skip_cause"] == "out_of_scope"

    rejected = make_decision(
        technical_state=DecisionTechnicalState.evidence_validation_failed,
        validation_state=ValidationState.pending,
        scope_class=None,
        confidence=None,
        evidence=(),
        needs_human_review=True,
        reason_code=ReasonCode.evidence_validation_failed,
    )
    rejected_run = run(tmp_path / "rejected", FakeProvider(), [rejected])
    review, = jsonl(Path(rejected_run.output_dir) / "review_queue.jsonl")
    event, = jsonl(Path(rejected_run.output_dir) / "stage_events.jsonl")
    assert review["target_id"] == rejected.decision_id
    assert event["detail"]["skip_cause"] == "relevance_not_accepted"

    empty = run(tmp_path / "empty", FakeProvider(response(DOC_ID, [])), [valid_decision()])
    checkpoint, = jsonl(Path(empty.output_dir) / "checkpoints.jsonl")
    assert checkpoint["status"] == "succeeded"
    assert jsonl(Path(empty.output_dir) / "review_queue.jsonl") == []


def test_attempt_routing_preserves_old_review_items_and_scopes_new_items_by_run(tmp_path: Path) -> None:
    from src.pipeline.extraction import ExtractionInput, _DocOutcome, _merge_reviews, _write_models
    from src.review.queue import append_resolution, open_extraction_items

    decision = valid_decision()
    old, = open_extraction_items(
        [("relevance_decision", decision.decision_id, ReasonCode.provider_unavailable)], opened_at=NOW,
    )
    path = tmp_path / "review_queue.jsonl"
    original = json.dumps(old.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(original, encoding="utf-8")
    outcome = _DocOutcome(
        item=ExtractionInput(DOC_ID, decision, True), state=DecisionTechnicalState.provider_error,
    )
    items = _merge_reviews(path, "run-one", [outcome])
    assert path.read_text(encoding="utf-8") == original
    _write_models(path, items, "item_id")
    assert original in path.read_text(encoding="utf-8").splitlines(keepends=True)
    items = _merge_reviews(path, "run-two", [outcome])
    retained, = [item for item in items if item.item_id == old.item_id]
    assert retained.model_dump_json() == old.model_dump_json()
    attempts = [item for item in items if item.target_type == "extraction_attempt"]
    assert {item.target_id for item in attempts} == {f"run-one:{DOC_ID}", f"run-two:{DOC_ID}"}
    assert len({item.item_id for item in attempts}) == 2
    _write_models(path, items, "item_id")
    assert len(_merge_reviews(path, "run-two", [outcome])) == len(items)
    resolved = append_resolution(items, old.item_id, decision="extraction issue", resolver="synthetic", resolved_at=NOW)
    assert retained in resolved
    assert len(resolved) == len(items) + 1
    assert original in path.read_text(encoding="utf-8").splitlines(keepends=True)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_dry_run_writes_nothing_and_calls_nothing(tmp_path: Path) -> None:
    provider = FakeProvider(response(DOC_ID, [case_body()]))
    result = run(tmp_path, provider, [valid_decision()], dry_run=True)
    assert result.provider_calls == 0
    assert provider.calls == 0
    assert result.files_written == ()
    assert list(tmp_path.iterdir()) == []


def test_null_provider_records_unavailability_without_cases(tmp_path: Path) -> None:
    result = run_extraction(
        doc_ids=[DOC_ID],
        model_decisions=[valid_decision()],
        human_decisions=[],
        derived_by_id={DOC_ID: derived()},
        output_dir=tmp_path,
        offline=True,
        provider_name="null",
        model_name="synthetic-extraction-model",
        max_retries=1,
        cache_dir=tmp_path / "cache",
    )
    assert result.provider_calls == 0
    assert result.valid_cases == 0
    failure = (Path(result.output_dir) / "extraction_failures.jsonl").read_text(encoding="utf-8")
    assert "provider_unavailable" in failure
    assert (Path(result.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8").strip() == ""
    assert not any((tmp_path / "cache").glob("**/*"))


def test_resume_skips_finished_work_and_cache_hit_skips_the_provider(tmp_path: Path) -> None:
    decision = valid_decision()
    provider = FakeProvider(response(DOC_ID, [case_body()]))
    first = run(tmp_path, provider, [decision])
    assert provider.calls == 1
    provider.calls = 0
    second = run(tmp_path, provider, [decision], resume=first.run_id)
    assert provider.calls == 0
    assert second.attempted == 0
    assert second.valid_cases == 0
    kept = (Path(first.output_dir) / "retrieval_cases.jsonl").read_text(encoding="utf-8")
    assert f"{DOC_ID}#c01" in kept

    other = tmp_path / "other"
    cached = FakeProvider(response(DOC_ID, [case_body()]))
    again = run(other, cached, [decision], cache_dir=tmp_path / "cache")
    assert cached.calls == 0
    assert again.cache_hits == 1
    assert again.valid_cases == 1


def test_prompt_excludes_human_labels_and_cache_ignores_taxonomy(tmp_path: Path) -> None:
    decision = valid_decision()
    provider = FakeProvider(response(DOC_ID, [case_body()]))
    result = run(
        tmp_path,
        provider,
        [decision],
        approved_labels={DOC_ID: ("adjacent_known_item_retrieval", "known_item_with_precise_recall_failure")},
    )
    assert provider.prompts
    prompt = provider.prompts[0]
    assert LEAK not in prompt
    assert "human_notes" not in prompt
    assert "known_item_with_precise_recall_failure" not in prompt
    assert provider.schemas[0] is not None
    embedded = prompt.split("Transmitted JSON Schema:\n", 1)[1].split("\n\nUNTRUSTED", 1)[0]
    assert json.loads(embedded) == json.loads(json.dumps(provider.schemas[0], sort_keys=True))
    cache_files = list((tmp_path / "cache").glob("**/*.json"))
    assert cache_files
    stored = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert stored["ruleset_version"] is None
    assert "taxonomy_version" not in stored
    assert TAXONOMY_VERSION not in json.dumps(stored["decoding_params"])
    inputs = (Path(result.output_dir) / "extraction_inputs.jsonl").read_text(encoding="utf-8")
    assert '"decided_by": "llm"' in inputs


def test_provider_diagnostic_persists_status_without_source_or_credentials(tmp_path: Path) -> None:
    from src.llm.providers.base import ProviderCallError, ProviderDiagnostic

    secret = "gsk-test-secret-not-real"

    class Failing(FakeProvider):
        def complete_structured(self, prompt: str, schema: dict, params: CompletionParams) -> ProviderResponse:
            self.calls += 1
            self.prompts.append(prompt)
            raise ProviderCallError(
                f"vendor rejected {secret}",
                DecisionTechnicalState.provider_error,
                diagnostic=ProviderDiagnostic(
                    category="invalid_request",
                    http_status=400,
                    error_code="json_validate_failed",
                    error_message=f"{TEXT} Authorization: Bearer {secret}",
                ),
            )

    provider = Failing()
    result = run(tmp_path, provider, [valid_decision()], denylist=(secret,))
    assert provider.calls == 1
    assert result.provider_calls == 1
    assert result.valid_cases == 0
    stored = (Path(result.output_dir) / "extraction_failures.jsonl").read_text(encoding="utf-8")
    events = (Path(result.output_dir) / "stage_events.jsonl").read_text(encoding="utf-8")
    assert secret not in stored
    assert TEXT not in stored
    assert secret not in events
    assert TEXT not in events
    row = json.loads(stored)
    diagnostic = row["provider_diagnostic"]
    assert diagnostic["category"] == "invalid_request"
    assert diagnostic["http_status"] == 400
    assert diagnostic["error_code"] == "json_validate_failed"
    assert "error_message" not in diagnostic
    event = json.loads(events)
    assert event["detail"]["provider_diagnostic"]["category"] == "invalid_request"
    assert event["detail"]["provider_diagnostic"]["http_status"] == 400
    review, = jsonl(Path(result.output_dir) / "review_queue.jsonl")
    assert review["target_type"] == "extraction_attempt"
    assert review["target_id"] == f"{result.run_id}:{DOC_ID}"
    assert review["reason_code"] == "provider_unavailable"  # Vocabulary change remains deferred.
    written = "\n".join(path.read_text(encoding="utf-8") for path in Path(result.output_dir).glob("*"))
    assert secret not in written
    assert TEXT not in written


def test_stage_module_does_not_import_a_provider_sdk() -> None:
    tree = ast.parse((PROJECT / "src/pipeline/extraction.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(name.split(".")[0] in {"groq", "anthropic", "openai"} for name in imported)
