"""Deployment snapshot copies and local/Cloud selection, entirely offline."""
from pathlib import Path

import pytest
from src.export.cloud_snapshots import KINDS, prepare_cloud_snapshots, snapshot_root
from src.export.scheduled_status import load_snapshot, publish_snapshot, read_snapshot_version


def sources(root: Path, version: str = "one") -> None:
    for kind in KINDS:
        publish_snapshot(root / "data/exports/public" / kind,
                         {"snapshot_version": version, "new_documents": 3,
                          "reference_version": "n8n-reviewed-reference/01"})


def test_current_public_snapshots_copied_and_idempotent(tmp_path):
    sources(tmp_path)
    versions = prepare_cloud_snapshots(tmp_path)
    assert set(versions) == set(KINDS)
    assert prepare_cloud_snapshots(tmp_path) == versions
    for kind in KINDS:
        cloud = tmp_path / "data/exports/public/cloud-snapshots" / kind
        assert read_snapshot_version(cloud) == "one"
        assert load_snapshot(cloud)["human_approved_cases"] == 0
        assert len(list((cloud / "versions").iterdir())) == 1


def test_cloud_fallback_without_local_inputs(tmp_path):
    cloud = tmp_path / "data/exports/public/cloud-snapshots/scheduled-snapshot"
    publish_snapshot(cloud, {"snapshot_version": "cloud"})
    assert snapshot_root(tmp_path, "scheduled-snapshot") == cloud
    sources(tmp_path)
    assert snapshot_root(tmp_path, "scheduled-snapshot") == tmp_path / "data/exports/public/scheduled-snapshot"


def test_missing_or_private_input_keeps_previous_snapshot(tmp_path):
    sources(tmp_path)
    prepare_cloud_snapshots(tmp_path)
    source = tmp_path / "data/exports/public/reference-standard-snapshot"
    publish_snapshot(source, {"snapshot_version": "private", "author_name": "Private author"})
    with pytest.raises(ValueError, match="privacy"):
        prepare_cloud_snapshots(tmp_path)
    for kind in KINDS:
        assert read_snapshot_version(tmp_path / "data/exports/public/cloud-snapshots" / kind) == "one"


def test_missing_input_does_not_publish_half_package(tmp_path):
    publish_snapshot(tmp_path / "data/exports/public/scheduled-snapshot", {"snapshot_version": "one"})
    with pytest.raises(ValueError, match="Missing"):
        prepare_cloud_snapshots(tmp_path)
    assert not (tmp_path / "data/exports/public/cloud-snapshots").exists()


def test_bad_local_pointer_uses_cloud(tmp_path):
    sources(tmp_path)
    prepare_cloud_snapshots(tmp_path)
    (tmp_path / "data/exports/public/scheduled-snapshot/CURRENT.json").write_text("broken")
    assert snapshot_root(tmp_path, "scheduled-snapshot").parent.name == "cloud-snapshots"


def test_new_snapshot_keeps_previous_version(tmp_path):
    sources(tmp_path)
    prepare_cloud_snapshots(tmp_path)
    sources(tmp_path, "two")
    prepare_cloud_snapshots(tmp_path)
    for kind in KINDS:
        cloud = tmp_path / "data/exports/public/cloud-snapshots" / kind
        assert read_snapshot_version(cloud) == "two"
        assert (cloud / "versions/one/snapshot.json").is_file()
