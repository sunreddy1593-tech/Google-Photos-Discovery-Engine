"""Pure, strict parsers for inspected store formats; live compatibility unverified.

Wire references and limitations: STORE-COLLECTION.md. Original review body text
is retained verbatim. No raw response, author name, or developer reply is saved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from src.collect.store_access import Route, StoreStop


@dataclass(frozen=True)
class Review:
    native_id: str
    body: str
    author: str | None
    rating: int
    source_date: datetime | None
    title: str | None = None


def page_request(route: Route, country: str, language: str, page: int,
                 token: str | None, count: int) -> tuple[str, str, bytes | None]:
    if route.source == "app_store":
        return "GET", route.origin + route.path.format(country=country, page=page), None
    query = urlencode({"hl": language, "gl": country})
    window = [count] if token is None else [count, None, token]
    argument = [None, [2, 2, window, None, [None] * 9], [route.app_id, 7]]
    payload = [[["oCPfdb", json.dumps(argument), None, "generic"]]]
    body = urlencode({"f.req": json.dumps(payload)}).encode("utf-8")
    return "POST", route.origin + route.path + "?" + query, body


def _string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StoreStop("malformed_review")
    return value


def _rating(value: object) -> int:
    if isinstance(value, str) and value in {"1", "2", "3", "4", "5"}:
        return int(value)
    if type(value) is not int or not 1 <= value <= 5:
        raise StoreStop("malformed_review")
    return value


def _date(value: object) -> datetime | None:
    if value is None:
        return None
    date = datetime.fromisoformat(_string(value).replace("Z", "+00:00"))
    if date.utcoffset() is None:
        raise StoreStop("undated_timezone")
    return date.astimezone(UTC)


def _label(entry: dict, key: str) -> object:
    node = entry.get(key)
    if node is None:
        return None
    if not isinstance(node, dict) or "label" not in node:
        raise StoreStop("malformed_review")
    return node["label"]


def parse_apple(body: str) -> tuple[list[Review], str | None]:
    """Missing entry is ambiguous, not proof of an empty review corpus."""
    try:
        payload = json.loads(body)
        feed = payload["feed"]
        entries = feed["entry"]
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise StoreStop("malformed_page")
        reviews = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise StoreStop("malformed_review")
            if "im:rating" not in entry:
                # A known app-metadata entry may precede the reviews.
                if "im:name" in entry:
                    continue
                raise StoreStop("malformed_review")
            author = entry.get("author") or {}
            if not isinstance(author, dict):
                raise StoreStop("malformed_review")
            name = _label(author, "name")
            title = _label(entry, "title")
            reviews.append(Review(
                _string(_label(entry, "id")), _string(_label(entry, "content")),
                _string(name) if name is not None else None,
                _rating(_label(entry, "im:rating")), _date(_label(entry, "updated")),
                _string(title) if title is not None else None,
            ))
        return reviews, None
    except (ValueError, KeyError, TypeError, OverflowError):
        raise StoreStop("malformed_page") from None


def parse_play(body: str) -> tuple[list[Review], str | None]:
    """Read only the review RPC; reject unexpected framing or pagination types."""
    try:
        frames = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line == ")]}'" or line.isdigit():
                continue
            envelope = json.loads(line)
            if not isinstance(envelope, list):
                raise StoreStop("malformed_page")
            for frame in envelope:
                if isinstance(frame, list) and len(frame) >= 3 and frame[:2] == ["wrb.fr", "oCPfdb"]:
                    frames.append(frame)
        if len(frames) != 1:
            raise StoreStop("malformed_page")
        result = json.loads(frames[0][2])
        if not isinstance(result, list) or not result or not isinstance(result[0], list):
            raise StoreStop("malformed_page")
        token = None
        if len(result) > 1 and result[1] is not None:
            if not isinstance(result[1], list) or len(result[1]) < 2:
                raise StoreStop("malformed_pagination")
            token = result[1][1]
            if token is not None and (not isinstance(token, str) or not token):
                raise StoreStop("malformed_pagination")
        reviews = []
        for row in result[0]:
            if not isinstance(row, list) or len(row) < 6:
                raise StoreStop("malformed_review")
            author = row[1]
            if not isinstance(author, list) or not author:
                raise StoreStop("malformed_review")
            name = author[0]
            source_date = None
            timestamp = row[5]
            if timestamp is not None:
                if not isinstance(timestamp, list) or not 1 <= len(timestamp) <= 2:
                    raise StoreStop("malformed_review")
                seconds = timestamp[0]
                nanos = timestamp[1] if len(timestamp) == 2 else 0
                if type(seconds) is not int or type(nanos) is not int or not 0 <= nanos < 10**9:
                    raise StoreStop("malformed_review")
                source_date = datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=nanos // 1000)
            reviews.append(Review(
                _string(row[0]), _string(row[4]), _string(name) if name is not None else None,
                _rating(row[2]), source_date,
            ))
        return reviews, token
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, OSError):
        raise StoreStop("malformed_page") from None
