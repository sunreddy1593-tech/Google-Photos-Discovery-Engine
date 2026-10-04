"""Cue × forgotten cross-tab. Status values come from the schema only."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from src.models.enums import DimensionObservationStatus

_STATUSES = {member.value for member in DimensionObservationStatus}


def _labels(block: Mapping[str, object] | None, *, empty_status: str) -> list[str]:
    if not block:
        return [empty_status]
    status = str(block.get("observation") or empty_status)
    if status not in _STATUSES:
        raise ValueError(f"observation status {status!r} is not a schema member")
    if status != DimensionObservationStatus.stated.value:
        return [status]
    values = block.get("value") or []
    if isinstance(values, str):
        values = [values]
    names: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            names.append(str(item.get("value") or status))
        else:
            names.append(str(item))
    return names or [status]


def build_memory_map(cases: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Cross-tab remembered cues against forgotten information.

    ``not_stated`` and ``explicitly_none`` stay separate. Records whose
    ``technical_state`` is not ``ok`` are excluded and counted.
    """
    cells: Counter[tuple[str, str]] = Counter()
    excluded = 0
    for case in cases:
        technical = str(case.get("technical_state") or "ok")
        if technical != "ok":
            excluded += 1
            continue
        cues = _labels(case.get("remembered_cues"), empty_status="not_stated")  # type: ignore[arg-type]
        forgotten = _labels(case.get("forgotten_information"), empty_status="not_stated")  # type: ignore[arg-type]
        for cue in cues:
            for item in forgotten:
                cells[(cue, item)] += 1
    rows = [
        {"remembered": cue, "forgotten": forgotten, "cases": count}
        for (cue, forgotten), count in sorted(cells.items())
    ]
    statuses = sorted(
        value
        for row in rows
        for value in (row["remembered"], row["forgotten"])
        if value in _STATUSES
    )
    return {
        "cells": rows,
        "excluded_technical_failures": excluded,
        "statuses_used": statuses,
    }
