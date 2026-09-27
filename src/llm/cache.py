"""Content-addressed response cache.

Entries live under ``data/interim/cache/{prompt_id}/{cache_key}.json``. A hit
returns the stored raw response and must not call a provider. The file holds
the request, the raw response, the provider, the model, and a timestamp. It
does not hold an API key, a salt, or an author hash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class CacheSecretError(RuntimeError):
    """A cache write included a secret. The file is not written."""


@dataclass(frozen=True)
class CacheEntry:
    """One stored call, enough to replay the parse without the provider."""

    cache_key: str
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    schema_version: str
    ruleset_version: str | None
    content_hash: str
    decoding_params: dict[str, Any]
    request_text: str
    raw_response: str
    input_tokens: int
    output_tokens: int
    cached_at: str


class ResponseCache:
    """Read and write cache files. Corrupt files are misses, not crashes."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path_for(self, prompt_id: str, cache_key: str) -> Path:
        safe_id = prompt_id.replace("/", "_")
        return self.root / safe_id / f"{cache_key}.json"

    def read(self, prompt_id: str, cache_key: str) -> CacheEntry | None:
        path = self.path_for(prompt_id, cache_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return CacheEntry(
                cache_key=str(payload["cache_key"]),
                provider=str(payload["provider"]),
                model=str(payload["model"]),
                prompt_id=str(payload["prompt_id"]),
                prompt_version=str(payload["prompt_version"]),
                schema_version=str(payload["schema_version"]),
                ruleset_version=payload.get("ruleset_version"),
                content_hash=str(payload["content_hash"]),
                decoding_params=dict(payload.get("decoding_params") or {}),
                request_text=str(payload.get("request_text") or ""),
                raw_response=str(payload["raw_response"]),
                input_tokens=int(payload.get("input_tokens") or 0),
                output_tokens=int(payload.get("output_tokens") or 0),
                cached_at=str(payload.get("cached_at") or ""),
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def write(
        self,
        entry: CacheEntry,
        *,
        denylist: tuple[str, ...] = (),
    ) -> None:
        payload: dict[str, Any] = {
            "cache_key": entry.cache_key,
            "provider": entry.provider,
            "model": entry.model,
            "prompt_id": entry.prompt_id,
            "prompt_version": entry.prompt_version,
            "schema_version": entry.schema_version,
            "ruleset_version": entry.ruleset_version,
            "content_hash": entry.content_hash,
            "decoding_params": entry.decoding_params,
            "request_text": entry.request_text,
            "raw_response": entry.raw_response,
            "input_tokens": entry.input_tokens,
            "output_tokens": entry.output_tokens,
            "cached_at": entry.cached_at,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        for secret in denylist:
            if secret and secret in blob:
                raise CacheSecretError("refusing to store a secret in the response cache")
        path = self.path_for(entry.prompt_id, entry.cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob + "\n", encoding="utf-8")


def now_stamp(moment: datetime) -> str:
    return moment.isoformat()


def decoding_params(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): mapping[key] for key in sorted(mapping)}
