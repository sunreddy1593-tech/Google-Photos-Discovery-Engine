"""Prompt lock for a live holdout classification.

The artifact stores configuration and hashes. It does not store human labels,
notes, or document text. Development classification does not need a lock.
Holdout classification needs the lock and an explicit unlock.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.ids import sha256_hex
from src.core.versions import SCHEMA_VERSION, prompt_version
from src.relevance.prompts import PROMPT_ID, render_relevance_prompt
from src.relevance.split import SPLIT_DEVELOPMENT, SPLIT_HOLDOUT

LOCK_VERSION = "relevance-prompt-lock/v1"
PLACEHOLDER_DOC_ID = "doc-id"
PLACEHOLDER_AUDIT = "audit-text"
FORBIDDEN_LOCK_KEYS = frozenset(
    {
        "human_scope_class",
        "human_reason_code",
        "human_notes",
        "expected_label",
        "expected_scope",
        "privacy_safe_excerpt",
        "raw_text",
        "raw_text_audit",
    }
)


class HoldoutLocked(ValueError):
    """A live holdout classification is not authorized."""


def prompt_template_hash() -> str:
    """Hash the prompt skeleton. The placeholders are not corpus text."""
    rendered = render_relevance_prompt(
        doc_id=PLACEHOLDER_DOC_ID,
        raw_text_audit=PLACEHOLDER_AUDIT,
    )
    return sha256_hex(rendered)


def build_prompt_lock(
    *,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    transmitted_schema_sha256: str | None = None,
) -> dict[str, object]:
    """Configuration metadata for one frozen relevance prompt.

    ``transmitted_schema_sha256`` is the digest of the schema template this
    provider sends. For Groq that is the strict conversion, without a
    document-specific ``doc_id`` enum. The per-document digest belongs in the
    request cache, not in a reusable holdout lock.
    """
    lock: dict[str, object] = {
        "lock_version": LOCK_VERSION,
        "frozen": True,
        "prompt_id": PROMPT_ID,
        "prompt_version": prompt_version(PROMPT_ID),
        "prompt_hash": prompt_template_hash(),
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if transmitted_schema_sha256:
        lock["transmitted_schema_sha256"] = transmitted_schema_sha256
    return lock


def write_prompt_lock(path: Path | str, lock: dict[str, object]) -> None:
    destination = Path(path)
    _require_lock_shape(lock)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(lock, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_prompt_lock(path: Path | str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HoldoutLocked("prompt lock must be a JSON object")
    _require_lock_shape(payload)
    return payload


def authorize_live_classification(
    *,
    split_name: str,
    holdout_unlocked: bool,
    lock_path: Path | str | None,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    transmitted_schema_sha256: str | None = None,
) -> str:
    """Allow development as-is. Holdout and all require a matching lock."""
    if split_name not in {SPLIT_DEVELOPMENT, SPLIT_HOLDOUT, "all"}:
        raise HoldoutLocked(f"unknown split {split_name!r}")
    if split_name == SPLIT_DEVELOPMENT:
        return split_name
    if not holdout_unlocked:
        raise HoldoutLocked(
            "live holdout classification requires an explicit holdout unlock"
        )
    if lock_path is None or not Path(lock_path).is_file():
        raise HoldoutLocked("live holdout classification requires a prompt-lock artifact")
    lock = load_prompt_lock(lock_path)
    if lock.get("frozen") is not True:
        raise HoldoutLocked("prompt lock is not frozen")
    if lock.get("prompt_id") != PROMPT_ID or lock.get("prompt_version") != prompt_version(
        PROMPT_ID
    ):
        raise HoldoutLocked("prompt id and version are not the frozen relevance prompt")
    if lock.get("prompt_hash") != prompt_template_hash():
        raise HoldoutLocked("prompt hash does not match the current relevance prompt")
    if lock.get("provider") != provider or lock.get("model") != model:
        raise HoldoutLocked("prompt lock provider or model does not match this run")
    if lock.get("temperature") != temperature or lock.get("max_tokens") != max_tokens:
        raise HoldoutLocked("prompt lock decoding parameters do not match this run")
    if provider == "groq":
        stored_schema = lock.get("transmitted_schema_sha256")
        if (
            not isinstance(stored_schema, str)
            or not stored_schema
            or stored_schema != transmitted_schema_sha256
        ):
            raise HoldoutLocked("prompt lock transmitted schema does not match this run")
    return split_name


def _require_lock_shape(lock: dict[str, object]) -> None:
    leaked = FORBIDDEN_LOCK_KEYS.intersection(lock)
    if leaked:
        raise HoldoutLocked(
            "prompt lock contains label or text fields: " + ", ".join(sorted(leaked))
        )
    required = (
        "lock_version",
        "frozen",
        "prompt_id",
        "prompt_version",
        "prompt_hash",
        "provider",
        "model",
        "temperature",
        "max_tokens",
    )
    missing = [key for key in required if key not in lock]
    if missing:
        raise HoldoutLocked("prompt lock is missing " + ", ".join(missing))
    if lock["lock_version"] != LOCK_VERSION:
        raise HoldoutLocked(f"prompt lock version must be {LOCK_VERSION}")
