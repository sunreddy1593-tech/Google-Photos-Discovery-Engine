"""Validate completed annotation reviews and, when asked, emit gold JSONL.

An empty label directory prints pending. This does not write ``data/gold/``
and does not change the quality-gate reports.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.annotate import AnnotationError, emit_gold, validate_pack
from src.pipeline.extraction_development import holdout_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a development annotation pack.")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--emit", help="Directory for documents.jsonl and cases.jsonl")
    args = parser.parse_args(argv)
    frozen_holdout = holdout_ids()
    if args.emit:
        try:
            written = emit_gold(args.pack, args.emit, frozen_holdout)
        except AnnotationError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"emitted documents    {written}")
        print(f"gold directory       {args.emit}")
        return 0
    check = validate_pack(args.pack, frozen_holdout)
    print(f"documents            {check.documents}")
    print(f"reviews              {check.reviews}")
    if check.errors:
        for error in check.errors:
            print(error, file=sys.stderr)
        return 1
    if check.pending:
        print("status               pending")
        print("no completed reviews; gold files were not written")
        return 0
    print("status               reviews valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
