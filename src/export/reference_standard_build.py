"""Build the automated comparison snapshot from saved outputs.

Inputs are files that already exist on disk: the immutable human-reviewed
reference, prepared public export folders, and scheduled sub-batch outputs.
The scheduled outputs are turned into public records by the existing export
builder, so the same evidence gate, privacy scan and holdout exclusion apply.
No model, collector, webhook or spreadsheet is called here.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.export.build import build_submission
from src.export.load import browser_cards, load_submission
from src.export.privacy import leak_findings
from src.export.reference_standard import (
    assess_dataset,
    build_standard_payload,
    publish_standard_snapshot,
    reference_doc_index,
)
from src.export.reviewed_reference import load_reviewed_reference

DEFAULT_REFERENCE_DIR = Path("data/exports/reference/n8n-reviewed-reference-01")
DEFAULT_SNAPSHOT_ROOT = Path("data/exports/public/reference-standard-snapshot")
DEFAULT_WORK_DIR = Path("data/interim/reference-standard")
DEFAULT_SCHEDULED_ROOT = Path("data/interim/scheduled-runs")
#: Same precedence as the Streamlit app: the local demo export when it exists.
DEFAULT_PREPARED_EXPORTS = (
    Path("data/exports/submission/demo-2026-10-04-03"),
    Path("data/exports/submission"),
)
DEFAULT_FROZEN_SPLIT = Path("data/interim/phase4/relevance_split_manifest.csv")


def default_prepared_exports(root: Path) -> tuple[Path, ...]:
    """First prepared export that exists, in the app's precedence order."""
    for relative in DEFAULT_PREPARED_EXPORTS:
        if (root / relative / "index.json").is_file():
            return (root / relative,)
    return ()


def discover_scheduled_datasets(scheduled_root: Path, root: Path) -> list[dict[str, Any]]:
    """Dataset specs for every saved scheduled sub-batch with a relevance stage.

    A sub-batch that never reached relevance has nothing to classify and is
    not listed. The specs point at saved files only, relative to ``root``.
    """
    specs: list[dict[str, Any]] = []

    def _relative(path: Path) -> str:
        return _relative_to_root(root, path)

    if not scheduled_root.is_dir():
        return specs
    for run_dir in sorted(path for path in scheduled_root.iterdir() if path.is_dir()):
        manifest = _read_json(run_dir / "parent_manifest.json")
        pins = manifest.get("pins") if isinstance(manifest.get("pins"), dict) else {}
        for sub in sorted(path for path in run_dir.glob("sub-*") if path.is_dir()):
            relevance = sub / "relevance" / "relevance_decisions.jsonl"
            if not relevance.is_file():
                continue
            extract_dir = sub / "extract"
            extraction_manifest = _read_json(extract_dir / "run_manifest.json")
            run_id = str(extraction_manifest.get("run_id") or f"{run_dir.name}-{sub.name}-no-extraction")
            dataset_id = f"scheduled-{run_dir.name}-{sub.name}"
            reviews = [
                _relative(path)
                for path in (extract_dir / "review_queue.jsonl", sub / "relevance" / "review_queue.jsonl")
                if path.is_file()
            ]
            specs.append(
                {
                    "dataset_id": dataset_id,
                    "description": (
                        f"Scheduled run {run_dir.name}, {sub.name}. Collected by the bounded scheduler; "
                        "classified and extracted by the existing stages; not individually reviewed."
                    ),
                    "split_policy": "outside_frozen_split",
                    "collected": _relative(sub / "collected_documents.jsonl"),
                    "derived": _relative(sub / "normalize" / "documents_derived.jsonl"),
                    "links": _relative(sub / "normalize" / "duplicate_links.jsonl"),
                    "labels": None,
                    "relevance": _relative(relevance),
                    "reviews": reviews,
                    "corrections": None,
                    "extraction_run": {"run_id": run_id, "path": _relative(extract_dir)},
                    "limitations": [
                        "Collected by the bounded scheduler and not individually reviewed by a person.",
                        "Holdout documents are excluded by the export builder.",
                    ],
                    "pins": dict(pins),
                }
            )
    return specs


