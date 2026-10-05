"""Immutable human-reviewed n8n community-thread reference.

The owner reviewed the saved n8n ``insights`` rows in detail. This module turns
one saved local export of those rows into a versioned artifact that later
automatic classification is compared against. It reads saved files only. It
does not call n8n, Google Sheets, a webhook, or a model, and it does not import
any collection or integration module.

The n8n sheet schema is not the application's case schema. Only mappings that
need no inference are applied. Everything else is preserved under its own n8n
name and reported as unmapped. Missing information is recorded as unavailable,
never filled in.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.ids import doc_id, source_url_key
from src.core.versions import REFERENCE_STANDARD_VERSION
from src.export.privacy import leak_findings

HUMAN_REVIEWED_LABEL = "Human-reviewed reference"
REFERENCE_VERSION = REFERENCE_STANDARD_VERSION
REFERENCE_FILE = "reference.json"
RECORDS_FILE = "records.jsonl"
APPROVAL_FILE = "APPROVAL.md"

#: Columns of the n8n ``insights`` tab, in sheet order. A saved export with a
#: different header is refused rather than guessed at.
N8N_COLUMNS: tuple[str, ...] = (
    "source",
    "url",
    "title",
    "is_retrieval_problem",
    "photo_type",
    "intent",
    "cues_remembered",
    "cues_forgotten",
    "query_tried",
    "failure_stage",
    "workaround",
    "key_quote",
    "summary",
    "scraped_at",
)
N8N_SOURCE_VALUE = "google_photos_community"
RETRIEVAL_PROBLEM = "retrieval_problem"
NOT_RETRIEVAL_PROBLEM = "not_retrieval_problem"
_TRUE = frozenset({"TRUE", "True", "true", "1", "YES", "yes"})
_FALSE = frozenset({"FALSE", "False", "false", "0", "NO", "no", ""})
_UNSTATED_TOKENS = frozenset({"", "unknown", "not_applicable"})
_THREAD_PREFIX = "https://support.google.com/photos/thread/"

#: Fields the n8n export does not carry. They are recorded as unavailable on
#: every record and are never inferred.
UNAVAILABLE_FIELDS: tuple[str, ...] = (
    "original_post_text",
    "author",
    "published_at",
    "quote_offsets",
    "severity",
    "impact_signals",
    "scope_class_core_or_adjacent",
    "reason_code",
    "replies",
    "review_date",
)

#: Documented mapping between the n8n sheet and the application contracts.
#: ``supported`` mappings are applied. ``partial`` mappings apply only to the
#: listed values. ``preserved`` fields keep their n8n name and are shown as
#: n8n dimensions. ``unsupported`` targets are never filled from this data.
FIELD_MAPPINGS: tuple[dict[str, str], ...] = (
    {
        "n8n_field": "source",
        "application_field": "source_platform",
        "status": "supported",
        "rule": "google_photos_community -> google_support; any other value is refused.",
    },
    {
        "n8n_field": "url",
        "application_field": "source_url, source_url_key, source_item_id, expected_doc_id",
        "status": "supported",
        "rule": (
            "Copied exactly. The numeric thread id is the source item id. "
            "expected_doc_id is the existing deterministic doc_id for google_support "
            "and that thread id, so a later collected document can be recognised."
        ),
    },
    {
        "n8n_field": "title",
        "application_field": "title",
        "status": "supported",
        "rule": "Copied exactly. Not treated as the original post body.",
    },
    {
        "n8n_field": "is_retrieval_problem",
        "application_field": "reviewed_relevance",
        "status": "supported",
        "rule": (
            "TRUE -> retrieval_problem, FALSE -> not_retrieval_problem. The n8n schema does "
            "not distinguish core_incomplete_recall from adjacent_known_item_retrieval, so no "
            "scope class or reason code is assigned. Application scope classes collapse onto "
            "this binary in the other direction only: core and adjacent -> retrieval_problem, "
            "out_of_scope -> not_retrieval_problem."
        ),
    },
    {
        "n8n_field": "photo_type",
        "application_field": "target_asset_type",
        "status": "partial",
        "rule": (
            "screenshot -> screenshot only. unknown -> not stated. people_event and other stay "
            "preserved as n8n values because the vocabularies differ."
        ),
    },
    {
        "n8n_field": "intent",
        "application_field": "",
        "status": "preserved",
        "rule": "No application field. Shown as an n8n dimension; unknown -> not stated.",
    },
    {
        "n8n_field": "cues_remembered",
        "application_field": "remembered_cues",
        "status": "unsupported",
        "rule": (
            "Free text split on ';' versus a controlled vocabulary. Preserved as n8n text; the "
            "application vocabulary is not assigned."
        ),
    },
    {
        "n8n_field": "cues_forgotten",
        "application_field": "forgotten_information",
        "status": "unsupported",
        "rule": "Free text versus a controlled vocabulary. Preserved as n8n text.",
    },
    {
        "n8n_field": "query_tried",
        "application_field": "exact_query, query_strategies",
        "status": "unsupported",
        "rule": "Mixed query text and observations. Preserved as n8n text without classification.",
    },
    {
        "n8n_field": "failure_stage",
        "application_field": "",
        "status": "preserved",
        "rule": (
            "expression, understanding, evaluation and refinement are the n8n workflow's stages. "
            "No application field. not_applicable and unknown -> not stated."
        ),
    },
    {
        "n8n_field": "workaround",
        "application_field": "workarounds",
        "status": "unsupported",
        "rule": "Free text versus a controlled vocabulary. Preserved as n8n text.",
    },
    {
        "n8n_field": "key_quote",
        "application_field": "evidence quote",
        "status": "supported",
        "rule": (
            "Kept as the reviewed evidence quote. The export has no original post text and no "
            "offsets, so the quote cannot be verified against source text here."
        ),
    },
    {
        "n8n_field": "summary",
        "application_field": "problem_summary",
        "status": "supported",
        "rule": "Kept as a paraphrase. Never displayed as a quotation.",
    },
    {
        "n8n_field": "scraped_at",
        "application_field": "collected_at",
        "status": "supported",
        "rule": "Copied exactly. This is the workflow's collection time, not the publication time.",
    },
)


class ReviewedReferenceError(ValueError):
    """The saved export cannot become a reference. Nothing is written."""


def read_n8n_export(path: Path) -> list[dict[str, str]]:
    """Read one saved n8n ``insights`` CSV export exactly. No value is altered."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header != N8N_COLUMNS:
            raise ReviewedReferenceError(
                f"unexpected n8n export header {list(header)}; expected {list(N8N_COLUMNS)}"
            )
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ReviewedReferenceError("an n8n export row has a different number of columns")
            rows.append({column: str(row[column]) for column in N8N_COLUMNS})
    return rows


