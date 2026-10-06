"""Automatic publication exercised against a synthetic local bare Git remote."""
from pathlib import Path
import json
import subprocess

import pytest

from src.export import cloud_publication as publication
from src.export.cloud_snapshots import KINDS, prepare_cloud_snapshots
from src.export.scheduled_status import publish_snapshot

CONFIG = {"enabled": True, "remote": publication.REMOTE, "branch": "main"}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def snapshots(root, version="one", day="2026-10-06", **extra):
    for kind in KINDS:
        publish_snapshot(root / "data/exports/public" / kind, {
            "snapshot_version": version, "reference_version": "reference/one",
            "last_run_at": f"{day}T14:00:00+05:30",
            "built_at": f"{day}T08:30:00+00:00", **extra,
        })


@pytest.fixture
def setup(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    git(seed, "config", "user.name", "Synthetic test")
    git(seed, "config", "user.email", "synthetic@example.test")
    (seed / "README.md").write_text("unchanged remote source")
    snapshots(seed)
    prepare_cloud_snapshots(seed)
    # Only the deployment copies belong to the synthetic remote.
    git(seed, "add", "README.md", publication.PUBLIC_PATH)
    git(seed, "commit", "-m", "Initial public fixture")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "origin", "main")
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "--initial-branch=main")
    git(project, "config", "user.name", "Synthetic test")
    git(project, "config", "user.email", "synthetic@example.test")
    git(project, "remote", "add", "origin", publication.REMOTE)
    (project / "notes.txt").write_text("User's unrelated staged work")
    git(project, "add", "notes.txt")
    snapshots(project, "two", "2026-10-07")
    original = publication._git
    calls = []

    def local_git(root, *args, **kwargs):
        calls.append((args, kwargs.get("stage")))
        if args[:3] == ("remote", "add", "origin"):
            args = (*args[:3], str(remote))
        return original(root, *args, **kwargs)

    monkeypatch.setattr(publication, "_git", local_git)
    return project, remote, calls, local_git


def test_publication_pushes_only_snapshots_and_leaves_user_index(setup):
    project, remote, calls, _ = setup
    staged_before = git(project, "diff", "--cached")
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert outcome["ok"] and outcome["published"], outcome
    changed = git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").splitlines()
    assert changed and all(publication._ALLOWED.fullmatch(path) for path in changed)
    assert git(remote, "show", "main:README.md") == "unchanged remote source"
    assert git(project, "diff", "--cached") == staged_before
    assert json.loads((project / "data/interim/cloud-publication/CURRENT.json").read_text())["status"] == "published"
    assert not list((project / "data/interim/cloud-publication").glob("checkout-*"))
    pushes = [args for args, _ in calls if args[0] == "push"]
    assert len(pushes) == 1 and all("--force" not in args for args, _ in calls)


def test_unchanged_inputs_do_not_commit_or_push(setup):
    project, remote, calls, _ = setup
    first = publication.publish_cloud_snapshots(project, config=CONFIG)
    calls.clear()
    second = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert first["published"] and second["status"] == "unchanged"
    assert not any(args[0] in {"commit", "push"} for args, _ in calls)


def test_rejected_push_preserves_remote_and_does_not_retry(setup, monkeypatch):
    project, remote, calls, local_git = setup
    before = git(remote, "rev-parse", "main")
    def reject(root, *args, **kwargs):
        if args[0] == "push":
            calls.append((args, kwargs.get("stage")))
            raise publication.PublicationError("push")
        return local_git(root, *args, **kwargs)
    monkeypatch.setattr(publication, "_git", reject)
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert not outcome["ok"] and outcome["stage"] == "push"
    assert git(remote, "rev-parse", "main") == before
    assert len([args for args, _ in calls if args[0] == "push"]) == 1


def test_privacy_failure_does_not_push(setup):
    project, remote, calls, _ = setup
    snapshots(project, "private", "2026-10-08", author_name="must not publish")
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert not outcome["ok"]
    assert not any(args[0] == "push" for args, _ in calls)


def test_newer_remote_is_not_rolled_back(setup):
    project, remote, calls, _ = setup
    assert publication.publish_cloud_snapshots(project, config=CONFIG)["published"]
    snapshots(project, "older", "2026-10-05")
    calls.clear()
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert outcome["status"] == "skipped_stale"
    assert not any(args[0] in {"commit", "push"} for args, _ in calls)


def test_concurrent_remote_commit_is_not_overwritten(setup, monkeypatch):
    project, remote, calls, local_git = setup
    seed = remote.parent / "seed"
    def concurrent(root, *args, **kwargs):
        if args[0] == "push":
            (seed / "README.md").write_text("concurrent user's commit")
            git(seed, "add", "README.md")
            git(seed, "commit", "-m", "Concurrent source edit")
            git(seed, "push", "origin", "main")
        return local_git(root, *args, **kwargs)
    monkeypatch.setattr(publication, "_git", concurrent)
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert outcome["stage"] == "push" and not outcome["published"]
    assert git(remote, "show", "main:README.md") == "concurrent user's commit"
    pointer = json.loads(git(remote, "show", f"main:{publication.PUBLIC_PATH}/{KINDS[0]}/CURRENT.json"))
    assert pointer["snapshot_version"] == "one"


def test_changed_reference_is_not_overwritten(setup):
    project, remote, calls, _ = setup
    snapshots(project, "different-reference", "2026-10-08", reference_version="reference/two")
    outcome = publication.publish_cloud_snapshots(project, config=CONFIG)
    assert outcome["status"] == "skipped_reference_change"
    assert not any(args[0] == "push" for args, _ in calls)


def test_disabled_and_wrong_destination_make_no_git_request(tmp_path, monkeypatch):
    monkeypatch.setattr(publication, "_git", lambda *a, **k: pytest.fail("Unexpected Git request"))
    assert publication.publish_cloud_snapshots(tmp_path, config={"enabled": False})["status"] == "disabled"
    bad = {**CONFIG, "remote": "https://unexpected.example/repo.git"}
    assert publication.publish_cloud_snapshots(tmp_path, config=bad)["stage"] == "unsupported_destination"


def test_missing_inputs_fail_before_git(tmp_path, monkeypatch):
    monkeypatch.setattr(publication, "_git", lambda *a, **k: pytest.fail("Unexpected Git request"))
    assert publication.publish_cloud_snapshots(tmp_path, config=CONFIG)["stage"] == "missing_public_snapshot"


def test_git_errors_do_not_expose_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(publication.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, stdout="secret credential", stderr="secret credential"))
    with pytest.raises(publication.PublicationError) as exc:
        publication._git(tmp_path, "fetch", stage="fetch")
    assert str(exc.value) == "fetch"


def test_launcher_uses_shared_queue():
    root = Path(__file__).resolve().parents[1]
    command = (root / "scripts/run_scheduled_discovery.cmd").read_text()
    assert "run_queued_discovery.py" in command
    assert command.rstrip().endswith("exit /b %ERRORLEVEL%")
