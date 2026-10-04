"""Compare stored case fields. Counts are model assignments, not a taxonomy."""

from __future__ import annotations

from collections import Counter
from typing import Any

CORE = "core_incomplete_recall"
ADJACENT = "adjacent_known_item_retrieval"

DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("target_asset_type", "Target item"),
    ("remembered_cues", "Remembered cues"),
    ("query_strategies", "Query strategies"),
    ("system_responses", "System responses"),
    ("outcome", "Outcomes"),
)


def comparison(cards: list[dict[str, Any]], *, approved_only: bool) -> dict[str, Any]:
    """Split core and adjacent cases. Unapproved output stays out of conclusions."""
    chosen = []
    for card in cards:
        if card.get("kind") != "case":
            continue
        if approved_only:
            if card.get("semantically_approved"):
                chosen.append(card)
        elif card.get("automatically_valid") and not card.get("semantically_approved"):
            chosen.append(card)
    return {
        "approved_only": approved_only,
        "case_count": len(chosen),
        "core": _bucket(chosen, CORE),
        "adjacent": _bucket(chosen, ADJACENT),
    }


def _bucket(cards: list[dict[str, Any]], scope: str) -> dict[str, Any]:
    group = [card for card in cards if card.get("model_scope_class") == scope]
    dimensions = []
    for field_name, label in DIMENSIONS:
        counter: Counter[str] = Counter()
        links: dict[str, list[str]] = {}
        for card in group:
            for value in _values(card.get("assigned_values") or {}, field_name):
                counter[value] += 1
                links.setdefault(value, []).append(str(card.get("case_id") or card.get("doc_id")))
        dimensions.append(
            {
                "field": field_name,
                "label": label,
                "rows": [
                    {"value": value, "count": count, "cases": links[value]}
                    for value, count in counter.most_common()
                ],
            }
        )
    return {
        "scope_class": scope,
        "case_count": len(group),
        "case_ids": [str(card.get("case_id") or "") for card in group],
        "dimensions": dimensions,
    }


def _values(assigned: dict[str, Any], field_name: str) -> list[str]:
    payload = assigned.get(field_name)
    if not isinstance(payload, dict):
        return []
    value = payload.get("value")
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]
