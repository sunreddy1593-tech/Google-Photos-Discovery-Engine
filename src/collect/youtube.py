"""Read-only YouTube comment collection into ``CollectedDocument`` records.

Official surface, checked 2026-10-01:

* ``commentThreads.list`` — published threads for one ``videoId``. Quota cost 1.
  ``https://developers.google.com/youtube/v3/docs/commentThreads/list``
* ``comments.list`` with ``parentId`` — replies to one top-level comment. Quota
  cost 1. Replies are one level deep.
  ``https://developers.google.com/youtube/v3/docs/comments/list``
* A thread's ``replies.comments`` list is only a subset unless its length equals
  ``snippet.totalReplyCount``. This collector does not read that subset. It
  marks replies complete only when ``totalReplyCount`` is 0, or when
  ``comments.list`` pagination returns no ``nextPageToken``.
  ``https://developers.google.com/youtube/v3/docs/commentThreads``

The ``id`` filter is not used. Google documents it as Google+-only.

No relevance classification and no extraction run from this module.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, ConfigDict

from src.collect.workbook import _reject_forbidden_keys
from src.core.errors import ConfigError, ValidationError
from src.core.ids import author_hash, author_salt_id, doc_id, raw_text_sha256, sha256_hex, source_url_key
from src.core.logging import get_logger
from src.models.collected_document import CollectedDocument
from src.models.enums import CollectionMethod, EvidenceTier, SourcePlatform, SourceType

API_ORIGIN: str = "https://www.googleapis.com/youtube/v3"
THREAD_METHOD: str = "commentThreads"
COMMENT_METHOD: str = "comments"
MAX_RESULTS: int = 100
SOURCE_NAME: str = "YouTube"
TEXT_FORM: str = "api_plain_text_display"

_QUOTA_REASONS: frozenset[str] = frozenset({"quotaExceeded", "dailyLimitExceeded"})
_RATE_REASONS: frozenset[str] = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
_YOUTUBE_HOSTS: frozenset[str] = frozenset(
    {"youtube.com", "m.youtube.com", "music.youtube.com"}
)
_VIDEO_ID_CHARS: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)

Transport = Callable[[str], tuple[int, dict[str, Any]]]


class YoutubeCollectionError(ValidationError):
    """The video list or a limit is unusable. No request should be made."""


class _Stop(Exception):
    """The run must stop. ``reason`` is a report code, not a provider body."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _VideoSkip(Exception):
    """This video cannot supply comments. Other videos may continue."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


class YoutubeThreadReport(BaseModel):
    """Reply completeness for one thread in this run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str
    top_level_comment_id: str
    total_reply_count: int
    reply_pages_fetched: int
    replies_written: int
    replies_already_present: int
    replies_complete: bool
    skipped_reason: str | None = None


class YoutubeVideoReport(BaseModel):
    """What this run did with one seed video. No comment text and no authors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    outcome: str
    requests: int
    documents_written: int
    documents_already_present: int
    thread_pages_fetched: int
    reply_pages_fetched: int
    replies_complete: bool | None = None
    threads: tuple[YoutubeThreadReport, ...] = ()


class YoutubeRunReport(BaseModel):
    """Count summary for one collection run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collector: str = "youtube_comments"
    api: str = "youtube_data_api_v3"
    methods: tuple[str, ...] = ("commentThreads.list", "comments.list")
    text_format: str = "plainText"
    moderation_status: str = "published"
    dry_run: bool
    videos_in_file: int
    requests_made: int
    request_budget: int
    document_limit: int
    documents_written: int
    documents_already_present: int
    stopped_reason: str | None = None
    videos: tuple[YoutubeVideoReport, ...] = ()


@dataclass(frozen=True)
class YoutubeCollection:
    """In-memory result. Dry-run leaves the output paths unset."""

    report: YoutubeRunReport
    documents_path: Path | None = None
    report_path: Path | None = None


@dataclass(frozen=True)
class _Seed:
    video_id: str
    source_url: str


@dataclass
class _Pending:
    """One comment held until this thread's reply walk finishes or stops."""

    comment: dict[str, Any]
    is_reply: bool


