"""Synthetic milestone audit tests. No provider or research-source reads."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import audit_m1
from src.models.enums import ValidationState
from tests.synthetic import DOC_ID, RAW_TEXT_AUDIT, case_scalar_spans, make_case


def _junit(path: Path, *, failures: int = 0) -> Path:
    path.write_text(
        f'<testsuites><testsuite tests="4" failures="{failures}" errors="0" skipped="0">'
        + "".join(f'<testcase classname="tests.{name}" name="synthetic" />' for name in
                  ("test_evidence", "test_evidence_map", "test_extraction_development", "test_models"))
        + "</testsuite></testsuites>", encoding="utf-8",
    )
    return path


def _write(path: Path, payload, *, rows: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in payload) if rows else json.dumps(payload),
        encoding="utf-8",
    )


@pytest.fixture
def saved_run(tmp_path, monkeypatch):
    run = tmp_path / "run"
    pack = tmp_path / "annotation" / "approved"
    chosen = {DOC_ID, *(f"synthetic-{i}" for i in range(29))}
    monkeypatch.setattr(audit_m1, "development_ids", lambda: tuple(chosen))
    monkeypatch.setattr(audit_m1, "holdout_ids", lambda: ("holdout-closed",))
    monkeypatch.setattr(audit_m1, "validate_pack", lambda *args: SimpleNamespace(errors=(), pending=False, documents=1, reviews=1))
    imported = tmp_path / "import.json"
    split = tmp_path / "split.csv"
    _write(imported, {"accepted_rows": [{"doc_id": doc, "source_item_id": doc} for doc in chosen], "rows_accepted": 30, "workbook_sha256": "a" * 64})
    split.write_text("synthetic split", encoding="utf-8")
    monkeypatch.setattr(audit_m1, "IMPORT_REPORT", imported)
    monkeypatch.setattr(audit_m1, "SPLIT", split)
    sources = []
    for stage in ("normalize", "dedupe", "prefilter", "relevance"):
        path = tmp_path / f"{stage}.jsonl"
        _write(path, [{"target_id": doc, "stage": stage, "status": "succeeded"} for doc in chosen], rows=True)
        sources.append((path, frozenset({stage})))
    monkeypatch.setattr(audit_m1, "FUNNEL_SOURCES", tuple(sources))
    _write(run / "extraction_inputs.jsonl", [{"doc_id": doc, "eligible": True} for doc in chosen], rows=True)
    case = make_case(validation_state=ValidationState.valid)
    _write(run / "retrieval_cases.jsonl", [case.model_dump(mode="json")], rows=True)
    spans = [s.model_dump(mode="json") for s in (*case.all_evidence_spans, *case_scalar_spans())]
    _write(run / "evidence_spans.jsonl", spans, rows=True)
    _write(run / "span_validations.jsonl", [{**s, "ok": True} for s in spans], rows=True)
    _write(run / "stage_events.jsonl", [{"target_id": doc, "stage": "extract", "status": "succeeded", "detail": {"case_count": int(doc == DOC_ID)}} for doc in chosen], rows=True)
    _write(run / "stage_funnel.json", {"documents": 30, "analysis_spans": len(case.all_evidence_spans), "stages": {stage: {"succeeded": 30} for stage in ("normalize", "dedupe", "prefilter", "relevance", "extract")}})
    _write(run / "run_manifest.json", {"run_id": "synthetic", "cache": {"provider_calls": 0, "hits": 30}})
    _write(pack.parent / "selection.json", {"reserved_development_doc_ids": sorted(chosen - {DOC_ID})})
    _write(pack / "manifest.json", {"documents": [{"doc_id": DOC_ID, "gold_split": "dev"}]})
    _write(pack / "review_policy.json", {"role": "synthetic_test"})
    _write(pack / "packets" / f"{DOC_ID}.json", {"doc_id": DOC_ID, "gold_split": "dev", "phase4_split": "development", "source_text": RAW_TEXT_AUDIT})
    return run, pack, _junit(tmp_path / "tests.xml")


def test_audit_complete_requires_full_union_and_retained_verdicts(saved_run):
    report = audit_m1.build_audit(*saved_run)
    assert report["status"] == "complete"
    assert report["extraction"]["analysis_spans"] == 5
    assert report["extraction"]["historical_inline_only_count"] == 2
    assert report["extraction"]["fresh_development_source_checks"] == 5
    assert report["holdout_source_text_loaded"] is False
    assert report["provider_calls_this_audit"] == 0


def test_audit_incomplete_when_a_verdict_is_missing(saved_run):
    run, pack, tests = saved_run
    rows = audit_m1._rows(run / "span_validations.jsonl")
    _write(run / "span_validations.jsonl", rows[:-1], rows=True)
    report = audit_m1.build_audit(run, pack, tests)
    assert report["status"] == "incomplete"
    assert report["extraction"]["missing_retained_valid_verdicts"] == 1


def test_audit_incomplete_when_tests_fail(saved_run):
    run, pack, tests = saved_run
    _junit(tests, failures=1)
    assert audit_m1.build_audit(run, pack, tests)["status"] == "incomplete"


def test_audit_refuses_reserved_packet_before_source_read(saved_run):
    run, pack, tests = saved_run
    _write(pack / "manifest.json", {"documents": [{"doc_id": "synthetic-0", "gold_split": "dev"}]})
    with pytest.raises(ValueError, match="holdout"):
        audit_m1.build_audit(run, pack, tests)


def test_audit_preserves_occupied_output(tmp_path, monkeypatch):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    monkeypatch.setattr(audit_m1, "build_audit", lambda *a: pytest.fail("must refuse before audit"))
    assert audit_m1.main(["--test-result", "missing.xml", "--out", str(target)]) == 2
    assert sentinel.read_text(encoding="utf-8") == "original"
