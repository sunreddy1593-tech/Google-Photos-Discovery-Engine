"""`DocumentDerived` — normalization output (spec Section 15.6).

One row per document, produced by Phase 3, rebuildable at any time from the
:class:`~src.models.collected_document.CollectedDocument` plus the normalizer
version. It holds no independent truth, which is why it is a separate record: a
normalizer change rewrites this row and touches nothing that was collected.

The load-bearing rule is ``len(raw_text_audit) == len(raw_text)``. Masking PII
with a replacement of identical character length is what keeps every evidence
offset valid against both the collected text and the redacted text, so the same
span can be validated locally, sent to a provider, and shown to an evaluator
without three different coordinate spaces (ARCHITECTURE Section 9.2).

That equality cannot be a field validator, because ``raw_text`` is not on this
record. It is :meth:`DocumentDerived.check_length_preserved`, called by the
Phase 3 normalizer and by the store layer, and it raises rather than warns.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from src.core.errors import ValidationError
from src.models.base import ResearchModel, VersionedModel
from src.models.enums import RedactionType


class RedactionSpan(ResearchModel):
    """One masked region of ``raw_text_audit`` (spec Section 15.6).

    Offsets are in the same coordinate space as every evidence offset, which is
    what lets the validator reject a span that overlaps personal data instead of
    discovering the overlap at display time.
    """

    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    redaction_type: RedactionType
    detector_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_bounds(self) -> "RedactionSpan":
        if self.end_char <= self.start_char:
            raise ValueError(
                f"end_char is exclusive and must exceed start_char, got "
                f"start_char={self.start_char}, end_char={self.end_char}"
            )
        return self

    @property
    def length(self) -> int:
        return self.end_char - self.start_char

    def overlaps(self, start_char: int, end_char: int) -> bool:
        """Whether ``[start_char, end_char)`` intersects this masked region."""
        return start_char < self.end_char and end_char > self.start_char


class DocumentDerived(VersionedModel):
    """Derived text and hashes for one document (spec Section 15.6)."""

    doc_id: str = Field(min_length=1)

    normalized_text: str = Field(
        description=(
            "NFKC, lowercased, whitespace-collapsed text for matching, "
            "prefiltering, and lexical retrieval. Never used for evidence "
            "offsets (invariant I2)."
        )
    )
    raw_text_audit: str = Field(
        description=(
            "raw_text with each detected PII span replaced by a mask of "
            "identical character length. The text sent to model providers and "
            "shown to evaluators."
        )
    )
    redaction_spans: tuple[RedactionSpan, ...] = ()

    canonical_url: str = Field(min_length=1)
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 of the canonicalized text, for exact-duplicate grouping.",
    )
    simhash: str = Field(
        min_length=1,
        description="64-bit simhash over 3-word shingles, for near-duplicate blocking.",
    )
    token_count: int = Field(
        ge=0,
        description=(
            "Token count of normalized_text. Drives the dedupe_min_tokens guard "
            "(spec Section 19.6)."
        ),
    )

    language_detected: str | None = Field(
        default=None,
        description=(
            "Null when detection is unavailable or inconclusive. The collected "
            "language_reported is never overwritten."
        ),
    )
    language_detector_version: str | None = None

    normalizer_version: str = Field(min_length=1)
    derived_at: AwareDatetime

    @model_validator(mode="after")
    def _check_redactions_are_inside_the_audit_text(self) -> "DocumentDerived":
        """Every mask must address a region that exists.

        A redaction span past the end of the text would make the overlap check in
        the evidence validator silently vacuous for that region.
        """
        length = len(self.raw_text_audit)
        for span in self.redaction_spans:
            if span.end_char > length:
                raise ValueError(
                    f"redaction span [{span.start_char}, {span.end_char}) falls "
                    f"outside raw_text_audit of length {length}"
                )

        ordered = sorted(self.redaction_spans, key=lambda s: s.start_char)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.start_char < earlier.end_char:
                raise ValueError(
                    f"redaction spans overlap: [{earlier.start_char}, "
                    f"{earlier.end_char}) and [{later.start_char}, "
                    f"{later.end_char})"
                )
        return self

    def check_length_preserved(self, raw_text: str) -> None:
        """Assert ``len(raw_text_audit) == len(raw_text)`` (spec Section 15.6).

        Raises :class:`~src.core.errors.ValidationError` on mismatch. A shortened
        or lengthened audit text invalidates every evidence offset downstream of
        the first edit, and it does so silently — the offsets still point
        somewhere, just not at the quote. This is the check that makes one
        coordinate space possible, so it is an exception rather than a log line.
        """
        if len(self.raw_text_audit) != len(raw_text):
            raise ValidationError(
                f"redaction changed the text length for {self.doc_id}: "
                f"raw_text is {len(raw_text)} characters, raw_text_audit is "
                f"{len(self.raw_text_audit)}. Masks must preserve length or "
                f"every evidence offset after the first mask is wrong."
            )

    def redaction_overlapping(
        self, start_char: int, end_char: int
    ) -> RedactionSpan | None:
        """The first masked region intersecting ``[start_char, end_char)``, if any."""
        for span in sorted(self.redaction_spans, key=lambda s: s.start_char):
            if span.overlaps(start_char, end_char):
                return span
        return None
