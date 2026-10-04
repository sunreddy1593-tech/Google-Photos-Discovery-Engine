"""Align extracted cases to gold cases by evidence-span overlap.

The match is greedy and does not use list order. A pair scores the number of
gold quotes whose character range overlaps an extracted span. Equal quotes are
the fallback when the document text is absent. Version: evidence-overlap/v1.
"""

from __future__ import annotations

from dataclasses import dataclass

MATCH_VERSION = "evidence-overlap/v1"


@dataclass(frozen=True)
class MatchSpan:
    """One extracted span. Offsets are document coordinates."""

    quote: str
    start_char: int | None
    end_char: int | None
    validation_state: str
    field_name: str


def match_cases(
    gold_cases: tuple | list,
    extracted_cases: tuple | list,
    text: str | None = None,
) -> tuple[tuple[object, object], ...]:
    """Return matched pairs. Unmatched gold and extracted cases are omitted."""
    candidates: list[tuple[int, str, str, object, object]] = []
    for gold in gold_cases:
        for extracted in extracted_cases:
            score = _score(gold, extracted, text)
            if score <= 0:
                continue
            candidates.append(
                (
                    score,
                    str(getattr(gold, "gold_case_id")),
                    str(getattr(extracted, "case_id")),
                    gold,
                    extracted,
                )
            )
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_gold: set[str] = set()
    used_extracted: set[str] = set()
    pairs: list[tuple[object, object]] = []
    for _ranked, gold_id, extracted_id, gold, extracted in candidates:
        if gold_id in used_gold or extracted_id in used_extracted:
            continue
        used_gold.add(gold_id)
        used_extracted.add(extracted_id)
        pairs.append((gold, extracted))
    return tuple(pairs)


def _score(gold: object, extracted: object, text: str | None) -> int:
    quotes = tuple(getattr(gold, "expected_evidence", ()) or ())
    spans = tuple(getattr(extracted, "spans", ()) or ())
    if not quotes or not spans:
        return 0
    matched = 0
    for quote in quotes:
        if any(_quote_overlaps(str(quote), span, text) for span in spans):
            matched += 1
    return matched


def _quote_overlaps(quote: str, span: MatchSpan, text: str | None) -> bool:
    if quote == span.quote:
        return True
    if (
        text is None
        or span.start_char is None
        or span.end_char is None
        or not quote
    ):
        return False
    start = 0
    while True:
        found = text.find(quote, start)
        if found < 0:
            return False
        end = found + len(quote)
        if found < span.end_char and span.start_char < end:
            return True
        start = found + 1
