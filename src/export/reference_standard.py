"""Automatic classification assessed against the human-reviewed standard.

The standard is the immutable n8n reviewed reference. This module takes
prepared public export cards, which already passed the existing evidence gate,
and decides whether each case may enter a clearly labelled automated
comparison. It makes no model call, reads no raw private file, and never sets
semantic approval. Resemblance to a reference record is not consulted and does
not establish relevance; relevance and extraction stay with the existing
classifier and extractor.

The Streamlit app imports this module. It must not import the export builder,
collection, extraction, or a provider.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.core.ids import sha1_short
from src.core.versions import SCHEMA_VERSION
from src.export.compare import ADJACENT, CORE, DIMENSIONS
from src.export.reviewed_reference import (
    HUMAN_REVIEWED_LABEL,
    NOT_RETRIEVAL_PROBLEM,
    RETRIEVAL_PROBLEM,
)
from src.export.scheduled_status import load_snapshot, publish_snapshot, read_snapshot_version

AUTOMATED_LABEL = "Automatically classified using the human-reviewed standard"
AUTOMATED_NOTE = (
    "These results passed automatic checks and have not been individually reviewed by a person. "
    "They are not human-approved findings. No accuracy against the reference has been measured."
)
UNKNOWN = "unknown"

VERDICT_ELIGIBLE = "eligible"
VERDICT_FLAGGED = "flagged"
VERDICT_FAILED = "failed_or_incomplete"
VERDICT_REFERENCE_OVERLAP = "excluded_reference_overlap"
VERDICT_UNVERIFIABLE = "unverifiable"

ELIGIBILITY_RULES: tuple[str, ...] = (
    "The record is an extraction case that passed the existing automatic evidence gate.",
    "The model scope class is core_incomplete_recall or adjacent_known_item_retrieval; the two stay in separate buckets and out_of_scope decisions are counted separately.",
    "Every evidence quote is one continuous span that equals the exported excerpt at its stored offsets, and the offsets reconcile with the document coordinates.",
    "No rejected, invented, abbreviated or spliced model text is attached to the case.",
    "A stated retrieval_trigger has its own evidence span and no recorded objection.",
    "Stated impact signals or severity have their own evidence spans and no recorded objection.",
    "A problem_summary has a supporting evidence span and no recorded objection.",
    "No recorded semantic finding stands against the case.",
    "The public source link is present.",
    "The document is not one of the human-reviewed reference records; those stay in the human-reviewed view.",
    "A case id already assessed in the same snapshot is skipped, not counted twice.",
    "Semantic approval is never set by this layer. Passing these checks is not human approval.",
)

_SCOPE_TO_REVIEWED = {
    CORE: RETRIEVAL_PROBLEM,
    ADJACENT: RETRIEVAL_PROBLEM,
    "out_of_scope": NOT_RETRIEVAL_PROBLEM,
}
_ASSET_TO_PHOTO_TYPE = {"screenshot": "screenshot"}


def assessment_identity(
    *,
    reference_version: str,
    relevance_prompt: str,
    extraction_prompt: str,
    schema_version: str,
    model: str,
    case_id: str,
    dataset_version: str,
) -> str:
    """Identity of one assessment. A new reference or prompt version is a new identity."""
    payload = {
        "reference_version": reference_version,
        "relevance_prompt": relevance_prompt,
        "extraction_prompt": extraction_prompt,
        "schema_version": schema_version,
        "model": model,
        "case_id": case_id,
        "dataset_version": dataset_version,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def reference_doc_index(records: list[dict[str, Any]]) -> dict[str, str]:
    """Expected doc ids and URL keys of the human-reviewed records."""
    index: dict[str, str] = {}
    for row in records:
        for key in ("expected_doc_id", "source_url_key", "source_url"):
            value = row.get(key)
            if isinstance(value, str) and value:
                index[value] = str(row.get("reference_record_id") or "")
    return index


def assess_case(
    card: dict[str, Any],
    *,
    reference_version: str,
    reference_index: dict[str, str],
    pins: dict[str, Any],
    dataset_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Deterministic checks on one public card. Nothing here approves a case."""
    scope = str(card.get("model_scope_class") or "")
    reasons: list[str] = []
    checks: dict[str, Any] = {}
    spans = list(card.get("evidence_spans") or [])
    excerpt = str(card.get("excerpt") or "")
    origin = int(card.get("excerpt_start_char") or 0)
    kind = str(card.get("kind") or "")
    automatically_valid = bool(card.get("automatically_valid"))
    overlap = _overlap(card, reference_index)

    checks["is_extraction_case"] = kind == "case"
    if kind != "case":
        reasons.append(f"not an extraction case ({str(card.get('attempt_kind') or kind or 'record')})")
    checks["automatically_valid"] = automatically_valid
    if not automatically_valid:
        reasons.append("did not pass the automatic evidence gate")
    checks["scope_core_or_adjacent"] = scope in (CORE, ADJACENT)
    if scope not in (CORE, ADJACENT):
        reasons.append(f"model scope class is {scope or 'missing'}, not core or adjacent")

    if not excerpt:
        checks["source_context_present"] = False
        reasons.append("no exported source context; quotes cannot be verified here")
    else:
        checks["source_context_present"] = True
    checks["evidence_present"] = bool(spans)
    if not spans:
        reasons.append("no evidence span")
    offsets_ok = True
    continuous_ok = True
    for span in spans:
        start = span.get("excerpt_start_char")
        end = span.get("excerpt_end_char")
        quote = str(span.get("quote") or "")
        doc_start = span.get("document_start_char")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start or end > len(excerpt):
            offsets_ok = False
            continue
        if excerpt[start:end] != quote:
            offsets_ok = False
        if isinstance(doc_start, int) and doc_start - origin != start:
            offsets_ok = False
        if not quote or quote not in excerpt:
            continuous_ok = False
    checks["offsets_valid"] = offsets_ok if spans and excerpt else False
    if spans and not offsets_ok:
        reasons.append("an evidence span does not match the excerpt at its stored offsets")
    checks["quotes_continuous_in_source"] = continuous_ok if spans and excerpt else False
    if spans and excerpt and not continuous_ok:
        reasons.append("a quote is not one continuous span of the available source text")
    rejected = list(card.get("rejected_model_text") or [])
    checks["no_rejected_model_text"] = not rejected
    if rejected:
        reasons.append(f"{len(rejected)} invented, altered or spliced quote(s) attached")

    assigned = card.get("assigned_values") or {}
    span_fields = {str(span.get("field_name") or "") for span in spans}
    findings = list(card.get("findings") or [])
    finding_risks = {str(item.get("risk") or "") for item in findings}
    finding_fields = {str(item.get("field") or "") for item in findings}

    trigger_stated = bool(_value(assigned, "retrieval_trigger"))
    checks["retrieval_trigger_supported"] = (
        not trigger_stated
        or ("retrieval_trigger" in span_fields and "retrieval_trigger" not in finding_fields)
    )
    if not checks["retrieval_trigger_supported"]:
        reasons.append("retrieval_trigger is stated without its own supporting quote or has a recorded objection")

    impact_stated = bool(_value(assigned, "impact_signals")) or bool(_value(assigned, "severity"))
    impact_supported = True
    if _value(assigned, "impact_signals") and ("impact_signals" not in span_fields or "impact_signals" in finding_fields):
        impact_supported = False
    if _value(assigned, "severity") and ("severity" not in span_fields or "severity" in finding_fields):
        impact_supported = False
    if "unsupported_impact" in finding_risks:
        impact_supported = False
    checks["impact_or_severity_supported"] = (not impact_stated) or impact_supported
    if impact_stated and not impact_supported:
        reasons.append("impact or severity is stated without a quote that states it")

    summary = str(card.get("problem_summary") or "")
    checks["summary_supported"] = (
        not summary
        or ("problem_summary" in span_fields and "incomplete_summary" not in finding_risks and "problem_summary" not in finding_fields)
    )
    if summary and not checks["summary_supported"]:
        reasons.append("problem_summary lacks sufficient supporting evidence")

    checks["no_recorded_finding"] = not findings
    for item in findings:
        reasons.append(f"recorded finding on {item.get('field')}: {item.get('risk')}")
    checks["source_link_present"] = bool(card.get("source_url"))
    if not card.get("source_url"):
        reasons.append("source link missing")
    checks["not_a_reviewed_reference_record"] = overlap is None
    if overlap is not None:
        reasons.append(f"document is human-reviewed reference record {overlap}")

    if overlap is not None:
        verdict = VERDICT_REFERENCE_OVERLAP
    elif kind != "case" or not automatically_valid:
        verdict = VERDICT_FAILED
    elif not excerpt:
        verdict = VERDICT_UNVERIFIABLE
    elif reasons:
        verdict = VERDICT_FLAGGED
    else:
        verdict = VERDICT_ELIGIBLE

    extraction_prompt = str(card.get("prompt_version") or pins.get("extraction_prompt") or UNKNOWN)
    relevance_prompt = str(pins.get("relevance_prompt") or UNKNOWN)
    model = str(pins.get("model") or UNKNOWN)
    schema = str(pins.get("schema_version") or SCHEMA_VERSION)
    dataset_version = f"{dataset_id}/{run_id}"
    asset = _value(assigned, "target_asset_type")
    asset_text = str(asset) if asset not in (None, "", [], ()) else ""
    return {
        "label": AUTOMATED_LABEL,
        "case_id": str(card.get("case_id") or ""),
        "doc_id": str(card.get("doc_id") or ""),
        "source_url": str(card.get("source_url") or ""),
        "source_platform": str(card.get("source_platform") or ""),
        "dataset_id": dataset_id,
        "run_id": run_id,
        "model_scope_class": scope,
        "verdict": verdict,
        "eligible_for_automated_comparison": verdict == VERDICT_ELIGIBLE,
        "reasons": reasons,
        "checks": checks,
        "automatically_valid": automatically_valid,
        "semantically_approved": False,
        "recorded_semantic_approval_elsewhere": bool(card.get("semantically_approved")),
        "human_reviewed": False,
        "versions": {
            "reference_version": reference_version,
            "relevance_prompt": relevance_prompt,
            "extraction_prompt": extraction_prompt,
            "schema_version": schema,
            "model": model,
            "provider": str(pins.get("provider") or UNKNOWN),
        },
        "assessment_identity": assessment_identity(
            reference_version=reference_version,
            relevance_prompt=relevance_prompt,
            extraction_prompt=extraction_prompt,
            schema_version=schema,
            model=model,
            case_id=str(card.get("case_id") or card.get("doc_id") or ""),
            dataset_version=dataset_version,
        ),
        "mapped_to_reference": {
            "reviewed_relevance_equivalent": _SCOPE_TO_REVIEWED.get(scope, UNKNOWN),
            "photo_type_equivalent": _ASSET_TO_PHOTO_TYPE.get(asset_text, "not mapped" if asset_text else "not stated"),
        },
        "assigned_values": dict(assigned),
        "evidence_excerpts": [
            {"field_name": str(span.get("field_name") or ""), "quote": str(span.get("quote") or "")}
            for span in spans
        ],
        "excerpt": excerpt,
        "excerpt_start_char": origin,
        "evidence_spans": spans,
    }


