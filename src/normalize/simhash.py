"""64-bit simhash over 3-word shingles (ADR-11, spec Section 15.6).

The value is a property of ``normalized_text``, so it is computed while the
derived record is built. Deduplication only compares the stored hex strings.
"""

from __future__ import annotations

import hashlib


def simhash_hex(normalized: str) -> str:
    """16 hex characters. Texts shorter than three words use one shingle.

    A tie on a bit (equal votes for 0 and 1) resolves to 0, so the same text
    always produces the same hash.
    """
    tokens = normalized.split()
    if len(tokens) >= 3:
        shingles = [
            " ".join(tokens[index:index + 3]) for index in range(len(tokens) - 2)
        ]
    elif tokens:
        shingles = [" ".join(tokens)]
    else:
        shingles = []

    if not shingles:
        return "0" * 16

    votes = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.sha1(shingle.encode("utf-8")).digest()[:8], "big")
        for bit in range(64):
            if value & (1 << bit):
                votes[bit] += 1
            else:
                votes[bit] -= 1

    result = 0
    for bit, vote in enumerate(votes):
        if vote > 0:
            result |= 1 << bit
    return f"{result:016x}"
