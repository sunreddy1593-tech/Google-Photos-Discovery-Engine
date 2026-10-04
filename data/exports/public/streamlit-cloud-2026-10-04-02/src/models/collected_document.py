"""`CollectedDocument` — immutable collection-time provenance and raw text.

Spec Section 15.1. This record is complete the moment a document is imported.
Nothing in it depends on normalization, canonical hashing, deduplication,
classification, or extraction, which is invariant I11 and the property that lets
Phase 1 and Phase 2 be finished independently of Phase 3.

Five fields that a previous draft put here now live where they are actually
produced (ADR-15):

===================== ==========================================
Former field          Now
===================== ==========================================
``normalized_text``   ``DocumentDerived.normalized_text``
``content_hash``      ``DocumentDerived.content_hash``
``redactions``        ``DocumentDerived.redaction_spans``
``duplicate_of``      ``DuplicateLink.canonical_doc_id``
``duplicate_kind``    ``DuplicateLink.duplicate_kind``
===================== ==========================================

Because ``extra="forbid"`` is inherited from :class:`ResearchModel`, passing any
of them raises rather than being quietly retained. That is deliberate: the reason
they moved is that an importer which cannot produce ``content_hash`` is still a
valid importer, and a permissive model would let the dependency creep back in one
convenient keyword argument at a time.
"""

from __future__ import annotations

from typing import Any

from pydantic import AnyHttpUrl, AwareDatetime, Field, field_validator

from src.models.base import VersionedModel
from src.models.enums import (
    CollectionMethod,
    EvidenceTier,
    SourcePlatform,
    SourceType,
)


class CollectedDocument(VersionedModel):
    """One collected public document (spec Section 15.1).

    Written once. No ``UPDATE`` or ``DELETE`` is permitted against it; the Phase 2
    store enforces that at the database level, and the frozen model enforces it
    in memory.
    """

    doc_id: str = Field(
        min_length=1,
        description=(
            "Stable deterministic identifier, derivable at import from "
            "collection-time values only (spec Section 26.1)."
        ),
    )
    ingest_batch_id: str = Field(min_length=1)

    source_platform: SourcePlatform
    source_type: SourceType
    evidence_tier: EvidenceTier = Field(
        description=(
            "Tiered honestly at collection time. Counting a tech-press article "
            "as user evidence was the prototype's main defect (ARCHITECTURE "
            "Section 20.2), and the fix only works on the way in."
        )
    )

    source_item_id: str | None = None
    parent_thread_id: str | None = None
    source_url: AnyHttpUrl = Field(
        description="Direct permalink wherever possible, stored exactly as collected."
    )
    source_url_key: str = Field(
        min_length=1,
        description=(
            "Deterministic import-time URL normalization. Distinct from the "
            "Phase 3 canonical_url, which may resolve share-link and redirect "
            "forms and can require a network call."
        ),
    )
    source_name: str = Field(min_length=1)
    title: str | None = None

    author_hash: str | None = Field(
        default=None,
        description=(
            "Salted deterministic author hash. A plaintext username is never "
            "stored here or in any downstream record (spec Section 12)."
        ),
    )
    author_salt_id: str = Field(
        min_length=1,
        description="Identifier of the salt used, never the salt value.",
    )

    published_at: AwareDatetime | None = None
    collected_at: AwareDatetime
    language_reported: str | None = Field(
        default=None,
        description=(
            "Language as supplied by the source or importer. Detection is a "
            "derived field (DocumentDerived.language_detected)."
        ),
    )

    raw_text: str = Field(
        min_length=1,
        description=(
            "Original collected text, verbatim. The only coordinate space for "
            "evidence offsets (invariant I2)."
        ),
    )
    raw_text_sha256: str = Field(
        min_length=64,
        max_length=64,
        description=(
            "SHA-256 of raw_text exactly as collected. A pure function of raw "
            "text, therefore available at import. Not content_hash, which is a "
            "canonicalized Phase 3 value."
        ),
    )

    collection_query: str | None = None
    collection_method: CollectionMethod
    rating: float | None = Field(default=None, ge=0)
    engagement: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("raw_text")
    @classmethod
    def _reject_blank_raw_text(cls, value: str) -> str:
        """Whitespace-only text is an empty document with extra steps.

        ``min_length`` alone would accept ``"   "``, which would then produce
        offsets into nothing and a document that can never carry evidence.
        """
        if not value.strip():
            raise ValueError("raw_text must contain non-whitespace characters")
        return value

    @field_validator("raw_text_sha256")
    @classmethod
    def _check_hash_is_hex(cls, value: str) -> str:
        lowered = value.lower()
        if any(ch not in "0123456789abcdef" for ch in lowered):
            raise ValueError("raw_text_sha256 must be a hex SHA-256 digest")
        return lowered

    @property
    def is_synthetic(self) -> bool:
        """Whether this document is a test fixture (invariant I9).

        Every analysis query filters on the tier rather than on where a file
        lives, so a fixture cannot reach a research output by being moved.
        """
        return self.evidence_tier is EvidenceTier.synthetic_test
