"""Record scoped human decisions without replacing earlier AI drafts or gold."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "ai-assisted-draft-01"
NEW = ROOT / "ai-assisted-draft-02"
STAMP = datetime.now(timezone.utc).isoformat()
if NEW.exists():
    raise SystemExit("Refusing an existing revision destination")

original_files = [p for p in OLD.rglob("*") if p.is_file()]
protected = original_files + [ROOT / "manifest.json", ROOT / "selection.json", *sorted((ROOT / "packets").glob("*.json")), Path("data/gold/documents.jsonl"), Path("data/gold/cases.jsonl"), Path("data/interim/phase4/relevance_split_manifest.csv")]
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
reviews = {r["doc_id"]: json.loads((OLD / "labels" / "codex_ai_draft" / (r["doc_id"] + ".json")).read_text(encoding="utf-8")) for r in manifest["documents"]}
assert len(reviews) == 10

doc = "google_support-5b2ec98df32b"
packet = json.loads((OLD / "packets" / (doc + ".json")).read_text(encoding="utf-8"))
assert packet["gold_split"] == "dev" and packet["phase4_split"] == "development"
source = packet["source_text"]
list_fields = {"target_subjects", "remembered_cues", "forgotten_information", "query_strategies", "system_responses", "workarounds", "impact_signals"}
values = {field: {"observation": "not_stated", "value": [] if field in list_fields else None} for field in packet["case_template"]["expected_values"]}
values["known_item_status"] = {"observation": "stated", "value": "explicit"}
values["target_asset_type"] = {"observation": "stated", "value": "photo"}

def span(field, quote):
    start = source.index(quote)
    assert source.find(quote, start + 1) == -1
    return {"field_name": field, "quote": quote, "start_char": start, "end_char": start + len(quote)}

memory_case = {
    "ordinal": 1,
    "expected_values": values,
    "evidence": [span("known_item_status", "My photo memories come up and I can see randomly"), span("target_asset_type", "My photo memories")],
    "notes": "New AI-assisted case draft following Sunayana's approved adjacent scope. The known target is the previously displayed photo Memories collection, not an identified individual photo. The source asks how to revisit it. It states no incomplete recall, executed query, returned failure, workaround, final outcome, impact, severity or motive. These case-field judgments and expected_case_count=1 have not received blanket human approval. Independent second human review remains required.",
}
review = reviews[doc]
review.update(scope_class="adjacent_known_item_retrieval", reason_code="known_item_retrieval_journey_described", expected_case_count=1, labeled_at=STAMP, cases=[memory_case])
review["notes"] = "AI-assisted revision. Sunayana approved adjacent scope on 2026-10-04 after reviewing the draft. Revisiting already displayed photo Memories is treated as a known-target collection retrieval need. No incomplete recall is stated. The inclusion reason and new single-case details remain AI proposals pending confirmation. This is not an independent human label or adjudication."

decisions = [
    {"item": 3, "doc_id": doc, "decision": "change_scope", "approved_scope_class": "adjacent_known_item_retrieval", "user_statement": "3. can be changed to adjacent", "approval_scope": ["scope_class"], "remaining": ["new inclusion reason and expected_case_count=1 proposal", "new Memories case fields", "independent second human review"]},
    {"item": 7, "doc_id": "reddit-87311c2633df", "decision": "accept_real_episode_grounding", "user_statement": "accept the later first-person search as real evidence despite the earlier illustrative 'Say I have' framing. The sample counts and other breed examples are not treated as observed counts or extra cases.", "approval_scope": ["real-world grounding of later first-person search", "exclude illustrative counts and additional breed examples"], "remaining": ["other case-field judgments are not blanket-approved by this decision"]},
    {"item": 9, "doc_id": "reddit-c2c00b25a88b", "decision": "approve_severity", "approved_severity": 3, "user_statement": "agree with proposed severity 3 .", "approval_scope": ["severity=3"], "remaining": ["other case-field judgments are not blanket-approved by this decision"]},
    {"item": 10, "doc_id": "youtube-17fd27447275", "decision": "approve_exclusion_proposal", "approved_scope_class": "out_of_scope", "approved_reason_code": "insufficient_evidence_for_a_case", "approved_expected_case_count": 0, "user_statement": "Agree with your proposal.", "approval_scope": ["out-of-scope/insufficient-evidence exclusion with zero cases"], "remaining": ["independent second human review"]},
]
for decision in decisions:
    decision.update(reviewer="Sunayana", reviewed_on="2026-10-04", recorded_at=STAMP, client_timezone="Asia/Calcutta", ai_assisted=True, independent_human_double_coding=False, adjudicated=False)
    if decision["item"] != 3:
        reviews[decision["doc_id"]]["notes"] += " Human decision recorded 2026-10-04: " + decision["decision"] + ". This scoped approval does not represent blanket approval of all fields or independent double-coding."
assert reviews["reddit-c2c00b25a88b"]["cases"][0]["expected_values"]["severity"]["value"] == 3

NEW.mkdir()
(NEW / "packets").mkdir()
(NEW / "labels" / "codex_ai_draft").mkdir(parents=True)
for name in ("manifest.json", "vocabularies.json"):
    (NEW / name).write_bytes((OLD / name).read_bytes())
for row in manifest["documents"]:
    name = row["doc_id"] + ".json"
    (NEW / "packets" / name).write_bytes((OLD / "packets" / name).read_bytes())
    (NEW / "labels" / "codex_ai_draft" / name).write_text(json.dumps(reviews[row["doc_id"]], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(NEW / "human_decisions.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in decisions), encoding="utf-8")
scope_counts = {s: sum(r["scope_class"] == s for r in reviews.values()) for s in ("core_incomplete_recall", "adjacent_known_item_retrieval", "out_of_scope")}
provenance = {"role": "ai_assisted_revision_with_scoped_human_decisions", "supersedes_for_inspection": str(OLD), "recorded_at": STAMP, "client_review_date": "2026-10-04", "client_timezone": "Asia/Calcutta", "document_count": 10, "case_count": sum(len(r["cases"]) for r in reviews.values()), "scope_counts": scope_counts, "human_decision_count": 4, "blanket_approved_documents": 0, "official_gold_records_written": 0, "provider_calls": 0, "independent_second_reviews_added": 0, "protected_file_sha256": hashes, "double_code_documents": [r["doc_id"] for r in manifest["documents"] if r["double_code"]]}
(NEW / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

approval = """# Annotation revision: human decisions recorded 2026-10-04

