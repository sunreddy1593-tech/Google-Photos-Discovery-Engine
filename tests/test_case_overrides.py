"""Human case overrides. No provider and no corpus files."""

from __future__ import annotations

from pathlib import Path

from src.core.versions import SCHEMA_VERSION
from src.models.enums import ExtractorType, ValidationState
from src.pipeline.extraction import PROMPT_ID, extraction_request_identity
from src.pipeline.human_cases import build_human_case
from src.review.overrides import append_case_overrides, make_case_override, v_current_cases
from tests.synthetic import NOW, RAW_TEXT_AUDIT, make_case
from tests.test_extraction_pilot import _derived


def _override(**kwargs):
    fields = dict(
        doc_id="reddit-000000000001",
        target_id="reddit-000000000001#c01",
        author="reviewer",
        rationale="The stored case remains the model row.",
        created_at=NOW,
    )
    fields.update(kwargs)
    return make_case_override(**fields)


def test_human_override_supersedes_without_editing_the_model_row() -> None:
    model = make_case()
    human = build_human_case(
        model,
        _override(),
        audit=RAW_TEXT_AUDIT,
        content_hash="a" * 64,
        extracted_at=NOW,
    )
    current = v_current_cases([model, human])
    assert model.extractor_type is ExtractorType.llm
    assert model.model_name == "synthetic-test-model"
    assert human.extractor_type is ExtractorType.human
    assert human.model_name is None
    assert human.validation_state is ValidationState.valid
    assert current == (human,)
    assert "taxonomy_version" not in human.model_fields_set
    assert "taxonomy_version" not in type(human).model_fields


def test_pending_quote_and_pending_state_do_not_replace_the_model() -> None:
    model = make_case()
    rejected = build_human_case(
        model,
        _override(evidence_quote="this quote is not in the document"),
        audit=RAW_TEXT_AUDIT,
        content_hash="a" * 64,
        extracted_at=NOW,
    )
    assert rejected.validation_state is ValidationState.pending
    assert v_current_cases([model, rejected]) == (model,)

    pending = human_copy(model, ValidationState.pending)
    assert v_current_cases([model, pending]) == (model,)


def test_verbatim_optional_quote_can_become_current() -> None:
    model = make_case()
    human = build_human_case(
        model,
        _override(evidence_quote="I scrolled for twenty minutes"),
        audit=RAW_TEXT_AUDIT,
        content_hash="b" * 64,
        extracted_at=NOW,
    )
    assert human.validation_state is ValidationState.valid
    assert v_current_cases([model, human]) == (human,)


def test_case_override_ledger_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "case_overrides.jsonl"
    first = _override()
    append_case_overrides(path, [first])
    before = path.read_bytes()
    again = append_case_overrides(path, [first])
    assert path.read_bytes() == before
    assert len(again) == 1
    second = _override(rationale="A later note, not an edit of the first.")
    append_case_overrides(path, [second])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].encode("utf-8") == before.strip()
    assert len(lines) == 2


def test_extraction_cache_key_ignores_taxonomy_version() -> None:
    derived = _derived("doc-a")
    identity = extraction_request_identity(
        derived,
        provider_name="groq",
        model_name="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=8192,
        prompt_version_value="extract/v2",
    )
    assert identity["prompt_id"] == PROMPT_ID
    assert "taxonomy_version" not in identity
    assert SCHEMA_VERSION
    changed = extraction_request_identity(
        derived,
        provider_name="groq",
        model_name="other-model",
        temperature=0.0,
        max_tokens=8192,
        prompt_version_value="extract/v2",
    )
    assert changed["cache_key"] != identity["cache_key"]


def human_copy(model, state: ValidationState):
    payload = model.model_dump(mode="python")
    payload.update(
        extractor_type=ExtractorType.human,
        model_name=None,
        validation_state=state,
        extraction_fingerprint="humanpending1",
    )
    from src.models.retrieval_case import RetrievalCase

    return RetrievalCase.model_validate(payload)
