"""Render a redacted excerpt with highlights at stored offsets."""

from __future__ import annotations

from html import escape
from typing import Any


def highlight_excerpt(excerpt: str, spans: list[dict[str, Any]]) -> str:
    """Highlight only spans whose stored offsets still equal the quote.

    The quote is not searched for again. A span that misses its offsets is left
    unmarked so a second matcher cannot promote it.
    """
    marks: list[tuple[int, int]] = []
    for span in spans:
        start = span.get("excerpt_start_char")
        end = span.get("excerpt_end_char")
        quote = span.get("quote")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(quote, str):
            continue
        if end <= start or end > len(excerpt):
            continue
        if excerpt[start:end] != quote:
            continue
        marks.append((start, end))
    if not marks:
        return f"<p>{escape(excerpt)}</p>" if excerpt else "<p></p>"
    marks.sort()
    pieces: list[str] = []
    cursor = 0
    for start, end in _merge(marks):
        pieces.append(escape(excerpt[cursor:start]))
        pieces.append(f"<mark>{escape(excerpt[start:end])}</mark>")
        cursor = end
    pieces.append(escape(excerpt[cursor:]))
    return "<p>" + "".join(pieces) + "</p>"


def _merge(marks: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in marks:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