This revision preserves draft 01 and the original blank pack. It contains 10
documents: 2 core, 4 adjacent, 4 out of scope, and 6 proposed cases. These are
AI-assisted annotations with scoped human decisions, not fully approved gold.

## Your decisions applied

- Item 3, Memories: adjacent scope approved and applied. The inclusion reason
  `known_item_retrieval_journey_described` and one-case proposal are prepared
  from the source below; those new details still need confirmation.
- Item 7, poodles: the later first-person search is accepted as real evidence.
  Illustrative counts and other breeds remain excluded from measured counts
  and extra cases. The original case-field proposals are unchanged.
- Item 9, cats: severity 3 is approved. Other case-field proposals are unchanged.
- Item 10, oldest photos: out-of-scope / insufficient-evidence / zero-case
  proposal accepted. Loss mechanism is not inferred.

The exact scope of each decision is recorded in `human_decisions.jsonl`. This
does not approve the other six documents or every field in items 3, 7 and 9.
No independent reviewer, adjudication or agreement score is claimed.

## New Memories case proposed for confirmation

Source: "My photo memories come up and I can see randomly but how do I go back to view them?"

- One retrieval need: revisit the previously displayed photo Memories collection.
- Known-item status: stated / explicit, supported by "My photo memories come up and I can see randomly".
- Asset type: stated / photo, supported by "My photo memories".
- No specific subject, remembered cue, forgotten information, query, returned
  failure, workaround, final outcome, impact, severity, reformulation count or
  reason for needing the content is supplied. These remain `not_stated`.
- Asking how to go back is a navigation need; it is not a retrieval trigger,
  an executed search method or a demonstrated failed system response.

Confirm the new inclusion reason, one-case count and case fields after review,
or request changes. Scope will remain adjacent as you instructed.

## Remaining work

The Memories document and short YouTube document still require another
independent human reviewer under the unchanged manifest. AI assistance and your
review are disclosed; neither is fabricated as independent double-coding.
Other unapproved labels/fields remain drafts. Official gold and quality reports
are unchanged; quality gates and M1 are pending/incomplete. No model/API calls,
holdout text access, evaluation, commit or push were made.

Detailed sources, expected values and all quotes are in REVIEW.md.
"""
(NEW / "APPROVAL.md").write_text(approval, encoding="utf-8")
lines = ["# Revised annotations with scoped human review", "", "Read APPROVAL.md for approval boundaries and human_decisions.jsonl for the ledger. Exact source quotes are retained; original draft 01 is unchanged.", ""]
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
(NEW / "README.md").write_text("# Revised AI-assisted annotation pack\n\nSee APPROVAL.md and human_decisions.jsonl. Validate using the existing scripts/validate_annotations.py --pack data/annotation/dev-starter-2026-10-03/ai-assisted-draft-02. Do not emit into official gold or treat the AI reviewer as a second independent human reviewer.\n", encoding="utf-8")
assert hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
print(json.dumps({"revision": str(NEW), "document_count": 10, "case_count": 6, "scope_counts": scope_counts, "human_decisions_recorded": 4, "protected_files_unchanged": len(hashes), "official_gold_records_written": 0}))