def thread_id_from_url(url: str) -> str:
    text = url.strip()
    if not text.startswith(_THREAD_PREFIX):
        raise ReviewedReferenceError(f"not a Google Photos Community thread URL: {url!r}")
    remainder = text[len(_THREAD_PREFIX):]
    thread = remainder.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not thread.isdigit():
        raise ReviewedReferenceError(f"thread id is not numeric in {url!r}")
    return thread


def record_sha256(fields: dict[str, str]) -> str:
    blob = json.dumps({column: fields[column] for column in N8N_COLUMNS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _unstated(value: str) -> bool:
    return value.strip().lower() in _UNSTATED_TOKENS


def build_record(fields: dict[str, str], ordinal: int, approval_basis: str) -> dict[str, Any]:
    """Map one n8n row onto the supported fields and preserve the rest."""
    if fields["source"] != N8N_SOURCE_VALUE:
        raise ReviewedReferenceError(f"unsupported n8n source value {fields['source']!r}")
    flag = fields["is_retrieval_problem"].strip()
    if flag in _TRUE:
        relevance = RETRIEVAL_PROBLEM
    elif flag in _FALSE:
        relevance = NOT_RETRIEVAL_PROBLEM
    else:
        raise ReviewedReferenceError(f"is_retrieval_problem value {flag!r} is not a boolean")
    thread = thread_id_from_url(fields["url"])
    photo_type = fields["photo_type"].strip().lower()
    if photo_type == "screenshot":
        asset_type, asset_observation = "screenshot", "stated"
    elif _unstated(photo_type):
        asset_type, asset_observation = None, "not_stated"
    else:
        asset_type, asset_observation = None, "unmapped_n8n_value"
    quote = fields["key_quote"]
    title = fields["title"]
    quote_check = {
        "present": bool(quote.strip()),
        "verified_against_original_text": "unavailable",
        "original_text_available": False,
        "offsets_available": False,
        "equals_title": bool(quote.strip()) and quote.strip() == title.strip(),
        "within_title": bool(quote.strip()) and quote.strip() in title,
    }
    return {
        "reference_record_id": f"{REFERENCE_VERSION}#{thread}",
        "ordinal": ordinal,
        "label": HUMAN_REVIEWED_LABEL,
        "thread_id": thread,
        "source_url": fields["url"],
        "source_url_key": source_url_key(fields["url"]),
        "expected_doc_id": doc_id("google_support", source_item_id=thread),
        "n8n_fields": {column: fields[column] for column in N8N_COLUMNS},
        "record_sha256": record_sha256(fields),
        "mapped": {
            "source_platform": "google_support",
            "source_type": "support_thread",
            "title": title,
            "reviewed_relevance": relevance,
            "target_asset_type": asset_type,
            "target_asset_type_observation": asset_observation,
            "evidence_quote": quote if quote.strip() else None,
            "problem_summary": fields["summary"] if fields["summary"].strip() else None,
            "collected_at": fields["scraped_at"],
        },
        "preserved_n8n": {
            "photo_type": fields["photo_type"],
            "intent": fields["intent"],
            "failure_stage": fields["failure_stage"],
            "cues_remembered": split_list(fields["cues_remembered"]),
            "cues_forgotten": split_list(fields["cues_forgotten"]),
            "query_tried": fields["query_tried"],
            "workaround": fields["workaround"],
        },
        "unavailable": list(UNAVAILABLE_FIELDS),
        "quote_check": quote_check,
        "review": {
            "human_reviewed": True,
            "reviewer": "Sunayana",
            "approval_basis": approval_basis,
            "review_date": "not stated by the owner",
            "semantically_approved_by_owner_review": True,
            "model_output": False,
        },
    }


def build_reviewed_reference(
    primary_csv: Path,
    destination: Path,
    *,
    approval: dict[str, Any],
    created_at: datetime,
    expected_count: int = 48,
    cross_check_csv: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write ``reference.json``, ``records.jsonl`` and ``APPROVAL.md`` once.

    ``approval`` must carry the owner's statement and where it was given. The
    actual record count is reported; the artifact is not padded or trimmed to
    ``expected_count``.
    """
    destination = Path(destination)
    if destination.exists():
        raise ReviewedReferenceError("reviewed reference destination must be fresh")
    for key in ("owner", "statement", "given_in", "recorded_on"):
        if not str(approval.get(key) or "").strip():
            raise ReviewedReferenceError(f"approval.{key} is required")
    rows = read_n8n_export(primary_csv)
    basis = f"owner review statement recorded {approval['recorded_on']}"
    records = []
    seen_threads: dict[str, int] = {}
    for ordinal, fields in enumerate(rows, start=1):
        record = build_record(fields, ordinal, basis)
        if record["thread_id"] in seen_threads:
            raise ReviewedReferenceError(
                f"thread {record['thread_id']} appears twice in the saved export (rows "
                f"{seen_threads[record['thread_id']]} and {ordinal})"
            )
        seen_threads[record["thread_id"]] = ordinal
        records.append(record)
    cross_check = _cross_check(rows, cross_check_csv, root)
    inputs = {_label(primary_csv, root): _sha(primary_csv)}
    if cross_check_csv is not None and Path(cross_check_csv).is_file():
        inputs[_label(cross_check_csv, root)] = _sha(cross_check_csv)
    records_blob = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
    metadata = {
        "reference_version": REFERENCE_VERSION,
        "label": HUMAN_REVIEWED_LABEL,
        "created_at": created_at.isoformat(),
        "created_at_note": "Artifact build time. The owner's review date was not stated and is not inferred.",
        "primary_input": _label(primary_csv, root),
        "input_sha256": inputs,
        "records_sha256": hashlib.sha256(records_blob.encode("utf-8")).hexdigest(),
        "records": len(records),
        "distinct_source_urls": len({row["source_url_key"] for row in records}),
        "distinct_thread_ids": len(seen_threads),
        "expected_records": expected_count,
        "count_matches_owner_statement": len(records) == expected_count,
        "count_discrepancy": (
            None if len(records) == expected_count
            else f"saved export has {len(records)} records; the owner's statement names {expected_count}"
        ),
        "record_ids": [row["reference_record_id"] for row in records],
        "cross_check": cross_check,
        "approval": {
            "owner": approval["owner"],
            "statement": approval["statement"],
            "given_in": approval["given_in"],
            "recorded_on": approval["recorded_on"],
            "basis": basis,
            "applies_to": "exactly the records listed in record_ids",
            "extends_to_future_records": False,
            "review_date": "not stated by the owner",
        },
        "fields_reviewed": {
            "named_by_owner": ["relevance", "classifications", "summaries", "evidence quotes"],
            "relevance": ["is_retrieval_problem"],
            "classifications": ["photo_type", "intent", "failure_stage"],
            "summaries": ["summary"],
            "evidence_quotes": ["key_quote"],
            "present_in_record_not_separately_named": [
                "title",
                "cues_remembered",
                "cues_forgotten",
                "query_tried",
                "workaround",
                "scraped_at",
            ],
        },
        "fields_unavailable": list(UNAVAILABLE_FIELDS),
        "field_mappings": [dict(item) for item in FIELD_MAPPINGS],
        "verification": _verification(records),
        "counts": _counts(records),
        "limitations": [
            "The n8n export carries titles, workflow tags, a key quote and a summary. It does not carry the original post text, so no quote is verified against source text here.",
            "The n8n schema records a binary retrieval-problem flag. It does not distinguish core incomplete recall from adjacent known-item retrieval, and no scope class is inferred.",
            "Cues, queries and workarounds are free text and are not mapped onto the application vocabularies.",
            "Severity, impact, offsets, publication dates and authors are unavailable and are not inferred.",
            "The owner's review is the approval basis for these exact records only. It does not approve later records.",
        ],
    }
    findings = leak_findings(records) + leak_findings(metadata)
    if findings:
        raise ReviewedReferenceError("reviewed reference failed the privacy scan:\n" + "\n".join(findings))
    destination.mkdir(parents=True)
    (destination / RECORDS_FILE).write_text(records_blob, encoding="utf-8")
    (destination / REFERENCE_FILE).write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / APPROVAL_FILE).write_text(approval_markdown(metadata), encoding="utf-8")
    return metadata


def approval_markdown(metadata: dict[str, Any]) -> str:
    approval = metadata["approval"]
    lines = [
        f"# {HUMAN_REVIEWED_LABEL}: {metadata['reference_version']}",
        "",
        f"Records covered: {metadata['records']} (owner statement: {metadata['expected_records']}).",
        f"Count matches the owner's statement: {str(metadata['count_matches_owner_statement']).lower()}.",
        "",
        "## Approval basis",
        "",
        f"Owner: {approval['owner']}. Given in: {approval['given_in']}. Recorded on: {approval['recorded_on']}.",
        "",
        "> " + approval["statement"].replace("\n", "\n> "),
        "",
        "The review date itself was not stated and is not recorded. The approval applies to the record ids listed in `reference.json` and does not extend to later records.",
        "",
        "## Fields reviewed",
        "",
    ]
    reviewed = metadata["fields_reviewed"]
    for group in ("relevance", "classifications", "summaries", "evidence_quotes"):
        lines.append(f"- {group}: {', '.join(reviewed[group])}")
    lines.append(
        "- present in each record, not separately named by the owner: "
        + ", ".join(reviewed["present_in_record_not_separately_named"])
    )
    lines.extend(["", "## Unavailable in the saved export", ""])
    lines.extend(f"- {name}" for name in metadata["fields_unavailable"])
    lines.extend(["", "## Inputs", ""])
    lines.extend(f"- `{name}`: sha256 {value}" for name, value in metadata["input_sha256"].items())
    lines.append(f"- records.jsonl: sha256 {metadata['records_sha256']}")
    lines.extend(["", "## Verification", ""])
    for key, value in metadata["verification"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in metadata["limitations"])
    return "\n".join(lines) + "\n"


def load_reviewed_reference(path: Path) -> dict[str, Any]:
    """Load and verify the artifact. A changed byte is reported, not repaired."""
    folder = Path(path)
    reference_path = folder / REFERENCE_FILE
    records_path = folder / RECORDS_FILE
    if not reference_path.is_file() or not records_path.is_file():
        return {"ok": False, "message": "The human-reviewed reference artifact is not present.", "records": [], "metadata": {}}
    try:
        metadata = json.loads(reference_path.read_text(encoding="utf-8"))
        blob = records_path.read_text(encoding="utf-8")
        records = [json.loads(line) for line in blob.splitlines() if line.strip()]
    except (OSError, ValueError):
        return {"ok": False, "message": "The human-reviewed reference artifact could not be read.", "records": [], "metadata": {}}
    problems: list[str] = []
    if hashlib.sha256(blob.encode("utf-8")).hexdigest() != metadata.get("records_sha256"):
        problems.append("records.jsonl does not match the recorded records_sha256")
    if len(records) != metadata.get("records"):
        problems.append("record count differs from reference.json")
    for row in records:
        fields = row.get("n8n_fields") or {}
        if set(fields) != set(N8N_COLUMNS) or record_sha256(fields) != row.get("record_sha256"):
            problems.append(f"record {row.get('reference_record_id')} changed after approval")
    if [row.get("reference_record_id") for row in records] != metadata.get("record_ids"):
        problems.append("record ids differ from reference.json")
    return {
        "ok": not problems,
        "message": "" if not problems else "The human-reviewed reference artifact was modified: " + "; ".join(problems),
        "metadata": metadata,
        "records": records,
        "reference_version": str(metadata.get("reference_version") or ""),
    }


def verify_inputs(metadata: dict[str, Any], root: Path) -> dict[str, str]:
    """Recompute saved-input hashes when the files are present. Reads local files only."""
    result: dict[str, str] = {}
    for name, expected in (metadata.get("input_sha256") or {}).items():
        path = Path(root) / name
        if not path.is_file():
            result[name] = "absent"
        else:
            result[name] = "unchanged" if _sha(path) == expected else "changed"
    return result


def reviewed_reference_comparison(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count the reviewed dimensions the n8n schema supports. Nothing is inferred."""
    positive = [row for row in records if row["mapped"]["reviewed_relevance"] == RETRIEVAL_PROBLEM]
    dimensions = [
        _dimension(
            "reviewed_relevance",
            "Reviewed relevance (is_retrieval_problem)",
            "supported",
            records,
            lambda row: [row["mapped"]["reviewed_relevance"]],
            "Binary flag. Core and adjacent are not distinguished by the n8n schema.",
        ),
        _dimension(
            "failure_stage",
            "Failure stage (n8n dimension, retrieval-problem records)",
            "preserved",
            positive,
            lambda row: [] if _unstated(row["preserved_n8n"]["failure_stage"]) else [row["preserved_n8n"]["failure_stage"].strip().lower()],
            "n8n workflow stages. No application field.",
        ),
        _dimension(
            "photo_type",
            "Photo type (n8n dimension, retrieval-problem records)",
            "partial",
            positive,
            lambda row: [] if _unstated(row["preserved_n8n"]["photo_type"]) else [row["preserved_n8n"]["photo_type"].strip().lower()],
            "Only screenshot maps onto target_asset_type.",
        ),
        _dimension(
            "intent",
            "Intent (n8n dimension, retrieval-problem records)",
            "preserved",
            positive,
            lambda row: [] if _unstated(row["preserved_n8n"]["intent"]) else [row["preserved_n8n"]["intent"].strip().lower()],
            "No application field.",
        ),
        _dimension(
            "cues_remembered",
            "Cues remembered (n8n free text, retrieval-problem records)",
            "unsupported",
            positive,
            lambda row: [item.lower() for item in row["preserved_n8n"]["cues_remembered"] if not _unstated(item)],
            "Free text, not the remembered_cues vocabulary.",
        ),
        _dimension(
            "cues_forgotten",
            "Cues forgotten (n8n free text, retrieval-problem records)",
            "unsupported",
            positive,
            lambda row: [item.lower() for item in row["preserved_n8n"]["cues_forgotten"] if not _unstated(item)],
            "Free text, not the forgotten_information vocabulary.",
        ),
        _dimension(
            "target_asset_type",
            "Target item (application field, mapped from photo_type = screenshot only)",
            "partial",
            positive,
            lambda row: [row["mapped"]["target_asset_type"]] if row["mapped"]["target_asset_type"] else [],
            "Mapped value only. Other photo types stay under the n8n dimension.",
        ),
    ]
    return {
        "label": HUMAN_REVIEWED_LABEL,
        "records": len(records),
        "retrieval_problem_records": len(positive),
        "not_retrieval_problem_records": len(records) - len(positive),
        "dimensions": dimensions,
        "evidence": {
            "records_with_quote": sum(1 for row in records if row["quote_check"]["present"]),
            "records_without_quote": sum(1 for row in records if not row["quote_check"]["present"]),
            "quotes_verified_against_original_text": 0,
            "quote_verification_unavailable": len(records),
        },
    }


def _dimension(field: str, label: str, status: str, rows: list[dict[str, Any]], values: Any, limitation: str) -> dict[str, Any]:
    from collections import Counter

    counter: Counter[str] = Counter()
    links: dict[str, list[str]] = {}
    unstated: list[str] = []
    for row in rows:
        found = [value for value in values(row) if value]
        if not found:
            unstated.append(row["thread_id"])
            continue
        for value in sorted(set(found)):
            counter[value] += 1
            links.setdefault(value, []).append(row["thread_id"])
    return {
        "field": field,
        "label": label,
        "mapping_status": status,
        "rows": [{"value": value, "count": count, "records": links[value]} for value, count in counter.most_common()],
        "unstated_records": unstated,
        "limitation": limitation,
    }


def _verification(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "records_with_quote": sum(1 for row in records if row["quote_check"]["present"]),
        "records_without_quote": sum(1 for row in records if not row["quote_check"]["present"]),
        "quotes_verified_against_original_text": 0,
        "quote_verification_unavailable": len(records),
        "quotes_equal_to_saved_title": sum(1 for row in records if row["quote_check"]["equals_title"]),
        "quotes_within_saved_title": sum(1 for row in records if row["quote_check"]["within_title"]),
        "records_with_summary": sum(1 for row in records if row["mapped"]["problem_summary"]),
        "records_without_summary": sum(1 for row in records if not row["mapped"]["problem_summary"]),
        "note": (
            "Title containment is a weak consistency check on saved sheet text. It is not "
            "verification against the original post, which the export does not include."
        ),
    }


def _counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [row for row in records if row["mapped"]["reviewed_relevance"] == RETRIEVAL_PROBLEM]
    return {
        RETRIEVAL_PROBLEM: len(positive),
        NOT_RETRIEVAL_PROBLEM: len(records) - len(positive),
        "target_asset_type_screenshot": sum(1 for row in records if row["mapped"]["target_asset_type"] == "screenshot"),
        "photo_type_unmapped": sum(
            1 for row in records if row["mapped"]["target_asset_type_observation"] == "unmapped_n8n_value"
        ),
    }


def _cross_check(rows: list[dict[str, str]], cross_check_csv: Path | None, root: Path | None) -> dict[str, Any]:
    if cross_check_csv is None or not Path(cross_check_csv).is_file():
        return {"performed": False, "reason": "no cross-check snapshot supplied or present"}
    other = {thread_id_from_url(row["url"]): row for row in read_n8n_export(cross_check_csv)}
    primary = {thread_id_from_url(row["url"]): row for row in rows}
    differences: dict[str, dict[str, int]] = {}
    for thread, fields in primary.items():
        match = other.get(thread)
        if match is None:
            continue
        for column in N8N_COLUMNS:
            if fields[column] == match[column]:
                continue
            kind = (
                "boolean_case_only"
                if column == "is_retrieval_problem" and fields[column].upper() == match[column].upper()
                else "value_differs"
            )
            bucket = differences.setdefault(column, {})
            bucket[kind] = bucket.get(kind, 0) + 1
    return {
        "performed": True,
        "snapshot": _label(cross_check_csv, root),
        "snapshot_rows": len(other),
        "covered_rows_present_in_snapshot": sum(1 for thread in primary if thread in other),
        "covered_rows_missing_from_snapshot": sorted(thread for thread in primary if thread not in other),
        "snapshot_rows_not_covered_by_review": sorted(thread for thread in other if thread not in primary),
        "field_differences_for_covered_rows": differences,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _label(path: Path, root: Path | None) -> str:
    path = Path(path)
    if root is not None:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            pass
    return path.name
