"""Local canonical URLs (spec Section 15.6).

Heavier than ``source_url_key``, and still offline. Share-link hosts are
rewritten when the rewrite is a string substitution. Redirects that need a
network lookup are left unresolved: a network call cannot be part of a
deterministic rerun.

Tracking parameters are removed. Identifiers that distinguish one comment or
reply from another — YouTube ``v`` and ``lc``, a support-forum ``msgid`` — stay.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.core.ids import TRACKING_PARAMS

_YOUTUBE_HOSTS: frozenset[str] = frozenset(
    {"m.youtube.com", "music.youtube.com", "www.youtube.com", "youtube.com"}
)
_REDDIT_HOSTS: frozenset[str] = frozenset(
    {"old.reddit.com", "m.reddit.com", "np.reddit.com", "www.reddit.com"}
)


def canonical_url(url: str) -> str:
    """Return one stable form of ``url``.

    Hosts are lowercased and a leading ``www.`` is removed. Known mobile and
    share hosts are folded onto the canonical host. The fragment is dropped.
    ``utm_*`` and the import-time tracking set are dropped. Remaining query
    keys are sorted.
    """
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    path = parts.path or ""
    query_pairs = list(parse_qsl(parts.query, keep_blank_values=True))

    if host.startswith("www."):
        host = host[4:]

    if host == "youtu.be":
        video_id = path.strip("/")
        host = "youtube.com"
        path = "/watch"
        query_pairs = [("v", video_id), *query_pairs]
    elif host in _YOUTUBE_HOSTS:
        host = "youtube.com"
        if path.startswith("/shorts/"):
            video_id = path.strip("/").split("/", 1)[-1]
            path = "/watch"
            query_pairs = [("v", video_id), *query_pairs]
    elif host in _REDDIT_HOSTS or host == "reddit.com":
        host = "reddit.com"

    kept = [
        (key, value)
        for key, value in query_pairs
        if not _is_tracking(key) and key
    ]
    query = urlencode(sorted(kept))
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, query, ""))


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_PARAMS
