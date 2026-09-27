"""Deterministic text normalization (spec Section 15.6).

``normalized_text`` is for matching. It is never the coordinate space for
evidence offsets, and producing it does not change ``raw_text``.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE: re.Pattern[str] = re.compile(r"\s+")


def normalized_text(raw_text: str) -> str:
    """NFKC, lowercase, and collapse every whitespace run to one space.

    The input string is not modified. Callers keep the collected text and store
    this result on ``DocumentDerived``.
    """
    folded = unicodedata.normalize("NFKC", raw_text).lower()
    return _WHITESPACE.sub(" ", folded).strip()