def assess_dataset(
    cards: list[dict[str, Any]],
    *,
    reference_version: str,
    reference_index: dict[str, str],
    pins: dict[str, Any],
    dataset_id: str,
    run_id: str,
    seen_case_ids: set[str],
) -> dict[str, Any]:
    """Assess every case and attempt card. Relevance decisions are summarised."""
    assessments: list[dict[str, Any]] = []
    skipped = 0
    relevance = {CORE: 0, ADJACENT: 0, "out_of_scope": 0, "invalid_or_failed": 0}
    for card in cards:
        kind = card.get("kind")
        if kind == "relevance":
            scope = str(card.get("model_scope_class") or "")
            if card.get("automatically_valid") and scope in relevance:
                relevance[scope] += 1
            else:
                relevance["invalid_or_failed"] += 1
            continue
        key = str(card.get("case_id") or f"{card.get('doc_id')}:{card.get('attempt_kind') or kind}")
        if key in seen_case_ids:
            skipped += 1
            continue
        seen_case_ids.add(key)
        assessments.append(
            assess_case(
                card,
                reference_version=reference_version,
                reference_index=reference_index,
                pins=pins,
                dataset_id=dataset_id,
                run_id=run_id,
            )
        )
    return {
        "dataset_id": dataset_id,
        "run_id": run_id,
        "assessments": assessments,
        "duplicates_skipped": skipped,
        "relevance_decisions": relevance,
    }


