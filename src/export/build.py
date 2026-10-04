"""Build prepared exports from an explicit dataset manifest.

This module reads saved research artifacts. The Streamlit app does not import
it. Holdout document text is discarded as soon as the document id is known.
Original artifacts are not modified.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from src.browse.findings import RECORDED_FINDINGS, SemanticFinding
from src.export.privacy import leak_findings
from src.models.base import ResearchModel
from src.models.enums import EvidenceTier, SourcePlatform, SourceType
from src.models.export import ExportedEvidenceSpan, PublicExportRecord
from src.normalize.privacy import redact

CONTEXT = 160
EXCERPT_CAP = 480
AUTHOR_KEY_LENGTH = 12
CONFIRMED = frozenset({"auto_confirmed", "human_confirmed"})
OUT_OF_SCOPE = "out_of_scope"
DEVELOPMENT = "development"
HOLDOUT = "holdout"

_VALUE_FIELDS = (
    "target_asset_type",
    "retrieval_trigger",
    "exact_query",
    "outcome",
    "severity",
    "known_item_status",
)
_LABEL_FIELDS = (
    "remembered_cues",
    "forgotten_information",
    "query_strategies",
    "system_responses",
    "workarounds",
    "impact_signals",
    "target_subjects",
)
_DIAGNOSTIC_KEYS = (
    "category",
    "error_code",
    "http_status",
    "provider_error_type",
    "sdk_exception_class",
)
_SUMMARY_KEYS = (
    "application_state",
    "character_count",
    "json_error_position",
    "json_state",
)


class ExtractionRunSpec(ResearchModel):
    run_id: str = Field(min_length=1)
    path: str = Field(min_length=1)


class DatasetSpec(ResearchModel):
    dataset_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    split_policy: Literal["development_only", "outside_frozen_split"]
    collected: str = Field(min_length=1)
    derived: str = Field(min_length=1)
    links: str = Field(min_length=1)
    labels: str | None = None
    relevance: str | None = None
    reviews: tuple[str, ...] = ()
    corrections: str | None = None
    extraction_run: ExtractionRunSpec
    limitations: tuple[str, ...] = ()


class SubmissionManifest(ResearchModel):
    submission_id: str = Field(min_length=1)
    frozen_split: str = Field(min_length=1)
    datasets: tuple[DatasetSpec, ...] = Field(min_length=1)
    not_combined: tuple[str, ...] = ()


def build_submission(
    manifest_path: Path,
    destination: Path,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write one folder per dataset plus ``index.json``. Return the index.

    Relative manifest paths resolve from ``root``, which defaults to the
    current working directory. They do not resolve from the manifest file's
    own folder.
    """
    manifest = SubmissionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    root = root or Path.cwd()
    destination.mkdir(parents=True, exist_ok=True)
    development, holdout = _split_ids(_resolve(root, manifest.frozen_split))
    datasets: list[dict[str, Any]] = []
    for spec in manifest.datasets:
        payload = _build_dataset(spec, root, development, holdout)
        folder = destination / spec.dataset_id
        folder.mkdir(parents=True, exist_ok=True)
        _write_dataset(folder, payload)
        datasets.append(
            {
                "dataset_id": spec.dataset_id,
                "description": spec.description,
                "run_id": spec.extraction_run.run_id,
                "split_policy": spec.split_policy,
                "limitations": list(spec.limitations),
            }
        )
    index = {
        "submission_id": manifest.submission_id,
        "datasets": datasets,
        "not_combined": list(manifest.not_combined),
        "semantic_risks": [
            "retrieval_trigger must be the stated reason the item was needed, not the search method",
            "impact and severity need a quote that states that impact or severity",
            "problem_summary evidence must support every factual clause",
            "quotes must be one continuous span; invented, abbreviated, or spliced text is invalid",
        ],
    }
    findings = leak_findings(index)
    if findings:
        raise RuntimeError("prepared index failed the privacy scan:\n" + "\n".join(findings))
    (destination / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index


def _build_dataset(
    spec: DatasetSpec,
    root: Path,
    development: set[str],
    holdout: set[str],
) -> dict[str, Any]:
    missing: list[str] = []
    documents, withheld, overlap = _documents(
        _resolve(root, spec.collected),
        spec.split_policy,
        development,
        holdout,
        missing,
    )
    allowed = set(documents)
    derived = _derived(_resolve(root, spec.derived), allowed, holdout, missing)
    for doc_id, document in documents.items():
        meta = derived.get(doc_id, {})
        if meta.get("canonical_url"):
            document["canonical_url"] = meta["canonical_url"]
        if meta.get("normalizer_version"):
            document["normalizer_version"] = meta["normalizer_version"]
    audits = {doc_id: meta.get("audit", "") for doc_id, meta in derived.items()}
    links = _links(_resolve(root, spec.links), allowed, missing)
    labels = _labels(_resolve(root, spec.labels) if spec.labels else None, allowed, holdout, missing)
    relevance = _relevance(
        _resolve(root, spec.relevance) if spec.relevance else None,
        allowed,
        missing,
    )
    aliases = {
        str(row.get("decision_id")): str(row.get("doc_id"))
        for row in relevance
        if row.get("decision_id") and row.get("doc_id")
    }
    reviews = _reviews(
        [_resolve(root, path) for path in spec.reviews],
        allowed,
        missing,
        aliases,
    )
    corrections = _corrections(
        _resolve(root, spec.corrections) if spec.corrections else None,
        missing,
    )
    run = _resolve(root, spec.extraction_run.path)
    inputs = _rows(run / "extraction_inputs.jsonl", allowed, holdout, missing)
    failures = _rows(run / "extraction_failures.jsonl", allowed, holdout, missing)
    candidates = _rows(run / "extraction_candidates.jsonl", allowed, holdout, missing)
    cases = _rows(run / "retrieval_cases.jsonl", allowed, holdout, missing)
    spans_by_case = _valid_spans_by_case(run / "evidence_spans.jsonl", allowed, holdout)
    approved = {
        row["case_id"]
        for row in corrections
        if row.get("field") == "semantic_approval" and row.get("case_id")
    }
    canonical = _canonical(links)
    failure_by_doc = {str(row.get("doc_id")): row for row in failures}
    candidate_by_doc = {str(row.get("doc_id")): row for row in candidates}
    case_ids_by_doc: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        case_ids_by_doc.setdefault(str(case.get("doc_id")), []).append(case)

    public_cases: list[dict[str, Any]] = []
    case_reviews: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for case in cases:
        case = _with_external_spans(case, spans_by_case.get(str(case.get("case_id")), []))
        built = _public_case(
            case,
            documents.get(str(case.get("doc_id")), {}),
            audits.get(str(case.get("doc_id")), ""),
            labels.get(str(case.get("doc_id")), {}),
            reviews,
            approved,
            spec,
        )
        if built is None:
            attempts.append(
                _attempt(
                    str(case.get("doc_id")),
                    documents.get(str(case.get("doc_id")), {}),
                    audits.get(str(case.get("doc_id")), ""),
                    labels.get(str(case.get("doc_id")), {}),
                    {"technical_state": "stored_case_without_matching_span", "doc_id": case.get("doc_id")},
                    case,
                    None,
                    reviews,
                    spec,
                    kind="stored_case_without_matching_span",
                )
            )
            continue
        public_cases.append(built[0])
        case_reviews.append(built[1])

    input_docs = {str(row.get("doc_id")) for row in inputs}
    for row in inputs:
        doc_id = str(row.get("doc_id"))
        state = str(row.get("technical_state") or "")
        if case_ids_by_doc.get(doc_id) and state == "ok":
            continue
        kind = "empty_response" if state == "ok" else "failed"
        attempts.append(
            _attempt(
                doc_id,
                documents.get(doc_id, {}),
                audits.get(doc_id, ""),
                labels.get(doc_id, {}),
                row,
                candidate_by_doc.get(doc_id),
                failure_by_doc.get(doc_id),
                reviews,
                spec,
                kind=kind,
            )
        )

    relevance_cards = [
        _relevance_card(
            row,
            documents.get(str(row.get("doc_id")), {}),
            audits.get(str(row.get("doc_id")), ""),
            labels.get(str(row.get("doc_id")), {}),
            spec,
        )
        for row in relevance
    ]
    for row in relevance:
        doc_id = str(row.get("doc_id"))
        if doc_id in input_docs or doc_id in case_ids_by_doc:
            _attach_relevance(doc_id, row, case_reviews, attempts)

    for attempt in attempts:
        if attempt.get("case_id") in approved:
            attempt["semantically_approved"] = True
            attempt["review_status"] = "semantically approved; no exported span window"
    summary = _summary(
        spec,
        documents,
        withheld,
        overlap,
        labels,
        relevance,
        reviews,
        inputs,
        cases,
        public_cases,
        case_reviews,
        attempts,
        canonical,
        links,
        missing,
        corrections,
    )
    payload = {
        "summary": summary,
        "cases": public_cases,
        "case_reviews": case_reviews,
        "attempts": attempts,
        "relevance": relevance_cards,
        "corrections": corrections,
    }
    findings = leak_findings(payload)
    if findings:
        raise RuntimeError(
            f"{spec.dataset_id} failed the privacy scan:\n" + "\n".join(findings)
        )
    return payload


def _public_case(
    case: dict[str, Any],
    document: dict[str, str],
    audit: str,
    label: dict[str, str],
    reviews: list[dict[str, Any]],
    approved: set[str],
    spec: DatasetSpec,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if str(case.get("validation_state")) != "valid":
        return None
    doc_id = str(case.get("doc_id") or "")
    case_id = str(case.get("case_id") or "")
    findings = _findings_for(doc_id, case_id)
    located = _matching_spans(audit, case.get("all_evidence_spans") or [])
    if not document or not audit or not located:
        return None
    excerpt, origin, spans = _window(audit, located)
    if not spans:
        return None
    support = [_span_support({"field_name": span.field_name}, findings) for span in spans]
    record = PublicExportRecord(
        case_id=case_id,
        doc_id=doc_id,
        source_platform=SourcePlatform(document["source_platform"]),
        source_type=SourceType(document["source_type"]),
        evidence_tier=EvidenceTier(document["evidence_tier"]),
        source_name=document["source_name"],
        source_url=document["source_url"],
        canonical_url=document.get("canonical_url") or document["source_url"],
        published_at=document.get("published_at") or None,
        collected_at=document.get("collected_at") or None,
        author_key=document.get("author_key") or None,
        excerpt=excerpt,
        excerpt_start_char=origin,
        excerpt_is_full_text=False,
        evidence_spans=tuple(spans),
        extracted_fields={
            "assigned_values": _assigned(case),
            "problem_summary": case.get("problem_summary") or "",
            "human_relevance_label": label.get("human_scope_class") or "",
            "human_reason_code": label.get("human_reason_code") or "",
            "model_scope_class": str(case.get("scope_class") or ""),
            "automatically_valid": True,
            "semantically_approved": case_id in approved and not findings,
            "approval_note": (
                "A human relevance label is not extraction approval. "
                "Semantic approval requires a recorded correction and no open finding."
            ),
        },
        prompt_version=str(case.get("prompt_version") or "") or None,
        normalizer_version=document.get("normalizer_version") or None,
        dataset_version=f"{spec.dataset_id}/{spec.extraction_run.run_id}",
    )
    review = {
        "case_id": case_id,
        "doc_id": doc_id,
        "automatically_valid": True,
        "semantically_approved": record.extracted_fields["semantically_approved"],
        "human_relevance_label": label.get("human_scope_class") or "",
        "human_reason_code": label.get("human_reason_code") or "",
        "model_scope_class": str(case.get("scope_class") or ""),
        "model_relevance_scope": "",
        "review_status": _status(True, case_id in approved and not findings, findings, reviews, doc_id, case_id),
        "findings": [_finding_dict(item) for item in findings],
        "span_support": support,
        "enters_conclusions": bool(record.extracted_fields["semantically_approved"]),
    }
    return record.model_dump(mode="json"), review


def _attempt(
    doc_id: str,
    document: dict[str, str],
    audit: str,
    label: dict[str, str],
    extraction_input: dict[str, Any],
    candidate: dict[str, Any] | None,
    failure: dict[str, Any] | None,
    reviews: list[dict[str, Any]],
    spec: DatasetSpec,
    *,
    kind: str,
) -> dict[str, Any]:
    findings = _findings_for(doc_id, str((candidate or {}).get("case_id") or "") or None)
    candidate_case = (candidate or {}).get("case") if isinstance((candidate or {}).get("case"), dict) else {}
    transport = (candidate or {}).get("candidate") if isinstance((candidate or {}).get("candidate"), dict) else {}
    matched, rejected = _split_candidate_spans(audit, candidate_case.get("all_evidence_spans") or [])
    rejected = _merge_quotes(
        rejected,
        _noncontinuous_quotes(audit, transport.get("field_evidence")),
        _noncontinuous_quotes(audit, transport.get("severity_evidence")),
    )
    excerpt, origin, spans = ("", 0, [])
    if audit and matched:
        excerpt, origin, spans = _window(audit, matched)
    if audit and not spans:
        excerpt = audit[:EXCERPT_CAP]
        origin = 0
    case_id = str((candidate or {}).get("case_id") or "") or None
    return {
        "dataset_id": spec.dataset_id,
        "run_id": spec.extraction_run.run_id,
        "kind": kind,
        "doc_id": doc_id,
        "case_id": case_id,
        "technical_state": str(extraction_input.get("technical_state") or ""),
        "source_platform": document.get("source_platform", ""),
        "source_type": document.get("source_type", ""),
        "source_name": document.get("source_name", ""),
        "source_url": document.get("source_url", ""),
        "author_key": document.get("author_key") or None,
        "excerpt": excerpt,
        "excerpt_start_char": origin,
        "excerpt_is_full_text": False,
        "excerpt_kind": "validated_span_window" if spans else "capped_audit_not_a_validated_window",
        "evidence_spans": [span.model_dump(mode="json") for span in spans],
        "span_support": [_span_support({"field_name": span.field_name}, findings) for span in spans],
        "human_relevance_label": label.get("human_scope_class") or "",
        "human_reason_code": label.get("human_reason_code") or "",
        "model_scope_class": str(extraction_input.get("scope_class") or ""),
        "model_relevance_scope": "",
        "assigned_values": _assigned(candidate_case) if candidate_case else {},
        "problem_summary": str(candidate_case.get("problem_summary") or "") if candidate_case else "",
        "rejected_model_text": rejected,
        "diagnostic": _diagnostic(failure),
        "findings": [_finding_dict(item) for item in findings],
        "review_status": _status(False, False, findings, reviews, doc_id, case_id) or kind.replace("_", " "),
        "automatically_valid": False,
        "semantically_approved": False,
        "enters_conclusions": False,
    }


def _relevance_card(
    row: dict[str, Any],
    document: dict[str, str],
    audit: str,
    label: dict[str, str],
    spec: DatasetSpec,
) -> dict[str, Any]:
    doc_id = str(row.get("doc_id") or "")
    findings = _findings_for(doc_id, None)
    matched, _rejected = _split_candidate_spans(audit, row.get("evidence") or [])
    # Relevance evidence that fails the offset check is omitted rather than quoted.
    excerpt, origin, spans = ("", 0, [])
    if audit and matched:
        excerpt, origin, spans = _window(audit, matched)
    if audit and not spans:
        excerpt = audit[:EXCERPT_CAP]
        origin = 0
    return {
        "dataset_id": spec.dataset_id,
        "run_id": spec.extraction_run.run_id,
        "kind": "relevance",
        "doc_id": doc_id,
        "source_platform": document.get("source_platform", ""),
        "source_name": document.get("source_name", ""),
        "source_url": document.get("source_url", ""),
        "author_key": document.get("author_key") or None,
        "excerpt": excerpt,
        "excerpt_start_char": origin,
        "excerpt_is_full_text": False,
        "excerpt_kind": "validated_span_window" if spans else "capped_audit_not_a_validated_window",
        "evidence_spans": [span.model_dump(mode="json") for span in spans],
        "span_support": [_span_support({"field_name": span.field_name}, findings) for span in spans],
        "human_relevance_label": label.get("human_scope_class") or "",
        "human_reason_code": label.get("human_reason_code") or "",
        "model_scope_class": str(row.get("scope_class") or ""),
        "reason_code": str(row.get("reason_code") or ""),
        "reason_summary": str(row.get("reason_summary") or ""),
        "validation_state": str(row.get("validation_state") or ""),
        "technical_state": str(row.get("technical_state") or ""),
        "needs_human_review": bool(row.get("needs_human_review")),
        "findings": [_finding_dict(item) for item in findings],
        "automatically_valid": str(row.get("validation_state")) == "valid",
        "semantically_approved": False,
        "enters_conclusions": False,
        "review_status": "relevance decision only",
    }


def _attach_relevance(
    doc_id: str,
    row: dict[str, Any],
    case_reviews: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> None:
    scope = str(row.get("scope_class") or "")
    for review in case_reviews:
        if review.get("doc_id") == doc_id and not review.get("model_relevance_scope"):
            review["model_relevance_scope"] = scope
    for attempt in attempts:
        if attempt.get("doc_id") == doc_id and not attempt.get("model_relevance_scope"):
            attempt["model_relevance_scope"] = scope


def _summary(
    spec: DatasetSpec,
    documents: dict[str, dict[str, str]],
    withheld: int,
    overlap: int,
    labels: dict[str, dict[str, str]],
    relevance: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    public_cases: list[dict[str, Any]],
    case_reviews: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    canonical: dict[str, str],
    links: list[dict[str, Any]],
    missing: list[str],
    corrections: list[dict[str, Any]],
) -> dict[str, Any]:
    doc_ids = list(documents)
    analysis = {canonical.get(doc_id, doc_id) for doc_id in doc_ids}
    by_state: dict[str, int] = {}
    for row in inputs:
        state = str(row.get("technical_state") or "missing")
        by_state[state] = by_state.get(state, 0) + 1
    relevance_scope: dict[str, int] = {}
    for row in relevance:
        if str(row.get("technical_state")) != "ok":
            continue
        scope = str(row.get("scope_class") or "missing")
        relevance_scope[scope] = relevance_scope.get(scope, 0) + 1
    human_out = sum(1 for row in labels.values() if row.get("human_scope_class") == OUT_OF_SCOPE)
    model_out = relevance_scope.get(OUT_OF_SCOPE, 0)
    valid_cases = sum(1 for row in case_reviews if row.get("automatically_valid"))
    approved_cases = len({
        str(row.get("case_id"))
        for row in (*case_reviews, *attempts)
        if row.get("semantically_approved") and row.get("case_id")
    })
    failed = sum(1 for row in attempts if row.get("kind") == "failed")
    empty = sum(1 for row in attempts if row.get("kind") == "empty_response")
    open_reviews = [row for row in reviews if row.get("state") == "open"]
    finding_count = sum(len(row.get("findings") or []) for row in case_reviews)
    finding_count += sum(len(row.get("findings") or []) for row in attempts)
    return {
        "dataset_id": spec.dataset_id,
        "run_id": spec.extraction_run.run_id,
        "description": spec.description,
        "split_policy": spec.split_policy,
        "documents": len(doc_ids),
        "withheld_evaluation_documents": withheld,
        "frozen_split_overlap_excluded": overlap,
        "analysis_documents": len(analysis),
        "confirmed_duplicate_links": sum(1 for row in links if row.get("review_state") in CONFIRMED),
        "pending_duplicate_links": sum(1 for row in links if row.get("review_state") == "pending_review"),
        "human_relevance_labels": len(labels),
        "human_labeled_out_of_scope": human_out,
        "model_relevance_attempts": len(relevance),
        "model_relevance_out_of_scope": model_out,
        "model_relevance_by_scope": relevance_scope,
        "extraction_attempts": len(inputs),
        "extraction_by_state": by_state,
        "stored_cases": len(cases),
        "exported_cases": len(public_cases),
        "automatically_valid_cases": valid_cases,
        "semantically_approved_cases": approved_cases,
        "failed_attempts": failed,
        "empty_responses": empty,
        "unresolved_review_items": len(open_reviews),
        "recorded_semantic_findings": finding_count,
        "corrections": len(corrections),
        "missing_inputs": missing,
        "limitations": list(spec.limitations),
        "counts_are_this_dataset_only": True,
    }


def _write_dataset(folder: Path, payload: dict[str, Any]) -> None:
    (folder / "summary.json").write_text(
        json.dumps(payload["summary"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(folder / "cases.jsonl", payload["cases"])
    _write_jsonl(folder / "case_reviews.jsonl", payload["case_reviews"])
    _write_jsonl(folder / "attempts.jsonl", payload["attempts"])
    _write_jsonl(folder / "relevance.jsonl", payload["relevance"])
    _write_jsonl(folder / "corrections.jsonl", payload["corrections"])


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _documents(
    path: Path,
    policy: str,
    development: set[str],
    holdout: set[str],
    missing: list[str],
) -> tuple[dict[str, dict[str, str]], int, int]:
    if not path.is_file():
        missing.append(path.name)
        return {}, 0, 0
    kept: dict[str, dict[str, str]] = {}
    withheld = 0
    overlap = 0
    for row in _jsonl(path):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id or doc_id in holdout:
            if doc_id in holdout:
                withheld += 1
            continue
        in_development = doc_id in development
        if policy == "development_only" and not in_development:
            continue
        if policy == "outside_frozen_split" and (in_development or doc_id in holdout):
            overlap += 1
            continue
        kept[doc_id] = _metadata(row)
    return kept, withheld, overlap


def _metadata(row: dict[str, Any]) -> dict[str, str]:
    author = row.get("author_hash")
    author_key = author[:AUTHOR_KEY_LENGTH] if isinstance(author, str) and author else ""
    return {
        "source_platform": str(row.get("source_platform") or ""),
        "source_type": str(row.get("source_type") or ""),
        "evidence_tier": str(row.get("evidence_tier") or ""),
        "source_name": _mask_export_text(str(row.get("source_name") or "")),
        "source_url": str(row.get("source_url") or ""),
        "published_at": str(row.get("published_at") or ""),
        "collected_at": str(row.get("collected_at") or ""),
        "author_key": author_key,
    }


def _derived(
    path: Path,
    allowed: set[str],
    holdout: set[str],
    missing: list[str],
) -> dict[str, dict[str, str]]:
    if not path.is_file():
        missing.append(path.name)
        return {}
    kept: dict[str, dict[str, str]] = {}
    for row in _jsonl(path):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id or doc_id in holdout or doc_id not in allowed:
            continue
        audit = row.get("raw_text_audit")
        kept[doc_id] = {
            "audit": audit if isinstance(audit, str) else "",
            "canonical_url": str(row.get("canonical_url") or ""),
            "normalizer_version": str(row.get("normalizer_version") or ""),
        }
    return kept


def _matching_spans(audit: str, spans: object) -> list[dict[str, Any]]:
    matched, _rejected = _split_candidate_spans(audit, spans)
    return matched


def _noncontinuous_quotes(audit: str, items: object) -> list[str]:
    """Quotes the model attached that are not one continuous source substring.

    Scalar evidence, including ``problem_summary``, is stored on the transport
    candidate. A rejected splice often never lands on ``all_evidence_spans``.
    A verbatim quote with unresolved offsets stays out of this list: the span
    ladder may still have repaired it.
    """
    if not isinstance(items, list):
        return []
    rejected: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "")
        if quote and quote not in audit and quote not in rejected:
            rejected.append(quote)
    return rejected


def _merge_quotes(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for quote in group:
            if quote not in merged:
                merged.append(quote)
    return merged


def _split_candidate_spans(
    audit: str, spans: object
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(spans, list):
        return [], []
    matched: list[dict[str, Any]] = []
    rejected: list[str] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        quote = str(span.get("quote") or "")
        start = span.get("start_char")
        end = span.get("end_char")
        state = str(span.get("validation_state") or "")
        exact = (
            bool(audit)
            and isinstance(start, int)
            and isinstance(end, int)
            and end > start
            and audit[start:end] == quote
            and state == "valid"
        )
        if exact:
            matched.append(span)
        elif quote:
            rejected.append(quote)
    return matched, rejected


def _window(
    audit: str, spans: list[dict[str, Any]]
) -> tuple[str, int, list[ExportedEvidenceSpan]]:
    origin = max(0, min(int(span["start_char"]) for span in spans) - CONTEXT)
    stop = min(len(audit), max(int(span["end_char"]) for span in spans) + CONTEXT)
    excerpt = audit[origin:stop]
    exported: list[ExportedEvidenceSpan] = []
    for span in spans:
        start = int(span["start_char"])
        end = int(span["end_char"])
        try:
            exported.append(
                ExportedEvidenceSpan(
                    field_name=str(span["field_name"]),
                    quote=str(span["quote"]),
                    excerpt_start_char=start - origin,
                    excerpt_end_char=end - origin,
                    document_start_char=start,
                    document_end_char=end,
                )
            )
        except ValueError:
            continue
    if not exported:
        return "", 0, []
    # Rebuild the window from the spans that the contract accepted.
    origin = max(0, min(span.document_start_char for span in exported) - CONTEXT)
    stop = min(len(audit), max(span.document_end_char for span in exported) + CONTEXT)
    excerpt = audit[origin:stop]
    exported = [
        ExportedEvidenceSpan(
            field_name=span.field_name,
            quote=span.quote,
            excerpt_start_char=span.document_start_char - origin,
            excerpt_end_char=span.document_end_char - origin,
            document_start_char=span.document_start_char,
            document_end_char=span.document_end_char,
        )
        for span in exported
    ]
    return excerpt, origin, exported


def _span_support(span: dict[str, Any], findings: tuple[SemanticFinding, ...]) -> dict[str, Any]:
    field_name = str(span.get("field_name") or "")
    objected = any(item.field == field_name for item in findings)
    if objected:
        label = (
            "The quote matches the excerpt at the stored offsets. "
            "It does not semantically support the assigned value."
        )
        supports: bool | None = False
    else:
        label = (
            "The quote matches the excerpt at the stored offsets. "
            "No recorded objection on this field. This is not semantic approval."
        )
        supports = None
    return {
        "field_name": field_name,
        "offset_matches": True,
        "supports_assigned_value": supports,
        "support_label": label,
    }


def _assigned(case: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in _VALUE_FIELDS:
        value = case.get(name)
        observation = str(case.get(f"{name}_observation") or "")
        if value not in (None, "", [], ()):
            values[name] = {"value": value, "observation": observation}
    for name in _LABEL_FIELDS:
        labels = case.get(name) or []
        observation = str(case.get(f"{name}_observation") or "")
        if isinstance(labels, list) and labels:
            values[name] = {
                "value": [_label_value(item) for item in labels if _label_value(item)],
                "observation": observation,
            }
    return values


def _label_value(item: object) -> str:
    if isinstance(item, dict):
        value = item.get("value")
        if isinstance(value, dict):
            return str(value.get("value") or "")
        return "" if value is None else str(value)
    return "" if item is None else str(item)


def _diagnostic(failure: dict[str, Any] | None) -> dict[str, Any]:
    if not failure:
        return {}
    diagnostic = failure.get("provider_diagnostic")
    kept: dict[str, Any] = {}
    if isinstance(diagnostic, dict):
        for key in _DIAGNOSTIC_KEYS:
            if key in diagnostic and not isinstance(diagnostic[key], (dict, list)):
                kept[key] = diagnostic[key]
        summary = diagnostic.get("rejected_output_summary")
        if isinstance(summary, dict):
            kept["rejected_output_summary"] = {
                key: summary[key] for key in _SUMMARY_KEYS if key in summary
            }
    error_class = failure.get("error_class")
    if isinstance(error_class, str):
        kept["error_class"] = error_class
    reason_codes = failure.get("reason_codes")
    if isinstance(reason_codes, list):
        kept["reason_codes"] = [str(item) for item in reason_codes]
    invalid_fields = failure.get("invalid_fields")
    if isinstance(invalid_fields, list):
        kept["invalid_fields"] = [str(item) for item in invalid_fields]
    return kept


def _status(
    automatically_valid: bool,
    approved: bool,
    findings: tuple[SemanticFinding, ...],
    reviews: list[dict[str, Any]],
    doc_id: str,
    case_id: str | None,
) -> str:
    if approved:
        return "semantically approved"
    open_rows = [
        row
        for row in reviews
        if row.get("state") == "open" and _targets(row, doc_id, case_id)
    ]
    if open_rows and not automatically_valid:
        return "unresolved review"
    if automatically_valid:
        return "automatically valid; not semantically approved"
    if findings and not automatically_valid:
        return "unresolved review"
    return ""


def _targets(row: dict[str, Any], doc_id: str, case_id: str | None) -> bool:
    if row.get("doc_id") == doc_id:
        return True
    target = str(row.get("target_id") or "")
    if case_id and target == case_id:
        return True
    tokens = set(target.replace(":", " ").replace("#", " ").split())
    return doc_id in tokens


def _findings_for(doc_id: str, case_id: str | None) -> tuple[SemanticFinding, ...]:
    """Findings aimed at this case. A document-level note does not veto a later case.

    A note with no case id stays on the document view. It does not block owner
    approval of a stored case from a later run.
    """
    return tuple(
        item
        for item in RECORDED_FINDINGS
        if item.doc_id == doc_id and item.case_id == case_id
    )


def _finding_dict(item: SemanticFinding) -> dict[str, str]:
    return {
        "field": item.field,
        "risk": item.risk,
        "summary": item.summary,
        "source_note": item.source_note,
    }


def _links(path: Path, allowed: set[str], missing: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        missing.append(path.name)
        return []
    kept = []
    for row in _jsonl(path):
        doc_id = str(row.get("doc_id") or "")
        if doc_id in allowed:
            kept.append(
                {
                    "doc_id": doc_id,
                    "canonical_doc_id": str(row.get("canonical_doc_id") or ""),
                    "review_state": str(row.get("review_state") or ""),
                }
            )
    return kept


def _canonical(links: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in links:
        if row.get("review_state") not in CONFIRMED:
            continue
        doc_id = str(row.get("doc_id") or "")
        canonical = str(row.get("canonical_doc_id") or "")
        if doc_id and canonical:
            mapping[doc_id] = canonical
    return mapping


def _labels(
    path: Path | None,
    allowed: set[str],
    holdout: set[str],
    missing: list[str],
) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    if not path.is_file():
        missing.append(path.name)
        return {}
    kept: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row.get("doc_id") or ""
            if not doc_id or doc_id in holdout or doc_id not in allowed:
                continue
            kept[doc_id] = {
                "human_scope_class": (row.get("human_scope_class") or "").strip(),
                "human_reason_code": (row.get("human_reason_code") or "").strip(),
            }
    return kept


def _relevance(
    path: Path | None,
    allowed: set[str],
    missing: list[str],
) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.is_file():
        missing.append(path.name)
        return []
    return [row for row in _jsonl(path) if str(row.get("doc_id") or "") in allowed]


def _reviews(
    paths: list[Path],
    allowed: set[str],
    missing: list[str],
    aliases: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            missing.append(path.name)
            continue
        for row in _jsonl(path):
            target = str(row.get("target_id") or "")
            tokens = set(target.replace(":", " ").replace("#", " ").split())
            resolved = ""
            if target in aliases and aliases[target] in allowed:
                resolved = aliases[target]
            else:
                for token in tokens:
                    if token in allowed:
                        resolved = token
                        break
                    if token in aliases and aliases[token] in allowed:
                        resolved = aliases[token]
                        break
            if not resolved:
                continue
            rows.append(
                {
                    "item_id": str(row.get("item_id") or ""),
                    "state": str(row.get("state") or ""),
                    "reason_code": str(row.get("reason_code") or ""),
                    "target_type": str(row.get("target_type") or ""),
                    "target_id": target,
                    "doc_id": resolved,
                    "priority": row.get("priority"),
                }
            )
    return rows


def _corrections(path: Path | None, missing: list[str]) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        if path is not None and not path.is_file():
            missing.append(path.name)
        return []
    kept = []
    for row in _jsonl(path):
        kept.append(
            {
                "case_id": str(row.get("case_id") or ""),
                "field": str(row.get("field") or ""),
                "original_value": _mask_export_text(str(row.get("original_value") or "")),
                "corrected_value": _mask_export_text(str(row.get("corrected_value") or "")),
                "reviewer": "recorded reviewer",
                "note": _mask_export_text(str(row.get("note") or "")),
            }
        )
    return kept


def _valid_spans_by_case(
    path: Path,
    allowed: set[str],
    holdout: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Valid spans stored beside the case. A missing file adds nothing.

    Scalar evidence, including ``problem_summary``, is not inline on the case.
    A stored case whose only valid spans are external would otherwise disappear
    from the export.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return grouped
    for span in _jsonl(path):
        doc_id = str(span.get("doc_id") or "")
        if not doc_id or doc_id in holdout or doc_id not in allowed:
            continue
        if str(span.get("validation_state") or "") != "valid":
            continue
        grouped.setdefault(str(span.get("owner_id") or ""), []).append(span)
    return grouped


def _with_external_spans(case: dict[str, Any], spans: list[dict[str, Any]]) -> dict[str, Any]:
    current = [span for span in (case.get("all_evidence_spans") or []) if isinstance(span, dict)]
    seen = {str(span.get("evidence_id")) for span in current if span.get("evidence_id")}
    added = False
    for span in spans:
        evidence_id = str(span.get("evidence_id") or "")
        if evidence_id and evidence_id in seen:
            continue
        current.append(span)
        if evidence_id:
            seen.add(evidence_id)
        added = True
    if not added:
        return case
    copied = dict(case)
    copied["all_evidence_spans"] = current
    return copied


def _rows(
    path: Path,
    allowed: set[str],
    holdout: set[str],
    missing: list[str],
) -> list[dict[str, Any]]:
    if not path.is_file():
        missing.append(path.name)
        return []
    kept = []
    for row in _jsonl(path):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id or doc_id in holdout or doc_id not in allowed:
            continue
        kept.append(row)
    return kept


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _split_ids(path: Path) -> tuple[set[str], set[str]]:
    development: set[str] = set()
    holdout: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row.get("doc_id") or ""
            split = row.get("split") or ""
            if split == DEVELOPMENT:
                development.add(doc_id)
            elif split == HOLDOUT:
                holdout.add(doc_id)
    return development, holdout


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _mask_export_text(value: str) -> str:
    masked, _spans = redact(value)
    return masked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build prepared submission exports.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    build_submission(args.manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
