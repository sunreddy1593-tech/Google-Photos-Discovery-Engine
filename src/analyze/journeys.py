"""Need → cue → strategy → response → workaround → outcome → impact."""

from __future__ import annotations

from typing import Iterable, Mapping


def _shown(block: object) -> str:
    if not isinstance(block, Mapping):
        return "not_stated"
    status = str(block.get("observation") or "not_stated")
    if status != "stated":
        return status
    value = block.get("value")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, Mapping):
                parts.append(str(item.get("value") or ""))
            else:
                parts.append(str(item))
        return ", ".join(part for part in parts if part) or status
    return str(value or status)


def build_journeys(cases: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    """One row per technically successful case. Status words stay unmerged."""
    rows: list[dict[str, str]] = []
    for case in cases:
        if str(case.get("technical_state") or "ok") != "ok":
            continue
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "need": _shown(case.get("retrieval_trigger")),
                "cue": _shown(case.get("remembered_cues")),
                "strategy": _shown(case.get("query_strategies")),
                "response": _shown(case.get("system_responses")),
                "workaround": _shown(case.get("workarounds")),
                "outcome": _shown(case.get("outcome")),
                "impact": _shown(case.get("impact_signals")),
            }
        )
    return rows