def automated_comparison(assessments: list[dict[str, Any]]) -> dict[str, Any]:
    """Core and adjacent buckets over eligible cases, with mapped reference dimensions."""
    eligible = [row for row in assessments if row.get("verdict") == VERDICT_ELIGIBLE]
    reviewed: dict[str, int] = {RETRIEVAL_PROBLEM: 0, NOT_RETRIEVAL_PROBLEM: 0, UNKNOWN: 0}
    photo: dict[str, int] = {}
    for row in eligible:
        mapped = row.get("mapped_to_reference") or {}
        reviewed[str(mapped.get("reviewed_relevance_equivalent") or UNKNOWN)] = (
            reviewed.get(str(mapped.get("reviewed_relevance_equivalent") or UNKNOWN), 0) + 1
        )
        key = str(mapped.get("photo_type_equivalent") or "not stated")
        photo[key] = photo.get(key, 0) + 1
    return {
        "label": AUTOMATED_LABEL,
        "case_count": len(eligible),
        "core": _bucket(eligible, CORE),
        "adjacent": _bucket(eligible, ADJACENT),
        "reviewed_relevance_equivalent": reviewed,
        "photo_type_equivalent": photo,
        "mapping_note": (
            "Application scope classes collapse onto the reviewed binary flag; the reviewed "
            "flag does not expand into core or adjacent. Only target_asset_type = screenshot maps "
            "onto the n8n photo_type."
        ),
    }


