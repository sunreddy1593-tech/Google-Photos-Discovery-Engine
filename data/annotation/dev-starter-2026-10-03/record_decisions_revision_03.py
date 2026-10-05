"""Preserve prior revisions and record two explicitly scoped human decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "ai-assisted-draft-02"
NEW = ROOT / "ai-assisted-draft-03"
STAMP = datetime.now(timezone.utc).isoformat()
if NEW.exists():
    raise SystemExit("Refusing existing revision destination")
protected = [p for folder in (ROOT / "ai-assisted-draft-01", OLD) for p in folder.rglob("*") if p.is_file()]
protected += [ROOT / "manifest.json", ROOT / "selection.json", *sorted((ROOT / "packets").glob("*.json")), Path("data/gold/documents.jsonl"), Path("data/gold/cases.jsonl"), Path("data/interim/phase4/relevance_split_manifest.csv")]
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
reviews = {row["doc_id"]: json.loads((OLD / "labels" / "codex_ai_draft" / (row["doc_id"] + ".json")).read_text(encoding="utf-8")) for row in manifest["documents"]}

album = "google_support-2a080da4b930"
video = "reddit-bde62ddef9b5"
album_values = json.dumps(reviews[album]["cases"], sort_keys=True)
video_values = json.dumps(reviews[video]["cases"], sort_keys=True)
reviews[album]["scope_class"] = "core_incomplete_recall"
reviews[album]["notes"] += " Sunayana directed core scope on 2026-10-04. This is a documented scope-criteria exception: the body does not demonstrate incomplete recall under spec Section 9.1. Existing known-item journey reason, case values and evidence are retained; forgotten information and trigger are not invented to justify the label. No classification rule or prompt changed."
reviews[album]["labeled_at"] = STAMP
reviews[video]["notes"] += " Sunayana approved the presented core/one-case summary on 2026-10-04: forgotten date, delimited natural-language query, successful retrieval, uncertain subject and no invented motive/impact/severity. This records approval of that summary, not additional unstated decisions, independent double-coding or adjudication."
assert album_values == json.dumps(reviews[album]["cases"], sort_keys=True)
assert video_values == json.dumps(reviews[video]["cases"], sort_keys=True)
assert reviews[album]["cases"][0]["expected_values"]["forgotten_information"] == {"observation": "not_stated", "value": []}
assert reviews[video]["cases"][0]["expected_values"]["outcome"] == {"observation": "stated", "value": "found"}

decisions = [
    {"item": 8, "doc_id": video, "decision": "approve_presented_case_summary", "approved_scope_class": "core_incomplete_recall", "approved_expected_case_count": 1, "approval_scope": ["core/one-case summary", "stated forgotten date", "delimited natural-language query", "successful retrieval", "uncertain subject type", "no invented motive, impact or severity"], "user_statement": "this can be marked as core , i approve of your decision", "remaining": ["unreviewed field-level details outside the presented summary", "other outstanding pack reviews"]},
    {"item": 1, "doc_id": album, "decision": "reviewer_directed_core_scope_exception", "previous_scope_class": "adjacent_known_item_retrieval", "approved_scope_class": "core_incomplete_recall", "approval_scope": ["scope_class override only"], "user_statement": "this can be changed to core.", "scope_criteria_exception": {"rule": "problem-statement.md Section 9.1", "missing_condition": "incomplete, approximate, uncertain or difficult-to-express memory cues are not demonstrated by the source", "evidence_fields_changed_to_justify_override": False, "rule_changed": False}, "remaining": ["case fields not blanket-approved by the scope override", "scope exception must be disclosed in later analysis/evaluation methodology"]},
]
for decision in decisions:
    decision.update(reviewer="Sunayana", reviewed_on="2026-10-04", recorded_at=STAMP, client_timezone="Asia/Calcutta", ai_assisted=True, independent_human_double_coding=False, adjudicated=False)

NEW.mkdir()
(NEW / "packets").mkdir()
(NEW / "labels" / "codex_ai_draft").mkdir(parents=True)
for name in ("manifest.json", "vocabularies.json"):
    (NEW / name).write_bytes((OLD / name).read_bytes())
for row in manifest["documents"]:
    name = row["doc_id"] + ".json"
    (NEW / "packets" / name).write_bytes((OLD / "packets" / name).read_bytes())
    (NEW / "labels" / "codex_ai_draft" / name).write_text(json.dumps(reviews[row["doc_id"]], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
old_ledger = (OLD / "human_decisions.jsonl").read_bytes()
(NEW / "human_decisions.jsonl").write_bytes(old_ledger + "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in decisions).encode("utf-8"))
(NEW / "scope_exceptions.json").write_text(json.dumps([decisions[1]], indent=2) + "\n", encoding="utf-8")
counts = {s: sum(r["scope_class"] == s for r in reviews.values()) for s in ("core_incomplete_recall", "adjacent_known_item_retrieval", "out_of_scope")}
provenance = {"role": "ai_assisted_revision_with_scoped_human_decisions", "supersedes_for_inspection": str(OLD), "recorded_at": STAMP, "client_review_date": "2026-10-04", "client_timezone": "Asia/Calcutta", "document_count": 10, "case_count": sum(len(r["cases"]) for r in reviews.values()), "scope_counts": counts, "human_decision_count": 6, "new_human_decisions": 2, "scope_criteria_exceptions": 1, "official_gold_records_written": 0, "provider_calls": 0, "independent_second_reviews_added": 0, "protected_file_sha256": hashes, "double_code_documents": [r["doc_id"] for r in manifest["documents"] if r["double_code"]]}
(NEW / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

approval = """# Annotation revision 03: decisions recorded 2026-10-04

