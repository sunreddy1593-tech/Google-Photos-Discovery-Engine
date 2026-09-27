"""Normalization: derived text, redaction, canonical URLs, and hashes.

This package reads ``CollectedDocument`` and returns ``DocumentDerived``. It
does not import deduplication, review, or any later stage.
"""

from src.normalize.derive import derive_document

__all__ = ["derive_document"]