def prepare_scheduled_export(
    root: Path,
    *,
    scheduled_root: Path,
    work_dir: Path,
    frozen_split: Path,
) -> tuple[Path | None, dict[str, dict[str, Any]]]:
    """Run the existing export builder over saved scheduled sub-batches.

    Returns the prepared folder and the scheduler pins per dataset id. With no
    sub-batch to export the folder is ``None`` and nothing is written.
    """
    specs = discover_scheduled_datasets(scheduled_root, root)
    if not specs:
        return None, {}
    pins = {spec["dataset_id"]: spec.pop("pins") for spec in specs}
    manifest = {
        "submission_id": "scheduled-runs",
        "frozen_split": _relative_to_root(root, frozen_split),
        "not_combined": [
            "Scheduled sub-batches are exported one by one. They are not merged with the pilot datasets."
        ],
        "datasets": specs,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "scheduled_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    prepared = work_dir / "prepared"
    staging = work_dir / "prepared.building"
    if staging.exists():
        shutil.rmtree(staging)
    build_submission(manifest_path, staging, root=root)
    if prepared.exists():
        shutil.rmtree(prepared)
    staging.rename(prepared)
    return prepared, pins


def build_automated_snapshot(
    root: Path,
    *,
    reference_dir: Path | None = None,
    snapshot_root: Path | None = None,
    work_dir: Path | None = None,
    scheduled_root: Path | None = None,
    prepared_exports: tuple[Path, ...] | None = None,
    frozen_split: Path | None = None,
    pins: dict[str, Any] | None = None,
    now: datetime | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Assess every saved public record against the standard and publish.

    The reference must load and verify; otherwise nothing is published and the
    previous snapshot stays current.
    """
    root = root.resolve()
    reference_dir = _abs(root, reference_dir or DEFAULT_REFERENCE_DIR)
    snapshot_root = _abs(root, snapshot_root or DEFAULT_SNAPSHOT_ROOT)
    work_dir = _abs(root, work_dir or DEFAULT_WORK_DIR)
    scheduled_root = _abs(root, scheduled_root or DEFAULT_SCHEDULED_ROOT)
    frozen_split = _abs(root, frozen_split or DEFAULT_FROZEN_SPLIT)
    exports = (
        tuple(_abs(root, path) for path in prepared_exports)
        if prepared_exports is not None
        else default_prepared_exports(root)
    )
    moment = now or datetime.now(timezone.utc)

    standard = load_reviewed_reference(reference_dir)
    if not standard.get("ok"):
        return {
            "published": False,
            "ok": False,
            "message": f"human-reviewed reference did not verify: {standard.get('message')}",
        }
    index = reference_doc_index(standard["records"])
    seen: set[str] = set()
    datasets: list[dict[str, Any]] = []
    sources_read: list[str] = []

    prepared, scheduled_pins = prepare_scheduled_export(
        root, scheduled_root=scheduled_root, work_dir=work_dir, frozen_split=frozen_split
    )
    folders = [path for path in exports if (path / "index.json").is_file()]
    if prepared is not None:
        folders.append(prepared)
    for folder in folders:
        loaded = load_submission(folder)
        if not loaded.get("ok"):
            continue
        sources_read.append(_relative_to_root(root, folder))
        for key, dataset in loaded["datasets"].items():
            summary = dataset.get("summary") or {}
            dataset_id = str(summary.get("dataset_id") or key)
            run_id = str(summary.get("run_id") or "")
            dataset_pins = dict(pins or {})
            dataset_pins.update(scheduled_pins.get(dataset_id, {}))
            prompt_by_case = {
                str(case.get("case_id")): str(case.get("prompt_version") or "")
                for case in dataset.get("cases", [])
            }
            cards = browser_cards(dataset)
            for card in cards:
                version = prompt_by_case.get(str(card.get("case_id")))
                if version:
                    card["prompt_version"] = version
            datasets.append(
                assess_dataset(
                    cards,
                    reference_version=standard["reference_version"],
                    reference_index=index,
                    pins=dataset_pins,
                    dataset_id=dataset_id,
                    run_id=run_id,
                    seen_case_ids=seen,
                )
            )
    payload = build_standard_payload(
        standard=standard,
        datasets=datasets,
        pins=dict(pins or {}),
        built_at=moment.isoformat(),
    )
    payload["sources_read"] = sources_read
    findings = leak_findings(payload)
    if findings:
        return {"published": False, "ok": False, "message": "privacy scan failed:\n" + "\n".join(findings)}
    result: dict[str, Any] = {"ok": True, "payload": payload, "published": False}
    if publish:
        result.update(publish_standard_snapshot(snapshot_root, payload))
    return result


def refresh_after_scheduled_run(root: Path) -> dict[str, Any]:
    """Best-effort refresh used by the scheduler after it publishes its own snapshot.

    Errors are returned, never raised, so a snapshot problem cannot fail or
    restart a scheduled run.
    """
    try:
        outcome = build_automated_snapshot(root)
    except Exception as exc:  # noqa: BLE001 - the scheduler must keep its own status
        return {"ok": False, "published": False, "message": f"{exc.__class__.__name__}: {exc}"}
    return {key: outcome.get(key) for key in ("ok", "published", "snapshot_version", "message")}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _abs(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path
