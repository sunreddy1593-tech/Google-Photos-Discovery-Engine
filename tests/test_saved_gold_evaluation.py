"""Synthetic saved-run evaluation. No real corpus, holdout source or network."""

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import evaluate
from src.gold.annotate import AnnotationError
from src.gold.evaluate import evaluate_gold
from src.gold.metrics import multilabel_scores, unsupported_inference
from src.gold.saved_run import load_saved_development
from src.models.enums import ValidationState
from tests.synthetic import DOC_ID, RAW_TEXT_AUDIT, case_scalar_spans, make_case, make_decision
from tests.test_evaluation import _document, _prediction, _write_gold
from src.models.enums import ScopeClass

pytestmark = pytest.mark.synthetic


def _write(path: Path, data, *, rows=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in data) if rows else json.dumps(data), encoding="utf-8")


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    run, pack = tmp_path / "run", tmp_path / "pack"
    relevance, prefilter = tmp_path / "relevance.jsonl", tmp_path / "prefilter.jsonl"
    case = make_case(validation_state=ValidationState.valid)
    _write(run / "retrieval_cases.jsonl", [case.model_dump(mode="json")], rows=True)
    _write(run / "evidence_spans.jsonl", [span.model_dump(mode="json") for span in (*case.all_evidence_spans, *case_scalar_spans())], rows=True)
    _write(run / "extraction_inputs.jsonl", [{"doc_id": DOC_ID, "eligible": True}], rows=True)
    _write(run / "stage_events.jsonl", [{"target_id": DOC_ID, "stage": "extract", "status": "succeeded", "detail": {"case_count": 1}}], rows=True)
    _write(run / "run_manifest.json", {"run_id": "synthetic", "versions": {}})
    _write(relevance, [make_decision(validation_state=ValidationState.valid).model_dump(mode="json")], rows=True)
    _write(prefilter, [{"target_id": DOC_ID, "stage": "prefilter", "status": "succeeded", "detail": {"route": "classify"}}], rows=True)
    _write(pack / "manifest.json", {"documents": [{"doc_id": DOC_ID, "gold_split": "dev", "phase4_split": "development"}]})
    _write(pack / "packets" / f"{DOC_ID}.json", {"doc_id": DOC_ID, "gold_split": "dev", "phase4_split": "development", "source_text": RAW_TEXT_AUDIT})
    return dict(doc_ids={DOC_ID}, run=run, relevance=relevance, pack=pack, prefilter_events=prefilter)


def test_saved_adapter_reuses_full_field_gate_and_stage_routes(saved):
    loaded = load_saved_development(**saved)
    assert len(loaded.extracted_cases) == 1
    assert len(loaded.extracted_cases[0].spans) == 5
    assert loaded.extracted_cases[0].values["remembered_cues"]["value"] == ["approximate_time"]
    assert loaded.predictions[DOC_ID].prefilter_passed is True
    assert loaded.processed_records == 2
    assert loaded.metadata["provider_calls"] == 0
    assert loaded.metadata["holdout_source_text_loaded"] is False


def test_saved_adapter_refuses_holdout_before_packet_read(saved):
    _write(saved["pack"] / "manifest.json", {"documents": [{"doc_id": DOC_ID, "gold_split": "holdout", "phase4_split": "development"}]})
    with pytest.raises(AnnotationError, match="gold-dev"):
        load_saved_development(**saved)


def test_saved_adapter_missing_prefilter_route_refused(saved):
    _write(saved["prefilter_events"], [], rows=True)
    with pytest.raises(AnnotationError, match="coverage"):
        load_saved_development(**saved)


def test_saved_adapter_missing_scalar_evidence_refused(saved):
    _write(saved["run"] / "evidence_spans.jsonl", [], rows=True)
    with pytest.raises(AnnotationError, match="evidence gate"):
        load_saved_development(**saved)


def test_structured_gold_labels_match_enum_values():
    gold = SimpleNamespace(expected_values={"remembered_cues": {"value": [{"value": "approximate_time", "detail": None}]}})
    model = SimpleNamespace(values={"remembered_cues": {"value": ["approximate_time"]}})
    assert multilabel_scores([(gold, model)])["remembered_cues"]["micro"]["f1"] == 1


