"""Credential status and source counts do not print secret values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_sources import audit
from scripts.check_credentials import main as check_main


@pytest.mark.synthetic
def test_missing_optional_credentials_are_disabled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "YOUTUBE_API_KEY",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
        "GROQ_API_KEY",
        "N8N_COLLECTION_WEBHOOK_URL",
        "N8N_WEBHOOK_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "empty.env"
    env.write_text("AUTHOR_SALT=synthetic-salt\n", encoding="utf-8")
    code = check_main(["--env-file", str(env)])
    captured = capsys.readouterr()
    assert code == 0
    assert "reddit: source disabled" in captured.out
    assert "youtube: source disabled" in captured.out
    assert "synthetic-salt" not in captured.out


@pytest.mark.synthetic
def test_audit_reports_concentration(tmp_path: Path) -> None:
    path = tmp_path / "docs.jsonl"
    rows = [{"source_platform": "reddit", "evidence_tier": "direct_user"}] * 8
    rows += [{"source_platform": "youtube", "evidence_tier": "direct_user"}] * 2
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report = audit([path])
    assert report["documents"] == 10
    assert report["source_types"] == 2
    assert report["concentration_over_threshold"] == ["reddit"]
