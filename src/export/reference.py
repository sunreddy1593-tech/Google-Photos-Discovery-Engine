"""Publish reviewed development reference evidence without approving model rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.export.privacy import leak_findings
from src.models.export import ExportedEvidenceSpan, PublicExportRecord


def build_reference(pack: Path, destination: Path) -> dict:
    from src.gold.annotate import _cases_from_review
    from src.gold.load import load_gold_cases, load_gold_documents
    if destination.exists():
        raise ValueError("Reference export destination must be fresh")
    gold = pack / "development-reference-02"
    documents = load_gold_documents(gold / "documents.jsonl")
    cases = {row.gold_case_id:row for row in load_gold_cases(gold / "cases.jsonl")}
    if any(row.split.value != "dev" or row.labeler_id != "Sunayana" for row in documents):
        raise ValueError("Only the approved Sunayana development reference is allowed")
    records = []
    case_metadata = []
    hashes = {}
    for document in documents:
        doc = document.doc_id
        packet_path = pack.parent / "packets" / f"{doc}.json"
        review_path = pack / "labels/Sunayana" / f"{doc}.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review["split"] != "dev" or packet["gold_split"] != "dev":
            raise ValueError("Holdout reference text cannot enter the public demonstration")
        source = packet["source_text"]
        provenance = packet["provenance"]
        converted = _cases_from_review(doc, review["cases"], source, labeler_id="Sunayana")
        if len(converted) != document.expected_case_count:
            raise ValueError("Reviewed case count differs from approved reference")
        for path in (packet_path, review_path):
            hashes[path.name+('/review' if path==review_path else '/packet')] = hashlib.sha256(path.read_bytes()).hexdigest()
        for index, candidate in enumerate(converted):
            approved = cases.get(candidate.gold_case_id)
            if (not approved or approved.expected_values != candidate.expected_values
                    or approved.expected_evidence != candidate.expected_evidence):
                raise ValueError("Reviewed values/evidence differ from the immutable approved reference")
            item = review["cases"][index]
            supported = {}
            for ordinal, span in enumerate(item["evidence"]):
                quote = span["quote"]
                start, end = span["start_char"], span["end_char"]
                field = span["field_name"]
                if len(quote) > 480 or quote == source:
                    raise ValueError("A reference quote exceeds public excerpt bounds or is complete source text")
                value = candidate.expected_values.get(field)
                assigned = {field:value} if value else {}
                if value:
                    supported[field] = value
                record = PublicExportRecord(
                    case_id=f"{candidate.gold_case_id}:e{ordinal:02d}", doc_id=doc,
                    source_platform=provenance["source_platform"], source_type=provenance["source_type"],
                    evidence_tier=provenance["evidence_tier"], source_name=provenance["source_name"],
                    source_url=provenance["source_url"], canonical_url=provenance["source_url"],
                    published_at=provenance.get("published_at"), collected_at=provenance.get("collected_at"),
                    excerpt=quote, excerpt_start_char=start, excerpt_is_full_text=False,
                    evidence_spans=(ExportedEvidenceSpan(field_name=field, quote=quote,
                        excerpt_start_char=0, excerpt_end_char=len(quote),
                        document_start_char=start, document_end_char=end),),
                    extracted_fields={"reference_case_id":candidate.gold_case_id,
                        "reference_label_approved":True, "model_output":False,
                        "reviewer":"Sunayana", "scope_class":document.scope_class.value,
                        "assigned_values":assigned,
                        "approval_basis":"AI-assisted development reference reviewed and approved by owner"},
                    dataset_version="approved-dev-reference/02",
                )
                records.append(record.model_dump(mode="json"))
            case_metadata.append({"case_id":candidate.gold_case_id, "doc_id":doc,
                "scope_class":document.scope_class.value, "assigned_values":supported,
                "source_platform":provenance["source_platform"],
                "missing_support_fields":sorted(set(candidate.expected_values)-set(supported))})
    if {row["case_id"] for row in case_metadata} != set(cases):
        raise ValueError("Reference evidence coverage is incomplete")
    metadata = {"reference_version":"approved-dev-reference/02", "documents":len(documents),
        "cases":len(case_metadata), "evidence_fragments":len(records), "reference_cases":case_metadata,
        "input_sha256":hashes, "model_outputs_approved":False,
        "limitations":["Six reviewed development reference cases; not model extraction recovery or population prevalence.",
                       "AI-assisted drafting and sole-human review; no independent second coder.",
                       "Scope exceptions remain disclosed; the family-album core label is an owner-directed exception.",
                       "Evidence fragments are not additional cases. Null/unstated fields are not filled by inference."]}
    if leak_findings(records) or leak_findings(metadata):
        raise ValueError("Public reference export failed privacy scan")
    destination.mkdir(parents=True)
    (destination/'cases.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in records),encoding='utf-8')
    (destination/'reference.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return metadata


def load_reference(path: Path) -> tuple[dict, list[dict]]:
    if not (path/'reference.json').is_file():
        return {}, []
    metadata = json.loads((path/'reference.json').read_text(encoding='utf-8'))
    records = [PublicExportRecord.model_validate_json(line).model_dump(mode='json')
               for line in (path/'cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return metadata, records


def reference_comparison(metadata: dict) -> dict:
    """Count reviewed field assignments, preserving links and unstated fields."""
    from collections import Counter
    result = {}
    for field in ("remembered_cues", "forgotten_information", "query_strategies", "system_responses", "outcome"):
        counts = Counter()
        links = {}
        unstated = []
        for case in metadata.get("reference_cases", []):
            observed = case.get("assigned_values", {}).get(field)
            if not observed or observed.get("observation") != "stated":
                unstated.append(case["case_id"])
                continue
            values = observed.get("value")
            values = values if isinstance(values, list) else [values]
            for value in set(str(v) for v in values if v not in (None, "")):
                counts[value] += 1
                links.setdefault(value, []).append(case["case_id"])
        result[field] = {"rows":[{"value":value, "count":count, "cases":links[value]}
                                  for value,count in counts.most_common()], "unstated_cases":unstated}
    return result