def test_summary_without_reference_is_unassessed_not_supported():
    gold = SimpleNamespace(expected_values={})
    model = SimpleNamespace(values={"problem_summary": {"value": "A paraphrase"}}, spans=(SimpleNamespace(field_name="problem_summary", validation_state="valid"),))
    result = unsupported_inference([(gold, model)])
    assert result["problem_summary"] is None
    assert result["overall"] is None


def test_omitted_multilabel_value_is_recall_miss_not_unsupported_inference():
    gold = SimpleNamespace(expected_values={"workarounds": {"value": ["manual_scrolling", "alternate_app"]}})
    model = SimpleNamespace(values={"workarounds": {"value": ["manual_scrolling"]}}, spans=(SimpleNamespace(field_name="workarounds", validation_state="valid"),))
    assert unsupported_inference([(gold, model)])["workarounds"] == 0
    assert multilabel_scores([(gold, model)])["workarounds"]["micro"]["recall"] == 0.5


def test_no_predictions_does_not_claim_measured_gold(tmp_path):
    _write_gold(tmp_path, [_document(DOC_ID, prefilter=True, scope=ScopeClass.core_incomplete_recall)], [])
    result = evaluate_gold(documents_path=tmp_path / "documents.jsonl", cases_path=tmp_path / "cases.jsonl", split="dev")
    assert result["status"] == "pending"
    assert result["prediction_coverage"]["documents_without_predictions"] == 1


def test_source_mismatch_in_relevance_span_fails_span_gate(saved, tmp_path):
    loaded = load_saved_development(**saved)
    _write_gold(tmp_path, [_document(DOC_ID, prefilter=True, scope=ScopeClass.core_incomplete_recall)], [])
    bad = SimpleNamespace(quote="not in the source", start_char=0, end_char=1, validation_state="rejected", field_name="scope_class")
    report = evaluate_gold(documents_path=tmp_path / "documents.jsonl", cases_path=tmp_path / "cases.jsonl", split="dev", predictions=loaded.predictions, extracted_cases=loaded.extracted_cases, processed_records=2, additional_spans_by_document={DOC_ID: (bad,)})
    assert report["gates"]["span_validation_rate"]["pass"] is False


def test_cli_refuses_saved_holdout_and_occupied_outputs(tmp_path):
    out = tmp_path / "out"
    flags = ["--gold", str(tmp_path), "--out", str(out), "--split", "holdout", "--saved-run", "run", "--relevance", "decisions", "--pack", "pack", "--prefilter-events", "events"]
    assert evaluate.main(flags) == 2
    assert not out.exists()
    out.mkdir()
    assert evaluate.main(["--gold", str(tmp_path), "--out", str(out), "--split", "dev"]) == 2


def test_cli_supplies_saved_predictions_to_real_metrics(saved, tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    _write_gold(gold, [_document(DOC_ID, prefilter=True, scope=ScopeClass.core_incomplete_recall)], [])
    out = tmp_path / "evaluation"
    flags = ["--gold", str(gold), "--split", "dev", "--out", str(out), "--saved-run", str(saved["run"]), "--relevance", str(saved["relevance"]), "--pack", str(saved["pack"]), "--prefilter-events", str(saved["prefilter_events"])]
    assert evaluate.main(flags) == 0
    report = json.loads((out / "report.json").read_text())
    assert report["relevance"]["precision"] == 1
    assert report["quality_gate_status"] == "development_only"
    assert report["case_coverage"]["unmatched_model_cases"] == 1
    assert (out / "disagreements.csv").is_file()
    ledger = json.loads((out / "failure_categories.json").read_text(encoding="utf-8"))
    assert ledger["split"] == "dev"
    assert ledger["thresholds_lowered"] is False
    assert ledger["holdout_rescored"] is False
    assert RAW_TEXT_AUDIT not in (out / "failure_categories.json").read_text(encoding="utf-8")


def test_measured_prompts_use_the_stage_that_ran_them(saved):
    _write(saved["run"] / "run_manifest.json", {
        "run_id": "synthetic",
        "versions": {"prompt_versions": {"extract": "extract/v4", "relevance": "relevance/v5"}},
    })
    _write(saved["relevance"].parent / "run_manifest.json", {
        "versions": {"prompt_versions": {"relevance": "relevance/v6", "extract": "extract/v2"}},
    })
    loaded = load_saved_development(**saved)
    prompts = loaded.metadata["measured_prompts"]
    assert prompts["extract"] == "extract/v4"
    assert prompts["relevance"] == "relevance/v6"
    assert prompts["extraction_manifest_relevance_pin"] == "relevance/v5"