@dataclass
class _Run:
    client: _Client
    known: set[str]
    documents_path: Path
    document_limit: int
    author_salt: str
    salt_id: str
    batch_id: str
    collected_at: datetime
    written: int = 0
    already: int = 0
    stop_reason: str | None = None
    _held: list[_Pending] = field(default_factory=list)
    _interrupted_thread: YoutubeThreadReport | None = None
    _reply_pages: int = 0

    def collect_video(self, seed: _Seed) -> YoutubeVideoReport:
        requests_before = self.client.made
        written_before = self.written
        already_before = self.already
        self._interrupted_thread = None
        threads: list[YoutubeThreadReport] = []
        thread_pages = 0
        reply_pages = 0
        page_token: str | None = None
        try:
            while True:
                self._ensure_request_room()
                payload = self.client.get(THREAD_METHOD, _thread_params(seed.video_id, page_token))
                thread_pages += 1
                items = payload.get("items")
                if not isinstance(items, list):
                    raise _Stop("api_error")
                for item in items:
                    if not isinstance(item, dict):
                        raise _Stop("api_error")
                    report, pages = self._collect_thread(seed, item)
                    threads.append(report)
                    reply_pages += pages
                token = payload.get("nextPageToken")
                if not isinstance(token, str) or not token:
                    break
                page_token = token
        except _VideoSkip as exc:
            return self._video_report(
                seed,
                outcome=exc.outcome,
                threads=threads,
                thread_pages=thread_pages,
                reply_pages=reply_pages,
                requests_before=requests_before,
                written_before=written_before,
                already_before=already_before,
                replies_complete=False if threads else None,
            )
        except _Stop as exc:
            self.stop_reason = exc.reason
            if self._interrupted_thread is not None:
                threads.append(self._interrupted_thread)
                self._interrupted_thread = None
            started = (
                thread_pages > 0
                or self.written > written_before
                or self.client.made > requests_before
            )
            return self._video_report(
                seed,
                outcome="partial" if started else "not_started",
                threads=threads,
                thread_pages=thread_pages,
                reply_pages=reply_pages,
                requests_before=requests_before,
                written_before=written_before,
                already_before=already_before,
                replies_complete=False if started else None,
            )
        included = [thread for thread in threads if thread.skipped_reason is None]
        complete = all(thread.replies_complete for thread in included)
        return self._video_report(
            seed,
            outcome="collected",
            threads=threads,
            thread_pages=thread_pages,
            reply_pages=reply_pages,
            requests_before=requests_before,
            written_before=written_before,
            already_before=already_before,
            replies_complete=complete,
        )

    def _collect_thread(
        self, seed: _Seed, item: dict[str, Any]
    ) -> tuple[YoutubeThreadReport, int]:
        snippet = item.get("snippet")
        if not isinstance(snippet, dict):
            raise _Stop("api_error")
        thread_id = item.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise _Stop("api_error")
        if snippet.get("isPublic") is False:
            return (
                YoutubeThreadReport(
                    thread_id=thread_id,
                    top_level_comment_id="",
                    total_reply_count=0,
                    reply_pages_fetched=0,
                    replies_written=0,
                    replies_already_present=0,
                    replies_complete=False,
                    skipped_reason="not_public",
                ),
                0,
            )
        top = snippet.get("topLevelComment")
        if not isinstance(top, dict):
            raise _Stop("api_error")
        total = snippet.get("totalReplyCount")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise _Stop("api_error")
        parent_id = _comment_id(top)
        self._held = []
        self._reply_pages = 0
        self._hold(top, is_reply=False)
        already_at_replies = self.already
        complete = total == 0
        try:
            if total > 0:
                self._hold_replies(parent_id)
                complete = True
        except _Stop:
            replies_written = sum(1 for item in self._held if item.is_reply)
            replies_already_present = self.already - already_at_replies
            self._flush(
                seed,
                thread_id,
                total,
                self._reply_pages,
                replies_complete=False,
            )
            self._interrupted_thread = YoutubeThreadReport(
                thread_id=thread_id,
                top_level_comment_id=parent_id,
                total_reply_count=total,
                reply_pages_fetched=self._reply_pages,
                replies_written=replies_written,
                replies_already_present=replies_already_present,
                replies_complete=False,
            )
            raise
        replies_written = sum(1 for item in self._held if item.is_reply)
        replies_already_present = self.already - already_at_replies
        self._flush(seed, thread_id, total, self._reply_pages, replies_complete=complete)
        return (
            YoutubeThreadReport(
                thread_id=thread_id,
                top_level_comment_id=parent_id,
                total_reply_count=total,
                reply_pages_fetched=self._reply_pages,
                replies_written=replies_written,
                replies_already_present=replies_already_present,
                replies_complete=complete,
            ),
            self._reply_pages,
        )

    def _hold_replies(self, parent_id: str) -> None:
        page_token: str | None = None
        while True:
            self._ensure_request_room()
            payload = self.client.get(COMMENT_METHOD, _reply_params(parent_id, page_token))
            self._reply_pages += 1
            items = payload.get("items")
            if not isinstance(items, list):
                raise _Stop("api_error")
            for item in items:
                if not isinstance(item, dict):
                    raise _Stop("api_error")
                self._hold(item, is_reply=True)
            token = payload.get("nextPageToken")
            if not isinstance(token, str) or not token:
                return
            page_token = token

    def _hold(self, comment: dict[str, Any], *, is_reply: bool) -> None:
        comment_id = _comment_id(comment)
        if comment_id in self.known or any(
            _comment_id(item.comment) == comment_id for item in self._held
        ):
            self.already += 1
            return
        snippet = comment.get("snippet")
        if not isinstance(snippet, dict):
            raise _Stop("api_error")
        text = snippet.get("textDisplay")
        if not isinstance(text, str) or not text.strip():
            return
        if self.written + len(self._held) >= self.document_limit:
            raise _Stop("document_limit")
        self._held.append(_Pending(comment=comment, is_reply=is_reply))

    def _flush(
        self,
        seed: _Seed,
        thread_id: str,
        total_reply_count: int,
        reply_pages_fetched: int,
        *,
        replies_complete: bool,
    ) -> None:
        for pending in self._held:
            self._write(
                seed,
                pending.comment,
                thread_id=thread_id,
                total_reply_count=None if pending.is_reply else total_reply_count,
                reply_pages_fetched=None if pending.is_reply else reply_pages_fetched,
                replies_complete=None if pending.is_reply else replies_complete,
            )
        self._held = []

    def _ensure_request_room(self) -> None:
        if self.written + len(self._held) >= self.document_limit:
            raise _Stop("document_limit")

    def _write(
        self,
        seed: _Seed,
        comment: dict[str, Any],
        *,
        thread_id: str,
        total_reply_count: int | None,
        reply_pages_fetched: int | None,
        replies_complete: bool | None,
    ) -> None:
        comment_id = _comment_id(comment)
        snippet = comment["snippet"]
        assert isinstance(snippet, dict)
        text = snippet["textDisplay"]
        assert isinstance(text, str)
        parent = snippet.get("parentId")
        parent_comment_id = parent if isinstance(parent, str) and parent else None
        identity = _author_identity(snippet)
        hashed = (
            author_hash(self.author_salt, SourcePlatform.youtube.value, identity)
            if identity is not None
            else None
        )
        metadata: dict[str, Any] = {
            "video_id": seed.video_id,
            "thread_id": thread_id,
            "parent_comment_id": parent_comment_id,
            "text_form": TEXT_FORM,
        }
        if total_reply_count is not None:
            metadata["total_reply_count"] = total_reply_count
            metadata["reply_pages_fetched"] = reply_pages_fetched
            metadata["replies_complete"] = replies_complete
        permalink = f"https://www.youtube.com/watch?v={seed.video_id}&lc={comment_id}"
        like_count = snippet.get("likeCount")
        engagement = (
            {"like_count": like_count}
            if isinstance(like_count, int) and not isinstance(like_count, bool)
            else None
        )
        document = CollectedDocument(
            doc_id=doc_id(SourcePlatform.youtube.value, source_item_id=comment_id),
            ingest_batch_id=self.batch_id,
            source_platform=SourcePlatform.youtube,
            source_type=SourceType.video_comment,
            evidence_tier=EvidenceTier.direct_user,
            source_item_id=comment_id,
            parent_thread_id=thread_id,
            source_url=permalink,  # type: ignore[arg-type]
            source_url_key=source_url_key(permalink),
            source_name=SOURCE_NAME,
            title=None,
            author_hash=hashed,
            author_salt_id=self.salt_id,
            published_at=_published_at(snippet.get("publishedAt")),
            collected_at=self.collected_at,
            language_reported=None,
            raw_text=text,
            raw_text_sha256=raw_text_sha256(text),
            collection_query=seed.source_url,
            collection_method=CollectionMethod.api,
            rating=None,
            engagement=engagement,
            metadata=metadata,
        )
        _append_document(self.documents_path, document)
        self.known.add(comment_id)
        self.written += 1

    def _video_report(
        self,
        seed: _Seed,
        *,
        outcome: str,
        threads: list[YoutubeThreadReport],
        thread_pages: int,
        reply_pages: int,
        requests_before: int,
        written_before: int,
        already_before: int,
        replies_complete: bool | None,
    ) -> YoutubeVideoReport:
        return YoutubeVideoReport(
            video_id=seed.video_id,
            outcome=outcome,
            requests=self.client.made - requests_before,
            documents_written=self.written - written_before,
            documents_already_present=self.already - already_before,
            thread_pages_fetched=thread_pages,
            reply_pages_fetched=reply_pages,
            replies_complete=replies_complete,
            threads=tuple(threads),
        )


