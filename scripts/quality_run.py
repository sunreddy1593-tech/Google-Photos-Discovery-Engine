"""Run or freeze the bounded gold verification; legacy CLI behavior is unchanged."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import load_settings
from src.core.errors import ConfigError
from src.pipeline.quality import QualityBoundsError, create_freeze, run_quality


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bounded, separately frozen gold verification")
    parser.add_argument("--split", choices=("dev", "holdout"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--cache", type=Path, default=Path("data/interim/cache"))
    parser.add_argument("--call-budget", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--candidate-prompt", choices=("extract/v4", "extract/v5"),
                        help="Explicit extraction candidate. extract/v5 is gold-dev only. Legacy defaults remain unchanged")
    parser.add_argument("--candidate-relevance", choices=("relevance/v6",),
                        help="Explicit unmeasured relevance candidate; gold-dev only unless --successor-holdout is set")
    parser.add_argument("--successor-holdout", action="store_true",
                        help="New holdout experiment using both candidates; does not reuse the consumed freeze")
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--pack", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--freeze-out", type=Path)
    parser.add_argument("--development-report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.freeze_out:
            if not args.development_report or args.split or args.dry_run or args.candidate_prompt or args.candidate_relevance or args.successor_holdout:
                parser.error("freeze creation requires only --freeze-out and --development-report")
            create_freeze(ROOT, args.freeze_out, args.development_report.resolve())
            print("configuration frozen; holdout still requires human-approved labels")
        else:
            if not args.split or args.out is None or args.call_budget is None:
                parser.error("run requires --split, --out, and --call-budget")
            result = run_quality(settings=load_settings(project_root=ROOT), split=args.split,
                                 output=args.out.resolve(), cache=args.cache.resolve(),
                                 call_budget=args.call_budget, dry_run=args.dry_run,
                                 freeze=args.freeze.resolve() if args.freeze else None,
                                 pack=args.pack.resolve() if args.pack else None,
                                 gold=args.gold.resolve() if args.gold else None,
                                 approval=args.approval.resolve() if args.approval else None,
                                 candidate_prompt=args.candidate_prompt,
                                 candidate_relevance=args.candidate_relevance,
                                 successor=args.successor_holdout)
            print(json.dumps({key: result[key] for key in
                             ("split", "documents", "maximum_provider_calls", "provider_calls")}, indent=2))
        return 0
    except (QualityBoundsError, ConfigError, ValueError, OSError) as exc:
        # Error text from the settings/bounds layer contains no secret values.
        print(f"Quality verification refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
