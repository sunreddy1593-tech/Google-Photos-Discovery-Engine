"""Length-preserving PII masks (ARCHITECTURE Section 9.2).

Each replacement has the same character length as the span it covers, so an
evidence offset into ``raw_text`` addresses the same characters of
``raw_text_audit``. Overlapping matches keep the longest span, then the
earliest start, then a fixed type order. The result does not depend on the
order the patterns happened to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.versions import NORMALIZER_VERSION
from src.models.document_derived import RedactionSpan
from src.models.enums import RedactionType

#: One character, repeated. A word like ``[email]`` would change the length and
#: invalidate every offset after the first mask.
_MASK: str = "#"

_EMAIL: re.Pattern[str] = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
_PHONE: re.Pattern[str] = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)"
)
_HANDLE: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9._%+\-])@[A-Za-z0-9_]{2,30}\b"
)
_DIGITS: re.Pattern[str] = re.compile(r"(?<!\d)\d{8,}(?!\d)")

_TYPE_ORDER: dict[RedactionType, int] = {
    RedactionType.email: 0,
    RedactionType.phone: 1,
    RedactionType.handle: 2,
    RedactionType.digit_run: 3,
}


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    redaction_type: RedactionType


def redact(raw_text: str) -> tuple[str, tuple[RedactionSpan, ...]]:
    """Return ``raw_text_audit`` and the non-overlapping spans that produced it.

    ``len(audit) == len(raw_text)``. Characters outside a mask are copied
    unchanged, including spelling and non-breaking spaces.
    """
    chosen = _resolve(_find(raw_text))
    chars = list(raw_text)
    spans: list[RedactionSpan] = []
    for match in chosen:
        length = match.end - match.start
        chars[match.start:match.end] = [_MASK] * length
        spans.append(
            RedactionSpan(
                start_char=match.start,
                end_char=match.end,
                redaction_type=match.redaction_type,
                detector_version=NORMALIZER_VERSION,
            )
        )
    audit = "".join(chars)
    if len(audit) != len(raw_text):
        raise RuntimeError(
            "redaction changed the text length; masks must preserve length"
        )
    return audit, tuple(spans)


def _find(raw_text: str) -> list[_Match]:
    found: list[_Match] = []
    patterns = (
        (_EMAIL, RedactionType.email),
        (_PHONE, RedactionType.phone),
        (_HANDLE, RedactionType.handle),
        (_DIGITS, RedactionType.digit_run),
    )
    for pattern, kind in patterns:
        for match in pattern.finditer(raw_text):
            if match.end() > match.start():
                found.append(_Match(match.start(), match.end(), kind))
    return found


def _resolve(matches: list[_Match]) -> list[_Match]:
    """Longest span wins, then earliest start, then the type order above."""
    ordered = sorted(
        matches,
        key=lambda match: (
            -(match.end - match.start),
            match.start,
            _TYPE_ORDER[match.redaction_type],
        ),
    )
    chosen: list[_Match] = []
    for match in ordered:
        if any(match.start < kept.end and kept.start < match.end for kept in chosen):
            continue
        chosen.append(match)
    chosen.sort(key=lambda match: (match.start, match.end, match.redaction_type.value))
    return chosen
