"""Publish the automated comparison snapshot from saved outputs only.

Reads the immutable human-reviewed reference, the prepared public export and
any saved scheduled sub-batches. Makes no model, collector, webhook or
spreadsheet request. Publication is atomic; an unchanged snapshot is left as is.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.export.reference_standard_build import build_automated_snapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, default=None)
    parser.add_argument("--snapshot-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="assess and report without publishing")
    args = parser.parse_args(argv)
    outcome = build_automated_snapshot(
        ROOT,
        reference_dir=args.reference_dir,
        snapshot_root=args.snapshot_root,
        publish=not args.dry_run,
    )
    payload = outcome.get("payload") or {}
    print(
        json.dumps(
            {
                "ok": outcome.get("ok"),
                "published": outcome.get("published"),
                "snapshot_version": outcome.get("snapshot_version") or payload.get("snapshot_version"),
                "message": outcome.get("message"),
                "counts": payload.get("counts"),
                "sources_read": payload.get("sources_read"),
                "requests_made": 0,
            },
            indent=2,
        )
    )
    return 0 if outcome.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
