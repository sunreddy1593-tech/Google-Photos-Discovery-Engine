"""Run manifest for a Phase 4 execution.

The file records funnel counts, cache statistics, and token estimates. It does
not record secrets, author hashes, or absolute paths. ``generated_at`` is
volatile and is listed in the exclusion set the hasher already uses.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.hashing import VOLATILE_FIELDS
from src.core.versions import version_summary


def git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


def write_manifest(path: Path | str, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def manifest_payload(
    *,
    run_id: str,
    stages: list[str],
    dry_run: bool,
    offline: bool,
    config_hash: str,
    project_root: Path,
    funnel: dict[str, Any],
    cache: dict[str, int],
    tokens: dict[str, float | int],
    output_hashes: dict[str, str],
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "stages": stages,
        "dry_run": dry_run,
        "offline": offline,
        "versions": version_summary(),
        "config_hash": config_hash,
        "git_commit": git_commit(project_root),
        "funnel": funnel,
        "cache": cache,
        "tokens": tokens,
        "output_hashes": output_hashes,
        "volatile_fields_excluded": sorted(VOLATILE_FIELDS),
        "generated_at": generated_at.isoformat(),
    }
