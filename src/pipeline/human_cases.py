"""Build a human retrieval case without editing the model row.

The review package owns the override ledger. This module checks optional
evidence and returns a separate case with ``extractor_type = human``. A quote
that is not verbatim stays pending and does not become the current case.
"""

from __future__ import annotations

from datetime import datetime

from src.core.ids import extraction_fingerprint
from src.core.versions import SCHEMA_VERSION
from src.extract.validator import validate_span
from src.models.enums import (
    EvidenceOwnerType,
    ExtractorType,
    OffsetState,
    Speaker,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.retrieval_case import RetrievalCase
from src.review.overrides import CaseOverride


def build_human_case(
    model_case: RetrievalCase,
    override: CaseOverride,
    *,
    audit: str,
    content_hash: str,
    extracted_at: datetime,
) -> RetrievalCase:
    """Copy the model case into a human row. The model object is not updated.

    ``override.evidence_quote`` is optional. When it is present it must occur
    in ``audit`` at resolvable offsets. The quote is not written onto the case
    as a new claim.
    """
    if override.target_id != model_case.case_id or override.doc_id != model_case.doc_id:
        raise ValueError("case override does not address this model case")
    accepted = _quote_is_verbatim(override, audit)
    payload = model_case.model_dump(mode="python")
    payload.update(
        extractor_type=ExtractorType.human,
        model_name=None,
        extraction_fingerprint=extraction_fingerprint(
            "human",
            model_case.prompt_version,
            SCHEMA_VERSION,
            content_hash,
        ),
        extracted_at=extracted_at,
        needs_human_review=not accepted,
        validation_state=ValidationState.valid if accepted else ValidationState.pending,
    )
    return RetrievalCase.model_validate(payload)


def _quote_is_verbatim(override: CaseOverride, audit: str) -> bool:
    if override.evidence_quote is None:
        return True
    candidate = EvidenceSpan(
        doc_id=override.doc_id,
        owner_type=EvidenceOwnerType.retrieval_case,
        owner_id=override.target_id,
        field_name="problem_summary",
        quote=override.evidence_quote,
        start_char=None,
        end_char=None,
        speaker=Speaker.unattributed,
        offset_state=OffsetState.missing_unresolved,
        validation_state=ValidationState.pending,
    )
    checked = validate_span(candidate, audit)
    span = checked.span
    return bool(
        checked.ok
        and span.doc_id == override.doc_id
        and span.owner_id == override.target_id
        and span.quote == override.evidence_quote
    )
