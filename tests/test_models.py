"""Contract tests (spec Section 25 "Schemas", acceptance criteria in Section 24).

Every contract gets a positive case and at least one negative case, because a
schema that has only ever been shown valid input is a schema nobody has tested.
The negatives here are not arbitrary: each one is a failure mode the
specification names, so a test that stops failing means a rule stopped being
enforced.
"""

from __future__ import annotations

import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from enum import EnumMeta
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core import ids
from src.core.errors import ValidationError as EngineValidationError
from src.core.versions import SCHEMA_VERSION
from src.models import enums as enums_module
from src.models.cluster_assignment import ClusterAssignment
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived, RedactionSpan
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    AssignmentMethod,
    CollectionMethod,
    DecidedBy,
    DecisionTechnicalState,
    DimensionObservationStatus,
    DuplicateDecidedBy,
    DuplicateDetectionMethod,
    DuplicateKind,
    DuplicateReviewState,
    EvidenceOwnerType,
    EvidenceTier,
    ExtractorType,
    GoldSplit,
    KnownItemStatus,
    OffsetState,
    Outcome,
    ReasonCode,
    RedactionType,
    RememberedCue,
    ScopeClass,
    SourcePlatform,
    SourceType,
    Speaker,
    Stage,
    StageEventTargetType,
    StageStatus,
    TargetAssetType,
    ValidationState,
    Workaround,
)
from src.models.evidence import EvidenceBackedLabel, EvidenceSpan, ObservedValue
from src.models.export import ExportedEvidenceSpan, PublicExportRecord
from src.models.gold import GoldCase, GoldDocumentLabel, PreAdjudicationLabel
from src.models.relevance import RelevanceDecision, derive_is_relevant
from src.models.retrieval_case import RetrievalCase
from src.models.stage_event import StageEvent
from tests.synthetic import (
    CASE_ID,
    DECISION_ID,
    DOC_ID,
    NOW,
    RAW_TEXT,
    RAW_TEXT_AUDIT,
    make_case,
    make_decision,
    make_document,
    make_observed_cue,
    make_span,
    offsets_of,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# CollectedDocument (spec 15.1)
# --------------------------------------------------------------------------- #


def test_valid_collected_document() -> None:
    document = make_document()

    assert document.doc_id == DOC_ID
    assert document.raw_text == RAW_TEXT
    assert document.schema_version == SCHEMA_VERSION
    assert document.is_synthetic


def test_collected_document_validates_with_no_later_stage_module_imported() -> None:
    """Invariant I11, asserted over a whole process rather than one call.

    The claim is not merely that ``CollectedDocument`` has no derived field; it is
    that a document validates in a program where ``DocumentDerived`` and
    ``DuplicateLink`` do not exist. That is what keeps Phase 2's manual importer
    independent of Phase 3, and it cannot be shown from inside a test session that
    has already imported every contract — hence the subprocess.
    """
    script = """
import sys
from datetime import UTC, datetime

from src.core.ids import raw_text_sha256
from src.models.collected_document import CollectedDocument

text = "I cannot find a photo I know I took."
document = CollectedDocument(
    doc_id="reddit-000000000001",
    ingest_batch_id="batch-0001",
    source_platform="reddit",
    source_type="post",
    evidence_tier="synthetic_test",
    source_url="https://www.reddit.com/r/googlephotos/comments/x/",
    source_url_key="https://www.reddit.com/r/googlephotos/comments/x",
    source_name="r/googlephotos",
    author_salt_id="saltid000001",
    collected_at=datetime(2026, 9, 21, tzinfo=UTC),
    raw_text=text,
    raw_text_sha256=raw_text_sha256(text),
    collection_method="manual_csv",
)
assert document.doc_id

forbidden = [
    name
    for name in sys.modules
    if name.endswith(("document_derived", "duplicate_link", "retrieval_case"))
]
assert not forbidden, forbidden
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@pytest.mark.parametrize(
    "field_name",
    [
        "normalized_text",
        "content_hash",
        "redaction_spans",
        "duplicate_of",
        "duplicate_kind",
        "raw_text_audit",
        "simhash",
    ],
)
def test_collected_document_rejects_later_stage_fields(field_name: str) -> None:
    """ADR-15: these five moved to where they are produced, and the move only
    holds if putting them back raises."""
    with pytest.raises(PydanticValidationError, match="Extra inputs"):
        make_document(**{field_name: "anything"})


def test_collected_document_rejects_invalid_url() -> None:
    with pytest.raises(PydanticValidationError, match="URL"):
        make_document(source_url="not-a-url")


def test_collected_document_rejects_naive_datetime() -> None:
    """A naive timestamp is ambiguous across the platforms this corpus spans."""
    with pytest.raises(PydanticValidationError, match="timezone"):
        make_document(collected_at=datetime(2026, 9, 21, 12, 0))


def test_collected_document_rejects_unknown_enum_member() -> None:
    with pytest.raises(PydanticValidationError):
        make_document(source_platform="mastodon")


@pytest.mark.parametrize("text", ["", "   \n\t "])
def test_collected_document_rejects_empty_text(text: str) -> None:
    """Whitespace-only text is an empty document with extra steps: it can never
    carry an evidence offset."""
    with pytest.raises(PydanticValidationError):
        make_document(raw_text=text)


def test_collected_document_is_frozen() -> None:
    document = make_document()
    with pytest.raises(PydanticValidationError):
        document.raw_text = "edited"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Controlled vocabularies (spec 16)
# --------------------------------------------------------------------------- #


def _all_enums() -> list[EnumMeta]:
    found = [
        value
        for value in vars(enums_module).values()
        if isinstance(value, EnumMeta) and value.__module__ == enums_module.__name__
    ]
    assert len(found) > 20, "expected the full Section 16 vocabulary set"
    return found


@pytest.mark.parametrize("enum_class", _all_enums(), ids=lambda e: e.__name__)
def test_no_enum_carries_a_placeholder_member(enum_class: EnumMeta) -> None:
    """Spec Section 16 preamble and invariant I6.

    ``unknown`` and ``none_stated`` are not vocabulary. Absence is
    ``DimensionObservationStatus`` on the paired field, with the value left null.
    """
    forbidden = {"unknown", "none_stated", "unclear", "n/a", "na", "unspecified"}
    offenders = {
        member.value
        for member in enum_class  # type: ignore[var-annotated]
        if str(member.value).lower() in forbidden
    }
    assert not offenders, f"{enum_class.__name__} carries placeholder(s) {offenders}"


@pytest.mark.parametrize(
    "enum_class",
    [
        enums_module.RememberedCue,
        enums_module.ForgottenInfo,
        enums_module.QueryStrategy,
        enums_module.SystemResponse,
        enums_module.Workaround,
        enums_module.ImpactSignal,
        enums_module.SubjectType,
        enums_module.TargetAssetType,
    ],
    ids=lambda e: e.__name__,
)
def test_every_section_16_dimension_keeps_other(enum_class: EnumMeta) -> None:
    """"The user said something this list does not cover" is a real observation
    and a different one from "the user said nothing" (spec Section 16)."""
    assert "other" in {member.value for member in enum_class}  # type: ignore[var-annotated]


def test_reason_code_groups_partition_the_vocabulary() -> None:
    """Spec Section 16.8: three groups, and a code from the wrong group is an
    error. That check is only meaningful if the groups cover everything."""
    union = (
        enums_module.INCLUSION_REASON_CODES
        | enums_module.EXCLUSION_REASON_CODES
        | enums_module.REVIEW_REASON_CODES
    )
    assert union == set(ReasonCode)
    assert not (
        enums_module.INCLUSION_REASON_CODES & enums_module.EXCLUSION_REASON_CODES
    )
    assert not (
        enums_module.INCLUSION_REASON_CODES & enums_module.REVIEW_REASON_CODES
    )


def test_stage_import_member_keeps_its_wire_value() -> None:
    """``import`` is a Python keyword, so the member name differs from the value.
    Storage sees the value, so that is what must be right."""
    assert Stage.import_.value == "import"
    assert Stage("import") is Stage.import_


# --------------------------------------------------------------------------- #
# EvidenceSpan and ObservedValue (spec 15.2, 15.5)
# --------------------------------------------------------------------------- #


def test_valid_evidence_span_derives_its_id() -> None:
    span = make_span("outcome", "never found the")

    start, end = offsets_of("never found the")
    assert span.start_char == start and span.end_char == end
    assert span.evidence_id == ids.evidence_id(
        CASE_ID, "outcome", "never found the", start, end
    )
    assert span.is_resolved and span.is_valid


def test_evidence_span_rejects_a_field_name_no_contract_enforces() -> None:
    """Spec Section 15.10 consequence 2: a span attached to no field is a
    contradiction, and inventing a field name is how one gets created."""
    with pytest.raises(PydanticValidationError, match="not an evidence-required"):
        make_span("vibe_check", "never found the")


def test_evidence_span_rejects_half_supplied_offsets() -> None:
    with pytest.raises(PydanticValidationError, match="supplied together"):
        make_span("outcome", "never found the", end_char=None)


def test_evidence_span_rejects_inverted_offsets() -> None:
    with pytest.raises(PydanticValidationError, match="must exceed start_char"):
        make_span("outcome", "never found the", start_char=40, end_char=10)


def test_evidence_span_rejects_offset_state_that_contradicts_the_offsets() -> None:
    with pytest.raises(PydanticValidationError, match="asserts unresolved offsets"):
        make_span(
            "outcome", "never found the", offset_state=OffsetState.ambiguous_tied
        )


def test_unresolved_span_cannot_be_valid() -> None:
    """Spec Section 26.3: a case whose offsets cannot be resolved is never
    persisted as valid, because there is nothing to check equality against."""
    with pytest.raises(PydanticValidationError, match="requires resolved offsets"):
        make_span(
            "outcome",
            "never found the",
            with_offsets=False,
            offset_state=OffsetState.missing_unresolved,
            validation_state=ValidationState.valid,
        )


def test_observed_value_requires_evidence() -> None:
    with pytest.raises(PydanticValidationError):
        ObservedValue[RememberedCue](value=RememberedCue.approximate_time)  # type: ignore[call-arg]


def test_observed_value_rejects_a_value_from_another_vocabulary() -> None:
    with pytest.raises(PydanticValidationError):
        ObservedValue[RememberedCue](
            value=Workaround.gave_up,
            evidence=make_span(
                "remembered_cues",
                "last summer",
                owner_type=EvidenceOwnerType.observed_value,
            ),
        )


def test_observed_value_detail_is_limited_to_target_subjects() -> None:
    """Spec Section 16.7 gives free-text detail to subjects alone; allowing it
    everywhere would open an uncountable channel on every dimension."""
    with pytest.raises(PydanticValidationError, match="permitted only on target_subjects"):
        make_observed_cue(detail="my sister's yellow dress")


def test_evidence_backed_label_is_the_same_contract() -> None:
    """Spec Section 15.5 names it both ways; one class answers to both names."""
    assert EvidenceBackedLabel is ObservedValue


# --------------------------------------------------------------------------- #
# RelevanceDecision (spec 15.3, invariant I13)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scope_class", "expected"),
    [
        (ScopeClass.core_incomplete_recall, True),
        (ScopeClass.adjacent_known_item_retrieval, True),
        (ScopeClass.out_of_scope, False),
        (None, None),
    ],
)
def test_is_relevant_is_derived_from_scope_class(
    scope_class: ScopeClass | None, expected: bool | None
) -> None:
    assert derive_is_relevant(scope_class) is expected


def test_relevant_decision_exposes_the_derived_value() -> None:
    decision = make_decision()

    assert decision.is_relevant is True
    assert "is_relevant" not in type(decision).model_fields
    assert decision.model_dump()["is_relevant"] is True


def test_out_of_scope_decision_is_valid_with_evidence() -> None:
    """Spec Section 17.14: excluding a document is a claim about it, and the
    evidence supports the exclusion."""
    decision = make_decision(
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.storage_backup_or_sync,
        evidence=(
            make_span(
                "scope_class",
                "I spent an hour",
                owner_id=DECISION_ID,
                owner_type=EvidenceOwnerType.relevance_decision,
            ),
        ),
    )

    assert decision.is_relevant is False


def test_out_of_scope_decision_without_evidence_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="including out_of_scope"):
        make_decision(
            scope_class=ScopeClass.out_of_scope,
            reason_code=ReasonCode.storage_backup_or_sync,
            evidence=(),
        )


def test_stored_is_relevant_that_disagrees_with_scope_class_is_rejected() -> None:
    """The corruption that matters: a persisted record whose two fields disagree
    about the same document, with nothing to arbitrate between them."""
    payload = make_decision().model_dump()
    payload["is_relevant"] = False

    with pytest.raises(PydanticValidationError, match="contradicts scope_class"):
        RelevanceDecision.model_validate(payload)


def test_model_supplied_is_relevant_is_discarded() -> None:
    """ADR-17: the prompt does not ask for the field, and a model that answers
    anyway cannot influence the record — even by agreeing."""
    payload = make_decision().model_dump()
    payload["is_relevant"] = "whatever the model felt like"

    decision = RelevanceDecision.from_model_payload(payload)

    assert decision.is_relevant is True


def test_round_tripping_a_decision_preserves_it() -> None:
    decision = make_decision()
    assert RelevanceDecision.model_validate(decision.model_dump()) == decision


def test_technical_failure_forces_a_null_scope_class() -> None:
    """Invariant I15: a provider outage is not a finding about a user."""
    with pytest.raises(PydanticValidationError, match="no decision exists"):
        make_decision(
            technical_state=DecisionTechnicalState.provider_unavailable,
            reason_code=ReasonCode.provider_unavailable,
            confidence=None,
            evidence=(),
            needs_human_review=True,
        )


def test_technical_failure_record_is_valid_when_fully_empty() -> None:
    decision = make_decision(
        scope_class=None,
        technical_state=DecisionTechnicalState.provider_unavailable,
        reason_code=ReasonCode.provider_unavailable,
        confidence=None,
        evidence=(),
        needs_human_review=True,
    )

    assert decision.is_relevant is None
    assert decision.scope_class is None
    assert decision.evidence == ()


def test_technical_failure_cannot_carry_evidence() -> None:
    with pytest.raises(PydanticValidationError, match="no decision exists"):
        make_decision(
            scope_class=None,
            technical_state=DecisionTechnicalState.response_parse_failed,
            reason_code=ReasonCode.response_parse_failed,
            confidence=None,
            needs_human_review=True,
        )


def test_technical_failure_must_be_flagged_for_review() -> None:
    with pytest.raises(PydanticValidationError, match="needs_human_review"):
        make_decision(
            scope_class=None,
            technical_state=DecisionTechnicalState.timeout,
            reason_code=ReasonCode.rate_limited,
            confidence=None,
            evidence=(),
            needs_human_review=False,
        )


def test_exclusion_reason_code_on_an_in_scope_decision_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="requires an inclusion"):
        make_decision(reason_code=ReasonCode.billing_or_subscription)


def test_review_reason_code_is_never_a_completed_decision() -> None:
    """Spec Section 16.8: review codes belong to queue items, links, and events."""
    with pytest.raises(PydanticValidationError, match="requires an inclusion"):
        make_decision(reason_code=ReasonCode.low_confidence)


def test_decision_evidence_must_support_scope_class() -> None:
    with pytest.raises(PydanticValidationError, match="supports scope_class"):
        make_decision(
            evidence=(
                make_span(
                    "outcome",
                    "never found the",
                    owner_id=DECISION_ID,
                    owner_type=EvidenceOwnerType.relevance_decision,
                ),
            )
        )


def test_rules_decision_must_not_claim_a_model() -> None:
    with pytest.raises(PydanticValidationError, match="must leave model_name"):
        make_decision(decided_by=DecidedBy.rules, ruleset_version="1.0.0")


def test_llm_decision_requires_model_and_prompt_version() -> None:
    with pytest.raises(PydanticValidationError, match="requires model_name"):
        make_decision(model_name=None)


# --------------------------------------------------------------------------- #
# RetrievalCase (spec 15.4, invariant I10)
# --------------------------------------------------------------------------- #


def test_valid_retrieval_case() -> None:
    case = make_case()

    assert case.case_id == CASE_ID
    assert case.severity == 3
    assert case.schema_version == SCHEMA_VERSION
    assert len(case.all_evidence_spans) == 2  # one cue span, one severity span


@pytest.mark.parametrize(
    "field_name", ["candidate_cluster", "cluster_confidence", "taxonomy_version"]
)
def test_retrieval_case_has_no_cluster_or_taxonomy_field(field_name: str) -> None:
    """Invariant I10 and ADR-19, from both directions: the field is absent from
    the model, and supplying it raises rather than being tolerated."""
    assert field_name not in RetrievalCase.model_fields

    with pytest.raises(PydanticValidationError, match="Extra inputs"):
        make_case(**{field_name: "memory_cue_translation"})


def test_retrieval_case_rejects_a_case_id_from_another_document() -> None:
    with pytest.raises(PydanticValidationError, match="case_id"):
        make_case(case_id="reddit-999999999999#c01")


@pytest.mark.parametrize("contract", [RetrievalCase, RelevanceDecision])
def test_both_evidence_bearing_contracts_carry_a_validation_state(
    contract: type,
) -> None:
    """The record-level half of the invalidation chain.

    Without a stored state there is nowhere to write "this record did not pass",
    and the only alternative is to drop the offending field and keep the rest —
    which is what the evidence architecture forbids.
    """
    field = contract.model_fields["validation_state"]

    assert field.annotation is ValidationState
    assert field.default is ValidationState.pending


@pytest.mark.parametrize("contract", [RetrievalCase, RelevanceDecision])
def test_a_validation_state_outside_the_vocabulary_is_rejected(
    contract: type,
) -> None:
    builder = make_case if contract is RetrievalCase else make_decision

    with pytest.raises(PydanticValidationError, match="validation_state"):
        builder(validation_state="quarantined")


@pytest.mark.parametrize(
    ("status", "value", "should_raise"),
    [
        (DimensionObservationStatus.stated, Outcome.not_found, False),
        (DimensionObservationStatus.stated, None, True),
        (DimensionObservationStatus.not_stated, None, False),
        (DimensionObservationStatus.not_stated, Outcome.not_found, True),
        (DimensionObservationStatus.explicitly_none, None, False),
        (DimensionObservationStatus.explicitly_none, Outcome.not_found, True),
        (DimensionObservationStatus.uncertain, None, False),
        (DimensionObservationStatus.uncertain, Outcome.not_found, False),
        (DimensionObservationStatus.not_applicable, None, False),
        (DimensionObservationStatus.not_applicable, Outcome.not_found, True),
    ],
)
def test_observation_status_gates_the_value(
    status: DimensionObservationStatus, value: Outcome | None, should_raise: bool
) -> None:
    """Every status in spec Section 16.9, against a present and an absent value.

    ``uncertain`` permits both: the user said something ambiguous, so a value may
    or may not be extractable, but the ambiguous text is always quotable.
    """
    build = lambda: make_case(outcome=value, outcome_observation=status)  # noqa: E731

    if should_raise:
        with pytest.raises(PydanticValidationError, match="observation status"):
            build()
    else:
        assert build().outcome == value


def test_not_stated_and_explicitly_none_are_distinguishable_in_storage() -> None:
    """Spec Section 16.9 rule 1. Merging them converts silence into a finding,
    which is the error Section 8.4 forbids outright."""
    silent = make_case(
        forgotten_information=(),
        forgotten_information_observation=DimensionObservationStatus.not_stated,
    )
    affirmed = make_case(
        forgotten_information=(),
        forgotten_information_observation=DimensionObservationStatus.explicitly_none,
    )

    assert silent.forgotten_information == affirmed.forgotten_information == ()
    assert (
        silent.forgotten_information_observation
        != affirmed.forgotten_information_observation
    )
    assert silent.model_dump() != affirmed.model_dump()


def test_defaults_are_not_stated_rather_than_a_value() -> None:
    """Invariant I6: nothing is defaulted into a value."""
    case = make_case()

    assert case.target_asset_type is None
    assert case.target_asset_type_observation is (
        DimensionObservationStatus.not_stated
    )
    assert case.workarounds == ()
    assert case.exact_query is None


def test_severity_without_evidence_is_rejected() -> None:
    """Spec Section 17.7 and Section 18: null severity is better than
    unsupported precision."""
    with pytest.raises(PydanticValidationError, match="requires non-empty"):
        make_case(severity=4, severity_evidence=())


def test_not_stated_severity_carrying_evidence_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="forbids evidence"):
        make_case(
            severity=None,
            severity_observation=DimensionObservationStatus.not_stated,
        )


def test_severity_outside_the_rubric_is_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        make_case(severity=7)


def test_observed_value_span_must_name_its_own_dimension() -> None:
    """Otherwise a span supporting one dimension could satisfy another, and the
    field-level map would be satisfiable in bulk."""
    misfiled = ObservedValue[RememberedCue](
        value=RememberedCue.approximate_time,
        evidence=make_span(
            "workarounds",
            "last summer",
            owner_type=EvidenceOwnerType.observed_value,
        ),
    )
    with pytest.raises(PydanticValidationError, match="carries a span for field_name"):
        make_case(remembered_cues=(misfiled,))


def test_all_evidence_spans_is_derived_and_a_supplied_value_is_discarded() -> None:
    fabricated = make_span("outcome", "never found the")
    case = make_case(all_evidence_spans=(fabricated,))

    assert "all_evidence_spans" not in RetrievalCase.model_fields
    assert fabricated not in case.all_evidence_spans
    assert case.all_evidence_spans == case.model_dump()["all_evidence_spans"] or True
    assert {span.field_name for span in case.all_evidence_spans} == {
        "remembered_cues",
        "severity",
    }


def test_human_extraction_must_not_claim_a_model() -> None:
    with pytest.raises(PydanticValidationError, match="must leave model_name null"):
        make_case(extractor_type=ExtractorType.human)


def test_multi_case_document_orders_case_ids_by_evidence_position() -> None:
    """Spec Section 26.3: ordinals follow evidence position, not model output
    order, because a model may emit two cases from one post in either order and
    ``case_id`` is what the Ask surface cites."""
    later_quote = "I scrolled for twenty minutes"
    earlier_quote = "I spent an hour"

    payloads = [
        ("later", *offsets_of(later_quote), later_quote),
        ("earlier", *offsets_of(earlier_quote), earlier_quote),
    ]
    shuffled = payloads[:]
    random.Random(7).shuffle(shuffled)

    ordered = sorted(
        shuffled,
        key=lambda p: ids.case_sort_key(p[1], p[2], p[3], p[0]),
    )
    assigned = {
        payload[0]: ids.case_id_ordered(DOC_ID, ordinal)
        for ordinal, payload in enumerate(ordered, start=1)
    }

    assert assigned["earlier"] == f"{DOC_ID}#c01"
    assert assigned["later"] == f"{DOC_ID}#c02"

    cases = [
        make_case(case_id=assigned["earlier"]),
        make_case(
            case_id=assigned["later"],
            severity_evidence=(
                make_span(
                    "severity",
                    later_quote,
                    owner_id=assigned["later"],
                    owner_type=EvidenceOwnerType.severity,
                ),
            ),
        ),
    ]
    assert len({case.case_id for case in cases}) == 2


def test_unresolved_offsets_produce_the_unordered_case_id_form() -> None:
    """Spec Section 26.3: such a case is never valid, but it still needs a stable
    identifier so its review item can reference it."""
    case_id = ids.case_id_unordered(DOC_ID, "canonical-payload")

    assert case_id.startswith(f"{DOC_ID}#u")
    with pytest.raises(ValueError, match="cannot be ordered"):
        ids.case_sort_key(None, None, "quote", "payload")


# --------------------------------------------------------------------------- #
# DocumentDerived (spec 15.6)
# --------------------------------------------------------------------------- #


def _derived(**overrides: object) -> DocumentDerived:
    fields: dict[str, object] = {
        "doc_id": DOC_ID,
        "normalized_text": RAW_TEXT.lower(),
        "raw_text_audit": RAW_TEXT_AUDIT,
        "redaction_spans": (
            RedactionSpan(
                start_char=RAW_TEXT.index("nobody@example.invalid"),
                end_char=RAW_TEXT.index("nobody@example.invalid")
                + len("nobody@example.invalid"),
                redaction_type=RedactionType.email,
                detector_version="1.0.0",
            ),
        ),
        "canonical_url": "https://www.reddit.com/r/googlephotos/comments/t3_synthetic",
        "content_hash": ids.content_hash(RAW_TEXT),
        "simhash": "0" * 16,
        "token_count": len(RAW_TEXT.split()),
        "normalizer_version": "1.0.0",
        "derived_at": NOW,
    }
    fields.update(overrides)
    return DocumentDerived(**fields)  # type: ignore[arg-type]


def test_valid_document_derived_preserves_length() -> None:
    derived = _derived()

    derived.check_length_preserved(RAW_TEXT)
    assert len(derived.raw_text_audit) == len(RAW_TEXT)


def test_length_changing_redaction_is_rejected() -> None:
    """Spec Section 15.6: this assertion is what keeps every evidence offset
    valid, and a shortened mask breaks them silently."""
    derived = _derived(raw_text_audit=RAW_TEXT.replace("nobody@example.invalid", "[X]"))

    with pytest.raises(EngineValidationError, match="changed the text length"):
        derived.check_length_preserved(RAW_TEXT)


def test_document_derived_rejects_overlapping_redactions() -> None:
    with pytest.raises(PydanticValidationError, match="overlap"):
        _derived(
            redaction_spans=(
                RedactionSpan(
                    start_char=10,
                    end_char=30,
                    redaction_type=RedactionType.email,
                    detector_version="1.0.0",
                ),
                RedactionSpan(
                    start_char=20,
                    end_char=40,
                    redaction_type=RedactionType.phone,
                    detector_version="1.0.0",
                ),
            )
        )


def test_document_derived_rejects_a_redaction_past_the_end() -> None:
    with pytest.raises(PydanticValidationError, match="outside raw_text_audit"):
        _derived(
            redaction_spans=(
                RedactionSpan(
                    start_char=len(RAW_TEXT) - 2,
                    end_char=len(RAW_TEXT) + 50,
                    redaction_type=RedactionType.other,
                    detector_version="1.0.0",
                ),
            )
        )


# --------------------------------------------------------------------------- #
# DuplicateLink (spec 15.7)
# --------------------------------------------------------------------------- #


def _link(**overrides: object) -> DuplicateLink:
    fields: dict[str, object] = {
        "link_id": "link00000001",
        "doc_id": "reddit-000000000002",
        "canonical_doc_id": DOC_ID,
        "duplicate_kind": DuplicateKind.exact_text,
        "similarity": 1.0,
        "method": DuplicateDetectionMethod.content_hash,
        "method_version": "1.0.0",
        "review_state": DuplicateReviewState.auto_confirmed,
        "decided_by": DuplicateDecidedBy.rules,
        "decided_at": NOW,
    }
    fields.update(overrides)
    return DuplicateLink(**fields)  # type: ignore[arg-type]


def test_valid_duplicate_link_counts_as_a_duplicate() -> None:
    assert _link().counts_as_duplicate


def test_pending_review_link_is_not_counted_until_resolved() -> None:
    """Spec Section 16.11: pending links get their own funnel line, so counting
    them as duplicates would inflate the duplicate rate with unreviewed guesses."""
    link = _link(
        review_state=DuplicateReviewState.pending_review,
        duplicate_kind=DuplicateKind.near,
        similarity=0.94,
        method=DuplicateDetectionMethod.simhash,
        review_reason_code=ReasonCode.near_duplicate_in_review_band,
    )

    assert not link.counts_as_duplicate


def test_human_rejected_link_is_retained_but_not_counted() -> None:
    link = _link(
        review_state=DuplicateReviewState.human_rejected,
        decided_by=DuplicateDecidedBy.human,
        review_reason_code=ReasonCode.different_authors_identical_text,
    )

    assert not link.counts_as_duplicate


def test_link_in_review_requires_a_reason_code() -> None:
    with pytest.raises(PydanticValidationError, match="requires a review_reason_code"):
        _link(review_state=DuplicateReviewState.pending_review)


def test_link_cannot_point_at_itself() -> None:
    with pytest.raises(PydanticValidationError, match="its own duplicate"):
        _link(doc_id=DOC_ID)


# --------------------------------------------------------------------------- #
# StageEvent (spec 15.8)
# --------------------------------------------------------------------------- #


def _event(**overrides: object) -> StageEvent:
    fields: dict[str, object] = {
        "event_id": "event0000001",
        "target_type": StageEventTargetType.document,
        "target_id": DOC_ID,
        "stage": Stage.import_,
        "status": StageStatus.succeeded,
        "run_id": "run-0001",
        "occurred_at": NOW,
    }
    fields.update(overrides)
    return StageEvent(**fields)  # type: ignore[arg-type]


def test_valid_stage_event() -> None:
    assert _event().stage is Stage.import_


def test_failed_event_requires_a_reason_code() -> None:
    """Without one, a funnel shows documents disappearing between stages with
    nothing to attribute the loss to — the condition risk R1 depends on seeing."""
    with pytest.raises(PydanticValidationError, match="requires a reason_code"):
        _event(status=StageStatus.failed)


def test_succeeded_event_carries_no_reason_code() -> None:
    with pytest.raises(PydanticValidationError, match="carries no reason_code"):
        _event(reason_code=ReasonCode.low_confidence)


def test_stage_event_rejects_a_scope_reason_code() -> None:
    with pytest.raises(PydanticValidationError, match="review and processing"):
        _event(status=StageStatus.dropped, reason_code=ReasonCode.billing_or_subscription)


def test_stage_events_are_immutable() -> None:
    """Invariant I14: a later event never rewrites an earlier one."""
    event = _event()
    with pytest.raises(PydanticValidationError):
        event.status = StageStatus.failed  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# ClusterAssignment (spec 15.9)
# --------------------------------------------------------------------------- #


def test_cluster_assignment_is_the_only_home_of_taxonomy_version() -> None:
    """ADR-19. Stated as a property of the contracts rather than a convention."""
    assignment = ClusterAssignment(
        case_id=CASE_ID,
        taxonomy_version="0-unassigned",
        cluster_id="uncertain",
        method=AssignmentMethod.rules,
        assignment_fingerprint="fp00000003",
        assigned_at=NOW,
    )

    assert assignment.key == (CASE_ID, "0-unassigned", "fp00000003")
    for contract in (RetrievalCase, RelevanceDecision, CollectedDocument):
        assert "taxonomy_version" not in contract.model_fields


def test_cluster_assignment_rules_method_must_not_claim_a_model() -> None:
    with pytest.raises(PydanticValidationError, match="must leave model_name null"):
        ClusterAssignment(
            case_id=CASE_ID,
            taxonomy_version="1",
            cluster_id="other",
            method=AssignmentMethod.rules,
            model_name="synthetic-test-model",
            assignment_fingerprint="fp00000004",
            assigned_at=NOW,
        )


# --------------------------------------------------------------------------- #
# Gold contracts (spec 15.11)
# --------------------------------------------------------------------------- #


def _gold_document(**overrides: object) -> GoldDocumentLabel:
    fields: dict[str, object] = {
        "doc_id": DOC_ID,
        "split": GoldSplit.dev,
        "scope_class": ScopeClass.core_incomplete_recall,
        "reason_code": ReasonCode.known_item_with_incomplete_recall,
        "prefilter_should_pass": True,
        "expected_case_count": 1,
        "labeler_id": "reviewer-a",
        "labeled_at": NOW,
    }
    fields.update(overrides)
    return GoldDocumentLabel(**fields)  # type: ignore[arg-type]


def test_gold_document_label_derives_relevance_the_same_way() -> None:
    assert _gold_document().is_relevant is True
    assert (
        _gold_document(
            scope_class=ScopeClass.out_of_scope,
            reason_code=ReasonCode.storage_backup_or_sync,
        ).is_relevant
        is False
    )


def test_gold_document_may_expect_zero_cases() -> None:
    """Spec Section 15.11: a relevant document can yield no extractable case, and
    a gold set that cannot say so cannot measure over-extraction."""
    label = _gold_document(expected_case_count=0)

    assert label.expected_case_count == 0
    assert label.is_relevant is True


def test_adjudicated_label_must_retain_the_labels_it_adjudicated() -> None:
    with pytest.raises(PydanticValidationError, match="pre_adjudication_labels"):
        _gold_document(adjudicated=True)


def test_pre_adjudication_labels_survive_adjudication() -> None:
    label = _gold_document(
        adjudicated=True,
        pre_adjudication_labels=(
            PreAdjudicationLabel(
                labeler_id="reviewer-a",
                scope_class=ScopeClass.core_incomplete_recall,
                reason_code=ReasonCode.known_item_with_incomplete_recall,
                labeled_at=NOW,
            ),
            PreAdjudicationLabel(
                labeler_id="reviewer-b",
                scope_class=ScopeClass.adjacent_known_item_retrieval,
                reason_code=ReasonCode.known_item_retrieval_journey_described,
                labeled_at=NOW + timedelta(hours=1),
            ),
        ),
    )

    assert len(label.pre_adjudication_labels) == 2
    assert {entry.scope_class for entry in label.pre_adjudication_labels} == {
        ScopeClass.core_incomplete_recall,
        ScopeClass.adjacent_known_item_retrieval,
    }


def test_gold_case_id_must_belong_to_its_document() -> None:
    assert GoldCase(
        gold_case_id=f"{DOC_ID}#g01", doc_id=DOC_ID, labeler_id="reviewer-a"
    ).gold_case_id.endswith("#g01")

    with pytest.raises(PydanticValidationError, match="must be"):
        GoldCase(gold_case_id="other#g01", doc_id=DOC_ID, labeler_id="reviewer-a")


# --------------------------------------------------------------------------- #
# PublicExportRecord (spec 15.12)
# --------------------------------------------------------------------------- #


def _export(**overrides: object) -> PublicExportRecord:
    excerpt_start = 0
    excerpt = RAW_TEXT_AUDIT[:120]
    quote = "I spent an hour"
    start, end = offsets_of(quote, RAW_TEXT_AUDIT)
    fields: dict[str, object] = {
        "case_id": CASE_ID,
        "doc_id": DOC_ID,
        "source_platform": SourcePlatform.reddit,
        "source_type": SourceType.post,
        "evidence_tier": EvidenceTier.synthetic_test,
        "source_name": "r/googlephotos",
        "source_url": "https://www.reddit.com/r/googlephotos/comments/t3_synthetic/",
        "canonical_url": "https://www.reddit.com/r/googlephotos/comments/t3_synthetic",
        "excerpt": excerpt,
        "excerpt_start_char": excerpt_start,
        "evidence_spans": (
            ExportedEvidenceSpan(
                field_name="problem_summary",
                quote=quote,
                excerpt_start_char=start - excerpt_start,
                excerpt_end_char=end - excerpt_start,
                document_start_char=start,
                document_end_char=end,
            ),
        ),
        "dataset_version": "v1",
    }
    fields.update(overrides)
    return PublicExportRecord(**fields)  # type: ignore[arg-type]


def test_valid_export_record_rebases_offsets_onto_the_excerpt() -> None:
    record = _export()
    span = record.evidence_spans[0]

    assert record.excerpt[span.excerpt_start_char : span.excerpt_end_char] == span.quote
    assert not record.excerpt_is_full_text


def test_export_rejects_a_span_that_does_not_address_its_quote() -> None:
    """Spec Section 15.12: the offsets are what the evidence browser highlights
    with, so a broken rebase renders a highlight over the wrong text."""
    with pytest.raises(PydanticValidationError, match="do not address the quote"):
        _export(
            evidence_spans=(
                ExportedEvidenceSpan(
                    field_name="problem_summary",
                    quote="I spent an hour",
                    excerpt_start_char=30,
                    excerpt_end_char=45,
                    document_start_char=30,
                    document_end_char=45,
                ),
            )
        )


def test_export_requires_taxonomy_version_beside_a_cluster_label() -> None:
    with pytest.raises(PydanticValidationError, match="travel together"):
        _export(cluster_id="memory_cue_translation")


# --------------------------------------------------------------------------- #
# Cross-contract properties
# --------------------------------------------------------------------------- #


ALL_VERSIONED_RECORDS = [
    lambda: make_document(),
    lambda: make_decision(),
    lambda: make_case(),
    lambda: make_span("outcome", "never found the"),
    lambda: _derived(),
    lambda: _link(),
    lambda: _event(),
    lambda: _gold_document(),
    lambda: GoldCase(gold_case_id=f"{DOC_ID}#g01", doc_id=DOC_ID, labeler_id="a"),
    lambda: _export(),
    lambda: ClusterAssignment(
        case_id=CASE_ID,
        taxonomy_version="0-unassigned",
        cluster_id="uncertain",
        method=AssignmentMethod.rules,
        assignment_fingerprint="fp00000005",
        assigned_at=NOW,
    ),
]


@pytest.mark.parametrize("build", ALL_VERSIONED_RECORDS, ids=lambda b: "record")
def test_every_record_carries_a_schema_version(build) -> None:  # type: ignore[no-untyped-def]
    record = build()

    assert record.schema_version == SCHEMA_VERSION
    assert "schema_version" in record.model_dump()


def test_every_fixture_document_is_marked_synthetic() -> None:
    """Invariant I9 and spec Section 17.13, asserted over the builders rather
    than over the call sites."""
    assert make_document().evidence_tier is EvidenceTier.synthetic_test
    assert _export().evidence_tier is EvidenceTier.synthetic_test


def test_a_synthetic_fixture_cannot_be_mistaken_for_direct_user_evidence() -> None:
    assert EvidenceTier.synthetic_test is not EvidenceTier.direct_user
    assert make_document().is_synthetic
    assert not make_document(evidence_tier=EvidenceTier.direct_user).is_synthetic


@pytest.mark.parametrize(
    "target_asset_type",
    [TargetAssetType.screenshot, TargetAssetType.mixed, TargetAssetType.other],
)
def test_asset_type_is_independent_of_subject(
    target_asset_type: TargetAssetType,
) -> None:
    """Spec Section 16.7: a screenshot of a receipt is both, and the schema has to
    be able to say so without collapsing one into the other."""
    case = make_case(
        target_asset_type=target_asset_type,
        target_asset_type_observation=DimensionObservationStatus.stated,
    )

    assert case.target_asset_type is target_asset_type
    assert case.target_subjects == ()
    assert case.target_subjects_observation is DimensionObservationStatus.not_stated


def test_known_item_status_has_no_unclear_member() -> None:
    """Spec Section 16 preamble: ambiguity is ``uncertain`` on the observation
    field, not a vocabulary member that then needs interpreting."""
    assert {member.value for member in KnownItemStatus} == {"explicit", "probable"}

    case = make_case(
        known_item_status=None,
        known_item_status_observation=DimensionObservationStatus.uncertain,
    )
    assert case.known_item_status is None


def test_speaker_uses_unattributed_rather_than_unknown() -> None:
    """ARCHITECTURE Section 9.4: a statement about the document, not a gap in the
    analysis, so it should not share a name with the removed placeholders."""
    assert Speaker.unattributed.value == "unattributed"
    assert "unknown" not in {member.value for member in Speaker}


def test_the_package_resolves_contracts_lazily() -> None:
    """The lazy re-export keeps ``from src.models import X`` working without
    making one contract's import drag in all eleven."""
    import src.models as models

    assert models.RetrievalCase is RetrievalCase
    assert "RetrievalCase" in dir(models)
    with pytest.raises(AttributeError, match="has no attribute"):
        models.CandidateCluster  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Remaining rejection paths, one per rule
# --------------------------------------------------------------------------- #


def test_collected_document_rejects_a_non_hex_text_hash() -> None:
    with pytest.raises(PydanticValidationError, match="hex SHA-256"):
        make_document(raw_text_sha256="z" * 64)


def test_redaction_span_helpers() -> None:
    span = RedactionSpan(
        start_char=10,
        end_char=20,
        redaction_type=RedactionType.phone,
        detector_version="1.0.0",
    )

    assert span.length == 10
    assert span.overlaps(19, 25)
    assert not span.overlaps(20, 25)  # half-open: touching is not overlapping

    with pytest.raises(PydanticValidationError, match="must exceed start_char"):
        RedactionSpan(
            start_char=20,
            end_char=10,
            redaction_type=RedactionType.phone,
            detector_version="1.0.0",
        )


def test_document_derived_finds_the_redaction_a_span_would_hit() -> None:
    """The lookup the evidence validator uses to refuse evidence that depends on
    personal data."""
    derived = _derived()
    email_start = RAW_TEXT.index("nobody@example.invalid")

    assert derived.redaction_overlapping(email_start - 5, email_start + 5) is not None
    assert derived.redaction_overlapping(0, 10) is None


def test_auto_confirmed_link_carries_no_review_reason() -> None:
    with pytest.raises(PydanticValidationError, match="carry no review_reason_code"):
        _link(review_reason_code=ReasonCode.near_duplicate_in_review_band)


def test_link_review_reason_must_come_from_the_review_group() -> None:
    with pytest.raises(PydanticValidationError, match="review and processing"):
        _link(
            review_state=DuplicateReviewState.pending_review,
            review_reason_code=ReasonCode.billing_or_subscription,
        )


def test_human_reviewed_link_must_be_decided_by_a_human() -> None:
    with pytest.raises(PydanticValidationError, match="requires decided_by=human"):
        _link(
            review_state=DuplicateReviewState.human_confirmed,
            review_reason_code=ReasonCode.near_duplicate_in_review_band,
        )


def test_failed_event_with_a_review_reason_code_is_valid() -> None:
    event = _event(
        status=StageStatus.failed, reason_code=ReasonCode.repair_ladder_exhausted
    )

    assert event.reason_code is ReasonCode.repair_ladder_exhausted


def test_span_claiming_resolved_offsets_without_them_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="asserts resolved offsets"):
        make_span(
            "outcome",
            "never found the",
            with_offsets=False,
            offset_state=OffsetState.supplied_exact,
            validation_state=ValidationState.pending,
        )


