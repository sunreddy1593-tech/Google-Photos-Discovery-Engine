"""Adapt saved development artifacts for the existing gold evaluator.

No providers or collection files are read. Source text comes only from selected
gold-dev annotation packets. Frozen holdout documents cannot enter this adapter.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from src.extract.validator import validate_record
from src.pipeline.quality import rooted
from src.gold.annotate import AnnotationError
from src.gold.match import MatchSpan
from src.models.enums import ValidationState
from src.models.evidence import EvidenceSpan
from src.models.evidence_map import OBSERVATION_FIELD, RETRIEVAL_CASE, required_fields
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import RetrievalCase


@dataclass(frozen=True)
class EvaluationCase:
    doc_id: str
    case_id: str
    scope_class: str
    values: dict
    spans: tuple[MatchSpan, ...]


@dataclass
class SavedInputs:
    predictions: dict[str, object]
    extracted_cases: tuple[EvaluationCase, ...]
    texts: dict[str, str]
    processed_records: int
    schema_failures: int
    review_count: int
    failure_count: int
    attempt_count: int
    metadata: dict
    relevance_spans: dict[str, tuple[MatchSpan, ...]]


def _rows_for(path: Path, wanted: set[str], *, key: str = "doc_id") -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get(key) in wanted:
                rows.append(row)
    return rows


def _by_id(rows: list[dict], key: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        identity = row[key]
        if identity in result:
            raise AnnotationError(f"duplicate saved evaluation row: {identity}")
        result[identity] = row
    return result


def _values(case: RetrievalCase) -> dict:
    values = {}
    for name in sorted(required_fields(RETRIEVAL_CASE)):
        value = getattr(case, name)
        if isinstance(value, tuple):
            value = [item.value.value for item in value]
        else:
            value = getattr(value, "value", value)
        observation_name = OBSERVATION_FIELD.get(name)
        observation = getattr(case, observation_name).value if observation_name else "stated"
        values[name] = {"observation": observation, "value": value}
    return values


def _measured_prompts(extraction_manifest: dict, relevance_manifest: Path) -> dict[str, str | None]:
    """Record the prompt each stage actually ran.

    An extraction manifest copies the registry pin for relevance. The paired
    relevance manifest is the source for the relevance prompt. Neither value
    moves the active pin.
    """
    extract_pins = (extraction_manifest.get("versions") or {}).get("prompt_versions") or {}
    relevance_pins: dict = {}
    if relevance_manifest.is_file():
        relevance_pins = (json.loads(relevance_manifest.read_text(encoding="utf-8")).get("versions") or {}).get("prompt_versions") or {}
    return {
        "extract": extract_pins.get("extract"),
        "relevance": relevance_pins.get("relevance"),
        "extraction_manifest_relevance_pin": extract_pins.get("relevance"),
        "relevance_manifest_extract_pin": relevance_pins.get("extract"),
    }


def load_saved_development(
    *, doc_ids: set[str], run: Path, relevance: Path, pack: Path, prefilter_events: Path,
) -> SavedInputs:
    return _load_saved(doc_ids=doc_ids, run=run, relevance=relevance, pack=pack,
                       prefilter_events=prefilter_events, split="dev")


def load_saved_holdout(
    *, root: Path, doc_ids: set[str], run: Path, relevance: Path, pack: Path,
    prefilter_events: Path, freeze: Path, gold: Path, approval: Path,
) -> SavedInputs:
    """Only the claimed, frozen run against the exact human-approved holdout."""
    from src.pipeline.quality import check_holdout_approval, read, sha, QualityBoundsError
    frozen = check_holdout_approval(root, freeze, pack, gold, approval)
    if doc_ids != set(frozen["seats"]["holdout"]):
        raise QualityBoundsError("holdout evaluation requires all reserved seats")
    claim = read(freeze.parent / "measurement_claim.json")
    output = root / claim["output"]
    completed = read(freeze.parent / "measurement_completed.json")
    if (completed.get("freeze_sha256") != sha(freeze) or completed.get("approval_sha256") != sha(approval)
            or completed.get("artifact_sha256") != {
                p.relative_to(root).as_posix(): sha(p) for p in sorted(output.rglob("*")) if p.is_file()
            }):
        raise QualityBoundsError("completed holdout artifacts changed or are incomplete")
    summary = read(output / "summary.json")
    if (claim["freeze_sha256"] != sha(freeze) or claim["approval_sha256"] != sha(approval)
            or run.resolve() != Path(summary["extraction"]["output_dir"]).resolve()
            or relevance.resolve() != (output / "relevance/relevance_decisions.jsonl").resolve()
            or prefilter_events.resolve() != (output / "relevance/stage_events.jsonl").resolve()
            or summary["human_overrides_used"] is not False):
        raise QualityBoundsError("saved holdout artifacts are not the claimed frozen measurement")
    run = rooted(root, run)
    relevance = rooted(root, relevance)
    pack = rooted(root, pack)
    prefilter_events = rooted(root, prefilter_events)
    inputs = _load_saved(doc_ids=doc_ids, run=run, relevance=relevance, pack=pack,
                         prefilter_events=prefilter_events, split="holdout")
    if inputs.metadata["versions"]["prompt_versions"]["extract"] != frozen["extraction_prompt"]:
        raise QualityBoundsError("saved extraction did not use the frozen correction")
    inputs.metadata["role"] = "frozen_holdout_measurement_with_prior_development_exposure"
    inputs.metadata["holdout_source_text_loaded"] = True
    inputs.metadata["freeze_sha256"] = sha(freeze)
    inputs.metadata["approval_sha256"] = sha(approval)
    return inputs


def _load_saved(
    *, doc_ids: set[str], run: Path, relevance: Path, pack: Path, prefilter_events: Path, split: str,
) -> SavedInputs:
    manifest_path = pack / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    allowed = {
        row["doc_id"] for row in manifest["documents"]
        if row.get("gold_split") == split and row.get("phase4_split") == "development"
    }
    if not doc_ids or not doc_ids <= allowed:
        raise AnnotationError("saved evaluation is restricted to the pack's gold-dev documents")
    texts = {}
    sources = [manifest_path, relevance, prefilter_events]
    for doc_id in sorted(doc_ids):
        path = pack / "packets" / f"{doc_id}.json"
        packet = json.loads(path.read_text(encoding="utf-8"))
        if packet["doc_id"] != doc_id or packet["gold_split"] != split or packet["phase4_split"] != "development":
            raise AnnotationError("packet source is not gold development")
        texts[doc_id] = packet["source_text"]
        sources.append(path)

    decisions = _by_id(_rows_for(relevance, doc_ids), "doc_id")
    routes = _by_id([
        row for row in _rows_for(prefilter_events, doc_ids, key="target_id") if row["stage"] == "prefilter"
    ], "target_id")
    inputs = _by_id(_rows_for(run / "extraction_inputs.jsonl", doc_ids), "doc_id")
    events = _by_id([
        row for row in _rows_for(run / "stage_events.jsonl", doc_ids, key="target_id") if row["stage"] == "extract"
    ], "target_id")
    if any(set(rows) != doc_ids for rows in (routes, inputs, events)):
        raise AnnotationError("missing saved stage coverage for a development document")
    predictions = {}
    relevance_spans = {}
    processed = 0
    schema_failures = 0
    for doc_id in sorted(doc_ids):
        route = routes[doc_id]
        passed = route["status"] == "succeeded" and route.get("detail", {}).get("route") == "classify"
        dropped = route["status"] == "dropped"
        if not (passed or dropped):
            raise AnnotationError("prefilter route is missing, failed or not evaluable")
        row = decisions.get(doc_id)
        if row is None and not dropped:
            raise AnnotationError("saved model relevance prediction is missing")
        if row is not None:
            decision = RelevanceDecision.model_validate(row)
            scope = None if decision.scope_class is None else decision.scope_class.value
            technical = decision.technical_state.value
            reason = decision.reason_code.value
            if technical == "ok":
                checked = validate_record(decision)
                if not checked.ok:
                    raise AnnotationError("saved relevance decision fails the current field gate")
                relevance_spans[doc_id] = tuple(
                    MatchSpan(span.quote, span.start_char, span.end_char,
                              "valid" if texts[doc_id][span.start_char:span.end_char] == span.quote else "rejected",
                              span.field_name)
                    for span in checked.all_evidence_spans
                )
        else:
            scope, technical, reason = "out_of_scope", "ok", route.get("reason_code")
        predictions[doc_id] = SimpleNamespace(
            doc_id=doc_id, scope_class=scope, reason_code=reason,
            technical_state=technical, prefilter_passed=passed,
        )
        # Non-ok technical outcomes are excluded by the Phase 6 contract and
        # reported separately; they are not invented as schema-valid responses.
        processed += int(technical == "ok" and row is not None)

    case_rows = _rows_for(run / "retrieval_cases.jsonl", doc_ids)
    _by_id(case_rows, "case_id")
    ledger = _rows_for(run / "evidence_spans.jsonl", doc_ids)
    adapted = []
    for row in case_rows:
        case = RetrievalCase.model_validate(row)
        if not inputs[case.doc_id]["eligible"] or events[case.doc_id]["status"] != "succeeded":
            raise AnnotationError("non-ok extraction case cannot enter evaluation")
        checked = validate_record(case, [EvidenceSpan.model_validate(s) for s in ledger if s.get("owner_id") == case.case_id])
        if case.validation_state != ValidationState.valid or not checked.ok:
            raise AnnotationError("saved analysis case fails the current evidence gate")
        spans = []
        for span in checked.all_evidence_spans:
            exact = texts[case.doc_id][span.start_char:span.end_char] == span.quote
            spans.append(MatchSpan(span.quote, span.start_char, span.end_char, "valid" if exact else "rejected", span.field_name))
        adapted.append(EvaluationCase(case.doc_id, case.case_id, case.scope_class.value, _values(case), tuple(spans)))
        processed += 1
    reviews_path = run / "review_queue.jsonl"
    reviews = _rows_for(reviews_path, doc_ids) if reviews_path.is_file() else []
    failure_count = sum(row["status"] == "failed" for row in events.values())
    attempts = sum(row["eligible"] for row in inputs.values())
    sources.extend(run / name for name in (
        "retrieval_cases.jsonl", "evidence_spans.jsonl", "extraction_inputs.jsonl", "stage_events.jsonl", "run_manifest.json",
    ))
    run_manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    relevance_manifest = relevance.parent / "run_manifest.json"
    if relevance_manifest.is_file():
        sources.append(relevance_manifest)
    return SavedInputs(
        predictions, tuple(adapted), texts, processed, schema_failures,
        len({row["doc_id"] for row in reviews}), failure_count, attempts,
        {
            "role": "development_diagnostic_not_final_quality_certification",
            "run_id": run_manifest["run_id"], "versions": run_manifest.get("versions"),
            "measured_prompts": _measured_prompts(run_manifest, relevance_manifest),
            "eligible_documents": attempts, "failed_extraction_documents": failure_count,
            "accepted_empty_documents": sum(row["status"] == "succeeded" and row.get("detail", {}).get("case_count") == 0 for row in events.values()),
            "skipped_documents": sum(row["status"] == "skipped" for row in events.values()),
            "non_ok_relevance_documents": sum(row.technical_state != "ok" for row in predictions.values()),
            "schema_denominator": "ok model relevance decisions plus stored accepted extraction cases; technical failures are excluded and reported",
            "holdout_source_text_loaded": False, "provider_calls": 0,
            "input_sha256": {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        }, relevance_spans,
    )
