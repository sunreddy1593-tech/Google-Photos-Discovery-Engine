"""Build the immutable human-reviewed n8n reference from saved local exports.

Reads two already-saved CSV snapshots and writes one fresh, versioned folder.
It makes no request to n8n, Google Sheets, a webhook or a model, and it does
not import any collection or integration module.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.export.reviewed_reference import REFERENCE_VERSION, build_reviewed_reference  # noqa: E402

PRIMARY = ROOT / "n8n" / "discovery_sheet_template - insights.csv"
CROSS_CHECK = ROOT / "data" / "insights_seed.csv"
DESTINATION = ROOT / "data" / "exports" / "reference" / REFERENCE_VERSION.replace("/", "-")

OWNER_STATEMENT = (
    "I have personally reviewed the existing 48 n8n threads in detail, including their "
    "relevance, classifications, summaries and evidence quotes. Record that review as the "
    "approval basis for those exact records. Future records should be classified using that "
    "standard without requiring individual human approval before appearing in a clearly "
    "labelled automated comparison."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, default=PRIMARY, help="saved 48-row insights export")
    parser.add_argument("--cross-check", type=Path, default=CROSS_CHECK, help="saved superset snapshot")
    parser.add_argument("--destination", type=Path, default=DESTINATION)
    parser.add_argument("--expected-count", type=int, default=48)
    parser.add_argument("--recorded-on", default="2026-10-05")
    args = parser.parse_args(argv)
    metadata = build_reviewed_reference(
        args.primary,
        args.destination,
        approval={
            "owner": "Sunayana",
            "statement": OWNER_STATEMENT,
            "given_in": "implementation conversation of 2026-10-05 authorising the reviewed n8n reference standard",
            "recorded_on": args.recorded_on,
        },
        created_at=datetime.now(timezone.utc),
        expected_count=args.expected_count,
        cross_check_csv=args.cross_check,
        root=ROOT,
    )
    print(
        json.dumps(
            {
                "reference_version": metadata["reference_version"],
                "records": metadata["records"],
                "count_matches_owner_statement": metadata["count_matches_owner_statement"],
                "count_discrepancy": metadata["count_discrepancy"],
                "snapshot_rows_not_covered_by_review": metadata["cross_check"].get("snapshot_rows_not_covered_by_review"),
                "destination": str(args.destination),
                "requests_made": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
