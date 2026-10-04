"""Open only reserved gold-holdout seats after a measured configuration is frozen.

Sources are separate from predictions. This command creates blank packets, not
human labels, gold records, or approval. It never calls a provider.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.annotate import blank_case, blank_document, reviewer_checks
from src.pipeline.quality import COLLECTED, DERIVED, LIMITATION, check_freeze, selected_rows, sha, write_new


def prepare(*, root: Path, freeze: Path, output: Path) -> None:
    frozen = check_freeze(root, freeze)
    if output.exists():
        raise ValueError("holdout labeling output must be fresh")
    wanted = set(frozen["seats"]["holdout"])
    collected = {row["doc_id"]: row for row in selected_rows(root / COLLECTED, wanted)}
    derived = {row["doc_id"]: row for row in selected_rows(root / DERIVED, wanted)}
    packets = []
    for doc in sorted(wanted):
        original, audit = collected[doc], derived[doc]
        if len(original["raw_text"]) != len(audit["raw_text_audit"]):
            raise ValueError("audit offsets are not length-preserving")
        packet = {
            "doc_id": doc, "gold_split": "holdout", "phase4_split": "development",
            "source_text": audit["raw_text_audit"], "source_text_field": "raw_text_audit",
            "source_text_sha256": sha(root / DERIVED), "redaction_spans": audit.get("redaction_spans", []),
            "provenance": {key: original.get(key) for key in (
                "source_platform", "source_type", "source_item_id", "source_url", "source_name", "title",
                "evidence_tier", "published_at", "collected_at", "collection_method", "ingest_batch_id")},
            "gold_document": blank_document(doc, "holdout"), "gold_cases": [],
            "case_template": blank_case(doc), "reviewer_checks": reviewer_checks(),
            "prediction_accessed_for_labeling": False,
        }
        packets.append(packet)
    manifest = {
        "split_rule": "gold-split/v1", "split_seed": "gold-split/v1", "freeze_sha256": sha(freeze),
        "documents": [{"doc_id": doc, "gold_split": "holdout", "phase4_split": "development", "double_code": False}
                      for doc in sorted(wanted)],
        "limitations": [LIMITATION], "original_phase4_holdout_text_copied": False,
        "human_approval": "pending", "predictions_in_pack": False,
    }
    for packet in packets:
        write_new(output / "packets" / f"{packet['doc_id']}.json", packet)
    write_new(output / "manifest.json", manifest)
    write_new(output / "review_policy.json", {
        "method": "AI-assisted source-first draft followed by single-human review",
        "reviewer": "Sunayana", "human_approved": False, "independent_double_coding": False,
        "agreement_estimate": None, "freeze_sha256": sha(freeze),
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    prepare(root=ROOT, freeze=args.freeze.resolve(), output=args.out.resolve())
    print("25 reserved holdout source packets prepared; human approval pending; provider calls 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
