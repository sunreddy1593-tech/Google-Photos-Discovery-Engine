"""YouTube comment collection against mocked API responses.

No test in this module contacts YouTube or a model provider.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import main
from src.collect.youtube import YoutubeCollectionError, collect_youtube_comments
from src.core.config import load_settings
from src.core.ids import author_hash, doc_id
from src.models.collected_document import CollectedDocument
from src.models.enums import CollectionMethod, EvidenceTier, SourcePlatform, SourceType

SALT = "youtube-test-salt"
API_KEY = "yt-test-key-not-real"
AUTHOR_NAME = "UNIQUE_AUTHOR_DISPLAY_9f3a"
CHANNEL_ID = "UCchannel9f3a"
VIDEO_A = "abcdefghijk"
VIDEO_B = "zyxwvutsrqp"
VIDEO_C = "qrstuvwxyza"
COLLECTED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _comment(
    comment_id: str,
    text: str,
    *,
    parent: str | None = None,
    channel: str = CHANNEL_ID,
    name: str = AUTHOR_NAME,
) -> dict[str, object]:
    snippet: dict[str, object] = {
        "textDisplay": text,
        "authorDisplayName": name,
        "authorChannelId": {"value": channel},
        "publishedAt": "2024-05-01T08:30:00Z",
        "likeCount": 3,
    }
    if parent is not None:
        snippet["parentId"] = parent
    return {"id": comment_id, "snippet": snippet}


def _thread(
    thread_id: str,
    text: str,
    total_replies: int,
    *,
    public: bool = True,
) -> dict[str, object]:
    return {
        "id": thread_id,
        "snippet": {
            "videoId": VIDEO_A,
            "isPublic": public,
            "totalReplyCount": total_replies,
            "topLevelComment": _comment(thread_id, text),
        },
        "replies": {
            "comments": [
                _comment("embedded-partial", "this embedded reply must not be stored", parent=thread_id)
            ]
        },
    }


def _error(status: int, reason: str) -> tuple[int, dict[str, object]]:
    return status, {"error": {"code": status, "errors": [{"reason": reason}]}}


class FakeYouTube:
    """Route mocked commentThreads.list and comments.list pages."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, dict[str, object]]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, dict[str, object]]:
        self.calls.append(url)
        parts = urlsplit(url)
        method = parts.path.rstrip("/").rsplit("/", 1)[-1]
        query = parse_qs(parts.query)
        assert query["key"] == [API_KEY]
        assert "id" not in query
        token = query.get("pageToken", ["first"])[0]
        status, body = self.routes[(method, token)]
        return status, body


def _videos(path: Path, *urls: str) -> Path:
    path.write_text("\n".join(urls) + "\n", encoding="utf-8")
    return path


def _collect(tmp_path: Path, fake: FakeYouTube, **kwargs: object) -> object:
    return collect_youtube_comments(
        kwargs.get("video_file", _videos(tmp_path / "videos.txt", f"https://www.youtube.com/watch?v={VIDEO_A}")),
        tmp_path / "out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=int(kwargs.get("document_limit", 20)),
        request_budget=int(kwargs.get("request_budget", 20)),
        dry_run=bool(kwargs.get("dry_run", False)),
        transport=fake,
        collected_at=COLLECTED_AT,
    )


