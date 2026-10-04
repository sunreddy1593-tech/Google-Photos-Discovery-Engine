"""Unnamed groupings from label co-occurrence. This module does not name clusters."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping


def _signature(case: Mapping[str, object]) -> str:
    parts: list[str] = []
    for field_name in ("scope_class", "outcome"):
        block = case.get(field_name)
        if isinstance(block, Mapping):
            parts.append(f"{field_name}={block.get('value') or block.get('observation')}")
        elif block:
            parts.append(f"{field_name}={block}")
    return "|".join(parts) or "unlabeled"


def propose_groupings(cases: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Group cases that share a label signature. The result has no cluster id."""
    groups: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        if str(case.get("technical_state") or "ok") != "ok":
            continue
        case_id = str(case.get("case_id") or "")
        if case_id:
            groups[_signature(case)].append(case_id)
    return [
        {
            "label_signature": signature,
            "case_ids": tuple(sorted(ids)),
            "size": len(ids),
        }
        for signature, ids in sorted(groups.items())
    ]
