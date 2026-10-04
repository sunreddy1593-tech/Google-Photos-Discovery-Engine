"""Five-document 8192-token pilot. Completions are mocked. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import main
from src.llm.cache import CacheEntry, ResponseCache
from src.llm.gateway import ModelGateway
from src.llm.providers.base import rate_limited
from src.models.enums import DecisionTechnicalState
from src.pipeline.extraction import PROMPT_ID, extraction_request_identity
from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER, PilotBoundsError
from tests.test_extraction_pilot import EXPECTED, CORE, CountingProvider, _decision, _derived, _pilot

SEAT = "google_support-d7f386f347b7"


def _inputs():
    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    derived = {doc_id: _derived(doc_id) for doc_id in ids}
    return ids, decisions, derived


def _identity(derived):
    return extraction_request_identity(
        derived,
        provider_name=PILOT_PROVIDER,
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=8192,
        prompt_version_value="extract/v2",
    )


def _seed(cache_dir: Path, derived, *, raw_response: str | None = None, mutate=None) -> None:
    identity = _identity(derived)
    entry = CacheEntry(
        cache_key=str(identity["cache_key"]),
        provider=str(identity["provider"]),
        model=str(identity["model"]),
        prompt_id=str(identity["prompt_id"]),
        prompt_version=str(identity["prompt_version"]),
        schema_version=str(identity["schema_version"]),
        ruleset_version=None,
        content_hash=str(identity["content_hash"]),
        decoding_params=dict(identity["decoding_params"]),
        request_text=str(identity["request_text"]),
        raw_response=raw_response if raw_response is not None else json.dumps(
            {"doc_id": derived.doc_id, "cases": []}
        ),
        input_tokens=3,
        output_tokens=1,
        cached_at="2026-10-01T00:00:00+00:00",
        finish_reason="stop",
    )
    ResponseCache(cache_dir).write(entry)
    if mutate is not None:
        path = ResponseCache(cache_dir).path_for(PROMPT_ID, entry.cache_key)
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _run(tmp_path: Path, provider, derived_map, **kwargs):
    ids, decisions, _default = _inputs()
    options = dict(pilot_max_tokens=8192, call_budget=4, max_tokens=4096)
    options.update(kwargs)
    return _pilot(tmp_path, provider, ids, decisions, derived_map, **options)


def test_cached_seat_is_reused_and_the_other_four_are_called_once(tmp_path: Path) -> None:
    ids, _decisions, derived = _inputs()
    cache = tmp_path / "cache"
    _seed(cache, derived[SEAT])
    provider = CountingProvider()
    result = _run(tmp_path / "run", provider, derived, cache_dir=cache)
    called = [schema["properties"]["doc_id"]["enum"][0] for schema in provider.schemas]
    assert provider.calls == result.provider_calls == 4
    assert result.cache_hits == 1
    assert result.cache_misses == 4
    assert SEAT not in called
    assert called == [doc_id for doc_id in ids if doc_id != SEAT]


def test_missing_incompatible_and_unusable_cache_fail_before_calls(tmp_path: Path) -> None:
    _ids, _decisions, derived = _inputs()
    missing = CountingProvider()
    with pytest.raises(PilotBoundsError, match="cache entry is missing"):
        _run(tmp_path / "missing", missing, derived, cache_dir=tmp_path / "missing-cache")
    assert missing.calls == 0
    assert list((tmp_path / "missing").rglob("run_manifest.json")) == []

    cache = tmp_path / "bad-cache"
    _seed(cache, derived[SEAT], mutate=lambda payload: payload.update(content_hash="0" * 64))
    mismatched = CountingProvider()
    with pytest.raises(PilotBoundsError, match="does not match the request"):
        _run(tmp_path / "mismatch", mismatched, derived, cache_dir=cache)
    assert mismatched.calls == 0
    assert list((tmp_path / "mismatch").rglob("run_manifest.json")) == []

    invalid = tmp_path / "invalid-cache"
    _seed(invalid, derived[SEAT], raw_response='{"doc_id": "other", "cases": []}')
    rejected = CountingProvider()
    with pytest.raises(PilotBoundsError, match="failed local response validation"):
        _run(tmp_path / "invalid", rejected, derived, cache_dir=invalid)
    assert rejected.calls == 0
    assert list((tmp_path / "invalid").rglob("run_manifest.json")) == []


def test_rate_limit_uses_one_attempt_for_each_uncached_document(tmp_path: Path) -> None:
    _ids, _decisions, derived = _inputs()
    cache = tmp_path / "cache"
    _seed(cache, derived[SEAT])
    provider = CountingProvider(failure=rate_limited("limited"))
    result = _run(tmp_path / "limited", provider, derived, cache_dir=cache)
    assert provider.calls == result.provider_calls == 4
    assert SEAT not in "".join(provider.prompts)


def test_budget_reserves_one_first_attempt_for_four_uncached_documents(tmp_path: Path) -> None:
    provider = CountingProvider(failure=rate_limited("limited"))
    gateway = ModelGateway(
        provider,
        ResponseCache(tmp_path / "cache"),
        provider_name="fake",
        model=PILOT_MODEL,
        temperature=0.0,
        max_tokens=8192,
        timeout_seconds=5,
        max_retries=2,
        input_usd_per_million=0.0,
        output_usd_per_million=0.0,
        call_budget=4,
        sleeper=lambda _seconds: None,
    )
    for remaining in (3, 2, 1, 0):
        result = gateway.complete(
            prompt="extract",
            schema={"type": "object"},
            response_model=type("Payload", (), {}),
            content_hash=f"hash-{remaining}",
            prompt_id="extract",
            prompt_version="extract/v2",
            unattempted_documents=remaining,
        )
        assert result.technical_state is DecisionTechnicalState.rate_limited
    assert provider.calls == 4


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"call_budget": 5}, "allows 4"),
        ({"max_retries": 2}, "one attempt"),
        ({"pilot_max_tokens": 4096, "call_budget": 5}, "allows only 8192"),
        ({"offline": True}, "does not run offline"),
    ],
)
def test_invalid_five_document_limit_options_make_no_calls(tmp_path: Path, kwargs, message) -> None:
    _ids, _decisions, derived = _inputs()
    provider = CountingProvider()
    with pytest.raises(PilotBoundsError, match=message):
        _run(tmp_path, provider, derived, **kwargs)
    assert provider.calls == 0
    assert list(tmp_path.rglob("run_manifest.json")) == []


def test_dry_run_confirms_the_cache_and_writes_nothing(tmp_path: Path) -> None:
    _ids, _decisions, derived = _inputs()
    cache = tmp_path / "cache"
    _seed(cache, derived[SEAT])
    provider = CountingProvider()
    result = _run(tmp_path / "dry", provider, derived, cache_dir=cache, dry_run=True)
    assert provider.calls == result.provider_calls == 0
    assert result.files_written == ()
    assert result.dry_run is True
    assert not (tmp_path / "dry").exists()


def test_cli_requires_budget_four_and_one_attempt(capsys) -> None:
    base = [
        "run", "--stages", "extract", "--pilot", "--pilot-max-tokens", "8192",
        "--provider", "groq", "--split", "development",
    ]
    assert main.main([*base, "--max-retries", "1"]) == 1
    assert "requires --call-budget 4" in capsys.readouterr().err
    assert main.main([*base, "--call-budget", "5", "--max-retries", "1"]) == 1
    assert "requires --call-budget 4" in capsys.readouterr().err
    assert main.main([*base, "--call-budget", "4", "--max-retries", "2"]) == 1
    assert "requires --max-retries 1" in capsys.readouterr().err