This revision preserves drafts 01 and 02. Proposed document labels now total
3 core, 3 adjacent, 4 out of scope, with six proposed retrieval cases. These
are AI-assisted annotations with scoped human review; official gold is unchanged.

## Latest decisions

- **Item 8, successful sleeping-video search** (`reddit-bde62ddef9b5`): core,
  one-case summary approved by Sunayana. Forgotten date, the delimited
  natural-language query and successful retrieval are supported. Subject type
  stays uncertain; no motive, impact or severity is added. The case values and
  quotes are unchanged.
- **Item 1, family photo inside an album** (`google_support-2a080da4b930`): core
  scope applied as directed by Sunayana. One proposed case is retained, with
  all case fields and quotes unchanged.

## Family-album scope exception

The source describes a known-item need and an album face-search limitation,
but no incomplete recall. Under the existing Section 9.1 criterion, that
evidence would ordinarily support adjacent scope. The user's core instruction
is recorded explicitly as a reviewer-directed scope exception, not evidence
of forgotten information or inability to formulate a query. The existing
`known_item_retrieval_journey_described` reason remains; the inclusion reason
group validates for core, but local validation does not establish consistency
with the substantive core definition. No definition or prompt was changed.

Source: "I'm trying to search for one of my family in a Google photos album. It is not a shared album. It seems you can't search for a face within a specific album, which means I have to scroll through hundreds of photos to find the one I want. Any tips?"

This exception is also in `scope_exceptions.json` and must remain visible when
the label is later evaluated or used in core comparisons.

## Earlier decisions preserved

- Item 3: Memories adjacent scope approved. The new reason, one-case count and
  case fields still await confirmation.
- Item 7: later first-person poodle search accepted as real evidence; illustrative
  quantities and other breed examples are excluded from measured counts/cases.
- Item 9: cat case severity 3 approved.
- Item 10: short YouTube insufficient-evidence exclusion with zero cases approved.

`human_decisions.jsonl` retains all six decision records without rewriting the
earlier four. Decisions are scoped and do not imply blanket approval of all
other document labels or every field. Original gold, split, source packets,
saved model output and quality reports are unchanged.

The two manifest-designated documents still require independent second human
reviews. There is no adjudication, fabricated second coder or agreement score.
Quality gates and M1 remain pending/incomplete. No model/API calls, evaluation,
holdout text access, commit or push occurred.

REVIEW.md contains the ten source texts, proposed fields and exact quotes.
"""
(NEW / "APPROVAL.md").write_text(approval, encoding="utf-8")
lines = ["# Revision 03: annotations and evidence", "", "Read APPROVAL.md for scoped approvals and the core-scope exception. All case fields and quotes are preserved from revision 02.", ""]
for row in manifest["documents"]:
    doc = row["doc_id"]
    r = reviews[doc]
    p = json.loads((NEW / "packets" / (doc + ".json")).read_text(encoding="utf-8"))
    lines += [f"## {doc}", "", "> " + p["source_text"].replace("\n", "\n> "), "", f"Scope: `{r['scope_class']}`; reason: `{r['reason_code']}`; cases: {r['expected_case_count']}", "", r["notes"], ""]
    for c in r["cases"]:
        for field, payload in c["expected_values"].items():
            lines += [f"- `{field}`: `{payload['observation']}`; `{json.dumps(payload['value'], ensure_ascii=False)}`"]
        lines += ["", "Evidence:", ""]
        for e in c["evidence"]:
            lines += [f"- `{e['field_name']}` [{e['start_char']}, {e['end_char']}): {e['quote']}"]
        lines += ["", c["notes"], ""]
(NEW / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(NEW / "README.md").write_text("# AI-assisted annotation revision 03\n\nSee APPROVAL.md, human_decisions.jsonl and scope_exceptions.json. Validate with scripts/validate_annotations.py --pack data/annotation/dev-starter-2026-10-03/ai-assisted-draft-03. Do not emit into official gold or treat AI assistance as independent second human coding.\n", encoding="utf-8")
assert hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
print(json.dumps({"revision": str(NEW), "scope_counts": counts, "case_count": provenance["case_count"], "decisions_total": 6, "case_values_unchanged": True, "protected_files_unchanged": len(hashes), "official_gold_records_written": 0}))