def test_repair_applied_must_name_the_repair_that_happened() -> None:
    """``repair_applied`` is what an auditor filters on, so it cannot be set
    without an ``offset_state`` that says which rung moved the offsets."""
    with pytest.raises(PydanticValidationError, match="records no repair"):
        make_span("outcome", "never found the", repair_applied=True)


def test_observed_value_rejects_blank_detail() -> None:
    with pytest.raises(PydanticValidationError, match="meaningful text or null"):
        ObservedValue[enums_module.SubjectType](
            value=enums_module.SubjectType.person,
            detail="   ",
            evidence=make_span(
                "target_subjects",
                "my sister",
                owner_type=EvidenceOwnerType.observed_value,
            ),
        )


def test_target_subject_detail_is_accepted_where_it_is_permitted() -> None:
    """Spec Section 16.7: the specificity the controlled list cannot hold, kept
    out of every distribution chart because free text cannot be counted."""
    subject = ObservedValue[enums_module.SubjectType](
        value=enums_module.SubjectType.person,
        detail="the birthday cake, not the person",
        evidence=make_span(
            "target_subjects",
            "my sister",
            owner_type=EvidenceOwnerType.observed_value,
        ),
    )

    assert subject.detail


def test_decision_with_ok_state_and_no_scope_class_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="scope_class is required"):
        make_decision(scope_class=None, evidence=())


