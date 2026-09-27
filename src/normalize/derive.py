"""Build one ``DocumentDerived`` from one collected document.

The collected record is only read. ``raw_text`` stays on that record, byte for
byte, and nothing here writes back into it.
"""

from __future__ import annotations

from datetime import datetime

from src.core.ids import content_hash
from src.core.versions import NORMALIZER_VERSION
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.normalize.canonicalize import canonical_url
from src.normalize.privacy import redact
from src.normalize.simhash import simhash_hex
from src.normalize.text import normalized_text
from src.normalize.tokens import token_count


def derive_document(
    document: CollectedDocument, *, derived_at: datetime
) -> DocumentDerived:
    """Normalize, redact, and hash ``document`` into a derived row.

    ``language_detected`` carries ``language_reported`` when no detector is
    available, so the collected language is not dropped. ``language_reported``
    itself is left on the collected record. ``language_detector_version`` stays
    null because nothing detected a language.
    """
    original = document.raw_text
    normalized = normalized_text(original)
    audit, spans = redact(original)
    derived = DocumentDerived(
        doc_id=document.doc_id,
        normalized_text=normalized,
        raw_text_audit=audit,
        redaction_spans=spans,
        canonical_url=canonical_url(str(document.source_url)),
        content_hash=content_hash(original),
        simhash=simhash_hex(normalized),
        token_count=token_count(normalized),
        language_detected=document.language_reported,
        language_detector_version=None,
        normalizer_version=NORMALIZER_VERSION,
        derived_at=derived_at,
    )
    derived.check_length_preserved(original)
    return derived
