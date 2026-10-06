"""Human-reviewed n8n reference and the automated comparison built against it.

Every fixture is synthetic or an already-saved local export. No test makes a
request, imports an integration module, or reads frozen holdout text.
"""

from __future__ import annotations

import ast
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.core.ids import doc_id
from src.core.versions import REFERENCE_STANDARD_VERSION, version_summary
from src.export.build import build_submission
from src.export.reference_standard import (
    AUTOMATED_LABEL,
    AUTOMATED_NOTE,
    VERDICT_ELIGIBLE,
    VERDICT_FAILED,
    VERDICT_FLAGGED,
    VERDICT_REFERENCE_OVERLAP,
    VERDICT_UNVERIFIABLE,
    assess_case,
    assess_dataset,
    assessment_identity,
    automated_comparison,
    build_standard_payload,
    counts,
    load_standard_snapshot,
    publish_standard_snapshot,
    reference_doc_index,
)
from src.export.reference_standard_build import (
    build_automated_snapshot,
    discover_scheduled_datasets,
    refresh_after_scheduled_run,
)
from src.export.reviewed_reference import (
    HUMAN_REVIEWED_LABEL,
    N8N_COLUMNS,
    REFERENCE_VERSION,
    ReviewedReferenceError,
    build_reviewed_reference,
    load_reviewed_reference,
    reviewed_reference_comparison,
    verify_inputs,
)
from src.export.scheduled_status import read_snapshot_version
from src.pipeline import scheduled_run
from tests.test_submission_export import HOLDOUT_TEXT, _fixture

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP = PROJECT_ROOT / "app.py"
REAL_REFERENCE = PROJECT_ROOT / "data" / "exports" / "reference" / "n8n-reviewed-reference-01"
APPROVAL = {
    "owner": "Sunayana",
    "statement": "Synthetic approval statement for the test reference.",
    "given_in": "test",
    "recorded_on": "2026-10-05",
}
ROWS = (
    {
        "url": "https://support.google.com/photos/thread/1001",
        "title": "Cannot find a screenshot from 2020",
        "is_retrieval_problem": "TRUE",
        "photo_type": "screenshot",
        "intent": "practical_info",
        "cues_remembered": "september 2020",
        "cues_forgotten": "exact date",
        "query_tried": "2020",
        "failure_stage": "expression",
        "workaround": "",
        "key_quote": "Cannot find a screenshot from 2020",
        "summary": "User cannot find a screenshot.",
        "scraped_at": "2026-10-03T13:46:40.758Z",
    },
    {
        "url": "https://support.google.com/photos/thread/1002",
        "title": "Backup stuck",
        "is_retrieval_problem": "FALSE",
        "photo_type": "unknown",
        "intent": "unknown",
        "cues_remembered": "",
        "cues_forgotten": "",
        "query_tried": "",
        "failure_stage": "not_applicable",
        "workaround": "",
        "key_quote": "",
        "summary": "Backup problem, not retrieval.",
        "scraped_at": "2026-10-03T13:47:40.758Z",
    },
    {
        "url": "https://support.google.com/photos/thread/1003",
        "title": "Where is the video of my dog",
        "is_retrieval_problem": "TRUE",
        "photo_type": "pet_video",
        "intent": "nostalgia",
        "cues_remembered": "dog; last winter",
        "cues_forgotten": "exact location",
        "query_tried": "dog",
        "failure_stage": "understanding",
        "workaround": "scrolled",
        "key_quote": "I know it exists but search shows nothing",
        "summary": "",
        "scraped_at": "2026-10-03T13:48:40.758Z",
    },
)