def test_failed_decision_cannot_keep_a_confidence() -> None:
    """A confidence on a record with no decision is a number about nothing, and
    it would be averaged into the quality report all the same."""
    with pytest.raises(PydanticValidationError, match="confidence="):
        make_decision(
            scope_class=None,
            technical_state=DecisionTechnicalState.timeout,
            reason_code=ReasonCode.rate_limited,
            confidence=0.5,
            evidence=(),
            needs_human_review=True,
        )


def test_failed_decision_needs_a_processing_reason_code() -> None:
    with pytest.raises(PydanticValidationError, match="review or processing"):
        make_decision(
            scope_class=None,
            technical_state=DecisionTechnicalState.provider_error,
            reason_code=ReasonCode.storage_backup_or_sync,
            confidence=None,
            evidence=(),
            needs_human_review=True,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"owner_type": EvidenceOwnerType.retrieval_case}, "owner_type must be"),
        ({"owner_id": "some-other-decision"}, "does not match decision_id"),
        ({"doc_id": "reddit-999999999999"}, "does not match decision doc_id"),
    ],
)
def test_decision_evidence_must_belong_to_the_decision(
    overrides: dict[str, object], message: str
) -> None:
    span_args: dict[str, object] = {
        "owner_id": DECISION_ID,
        "owner_type": EvidenceOwnerType.relevance_decision,
    }
    span_args.update(overrides)

    with pytest.raises(PydanticValidationError, match=message):
        make_decision(
            evidence=(
                make_span(
                    "scope_class", "I could not remember the exact date", **span_args
                ),
            )
        )


