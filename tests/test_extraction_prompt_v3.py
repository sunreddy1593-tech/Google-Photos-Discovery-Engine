"""extract/v3 clarifications. Synthetic fixtures only. No provider and no corpus text.

A mocked response that follows these fixtures does not show that a live model
will follow the instructions. The gates still check quotes and field attachment,
not whether a verbatim quote means the assigned value.
"""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

import pytest

from src.core.versions import (
    EXTRACTION_PROMPT_CORRECTION,
    EXTRACTION_PROMPT_VERSION,
    PROMPT_VERSIONS,
    prompt_version,
)
from src.extract.extractor import assemble_cases
from src.extract.prompts import build_extraction_prompt
from src.extract.schema import ExtractionPayload
from src.models.enums import DecisionTechnicalState, OffsetState, ScopeClass
from src.pipeline.extraction import PROMPT_ID, transmitted_extraction_schema
from src.pipeline.extraction_development import DevelopmentBoundsError, assert_development_bounds
from src.pipeline.extraction_pilot import (
    PILOT_MODEL,
    PILOT_PROVIDER,
    PilotBoundsError,
    confirm_corrected_schema_cache,
)
from tests.synthetic import DOC_ID, NOW, make_decision
from tests.test_extraction import FakeProvider, derived, jsonl, response, run, valid_decision
from tests.test_extraction_eight_k_pilot import SEAT, _inputs, _seed
from tests.test_extraction_foundation import quote
from tests.test_extraction_prompt_v2 import render

pytestmark = pytest.mark.synthetic

V2_INSTRUCTION_SHA256 = "cb1cbe5262dd601695dda9f5c692956b7b7e96d11efa64ca4065eca52497aba4"

