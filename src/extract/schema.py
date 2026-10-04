"""Model-facing extraction claims; application-owned provenance stays local.

This response shape uses the existing dimension vocabularies. The existing
RetrievalCase and record gate, rather than this transport model, enforce the
value/status/evidence contract when a response is assembled.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, Mapping, TypeVar

from pydantic import Field, model_validator

from src.models.base import ResearchModel
from src.models.enums import (
    DimensionObservationStatus,
    ForgottenInfo,
    ImpactSignal,
    KnownItemStatus,
    Outcome,
    QueryStrategy,
    RememberedCue,
    Speaker,
    SubjectType,
    SystemResponse,
    TargetAssetType,
    Workaround,
)


class QuotePayload(ResearchModel):
    """A target-document quote, with unknown offsets represented by null."""

    quote: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    speaker: Speaker


ValueT = TypeVar("ValueT")


class LabelPayload(ResearchModel, Generic[ValueT]):
    value: ValueT
    # Match ObservedValue: only target_subjects permits free-text detail.
    detail: None = None
    evidence: QuotePayload


class SubjectLabelPayload(LabelPayload[SubjectType]):
    detail: str | None = None


class FieldEvidencePayload(QuotePayload):
    """External evidence for scalar claims or evidenced empty dimensions."""

    field_name: Literal[
        "known_item_status", "target_asset_type", "target_subjects",
        "retrieval_trigger", "remembered_cues", "forgotten_information",
        "exact_query", "query_paraphrase", "query_strategies",
        "reformulation_count", "system_responses", "workarounds", "outcome",
        "impact_signals", "problem_summary",
    ]


class ExtractionCasePayload(ResearchModel):
    known_item_status: KnownItemStatus | None = None
    known_item_status_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    target_asset_type: TargetAssetType | None = None
    target_asset_type_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    target_subjects: tuple[SubjectLabelPayload, ...] = ()
    target_subjects_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    retrieval_trigger: str | None = None
    retrieval_trigger_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    remembered_cues: tuple[LabelPayload[RememberedCue], ...] = ()
    remembered_cues_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    forgotten_information: tuple[LabelPayload[ForgottenInfo], ...] = ()
    forgotten_information_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    exact_query: str | None = None
    exact_query_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    query_paraphrase: str | None = None
    query_paraphrase_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    query_strategies: tuple[LabelPayload[QueryStrategy], ...] = ()
    query_strategies_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    reformulation_count: int | None = Field(default=None, ge=0)
    reformulation_count_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    system_responses: tuple[LabelPayload[SystemResponse], ...] = ()
    system_responses_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    workarounds: tuple[LabelPayload[Workaround], ...] = ()
    workarounds_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    outcome: Outcome | None = None
    outcome_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    impact_signals: tuple[LabelPayload[ImpactSignal], ...] = ()
    impact_signals_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    severity: int | None = Field(default=None, ge=1, le=5)
    severity_observation: DimensionObservationStatus = DimensionObservationStatus.not_stated
    severity_evidence: tuple[QuotePayload, ...] = ()
    problem_summary: str = Field(min_length=1)
    field_evidence: tuple[FieldEvidencePayload, ...] = ()
    uncertainty_notes: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def discard_supplied_union(cls, data: Any) -> Any:
        # Spec 15.10: field-level evidence is primary, the union is derived.
        if isinstance(data, Mapping):
            return {key: value for key, value in data.items() if key != "all_evidence_spans"}
        return data


class ExtractionPayload(ResearchModel):
    doc_id: str = Field(min_length=1)
    cases: tuple[ExtractionCasePayload, ...]


def extraction_schema(doc_id: str) -> dict[str, Any]:
    """Application schema with request-specific identity, before SDK conversion.

    Provider-side strict conversion belongs to src/llm. The converted object must
    be supplied unchanged to both the prompt builder and response_format.
    """
    if not doc_id.strip():
        raise ValueError("doc_id must be non-empty")
    schema = ExtractionPayload.model_json_schema()
    schema["properties"]["doc_id"]["enum"] = [doc_id]
    return schema