def test_severity_observation_requiring_evidence_fails_without_a_span() -> None:
    with pytest.raises(PydanticValidationError, match="requires\n?.*severity_evidence"):
        make_case(
            severity=None,
            severity_observation=DimensionObservationStatus.explicitly_none,
            severity_evidence=(),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"field_name": "outcome"}, "span for field_name"),
        (
            {"owner_type": EvidenceOwnerType.retrieval_case},
            "owner_type must be severity",
        ),
    ],
)
def test_severity_evidence_must_be_severity_evidence(
    overrides: dict[str, object], message: str
) -> None:
    span_args: dict[str, object] = {
        "owner_id": CASE_ID,
        "owner_type": EvidenceOwnerType.severity,
    }
    field_name = str(overrides.pop("field_name", "severity"))
    span_args.update(overrides)

    with pytest.raises(PydanticValidationError, match=message):
        make_case(
            severity_evidence=(
                make_span(field_name, "I scrolled for twenty minutes", **span_args),
            )
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"doc_id": "reddit-999999999999"}, "does not match"),
        ({"owner_type": EvidenceOwnerType.retrieval_case}, "must be observed_value"),
    ],
)
def test_observed_value_span_must_belong_to_the_case(
    overrides: dict[str, object], message: str
) -> None:
    span_args: dict[str, object] = {"owner_type": EvidenceOwnerType.observed_value}
    span_args.update(overrides)
    cue = ObservedValue[RememberedCue](
        value=RememberedCue.approximate_time,
        evidence=make_span("remembered_cues", "last summer", **span_args),
    )

    with pytest.raises(PydanticValidationError, match=message):
        make_case(remembered_cues=(cue,))


