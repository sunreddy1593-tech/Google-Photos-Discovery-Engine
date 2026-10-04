"""Separate opportunity components. The composite score stays off.

Counts are cases, documents, threads, and authors. Severity means carry the
number of cases that actually had a severity. Contextual and second-hand
documents are omitted from the direct-user counts and reported beside them.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping


def _direct(case: Mapping[str, object]) -> bool:
    tier = str(case.get("evidence_tier") or "direct_user")
    return tier == "direct_user"


def build_opportunities(
    cases: Iterable[Mapping[str, object]],
    *,
    scope: str | None = None,
    concentration_threshold: float = 0.40,
) -> dict[str, object]:
    """Component table for one scope, or for every scope when ``scope`` is omitted."""
    eligible: list[Mapping[str, object]] = []
    population: dict[str, int] = defaultdict(int)
    excluded_technical = 0
    excluded_tier = 0
    for case in cases:
        if str(case.get("technical_state") or "ok") != "ok":
            excluded_technical += 1
            continue
        if str(case.get("evidence_tier") or "") == "synthetic_test":
            continue
        if not _direct(case):
            excluded_tier += 1
            continue
        source_name = str(case.get("source_platform") or "unknown")
        population[source_name] += 1
        if scope and str(case.get("scope_class") or "") != scope:
            continue
        eligible.append(case)
    by_source: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for case in eligible:
        by_source[str(case.get("source_platform") or "unknown")].append(case)
    total = len(eligible)
    shares = {
        source: (len(rows) / total if total else 0.0)
        for source, rows in sorted(by_source.items())
    }
    within = {
        source: (len(by_source.get(source, [])) / count if count else 0.0)
        for source, count in sorted(population.items())
    }
    balanced = sum(within.values()) / len(within) if within else 0.0
    # Within-source share of this scope is 1 when the table is one scope.
    # The balanced view is the unweighted mean of within-source shares.
    severity_values = [
        int(case["severity"])
        for case in eligible
        if isinstance(case.get("severity"), int)
    ]
    threads = {str(case.get("parent_thread_id") or case.get("doc_id") or "") for case in eligible}
    authors = {str(case["author_hash"]) for case in eligible if case.get("author_hash")}
    documents = {str(case.get("doc_id") or "") for case in eligible}
    over = [
        source
        for source, share in shares.items()
        if share > concentration_threshold
    ]
    return {
        "scope": scope or "all_direct",
        "unique_cases": total,
        "unique_documents": len(documents),
        "unique_threads": len(threads - {""}),
        "unique_authors": len(authors),
        "source_count": len(shares),
        "source_shares": shares,
        "within_source_shares": within,
        "source_balanced_mean": balanced,
        "mean_severity": (
            sum(severity_values) / len(severity_values) if severity_values else None
        ),
        "severity_denominator": len(severity_values),
        "severity_nulls": total - len(severity_values),
        "concentration_disclosure": over,
        "excluded_technical_failures": excluded_technical,
        "excluded_non_direct": excluded_tier,
        "composite_score": None,
    }
