"""Deduplication. Links documents; never deletes them.

Detection reads prepared fields only. It does not import ``src.normalize``:
the runner passes ``content_hash`` and ``simhash`` that normalization already
stored on ``DocumentDerived``.
"""

from src.dedupe.detect import PreparedDocument, detect_links

__all__ = ["PreparedDocument", "detect_links"]
