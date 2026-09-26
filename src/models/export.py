"""`PublicExportRecord` — the committed public artifact (spec Section 15.12).

Implements the public-export profile in spec Section 12.1 (ADR-23). The shape is
driven by one constraint: an evaluator must be able to read the evidence and open
the source, and nothing beyond that may leave the machine.

Hence the **minimum redacted excerpt**. Rather than the full document, the export
carries only enough text to contain every validated span plus a configured
context window, with ``excerpt_start_char`` recording where the excerpt sits in
``raw_text_audit`` so excerpt-relative offsets map back to document coordinates.
Highlighting in the app then uses stored offsets and never re-searches for the
quote at render time — a second, unvalidated matching implementation is exactly
the thing the evidence architecture exists to avoid.

Phase 10 builds the exporter and the test that scans the *generated artifact* for
usernames, credentials, emails, and phone numbers. Phase 1 builds only the
contract, but ``excerpt_is_full_text`` defaults to ``False`` here so the
permissive case has to be asked for.
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from src.models.base import ResearchModel, VersionedModel
from src.models.enums import EvidenceTier, SourcePlatform, SourceType
from src.models.evidence_map import ALL_EVIDENCE_FIELD_NAMES


class ExportedEvidenceSpan(ResearchModel):
    """A validated span with offsets rebased to the excerpt (spec 15.12)."""

    field_name: str = Field(
        min_length=1,
        description=(
            "The evidence-required field this span supports. Paraphrase fields "
            "are not admissible here (spec Section 17.19)."
        ),
    )
    quote: str = Field(min_length=1)
    excerpt_start_char: int = Field(
        ge=0, description="Offset within the exported excerpt."
    )
    excerpt_end_char: int = Field(ge=0)
    document_start_char: int = Field(
        ge=0, description="Original offset within raw_text_audit, retained."
    )
    document_end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_field_name_is_quotable(self) -> "ExportedEvidenceSpan":
        """Only an evidence-required field may appear as a quotation.

        This is the enforcement point for "a paraphrase is never displayed in
        quotation marks" (spec Section 17.19). ``reason_summary`` and
        ``problem_summary`` are evidence-exempt precisely because they are the
        analyst's or model's words, and this contract is what the evidence
        browser highlights: a span admitted here is rendered as though the user
        wrote it. Without this check the export could put a model's paraphrase in
        quotation marks beside a real quote, which is the fabrication the whole
        evidence architecture exists to prevent — arriving at the last step.
        """
        if self.field_name not in ALL_EVIDENCE_FIELD_NAMES:
            raise ValueError(
                f"field_name {self.field_name!r} is not an evidence-required "
                f"field and must never be exported as a quotation; a paraphrase "
                f"belongs in extracted_fields, unquoted (spec Section 17.19). "
                f"Quotable fields: {sorted(ALL_EVIDENCE_FIELD_NAMES)}"
            )
        return self

    @model_validator(mode="after")
    def _check_offsets(self) -> "ExportedEvidenceSpan":
        if self.excerpt_end_char <= self.excerpt_start_char:
            raise ValueError("excerpt_end_char must exceed excerpt_start_char")
        if self.document_end_char <= self.document_start_char:
            raise ValueError("document_end_char must exceed document_start_char")
        if (self.excerpt_end_char - self.excerpt_start_char) != (
            self.document_end_char - self.document_start_char
        ):
            raise ValueError(
                "rebasing an offset changes where a span starts, never how long "
                "it is; excerpt and document lengths disagree"
            )
        return self


class PublicExportRecord(VersionedModel):
    """One exported case (spec Section 15.12)."""

    case_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)

    source_platform: SourcePlatform
    source_type: SourceType
    evidence_tier: EvidenceTier
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    canonical_url: str = Field(min_length=1)
    published_at: AwareDatetime | None = None
    collected_at: AwareDatetime | None = None

    author_key: str | None = Field(
        default=None,
        description=(
            "Truncated author_hash: enough to count distinct authors, not enough "
            "to identify one. Never a username, never the salt."
        ),
    )

    excerpt: str = Field(min_length=1)
    excerpt_start_char: int = Field(
        ge=0, description="Offset of excerpt within raw_text_audit."
    )
    excerpt_is_full_text: bool = Field(
        default=False,
        description=(
            "True only where a source's redistribution terms explicitly permit "
            "full text, recorded per source in DECISIONS.md."
        ),
    )
    evidence_spans: tuple[ExportedEvidenceSpan, ...] = ()

    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Spec Section 15.4 values, observation statuses, and ObservedValue "
            "members."
        ),
    )

    cluster_id: str | None = None
    taxonomy_version: str | None = None
    prompt_version: str | None = None
    normalizer_version: str | None = None
    dataset_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_spans_fall_inside_the_excerpt(self) -> "PublicExportRecord":
        """A rebased span must address text the reader actually received.

        Spec Section 15.12 requires the excerpt to contain *every* validated span
        for the record. A span pointing past the excerpt end means the excerpt was
        trimmed after rebasing, and the evidence browser would highlight nothing.
        """
        length = len(self.excerpt)
        for span in self.evidence_spans:
            if span.excerpt_end_char > length:
                raise ValueError(
                    f"span [{span.excerpt_start_char}, {span.excerpt_end_char}) "
                    f"falls outside an excerpt of length {length}"
                )
            actual = self.excerpt[span.excerpt_start_char : span.excerpt_end_char]
            if actual != span.quote:
                raise ValueError(
                    f"rebased offsets do not address the quote: excerpt holds "
                    f"{actual!r}, span claims {span.quote!r}"
                )
            if span.document_start_char - self.excerpt_start_char != (
                span.excerpt_start_char
            ):
                raise ValueError(
                    "excerpt_start_char does not reconcile document and excerpt "
                    "offsets; the mapping back to document coordinates is broken"
                )
        return self

    @model_validator(mode="after")
    def _check_taxonomy_pairing(self) -> "PublicExportRecord":
        if bool(self.cluster_id) != bool(self.taxonomy_version):
            raise ValueError(
                "cluster_id and taxonomy_version travel together: a cluster "
                "label means nothing without the taxonomy version that defined it"
            )
        return self
