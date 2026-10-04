"""Phase 8 counting rules on synthetic records."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.analyze.funnel import build_funnel
from src.analyze.journeys import build_journeys
from src.analyze.memory_map import build_memory_map
from src.analyze.opportunities import build_opportunities
from src.models.enums import (
    DimensionObservationStatus,
    Stage,
    StageEventTargetType,
    StageStatus,
)
from src.models.stage_event import StageEvent

WHEN = datetime(2026, 10, 4, tzinfo=timezone.utc)


def _event(doc_id: str, stage: Stage, status: StageStatus = StageStatus.succeeded) -> StageEvent:
    return StageEvent(
        event_id=f"{doc_id}-{stage.value}-{status.value}",
        target_type=StageEventTargetType.document,
        target_id=doc_id,
        stage=stage,
        status=status,
        reason_code=None,
        run_id="synthetic",
        occurred_at=WHEN,
    )


@pytest.mark.synthetic
def test_funnel_keeps_a_document_at_every_stage_it_reached() -> None:
    events = [
        _event("doc-a", Stage.import_),
        _event("doc-a", Stage.normalize),
        _event("doc-a", Stage.dedupe),
        _event("doc-a", Stage.extract),
        _event("doc-b", Stage.import_),
    ]
    links = [
        {"review_state": "confirmed", "duplicate_doc_id": "doc-a", "canonical_doc_id": "doc-b"},
        {"review_state": "pending_review", "duplicate_doc_id": "doc-c", "canonical_doc_id": "doc-b"},
    ]
    funnel = build_funnel(events, links)
    by_stage = {row["stage"]: row["documents"] for row in funnel["stages"]}
    assert by_stage["import"] == 2
    assert by_stage["dedupe"] == 1
    assert by_stage["extract"] == 1
    assert funnel["confirmed_duplicates"] == 1
    assert funnel["pending_review_duplicates"] == 1
    reached = funnel["documents_by_stage"]
    assert "doc-a" in reached["dedupe"] and "doc-a" in reached["extract"]


@pytest.mark.synthetic
def test_memory_map_keeps_not_stated_distinct_from_explicitly_none() -> None:
    cases = [
        {
            "technical_state": "ok",
            "remembered_cues": {"observation": "not_stated", "value": []},
            "forgotten_information": {"observation": "explicitly_none", "value": []},
        },
        {
            "technical_state": "provider_error",
            "remembered_cues": {"observation": "stated", "value": [{"value": "person"}]},
            "forgotten_information": {"observation": "stated", "value": [{"value": "time"}]},
        },
    ]
    table = build_memory_map(cases)
    assert table["excluded_technical_failures"] == 1
    assert table["cells"] == [
        {"remembered": "not_stated", "forgotten": "explicitly_none", "cases": 1}
    ]
    assert "not_stated" in table["statuses_used"]
    assert "explicitly_none" in table["statuses_used"]
    for status in table["statuses_used"]:
        DimensionObservationStatus(status)


@pytest.mark.synthetic
def test_journeys_read_observation_status_without_merging_gaps() -> None:
    rows = build_journeys(
        [
            {
                "case_id": "c1",
                "technical_state": "ok",
                "retrieval_trigger": {"observation": "stated", "value": "find the photo"},
                "remembered_cues": {"observation": "not_stated", "value": []},
                "query_strategies": {"observation": "explicitly_none", "value": []},
                "system_responses": {"observation": "not_stated", "value": []},
                "workarounds": {"observation": "not_stated", "value": []},
                "outcome": {"observation": "stated", "value": "not_found"},
                "impact_signals": {"observation": "not_stated", "value": []},
            }
        ]
    )
    assert rows[0]["cue"] == "not_stated"
    assert rows[0]["strategy"] == "explicitly_none"
    assert rows[0]["need"] == "find the photo"


@pytest.mark.synthetic
def test_source_balanced_mean_and_severity_denominator() -> None:
    cases = []
    for index in range(10):
        cases.append(
            {
                "case_id": f"r{index}",
                "doc_id": f"rd{index}",
                "parent_thread_id": "thread-r",
                "author_hash": f"a{index}",
                "source_platform": "reddit",
                "evidence_tier": "direct_user",
                "scope_class": "core_incomplete_recall" if index < 8 else "out_of_scope",
                "technical_state": "ok",
                "severity": 3 if index < 2 else None,
            }
        )
    for index in range(10):
        cases.append(
            {
                "case_id": f"y{index}",
                "doc_id": f"yd{index}",
                "parent_thread_id": f"thread-y{index}",
                "author_hash": f"b{index}",
                "source_platform": "youtube",
                "evidence_tier": "direct_user",
                "scope_class": "core_incomplete_recall" if index == 0 else "out_of_scope",
                "technical_state": "ok",
                "severity": None,
            }
        )
    cases.append(
        {
            "case_id": "editorial",
            "doc_id": "ed",
            "source_platform": "editorial",
            "evidence_tier": "contextual_editorial",
            "scope_class": "core_incomplete_recall",
            "technical_state": "ok",
        }
    )
    report = build_opportunities(cases, scope="core_incomplete_recall")
    assert report["unique_cases"] == 9
    assert report["unique_threads"] == 2
    assert report["excluded_non_direct"] == 1
    assert report["severity_denominator"] == 2
    assert report["severity_nulls"] == 7
    assert report["within_source_shares"]["reddit"] == pytest.approx(0.8)
    assert report["within_source_shares"]["youtube"] == pytest.approx(0.1)
    assert report["source_balanced_mean"] == pytest.approx(0.45)
    assert report["composite_score"] is None
    again = build_opportunities(cases, scope="core_incomplete_recall")
    assert again == report