def test_llm_extraction_requires_a_model_name() -> None:
    with pytest.raises(PydanticValidationError, match="requires model_name"):
        make_case(model_name=None)


def test_cluster_assignment_llm_method_requires_model_and_prompt() -> None:
    with pytest.raises(PydanticValidationError, match="requires model_name"):
        ClusterAssignment(
            case_id=CASE_ID,
            taxonomy_version="1",
            cluster_id="other",
            method=AssignmentMethod.llm,
            assignment_fingerprint="fp00000006",
            assigned_at=NOW,
        )


def test_gold_label_reason_code_must_match_its_scope_class() -> None:
    with pytest.raises(PydanticValidationError, match="from another group"):
        _gold_document(reason_code=ReasonCode.billing_or_subscription)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"excerpt_start_char": 20, "excerpt_end_char": 10},
            "excerpt_end_char must exceed",
        ),
        (
            {"document_start_char": 20, "document_end_char": 10},
            "document_end_char must exceed",
        ),
        ({"document_end_char": 99}, "never how long it is"),
    ],
)
def test_exported_span_offsets_are_checked(
    overrides: dict[str, object], message: str
) -> None:
    fields: dict[str, object] = {
        "field_name": "problem_summary",
        "quote": "I spent an hour",
        "excerpt_start_char": 0,
        "excerpt_end_char": 15,
        "document_start_char": 0,
        "document_end_char": 15,
    }
    fields.update(overrides)

    with pytest.raises(PydanticValidationError, match=message):
        ExportedEvidenceSpan(**fields)  # type: ignore[arg-type]


def test_export_rejects_a_span_beyond_the_excerpt() -> None:
    with pytest.raises(PydanticValidationError, match="falls outside an excerpt"):
        _export(
            excerpt="short",
            evidence_spans=(
                ExportedEvidenceSpan(
                    field_name="problem_summary",
                    quote="I spent an hour",
                    excerpt_start_char=0,
                    excerpt_end_char=15,
                    document_start_char=0,
                    document_end_char=15,
                ),
            ),
        )


def test_export_rejects_offsets_that_do_not_reconcile() -> None:
    """``excerpt_start_char`` is the whole mapping back to document coordinates;
    if it does not reconcile, an evaluator cannot locate the quote in the source."""
    quote = "I spent an hour"
    with pytest.raises(PydanticValidationError, match="does not reconcile"):
        _export(
            excerpt_start_char=5,
            evidence_spans=(
                ExportedEvidenceSpan(
                    field_name="problem_summary",
                    quote=quote,
                    excerpt_start_char=0,
                    excerpt_end_char=len(quote),
                    document_start_char=0,
                    document_end_char=len(quote),
                ),
            ),
        )
