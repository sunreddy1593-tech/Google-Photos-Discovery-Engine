"""Public scheduled-run snapshot.

The file is a status record for the evaluator UI. It stores counts, source
links, and evidence excerpts. It does not store credentials, raw collection
files, or controls that start collection or a model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

POINTER_NAME = "CURRENT.json"
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "author_salt",
        "client_secret",
        "password",
        "raw_text",
        "secret",
        "token",
    }
)


class SnapshotPublishError(RuntimeError):
    """The new snapshot was not published. The previous pointer stays in place."""


def publish_snapshot(root: Path | str, payload: dict[str, Any]) -> Path:
    """Write one version, then point ``CURRENT.json`` at it.

    The pointer is replaced only after the version file exists. A failure
    leaves the previous pointer unchanged.
    """
    destination = Path(root)
    version = str(payload.get("snapshot_version") or "")
    if not version or any(character in version for character in "/\\"):
        raise SnapshotPublishError("snapshot version is not a safe path token")
    public = _public_payload(payload)
    version_dir = destination / "versions" / version
    if version_dir.exists():
        raise SnapshotPublishError("snapshot version already exists")
    version_dir.mkdir(parents=True)
    body_path = version_dir / "snapshot.json"
    body_path.write_text(
        json.dumps(public, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    pointer = {
        "snapshot_version": version,
        "snapshot_file": f"versions/{version}/snapshot.json",
    }
    temporary = destination / "CURRENT.json.tmp"
    temporary.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination / POINTER_NAME)
    return destination / POINTER_NAME


def read_snapshot_version(root: Path | str) -> str:
    """Version named by the current pointer. Empty when nothing is published."""
    pointer_path = Path(root) / POINTER_NAME
    if not pointer_path.is_file():
        return ""
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    version = payload.get("snapshot_version")
    return version if isinstance(version, str) else ""


def load_snapshot(root: Path | str) -> dict[str, Any]:
    """Read the current snapshot. A bad pointer does not invent counts."""
    destination = Path(root)
    pointer_path = destination / POINTER_NAME
    if not pointer_path.is_file():
        return {
            "ok": False,
            "message": "No scheduled processing snapshot has been published.",
        }
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {"ok": False, "message": "Scheduled snapshot pointer could not be read."}
    if not isinstance(pointer, dict):
        return {"ok": False, "message": "Scheduled snapshot pointer is invalid."}
    relative = pointer.get("snapshot_file")
    version = pointer.get("snapshot_version")
    if not isinstance(relative, str) or not isinstance(version, str):
        return {"ok": False, "message": "Scheduled snapshot pointer is invalid."}
    path = _contained(destination, relative)
    if path is None or not path.is_file():
        return {"ok": False, "message": "Scheduled snapshot file is missing."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {"ok": False, "message": "Scheduled snapshot file could not be read."}
    if not isinstance(payload, dict):
        return {"ok": False, "message": "Scheduled snapshot file is invalid."}
    public = _public_payload(payload)
    public["ok"] = True
    public["snapshot_version"] = version
    return public


def _contained(root: Path, relative: str) -> Path | None:
    if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        return None
    path = (root / relative).resolve()
    root_resolved = root.resolve()
    if path == root_resolved or root_resolved not in path.parents:
        return None
    return path


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop secret-shaped keys and keep new cases unapproved."""
    public = _strip(payload)
    if not isinstance(public, dict):
        raise SnapshotPublishError("snapshot payload is not an object")
    public["human_approved_cases"] = 0
    cases = public.get("unreviewed_cases")
    if isinstance(cases, list):
        cleaned: list[dict[str, Any]] = []
        for item in cases:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["semantically_approved"] = False
            row["awaiting_semantic_review"] = True
            row["enters_approved_comparison"] = False
            cleaned.append(row)
        public["unreviewed_cases"] = cleaned
    return public


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip(item)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_KEYS
        }
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value