ALBUM = (
    "I want to find one of my family. I would scroll through hundreds of photos "
    "to find the one I want. It seems you can't search for a face within a specific album."
)
MEMORIES = "My photo memories come up and I can see randomly but how do I go back to view them?"
POODLE = (
    "Say I have 500 photos and 75 poodles and I might page through them or group terriers. "
    "Later, searching for poodles isn't working. After using CtrlF, it says there are 0 poodle pictures."
)
SLEEP = (
    'I took a video of it once. I can\'t remember when it was. '
    'I searched "Show me videos of Suzie sleeping" and up it pops.'
)
OLDER = (
    "I have an older photo I have of that same item. I don't remember when I took the photo. "
    "I have so many photos I can't find it. Can you match it from a recent picture?"
)
CAT = (
    "I am trying to show a friend some pictures of my cats. Search got no results. "
    "The Gallery app has no search, so I scrolled through every photo."
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("extract/v3 regressions must remain offline")

    monkeypatch.setattr(socket, "socket", forbidden)


def test_active_pin_stays_on_v2_and_v3_is_only_a_prepared_correction():
    assert EXTRACTION_PROMPT_VERSION == "extract/v2"
    assert EXTRACTION_PROMPT_CORRECTION == "extract/v3"
    assert prompt_version("extract") == "extract/v2"
    assert "extract/v3" not in PROMPT_VERSIONS.values()


def test_v2_instruction_rendering_is_unchanged_and_v1_has_no_v3_rules():
    current = render("extract/v2").split("Transmitted JSON Schema:\n", 1)[0]
    assert hashlib.sha256(current.encode()).hexdigest() == V2_INSTRUCTION_SHA256
    historical = render("extract/v1")
    assert "album-scoped face-search request" not in historical
    assert "album-scoped face-search request" not in render("extract/v2")


def test_v3_states_the_approved_clarifications_without_changing_the_wire_schema():
    prompt = render("extract/v3")
    assert prompt.startswith("Extraction prompt: extract/v3\n")
    for rule in (
        "album-scoped face-search request",
        "revisit previously seen",
        "succeeds even though recall is incomplete",
        "explicitly stated reason the item was needed",
        "cannot support a remembered",
        "prose help request",
        "query_paraphrase stays null and not_stated for",
        "Remaining ambiguity: a paraphrase",
        "do not establish the eventual outcome",
        "meaningful elapsed time",
        "separate sittings",
        "alternate app plus item-by-item browsing",
        "exact_query needs its",
        "own field_evidence entry",
        "Never splice passages",
        "every factual clause",
        "proposed paging",
    ):
        assert rule in prompt
    assert render("extract/v2").split("Transmitted JSON Schema:\n", 1)[1] == prompt.split(
        "Transmitted JSON Schema:\n", 1
    )[1]


def test_v3_cache_identity_misses_a_v2_entry(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    provider = FakeProvider(response(DOC_ID, []))
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v2")
    historical = run(tmp_path / "v2", provider, [valid_decision()], cache_dir=cache)
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v3")
    current = run(tmp_path / "v3", provider, [valid_decision()], cache_dir=cache)
    assert current.provider_calls == 1
    assert current.cache_hits == 0
    old_input, = jsonl(Path(historical.output_dir) / "extraction_inputs.jsonl")
    new_input, = jsonl(Path(current.output_dir) / "extraction_inputs.jsonl")
    assert old_input["request_identity"]["prompt_sha256"] != new_input["request_identity"]["prompt_sha256"]
    assert new_input["request_identity"]["prompt_version"] == "extract/v3"


def test_five_document_cache_guard_fails_closed_for_v3(tmp_path, monkeypatch):
    _ids, _decisions, documents = _inputs()
    cache = tmp_path / "cache"
    _seed(cache, documents[SEAT])
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v3")
    with pytest.raises(PilotBoundsError, match="expected corrected-schema cache entry is missing"):
        confirm_corrected_schema_cache(
            doc_ids=_ids,
            derived_by_id=documents,
            cache_dir=cache,
            provider_name=PILOT_PROVIDER,
            model_name=PILOT_MODEL,
            temperature=0.0,
            max_tokens=8192,
        )


def test_development_corpus_bounds_remain_pinned_to_v2(monkeypatch):
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v3")
    with pytest.raises(DevelopmentBoundsError, match="requires extract/v2"):
        assert_development_bounds(
            doc_ids=("doc-a",),
            development=("doc-a",),
            holdout=(),
            provider=PILOT_PROVIDER,
            model=PILOT_MODEL,
            max_retries=1,
            max_tokens=8192,
            call_budget=1,
            eligible=1,
            split="development",
        )


def test_exact_query_still_needs_its_own_field_evidence():
    text = SLEEP
    shared = "I searched \"Show me videos of Suzie sleeping\""
    body = _case(
        text,
        summary="The author found a sleeping video with a quoted search.",
        summary_quotes=(shared, "and up it pops"),
        exact_query="Show me videos of Suzie sleeping",
        strategies=[("natural_language_description", shared)],
        responses=[("other", "and up it pops")],
        forgotten=[("exact_date", "I can't remember when it was")],
        known=("I took a video of it once",),
        asset=("video", "I took a video"),
    )
    missing = _without_field(body, "exact_query")
    rejected, = _assemble(missing, text)
    assert rejected.technical_state is not DecisionTechnicalState.ok
    assert "exact_query" in rejected.record_validation.invalid_fields
    accepted, = _assemble(body, text)
    assert accepted.technical_state is DecisionTechnicalState.ok
    assert accepted.case.exact_query == "Show me videos of Suzie sleeping"
    assert any(span.field_name == "exact_query" for span in accepted.external_spans)
    assert any(span.field_name == "query_strategies" for span in accepted.case.inline_evidence_spans())


def test_spliced_quote_is_rejected_and_a_continuous_poodle_quote_is_accepted():
    spliced = _case(
        POODLE,
        summary="The author reports a failed poodle search.",
        summary_quotes=("CtrlF says there are 0 poodle pictures",),
    )
    rejected, = _assemble(spliced, POODLE)
    assert rejected.requires_review
    assert not rejected.span_validations[0].ok
    accepted_body = _case(
        POODLE,
        summary="The author reports that searching for poodles returns zero results.",
        summary_quotes=("searching for poodles isn't working", "0 poodle pictures"),
        strategies=[("single_keyword", "searching for poodles isn't working")],
        responses=[("no_results", "0 poodle pictures")],
        paraphrase=None,
    )
    accepted, = _assemble(accepted_body, POODLE)
    assert accepted.technical_state is DecisionTechnicalState.ok
    assert accepted.case.outcome is None
    assert accepted.case.severity is None
    assert accepted.case.query_paraphrase is None


def test_repeated_short_quote_stays_unresolved_without_unique_offsets():
    text = "poodles here and poodles there"
    body = _case(text, summary="poodles", summary_quotes=("poodles",))
    result, = _assemble(body, text)
    assert "#u" in result.case_id
    assert result.span_validations[0].span.offset_state is OffsetState.ambiguous_tied


def test_approved_episode_fixtures_leave_unstated_fields_empty():
    album, = _assemble(_case(
        ALBUM,
        summary="The author wants to find one family photo.",
        summary_quotes=("I want to find one of my family",),
        cues=[("relationship", "one of my family")],
        asset=("photo", "photos"),
    ), ALBUM)
    assert album.technical_state is DecisionTechnicalState.ok
    assert album.case.exact_query is None
    assert album.case.outcome is None
    assert album.case.severity is None
    assert album.case.retrieval_trigger is None

    memories, = _assemble(_case(
        MEMORIES,
        summary="The author wants to revisit previously seen photo Memories.",
        summary_quotes=(MEMORIES,),
        asset=("photo", "photo memories"),
    ), MEMORIES)
    assert memories.technical_state is DecisionTechnicalState.ok
    assert memories.case.exact_query is None
    assert memories.case.system_responses == ()

    older, = _assemble(_case(
        OLDER,
        summary="The author cannot find an older photo of the same item.",
        summary_quotes=("I have so many photos I can't find it",),
        forgotten=[("exact_date", "I don't remember when I took the photo.")],
        known=("an older photo I have of that same item",),
        asset=("photo", "older photo"),
        outcome=("not_found", "I have so many photos I can't find it"),
    ), OLDER)
    assert older.technical_state is DecisionTechnicalState.ok
    assert older.case.remembered_cues == ()
    assert older.case.query_strategies == ()
    assert older.case.query_paraphrase is None
    assert older.case.forgotten_information[0].value.value == "exact_date"
    assert older.case.outcome.value == "not_found"

    cat, = _assemble(_case(
        CAT,
        summary="The author could not find cat photos.",
        summary_quotes=("pictures of my cats", "Search got no results"),
        trigger=("show a friend some pictures",),
        cues=[("object_or_subject", "pictures of my cats")],
        subjects=[("pet_or_animal", "cats")],
        asset=("photo", "photo"),
        responses=[("no_results", "got no results"), ("other", "Gallery app has no search")],
        workarounds=[
            ("manual_scrolling", "I scrolled through every photo"),
            ("used_external_app", "The Gallery app"),
        ],
        severity_quotes=("The Gallery app", "I scrolled through every photo"),
    ), CAT)
    assert cat.technical_state is DecisionTechnicalState.ok
    assert cat.case.severity == 3
    assert cat.case.impact_signals == ()
    assert cat.case.impact_signals_observation.value == "not_stated"
    assert cat.case.outcome is None
    assert cat.case.retrieval_trigger == "show a friend some pictures"


def test_gate_still_accepts_a_verbatim_quote_assigned_to_the_wrong_meaning():
    """The prompt forbids this assignment. The quote gate does not judge meaning."""
    body = _case(
        OLDER,
        summary="The author cannot find an older photo of the same item.",
        summary_quotes=("I have so many photos I can't find it",),
        cues=[("approximate_time", "I don't remember when I took the photo.")],
    )
    result, = _assemble(body, OLDER)
    assert result.technical_state is DecisionTechnicalState.ok
    assert result.case.remembered_cues[0].value.value == "approximate_time"


def _case(
    text,
    *,
    summary,
    summary_quotes,
    exact_query=None,
    strategies=(),
    responses=(),
    forgotten=(),
    cues=(),
    subjects=(),
    workarounds=(),
    known=(),
    asset=None,
    trigger=(),
    outcome=None,
    paraphrase=None,
    severity_quotes=(),
):
    del text
    evidence = [{"field_name": "problem_summary", **quote(item)} for item in summary_quotes]
    body = {
        "problem_summary": summary,
        "field_evidence": evidence,
        "query_strategies": [_label(value, span) for value, span in strategies],
        "system_responses": [_label(value, span) for value, span in responses],
        "forgotten_information": [_label(value, span) for value, span in forgotten],
        "remembered_cues": [_label(value, span) for value, span in cues],
        "target_subjects": [_label(value, span) for value, span in subjects],
        "workarounds": [_label(value, span) for value, span in workarounds],
    }
    if strategies:
        body["query_strategies_observation"] = "stated"
    if responses:
        body["system_responses_observation"] = "stated"
    if forgotten:
        body["forgotten_information_observation"] = "stated"
    if cues:
        body["remembered_cues_observation"] = "stated"
    if subjects:
        body["target_subjects_observation"] = "stated"
    if workarounds:
        body["workarounds_observation"] = "stated"
    if known:
        body["known_item_status"] = "explicit"
        body["known_item_status_observation"] = "stated"
        evidence.append({"field_name": "known_item_status", **quote(known[0])})
    if asset is not None:
        body["target_asset_type"] = asset[0]
        body["target_asset_type_observation"] = "stated"
        evidence.append({"field_name": "target_asset_type", **quote(asset[1])})
    if trigger:
        body["retrieval_trigger"] = trigger[0]
        body["retrieval_trigger_observation"] = "stated"
        evidence.append({"field_name": "retrieval_trigger", **quote(trigger[0])})
    if exact_query is not None:
        body["exact_query"] = exact_query
        body["exact_query_observation"] = "stated"
        evidence.append({"field_name": "exact_query", **quote(f'"{exact_query}"')})
    if outcome is not None:
        body["outcome"] = outcome[0]
        body["outcome_observation"] = "stated"
        evidence.append({"field_name": "outcome", **quote(outcome[1])})
    if paraphrase is not None:
        body["query_paraphrase"] = paraphrase
        body["query_paraphrase_observation"] = "stated"
    if severity_quotes:
        body["severity"] = 3
        body["severity_observation"] = "stated"
        body["severity_evidence"] = [quote(item) for item in severity_quotes]
    return body


def _label(value, span):
    return {"value": value, "evidence": quote(span)}


def _without_field(body, field_name):
    copied = dict(body)
    copied["field_evidence"] = [
        item for item in body["field_evidence"] if item["field_name"] != field_name
    ]
    return copied


def _assemble(body, text):
    return assemble_cases(
        ExtractionPayload.model_validate({"doc_id": DOC_ID, "cases": [body]}),
        derived(text=text),
        make_decision(validation_state="valid", scope_class=ScopeClass.adjacent_known_item_retrieval),
        model_name="synthetic-test-model",
        prompt_version="extract/v3",
        extracted_at=NOW,
    )


def test_renderer_refuses_to_build_a_prompt_for_an_unregistered_correction():
    with pytest.raises(ValueError, match="unsupported extraction prompt"):
        build_extraction_prompt(
            derived(),
            prompt_version="extract/v9",
            transmitted_schema=transmitted_extraction_schema(DOC_ID, provider_name="groq"),
        )
    assert PROMPT_ID == "extract"


def test_v4_candidate_is_renderable_and_does_not_replace_measured_v3():
    from src.core.versions import EXTRACTION_PROMPT_CANDIDATE, EXTRACTION_PROMPT_CORRECTION
    measured = render("extract/v3")
    current = measured.split("Transmitted JSON Schema:\n", 1)[0]
    assert hashlib.sha256(current.encode()).hexdigest() == (
        "8805ca3bc7e281256df02279176e5904fc6d63e3b10cc522847a78a9e438c76e"
    )
    candidate = render("extract/v4")
    assert EXTRACTION_PROMPT_CANDIDATE == "extract/v4"
    assert EXTRACTION_PROMPT_CORRECTION == "extract/v3"
    assert prompt_version("extract") == "extract/v2"
    assert "extract/v4" not in PROMPT_VERSIONS.values()
    assert "empty case list" in candidate
    assert "empty case list" not in measured
    assert candidate.split("Transmitted JSON Schema:\n", 1)[1] == measured.split(
        "Transmitted JSON Schema:\n", 1
    )[1]


def test_v5_candidate_is_development_only_and_does_not_replace_the_pin():
    from src.core.versions import EXTRACTION_PROMPT_DEV_CANDIDATE
    rendered = render("extract/v5")
    assert EXTRACTION_PROMPT_DEV_CANDIDATE == "extract/v5"
    assert prompt_version("extract") == "extract/v2"
    assert "extract/v5" not in PROMPT_VERSIONS.values()
    assert "75 of the poodles" in rendered
    assert "unbroken substring" in rendered
