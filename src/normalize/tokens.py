"""Token counts for the dedupe length guard (spec Section 19.6).

The count is the number of whitespace-separated words in ``normalized_text``.
That is deterministic and needs no extra tokenizer. ``dedupe_min_tokens`` is
compared against this number.
"""

from __future__ import annotations


def token_count(normalized: str) -> int:
    """Word count of already-normalized text. Empty text counts as zero."""
    if not normalized:
        return 0
    return len(normalized.split())
