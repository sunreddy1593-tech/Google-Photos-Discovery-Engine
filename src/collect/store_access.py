"""Access and bounded HTTP for the two fixed store routes; no bypass switches.

No live review route has passed the 2026-10-01 access audit. Implementing an
adapter does not change that finding. Approval requires a reviewed code/doc
change with source evidence; credentials or library installation cannot enable it.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit


USER_AGENT = "PhotoRetrievalResearch/0.1 (public feedback research)"
PRODUCT_TOKEN = "PhotoRetrievalResearch"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class StoreStop(Exception):
    """A public reason code, never a server body, author, or exception detail."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Route:
    source: str
    app_id: str
    origin: str
    path: str
    access_status: str = "blocked"
    permission_reference: str | None = None
    reason: str = "audited_robots_restriction"


# A source-specific permission reference AND a current robots check are needed.
# These defaults deliberately cannot be overridden by a CLI flag or env variable.
ROUTES = {
    "play_store": Route(
        "play_store", "com.google.android.apps.photos", "https://play.google.com",
        "/_/PlayStoreUi/data/batchexecute",
    ),
    "app_store": Route(
        "app_store", "962194608", "https://itunes.apple.com",
        "/{country}/rss/customerreviews/page={page}/id=962194608/sortby=mostrecent/json",
    ),
}


@dataclass(frozen=True)
class Response:
    status: int
    body: str


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def default_transport(method: str, url: str, body: bytes | None) -> Response:
    """Exactly one HTTP request, no redirects, proxies, cookies, or retries."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/plain"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise StoreStop("response_too_large")
            return Response(response.status, raw.decode("utf-8-sig"))
    except urllib.error.HTTPError as exc:
        # Do not retain/print the error body or follow Location.
        status = exc.code
        exc.close()
        return Response(status, "")
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
        raise StoreStop("transport_error") from None


def check_response(response: Response) -> None:
    if response.status in {401, 403, 429}:
        raise StoreStop(f"access_http_{response.status}")
    if 300 <= response.status < 400:
        raise StoreStop("redirect_refused")
    if response.status != 200:
        raise StoreStop(f"http_{response.status}")
    head = response.body.lstrip()[:8192].lower()
    if head.startswith(("<!doctype html", "<html")) or any(
        marker in head for marker in ("cf-chl-", "cf_chl_", "checking your browser", "<form")
    ):
        raise StoreStop("challenge_or_html_response")


def _normal_path(value: str) -> str:
    """Normalize encoded unreserved ASCII; refuse unsupported rule encodings."""
    if not value.isascii() or re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise StoreStop("robots_unsupported_encoding")
    def decode(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if re.fullmatch(r"[A-Za-z0-9._~-]", char) else match.group(0).upper()
    return re.sub(r"%([0-9a-fA-F]{2})", decode, value)


def robots_delay_or_raise(text: str, url: str) -> float:
    """Conservative gate for fixed ASCII store URLs, not a general crawler.

    Supports wildcard paths and end anchors. Any matching Disallow in a wildcard
    or matching-agent group wins, even over Allow. That is deliberately stricter
    than RFC 9309 precedence. Unsupported/malformed policy fails closed.
    """
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise StoreStop("robots_malformed")
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not value or not re.fullmatch(r"[A-Za-z0-9_.*-]+", value):
                raise StoreStop("robots_malformed")
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key in {"allow", "disallow", "crawl-delay"}:
            if not agents:
                raise StoreStop("robots_malformed")
            rules.append((key, value))
        elif key not in {"sitemap", "host"}:
            raise StoreStop("robots_unsupported_directive")
    groups.append((agents, rules))
    parts = urlsplit(url)
    target = _normal_path(parts.path + ("?" + parts.query if parts.query else ""))
    delay = 3.0
    for group_agents, group_rules in groups:
        if not any(agent == "*" or agent in PRODUCT_TOKEN.lower() for agent in group_agents):
            continue
        for key, pattern in group_rules:
            if key == "crawl-delay":
                if not re.fullmatch(r"\d+(\.\d+)?", pattern):
                    raise StoreStop("robots_malformed")
                delay = max(delay, float(pattern))
                if delay > 60:
                    raise StoreStop("robots_delay_exceeds_run_limit")
            elif pattern:
                if not pattern.startswith("/"):
                    raise StoreStop("robots_malformed")
                normalized = _normal_path(pattern)
                anchored = normalized.endswith("$")
                if anchored:
                    normalized = normalized[:-1]
                regex = "^" + re.escape(normalized).replace(r"\*", ".*")
                if anchored:
                    regex += "$"
                if key == "disallow" and re.search(regex, target):
                    raise StoreStop("robots_disallowed")
    return delay