def _csv(path: Path, rows: tuple[dict[str, str], ...] = ROWS) -> Path:
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(N8N_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({"source": "google_photos_community", **row})
    return path


def _reference(tmp_path: Path, rows: tuple[dict[str, str], ...] = ROWS, expected: int | None = None) -> Path:
    destination = tmp_path / "reference"
    build_reviewed_reference(
        _csv(tmp_path / "insights.csv", rows),
        destination,
        approval=APPROVAL,
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        expected_count=expected if expected is not None else len(rows),
        root=tmp_path,
    )
    return destination


def _card(**overrides: object) -> dict:
    excerpt = "I cannot find the birthday photo from last summer because my phone broke and I need it for a card."
    quote = "cannot find the birthday photo"
    start = excerpt.index(quote)
    card = {
        "kind": "case",
        "doc_id": "doc-1",
        "case_id": "doc-1#c01",
        "source_platform": "reddit",
        "source_url": "https://example.com/doc-1",
        "model_scope_class": "core_incomplete_recall",
        "automatically_valid": True,
        "semantically_approved": False,
        "excerpt": excerpt,
        "excerpt_start_char": 10,
        "evidence_spans": [
            {
                "field_name": "target_asset_type",
                "quote": quote,
                "excerpt_start_char": start,
                "excerpt_end_char": start + len(quote),
                "document_start_char": 10 + start,
                "document_end_char": 10 + start + len(quote),
            }
        ],
        "assigned_values": {"target_asset_type": {"value": "photo", "observation": "stated"}},
        "problem_summary": "",
        "rejected_model_text": [],
        "findings": [],
    }
    card.update(overrides)
    return card


def _assess(card: dict, index: dict[str, str] | None = None) -> dict:
    return assess_case(
        card,
        reference_version=REFERENCE_VERSION,
        reference_index=index or {},
        pins={"relevance_prompt": "relevance/v5", "extraction_prompt": "extract/v2", "model": "m", "schema_version": "1.0.0"},
        dataset_id="ds",
        run_id="run",
    )


# --------------------------------------------------------------------------- #
# Reviewed reference: identity, immutability, mappings, explicit unknowns
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def test_reference_records_keep_identity_and_refuse_overwrite(tmp_path: Path) -> None:
    destination = _reference(tmp_path)
    loaded = load_reviewed_reference(destination)
    assert loaded["ok"], loaded["message"]
    assert loaded["reference_version"] == REFERENCE_VERSION == REFERENCE_STANDARD_VERSION
    ids = [row["reference_record_id"] for row in loaded["records"]]
    assert ids == [f"{REFERENCE_VERSION}#1001", f"{REFERENCE_VERSION}#1002", f"{REFERENCE_VERSION}#1003"]
    first = loaded["records"][0]
    assert first["label"] == HUMAN_REVIEWED_LABEL
    assert first["source_url"] == ROWS[0]["url"]
    assert first["expected_doc_id"] == doc_id("google_support", source_item_id="1001")
    assert first["n8n_fields"]["title"] == ROWS[0]["title"]
    assert first["review"]["human_reviewed"] is True
    assert first["review"]["review_date"] == "not stated by the owner"
    metadata = loaded["metadata"]
    assert metadata["approval"]["extends_to_future_records"] is False
    assert metadata["count_matches_owner_statement"] is True
    assert set(metadata["input_sha256"]) == {"insights.csv"}
    assert verify_inputs(metadata, tmp_path)["insights.csv"] == "unchanged"

    with pytest.raises(ReviewedReferenceError):
        build_reviewed_reference(
            tmp_path / "insights.csv",
            destination,
            approval=APPROVAL,
            created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            expected_count=3,
            root=tmp_path,
        )
    records = destination / "records.jsonl"
    lines = records.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    assert tampered["mapped"]["reviewed_relevance"] == "retrieval_problem"
    tampered["mapped"]["reviewed_relevance"] = "not_retrieval_problem"
    lines[0] = json.dumps(tampered, ensure_ascii=False)
    records.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert load_reviewed_reference(destination)["ok"] is False


@pytest.mark.synthetic
def test_reference_reports_count_discrepancy_and_duplicates(tmp_path: Path) -> None:
    destination = _reference(tmp_path, expected=48)
    metadata = load_reviewed_reference(destination)["metadata"]
    assert metadata["records"] == 3
    assert metadata["count_matches_owner_statement"] is False
    assert "48" in metadata["count_discrepancy"] and "3" in metadata["count_discrepancy"]
    duplicate = (ROWS[0], ROWS[0])
    with pytest.raises(ReviewedReferenceError):
        build_reviewed_reference(
            _csv(tmp_path / "dup.csv", duplicate),
            tmp_path / "dup-reference",
            approval=APPROVAL,
            created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            expected_count=2,
            root=tmp_path,
        )
    assert not (tmp_path / "dup-reference").exists()


@pytest.mark.synthetic
def test_reference_mappings_are_explicit_and_unknowns_stay_unknown(tmp_path: Path) -> None:
    loaded = load_reviewed_reference(_reference(tmp_path))
    first, second, third = loaded["records"]
    assert first["mapped"]["reviewed_relevance"] == "retrieval_problem"
    assert second["mapped"]["reviewed_relevance"] == "not_retrieval_problem"
    assert first["mapped"]["target_asset_type"] == "screenshot"
    assert third["mapped"]["target_asset_type"] is None
    assert third["mapped"]["target_asset_type_observation"] == "unmapped_n8n_value"
    assert third["preserved_n8n"]["photo_type"] == "pet_video"
    assert third["preserved_n8n"]["cues_remembered"] == ["dog", "last winter"]
    assert "scope_class_core_or_adjacent" in first["unavailable"]
    assert "severity" in first["unavailable"]
    assert first["quote_check"]["verified_against_original_text"] == "unavailable"
    assert first["quote_check"]["equals_title"] is True
    assert third["quote_check"]["within_title"] is False
    statuses = {row["n8n_field"]: row["status"] for row in loaded["metadata"]["field_mappings"]}
    assert statuses["is_retrieval_problem"] == "supported"
    assert statuses["photo_type"] == "partial"
    assert statuses["cues_remembered"] == "unsupported"
    verification = loaded["metadata"]["verification"]
    assert verification["quotes_verified_against_original_text"] == 0
    assert verification["quote_verification_unavailable"] == 3
    analysis = reviewed_reference_comparison(loaded["records"])
    relevance = next(item for item in analysis["dimensions"] if item["field"] == "reviewed_relevance")
    assert {row["value"]: row["count"] for row in relevance["rows"]} == {"retrieval_problem": 2, "not_retrieval_problem": 1}
    assert analysis["label"] == HUMAN_REVIEWED_LABEL


def test_saved_48_record_reference_verifies_against_its_inputs() -> None:
    loaded = load_reviewed_reference(REAL_REFERENCE)
    assert loaded["ok"], loaded["message"]
    assert len(loaded["records"]) == 48
    metadata = loaded["metadata"]
    assert metadata["records"] == 48 and metadata["distinct_thread_ids"] == 48
    assert metadata["count_matches_owner_statement"] is True
    assert metadata["primary_input"] == "n8n/discovery_sheet_template - insights.csv"
    assert all(state == "unchanged" for state in verify_inputs(metadata, PROJECT_ROOT).values())
    assert metadata["cross_check"]["snapshot_rows_not_covered_by_review"] == ["106429666", "471259711", "471279651"]
    assert "holdout" not in json.dumps(metadata["input_sha256"])
    assert version_summary()["reference_standard_version"] == REFERENCE_STANDARD_VERSION


# --------------------------------------------------------------------------- #
# Automated assessment
# --------------------------------------------------------------------------- #


def test_assessment_identity_changes_with_reference_and_prompt_versions() -> None:
    base = dict(
        reference_version="n8n-reviewed-reference/01",
        relevance_prompt="relevance/v5",
        extraction_prompt="extract/v2",
        schema_version="1.0.0",
        model="m",
        case_id="c",
        dataset_version="d/r",
    )
    first = assessment_identity(**base)
    assert first == assessment_identity(**base)
    assert first != assessment_identity(**{**base, "reference_version": "n8n-reviewed-reference/02"})
    assert first != assessment_identity(**{**base, "extraction_prompt": "extract/v3"})
    assert first != assessment_identity(**{**base, "relevance_prompt": "relevance/v6"})


def test_eligible_case_enters_without_human_approval() -> None:
    row = _assess(_card())
    assert row["verdict"] == VERDICT_ELIGIBLE
    assert row["eligible_for_automated_comparison"] is True
    assert row["semantically_approved"] is False
    assert row["human_reviewed"] is False
    assert row["label"] == AUTOMATED_LABEL
    assert row["versions"]["reference_version"] == REFERENCE_VERSION
    assert row["versions"]["extraction_prompt"] == "extract/v2"
    assert row["mapped_to_reference"]["reviewed_relevance_equivalent"] == "retrieval_problem"


def test_recorded_semantic_approval_is_not_inherited() -> None:
    row = _assess(_card(semantically_approved=True))
    assert row["semantically_approved"] is False
    assert row["recorded_semantic_approval_elsewhere"] is True
    payload = build_standard_payload(standard={"ok": True, "reference_version": REFERENCE_VERSION, "metadata": {"records": 3}}, datasets=[{"dataset_id": "ds", "run_id": "r", "assessments": [row], "duplicates_skipped": 0, "relevance_decisions": {}}], pins={}, built_at="t")
    assert payload["included"][0]["semantically_approved"] is False
    assert payload["semantically_approved_by_this_layer"] == 0
    assert payload["counts"]["cases_with_recorded_semantic_approval_elsewhere"] == 1


@pytest.mark.parametrize(
    ("overrides", "verdict", "fragment"),
    [
        ({"assigned_values": {"retrieval_trigger": {"value": "search backup", "observation": "stated"}}}, VERDICT_FLAGGED, "retrieval_trigger"),
        ({"assigned_values": {"impact_signals": {"value": ["frustration"], "observation": "stated"}}}, VERDICT_FLAGGED, "impact or severity"),
        ({"assigned_values": {"severity": {"value": "high", "observation": "stated"}}}, VERDICT_FLAGGED, "impact or severity"),
        ({"problem_summary": "cannot find the photo"}, VERDICT_FLAGGED, "problem_summary"),
        ({"rejected_model_text": [{"quote": "spliced text"}]}, VERDICT_FLAGGED, "spliced"),
        ({"findings": [{"field": "target_asset_type", "risk": "unsupported_value"}]}, VERDICT_FLAGGED, "recorded finding"),
        ({"source_url": ""}, VERDICT_FLAGGED, "source link"),
        ({"model_scope_class": "out_of_scope"}, VERDICT_FLAGGED, "not core or adjacent"),
        ({"kind": "attempt", "attempt_kind": "failed", "automatically_valid": False}, VERDICT_FAILED, "not an extraction case"),
        ({"automatically_valid": False}, VERDICT_FAILED, "evidence gate"),
        ({"excerpt": "", "evidence_spans": []}, VERDICT_UNVERIFIABLE, "cannot be verified"),
    ],
)
def test_unsupported_fields_and_invalid_evidence_are_flagged(overrides: dict, verdict: str, fragment: str) -> None:
    row = _assess(_card(**overrides))
    assert row["verdict"] == verdict
    assert any(fragment in reason for reason in row["reasons"]), row["reasons"]
    assert row["eligible_for_automated_comparison"] is False


def test_altered_quotes_and_bad_offsets_are_flagged() -> None:
    card = _card()
    span = dict(card["evidence_spans"][0])
    span["quote"] = "cannot find the holiday photo"
    row = _assess(_card(evidence_spans=[span]))
    assert row["verdict"] == VERDICT_FLAGGED
    assert row["checks"]["offsets_valid"] is False
    assert row["checks"]["quotes_continuous_in_source"] is False
    shifted = dict(card["evidence_spans"][0])
    shifted["excerpt_end_char"] = shifted["excerpt_end_char"] + 3
    row = _assess(_card(evidence_spans=[shifted]))
    assert row["verdict"] == VERDICT_FLAGGED
    assert row["checks"]["offsets_valid"] is False
    wrong_doc = dict(card["evidence_spans"][0])
    wrong_doc["document_start_char"] = 999
    assert _assess(_card(evidence_spans=[wrong_doc]))["checks"]["offsets_valid"] is False
    assert _assess(_card(evidence_spans=[]))["verdict"] == VERDICT_FLAGGED


def test_reviewed_reference_documents_stay_out_of_the_automated_view(tmp_path: Path) -> None:
    loaded = load_reviewed_reference(_reference(tmp_path))
    index = reference_doc_index(loaded["records"])
    overlap = _assess(_card(doc_id=loaded["records"][0]["expected_doc_id"]), index)
    assert overlap["verdict"] == VERDICT_REFERENCE_OVERLAP
    by_url = _assess(_card(source_url=ROWS[1]["url"]), index)
    assert by_url["verdict"] == VERDICT_REFERENCE_OVERLAP
    assert _assess(_card(), index)["verdict"] == VERDICT_ELIGIBLE


def test_dataset_assessment_separates_scopes_skips_duplicates_and_counts() -> None:
    seen: set[str] = set()
    cards = [
        _card(),
        _card(case_id="doc-2#c01", doc_id="doc-2", model_scope_class="adjacent_known_item_retrieval"),
        _card(),
        {"kind": "relevance", "doc_id": "r1", "model_scope_class": "out_of_scope", "automatically_valid": True},
        {"kind": "relevance", "doc_id": "r2", "model_scope_class": "core_incomplete_recall", "automatically_valid": True},
        {"kind": "relevance", "doc_id": "r3", "model_scope_class": "core_incomplete_recall", "automatically_valid": False},
    ]
    kwargs = dict(reference_version=REFERENCE_VERSION, reference_index={}, pins={}, dataset_id="ds", run_id="r")
    dataset = assess_dataset(cards, seen_case_ids=seen, **kwargs)
    assert dataset["duplicates_skipped"] == 1
    assert len(dataset["assessments"]) == 2
    assert dataset["relevance_decisions"] == {"core_incomplete_recall": 1, "adjacent_known_item_retrieval": 0, "out_of_scope": 1, "invalid_or_failed": 1}
    again = assess_dataset([_card()], seen_case_ids=seen, **kwargs)
    assert again["duplicates_skipped"] == 1 and again["assessments"] == []
    comparison = automated_comparison(dataset["assessments"])
    assert comparison["core"]["case_count"] == 1 and comparison["adjacent"]["case_count"] == 1
    assert comparison["core"]["case_ids"] == ["doc-1#c01"]
    assert comparison["adjacent"]["case_ids"] == ["doc-2#c01"]
    assert comparison["reviewed_relevance_equivalent"]["retrieval_problem"] == 2
    totals = counts(reference_records=3, datasets=[dataset, again])
    assert totals["human_reviewed_records"] == 3
    assert totals["eligible_cases"] == 2 and totals["duplicates_skipped"] == 2
    assert totals["semantically_approved_by_this_layer"] == 0


def test_empty_assessment_has_zero_counts_and_no_buckets() -> None:
    payload = build_standard_payload(standard={"ok": True, "reference_version": REFERENCE_VERSION, "metadata": {"records": 48}}, datasets=[], pins={}, built_at="t")
    assert payload["counts"]["human_reviewed_records"] == 48
    assert payload["counts"]["cases_assessed"] == 0
    assert payload["comparison"]["case_count"] == 0
    assert payload["comparison"]["core"]["case_count"] == 0
    assert payload["included"] == [] and payload["excluded"] == []
    assert payload["label"] == AUTOMATED_LABEL and payload["note"] == AUTOMATED_NOTE
    assert payload["snapshot_version"]


# --------------------------------------------------------------------------- #
# Snapshot build and publication
# --------------------------------------------------------------------------- #


def _prepared_export(tmp_path: Path) -> Path:
    destination = tmp_path / "prepared"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    return destination


@pytest.mark.synthetic
def test_snapshot_build_is_offline_atomic_and_version_aware(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    prepared = _prepared_export(tmp_path)
    snapshot_root = tmp_path / "snapshot"
    before = {path: path.read_bytes() for path in reference.rglob("*") if path.is_file()}
    first = build_automated_snapshot(
        tmp_path,
        reference_dir=reference,
        snapshot_root=snapshot_root,
        work_dir=tmp_path / "work",
        scheduled_root=tmp_path / "no-scheduled-runs",
        prepared_exports=(prepared,),
        frozen_split=tmp_path / "split.csv",
        pins={"relevance_prompt": "relevance/v5", "extraction_prompt": "extract/v2", "model": "m"},
        now=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    assert first["ok"] and first["published"], first
    assert {path: path.read_bytes() for path in before} == before
    version = first["snapshot_version"]
    assert read_snapshot_version(snapshot_root) == version
    snapshot = load_standard_snapshot(snapshot_root)
    assert snapshot["ok"] and snapshot["label"] == AUTOMATED_LABEL
    assert snapshot["reference_version"] == REFERENCE_VERSION
    assert snapshot["counts"]["human_reviewed_records"] == 3
    assert snapshot["counts"]["automatically_valid_cases"] == 1
    assert snapshot["counts"]["eligible_cases"] == 0
    flagged = next(row for row in snapshot["excluded"] if row["case_id"] == "dev-a#c01")
    assert flagged["verdict"] == VERDICT_FLAGGED
    assert flagged["versions"]["extraction_prompt"] == "extract/v2"
    assert flagged["semantically_approved"] is False
    text = json.dumps(snapshot)
    assert HOLDOUT_TEXT not in text and "hold-1" not in text
    assert "raw_text" not in text

    second = build_automated_snapshot(
        tmp_path,
        reference_dir=reference,
        snapshot_root=snapshot_root,
        work_dir=tmp_path / "work",
        scheduled_root=tmp_path / "no-scheduled-runs",
        prepared_exports=(prepared,),
        frozen_split=tmp_path / "split.csv",
        pins={"relevance_prompt": "relevance/v5", "extraction_prompt": "extract/v2", "model": "m"},
    )
    assert second["ok"] and second["published"] is False
    assert read_snapshot_version(snapshot_root) == version

    shutil.rmtree(reference)
    failed = build_automated_snapshot(
        tmp_path,
        reference_dir=reference,
        snapshot_root=snapshot_root,
        work_dir=tmp_path / "work",
        scheduled_root=tmp_path / "no-scheduled-runs",
        prepared_exports=(prepared,),
        frozen_split=tmp_path / "split.csv",
    )
    assert failed["ok"] is False and failed["published"] is False
    assert read_snapshot_version(snapshot_root) == version


@pytest.mark.synthetic
def test_failed_publication_keeps_previous_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    first = build_standard_payload(standard={"ok": True, "reference_version": REFERENCE_VERSION, "metadata": {"records": 1}}, datasets=[], pins={"model": "a"}, built_at="t")
    assert publish_standard_snapshot(root, first)["published"]
    broken = build_standard_payload(standard={"ok": True, "reference_version": REFERENCE_VERSION, "metadata": {"records": 1}}, datasets=[], pins={"model": "b"}, built_at="t")
    assert broken["snapshot_version"] != first["snapshot_version"]
    broken["snapshot_version"] = "unsafe/version"
    with pytest.raises(Exception):
        publish_standard_snapshot(root, broken)
    assert read_snapshot_version(root) == first["snapshot_version"]
    assert load_standard_snapshot(root)["pins"] == {"model": "a"}
    stripped = build_standard_payload(standard={"ok": True, "reference_version": REFERENCE_VERSION, "metadata": {"records": 1}}, datasets=[], pins={"model": "c", "api_key": "sk-not-real"}, built_at="t")
    assert publish_standard_snapshot(root, stripped)["published"]
    assert "api_key" not in load_standard_snapshot(root)["pins"]


@pytest.mark.synthetic
def test_scheduled_sub_batches_are_discovered_and_exported_through_the_builder(tmp_path: Path) -> None:
    _fixture(tmp_path)
    root = tmp_path
    sub = root / "data" / "interim" / "scheduled-runs" / "run-x" / "sub-01"
    (sub / "normalize").mkdir(parents=True)
    (sub / "relevance").mkdir()
    shutil.copy(root / "collected.jsonl", sub / "collected_documents.jsonl")
    shutil.copy(root / "derived.jsonl", sub / "normalize" / "documents_derived.jsonl")
    shutil.copy(root / "links.jsonl", sub / "normalize" / "duplicate_links.jsonl")
    shutil.copy(root / "relevance.jsonl", sub / "relevance" / "relevance_decisions.jsonl")
    shutil.copytree(root / "extract", sub / "extract")
    (sub / "extract" / "run_manifest.json").write_text(json.dumps({"run_id": "ext-1"}), encoding="utf-8")
    (root / "data" / "interim" / "scheduled-runs" / "run-x" / "parent_manifest.json").write_text(
        json.dumps({"run_id": "run-x", "pins": {"model": "pinned-model", "relevance_prompt": "relevance/v5", "extraction_prompt": "extract/v2"}}),
        encoding="utf-8",
    )
    empty_sub = root / "data" / "interim" / "scheduled-runs" / "run-x" / "sub-02"
    empty_sub.mkdir()
    specs = discover_scheduled_datasets(root / "data" / "interim" / "scheduled-runs", root)
    assert [spec["dataset_id"] for spec in specs] == ["scheduled-run-x-sub-01"]
    assert specs[0]["extraction_run"] == {"run_id": "ext-1", "path": "data/interim/scheduled-runs/run-x/sub-01/extract"}
    assert specs[0]["split_policy"] == "outside_frozen_split"

    outside_split = root / "empty-split.csv"
    outside_split.write_text("doc_id,split,stratum,split_version\nhold-1,holdout,core_incomplete_recall,v1\n", encoding="utf-8")
    outcome = build_automated_snapshot(
        root,
        reference_dir=_reference(tmp_path),
        snapshot_root=root / "snapshot",
        work_dir=root / "work",
        prepared_exports=(),
        frozen_split=outside_split,
    )
    assert outcome["ok"] and outcome["published"], outcome
    snapshot = load_standard_snapshot(root / "snapshot")
    assert [source["dataset_id"] for source in snapshot["sources"]] == ["scheduled-run-x-sub-01"]
    flagged = next(row for row in snapshot["excluded"] if row["case_id"] == "dev-a#c01")
    assert flagged["versions"]["model"] == "pinned-model"
    assert flagged["run_id"] == "ext-1"
    assert HOLDOUT_TEXT not in json.dumps(snapshot)


# --------------------------------------------------------------------------- #
# Scheduler: budgets unchanged, refresh is best effort, no extra model calls
# --------------------------------------------------------------------------- #


def test_scheduler_budgets_and_pins_are_unchanged() -> None:
    assert scheduled_run.TARGET_DOCUMENTS == 50
    assert scheduled_run.SUB_BATCH_CAPS == (20, 20, 10)
    assert scheduled_run.MAX_DOCUMENTS == 20
    assert scheduled_run.COLLECTION_REQUESTS_PER_RUN == 20
    assert scheduled_run.MODEL_ATTEMPTS_PER_RUN == 100
    assert scheduled_run.COLLECTION_REQUESTS_PER_DAY == 60
    assert scheduled_run.MODEL_ATTEMPTS_PER_DAY == 300
    source = (PROJECT_ROOT / "src" / "pipeline" / "scheduled_run.py").read_text(encoding="utf-8")
    assert source.count("run_extraction(") == 1
    assert "review call" not in source.lower()


@pytest.mark.synthetic
def test_scheduler_records_refresh_outcome_without_failing_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_scheduled_run import _paths, _settings

    paths = _paths(tmp_path)
    calls: list[Path] = []

    def boom(root: Path) -> dict:
        calls.append(root)
        raise RuntimeError("refresh exploded")

    now = datetime(2026, 10, 5, 8, 0, tzinfo=scheduled_run.SCHEDULE_ZONE)
    dry = scheduled_run.run_scheduled(paths, dry_run=True, now=now, settings=_settings(), comparison_refresh=boom)
    assert dry.status == "dry_run" and calls == []
    report = scheduled_run.run_scheduled(
        paths,
        dry_run=False,
        now=now,
        settings=_settings(),
        collector=lambda **_: [],
        process_batch=lambda **_: {"stop": False, "failures": [], "unprocessed_doc_ids": []},
        pid=4242,
        pid_alive=lambda _pid: False,
        comparison_refresh=boom,
    )
    assert calls == [paths.project_root]
    assert report.status in {"partial", "completed"}
    assert report.automated_comparison["ok"] is False
    assert "RuntimeError" in report.automated_comparison["message"]
    assert "automated comparison" in scheduled_run.format_schedule_report(report)
    default = refresh_after_scheduled_run(tmp_path / "no-project")
    assert default["ok"] is False and default["published"] is False


# --------------------------------------------------------------------------- #
# Boundaries: no n8n or spreadsheet access, no holdout reads
# --------------------------------------------------------------------------- #


def test_reference_modules_do_not_touch_integrations_or_network() -> None:
    files = [
        PROJECT_ROOT / "src" / "export" / "reviewed_reference.py",
        PROJECT_ROOT / "src" / "export" / "reference_standard.py",
        PROJECT_ROOT / "src" / "export" / "reference_standard_build.py",
        PROJECT_ROOT / "scripts" / "build_reviewed_reference.py",
        PROJECT_ROOT / "scripts" / "build_reference_standard_snapshot.py",
    ]
    banned_modules = {"requests", "urllib", "httpx", "aiohttp", "gspread", "googleapiclient", "community_insights", "socket"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
        assert not imported & banned_modules, (path.name, imported & banned_modules)
        assert not any(module.startswith(("src.collect", "src.llm", "src.relevance", "src.extract")) for module in imported), path.name
        source = path.read_text(encoding="utf-8")
        for marker in ("n8n/workflows", "sheets.googleapis", "os.environ", "holdout-review"):
            assert marker not in source, (path.name, marker)
        for call in ("urlopen(", "requests.", ".post(", ".get(\"http", "subprocess"):
            assert call not in source, (path.name, call)


# --------------------------------------------------------------------------- #
# Streamlit: two labelled views, counts, refresh, versioned cache
# --------------------------------------------------------------------------- #


def _launch_standard(tmp_path: Path, export_dir: Path, reference: Path, snapshot_root: Path) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.session_state["export_dir"] = str(export_dir)
    app.session_state["reference_standard_dir"] = str(reference)
    app.session_state["reference_standard_snapshot_root"] = str(snapshot_root)
    app.session_state["scheduled_snapshot_root"] = str(tmp_path / "no-scheduled")
    app.session_state["scheduled_autorefresh"] = False
    app.session_state["section"] = "Reference standard"
    return app.run()


@pytest.mark.synthetic
def test_automated_view_displays_named_comparison_buckets(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    prepared = _prepared_export(tmp_path)
    root = tmp_path / "snapshot"
    payload = {
        "snapshot_version": "bucket-regression",
        "reference_version": REFERENCE_VERSION,
        "counts": {"eligible_cases": 2},
        "comparison": {
            "case_count": 2,
            "core": {"case_count": 1, "dimensions": []},
            "adjacent": {"case_count": 1, "dimensions": []},
        },
        "included": [], "excluded": [],
    }
    publish_standard_snapshot(root, payload)
    app = _launch_standard(tmp_path, prepared, reference, root)
    assert not app.exception
    labels = [expander.label for expander in app.expander]
    assert "Core incomplete recall: 1 case(s)" in labels
    assert "Adjacent known-item retrieval: 1 case(s)" in labels


@pytest.mark.synthetic
def test_app_shows_both_views_with_labels_counts_and_empty_state(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    prepared = _prepared_export(tmp_path)
    snapshot_root = tmp_path / "snapshot"
    app = _launch_standard(tmp_path, prepared, reference, snapshot_root)
    assert not app.exception
    rendered = " ".join(block.value for group in (app.markdown, app.caption, app.info) for block in group)
    assert HUMAN_REVIEWED_LABEL in rendered
    assert AUTOMATED_LABEL in rendered
    assert AUTOMATED_NOTE in rendered
    assert any("No automated comparison snapshot" in block.value for block in app.info)
    assert any(metric.label == "Human-reviewed records" and metric.value == "3" for metric in app.metric)
    assert any(button.key == "refresh_reference_standard" for button in app.button)
    assert "human-approved" not in rendered.replace("not human-approved", "").lower()

    outcome = build_automated_snapshot(
        tmp_path,
        reference_dir=reference,
        snapshot_root=snapshot_root,
        work_dir=tmp_path / "work",
        scheduled_root=tmp_path / "no-scheduled-runs",
        prepared_exports=(prepared,),
        frozen_split=tmp_path / "split.csv",
        pins={"model": "m"},
    )
    assert outcome["published"]
    app = app.run()
    assert not app.exception
    captions = " ".join(block.value for block in app.caption)
    assert outcome["snapshot_version"] in captions
    assert "Semantic approval set by this layer: 0" in captions
    labels = {metric.label: metric.value for metric in app.metric}
    assert labels["Eligible for comparison"] == "0"
    assert labels["Flagged"] == "1"
    assert labels["Failed or incomplete"] == "2"
    assert any("No automatically classified case is eligible" in block.value for block in app.info)
    app.radio(key="reference_standard_show").set_value("Flagged, failed or excluded").run()
    assert not app.exception
    assert any("dev-a#c01" in block.value for block in app.markdown)
    assert any(HOLDOUT_TEXT not in block.value for block in app.markdown)

    app.button(key="refresh_reference_standard").click().run()
    assert not app.exception