class _Client:
    def __init__(self, *, api_key: str, transport: Transport, request_budget: int) -> None:
        self._api_key = api_key
        self._transport = transport
        self._budget = request_budget
        self.made = 0

    def get(self, method: str, params: dict[str, str]) -> dict[str, Any]:
        if self.made >= self._budget:
            raise _Stop("request_budget")
        query = dict(params)
        query["key"] = self._api_key
        url = f"{API_ORIGIN}/{method}?{urlencode(query)}"
        self.made += 1
        try:
            status, payload = self._transport(url)
        except _Stop:
            raise
        except Exception as exc:
            raise _Stop("transport_error") from exc
        if status == 200:
            return payload
        reason = _error_reason(payload)
        if reason == "commentsDisabled":
            raise _VideoSkip("comments_disabled")
        if reason == "videoNotFound":
            raise _VideoSkip("video_unavailable")
        if reason in _QUOTA_REASONS:
            raise _Stop("quota")
        if reason in _RATE_REASONS or status == 429:
            raise _Stop("rate_limit")
        raise _Stop("api_error")


def default_transport(url: str) -> tuple[int, dict[str, Any]]:
    """GET one API URL. The URL contains the key and must not be logged."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            raw = response.read()
        time.sleep(0.2)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    except urllib.error.URLError as exc:
        raise _Stop("transport_error") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _Stop("transport_error") from exc
    if not isinstance(payload, dict):
        raise _Stop("api_error")
    return status, payload


def collect_youtube_comments(
    video_file: Path | str,
    output_dir: Path | str,
    *,
    api_key: str,
    author_salt: str,
    document_limit: int,
    request_budget: int,
    dry_run: bool = False,
    transport: Transport | None = None,
    collected_at: datetime | None = None,
) -> YoutubeCollection:
    """Collect published comments for the video URLs in ``video_file``.

    Credentials, the video file, and both limits are checked before any request
    and before the output directory is created. Dry-run returns a plan and
    writes nothing.
    """
    if not api_key:
        raise ConfigError(
            "YOUTUBE_API_KEY is not set but is required for YouTube comment "
            "collection. Add it to .env (see .env.example)."
        )
    if not author_salt:
        raise ConfigError(
            "AUTHOR_SALT is not set but is required for author hashing at "
            "YouTube collection. Add it to .env (see .env.example)."
        )
    if document_limit < 1:
        raise YoutubeCollectionError("document_limit must be at least 1")
    if request_budget < 1:
        raise YoutubeCollectionError("request_budget must be at least 1")

    source = Path(video_file)
    if not source.is_file():
        raise FileNotFoundError(source)
    file_text = source.read_text(encoding="utf-8")
    seeds = _parse_video_file(file_text)
    stamp = collected_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise YoutubeCollectionError("collected_at must be timezone-aware")

    if dry_run:
        return YoutubeCollection(
            report=YoutubeRunReport(
                dry_run=True,
                videos_in_file=len(seeds),
                requests_made=0,
                request_budget=request_budget,
                document_limit=document_limit,
                documents_written=0,
                documents_already_present=0,
                videos=tuple(_not_started(seed) for seed in seeds),
            )
        )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    documents_path = destination / "collected_documents.jsonl"
    run = _Run(
        client=_Client(
            api_key=api_key,
            transport=transport or default_transport,
            request_budget=request_budget,
        ),
        known=_existing_source_ids(documents_path),
        documents_path=documents_path,
        document_limit=document_limit,
        author_salt=author_salt,
        salt_id=author_salt_id(author_salt),
        batch_id=f"youtube-{sha256_hex(file_text)[:12]}",
        collected_at=stamp,
    )
    videos: list[YoutubeVideoReport] = []
    for index, seed in enumerate(seeds):
        if run.written >= document_limit:
            run.stop_reason = run.stop_reason or "document_limit"
            videos.extend(_not_started(item) for item in seeds[index:])
            break
        videos.append(run.collect_video(seed))
        if run.stop_reason:
            videos.extend(_not_started(item) for item in seeds[index + 1 :])
            break

    report = YoutubeRunReport(
        dry_run=False,
        videos_in_file=len(seeds),
        requests_made=run.client.made,
        request_budget=request_budget,
        document_limit=document_limit,
        documents_written=run.written,
        documents_already_present=run.already,
        stopped_reason=run.stop_reason,
        videos=tuple(videos),
    )
    report_path = destination / "youtube_collection_report.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    get_logger("collect.youtube").info(
        "youtube collection finished",
        extra={
            "requests_made": report.requests_made,
            "documents_written": report.documents_written,
            "stopped_reason": report.stopped_reason,
        },
    )
    return YoutubeCollection(
        report=report,
        documents_path=documents_path,
        report_path=report_path,
    )


def _not_started(seed: _Seed) -> YoutubeVideoReport:
    return YoutubeVideoReport(
        video_id=seed.video_id,
        outcome="not_started",
        requests=0,
        documents_written=0,
        documents_already_present=0,
        thread_pages_fetched=0,
        reply_pages_fetched=0,
        replies_complete=None,
    )


def _parse_video_file(text: str) -> list[_Seed]:
    seeds: list[_Seed] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            video_id = _video_id(line)
        except ValueError as exc:
            raise YoutubeCollectionError(
                f"line {line_number} is not a public YouTube video URL"
            ) from exc
        if video_id in seen:
            continue
        seen.add(video_id)
        seeds.append(_Seed(video_id=video_id, source_url=line))
    if not seeds:
        raise YoutubeCollectionError("the video file has no YouTube video URLs")
    return seeds


def _video_id(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(url)
    host = parts.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/", 1)[0]
    elif host in _YOUTUBE_HOSTS:
        segments = [segment for segment in parts.path.split("/") if segment]
        query = {
            key: value
            for key, _, value in (item.partition("=") for item in parts.query.split("&") if item)
        }
        if not segments or segments[0] == "watch":
            candidate = query.get("v", "")
        elif segments[0] in {"shorts", "embed", "live"} and len(segments) >= 2:
            candidate = segments[1]
        else:
            raise ValueError(url)
    else:
        raise ValueError(url)
    if len(candidate) != 11 or any(character not in _VIDEO_ID_CHARS for character in candidate):
        raise ValueError(url)
    return candidate


def _existing_source_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    found: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise YoutubeCollectionError(
                f"existing collected_documents.jsonl line {line_number} is not JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise YoutubeCollectionError(
                f"existing collected_documents.jsonl line {line_number} is not an object"
            )
        item_id = payload.get("source_item_id")
        if isinstance(item_id, str) and item_id:
            found.add(item_id)
    return found


def _comment_id(comment: dict[str, Any]) -> str:
    comment_id = comment.get("id")
    if not isinstance(comment_id, str) or not comment_id:
        raise _Stop("api_error")
    return comment_id


def _author_identity(snippet: dict[str, Any]) -> str | None:
    """Stable channel id when YouTube provides one, otherwise the display name.

    The chosen value is hashed and discarded. Neither form is stored.
    """
    channel = snippet.get("authorChannelId")
    if isinstance(channel, dict):
        value = channel.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    name = snippet.get("authorDisplayName")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return None
    return parsed


def _thread_params(video_id: str, page_token: str | None) -> dict[str, str]:
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": str(MAX_RESULTS),
        "moderationStatus": "published",
        "order": "time",
        "textFormat": "plainText",
    }
    if page_token:
        params["pageToken"] = page_token
    return params


def _reply_params(parent_id: str, page_token: str | None) -> dict[str, str]:
    params = {
        "part": "snippet",
        "parentId": parent_id,
        "maxResults": str(MAX_RESULTS),
        "textFormat": "plainText",
    }
    if page_token:
        params["pageToken"] = page_token
    return params


def _error_reason(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    errors = error.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        reason = errors[0].get("reason")
        if isinstance(reason, str):
            return reason
    return ""


def _append_document(path: Path, document: CollectedDocument) -> None:
    payload = document.model_dump(mode="json")
    _reject_forbidden_keys(payload)
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def public_message(message: str, *secrets: str) -> str:
    """Remove credential values from a message before it is printed."""
    redacted = message
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted
