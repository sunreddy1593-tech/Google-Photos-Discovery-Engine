"""Synthetic fixtures for the Phase 1 contract tests.

Every document built here carries ``evidence_tier = synthetic_test`` (spec Section
17.13, invariant I9). ``tests/test_models.py`` asserts that property over the
builders themselves rather than trusting the call sites, because the exclusion
rule is enforced by the tier on the data, not by which directory a file lives in.

The text below is invented for testing and describes nobody. It is written to
exercise the awkward cases on purpose: a phrase that occurs twice (``"the photo"``),
a phrase reflowed across a line break, and an email address that a Phase 3
redaction would mask.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.collected_document import CollectedDocument
from src.models.enums import (
    CollectionMethod,
    DecidedBy,
    DimensionObservationStatus,
    EvidenceOwnerType,
    EvidenceTier,
    ExtractorType,
    KnownItemStatus,
    OffsetState,
    Outcome,
    ReasonCode,
    RememberedCue,
    ScopeClass,
    SourcePlatform,
    SourceType,
    Speaker,
    ValidationState,
)
from src.models.evidence import EvidenceSpan, ObservedValue
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import RetrievalCase

DOC_ID = "reddit-000000000001"
CASE_ID = f"{DOC_ID}#c01"
DECISION_ID = "decision-0001"

#: One synthetic document's raw text, and the only coordinate space its spans
#: address. ``"the photo"`` deliberately occurs twice, so the ambiguous-tie rung
#: of the ladder has something real to trip over.
RAW_TEXT = (
    "I spent an hour looking for the photo of my sister's birthday cake from "
    "last summer. I could not remember the exact date, so I searched for cake "
    "and got nothing useful. I scrolled for twenty minutes and never found the "
    "photo. Reach me at nobody@example.invalid if you know a trick."
)

#: The same text with the email masked to an identical number of characters, as
#: Phase 3's length-preserving redaction will produce it (ARCHITECTURE 9.2).
EMAIL = "nobody@example.invalid"
EMAIL_START = RAW_TEXT.index(EMAIL)
EMAIL_END = EMAIL_START + len(EMAIL)
RAW_TEXT_AUDIT = RAW_TEXT[:EMAIL_START] + "#" * len(EMAIL) + RAW_TEXT[EMAIL_END:]
REDACTIONS: tuple[tuple[int, int], ...] = ((EMAIL_START, EMAIL_END),)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def offsets_of(quote: str, text: str = RAW_TEXT) -> tuple[int, int]:
    """First occurrence of ``quote``, as a half-open offset pair."""
    start = text.index(quote)
    return start, start + len(quote)


def make_document(**overrides: object) -> CollectedDocument:
    """A valid `CollectedDocument`, always tiered ``synthetic_test``."""
    from src.core.ids import raw_text_sha256

    fields: dict[str, object] = {
        "doc_id": DOC_ID,
        "ingest_batch_id": "batch-0001",
        "source_platform": SourcePlatform.reddit,
        "source_type": SourceType.post,
        "evidence_tier": EvidenceTier.synthetic_test,
        "source_item_id": "t3_synthetic",
        "source_url": "https://www.reddit.com/r/googlephotos/comments/t3_synthetic/",
        "source_url_key": (
            "https://www.reddit.com/r/googlephotos/comments/t3_synthetic"
        ),
        "source_name": "r/googlephotos",
        "title": "Cannot find a photo I know I took",
        "author_hash": "0f1e2d3c4b5a6978",
        "author_salt_id": "saltid000001",
        "published_at": NOW,
        "collected_at": NOW,
        "language_reported": "en",
        "raw_text": RAW_TEXT,
        "raw_text_sha256": raw_text_sha256(RAW_TEXT),
        "collection_query": "cannot find photo",
        "collection_method": CollectionMethod.manual_csv,
    }
    fields.update(overrides)
    return CollectedDocument(**fields)  # type: ignore[arg-type]


def make_span(
    field_name: str,
    quote: str,
    *,
    owner_id: str = CASE_ID,
    owner_type: EvidenceOwnerType = EvidenceOwnerType.retrieval_case,
    text: str = RAW_TEXT,
    validated: bool = True,
    with_offsets: bool = True,
    **overrides: object,
) -> EvidenceSpan:
    """A span over ``text``, valid by default so gate tests start from a pass.

    Offsets are looked up from ``text`` unless the caller supplies them or asks
    for an unresolved span, which is the shape a model response arrives in. The
    ``offset_state`` follows from whether offsets ended up present, so a caller
    never has to keep the two in sync by hand.
    """
    resolved = with_offsets and "start_char" not in overrides
    start, end = offsets_of(quote, text) if resolved else (None, None)
    fields: dict[str, object] = {
        "doc_id": DOC_ID,
        "owner_type": owner_type,
        "owner_id": owner_id,
        "field_name": field_name,
        "quote": quote,
        "start_char": start,
        "end_char": end,
        "speaker": Speaker.author,
        "offset_state": (
            OffsetState.supplied_exact if resolved else OffsetState.missing_unresolved
        ),
        "validation_state": (
            ValidationState.valid if validated else ValidationState.pending
        ),
    }
    fields.update(overrides)
    if fields.get("start_char") is not None and fields["offset_state"] is (
        OffsetState.missing_unresolved
    ):
        fields["offset_state"] = OffsetState.supplied_exact
    return EvidenceSpan(**fields)  # type: ignore[arg-type]


def make_observed_cue(
    value: RememberedCue = RememberedCue.approximate_time,
    quote: str = "last summer",
    **overrides: object,
) -> ObservedValue[RememberedCue]:
    """One evidence-backed ``remembered_cues`` entry."""
    fields: dict[str, object] = {
        "value": value,
        "evidence": make_span(
            "remembered_cues",
            quote,
            owner_type=EvidenceOwnerType.observed_value,
        ),
    }
    fields.update(overrides)
    return ObservedValue[RememberedCue](**fields)  # type: ignore[arg-type]


def make_case(**overrides: object) -> RetrievalCase:
    """A valid `RetrievalCase`: a few fields stated, the rest honestly silent.

    This shape is the realistic one. Most dimensions of most posts are
    ``not_stated``, and a fixture where everything is populated would test a
    record the corpus will rarely contain while hiding the null paths entirely.
    """
    case_id = str(overrides.get("case_id", CASE_ID))
    fields: dict[str, object] = {
        "case_id": case_id,
        "doc_id": DOC_ID,
        "scope_class": ScopeClass.core_incomplete_recall,
        "known_item_status": KnownItemStatus.explicit,
        "known_item_status_observation": DimensionObservationStatus.stated,
        "remembered_cues": (make_observed_cue(),),
        "remembered_cues_observation": DimensionObservationStatus.stated,
        "outcome": Outcome.not_found,
        "outcome_observation": DimensionObservationStatus.stated,
        "severity": 3,
        "severity_observation": DimensionObservationStatus.stated,
        "severity_evidence": (
            make_span(
                "severity",
                "I scrolled for twenty minutes",
                owner_id=case_id,
                owner_type=EvidenceOwnerType.severity,
            ),
        ),
        "problem_summary": (
            "User cannot retrieve a known photo and abandons the attempt after "
            "prolonged scrolling."
        ),
        "extractor_type": ExtractorType.llm,
        "model_name": "synthetic-test-model",
        "prompt_version": "extract/v1",
        "extraction_fingerprint": "fp00000001",
        "extracted_at": NOW,
    }
    fields.update(overrides)
    return RetrievalCase(**fields)  # type: ignore[arg-type]


def case_scalar_spans(case_id: str = CASE_ID) -> tuple[EvidenceSpan, ...]:
    """Store-side spans for the scalar fields :func:`make_case` states.

    Scalar fields keep their spans in the ``evidence_spans`` table rather than on
    the case, so these are what the Phase 5 store would hand
    :func:`~src.extract.validator.validate_record`.
    """
    return (
        make_span(
            "known_item_status",
            "looking for the photo of my sister's birthday cake",
            owner_id=case_id,
        ),
        make_span("outcome", "never found the", owner_id=case_id),
        make_span(
            "problem_summary",
            "I spent an hour looking for the photo",
            owner_id=case_id,
        ),
    )


def make_decision(**overrides: object) -> RelevanceDecision:
    """A valid in-scope `RelevanceDecision` with evidence."""
    decision_id = str(overrides.get("decision_id", DECISION_ID))
    fields: dict[str, object] = {
        "decision_id": decision_id,
        "doc_id": DOC_ID,
        "scope_class": ScopeClass.core_incomplete_recall,
        "reason_code": ReasonCode.known_item_with_incomplete_recall,
        "reason_summary": (
            "User describes a specific remembered photo and an unsuccessful "
            "search for it."
        ),
        "confidence": 0.82,
        "evidence": (
            make_span(
                "scope_class",
                "I could not remember the exact date",
                owner_id=decision_id,
                owner_type=EvidenceOwnerType.relevance_decision,
            ),
        ),
        "decided_by": DecidedBy.llm,
        "model_name": "synthetic-test-model",
        "prompt_version": "relevance/v1",
        "ruleset_version": "1.0.0",
        "decision_fingerprint": "fp00000002",
        "decided_at": NOW,
    }
    fields.update(overrides)
    return RelevanceDecision(**fields)  # type: ignore[arg-type]
