"""Extraction stage.

Phase 1 builds only :mod:`src.extract.validator`, the gate every extracted record
has to pass. The prompt, the extractor, and the persistence layer arrive in
Phase 5; the validator exists first because it is what those three are measured
against, and building them in the other order is how validation ends up being
relaxed to let output through.
"""

from __future__ import annotations

from src.extract.validator import (
    RecordValidation,
    SpanValidation,
    derive_all_evidence_spans,
    validate_record,
    validate_span,
    validate_spans,
)

__all__ = [
    "RecordValidation",
    "SpanValidation",
    "derive_all_evidence_spans",
    "validate_record",
    "validate_span",
    "validate_spans",
]
