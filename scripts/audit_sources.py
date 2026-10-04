"""Count collected documents by source and tier. This script does not fetch pages."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def audit(paths: list[Path], *, threshold: float = 0.40) -> dict[str, object]:
    platforms: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            platforms[str(row.get("source_platform") or "unknown")] += 1
            tiers[str(row.get("evidence_tier") or "unknown")] += 1
    total = sum(platforms.values())
    shares = {name: count / total for name, count in platforms.items()} if total else {}
    over = [name for name, share in shares.items() if share > threshold]
    return {
        "documents": total,
        "by_platform": dict(platforms),
        "by_tier": dict(tiers),
        "concentration_over_threshold": over,
        "source_types": len(platforms),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit collected JSONL files.")
    parser.add_argument("--input", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    report = audit(args.input)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