def counts(
    *,
    reference_records: int,
    datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [row for item in datasets for row in item["assessments"]]
    relevance = {CORE: 0, ADJACENT: 0, "out_of_scope": 0, "invalid_or_failed": 0}
    for item in datasets:
        for key, value in (item.get("relevance_decisions") or {}).items():
            relevance[key] = relevance.get(key, 0) + int(value)
    return {
        "human_reviewed_records": reference_records,
        "cases_assessed": len(rows),
        "automatically_valid_cases": sum(1 for row in rows if row["automatically_valid"]),
        "eligible_cases": sum(1 for row in rows if row["verdict"] == VERDICT_ELIGIBLE),
        "flagged_cases": sum(1 for row in rows if row["verdict"] == VERDICT_FLAGGED),
        "unverifiable_cases": sum(1 for row in rows if row["verdict"] == VERDICT_UNVERIFIABLE),
        "failed_or_incomplete_cases": sum(1 for row in rows if row["verdict"] == VERDICT_FAILED),
        "reference_overlap_excluded": sum(1 for row in rows if row["verdict"] == VERDICT_REFERENCE_OVERLAP),
        "duplicates_skipped": sum(int(item.get("duplicates_skipped") or 0) for item in datasets),
        "cases_with_recorded_semantic_approval_elsewhere": sum(
            1 for row in rows if row["recorded_semantic_approval_elsewhere"]
        ),
        "semantically_approved_by_this_layer": 0,
        "relevance_decisions_by_scope": relevance,
    }


def build_standard_payload(
    *,
    standard: dict[str, Any],
    datasets: list[dict[str, Any]],
    pins: dict[str, Any],
    built_at: str,
) -> dict[str, Any]:
    """Assemble the public snapshot. ``datasets`` come from :func:`assess_dataset`."""
    metadata = standard.get("metadata") or {}
    rows = [row for item in datasets for row in item["assessments"]]
    included = [_public_row(row) for row in rows if row["verdict"] == VERDICT_ELIGIBLE]
    excluded = [_public_row(row) for row in rows if row["verdict"] != VERDICT_ELIGIBLE]
    body = {
        "label": AUTOMATED_LABEL,
        "note": AUTOMATED_NOTE,
        "human_reviewed_label": HUMAN_REVIEWED_LABEL,
        "reference_version": str(standard.get("reference_version") or metadata.get("reference_version") or ""),
        "reference_records": int(metadata.get("records") or 0),
        "reference_records_sha256": str(metadata.get("records_sha256") or ""),
        "reference_ok": bool(standard.get("ok")),
        "built_at": built_at,
        "pins": dict(pins),
        "eligibility_rules": list(ELIGIBILITY_RULES),
        "sources": [
            {
                "dataset_id": item["dataset_id"],
                "run_id": item["run_id"],
                "cases_assessed": len(item["assessments"]),
                "eligible": sum(1 for row in item["assessments"] if row["verdict"] == VERDICT_ELIGIBLE),
                "flagged": sum(1 for row in item["assessments"] if row["verdict"] == VERDICT_FLAGGED),
                "failed_or_incomplete": sum(1 for row in item["assessments"] if row["verdict"] == VERDICT_FAILED),
                "duplicates_skipped": int(item.get("duplicates_skipped") or 0),
                "relevance_decisions": dict(item.get("relevance_decisions") or {}),
            }
            for item in datasets
        ],
        "counts": counts(reference_records=int(metadata.get("records") or 0), datasets=datasets),
        "comparison": automated_comparison(rows),
        "included": included,
        "excluded": excluded,
        "semantically_approved_by_this_layer": 0,
    }
    version_blob = json.dumps(
        {key: body[key] for key in ("reference_version", "pins", "sources", "counts", "included", "excluded")},
        sort_keys=True,
        ensure_ascii=False,
    )
    body["snapshot_version"] = sha1_short("reference-standard", body["reference_version"], version_blob, length=16)
    return body


def publish_standard_snapshot(root: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Publish atomically. An identical snapshot is reported as unchanged, not rewritten."""
    version = str(payload.get("snapshot_version") or "")
    if version and read_snapshot_version(root) == version:
        return {"published": False, "snapshot_version": version, "message": "snapshot unchanged"}
    pointer = publish_snapshot(root, payload)
    return {"published": True, "snapshot_version": version, "pointer": str(pointer)}


def load_standard_snapshot(root: Any) -> dict[str, Any]:
    snapshot = load_snapshot(root)
    if not snapshot.get("ok"):
        snapshot["message"] = snapshot.get("message", "").replace(
            "scheduled processing snapshot", "automated comparison snapshot"
        ).replace("Scheduled snapshot", "Automated comparison snapshot")
    for row in list(snapshot.get("included") or []) + list(snapshot.get("excluded") or []):
        if isinstance(row, dict):
            row["semantically_approved"] = False
            row["human_reviewed"] = False
    snapshot["semantically_approved_by_this_layer"] = 0
    return snapshot


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": AUTOMATED_LABEL,
        "case_id": row["case_id"],
        "doc_id": row["doc_id"],
        "source_url": row["source_url"],
        "source_platform": row["source_platform"],
        "dataset_id": row["dataset_id"],
        "run_id": row["run_id"],
        "model_scope_class": row["model_scope_class"],
        "verdict": row["verdict"],
        "reasons": list(row["reasons"]),
        "checks": dict(row["checks"]),
        "versions": dict(row["versions"]),
        "assessment_identity": row["assessment_identity"],
        "mapped_to_reference": dict(row["mapped_to_reference"]),
        "assigned_values": dict(row["assigned_values"]),
        "evidence_excerpts": list(row["evidence_excerpts"]),
        "excerpt": row["excerpt"],
        "excerpt_start_char": row["excerpt_start_char"],
        "evidence_spans": list(row["evidence_spans"]),
        "automatically_valid": row["automatically_valid"],
        "semantically_approved": False,
        "human_reviewed": False,
        "recorded_semantic_approval_elsewhere": row["recorded_semantic_approval_elsewhere"],
    }


def _bucket(rows: list[dict[str, Any]], scope: str) -> dict[str, Any]:
    from collections import Counter

    group = [row for row in rows if row.get("model_scope_class") == scope]
    dimensions = []
    for field_name, label in DIMENSIONS:
        counter: Counter[str] = Counter()
        links: dict[str, list[str]] = {}
        for row in group:
            for value in _values(row.get("assigned_values") or {}, field_name):
                counter[value] += 1
                links.setdefault(value, []).append(str(row.get("case_id") or row.get("doc_id")))
        dimensions.append(
            {
                "field": field_name,
                "label": label,
                "rows": [{"value": value, "count": count, "cases": links[value]} for value, count in counter.most_common()],
            }
        )
    return {
        "scope_class": scope,
        "case_count": len(group),
        "case_ids": [str(row.get("case_id") or "") for row in group],
        "dimensions": dimensions,
    }


def _values(assigned: dict[str, Any], field_name: str) -> list[str]:
    payload = assigned.get(field_name)
    if not isinstance(payload, dict):
        return []
    value = payload.get("value")
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]


def _value(assigned: dict[str, Any], field_name: str) -> Any:
    payload = assigned.get(field_name)
    if isinstance(payload, dict):
        return payload.get("value")
    return payload


def _overlap(card: dict[str, Any], reference_index: dict[str, str]) -> str | None:
    for key in ("doc_id", "source_url"):
        value = str(card.get(key) or "")
        if value and value in reference_index:
            return reference_index[value]
    return None
