"""Prepare private, unapproved source-only AI annotation drafts; no network."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "ai-assisted-draft-01"
LABELER = "codex_ai_draft"
STAMP = datetime.now(timezone.utc).isoformat()
if DEST.exists():
    raise SystemExit("Refusing existing draft destination")

MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PACKETS = {r["doc_id"]: json.loads((ROOT / "packets" / (r["doc_id"] + ".json")).read_text(encoding="utf-8")) for r in MANIFEST["documents"]}
assert len(PACKETS) == 10
assert all(p["gold_split"] == "dev" and p["phase4_split"] == "development" for p in PACKETS.values())

def scalar(value):
    return {"observation": "stated", "value": value}

def many(*values, subject_detail=None):
    return scalar([{"value": v, "detail": subject_detail if subject_detail is not None else None} for v in values])

def span(doc, field, quote):
    text = PACKETS[doc]["source_text"]
    start = text.index(quote)
    assert text.find(quote, start + 1) == -1, (doc, field, "ambiguous quote")
    return {"field_name": field, "quote": quote, "start_char": start, "end_char": start + len(quote)}

def case(doc, updates, evidence, notes):
    template = PACKETS[doc]["case_template"]
    list_fields = {"target_subjects", "remembered_cues", "forgotten_information", "query_strategies", "system_responses", "workarounds", "impact_signals"}
    values = {k: {"observation": "not_stated", "value": [] if k in list_fields else None} for k in template["expected_values"]}
    values.update(updates)
    return {"ordinal": 1, "expected_values": values, "evidence": [span(doc, f, q) for f, q in evidence], "notes": notes}

SPECS = {}
def add(doc, scope, reason, prefilter, notes, cases=(), flags=()):
    SPECS[doc] = {"scope": scope, "reason": reason, "prefilter": prefilter, "notes": notes, "cases": list(cases), "flags": list(flags)}

d = "google_support-2a080da4b930"
add(d, "adjacent_known_item_retrieval", "known_item_retrieval_journey_described", True,
    "The user wants a particular family photo inside an album and describes unavailable face search. No forgotten or approximate cue is stated.",
    [case(d, {
        "known_item_status": scalar("explicit"),
        "target_asset_type": scalar("photo"),
        "target_subjects": many("person", subject_detail="one of my family"),
        "remembered_cues": many("relationship"),
        "query_strategies": many("person_or_face_search"),
        "system_responses": {"observation": "uncertain", "value": [{"value": "filter_or_scope_mismatch", "detail": None}]},
    }, [
        ("known_item_status", "to find the one I want"),
        ("target_asset_type", "scroll through hundreds of photos to find the one I want"),
        ("target_subjects", "one of my family"),
        ("remembered_cues", "one of my family"),
        ("query_strategies", "It seems you can't search for a face within a specific album"),
        ("system_responses", "It seems you can't search for a face within a specific album"),
    ], "Face search is the requested approach, not a reported exact query. 'Have to scroll' describes the required alternative; completed scrolling, time consumed and final outcome are not established. The trigger is not stated. The scope limitation is hedged ('It seems'), so the reported system behavior is uncertain.")],
    ["Confirm requested face-search approach versus an actual search attempt.", "Confirm the hedged album limitation's observation status."])

add("google_support-4f34e2312ca6", "out_of_scope", "storage_backup_or_sync", False,
    "Bulk photos/videos disappear after connecting and disconnecting a tablet/account. This is a data availability/backup story, with no particular remembered item or retrieval journey. Deletion is not confirmed.")

add("google_support-5b2ec98df32b", "out_of_scope", "casual_browsing_without_known_target", True,
    "The user asks how to revisit randomly displayed photo memories. The body identifies no particular photo or remembered episode to retrieve. A broad high-recall screen should retain this ambiguous navigation request for classification.",
    flags=["Borderline: approve out-of-scope only if general revisiting of Memories is not a sufficiently specific known target. Adjacent is the alternative; no incomplete recall is stated.", "Manifest requires an independent second human review."])

add("google_support-8c6ab430fbee", "out_of_scope", "storage_backup_or_sync", False,
    "The source describes 90% of old photos disappearing after backup, including absence from trash/account. This is bulk backup/data availability, rather than retrieval of a particular remembered item. The source does not establish actual deletion.")

add("play_store-fb8c41525287", "out_of_scope", "editing_sharing_or_printing", False,
    "Generic disappearing-after-editing and nonfunctional edit/share/ask controls, without a particular known target or a personal retrieval episode. The word 'find' does not establish a retrieval case.")

d = "reddit-0d477b54fb9b"
add(d, "core_incomplete_recall", "known_item_with_incomplete_recall", True,
    "The user explicitly has an older photo of the same item but cannot find it and cannot remember when it was taken. Their proposed reference-photo search is not reported as performed.",
    [case(d, {
        "known_item_status": scalar("explicit"),
        "target_asset_type": scalar("photo"),
        "remembered_cues": many("object_or_subject"),
        "forgotten_information": many("exact_date"),
        "outcome": scalar("not_found"),
    }, [
        ("known_item_status", "an older photo I have of that same item"),
        ("target_asset_type", "an older photo I have of that same item"),
        ("remembered_cues", "an older photo I have of that same item"),
        ("forgotten_information", "I don't remember when I took the photo"),
        ("outcome", "I have so many photos I can't find it"),
    ], "The source states a failed search for the item, but not a specific system response or executed image-search strategy. 'When' is coded as exact_date; it does not establish forgotten time-of-day. The item is unspecified, so no subject type is inferred. No stated impact, severity, trigger or reformulation count.")],
    ["Confirm mapping nonspecific forgotten 'when' to exact_date."])

d = "reddit-87311c2633df"
q = "doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album."
add(d, "adjacent_known_item_retrieval", "known_item_with_precise_recall_failure", True,
    "The initial 'Say I have' framing is hypothetical, but the later first-person CtrlF attempt and currently visible poodle ground a real album retrieval issue. Precise breed is recalled; scattered dates do not establish forgotten dates.",
    [case(d, {
        "known_item_status": scalar("explicit"),
        "target_asset_type": scalar("photo"),
        "target_subjects": many("pet_or_animal", subject_detail="poodles"),
        "remembered_cues": many("object_or_subject"),
        "query_strategies": many("single_keyword"),
        "system_responses": many("no_results"),
        "query_paraphrase": scalar("poodles"),
    }, [
        ("known_item_status", q),
        ("target_asset_type", "there are 0 poodle pictures even though I'm looking at one at the top of the album"),
        ("target_subjects", "poodle pictures"),
        ("remembered_cues", "searching for poodles"),
        ("query_strategies", q),
        ("system_responses", "it says there are 0 poodle pictures"),
    ], "The counts 500/75 and proposed grouping of other breeds are illustrative, not independent episodes or measured corpus quantities. The field query_paraphrase records the reported search term, without presenting it as a delimited exact query. Zero CtrlF results are a system response; the ultimate retrieval/grouping outcome is unstated. Proposed manual paging is not treated as a completed workaround or time loss.")],
    ["Confirm later first-person evidence sufficiently grounds the initially hypothetical album example."])

d = "reddit-bde62ddef9b5"
add(d, "core_incomplete_recall", "known_item_with_incomplete_recall", True,
    "The author recalls a particular video but not when it was taken and describes successfully retrieving it with a natural-language query. Successful retrieval remains relevant to the discovery question.",
    [case(d, {
        "known_item_status": scalar("explicit"),
        "target_asset_type": scalar("video"),
        "target_subjects": {"observation": "uncertain", "value": []},
        "remembered_cues": many("activity"),
        "forgotten_information": many("exact_date"),
        "query_strategies": many("natural_language_description"),
        "system_responses": many("other"),
        "outcome": scalar("found"),
        "exact_query": scalar("Show me videos of Suzie sleeping"),
    }, [
        ("known_item_status", "I took a video of it once"),
        ("target_asset_type", "I took a video of it once"),
        ("target_subjects", "my 3rd used to listen to the weirdest white noise"),
        ("remembered_cues", "Show me videos of Suzie sleeping"),
        ("forgotten_information", "I can't remember when it was"),
        ("query_strategies", 'I can type in "Show me videos of Suzie sleeping" and up it pops.'),
        ("system_responses", "and up it pops"),
        ("outcome", "and up it pops"),
        ("exact_query", "Show me videos of Suzie sleeping"),
    ], "Suzie and 'my 3rd' do not unambiguously establish a person versus another subject from this body alone; subject type remains uncertain. White noise is not treated as a retrieval trigger. No explicit impact or severity. 'Other' means the desired asset surfaces, since the response vocabulary has no successful-result member.")],
    ["Confirm forgotten 'when' coding and uncertain subject type."])

d = "reddit-c2c00b25a88b"
journey = "I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one."
add(d, "adjacent_known_item_retrieval", "known_item_with_precise_recall_failure", True,
    "The user recalls their cat pictures, receives no results, tries Gallery and resorts to manual scrolling to show a friend. No incomplete recall is described.",
    [case(d, {
        "known_item_status": scalar("explicit"),
        "target_asset_type": scalar("photo"),
        "target_subjects": many("pet_or_animal", subject_detail="cats"),
        "remembered_cues": many("object_or_subject"),
        "query_strategies": many("external_app_or_search", "manual_scrolling"),
        "system_responses": many("no_results", "other"),
        "workarounds": many("used_external_app", "manual_scrolling"),
        "impact_signals": many("repeat_effort"),
        "severity": scalar(3),
        "retrieval_trigger": scalar("show a friend some pictures over the weekend"),
    }, [
        ("known_item_status", "I remember being able to find such straightforward pictures with ease."),
        ("target_asset_type", "look for the photos one-by-one"),
        ("target_subjects", "pictures of my cats"),
        ("remembered_cues", "pictures of my cats"),
        ("query_strategies", journey),
        ("system_responses", "but got no results"),
        ("system_responses", "Gallery app but it also has no search function"),
        ("workarounds", journey),
        ("impact_signals", journey),
        ("severity", journey),
        ("retrieval_trigger", "I was trying to show a friend some pictures over the weekend"),
    ], "Multiple paths and forced item-by-item browsing support repeat_effort and rubric severity 3. No elapsed time is stated, so time_loss is absent. The initial exact query/keyword and eventual outcome are not stated. Frustration alone is not coded as distress.")],
    ["Severity 3 is a rubric judgment from demonstrated alternative paths/manual browsing; review this ordinal choice."])

add("youtube-17fd27447275", "out_of_scope", "insufficient_evidence_for_a_case", True,
    "'Lost my oldest photos' establishes neither a specific remembered target nor a retrieval attempt; it could refer to loss or inability to retrieve. Do not infer deletion, backup or incomplete recall. A broad prefilter should retain this ambiguous short text.",
    flags=["Very short ambiguous text: confirm exclusion for insufficient evidence, rather than assume a loss mechanism.", "Manifest requires an independent second human review."])

assert set(SPECS) == set(PACKETS)
protected = [ROOT / "manifest.json", ROOT / "selection.json", *sorted((ROOT / "packets").glob("*.json")), Path("data/gold/documents.jsonl"), Path("data/gold/cases.jsonl"), Path("data/interim/phase4/relevance_split_manifest.csv")]
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
DEST.mkdir()
(DEST / "packets").mkdir()
(DEST / "labels" / LABELER).mkdir(parents=True)
(DEST / "manifest.json").write_text(json.dumps(MANIFEST, indent=2) + "\n", encoding="utf-8")
(DEST / "vocabularies.json").write_bytes((ROOT / "vocabularies.json").read_bytes())
all_reviews = []
for doc, p in PACKETS.items():
    (DEST / "packets" / (doc + ".json")).write_bytes((ROOT / "packets" / (doc + ".json")).read_bytes())
    spec = SPECS[doc]
    review = {
        "doc_id": doc, "split": "dev", "scope_class": spec["scope"], "reason_code": spec["reason"],
        "prefilter_should_pass": spec["prefilter"], "expected_case_count": len(spec["cases"]),
        "labeler_id": LABELER, "labeled_at": STAMP, "adjudicated": False, "pre_adjudication_labels": [],
        "notes": "AI-assisted unapproved draft. Not an independent human label. " + spec["notes"],
        "cases": spec["cases"],
        "reviewer_checks": [{"check": c["check"], "passed": None, "notes": "Human confirmation remains pending; see case notes and evidence."} for c in p["reviewer_checks"]],
    }
    (DEST / "labels" / LABELER / (doc + ".json")).write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    all_reviews.append(review)

summary = {
    "role": "ai_assisted_drafts_pending_human_review", "prepared_at": STAMP,
    "document_count": 10, "case_count": sum(len(s["cases"]) for s in SPECS.values()),
    "scope_counts": {scope: sum(s["scope"] == scope for s in SPECS.values()) for scope in ("core_incomplete_recall", "adjacent_known_item_retrieval", "out_of_scope")},
    "provider_calls": 0, "human_approvals": 0, "gold_records_written": 0,
    "double_code_documents": [r["doc_id"] for r in MANIFEST["documents"] if r["double_code"]],
    "protected_file_sha256": before,
    "drafts": [{"doc_id": d, "scope_class": s["scope"], "expected_case_count": len(s["cases"]), "review_flags": s["flags"]} for d,s in SPECS.items()],
}
(DEST / "provenance.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

lines = ["# Ten development annotation drafts for approval", "", "These are source-grounded AI-assisted proposals, not independent human gold labels. No prediction file was read for this drafting task. Earlier conversation/selection context exists, so this is not claimed as a blinded review.", "", "10 documents: 2 core, 3 adjacent, 5 out of scope; 5 proposed cases. All human approvals remain pending. The original pack, official gold files and splits are unchanged. The two manifest-designated double-code documents still require independent human reviews; approval of this AI draft does not satisfy that requirement.", "", "Read the source and proposed values below. Approve or request changes by document ID. In particular, confirm the Memories navigation exclusion, the poodle example's real-world grounding, the short YouTube exclusion and the cat case's severity. Approval must retain AI-assistance provenance. Do not emit these drafts as official gold automatically.", ""]
for review in all_reviews:
    doc = review["doc_id"]
    p = PACKETS[doc]
    s = SPECS[doc]
    lines += [f"## {doc}", "", f"Source: {p['provenance'].get('source_url')}", "", "### Source text", "", "> " + p["source_text"].replace("\n", "\n> "), "", "### Proposed document label", "", f"- Scope: `{s['scope']}`", f"- Reason: `{s['reason']}`", f"- Prefilter should pass: `{str(s['prefilter']).lower()}`", f"- Expected cases: {len(s['cases'])}", "", s["notes"], ""]
    if s["flags"]:
        lines += ["Approval points:", "", *["- " + f for f in s["flags"]], ""]
    for c in s["cases"]:
        lines += ["### Proposed case fields", ""]
        for field, payload in c["expected_values"].items():
            lines += [f"- `{field}`: `{payload['observation']}`; value `{json.dumps(payload['value'], ensure_ascii=False)}`"]
        lines += ["", "Supporting continuous source quotes:", ""]
        for e in c["evidence"]:
            lines += [f"- `{e['field_name']}` [{e['start_char']}, {e['end_char']}): {e['quote']}"]
        lines += ["", c["notes"], ""]
    lines += ["Human decision: pending. Reviewer check answers: pending.", ""]
(DEST / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(DEST / "README.md").write_text("# Private AI-assisted draft pack\n\nRead REVIEW.md before approving anything. The copied packets use only the original ten development documents. labels/codex_ai_draft contains ten proposed labels. No prediction file is copied. provenance.json records the origin and preserved hashes. Do not count these as independent human reviews or double-coding. Original pack and official gold are unchanged.\n\nLocal contract validation:\n\n```powershell\n.\\.venv\\Scripts\\python.exe scripts\\validate_annotations.py --pack data/annotation/dev-starter-2026-10-03/ai-assisted-draft-01\n```\n\nA valid result establishes parsing/contracts and exact quotes, not semantic approval. No evaluation or gold promotion is authorized by generation of this pack. Human approval and the two genuine independent review requirements remain pending.\n", encoding="utf-8")
assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
print(json.dumps({"draft_destination": str(DEST), "documents": 10, "cases": summary["case_count"], "scopes": summary["scope_counts"], "protected_files_unchanged": len(before), "provider_calls": 0, "gold_records_written": 0}))
