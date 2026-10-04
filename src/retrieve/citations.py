"""Validate ``[case_id]`` citations against the records that were retrieved.

The evidence panel is the intersection of cited and retrieved ids. An
unsupported id is removed once. If an unsupported id remains, the answer is
rejected and the panel is empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CITE = re.compile(r"\[([A-Za-z0-9_#.:-]+)\]")


@dataclass(frozen=True)
class CitationResult:
    cited: tuple[str, ...]
    rejected: bool
    repaired: bool


def _ids(text: str) -> list[str]:
    return _CITE.findall(text)


def validate_citations(answer: str, retrieved_ids: set[str]) -> CitationResult:
    """One repair, then reject. Cited ids are those that survived."""
    found = _ids(answer)
    if not found:
        return CitationResult(cited=(), rejected=False, repaired=False)
    valid = [item for item in found if item in retrieved_ids]
    unsupported = [item for item in found if item not in retrieved_ids]
    if not unsupported:
        return CitationResult(cited=tuple(dict.fromkeys(valid)), rejected=False, repaired=False)
    if not valid:
        return CitationResult(cited=(), rejected=True, repaired=True)
    return CitationResult(cited=tuple(dict.fromkeys(valid)), rejected=False, repaired=True)


def evidence_panel(answer: str, retrieved_ids: set[str]) -> list[str]:
    """Ids an evaluator may see under evidence used. Empty when rejected."""
    result = validate_citations(answer, retrieved_ids)
    if result.rejected:
        return []
    return [item for item in result.cited if item in retrieved_ids]
