"""The evidence-required field map, the closed exception list, and the status gate.

Spec Section 15.10 makes evidence enforcement a table rather than a habit, and
ARCHITECTURE Section 9.5 makes that table *data* — loaded once and consulted by
the validator — rather than a set of checks scattered through the extractor. The
difference matters when a field is added: a scattered check is simply absent for
the new field and nobody notices, whereas an unclassified field fails
``tests/test_evidence_map.py`` until somebody decides which list it belongs to.

This module imports no contract. The classification is literal data, so the
models can import it (``EvidenceSpan.field_name`` is constrained by it) without a
cycle, and the completeness test walks the Pydantic field sets in the opposite
direction to prove the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.models.enums import DimensionObservationStatus

RELEVANCE_DECISION: Final[str] = "RelevanceDecision"
RETRIEVAL_CASE: Final[str] = "RetrievalCase"


# --------------------------------------------------------------------------- #
# Evidence-required fields (spec 15.10)
# --------------------------------------------------------------------------- #

#: Substantive claims about a user. Each needs at least one valid field-level
#: ``EvidenceSpan`` whose ``field_name`` matches the key, unless the paired
#: observation status in :data:`STATUS_GATE` permits its absence.
#:
#: ``query_paraphrase`` is here deliberately. A paraphrase is still a claim that
#: the user described a search, so it needs a span showing the described search.
#: What makes it a paraphrase rather than a quote is how it is *displayed*, not
#: whether it is evidenced (spec Section 15.10).
EVIDENCE_REQUIRED: Final[dict[str, frozenset[str]]] = {
    RELEVANCE_DECISION: frozenset({"scope_class"}),
    RETRIEVAL_CASE: frozenset(
        {
            "known_item_status",
            "target_asset_type",
            "target_subjects",
            "retrieval_trigger",
            "remembered_cues",
            "forgotten_information",
            "exact_query",
            "query_paraphrase",
            "query_strategies",
            "reformulation_count",
            "system_responses",
            "workarounds",
            "outcome",
            "impact_signals",
            "severity",
            "problem_summary",
        }
    ),
}

#: Every ``field_name`` an ``EvidenceSpan`` may legally carry, across contracts.
#: A span naming anything else is attached to no field and fails validation
#: (spec Section 15.10 consequence 2).
ALL_EVIDENCE_FIELD_NAMES: Final[frozenset[str]] = frozenset().union(
    *EVIDENCE_REQUIRED.values()
)

#: Where a required field's spans are physically stored. Most scalar fields keep
#: their spans in the ``evidence_spans`` store, keyed by ``owner_id`` and
#: ``field_name``; these three carry them inline on the record itself.
INLINE_EVIDENCE_FIELDS: Final[dict[str, str]] = {
    "severity": "severity_evidence",
    "scope_class": "evidence",
}


# --------------------------------------------------------------------------- #
# Evidence-exempt fields (spec 15.10, closed list)
# --------------------------------------------------------------------------- #

#: Identifiers, provenance, versions, and uncertainty metadata — never a
#: substantive claim about a user.
#:
#: Four categories below are **additions to the spec's closed list**, each named
#: separately so the addition is visible rather than folded into a spec category.
#: Spec Section 15.10's five categories do not mention ``reason_summary``,
#: ``evidence``, ``severity_evidence``, or ``RetrievalCase.scope_class``, yet the
#: same section requires every field of both contracts to appear in exactly one
#: list. The rationale for each is in :data:`EXEMPT_ADDITIONS_RATIONALE`.
EVIDENCE_EXEMPT: Final[dict[str, frozenset[str]]] = {
    "identifiers": frozenset(
        {
            "case_id",
            "doc_id",
            "decision_id",
            "link_id",
            "event_id",
            "evidence_id",
            "ingest_batch_id",
            "run_id",
            "cluster_id",
        }
    ),
    "provenance": frozenset(
        {
            "extractor_type",
            "decided_by",
            "method",
            "model_name",
            "extracted_at",
            "decided_at",
            "assigned_at",
            "derived_at",
            "occurred_at",
            "collected_at",
            "collection_method",
            "collection_query",
            "source_platform",
            "source_type",
            "source_item_id",
            "source_name",
            "source_url",
            "source_url_key",
            "author_hash",
            "author_salt_id",
        }
    ),
    "versions": frozenset(
        {
            "schema_version",
            "prompt_version",
            "ruleset_version",
            "normalizer_version",
            "taxonomy_version",
            "method_version",
            "language_detector_version",
            "extraction_fingerprint",
            "decision_fingerprint",
            "assignment_fingerprint",
        }
    ),
    "uncertainty_metadata": frozenset(
        {
            "known_item_status_observation",
            "target_asset_type_observation",
            "target_subjects_observation",
            "retrieval_trigger_observation",
            "remembered_cues_observation",
            "forgotten_information_observation",
            "exact_query_observation",
            "query_paraphrase_observation",
            "query_strategies_observation",
            "reformulation_count_observation",
            "system_responses_observation",
            "workarounds_observation",
            "outcome_observation",
            "impact_signals_observation",
            "severity_observation",
            "confidence",
            "needs_human_review",
            "uncertainty_notes",
            "technical_state",
            "validation_state",
            "offset_state",
            "review_state",
            "reason_code",
            "review_reason_code",
        }
    ),
    "derived": frozenset({"is_relevant", "all_evidence_spans"}),
    # -- additions, see EXEMPT_ADDITIONS_RATIONALE ---------------------------- #
    "evidence_containers": frozenset({"evidence", "severity_evidence"}),
    "inherited_validated": frozenset({"scope_class"}),
    "decision_narrative": frozenset({"reason_summary"}),
}

#: Why each field outside spec Section 15.10's five categories is exempt. Kept as
#: data so the report can print it and a reviewer can disagree with a specific
#: line rather than with a silence.
EXEMPT_ADDITIONS_RATIONALE: Final[dict[str, str]] = {
    "evidence": (
        "The span container for RelevanceDecision.scope_class. Requiring evidence "
        "for the evidence field is circular; the claim it supports is scope_class, "
        "which is evidence-required."
    ),
    "severity_evidence": (
        "The span container for RetrievalCase.severity, which is evidence-required "
        "and whose spans this field holds (spec Section 15.10)."
    ),
    "scope_class": (
        "On RetrievalCase this is the inherited, already-validated decision from "
        "RelevanceDecision, where scope_class is evidence-required. Requiring a "
        "second span for the same claim would duplicate evidence rather than add "
        "any. On RelevanceDecision the field is evidence-required, which is why "
        "the contract-scoped required map takes precedence over this entry. The "
        "exemption holds only while the inheritance is real, which is why "
        "src.extract.validator checks all three conditions in "
        "SCOPE_INHERITANCE_CONDITIONS whenever the decision is available."
    ),
    "reason_summary": (
        "A paraphrase of why the scope decision was made (spec Section 17.19). The "
        "substantive claim it narrates is scope_class, whose span is the proof; the "
        "summary is never displayed in quotation marks and never counted. It can "
        "never stand in for evidence: RelevanceDecision requires a non-empty "
        "evidence tuple for every ok decision, and the record gate requires at "
        "least one of those spans to be valid."
    ),
}

#: The conditions under which ``RetrievalCase.scope_class`` may be exempt from
#: field-level evidence, kept as data beside the exemption it qualifies so the
#: two cannot drift apart. Enforced by
#: :func:`src.extract.validator._check_scope_inheritance`.
SCOPE_INHERITANCE_CONDITIONS: Final[tuple[str, ...]] = (
    "the case and the decision concern the same doc_id",
    "the case's scope_class equals the decision's scope_class",
    "the decision's validation_state is valid",
)

#: Fields that hold spans rather than making a claim, and so are exempt from
#: evidence requirements without any qualifying condition. Requiring evidence for
#: an evidence container is a recursive demand that no record could satisfy: the
#: span supporting ``severity_evidence`` would itself need a span.
EVIDENCE_CONTAINER_FIELDS: Final[frozenset[str]] = frozenset(
    {"evidence", "severity_evidence"}
)

#: Flat view of every exempt field name, for the completeness test.
ALL_EXEMPT_FIELD_NAMES: Final[frozenset[str]] = frozenset().union(
    *EVIDENCE_EXEMPT.values()
)


# --------------------------------------------------------------------------- #
# Status gate (spec 15.10, 16.9)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class StatusRule:
    """What one observation status permits for its field's value and evidence.

    ``value_required`` and ``value_must_be_empty`` are both false for
    ``uncertain``: the user said something ambiguous, so a value may or may not
    be extractable, but the ambiguous text itself is always quotable and the
    span is therefore required.
    """

    value_required: bool
    value_must_be_empty: bool
    evidence_required: bool
    evidence_must_be_empty: bool
    meaning: str


#: Spec Section 15.10's status-gate table, as data. A mismatch is a validation
#: error routed to review, never a coercion (spec Section 17.17).
STATUS_GATE: Final[dict[DimensionObservationStatus, StatusRule]] = {
    DimensionObservationStatus.stated: StatusRule(
        value_required=True,
        value_must_be_empty=False,
        evidence_required=True,
        evidence_must_be_empty=False,
        meaning="The user said it.",
    ),
    DimensionObservationStatus.explicitly_none: StatusRule(
        value_required=False,
        value_must_be_empty=True,
        evidence_required=True,
        evidence_must_be_empty=False,
        meaning=(
            "The user affirmatively said there was none. A finding in its own "
            "right, so it needs proof."
        ),
    ),
    DimensionObservationStatus.uncertain: StatusRule(
        value_required=False,
        value_must_be_empty=False,
        evidence_required=True,
        evidence_must_be_empty=False,
        meaning="The user said something ambiguous. The span is the ambiguous text.",
    ),
    DimensionObservationStatus.not_stated: StatusRule(
        value_required=False,
        value_must_be_empty=True,
        evidence_required=False,
        evidence_must_be_empty=True,
        meaning="The source is silent. The default, and never an inference.",
    ),
    DimensionObservationStatus.not_applicable: StatusRule(
        value_required=False,
        value_must_be_empty=True,
        evidence_required=False,
        evidence_must_be_empty=True,
        meaning="The dimension cannot apply to this case.",
    ),
}

#: Required field -> its paired ``*_observation`` field. ``None`` means the field
#: has no paired status and is therefore always required to carry evidence:
#: ``scope_class`` and ``problem_summary`` are present on every valid record by
#: construction, so there is no absence for a status to explain.
OBSERVATION_FIELD: Final[dict[str, str | None]] = {
    "scope_class": None,
    "problem_summary": None,
    "known_item_status": "known_item_status_observation",
    "target_asset_type": "target_asset_type_observation",
    "target_subjects": "target_subjects_observation",
    "retrieval_trigger": "retrieval_trigger_observation",
    "remembered_cues": "remembered_cues_observation",
    "forgotten_information": "forgotten_information_observation",
    "exact_query": "exact_query_observation",
    "query_paraphrase": "query_paraphrase_observation",
    "query_strategies": "query_strategies_observation",
    "reformulation_count": "reformulation_count_observation",
    "system_responses": "system_responses_observation",
    "workarounds": "workarounds_observation",
    "outcome": "outcome_observation",
    "impact_signals": "impact_signals_observation",
    "severity": "severity_observation",
}


def required_fields(contract: str) -> frozenset[str]:
    """Evidence-required fields for one contract.

    Raises ``KeyError`` for an unknown contract rather than returning an empty
    set, because an empty set would silently disable enforcement for a record
    type the validator does not recognise.
    """
    return EVIDENCE_REQUIRED[contract]


def exempt_fields(contract: str) -> frozenset[str]:
    """Evidence-exempt fields for one contract.

    The exempt list is global by category, as spec Section 15.10 writes it, but
    the required list is contract-scoped, and exactly one field differs between
    the two contracts: ``scope_class`` is a substantive claim on
    ``RelevanceDecision`` and an inherited, already-validated value on
    ``RetrievalCase``. Subtracting the contract's required set is what keeps
    "exactly one of the two lists" true per contract rather than approximately
    true overall.
    """
    return ALL_EXEMPT_FIELD_NAMES - EVIDENCE_REQUIRED.get(contract, frozenset())


def is_evidence_required(contract: str, field_name: str) -> bool:
    """Whether ``field_name`` on ``contract`` is a substantive claim.

    Contract-scoped, which is what lets ``scope_class`` be evidence-required on
    ``RelevanceDecision`` and exempt on ``RetrievalCase``, where it is inherited.
    """
    return field_name in EVIDENCE_REQUIRED.get(contract, frozenset())


def classify(contract: str, field_name: str) -> str:
    """Return ``"required"`` or the exempt category name for one field.

    Raises ``KeyError`` when a field belongs to neither list. That is the
    condition ``tests/test_evidence_map.py`` turns into a failing suite, so a new
    substantive field cannot quietly arrive without enforcement.
    """
    if is_evidence_required(contract, field_name):
        return "required"
    for category, names in EVIDENCE_EXEMPT.items():
        if field_name in names:
            return category
    raise KeyError(
        f"{contract}.{field_name} appears in neither EVIDENCE_REQUIRED nor "
        f"EVIDENCE_EXEMPT; classify it before it can be stored"
    )
