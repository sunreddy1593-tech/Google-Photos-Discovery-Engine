"""Read-only Reddit collection into ``CollectedDocument`` records.

Official read access needs a registered OAuth client even for read-only use.
The free tier allows 100 queries per minute per client id, averaged over a
10-minute window. Confirmed 2026-10-04 from the Reddit Data API Wiki
(https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki).
When ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, or ``REDDIT_USER_AGENT``
is missing, collection is skipped and the rest of a run can continue. A
rate-limit response stops this source and records ``rate_limited``.

``collect_reddit`` parses a recorded listing or a test transport and does not
open a socket. ``collect_reddit_live`` is the OAuth client. Tests pass a
transport callable and never use the urllib implementation.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode

from src.core.errors import ConfigError
from src.core.ids import author_hash, author_salt_id, doc_id, raw_text_sha256, source_url_key
from src.models.collected_document import CollectedDocument
from src.models.enums import CollectionMethod, EvidenceTier, SourcePlatform, SourceType

Transport = Callable[[str], tuple[int, dict[str, str], dict[str, Any]]]
LiveTransport = Callable[
    [str, str, dict[str, str], bytes | None],
    tuple[int, dict[str, str], Any],
]

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_ORIGIN = "https://oauth.reddit.com"
DEFAULT_SUBREDDIT = "googlephotos"
DEFAULT_QUERIES: tuple[str, ...] = (
    "google photos can't find photo",
    "google photos search not working",
)
_DELETED_AUTHORS = frozenset({"[deleted]", "[removed]"})
_REMOVED_BODIES = frozenset({"[removed]", "[deleted]"})


@dataclass(frozen=True)
class RedditReport:
    """One Reddit attempt. A skip writes no documents."""

    skipped: bool
    reason: str
    documents: tuple[CollectedDocument, ...] = ()
    requests_made: int = 0
    documents_already_present: int = 0
    stopped_reason: str | None = None


def credentials_present(
    client_id: str | None,
    client_secret: str | None,
    user_agent: str | None,
) -> bool:
    """All three official client fields are required. A partial set is absent."""
    return bool(client_id and client_secret and user_agent)


def collect_listing(
    listing: dict[str, Any],
    *,
    author_salt: str,
    collected_at: datetime,
    ingest_batch_id: str,
    collection_query: str | None = None,
) -> tuple[CollectedDocument, ...]:
    """Turn one recorded ``Listing`` payload into documents. Usernames are hashed."""
    children = ((listing.get("data") or {}).get("children") or [])
    documents: list[CollectedDocument] = []
    for child in children:
        data = child.get("data") or {}
        body = (data.get("selftext") or data.get("body") or "").strip()
        if body in _REMOVED_BODIES:
            body = ""
        title = (data.get("title") or "").strip()
        raw_text = "\n\n".join(part for part in (title, body) if part)
        if not raw_text:
            continue
        item_id = str(data.get("name") or data.get("id") or "")
        if not item_id:
            continue
        permalink = str(data.get("permalink") or "")
        if permalink.startswith("/"):
            url = f"https://www.reddit.com{permalink}"
        else:
            url = permalink or f"https://www.reddit.com/comments/{item_id}"
        username = str(data.get("author") or "")
        if username in _DELETED_AUTHORS:
            username = ""
        hashed = author_hash(author_salt, SourcePlatform.reddit.value, username) if username else None
        created = data.get("created_utc")
        published = (
            datetime.fromtimestamp(float(created), tz=timezone.utc) if created else None
        )
        text_hash = raw_text_sha256(raw_text)
        url_key = source_url_key(url)
        documents.append(
            CollectedDocument(
                doc_id=doc_id(
                    SourcePlatform.reddit.value,
                    source_item_id=item_id,
                    url_key=url_key,
                ),
                ingest_batch_id=ingest_batch_id,
                source_platform=SourcePlatform.reddit,
                source_type=SourceType.post if data.get("title") else SourceType.comment,
                evidence_tier=EvidenceTier.direct_user,
                source_item_id=item_id,
                parent_thread_id=str(data.get("link_id") or item_id),
                source_url=url,
                source_url_key=url_key,
                source_name=f"Reddit r/{data.get('subreddit') or 'unknown'}",
                title=title or None,
                author_hash=hashed,
                author_salt_id=author_salt_id(author_salt),
                published_at=published,
                collected_at=collected_at,
                raw_text=raw_text,
                raw_text_sha256=text_hash,
                collection_query=collection_query,
                collection_method=CollectionMethod.api,
            )
        )
    return tuple(documents)


def collect_reddit(
    *,
    client_id: str | None,
    client_secret: str | None,
    user_agent: str | None,
    author_salt: str,
    listing: dict[str, Any] | None = None,
    transport: Transport | None = None,
    path: str = "/r/googlephotos/new",
    collected_at: datetime | None = None,
    ingest_batch_id: str = "reddit-unexercised",
) -> RedditReport:
    """Skip when credentials are absent. Never opens a socket itself.

    ``listing`` is a recorded payload. ``transport`` is a test double that
    returns ``(status, headers, body)``. Neither path is a live exercise.
    """
    if not credentials_present(client_id, client_secret, user_agent):
        return RedditReport(
            skipped=True,
            reason="source disabled: Reddit credentials are absent",
        )
    moment = collected_at or datetime(2026, 10, 4, tzinfo=timezone.utc)
    if listing is not None:
        documents = collect_listing(
            listing,
            author_salt=author_salt,
            collected_at=moment,
            ingest_batch_id=ingest_batch_id,
        )
        return RedditReport(skipped=False, reason="recorded listing", documents=documents)
    if transport is None:
        return RedditReport(
            skipped=True,
            reason="Reddit credentials are present. This command does not call the API.",
        )
    status, headers, body = transport(path)
    remaining = headers.get("X-Ratelimit-Remaining") or headers.get("x-ratelimit-remaining")
    if status == 429 or remaining == "0":
        return RedditReport(
            skipped=False,
            reason="rate_limited",
            requests_made=1,
            stopped_reason="rate_limited",
        )
    if status >= 400:
        return RedditReport(
            skipped=False,
            reason="source_blocked",
            requests_made=1,
            stopped_reason="source_blocked",
        )
    documents = collect_listing(
        body,
        author_salt=author_salt,
        collected_at=moment,
        ingest_batch_id=ingest_batch_id,
    )
    return RedditReport(
        skipped=False,
        reason="transport",
        documents=documents,
        requests_made=1,
    )


class _StopLive(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def collect_reddit_live(
    *,
    client_id: str | None,
    client_secret: str | None,
    user_agent: str | None,
    author_salt: str,
    output_dir: Path | str,
    document_limit: int,
    request_budget: int,
    dry_run: bool = False,
    subreddit: str = DEFAULT_SUBREDDIT,
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    transport: LiveTransport | None = None,
    collected_at: datetime | None = None,
    ingest_batch_id: str = "reddit-live",
) -> RedditReport:
    """Collect posts and comments through the official OAuth API.

    A missing credential skips the source. ``transport`` replaces urllib in
    tests. The live client does not follow redirects and stops when the
    response says the rate-limit window is exhausted.
    """
    if not credentials_present(client_id, client_secret, user_agent):
        return RedditReport(
            skipped=True,
            reason="source disabled: Reddit credentials are absent",
        )
    if not author_salt:
        raise ConfigError(
            "AUTHOR_SALT is not set but is required for author hashing at "
            "Reddit collection. Add it to .env (see .env.example)."
        )
    if document_limit < 1:
        raise ValueError("document_limit must be at least 1")
    if request_budget < 1:
        raise ValueError("request_budget must be at least 1")
    moment = collected_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    if dry_run:
        return RedditReport(skipped=False, reason="dry_run", requests_made=0)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    documents_path = destination / "collected_documents.jsonl"
    known = _existing_ids(documents_path)
    caller = transport or _urllib_transport
    state = _LiveState(
        client_id=client_id or "",
        client_secret=client_secret or "",
        user_agent=user_agent or "",
        author_salt=author_salt,
        documents_path=documents_path,
        known=known,
        document_limit=document_limit,
        request_budget=request_budget,
        transport=caller,
        collected_at=moment,
        ingest_batch_id=ingest_batch_id,
        pace=transport is None,
    )
    try:
        state.authorize()
        state.collect_listings(subreddit, queries)
    except _StopLive as exc:
        state.stopped = exc.reason
    written = state.written
    report = RedditReport(
        skipped=False,
        reason=state.stopped or "collected",
        documents=tuple(state.new_documents),
        requests_made=state.requests_made,
        documents_already_present=state.already,
        stopped_reason=state.stopped,
    )
    (destination / "reddit_collection_report.json").write_text(
        json.dumps(
            {
                "collector": "reddit_data_api",
                "requests_made": report.requests_made,
                "documents_written": written,
                "documents_already_present": report.documents_already_present,
                "stopped_reason": report.stopped_reason,
                "skipped": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


@dataclass
class _LiveState:
    client_id: str
    client_secret: str
    user_agent: str
    author_salt: str
    documents_path: Path
    known: set[str]
    document_limit: int
    request_budget: int
    transport: LiveTransport
    collected_at: datetime
    ingest_batch_id: str
    pace: bool
    token: str = ""
    requests_made: int = 0
    written: int = 0
    already: int = 0
    stopped: str | None = None
    new_documents: list[CollectedDocument] | None = None

    def __post_init__(self) -> None:
        self.new_documents = []

    def authorize(self) -> None:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode("ascii")
        status, headers, payload = self._send(
            "POST",
            TOKEN_URL,
            {
                "Authorization": f"Basic {basic}",
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            b"grant_type=client_credentials",
        )
        self._stop_if_limited(status, headers, keep_body=False)
        if status >= 400 or not isinstance(payload, dict):
            raise _StopLive("source_blocked")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise _StopLive("source_blocked")
        self.token = token

    def collect_listings(self, subreddit: str, queries: tuple[str, ...]) -> None:
        paths = [f"/r/{subreddit}/new?limit=100&raw_json=1"]
        for query in queries:
            paths.append(
                "/r/"
                + subreddit
                + "/search?"
                + urlencode(
                    {
                        "q": query,
                        "restrict_sr": "1",
                        "sort": "new",
                        "limit": "100",
                        "raw_json": "1",
                    }
                )
            )
        post_ids: list[str] = []
        for path in paths:
            post_ids.extend(self._walk(path))
            if self.stopped:
                return
        for post_id in post_ids:
            if self.written >= self.document_limit:
                self.stopped = "document_limit"
                return
            self._walk(
                f"/r/{subreddit}/comments/{post_id}?limit=100&depth=1&raw_json=1&sort=new",
                paginate=False,
            )
            if self.stopped:
                return

    def _walk(self, path: str, *, paginate: bool = True) -> list[str]:
        found: list[str] = []
        after: str | None = None
        while True:
            if self.written >= self.document_limit:
                self.stopped = "document_limit"
                return found
            url = OAUTH_ORIGIN + path
            if after:
                url += "&after=" + quote(after, safe="")
            status, headers, payload = self._send(
                "GET",
                url,
                {
                    "Authorization": f"Bearer {self.token}",
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
                None,
            )
            self._stop_if_limited(status, headers, keep_body=True)
            if status != 200:
                raise _StopLive("source_blocked")
            documents = collect_listing(
                _as_listing(payload),
                author_salt=self.author_salt,
                collected_at=self.collected_at,
                ingest_batch_id=self.ingest_batch_id,
                collection_query=path.split("?", 1)[0],
            )
            for document in documents:
                if document.source_item_id in self.known:
                    self.already += 1
                    continue
                if self.written >= self.document_limit:
                    self.stopped = "document_limit"
                    return found
                _append_document(self.documents_path, document)
                self.known.add(document.source_item_id)
                self.written += 1
                assert self.new_documents is not None
                self.new_documents.append(document)
                if document.source_type is SourceType.post and document.source_item_id.startswith("t3_"):
                    found.append(document.source_item_id.removeprefix("t3_"))
            if not paginate or self.stopped:
                return found
            remaining = _remaining(headers)
            if remaining is not None and remaining <= 0:
                raise _StopLive("rate_limited")
            after = _after(payload)
            if not after:
                return found

    def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, str], Any]:
        if self.requests_made >= self.request_budget:
            raise _StopLive("request_budget")
        self.requests_made += 1
        status, response_headers, payload = self.transport(method, url, headers, body)
        if self.pace:
            time.sleep(0.6)
        return status, response_headers, payload

    @staticmethod
    def _stop_if_limited(status: int, headers: dict[str, str], *, keep_body: bool) -> None:
        remaining = _remaining(headers)
        if status == 429 or (remaining is not None and remaining <= 0 and not keep_body):
            raise _StopLive("rate_limited")


def _remaining(headers: dict[str, str]) -> float | None:
    raw = headers.get("X-Ratelimit-Remaining") or headers.get("x-ratelimit-remaining")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _after(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("after")
    if isinstance(token, str) and token:
        return token
    return None


def _as_listing(payload: Any) -> dict[str, Any]:
    """Flatten a listing or a comments-endpoint list into one listing."""
    children: list[Any] = []

    def take(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                take(item)
            return
        if not isinstance(value, dict):
            return
        data = value.get("data")
        if isinstance(data, dict) and isinstance(data.get("children"), list):
            children.extend(data["children"])

    take(payload)
    return {"data": {"children": children}}


def _existing_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        item_id = payload.get("source_item_id")
        if isinstance(item_id, str) and item_id:
            found.add(item_id)
    return found


def _append_document(path: Path, document: CollectedDocument) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(document.model_dump_json() + "\n")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> tuple[int, dict[str, str], Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            status = int(response.status)
            raw = response.read()
            response_headers = {key: value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
        response_headers = {key: value for key, value in exc.headers.items()} if exc.headers else {}
    except urllib.error.URLError as exc:
        raise _StopLive("source_blocked") from exc
    if not raw:
        return status, response_headers, {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _StopLive("source_blocked") from exc
    return status, response_headers, payload
