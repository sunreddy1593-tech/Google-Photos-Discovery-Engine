"""Reddit collection skips without credentials and parses a recorded listing."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.collect.reddit import collect_reddit, collect_reddit_live

SALT = "reddit-test-salt"
WHEN = datetime(2026, 10, 4, tzinfo=timezone.utc)
LISTING = {
    "data": {
        "children": [
            {
                "data": {
                    "name": "t3_fixture",
                    "id": "fixture",
                    "title": "I cannot find an older photo",
                    "selftext": "I do not remember when I took it.",
                    "author": "person_one",
                    "permalink": "/r/googlephotos/comments/fixture/title/",
                    "subreddit": "googlephotos",
                    "created_utc": 1_700_000_000,
                    "link_id": "t3_fixture",
                }
            }
        ]
    }
}


@pytest.mark.synthetic
def test_missing_credentials_skip_without_documents() -> None:
    report = collect_reddit(
        client_id=None,
        client_secret=None,
        user_agent=None,
        author_salt=SALT,
        listing=LISTING,
        collected_at=WHEN,
    )
    assert report.skipped is True
    assert report.documents == ()
    assert report.requests_made == 0
    assert "disabled" in report.reason


@pytest.mark.synthetic
def test_recorded_listing_hashes_the_author_and_keeps_the_text() -> None:
    report = collect_reddit(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        listing=LISTING,
        collected_at=WHEN,
    )
    assert report.skipped is False
    assert len(report.documents) == 1
    document = report.documents[0]
    assert document.source_platform.value == "reddit"
    assert "person_one" not in document.model_dump_json()
    assert document.raw_text.startswith("I cannot find an older photo")
    assert document.doc_id.startswith("reddit-")


@pytest.mark.synthetic
def test_rate_limit_stops_the_source() -> None:
    def transport(_path: str) -> tuple[int, dict[str, str], dict]:
        return 200, {"X-Ratelimit-Remaining": "0"}, LISTING

    report = collect_reddit(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        transport=transport,
        collected_at=WHEN,
    )
    assert report.stopped_reason == "rate_limited"
    assert report.documents == ()
    assert report.requests_made == 1


@pytest.mark.synthetic
def test_credentials_without_transport_do_not_call_the_api() -> None:
    report = collect_reddit(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        collected_at=WHEN,
    )
    assert report.skipped is True
    assert report.requests_made == 0


def _live_transport(pages: dict[str, tuple[int, dict[str, str], dict]]):
    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        if url.endswith("/api/v1/access_token"):
            assert headers["Authorization"].startswith("Basic ")
            assert b"grant_type=client_credentials" == body
            return 200, {"X-Ratelimit-Remaining": "50"}, {"access_token": "token"}
        for fragment, response in pages.items():
            if fragment in url:
                return response
        raise AssertionError(url)

    return transport


@pytest.mark.synthetic
def test_live_collection_hashes_the_author_and_keeps_a_stable_id(tmp_path) -> None:
    transport = _live_transport(
        {
            "/new?": (
                200,
                {"X-Ratelimit-Remaining": "40"},
                LISTING,
            ),
            "/comments/": (
                200,
                {"X-Ratelimit-Remaining": "39"},
                {"data": {"children": [], "after": None}},
            ),
        }
    )
    report = collect_reddit_live(
        client_id="id",
        client_secret="super-secret-value",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        output_dir=tmp_path,
        document_limit=10,
        request_budget=5,
        queries=(),
        transport=transport,
        collected_at=WHEN,
    )
    assert report.skipped is False
    assert report.stopped_reason is None
    assert len(report.documents) == 1
    assert report.documents[0].doc_id == report.documents[0].doc_id
    saved = (tmp_path / "collected_documents.jsonl").read_text(encoding="utf-8")
    assert "person_one" not in saved
    assert "super-secret-value" not in saved
    assert report.documents[0].doc_id.startswith("reddit-")


@pytest.mark.synthetic
def test_live_rate_limit_stops_before_the_next_page(tmp_path) -> None:
    seen: list[str] = []

    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        seen.append(url)
        if url.endswith("/api/v1/access_token"):
            return 200, {}, {"access_token": "token"}
        listing = {
            "data": {
                "after": "t3_next",
                "children": LISTING["data"]["children"],
            }
        }
        return 200, {"X-Ratelimit-Remaining": "0"}, listing

    report = collect_reddit_live(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        output_dir=tmp_path,
        document_limit=10,
        request_budget=5,
        queries=(),
        transport=transport,
        collected_at=WHEN,
    )
    assert report.stopped_reason == "rate_limited"
    assert len(report.documents) == 1
    assert not any("after=" in url for url in seen)


@pytest.mark.synthetic
def test_live_error_stops_the_source_without_documents(tmp_path) -> None:
    def transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        if url.endswith("/api/v1/access_token"):
            return 200, {}, {"access_token": "token"}
        return 403, {}, {}

    report = collect_reddit_live(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        output_dir=tmp_path,
        document_limit=5,
        request_budget=3,
        queries=(),
        transport=transport,
        collected_at=WHEN,
    )
    assert report.stopped_reason == "source_blocked"
    assert report.documents == ()


@pytest.mark.synthetic
def test_live_dry_run_writes_nothing(tmp_path) -> None:
    destination = tmp_path / "reddit"
    report = collect_reddit_live(
        client_id="id",
        client_secret="secret",
        user_agent="discovery-engine-test",
        author_salt=SALT,
        output_dir=destination,
        document_limit=5,
        request_budget=3,
        dry_run=True,
        collected_at=WHEN,
    )
    assert report.requests_made == 0
    assert not destination.exists()


@pytest.mark.synthetic
def test_missing_live_credentials_skip_without_a_directory(tmp_path) -> None:
    destination = tmp_path / "reddit"
    report = collect_reddit_live(
        client_id=None,
        client_secret=None,
        user_agent=None,
        author_salt=SALT,
        output_dir=destination,
        document_limit=5,
        request_budget=3,
        collected_at=WHEN,
    )
    assert report.skipped is True
    assert report.requests_made == 0
    assert not destination.exists()
