"""Select or package public snapshots without touching collection or providers."""
from __future__ import annotations

from pathlib import Path

from src.export.privacy import leak_findings
from src.export.scheduled_status import load_snapshot, publish_snapshot, read_snapshot_version

KINDS = ("scheduled-snapshot", "reference-standard-snapshot")
CLOUD_FOLDER = "cloud-snapshots"
CLOUD_NOTE = (
    "Saved deployment snapshot. The scheduler runs on the owner's computer; "
    "Refresh reloads published files. Later local runs appear here only after "
    "updated public snapshots are deployed. Next-run times are those recorded in this snapshot."
)


def snapshot_root(project: Path, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError("Unsupported snapshot kind")
    public = project / "data" / "exports" / "public"
    local = public / kind
    return local if load_snapshot(local).get("ok") else public / CLOUD_FOLDER / kind


def is_cloud_snapshot(root: Path) -> bool:
    return root.parent.name == CLOUD_FOLDER


def prepare_cloud_snapshots(project: Path, destination: Path | None = None) -> dict[str, str]:
    """Validate both saved public inputs before publishing either deployment copy.

    Only current snapshot bodies are copied. Each pointer uses the existing
    atomic writer; private runs, source text and credentials are never read.
    """
    public = project / "data" / "exports" / "public"
    target = destination or public / CLOUD_FOLDER
    payloads = {}
    for kind in KINDS:
        payload = load_snapshot(public / kind)
        if not payload.get("ok"):
            raise ValueError(f"Missing usable public snapshot: {kind}")
        payload.pop("ok", None)
        if leak_findings(payload):
            raise ValueError(f"Public snapshot failed privacy checks: {kind}")
        payloads[kind] = payload
    for kind, payload in payloads.items():
        root = target / kind
        version = payload["snapshot_version"]
        if read_snapshot_version(root) == version:
            existing = load_snapshot(root)
            existing.pop("ok", None)
            if existing != payload:
                raise ValueError(f"Immutable deployment snapshot differs: {kind}")
            continue
        publish_snapshot(root, payload)
    return {kind: payload["snapshot_version"] for kind, payload in payloads.items()}
