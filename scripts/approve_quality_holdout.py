"""Record an owner's actual approval of reviewed holdout drafts, never infer it.

Run only after Sunayana has reviewed APPROVAL.md and supplied an explicit
approval statement. Drafts remain unchanged and are not called independent
human coding. Gold export and approval receipt are new, separate artifacts.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.annotate import _cases_from_review
from src.gold.evaluate import validate_gold_quotes
from src.gold.load import require_case_counts
from src.models.gold import GoldDocumentLabel
from src.pipeline.quality import DEV_GOLD, check_freeze, read, sha, write_new


def approve(*, root: Path, freeze: Path, pack: Path, output: Path, receipt: Path, statement: str) -> None:
    frozen = check_freeze(root, freeze)
    if not statement.strip() or output.exists() or receipt.exists():
        raise ValueError("actual approval statement and fresh gold/receipt destinations are required")
    wanted = set(frozen["seats"]["holdout"])
    drafts = sorted((pack / "drafts").glob("*.json"))
    if {path.stem for path in drafts} != wanted:
        raise ValueError("every reserved holdout document needs a reviewed draft")
    documents, cases, texts = [], [], {}
    for path in drafts:
        draft = read(path)
        doc = draft["doc_id"]
        packet = read(pack / "packets" / f"{doc}.json")
        if draft["split"] != "holdout" or packet["gold_split"] != "holdout":
            raise ValueError("split mismatch")
        texts[doc] = packet["source_text"]
        # Reuse existing offset, case-id, and gold-value conversion.
        new_cases = _cases_from_review(doc, draft.get("cases") or [], texts[doc], labeler_id="Sunayana")
        documents.append(GoldDocumentLabel(
            doc_id=doc, split="holdout", scope_class=draft["scope_class"], reason_code=draft["reason_code"],
            prefilter_should_pass=draft["prefilter_should_pass"], expected_case_count=draft["expected_case_count"],
            labeler_id="Sunayana", labeled_at=datetime.now(UTC), adjudicated=False,
            notes="AI-assisted source-first draft reviewed and approved by sole human Sunayana. " + (draft.get("notes") or ""),
        ))
        cases.extend(new_cases)
    require_case_counts(documents, cases)
    if validate_gold_quotes(cases, texts):
        raise ValueError("gold evidence is not verbatim")
    output.mkdir(parents=True, exist_ok=False)
    # Copy approved development labels unchanged; the split field is preserved.
    for name, rows in (("documents.jsonl", documents), ("cases.jsonl", cases)):
        prior = (root / DEV_GOLD / name).read_text(encoding="utf-8")
        with (output / name).open("x", encoding="utf-8") as handle:
            handle.write(prior + ("\n" if prior and not prior.endswith("\n") else ""))
            handle.write("".join(row.model_dump_json() + "\n" for row in rows))
    bound = [pack / "manifest.json", output / "documents.jsonl", output / "cases.jsonl"]
    bound += [pack / "packets" / f"{doc}.json" for doc in sorted(wanted)]
    write_new(receipt, {
        "human_approved": True, "reviewer": "Sunayana", "approval_statement": statement,
        "approved_at": datetime.now(UTC).isoformat(), "freeze_sha256": sha(freeze),
        "approved_sha256": {path.relative_to(root).as_posix(): sha(path) for path in bound},
        "review_method": "AI-assisted source-first labels, single-human approval; no independent double-coding",
        "draft_sha256": {path.relative_to(root).as_posix(): sha(path) for path in drafts},
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--approval-statement", required=True)
    args = parser.parse_args(argv)
    approve(root=ROOT, freeze=args.freeze.resolve(), pack=args.pack.resolve(), output=args.out.resolve(),
            receipt=args.receipt.resolve(), statement=args.approval_statement)
    print("Human approval recorded; versioned gold export created; provider calls 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
