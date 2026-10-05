"""Record the owner's approved, single-human-reviewer annotation protocol."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "ai-assisted-draft-03"
NEW = ROOT / "sunayana-reviewed-01"
STAMP = datetime.now(timezone.utc).isoformat()
if NEW.exists():
    raise SystemExit("Refusing existing reviewed destination")
protected = [p for folder in (ROOT / "ai-assisted-draft-01", ROOT / "ai-assisted-draft-02", OLD) for p in folder.rglob("*") if p.is_file()]
protected += [ROOT / "manifest.json", ROOT / "selection.json", *sorted((ROOT / "packets").glob("*.json")), Path("data/gold/documents.jsonl"), Path("data/gold/cases.jsonl"), Path("data/interim/phase4/relevance_split_manifest.csv")]
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
policy = {
    "version": "single-reviewer-ai-assisted/v1", "human_reviewer": "Sunayana",
    "approved_on": "2026-10-04", "recorded_at": STAMP, "client_timezone": "Asia/Calcutta",
    "human_reviewer_count": 1, "ai_assisted": True, "blinded_independent_coding": False,
    "second_human_review_required": False, "adjudication_performed": False,
    "inter_reviewer_agreement": {"status": "not_performed_single_reviewer", "raw_agreement": None, "cohen_kappa": None},
    "authorization": "There is no second reviewer as such you can name the current files with my name as the reviewer. Its an individual project i cant involve more people in it",
    "draft_approval": "I have reviewed both the documents in detail and approve the drafts",
    "original_seating_and_split_unchanged": True,
    "limitations": ["AI-generated drafts were reviewed and corrected by one human; no independent inter-coder validation.", "Ten development documents are a small diagnostic sample, not full quality certification.", "The family-album core scope exception remains disclosed."],
}
review_manifest = json.loads(json.dumps(manifest))
review_manifest["review_policy"] = policy["version"]
review_manifest["source_seating_manifest"] = "seating_manifest.json"
for row in review_manifest["documents"]:
    row["original_double_code_requested"] = row["double_code"]
    row["double_code"] = False
    row["review_policy_change"] = "Owner explicitly authorized single-reviewer protocol; original flag preserved above."
assert [(r["doc_id"],r["gold_split"],r["phase4_split"]) for r in manifest["documents"]] == [(r["doc_id"],r["gold_split"],r["phase4_split"]) for r in review_manifest["documents"]]

NEW.mkdir()
(NEW / "packets").mkdir()
(NEW / "labels" / "Sunayana").mkdir(parents=True)
(NEW / "seating_manifest.json").write_bytes((OLD / "manifest.json").read_bytes())
(NEW / "manifest.json").write_text(json.dumps(review_manifest,indent=2)+"\n",encoding="utf-8")
(NEW / "review_policy.json").write_text(json.dumps(policy,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
(NEW / "vocabularies.json").write_bytes((OLD / "vocabularies.json").read_bytes())
(NEW / "scope_exceptions.json").write_bytes((OLD / "scope_exceptions.json").read_bytes())
case_count = 0
for row in manifest["documents"]:
    name = row["doc_id"] + ".json"
    (NEW / "packets" / name).write_bytes((OLD / "packets" / name).read_bytes())
    review = json.loads((OLD / "labels" / "codex_ai_draft" / name).read_text(encoding="utf-8"))
    review["labeler_id"] = "Sunayana"
    review["labeled_at"] = STAMP
    review["adjudicated"] = False
    review["pre_adjudication_labels"] = []
    review["notes"] = "Approved AI-assisted annotation; sole human reviewer: Sunayana, 2026-10-04. Prepared from AI draft revision 03, reviewed/approved by the owner after scoped corrections. Not a blinded independent coding pass; no second reviewer, adjudication or agreement score. Historical drafting/review rationale follows: " + review["notes"]
    review["review_provenance"] = {"human_reviewer": "Sunayana", "draft_author": "Codex", "ai_assisted": True, "approved": True, "approved_on": "2026-10-04", "recorded_at": STAMP, "source_revision": str(OLD), "review_policy": policy["version"]}
    for case in review["cases"]:
        case["labeler_id"] = "Sunayana"
        case["adjudicated"] = False
        case["notes"] = "Approved AI-assisted case; sole human reviewer Sunayana. Prior proposal rationale (historical pending language superseded by the owner's blanket draft approval): " + str(case.get("notes") or "")
        case_count += 1
    for check in review.get("reviewer_checks", []):
        check["notes"] = "The owner approved the reviewed draft; no separate per-check answer was supplied. This does not represent independent second coding."
    (NEW / "labels" / "Sunayana" / name).write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
approval_record = {"decision": "approve_current_drafts_single_reviewer", "reviewer": "Sunayana", "approved_on": "2026-10-04", "recorded_at": STAMP, "source_revision": str(OLD), "approved_documents": [r["doc_id"] for r in manifest["documents"]], "approved_case_count": case_count, "review_policy": policy["version"], "draft_approval": policy["draft_approval"], "method_authorization": policy["authorization"], "original_double_code_requests_waived": [r["doc_id"] for r in manifest["documents"] if r["double_code"]]}
(NEW / "human_decisions.jsonl").write_bytes((OLD / "human_decisions.jsonl").read_bytes()+ (json.dumps(approval_record,ensure_ascii=False)+"\n").encode("utf-8"))
provenance = {"role": "human_approved_ai_assisted_annotations", "human_reviewer": "Sunayana", "document_count": 10, "case_count": case_count, "review_policy": policy["version"], "provider_calls": 0, "official_gold_records_written": 0, "protected_file_sha256": hashes}
(NEW / "provenance.json").write_text(json.dumps(provenance,indent=2)+"\n",encoding="utf-8")
(NEW / "APPROVAL.md").write_text("""# Approved annotations: sole reviewer Sunayana

