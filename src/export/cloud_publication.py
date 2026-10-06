"""Publish only saved public snapshots from an isolated Git checkout.

No collector, integration, model, private run or credential file is read.
The existing Git credential manager supplies authentication. Publication is
one regular push; a rejection is recorded and never force-pushed or retried.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import git_publication_environment
from src.export.cloud_snapshots import KINDS, prepare_cloud_snapshots
from src.export.scheduled_status import load_snapshot

PUBLIC_PATH = "data/exports/public/cloud-snapshots"
REMOTE = "https://github.com/sunreddy1593-tech/Google-Photos-Discovery-Engine.git"
_ALLOWED = re.compile(
    rf"^{PUBLIC_PATH}/(?:scheduled-snapshot|reference-standard-snapshot)/"
    r"(?:CURRENT\.json|versions/[A-Za-z0-9_-]+/snapshot\.json)$"
)


class PublicationError(RuntimeError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(stage)


def _git(root: Path, *arguments: str, stage: str = "git", allow_empty: bool = False) -> str:
    env = git_publication_environment()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError(stage) from exc
    if result.returncode and not (allow_empty and result.returncode == 1):
        raise PublicationError(stage)
    return result.stdout.strip()


def _newer(remote: dict, local: dict, field: str) -> bool:
    if not remote.get("ok"):
        return False
    try:
        return datetime.fromisoformat(remote[field]) > datetime.fromisoformat(local[field])
    except (KeyError, TypeError, ValueError):
        # A remote snapshot with an unknown date cannot safely be replaced by
        # a different snapshot whose age cannot be compared.
        return remote.get("snapshot_version") != local.get("snapshot_version")


def publish_cloud_snapshots(project: Path, *, config: dict[str, Any] | None = None) -> dict:
    """Non-throwing publication outcome with durable local status.

    The temporary checkout fetches the remote branch and checks out only the
    public snapshot subtree. It never stages or commits in the user's checkout.
    """
    project = project.resolve()
    state = project / "data/interim/cloud-publication"
    outcome: dict[str, Any] = {"ok": False, "published": False}
    try:
        settings = config if config is not None else json.loads(
            (project / "config/cloud_publication.json").read_text(encoding="utf-8")
        )
        if settings.get("enabled") is not True:
            outcome.update(ok=True, status="disabled")
            return outcome
        if settings.get("remote") != REMOTE or settings.get("branch") != "main":
            raise PublicationError("unsupported_destination")
        local_public = project / "data/exports/public"
        inputs = {kind: load_snapshot(local_public / kind) for kind in KINDS}
        if not all(payload.get("ok") for payload in inputs.values()):
            raise PublicationError("missing_public_snapshot")
        if _git(project, "remote", "get-url", "origin", stage="origin") != REMOTE:
            raise PublicationError("origin_mismatch")
        name = _git(project, "config", "--get", "user.name", stage="git_identity")
        email = _git(project, "config", "--get", "user.email", stage="git_identity")
        if not name or not email:
            raise PublicationError("git_identity")
        state.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="checkout-", dir=state) as directory:
            checkout = Path(directory)
            _git(checkout, "init", stage="init")
            _git(checkout, "sparse-checkout", "init", "--no-cone", stage="sparse_checkout")
            _git(checkout, "sparse-checkout", "set", "--no-cone", f"/{PUBLIC_PATH}/", stage="sparse_checkout")
            _git(checkout, "remote", "add", "origin", REMOTE, stage="remote")
            _git(checkout, "fetch", "--depth=1", "--filter=blob:none", "origin", "main", stage="fetch")
            _git(checkout, "checkout", "-b", "main", "FETCH_HEAD", stage="checkout")
            target = checkout / PUBLIC_PATH
            for kind, field in ((KINDS[0], "last_run_at"), (KINDS[1], "built_at")):
                remote = load_snapshot(target / kind)
                if kind == KINDS[1] and remote.get("ok") and remote.get("reference_version") != inputs[kind].get("reference_version"):
                    outcome.update(ok=True, status="skipped_reference_change")
                    return outcome
                if _newer(remote, inputs[kind], field):
                    outcome.update(ok=True, status="skipped_stale")
                    return outcome
            versions = prepare_cloud_snapshots(project, target)
            _git(checkout, "add", "--", PUBLIC_PATH, stage="stage")
            changed = _git(checkout, "diff", "--cached", "--name-only", stage="verify_paths").splitlines()
            if not changed:
                outcome.update(ok=True, status="unchanged", versions=versions)
                return outcome
            if any(not _ALLOWED.fullmatch(path) for path in changed):
                raise PublicationError("unexpected_path")
            _git(checkout, "diff", "--cached", "--check", stage="verify_diff")
            _git(checkout, "config", "user.name", name, stage="git_identity")
            _git(checkout, "config", "user.email", email, stage="git_identity")
            _git(checkout, "commit", "-m", "Update public discovery snapshots " + versions[KINDS[0]], stage="commit")
            commit = _git(checkout, "rev-parse", "HEAD", stage="commit_id")
            _git(checkout, "push", "origin", "HEAD:refs/heads/main", stage="push")
            outcome.update(ok=True, published=True, status="published", commit=commit, versions=versions)
    except PublicationError as exc:
        outcome.update(status="failed", stage=exc.stage)
    except Exception as exc:
        outcome.update(status="failed", stage="packaging", error_type=type(exc).__name__)
    finally:
        outcome["checked_at"] = datetime.now(timezone.utc).isoformat()
        try:
            state.mkdir(parents=True, exist_ok=True)
            pending = state / "CURRENT.json.tmp"
            pending.write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
            os.replace(pending, state / "CURRENT.json")
        except OSError:
            outcome["status_recorded"] = False
    return outcome
