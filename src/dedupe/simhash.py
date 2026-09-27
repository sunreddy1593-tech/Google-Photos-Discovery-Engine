"""Hamming distance between stored 64-bit simhashes.

Generation of the hash lives in normalization. This module only compares the
hex strings ``DocumentDerived`` already carries, so dedupe does not import
``src.normalize``.
"""

from __future__ import annotations


def hamming_distance(left: str, right: str) -> int:
    """Bit differences between two 16-hex-character simhashes."""
    return (int(left, 16) ^ int(right, 16)).bit_count()
