"""Live Community insights analyse box. No network and no webhook calls."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

import community_insights

APP = Path(__file__).resolve().parents[1] / "community_insights.py"
THREAD = "https://support.google.com/photos/thread/106429666?hl=en"
CANONICAL = "https://support.google.com/photos/thread/106429666"


class _Response:
    def __init__(self, text: str = "", content_type: str = "text/csv") -> None:
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


def _sheet_csv() -> str:
    columns = ",".join(community_insights.COLUMNS)
    values = [
        "community", CANONICAL, "Old album", "TRUE", "screenshot", "find",
        "place; person", "date", "beach", "expression", "none", "the quote",
        "summary", "2026-10-04",
    ]
    return columns + "\n" + ",".join(values) + "\n"


def _block_network(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls = {"post": [], "get": 0}

    def post(url, json=None, headers=None, timeout=None):
        calls["post"].append({"json": json, "has_api_key": bool(headers and headers.get("X-Api-Key"))})
        return _Response("ok", "application/json")

    def get(url, timeout=None):
        calls["get"] += 1
        return _Response(_sheet_csv())

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    return calls


def _clock(monkeypatch: pytest.MonkeyPatch) -> dict:
    clock = {"now": 1_000.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds
        clock.setdefault("sleeps", []).append(seconds)

    monkeypatch.setattr(community_insights.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(community_insights.time, "sleep", sleep)
    return clock


@pytest.mark.synthetic
def test_reddit_and_thread_links_are_classified() -> None:
    assert community_insights._is_reddit_link("https://www.reddit.com/r/googlephotos/comments/abc")
    assert community_insights._is_reddit_link("old.reddit.com/r/photos")
    assert not community_insights._is_reddit_link(THREAD)
    assert not community_insights._is_reddit_link("https://example.com/not-reddit")
    assert community_insights.THREAD_RE.match(THREAD)
    assert community_insights._thread_id(THREAD) == "106429666"


@pytest.mark.synthetic
def test_poll_stops_when_the_thread_row_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [
        pd.DataFrame({"url": ["https://support.google.com/photos/thread/1"]}),
        pd.DataFrame({"url": [CANONICAL], "title": ["Found it"], "is_retrieval_problem": ["YES"]}),
    ]

    def read_sheet(sheet_url: str, tab: str = "insights") -> pd.DataFrame:
        return frames.pop(0)

    def reject_post(*args, **kwargs):
        raise AssertionError("webhook")

    monkeypatch.setattr(community_insights, "_read_public_sheet", read_sheet)
    monkeypatch.setattr(requests, "post", reject_post)
    _clock(monkeypatch)
    row = community_insights._poll_insights_row("https://docs.google.com/spreadsheets/d/abc/edit", "106429666")
    assert row is not None
    assert row["title"] == "Found it"
    assert bool(row["is_retrieval_problem"]) is True
    assert frames == []


@pytest.mark.synthetic
def test_poll_stops_after_the_deadline_without_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def read_sheet(sheet_url: str, tab: str = "insights") -> pd.DataFrame:
        return pd.DataFrame({"url": ["https://support.google.com/photos/thread/1"]})

    monkeypatch.setattr(community_insights, "_read_public_sheet", read_sheet)
    clock = _clock(monkeypatch)
    row = community_insights._poll_insights_row(
        "https://docs.google.com/spreadsheets/d/abc/edit", "106429666", timeout_s=25, interval_s=10,
    )
    assert row is None
    assert clock["now"] == 1_025.0
    assert clock["sleeps"] == [10, 10, 5]


@pytest.mark.synthetic
def test_invalid_and_reddit_links_do_not_call_the_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _block_network(monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()
    assert not app.exception
    assert any("Try it live: analyse a thread" in block.value for block in app.markdown)

    app.text_input(key="analyse_thread_url").set_value("https://example.com/nope")
    app.button(key="analyse_thread").click().run()
    assert any("Paste a Google Photos Community thread link." in item.value for item in app.error)
    assert calls["post"] == []

    app.text_input(key="analyse_thread_url").set_value("https://www.reddit.com/r/googlephotos/comments/abc")
    app.button(key="analyse_thread").click().run()
    assert any("Reddit isn't supported" in item.value for item in app.error)
    assert calls["post"] == []


@pytest.mark.synthetic
def test_existing_thread_shows_the_result_card(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        has_webhook = bool(community_insights._secret("N8N_WEBHOOK_URL"))
    except Exception:
        has_webhook = False
    if not has_webhook:
        pytest.skip("N8N_WEBHOOK_URL is not configured")
    calls = _block_network(monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()
    app.text_input(key="analyse_thread_url").set_value(THREAD)
    app.button(key="analyse_thread").click().run()
    assert not app.exception
    assert calls["post"]
    assert calls["post"][0]["json"] == {"url": THREAD, "limit": 1, "source": "streamlit"}
    assert any("Already analysed earlier" in item.value for item in app.info)
    rendered = " ".join(block.value for block in app.markdown)
    assert "Old album" in rendered
    assert "About finding a photo:" in rendered and "Yes" in rendered
    assert "Expression – can't put memory into words" in rendered
    assert "> the quote" in rendered or "the quote" in rendered
