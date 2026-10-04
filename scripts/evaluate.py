"""Score a gold split. An empty gold set prints pending and does not invent zeros.

Error analysis is written only for ``--split dev``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.evaluate import HoldoutAnalysisError, evaluate_gold, write_error_analysis, write_report
from src.gold.failures import build_development_failure_ledger
from src.gold.load import load_gold_cases, load_gold_documents
from src.gold.annotate import AnnotationError
from src.gold.saved_run import load_saved_development, load_saved_holdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate one gold split.")
    parser.add_argument("--gold", required=True, help="Directory with documents.jsonl and cases.jsonl")
    parser.add_argument("--split", required=True, choices=("dev", "holdout"))
    parser.add_argument("--out", required=True, help="Directory for report.json")
    parser.add_argument("--saved-run", type=Path, help="Saved extraction run; development only")
    parser.add_argument("--relevance", type=Path, help="Saved model relevance decisions.jsonl")
    parser.add_argument("--pack", type=Path, help="Approved gold-dev annotation pack with source packets")
    parser.add_argument("--prefilter-events", type=Path, help="Saved prefilter stage_events.jsonl")
    parser.add_argument("--freeze", type=Path, help="Frozen configuration for an authorized holdout measurement")
    parser.add_argument("--approval", type=Path, help="Hash-bound approval of the actual holdout gold labels")
    args = parser.parse_args(argv)
    gold = Path(args.gold)
    destination = Path(args.out)
    if destination.exists():
        print("Evaluation output exists; use a fresh destination.", file=sys.stderr)
        return 2
    supplied = (args.saved_run, args.relevance, args.pack, args.prefilter_events)
    authorized_holdout = args.split == "holdout" and args.freeze is not None and args.approval is not None
    if (any(supplied) and (not all(supplied) or (args.split != "dev" and not authorized_holdout))
            or (args.freeze or args.approval) and not (authorized_holdout and all(supplied))):
        print("Saved-run evaluation requires all four inputs and --split dev; holdout remains locked.", file=sys.stderr)
        return 2
    inputs = None
    kwargs = {}
    if args.saved_run:
        documents = tuple(row for row in load_gold_documents(gold / "documents.jsonl") if row.split.value == args.split)
        try:
            loader = load_saved_holdout if authorized_holdout else load_saved_development
            extra = dict(root=ROOT, freeze=args.freeze, gold=gold, approval=args.approval) if authorized_holdout else {}
            inputs = loader(
                doc_ids={row.doc_id for row in documents}, run=args.saved_run,
                relevance=args.relevance, pack=args.pack, prefilter_events=args.prefilter_events,
                **extra,
            )
        except (AnnotationError, ValueError, KeyError, OSError) as exc:
            print(f"Saved evaluation refused: {type(exc).__name__}", file=sys.stderr)
            return 2
        kwargs = dict(
            predictions=inputs.predictions, extracted_cases=inputs.extracted_cases, texts=inputs.texts,
            schema_failures=inputs.schema_failures, processed_records=inputs.processed_records,
            review_count=inputs.review_count, failure_count=inputs.failure_count, attempt_count=inputs.attempt_count,
            additional_spans_by_document=inputs.relevance_spans,
        )
    report = evaluate_gold(
        documents_path=gold / "documents.jsonl",
        cases_path=gold / "cases.jsonl",
        split=args.split,
        **kwargs,
    )
    if inputs:
        if report["gold_quote_failures"]:
            print("Saved evaluation refused: gold quotes failed source validation.", file=sys.stderr)
            return 2
        report["saved_inputs"] = inputs.metadata
        policy = args.pack / "review_policy.json"
        report["review_method"] = json.loads(policy.read_text(encoding="utf-8")) if policy.is_file() else {"method": "not supplied"}
        bound_files = [gold / "documents.jsonl", gold / "cases.jsonl", policy,
                       Path(__file__), ROOT / "src/gold/evaluate.py", ROOT / "src/gold/metrics.py",
                       ROOT / "src/gold/saved_run.py"]
        exception_file = gold / "scope_exceptions.json"
        if exception_file.is_file():
            bound_files.append(exception_file)
            report["scope_exceptions"] = json.loads(exception_file.read_text(encoding="utf-8"))
        inputs.metadata["input_sha256"].update({
            path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in bound_files if path.is_file()
        })
        report["limitations"] = [
            "Development diagnostic over an AI-assisted, single-human-reviewed reference sample; not a final holdout quality gate.",
            "Field accuracy is conditional on matched retained cases; inspect case coverage and extraction failures separately.",
            "Unsupported-inference rates combine missing/invalid spans and disagreement with available reference values; a verbatim quote alone does not prove semantic support.",
            "problem_summary has no reference summary value in the existing gold contract; its semantic support needs manual review, even when its attached span is valid.",
            "Gold scope exceptions remain disclosed in the reference export; no label was changed to match the model.",
        ]
        if authorized_holdout:
            from src.pipeline.quality import LIMITATION, read
            report["limitations"][0] = "AI-assisted labels approved by one human; no independent double-coding or agreement estimate."
            report["limitations"].append(LIMITATION)
            report["freeze"] = read(args.freeze)
            report["human_approval"] = {"reviewer": "Sunayana", "approval_sha256": inputs.metadata["approval_sha256"]}
            from src.pipeline.quality import write_new
            score_claim = args.freeze.parent / "evaluation_claim.json"
            if score_claim.exists():
                print("Frozen holdout has already been scored; refusing another measurement.", file=sys.stderr)
                return 2
            write_new(score_claim, {"output": str(destination), "freeze_sha256": inputs.metadata["freeze_sha256"],
                                    "approval_sha256": inputs.metadata["approval_sha256"]})
    write_report(args.out, report)
    if args.split == "dev" and report["status"] == "measured":
        documents = tuple(
            row for row in load_gold_documents(gold / "documents.jsonl") if row.split.value == "dev"
        )
        write_error_analysis(
            Path(args.out) / "disagreements.csv",
            split="dev",
            documents=documents,
            predictions=inputs.predictions if inputs else {},
            texts=inputs.texts if inputs else {},
        )
        events = []
        if args.saved_run is not None:
            event_path = Path(args.saved_run) / "stage_events.jsonl"
            if event_path.is_file():
                events = [
                    json.loads(line)
                    for line in event_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
        case_ids = {row.doc_id for row in documents}
        ledger = build_development_failure_ledger(
            report=report,
            documents=documents,
            predictions=inputs.predictions if inputs else {},
            gold_cases=tuple(
                row for row in load_gold_cases(gold / "cases.jsonl") if row.doc_id in case_ids
            ),
            extracted_cases=inputs.extracted_cases if inputs else (),
            texts=inputs.texts if inputs else {},
            extraction_events=events,
        )
        (Path(args.out) / "failure_categories.json").write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif args.split == "holdout":
        forbidden = Path(args.out) / "disagreements.csv"
        if forbidden.exists() or (Path(args.out) / "failure_categories.json").exists():
            raise HoldoutAnalysisError("refusing to leave a holdout error analysis in place")
    print(f"status               {report['status']}")
    print(f"split                {report['split']}")
    print(f"documents            {report['documents']}")
    print(f"excluded technical   {report['excluded_technical_failures']}")
    for name, gate in report["gates"].items():
        print(f"gate {name:<24} {gate['pass']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HoldoutAnalysisError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
