"""Per-stage funnel from stage events. There is no lifecycle column.

A document stays visible at every stage it reached, including when it is also
a duplicate. Pending-review duplicate links are their own line and are not
counted as confirmed duplicates.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from src.models.enums import Stage, StageStatus
from src.models.stage_event import StageEvent

_ORDER: tuple[str, ...] = (
    Stage.import_.value,
    Stage.normalize.value,
    Stage.dedupe.value,
    Stage.prefilter.value,
    Stage.relevance.value,
    Stage.extract.value,
    Stage.validate.value,
)


def build_funnel(
    events: Iterable[StageEvent],
    duplicate_links: Iterable[Mapping[str, str]] | None = None,
) -> dict[str, object]:
    """Count distinct documents per stage from the events they actually have."""
    reached: dict[str, set[str]] = defaultdict(set)
    technical_failures = 0
    for event in events:
        if event.target_id:
            reached[event.stage.value].add(event.target_id)
        if event.status in {StageStatus.failed, StageStatus.unavailable}:
            technical_failures += 1
    confirmed = 0
    pending = 0
    for link in duplicate_links or ():
        state = link.get("review_state")
        if state == "confirmed":
            confirmed += 1
        elif state == "pending_review":
            pending += 1
    stages = [
        {"stage": name, "documents": len(reached.get(name, set()))}
        for name in _ORDER
        if name in reached
    ]
    return {
        "stages": stages,
        "confirmed_duplicates": confirmed,
        "pending_review_duplicates": pending,
        "technical_failures": technical_failures,
        "documents_by_stage": {name: sorted(ids) for name, ids in sorted(reached.items())},
    }
