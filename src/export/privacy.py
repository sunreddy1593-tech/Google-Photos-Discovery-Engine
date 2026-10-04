"""Scan a prepared export for fields and patterns that must not leave the machine."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)"
)
_SECRET_MARKERS = (
    "GROQ_API_KEY",
    "YOUTUBE_API_KEY",
    "ANTHROPIC_API_KEY",
    "AUTHOR_SALT",
    "sk-ant-",
    "AIza",
)
_FORBIDDEN_KEYS = frozenset(
    {
        "raw_text",
        "raw_text_audit",
        "author_hash",
        "author_salt_id",
        "author_name",
        "author_name_raw",
        "provider_diagnostic",
        "raw_response_ref",
        "validation_errors",
        "error_message",
        "gate_errors",
        "request_identity",
        "prompt",
        "human_notes",
        "credentials",
        "api_key",
    }
)


def leak_findings(payload: object, *, where: str = "$") -> list[str]:
    """Return human-readable findings. An empty list means the scan passed."""
    found: list[str] = []
    _walk(payload, where, found)
    return found


def _walk(payload: object, where: str, found: list[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FORBIDDEN_KEYS:
                found.append(f"{where}.{key} is not allowed in a prepared export")
            _walk(value, f"{where}.{key}", found)
        return
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            _walk(value, f"{where}[{index}]", found)
        return
    if isinstance(payload, str):
        if _EMAIL.search(payload):
            found.append(f"{where} contains an email address")
        if _PHONE.search(payload):
            found.append(f"{where} contains a phone number")
        for marker in _SECRET_MARKERS:
            if marker in payload:
                found.append(f"{where} contains {marker}")
