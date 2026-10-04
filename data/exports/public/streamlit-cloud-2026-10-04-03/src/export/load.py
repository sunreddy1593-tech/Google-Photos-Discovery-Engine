"""Read prepared submission exports. This module does not open research artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.export import PublicExportRecord

RECORD_ALL = "All records"
RECORD_CASES = "Extraction cases"
RECORD_ATTEMPTS = "Failed or empty attempts"
RECORD_RELEVANCE = "Relevance decisions"
FILTER_ALL = "All"


def load_submission(path: Path) -> dict[str, Any]:
    """Load ``index.json`` and each dataset folder. Missing exports are an empty state."""
    index_path = path / "index.json"
    if not index_path.is_file():
        return {
            "ok": False,
            "message": "Prepared export is missing. Build it before opening this app.",
        }
    index = json.loads(index_path.read_text(encoding="utf-8"))
    datasets: dict[str, dict[str, Any]] = {}
    for item in index.get("datasets") or []:
        dataset_id = str(item.get("dataset_id") or "")
        folder = path / dataset_id
        summary_path = folder / "summary.json"
        if not dataset_id or not summary_path.is_file():
            return {
                "ok": False,
                "message": f"Prepared summary is missing for {dataset_id or 'a dataset'}.",
            }
        datasets[dataset_id] = _load_dataset(folder)
    if not datasets:
        return {"ok": False, "message": "Prepared export lists no datasets."}
    return {"ok": True, "index": index, "datasets": datasets}


def browser_cards(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """One card per case, failed or empty attempt, and relevance decision."""
    reviews = {row.get("case_id"): row for row in dataset["case_reviews"]}
    cards: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        review = reviews.get(case.get("case_id"), {})
        fields = case.get("extracted_fields") or {}
        cards.append(
            {
                "kind": "case",
                "record_label": RECORD_CASES,
                "doc_id": case.get("doc_id") or "",
                "case_id": case.get("case_id"),
                "source_platform": case.get("source_platform") or "",
                "source_name": case.get("source_name") or "",
                "source_url": case.get("source_url") or "",
                "model_scope_class": fields.get("model_scope_class") or review.get("model_scope_class") or "",
                "model_relevance_scope": review.get("model_relevance_scope") or "",
                "human_relevance_label": fields.get("human_relevance_label") or "",
                "human_reason_code": fields.get("human_reason_code") or "",
                "review_status": review.get("review_status") or "",
                "automatically_valid": bool(review.get("automatically_valid")),
                "semantically_approved": bool(review.get("semantically_approved")),
                "enters_conclusions": bool(review.get("enters_conclusions")),
                "excerpt": case.get("excerpt") or "",
                "excerpt_start_char": case.get("excerpt_start_char") or 0,
                "excerpt_kind": "validated_span_window",
                "evidence_spans": list(case.get("evidence_spans") or []),
                "span_support": list(review.get("span_support") or []),
                "assigned_values": (fields.get("assigned_values") or {}),
                "problem_summary": fields.get("problem_summary") or "",
                "reason_summary": "",
                "rejected_model_text": [],
                "diagnostic": {},
                "findings": list(review.get("findings") or []),
            }
        )
    for attempt in dataset["attempts"]:
        cards.append(
            {
                "kind": "attempt",
                "record_label": RECORD_ATTEMPTS,
                "doc_id": attempt.get("doc_id") or "",
                "case_id": attempt.get("case_id"),
                "source_platform": attempt.get("source_platform") or "",
                "source_name": attempt.get("source_name") or "",
                "source_url": attempt.get("source_url") or "",
                "model_scope_class": attempt.get("model_scope_class") or "",
                "model_relevance_scope": attempt.get("model_relevance_scope") or "",
                "human_relevance_label": attempt.get("human_relevance_label") or "",
                "human_reason_code": attempt.get("human_reason_code") or "",
                "review_status": attempt.get("review_status") or attempt.get("kind") or "",
                "automatically_valid": False,
                "semantically_approved": False,
                "enters_conclusions": False,
                "excerpt": attempt.get("excerpt") or "",
                "excerpt_start_char": attempt.get("excerpt_start_char") or 0,
                "excerpt_kind": attempt.get("excerpt_kind") or "",
                "evidence_spans": list(attempt.get("evidence_spans") or []),
                "span_support": list(attempt.get("span_support") or []),
                "assigned_values": attempt.get("assigned_values") or {},
                "problem_summary": attempt.get("problem_summary") or "",
                "reason_summary": "",
                "rejected_model_text": list(attempt.get("rejected_model_text") or []),
                "diagnostic": attempt.get("diagnostic") or {},
                "findings": list(attempt.get("findings") or []),
                "attempt_kind": attempt.get("kind") or "",
            }
        )
    for row in dataset["relevance"]:
        cards.append(
            {
                "kind": "relevance",
                "record_label": RECORD_RELEVANCE,
                "doc_id": row.get("doc_id") or "",
                "case_id": None,
                "source_platform": row.get("source_platform") or "",
                "source_name": row.get("source_name") or "",
                "source_url": row.get("source_url") or "",
                "model_scope_class": row.get("model_scope_class") or "",
                "model_relevance_scope": row.get("model_scope_class") or "",
                "human_relevance_label": row.get("human_relevance_label") or "",
                "human_reason_code": row.get("human_reason_code") or "",
                "review_status": row.get("review_status") or "relevance decision only",
                "automatically_valid": bool(row.get("automatically_valid")),
                "semantically_approved": False,
                "enters_conclusions": False,
                "excerpt": row.get("excerpt") or "",
                "excerpt_start_char": row.get("excerpt_start_char") or 0,
                "excerpt_kind": row.get("excerpt_kind") or "",
                "evidence_spans": list(row.get("evidence_spans") or []),
                "span_support": list(row.get("span_support") or []),
                "assigned_values": {},
                "problem_summary": "",
                "reason_summary": row.get("reason_summary") or "",
                "reason_code": row.get("reason_code") or "",
                "rejected_model_text": [],
                "diagnostic": {},
                "findings": list(row.get("findings") or []),
            }
        )
    return cards


def filter_cards(
    cards: list[dict[str, Any]],
    *,
    source: str = FILTER_ALL,
    model_scope: str = FILTER_ALL,
    human_label: str = FILTER_ALL,
    review_status: str = FILTER_ALL,
    record: str = RECORD_ALL,
) -> list[dict[str, Any]]:
    """Apply the evidence-browser filters. ``All`` leaves that dimension unchanged."""
    kept: list[dict[str, Any]] = []
    for card in cards:
        if source != FILTER_ALL and card.get("source_platform") != source:
            continue
        if model_scope != FILTER_ALL and card.get("model_scope_class") != model_scope:
            continue
        if human_label != FILTER_ALL and card.get("human_relevance_label") != human_label:
            continue
        if review_status != FILTER_ALL and card.get("review_status") != review_status:
            continue
        if record != RECORD_ALL and card.get("record_label") != record:
            continue
        kept.append(card)
    return kept


def _load_dataset(folder: Path) -> dict[str, Any]:
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    cases = []
    for line in _lines(folder / "cases.jsonl"):
        record = PublicExportRecord.model_validate(line)
        cases.append(record.model_dump(mode="json"))
    return {
        "summary": summary,
        "cases": cases,
        "case_reviews": _lines(folder / "case_reviews.jsonl"),
        "attempts": _lines(folder / "attempts.jsonl"),
        "relevance": _lines(folder / "relevance.jsonl"),
        "corrections": _lines(folder / "corrections.jsonl"),
    }


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows
