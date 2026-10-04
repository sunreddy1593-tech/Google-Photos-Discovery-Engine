"""Versioned assignment. Names come from a reviewed taxonomy, never from code.

``0-unassigned`` produces no rows. ``other`` and ``uncertain`` stay available
once a reviewed version exists. ``established`` is computed from the rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from src.core.ids import assignment_fingerprint
from src.models.cluster_assignment import ClusterAssignment
from src.models.enums import AssignmentMethod

PERMANENT_CLUSTERS: frozenset[str] = frozenset({"other", "uncertain"})


def is_established(document_ids: Iterable[str], source_types: Iterable[str]) -> bool:
    """True only at five independent documents and two source types."""
    return len(set(document_ids)) >= 5 and len(set(source_types)) >= 2


def assign_cases(
    cases: Iterable[Mapping[str, object]],
    *,
    taxonomy_version: str,
    clusters: list[Mapping[str, object]] | None = None,
    assigned_at: datetime,
    schema_version: str = "1.0.0",
    prior: Iterable[ClusterAssignment] | None = None,
) -> list[ClusterAssignment]:
    """Append assignments for one taxonomy version. Prior rows are kept.

    A cluster definition may list ``case_ids``. Cases with no listing become
    ``uncertain``. This function does not invent a name from the summary text.
    """
    kept = list(prior or ())
    if taxonomy_version == "0-unassigned" or not clusters:
        return kept
    named = {
        str(case_id): str(cluster["cluster_id"])
        for cluster in clusters
        if cluster.get("cluster_id") not in PERMANENT_CLUSTERS
        for case_id in cluster.get("case_ids") or ()
    }
    fresh: list[ClusterAssignment] = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        if not case_id:
            continue
        cluster_id = named.get(case_id, "uncertain")
        content = str(case.get("content_hash") or case_id)
        fresh.append(
            ClusterAssignment(
                case_id=case_id,
                taxonomy_version=taxonomy_version,
                cluster_id=cluster_id,
                confidence=None,
                method=AssignmentMethod.rules,
                model_name=None,
                prompt_version=None,
                assignment_fingerprint=assignment_fingerprint(
                    "rules",
                    "taxonomy/unassigned",
                    schema_version,
                    taxonomy_version,
                    content,
                ),
                assigned_at=assigned_at,
            )
        )
    return kept + fresh