Sunayana approved the current drafts and explicitly authorized an individual-
project, single-human-reviewer method on 2026-10-04. All 10 approved review files
are in `labels/Sunayana/`; document and case reviewer IDs are `Sunayana`.
AI assistance remains disclosed. No second reviewer, blinded coding,
adjudication or inter-reviewer agreement is claimed. Raw agreement and Cohen's
kappa are unavailable because independent double-coding was not performed.

The approved set contains 3 core, 3 adjacent and 4 out-of-scope documents,
with six cases. The family-album core label remains a disclosed scope exception;
forgotten cues, impact and outcome are not invented to justify that instruction.

Original source packets, prior drafts and frozen splits are preserved. The
original seating manifest is stored byte-for-byte as `seating_manifest.json`.
The new review manifest explicitly waives its procedural double-code flags
under the owner's authorization; document IDs and split assignments are unchanged.
The existing annotation validator/emitter is reused without changing its guards.

Approved source text, field values and quotes remain traceable through the
copied packets and reviewed JSON files. `review_policy.json` and the appended
decision ledger preserve authorization and the single-reviewer limitation.

This does not establish extraction quality or complete M1. Official gold and
existing reports have not been overwritten. A separate development reference
export can now include all ten records under the disclosed single-reviewer method.
""",encoding="utf-8")
(NEW / "README.md").write_text("# Sunayana's reviewed development annotations\n\nRead APPROVAL.md and review_policy.json. labels/Sunayana contains approved AI-assisted files. The review manifest changes review procedure only, under explicit owner authorization. Original seating/splits and all earlier drafts remain unchanged. Use scripts/validate_annotations.py to validate and emit a fresh development reference export; do not imply an independent double-coded gold set.\n",encoding="utf-8")
assert hashes == {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
print(json.dumps({"approved_pack":str(NEW),"reviewer":"Sunayana","approved_documents":10,"approved_cases":case_count,"human_reviewer_count":1,"original_files_preserved":len(hashes),"provider_calls":0}))