def _documents(path: Path) -> list[CollectedDocument]:
    return [
        CollectedDocument.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _full_routes() -> dict[tuple[str, str], tuple[int, dict[str, object]]]:
    return {
        ("commentThreads", "first"): (
            200,
            {"items": [_thread("thread-one", "where is the backup photo", 2)], "nextPageToken": "T2"},
        ),
        ("commentThreads", "T2"): (
            200,
            {"items": [_thread("thread-two", "the album search shows everyone else", 0)]},
        ),
        ("comments", "first"): (
            200,
            {
                "items": [_comment("reply-one", "I searched the car", parent="thread-one")],
                "nextPageToken": "R2",
            },
        ),
        ("comments", "R2"): (
            200,
            {"items": [_comment("reply-two", "still cannot find it", parent="thread-one")]},
        ),
    }


@pytest.mark.synthetic
def test_pagination_stores_fetched_replies_and_ignores_embedded_subset(tmp_path: Path) -> None:
    fake = FakeYouTube(_full_routes())
    result = _collect(tmp_path, fake)
    documents = _documents(tmp_path / "out" / "collected_documents.jsonl")

    assert result.report.requests_made == 4
    assert result.report.stopped_reason is None
    assert [document.source_item_id for document in documents] == [
        "thread-one",
        "reply-one",
        "reply-two",
        "thread-two",
    ]
    assert all(document.source_item_id != "embedded-partial" for document in documents)
    top = documents[0]
    assert top.metadata["replies_complete"] is True
    assert top.metadata["reply_pages_fetched"] == 2
    assert top.metadata["total_reply_count"] == 2
    assert documents[3].metadata["replies_complete"] is True
    assert documents[3].metadata["reply_pages_fetched"] == 0
    assert result.report.videos[0].replies_complete is True
    thread = result.report.videos[0].threads[0]
    assert thread.replies_complete is True
    assert thread.reply_pages_fetched == 2


@pytest.mark.synthetic
def test_documents_keep_provenance_and_hash_the_channel_id(tmp_path: Path) -> None:
    fake = FakeYouTube(_full_routes())
    _collect(tmp_path, fake)
    raw = (tmp_path / "out" / "collected_documents.jsonl").read_text(encoding="utf-8")
    report = (tmp_path / "out" / "youtube_collection_report.json").read_text(encoding="utf-8")
    documents = _documents(tmp_path / "out" / "collected_documents.jsonl")
    reply = documents[1]

    assert AUTHOR_NAME not in raw
    assert CHANNEL_ID not in raw
    assert API_KEY not in raw
    assert AUTHOR_NAME not in report
    assert API_KEY not in report
    assert reply.author_hash == author_hash(SALT, "youtube", CHANNEL_ID)
    assert reply.raw_text == "I searched the car"
    assert reply.source_platform is SourcePlatform.youtube
    assert reply.source_type is SourceType.video_comment
    assert reply.evidence_tier is EvidenceTier.direct_user
    assert reply.collection_method is CollectionMethod.api
    assert reply.parent_thread_id == "thread-one"
    assert reply.metadata["parent_comment_id"] == "thread-one"
    assert str(reply.source_url) == "https://www.youtube.com/watch?v=abcdefghijk&lc=reply-one"
    assert reply.published_at == datetime(2024, 5, 1, 8, 30, tzinfo=timezone.utc)
    assert reply.collected_at == COLLECTED_AT
    assert reply.collection_query == f"https://www.youtube.com/watch?v={VIDEO_A}"
    assert reply.doc_id == doc_id("youtube", source_item_id="reply-one")
    assert reply.engagement == {"like_count": 3}
    assert "relevance" not in raw
    assert "extract" not in reply.metadata


@pytest.mark.synthetic
def test_reimport_does_not_duplicate_or_rewrite_documents(tmp_path: Path) -> None:
    first = FakeYouTube(_full_routes())
    _collect(tmp_path, first)
    path = tmp_path / "out" / "collected_documents.jsonl"
    before = path.read_bytes()
    second = FakeYouTube(_full_routes())
    result = _collect(tmp_path, second)

    assert path.read_bytes() == before
    assert result.report.documents_written == 0
    assert result.report.documents_already_present == 4
    assert result.report.requests_made == 2
    assert all(not urlsplit(url).path.endswith("/comments") for url in second.calls)
    assert [json.loads(line)["source_item_id"] for line in before.decode().splitlines()] == [
        "thread-one",
        "reply-one",
        "reply-two",
        "thread-two",
    ]


@pytest.mark.synthetic
def test_changed_reply_count_is_fetched_again(tmp_path: Path) -> None:
    _collect(tmp_path, FakeYouTube(_full_routes()))
    routes = _full_routes()
    routes[("commentThreads", "first")] = (
        200,
        {"items": [_thread("thread-one", "where is the backup photo", 3)], "nextPageToken": "T2"},
    )
    routes[("comments", "R2")] = (
        200,
        {
            "items": [_comment("reply-two", "still cannot find it", parent="thread-one")],
            "nextPageToken": "R3",
        },
    )
    routes[("comments", "R3")] = (
        200,
        {"items": [_comment("reply-three", "a new reply arrived", parent="thread-one")]},
    )
    fake = FakeYouTube(routes)
    result = _collect(tmp_path, fake)

    assert any(urlsplit(url).path.endswith("/comments") for url in fake.calls)
    assert result.report.documents_written == 1
    documents = _documents(tmp_path / "out" / "collected_documents.jsonl")
    assert documents[-1].source_item_id == "reply-three"


@pytest.mark.synthetic
def test_document_limit_stops_before_reply_requests(tmp_path: Path) -> None:
    fake = FakeYouTube(_full_routes())
    result = _collect(tmp_path, fake, document_limit=1)
    documents = _documents(tmp_path / "out" / "collected_documents.jsonl")

    assert [document.source_item_id for document in documents] == ["thread-one"]
    assert documents[0].metadata["replies_complete"] is False
    assert result.report.stopped_reason == "document_limit"
    assert result.report.requests_made == 1
    assert all("comments" not in urlsplit(url).path for url in fake.calls)


@pytest.mark.synthetic
def test_request_budget_does_not_claim_unfetched_replies(tmp_path: Path) -> None:
    fake = FakeYouTube(_full_routes())
    result = _collect(tmp_path, fake, request_budget=2)
    top = _documents(tmp_path / "out" / "collected_documents.jsonl")[0]

    assert result.report.requests_made == 2
    assert result.report.stopped_reason == "request_budget"
    assert top.metadata["replies_complete"] is False
    assert top.metadata["reply_pages_fetched"] == 1
    assert result.report.videos[0].threads[0].replies_complete is False
    assert len(fake.calls) == 2


@pytest.mark.synthetic
def test_disabled_and_unavailable_videos_continue(tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str) -> tuple[int, dict[str, object]]:
        calls.append(url)
        video_id = parse_qs(urlsplit(url).query)["videoId"][0]
        if video_id == VIDEO_A:
            return _error(403, "commentsDisabled")
        if video_id == VIDEO_C:
            return _error(404, "videoNotFound")
        if video_id == VIDEO_B:
            return 200, {"items": [_thread("thread-b", "found one photo", 0)]}
        raise AssertionError(video_id)

    video_file = _videos(
        tmp_path / "videos.txt",
        f"https://youtu.be/{VIDEO_A}",
        "",
        f"https://www.youtube.com/watch?v={VIDEO_C}",
        f"https://www.youtube.com/shorts/{VIDEO_B}",
        f"https://www.youtube.com/watch?v={VIDEO_B}&utm_source=skip",
    )
    result = collect_youtube_comments(
        video_file,
        tmp_path / "out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=5,
        request_budget=5,
        transport=transport,
        collected_at=COLLECTED_AT,
    )
    documents = _documents(tmp_path / "out" / "collected_documents.jsonl")

    assert [video.outcome for video in result.report.videos] == [
        "comments_disabled",
        "video_unavailable",
        "collected",
    ]
    assert documents[0].source_item_id == "thread-b"
    assert documents[0].metadata["replies_complete"] is True
    assert len(calls) == 3


@pytest.mark.synthetic
def test_quota_and_rate_limit_stop_without_further_requests(tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str) -> tuple[int, dict[str, object]]:
        calls.append(url)
        video_id = parse_qs(urlsplit(url).query)["videoId"][0]
        if video_id == VIDEO_A:
            return 200, {"items": [_thread("thread-a", "first kept comment", 0)]}
        return _error(403, "quotaExceeded")

    result = collect_youtube_comments(
        _videos(
            tmp_path / "videos.txt",
            f"https://www.youtube.com/watch?v={VIDEO_A}",
            f"https://m.youtube.com/watch?v={VIDEO_B}",
        ),
        tmp_path / "out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=10,
        request_budget=10,
        transport=transport,
        collected_at=COLLECTED_AT,
    )

    assert result.report.stopped_reason == "quota"
    assert result.report.videos[1].outcome == "partial"
    assert len(calls) == 2
    assert _documents(tmp_path / "out" / "collected_documents.jsonl")[0].raw_text == "first kept comment"

    rate_calls: list[str] = []

    def rate_limited(url: str) -> tuple[int, dict[str, object]]:
        rate_calls.append(url)
        return _error(403, "userRateLimitExceeded")

    rate = collect_youtube_comments(
        _videos(tmp_path / "rate.txt", f"https://www.youtube.com/embed/{VIDEO_A}"),
        tmp_path / "rate-out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=5,
        request_budget=5,
        transport=rate_limited,
        collected_at=COLLECTED_AT,
    )
    assert rate.report.stopped_reason == "rate_limit"
    assert len(rate_calls) == 1


@pytest.mark.synthetic
def test_missing_credentials_invalid_urls_and_dry_run_write_nothing(tmp_path: Path) -> None:
    called = False

    def transport(_url: str) -> tuple[int, dict[str, object]]:
        nonlocal called
        called = True
        raise AssertionError("transport must not be called")

    video_file = _videos(tmp_path / "videos.txt", f"https://www.youtube.com/watch?v={VIDEO_A}")
    with pytest.raises(Exception, match="YOUTUBE_API_KEY"):
        collect_youtube_comments(
            video_file,
            tmp_path / "missing-key",
            api_key="",
            author_salt=SALT,
            document_limit=1,
            request_budget=1,
            transport=transport,
        )
    with pytest.raises(Exception, match="AUTHOR_SALT"):
        collect_youtube_comments(
            video_file,
            tmp_path / "missing-salt",
            api_key=API_KEY,
            author_salt="",
            document_limit=1,
            request_budget=1,
            transport=transport,
        )
    with pytest.raises(YoutubeCollectionError):
        collect_youtube_comments(
            _videos(tmp_path / "bad.txt", "https://example.com/not-a-video"),
            tmp_path / "bad-out",
            api_key=API_KEY,
            author_salt=SALT,
            document_limit=1,
            request_budget=1,
            transport=transport,
        )
    dry = collect_youtube_comments(
        video_file,
        tmp_path / "dry-out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=3,
        request_budget=4,
        dry_run=True,
        transport=transport,
    )

    assert called is False
    assert dry.report.dry_run is True
    assert dry.report.requests_made == 0
    assert dry.report.documents_written == 0
    assert not (tmp_path / "missing-key").exists()
    assert not (tmp_path / "missing-salt").exists()
    assert not (tmp_path / "bad-out").exists()
    assert not (tmp_path / "dry-out").exists()


def _settings(monkeypatch: pytest.MonkeyPatch, path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    monkeypatch.delenv("AUTHOR_SALT", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    settings = load_settings(env_file=path)
    monkeypatch.setattr(main, "load_settings", lambda: settings)


@pytest.mark.synthetic
def test_cli_dry_run_and_missing_key_make_no_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(_url: str) -> tuple[int, dict[str, object]]:
        raise AssertionError("live transport")

    monkeypatch.setattr("src.collect.youtube.default_transport", explode)
    _settings(
        monkeypatch,
        tmp_path / "creds.env",
        f"AUTHOR_SALT={SALT}\nYOUTUBE_API_KEY={API_KEY}\n",
    )
    videos = _videos(tmp_path / "videos.txt", f"https://www.youtube.com/live/{VIDEO_A}")
    output = tmp_path / "cli-out"
    code = main.main(
        [
            "collect",
            "--youtube",
            "--videos",
            str(videos),
            "--output",
            str(output),
            "--document-limit",
            "10",
            "--request-budget",
            "5",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "YouTube dry-run" in captured.out
    assert "requests made        0" in captured.out
    assert API_KEY not in captured.out
    assert API_KEY not in captured.err
    assert SALT not in captured.out
    assert not output.exists()

    _settings(monkeypatch, tmp_path / "nosecret.env", f"AUTHOR_SALT={SALT}\n")
    missing = main.main(
        [
            "collect",
            "--youtube",
            "--videos",
            str(videos),
            "--output",
            str(tmp_path / "no-key"),
            "--document-limit",
            "10",
            "--request-budget",
            "5",
        ]
    )
    missing_out = capsys.readouterr()
    assert missing == 1
    assert "YOUTUBE_API_KEY" in missing_out.err
    assert API_KEY not in missing_out.err
    assert not (tmp_path / "no-key").exists()


@pytest.mark.synthetic
def test_request_uses_published_plain_text_and_not_the_id_filter(tmp_path: Path) -> None:
    fake = FakeYouTube(
        {
            ("commentThreads", "first"): (200, {"items": [_thread("only", "one comment", 0)]}),
        }
    )
    _collect(tmp_path, fake, document_limit=5, request_budget=2)
    query = parse_qs(urlsplit(fake.calls[0]).query)
    assert query["part"] == ["snippet"]
    assert query["moderationStatus"] == ["published"]
    assert query["textFormat"] == ["plainText"]
    assert query["order"] == ["time"]
    assert query["videoId"] == [VIDEO_A]
    assert "id" not in query
    assert "relevance" not in query
    assert "extract" not in query


@pytest.mark.synthetic
def test_seed_comments_are_ignored(tmp_path: Path) -> None:
    videos = tmp_path / "videos.txt"
    videos.write_text(
        "# curated without search.list\nhttps://www.youtube.com/watch?v=abcdefghijk\n",
        encoding="utf-8",
    )
    result = collect_youtube_comments(
        videos,
        tmp_path / "out",
        api_key=API_KEY,
        author_salt=SALT,
        document_limit=1,
        request_budget=1,
        dry_run=True,
        collected_at=COLLECTED_AT,
    )
    assert result.report.dry_run is True
    assert result.report.videos_in_file == 1
    assert result.report.requests_made == 0
    assert not (tmp_path / "out").exists()
