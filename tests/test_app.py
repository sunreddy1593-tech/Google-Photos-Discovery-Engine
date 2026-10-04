"""Streamlit AppTest coverage for the read-only submission view."""

from __future__ import annotations

from pathlib import Path
import json

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_submission_export import _fixture
from src.export.build import build_submission

APP = Path(__file__).resolve().parents[1] / "app.py"


def _launch(export_dir: Path, **env_removed: str) -> AppTest:
    del env_removed
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["export_dir"] = str(export_dir)
    return app.run()


@pytest.mark.synthetic
def test_app_launches_without_provider_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROQ_API_KEY", "YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "AUTHOR_SALT"):
        monkeypatch.delenv(name, raising=False)
    destination = tmp_path / "export"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    app = _launch(destination)
    assert not app.exception
    assert app.metric[0].label == "Documents"
    assert app.metric[0].value == "3"
    assert app.metric[1].label == "Extraction attempts"
    assert app.metric[1].value == "3"
    assert any(metric.label == "Semantically approved" and metric.value == "0" for metric in app.metric)


@pytest.mark.synthetic
def test_missing_export_does_not_crash(tmp_path: Path) -> None:
    app = _launch(tmp_path / "missing-export")
    assert not app.exception
    assert app.error
    assert "Prepared export is missing" in app.error[0].value


@pytest.mark.synthetic
def test_filters_failed_records_and_zero_approved_cases(tmp_path: Path) -> None:
    destination = tmp_path / "export"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    app = _launch(destination)
    app.radio(key="section").set_value("Evidence browser").run()
    assert not app.exception
    assert any("dev-b" in block.value for block in app.markdown)
    assert any("dev-empty" in block.value for block in app.markdown)

    app.selectbox(key="human_filter_fixture-dev").select("out_of_scope").run()
    app.selectbox(key="record_filter_fixture-dev").select("Extraction cases").run()
    assert not app.exception
    assert any("No records match these filters." in block.value for block in app.info)

    app.selectbox(key="source_filter_fixture-dev").select("All").run()
    app.radio(key="section").set_value("Problem comparison").run()
    assert not app.exception
    assert any("No extraction case is semantically approved" in block.value for block in app.info)


@pytest.mark.synthetic
def test_methodology_uses_aggregate_quality_without_changing_sample_counts(tmp_path: Path) -> None:
    destination = tmp_path / "export"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    metadata = tmp_path / "quality.json"
    metadata.write_text(json.dumps({
        "status": "measured", "all_numeric_thresholds_passed": True,
        "holdout_documents": 8, "reference_cases": 4, "matched_cases": 2,
        "m1_status": "complete", "limitations": ["Synthetic sample has prior development exposure."],
        "development_matched_cases": 2, "development_reference_cases": 6,
        "development_relevance_precision": 0.8333, "development_relevance_precision_passed": False,
    }), encoding="utf-8")
    app = _launch(destination)
    app.session_state["quality_metadata_path"] = str(metadata)
    app.radio(key="section").set_value("Methodology and limitations").run()
    assert not app.exception
    rendered = " ".join(block.value for block in app.markdown)
    assert "passed on 8 holdout documents" in rendered
    assert "Recovered reference cases: 2 of 4" in rendered
    assert "Development extract/v3 recovered 2 of 6" in rendered
    assert "0.8333 missed the 0.85 threshold" in rendered
    assert "prior development exposure" in rendered
    assert any("does not change" in block.value and "approve" in block.value for block in app.caption)
    assert not any("Milestone 1 is not complete" in block.value for block in app.caption)


@pytest.mark.synthetic
def test_quality_report_labels_every_number_with_its_split(tmp_path: Path) -> None:
    destination = tmp_path / "export"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    metadata = tmp_path / "quality.json"
    metadata.write_text(json.dumps({
        "status": "measured",
        "splits": [
            {"split": "development", "documents": 10, "matched_cases": 2, "reference_cases": 6,
             "schema_validation_rate": 1, "span_validation_rate": 1, "prefilter_recall": 1,
             "relevance_precision": 0.8333, "relevance_recall": 1, "quality_gate_status": "development_only",
             "excluded_technical_failures": 1},
            {"split": "holdout", "documents": 25, "matched_cases": 5, "reference_cases": 15,
             "schema_validation_rate": 1, "span_validation_rate": 1, "prefilter_recall": 1,
             "relevance_precision": 0.9286, "relevance_recall": 0.9286,
             "quality_gate_status": "numeric_thresholds_passed", "excluded_technical_failures": 0},
        ],
        "accepted_limitations": [
            {"split": "holdout", "text": "Prior development exposure remains disclosed."},
        ],
    }), encoding="utf-8")
    app = _launch(destination)
    app.session_state["quality_metadata_path"] = str(metadata)
    app.radio(key="section").set_value("Quality report").run()
    assert not app.exception
    rendered = " ".join(block.value for block in app.markdown)
    assert "development documents" in rendered
    assert "holdout reference cases recovered" in rendered
    assert "2 of 6" in rendered
    assert "5 of 15" in rendered
    assert "Prior development exposure remains disclosed." in rendered


@pytest.mark.synthetic
def test_ask_returns_saved_excerpts_without_a_model(tmp_path: Path) -> None:
    destination = tmp_path / "export"
    build_submission(_fixture(tmp_path), destination, root=tmp_path)
    app = _launch(destination)
    app.radio(key="section").set_value("Ask the evidence").run()
    assert not app.exception
    app.text_input(key="ask_question").set_value("birthday").run()
    app.button(key="ask_search").click().run()
    assert not app.exception
    rendered = " ".join(block.value for block in list(app.markdown) + list(app.text))
    assert "birthday" in rendered.lower()
    assert any("not semantically approved" in block.value for block in app.caption)

    empty = _launch(destination)
    empty.radio(key="section").set_value("Ask the evidence").run()
    empty.text_input(key="ask_question").set_value("zzznomatch").run()
    empty.button(key="ask_search").click().run()
    assert any("insufficient evidence" in block.value for block in empty.info)
