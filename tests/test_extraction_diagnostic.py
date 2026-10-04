"""One-request synthetic extraction diagnostic. Completions are mocked. No network."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
from src.core.config import load_settings
from src.extract.schema import extraction_schema
from src.llm.providers.base import (
    CompletionParams,
    ProviderDiagnostic,
    ProviderResponse,
    provider_failed,
    rate_limited,
)
from src.llm.providers.groq import groq_request_schema
from src.pipeline.extraction import transmitted_extraction_schema
from src.pipeline.extraction_diagnostic import (
    DEFAULT_OUTPUT,
    DIAGNOSTIC_CALL_BUDGET,
    DIAGNOSTIC_DOC_ID,
    DIAGNOSTIC_MAX_RETRIES,
    DIAGNOSTIC_TEXT,
    PRESERVED_OUTPUTS,
    DiagnosticBoundsError,
    planned_output_dir,
    run_extraction_diagnostic,
    synthetic_decision,
    synthetic_document,
)
from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER

SECRET = "gsk-test-secret-not-real"
RAW_BODY = "RAW-VENDOR-BODY-SHOULD-NOT-PERSIST"
CLEAN_MESSAGE = "schema rejected at response_format.json_schema.schema"


class CountingProvider:
    provider_name = "fake"

    def __init__(self, text: str | None = None, failure=None) -> None:
        self.text = text
        self.failure = failure
        self.calls = 0
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def complete_structured(self, prompt: str, schema: dict, params: CompletionParams) -> ProviderResponse:
        self.calls += 1
        self.prompts.append(prompt)
        self.schemas.append(dict(schema))
        if self.failure is not None:
            raise self.failure
        return ProviderResponse(
            text=self.text or json.dumps({"doc_id": DIAGNOSTIC_DOC_ID, "cases": []}),
            input_tokens=3,
            output_tokens=1,
            model=params.model,
            provider=self.provider_name,
        )


def _run(tmp_path: Path, provider, **kwargs):
    settings = {
        "output_dir": tmp_path / "out",
        "cache_dir": tmp_path / "cache",
        "provider_name": PILOT_PROVIDER,
        "model_name": PILOT_MODEL,
        "temperature": 0.0,
        "max_tokens": 64,
        "max_retries": DIAGNOSTIC_MAX_RETRIES,
        "call_budget": DIAGNOSTIC_CALL_BUDGET,
        "provider": provider,
        "api_key": SECRET,
        "preserved": (tmp_path / "preserved",),
    }
    settings.update(kwargs)
    return run_extraction_diagnostic(**settings)


def test_synthetic_evidence_belongs_to_the_synthetic_document() -> None:
    document = synthetic_document()
    decision = synthetic_decision()
    assert document.doc_id == DIAGNOSTIC_DOC_ID
    assert decision.doc_id == document.doc_id
    assert decision.validation_state.value == "valid"
    assert len(decision.evidence) == 1
    span = decision.evidence[0]
    assert span.doc_id == document.doc_id
    assert span.owner_id == decision.decision_id
    assert span.owner_type.value == "relevance_decision"
    assert document.raw_text_audit[span.start_char : span.end_char] == span.quote
    assert DIAGNOSTIC_DOC_ID not in {
        "google_support-2a080da4b930",
        "google_support-d7f386f347b7",
        "google_support-e1e5277da7e8",
        "reddit-23be97c93709",
        "reddit-c49086caf891",
    }


def test_one_call_cap_does_not_retry(tmp_path: Path) -> None:
    provider = CountingProvider(failure=rate_limited("slow down", retry_after_seconds=30))
    result = _run(tmp_path, provider)
    assert provider.calls == 1
    assert result.provider_calls == 1
    assert result.eligible == 1
    assert result.valid_cases == 0
    wider = CountingProvider()
    with pytest.raises(DiagnosticBoundsError):
        _run(tmp_path / "wider", wider, call_budget=5)
    with pytest.raises(DiagnosticBoundsError):
        _run(tmp_path / "retry", wider, max_retries=2)
    assert wider.calls == 0


def test_missing_key_is_rejected_before_output(tmp_path: Path) -> None:
    provider = CountingProvider()
    output = tmp_path / "out"
    with pytest.raises(DiagnosticBoundsError, match="GROQ_API_KEY"):
        _run(tmp_path, None, api_key=None, output_dir=output)
    assert provider.calls == 0
    assert not output.exists()


def test_occupied_output_is_rejected_before_calls(tmp_path: Path) -> None:
    destination = planned_output_dir(
        tmp_path / "out",
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=64,
        dry_run=False,
        offline=False,
        preserved=(tmp_path / "preserved",),
    )
    destination.mkdir(parents=True)
    marker = destination / "checkpoints.jsonl"
    marker.write_text("keep\n", encoding="utf-8")
    provider = CountingProvider()
    with pytest.raises(DiagnosticBoundsError, match="already exists"):
        _run(tmp_path, provider)
    assert provider.calls == 0
    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_output_stays_outside_preserved_pilot_artifacts(tmp_path: Path) -> None:
    assert any(path.as_posix().endswith("data/interim/phase5/pilot") for path in PRESERVED_OUTPUTS)
    assert DEFAULT_OUTPUT.as_posix().endswith("data/interim/phase5/diagnostic")
    provider = CountingProvider()
    preserved = tmp_path / "pilot"
    with pytest.raises(DiagnosticBoundsError, match="preserved"):
        _run(tmp_path, provider, output_dir=preserved, preserved=(preserved,))
    assert provider.calls == 0
    assert not preserved.exists()
    with pytest.raises(DiagnosticBoundsError, match="preserved"):
        run_extraction_diagnostic(
            output_dir=Path("data/interim/phase5/pilot"),
            cache_dir=tmp_path / "cache",
            provider_name=PILOT_PROVIDER,
            model_name=PILOT_MODEL,
            temperature=0.0,
            max_tokens=64,
            max_retries=DIAGNOSTIC_MAX_RETRIES,
            call_budget=DIAGNOSTIC_CALL_BUDGET,
            dry_run=True,
            api_key=SECRET,
        )


def test_allowlisted_diagnostic_persists_without_source_or_credentials(tmp_path: Path) -> None:
    provider = CountingProvider(
        failure=provider_failed(
            f"vendor said {SECRET} {RAW_BODY}",
            diagnostic=ProviderDiagnostic(
                category="invalid_request",
                http_status=400,
                error_code="json_validate_failed",
                error_param="response_format.json_schema.schema",
                error_message=CLEAN_MESSAGE,
            ),
        )
    )
    result = _run(tmp_path, provider)
    stored = (Path(result.output_dir) / "extraction_failures.jsonl").read_text(encoding="utf-8")
    row = json.loads(stored)
    diagnostic = row["provider_diagnostic"]
    assert diagnostic["category"] == "invalid_request"
    assert diagnostic["http_status"] == 400
    assert diagnostic["error_code"] == "json_validate_failed"
    assert diagnostic["error_param"] == "response_format.json_schema.schema"
    assert diagnostic["error_message"] == CLEAN_MESSAGE
    assert row["raw_response_ref"] is None
    written = "\n".join(path.read_text(encoding="utf-8") for path in Path(result.output_dir).glob("*"))
    assert SECRET not in written
    assert DIAGNOSTIC_TEXT not in written
    assert RAW_BODY not in written


def test_dry_run_makes_no_call_and_writes_nothing(tmp_path: Path) -> None:
    provider = CountingProvider()
    output = tmp_path / "out"
    result = _run(tmp_path, provider, dry_run=True, api_key=None, output_dir=output)
    assert provider.calls == 0
    assert result.provider_calls == 0
    assert result.eligible == 1
    assert result.attempted == 0
    assert result.files_written == ()
    assert not output.exists()
    assert not (tmp_path / "cache").exists()


def test_groq_diagnostic_uses_unchanged_strict_schema_and_no_sdk_retry(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["calls"] = int(captured.get("calls", 0)) + 1
        captured["kwargs"] = kwargs
        schema = kwargs["response_format"]["json_schema"]["schema"]
        doc_id = schema["properties"]["doc_id"]["enum"][0]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"doc_id": doc_id, "cases": []})))],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
            model=PILOT_MODEL,
        )

    def groq_client(*, api_key, timeout, max_retries=1):
        captured["max_retries"] = max_retries
        captured["api_key"] = api_key
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(
        sys.modules,
        "groq",
        SimpleNamespace(
            Groq=groq_client,
            APITimeoutError=type("APITimeoutError", (Exception,), {}),
            RateLimitError=type("RateLimitError", (Exception,), {}),
            APIConnectionError=type("APIConnectionError", (Exception,), {}),
            APIStatusError=type("APIStatusError", (Exception,), {}),
            APIError=type("APIError", (Exception,), {}),
            AuthenticationError=type("AuthenticationError", (Exception,), {}),
        ),
    )
    result = _run(tmp_path, None)
    assert captured["max_retries"] == 0
    assert captured["calls"] == 1
    assert result.provider_calls == 1
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["model"] == PILOT_MODEL
    assert kwargs["max_tokens"] == 64
    sent = kwargs["response_format"]["json_schema"]["schema"]
    expected = groq_request_schema(
        extraction_schema(DIAGNOSTIC_DOC_ID), doc_id=DIAGNOSTIC_DOC_ID, nullable_scalars=True,
    )
    assert sent == expected
    assert sent == transmitted_extraction_schema(DIAGNOSTIC_DOC_ID, provider_name="groq")
    prompt = kwargs["messages"][1]["content"]
    embedded = json.loads(prompt.split("Transmitted JSON Schema:\n", 1)[1].split("\n\nUNTRUSTED", 1)[0])
    assert embedded == sent
    encoded = json.dumps(kwargs)
    assert SECRET not in encoded
    assert result.attempted == 1
    assert result.by_state.get("ok") == 1


def test_cli_diagnostic_dry_run_is_isolated(tmp_path: Path, capsys) -> None:
    output = tmp_path / "diagnostic-out"
    cache = tmp_path / "cache"
    code = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--diagnostic",
            "--dry-run",
            "--provider",
            "groq",
            "--split",
            "development",
            "--cache",
            str(cache),
            "--call-budget",
            "1",
            "--max-retries",
            "1",
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "provider calls       0" in captured.out
    assert DIAGNOSTIC_DOC_ID in captured.out
    assert PILOT_MODEL in captured.out
    assert "extract/v2" in captured.out
    assert "call budget          1" in captured.out
    assert not output.exists()
    assert not cache.exists()


def test_cli_refuses_pilot_combination_real_documents_and_a_missing_key(
    monkeypatch, tmp_path: Path, empty_env: Path, capsys
) -> None:
    combined = main.main(["run", "--stages", "extract", "--pilot", "--diagnostic", "--dry-run"])
    assert combined == 1
    assert "cannot be combined" in capsys.readouterr().err

    derived = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--diagnostic",
            "--dry-run",
            "--derived",
            str(tmp_path / "missing-derived.jsonl"),
        ]
    )
    assert derived == 1
    assert "real documents" in capsys.readouterr().err

    live = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--provider",
            "groq",
            "--call-budget",
            "1",
            "--max-retries",
            "1",
        ]
    )
    assert live == 1
    assert "not authorized" in capsys.readouterr().err

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(main, "load_settings", lambda: load_settings(env_file=empty_env))
    output = tmp_path / "live-out"
    missing = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--diagnostic",
            "--provider",
            "groq",
            "--output",
            str(output),
            "--cache",
            str(tmp_path / "cache"),
        ]
    )
    assert missing == 1
    assert "GROQ_API_KEY" in capsys.readouterr().err
    assert not output.exists()
