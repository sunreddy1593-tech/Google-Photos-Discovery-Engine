"""Audit the saved M1 checkpoint offline; never collect, extract or score holdout.

Uses existing record gates and stage events. Historical source validation is
attested by the retained verdict ledger. Fresh substring checks use only the
approved gold-dev packets; reserved gold-holdout source text stays closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.annotate import validate_pack
from src.pipeline.extraction_development import (
    FUNNEL_SOURCES,
    analysis_evidence_spans,
    count_stage_events,
    development_ids,
    holdout_ids,
    verbatim_span_failures,
)

DEFAULT_RUN = Path("data/interim/phase5/development-corpus/3dc346ec030a")
DEFAULT_PACK = Path("data/annotation/dev-starter-2026-10-03/sunayana-reviewed-01")
IMPORT_REPORT = Path("data/processed/pilot-import/import_report.json")
SPLIT = Path("data/interim/phase4/relevance_split_manifest.csv")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _span_key(row: dict) -> tuple:
    # Case ids can change from unresolved to ordered after validation. Document,
    # field, offsets and exact quote must still agree with the retained verdict.
    return (
        row.get("doc_id"), row.get("field_name"), row.get("start_char"), row.get("end_char"),
        hashlib.sha256(row["quote"].encode("utf-8")).hexdigest(),
    )


def test_summary(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError("test evidence has no suites")
    totals = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    names = {case.get("classname", "") for suite in suites for case in suite.findall("testcase")}
    required = {"test_evidence", "test_evidence_map", "test_extraction_development", "test_models"}
    totals["required_families_present"] = all(any(family in name.split(".") for name in names) for family in required)
    totals["ok"] = (
        totals["passed"] > 0 and totals["failures"] == 0 and totals["errors"] == 0
        and totals["required_families_present"]
    )
    return totals


def build_audit(run: Path, pack: Path, tests: Path) -> dict:
    development = set(development_ids())
    holdout = set(holdout_ids())
    inputs = _rows(run / "extraction_inputs.jsonl")
    chosen = {row["doc_id"] for row in inputs}
    if chosen != development or len(inputs) != len(development) or chosen & holdout:
        raise ValueError("M1 run must cover the frozen development split exactly, without holdout")
    imported = json.loads(IMPORT_REPORT.read_text(encoding="utf-8"))
    accepted = imported["accepted_rows"]
    imported_ids = {row["doc_id"] for row in accepted}
    provenance_ok = (
        chosen <= imported_ids and len(imported_ids) == len(accepted) == imported["rows_accepted"]
        and len(imported["workbook_sha256"]) == 64
        and all(row.get("source_item_id") for row in accepted if row["doc_id"] in chosen)
    )

    cases = _rows(run / "retrieval_cases.jsonl")
    ledger = _rows(run / "evidence_spans.jsonl")
    verdicts = _rows(run / "span_validations.jsonl")
    if any(row["doc_id"] not in chosen for row in cases + ledger + verdicts):
        raise ValueError("extraction artifact is outside the development run")
    spans = analysis_evidence_spans(cases, ledger)
    accepted_verdicts = {_span_key(row) for row in verdicts if row.get("ok") and row.get("validation_state") == "valid"}
    missing_verdicts = sum(_span_key(span) not in accepted_verdicts for span in spans)
    nonvalid = sum(span["validation_state"] != "valid" for span in spans)

    selection = json.loads((pack.parent / "selection.json").read_text(encoding="utf-8"))
    reserved = set(selection["reserved_development_doc_ids"])
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    allowed = {row["doc_id"] for row in manifest["documents"] if row["gold_split"] == "dev"}
    if allowed & (holdout | reserved) or allowed | reserved != development:
        raise ValueError("approved packet selection would breach a frozen holdout")
    texts = {}
    for doc_id in sorted(allowed):
        packet = json.loads((pack / "packets" / f"{doc_id}.json").read_text(encoding="utf-8"))
        if packet["doc_id"] != doc_id or packet["gold_split"] != "dev" or packet["phase4_split"] != "development":
            raise ValueError("packet is not development-only")
        texts[doc_id] = packet["source_text"]
    fresh_spans = [span for span in spans if span["doc_id"] in allowed]
    fresh_failures = verbatim_span_failures(fresh_spans, texts)
    approval = validate_pack(pack, tuple(holdout | reserved))
    if approval.errors or approval.pending:
        raise ValueError("approved annotations no longer validate")

    sources = FUNNEL_SOURCES + ((run / "stage_events.jsonl", frozenset({"extract"})),)
    stages = count_stage_events(sources, chosen)
    unique_events = {}
    for path, wanted in sources:
        for row in _rows(path):
            if row.get("stage") in wanted and row.get("target_id") in chosen:
                unique_events.setdefault(row["stage"], []).append(row["target_id"])
    events_ok = all(
        len(unique_events.get(stage, [])) == len(chosen)
        and set(unique_events.get(stage, [])) == chosen
        for stage in ("normalize", "dedupe", "prefilter", "relevance", "extract")
    )
    historical = json.loads((run / "stage_funnel.json").read_text(encoding="utf-8"))
    funnel_ok = historical["documents"] == len(chosen) and historical["stages"] == stages
    extract_events = _rows(run / "stage_events.jsonl")
    empty = sum(row.get("status") == "succeeded" and row.get("detail", {}).get("case_count") == 0 for row in extract_events)
    checks = {
        "at_least_30_genuine_public_documents": len(chosen) >= 30 and provenance_ok,
        "end_to_end_processing": events_ok and provenance_ok,
        "validated_verbatim_field_evidence": bool(cases) and bool(spans) and not (missing_verdicts or nonvalid or fresh_failures),
        "stage_funnel_reported": events_ok and funnel_ok,
        "schema_and_evidence_tests_passing": test_summary(tests)["ok"],
    }
    manifest_run = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    files = [IMPORT_REPORT, SPLIT, tests, pack / "manifest.json", pack / "review_policy.json"]
    files.extend(sorted(run.glob("*.json*")))
    files.extend(path for path, _ in FUNNEL_SOURCES)
    return {
        "milestone": "M1", "status": "complete" if all(checks.values()) else "incomplete",
        "basis": "problem-statement.md Section 28; technical pipeline checkpoint, not Phase 6 quality certification",
        "checks": checks, "documents": len(chosen), "imported_rows": imported["rows_accepted"],
        "phase4_holdout_excluded": len(holdout), "gold_holdout_sources_not_loaded": len(reserved),
        "run_id": manifest_run["run_id"], "stages": stages,
        "extraction": {
            "eligible": sum(row["eligible"] for row in inputs), "analysis_cases": len(cases),
            "case_scope_counts": dict(Counter(row["scope_class"] for row in cases)),
            "documents_with_cases": len({row["doc_id"] for row in cases}), "accepted_empty_documents": empty,
            "analysis_spans": len(spans), "historical_inline_only_count": historical["analysis_spans"],
            "ledger_nonvalid_attempt_spans": sum(row["validation_state"] != "valid" for row in ledger),
            "current_record_gate_failures": 0, "nonvalid_analysis_spans": nonvalid,
            "missing_retained_valid_verdicts": missing_verdicts,
            "fresh_development_source_checks": len(fresh_spans), "fresh_verbatim_failures": fresh_failures,
            "verbatim_basis": "All analysis spans matched retained successful source-validation verdicts; fresh source checks restricted to approved gold-dev packets.",
        },
        "approved_reference": {"documents": approval.documents, "review_files": approval.reviews, "human_reviewer": "Sunayana", "method": "single-reviewer-ai-assisted/v1"},
        "tests": test_summary(tests), "historical_provider_calls": manifest_run["cache"]["provider_calls"],
        "historical_cache_hits": manifest_run["cache"]["hits"],
        "provider_calls_this_audit": 0, "holdout_source_text_loaded": False,
        "quality_gate": "pending; no holdout scoring or extraction quality claim",
        "semantic_approval_of_saved_model_cases": "not established by this technical audit; approved human references are separate",
        "limitations": [
            "Manual convenience sample; provenance is retained, source availability was not re-fetched.",
            "Six failed extraction documents and seven accepted empty responses remain diagnostic findings.",
            "One unavailable model relevance decision used an existing effective human decision.",
            "Known semantic risks remain: retrieval_trigger, unsupported impact/severity, incomplete summary evidence, invented or spliced quotes.",
            "Gold references are ten documents, single-human-reviewed with AI assistance, and include a disclosed album scope exception.",
        ],
        "input_sha256": {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--test-result", type=Path, required=True, help="JUnit XML from the current full offline suite")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        print("Audit output exists; refusing to overwrite it.", file=sys.stderr)
        return 2
    try:
        report = build_audit(args.run, args.pack, args.test_result)
    except (ValueError, KeyError, OSError, ET.ParseError) as exc:
        print(f"M1 audit refused: {type(exc).__name__}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"M1 status            {report['status']}")
    print(f"documents            {report['documents']}")
    print(f"analysis cases       {report['extraction']['analysis_cases']}")
    print(f"analysis spans       {report['extraction']['analysis_spans']}")
    print("provider calls       0")
    print(f"audit report         {args.out / 'report.json'}")
    return int(report["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
