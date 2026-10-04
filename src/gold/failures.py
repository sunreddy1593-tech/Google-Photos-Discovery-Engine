"""Development failure categories for the Phase 6 quality gate.

Every category receives a corrective action or an accepted written limitation.
The holdout split is refused: this ledger is not an error analysis of frozen
documents, and it does not rescore them. Document text is not copied into the
ledger.
"""

from __future__ import annotations

from src.gold.evaluate import HoldoutAnalysisError
from src.gold.match import match_cases
from src.gold.metrics import (
    PREFILTER_RECALL_MIN,
    RELEVANCE_PRECISION_MIN,
    RELEVANCE_RECALL_MIN,
    RELEVANT_SCOPES,
)

LEDGER_VERSION = "phase6-failure-ledger/v2"
OFFICIAL_DEV_RUN_ID = "d7581cf180be"
CATEGORY_IDS: tuple[str, ...] = (
    "prefilter_false_drop",
    "relevance_false_positive",
    "relevance_false_negative",
    "scope_boundary_disagreement",
    "provider_schema_rejection",
    "evidence_span_rejection",
    "unmatched_gold_case",
    "unmatched_model_case",
    "unsupported_inference",
    "accepted_empty_extraction",
    "excluded_technical_failure",
    "inter_reviewer_agreement",
    "gold_set_final",
    "holdout_prior_exposure",
    "accepted_record_schema_denominator",
    "model_case_semantic_approval",
    "cross_stage_prompt_label",
)
_FORBIDDEN_EVIDENCE = frozenset({
    "document_text", "quote", "quotes", "source_text", "raw_text", "raw_text_audit",
})

# Published aggregates only. These constants do not read holdout packets.
OFFICIAL_PROJECT = {
    "official_gold_documents": 35,
    "official_gold_cases": 21,
    "approved_case_ids": (
        "reddit-0d477b54fb9b#c01",
        "reddit-bde62ddef9b5#c01",
        "google_support-2a080da4b930#c01",
        "google_support-5b2ec98df32b#c01",
        "reddit-87311c2633df#c01",
    ),
    "consumed_holdout_matched": 5,
    "consumed_holdout_cases": 15,
    "successor_holdout_matched": 7,
    "successor_holdout_cases": 15,
}


def build_development_failure_ledger(
    *,
    report: dict[str, object],
    documents: tuple | list,
    predictions: dict[str, object],
    gold_cases: tuple | list = (),
    extracted_cases: tuple | list = (),
    texts: dict[str, str] | None = None,
    extraction_events: tuple | list = (),
) -> dict[str, object]:
    """Document every development failure category. Holdout input is refused."""
    if report.get("split") != "dev":
        raise HoldoutAnalysisError(
            "failure categories are refused for the holdout split"
        )
    observations = _observe(
        documents=documents,
        predictions=predictions,
        gold_cases=gold_cases,
        extracted_cases=extracted_cases,
        texts=texts or {},
        extraction_events=extraction_events,
    )
    project = OFFICIAL_PROJECT if _official_run(report) else None
    categories = _categories(report, observations, project)
    _require_complete(categories)
    ledger = {
        "ledger_version": LEDGER_VERSION,
        "split": "dev",
        "status": "documented",
        "thresholds": {
            "prefilter_recall": PREFILTER_RECALL_MIN,
            "relevance_precision": RELEVANCE_PRECISION_MIN,
            "relevance_recall": RELEVANCE_RECALL_MIN,
        },
        "thresholds_lowered": False,
        "labels_edited": False,
        "holdout_rescored": False,
        "document_text_included": False,
        "categories": categories,
    }
    _reject_source_text(ledger)
    return ledger


def _official_run(report: dict[str, object]) -> bool:
    saved = report.get("saved_inputs")
    if not isinstance(saved, dict):
        return False
    return (
        saved.get("run_id") == OFFICIAL_DEV_RUN_ID
        and report.get("documents") == 10
        and report.get("gold_cases") == 6
    )


def _observe(
    *,
    documents,
    predictions: dict[str, object],
    gold_cases,
    extracted_cases,
    texts: dict[str, str],
    extraction_events,
) -> dict[str, list[str]]:
    drops: list[str] = []
    false_positives: list[str] = []
    false_negatives: list[str] = []
    boundaries: list[str] = []
    for document in documents:
        predicted = predictions.get(document.doc_id)
        if predicted is None or getattr(predicted, "technical_state", None) != "ok":
            continue
        gold_scope = _value(getattr(document, "scope_class", None))
        predicted_scope = _value(getattr(predicted, "scope_class", None))
        passed = bool(getattr(predicted, "prefilter_passed", False))
        if document.prefilter_should_pass and not passed:
            drops.append(document.doc_id)
        gold_relevant = gold_scope in RELEVANT_SCOPES
        predicted_relevant = passed and predicted_scope in RELEVANT_SCOPES
        if predicted_relevant and not gold_relevant:
            false_positives.append(document.doc_id)
        elif gold_relevant and not predicted_relevant:
            false_negatives.append(document.doc_id)
        elif gold_relevant and predicted_relevant and gold_scope != predicted_scope:
            boundaries.append(f"{document.doc_id}: gold {gold_scope}, predicted {predicted_scope}")

    schema: list[str] = []
    evidence: list[str] = []
    empty: list[str] = []
    other_failures: list[str] = []
    for event in extraction_events:
        if event.get("stage") not in (None, "extract"):
            continue
        detail = event.get("detail") or {}
        if event.get("status") == "skipped" or detail.get("skip_cause") == "out_of_scope":
            continue
        target = str(event.get("target_id") or "")
        if event.get("status") == "succeeded" and detail.get("case_count") == 0:
            empty.append(target)
            continue
        if event.get("status") != "failed":
            continue
        diagnostic = detail.get("provider_diagnostic") or {}
        summary = diagnostic.get("rejected_output_summary") or {}
        schema_rejected = (
            diagnostic.get("error_code") == "json_validate_failed"
            or summary.get("application_state") == "invalid"
        )
        if schema_rejected:
            schema.append(target)
        elif event.get("reason_code") == "evidence_validation_failed":
            evidence.append(target)
        else:
            other_failures.append(target)

    matched_gold: set[str] = set()
    matched_model: set[str] = set()
    gold_by_doc: dict[str, list] = {}
    extracted_by_doc: dict[str, list] = {}
    for case in gold_cases:
        gold_by_doc.setdefault(case.doc_id, []).append(case)
    for case in extracted_cases:
        extracted_by_doc.setdefault(getattr(case, "doc_id"), []).append(case)
    for document in documents:
        for gold, extracted in match_cases(
            gold_by_doc.get(document.doc_id, []),
            extracted_by_doc.get(document.doc_id, []),
            texts.get(document.doc_id),
        ):
            matched_gold.add(str(gold.gold_case_id))
            matched_model.add(str(extracted.case_id))
    unmatched_gold = [
        str(case.gold_case_id) for case in gold_cases
        if str(case.gold_case_id) not in matched_gold
    ]
    unmatched_model = [
        str(case.case_id) for case in extracted_cases
        if str(case.case_id) not in matched_model
    ]
    return {
        "prefilter_false_drop": drops,
        "relevance_false_positive": false_positives,
        "relevance_false_negative": false_negatives,
        "scope_boundary_disagreement": boundaries,
        "provider_schema_rejection": schema,
        "evidence_span_rejection": evidence,
        "unmatched_gold_case": unmatched_gold,
        "unmatched_model_case": unmatched_model,
        "accepted_empty_extraction": empty,
        "other_extraction_failure": other_failures,
    }


def _categories(report: dict[str, object], observations: dict[str, list[str]], project: dict | None) -> list[dict[str, object]]:
    relevance = report.get("relevance") if isinstance(report.get("relevance"), dict) else {}
    agreement = report.get("agreement") if isinstance(report.get("agreement"), dict) else {}
    unsupported = report.get("unsupported_inference") if isinstance(report.get("unsupported_inference"), dict) else {}
    saved = report.get("saved_inputs") if isinstance(report.get("saved_inputs"), dict) else {}
    prompts = saved.get("measured_prompts") if isinstance(saved.get("measured_prompts"), dict) else {}
    coverage = report.get("case_coverage") if isinstance(report.get("case_coverage"), dict) else {}
    rows = [
        _row(
            "prefilter_false_drop",
            observations["prefilter_false_drop"],
            "accepted_limitation",
            _count_sentence(
                "Gold documents with prefilter_should_pass that this run dropped",
                observations["prefilter_false_drop"],
            ) + f" Prefilter recall on this development report is {_num(report.get('prefilter_recall'))}. "
            "The 0.90 threshold was not lowered, and the prefilter ruleset was not edited.",
        ),
        _row(
            "relevance_false_positive",
            observations["relevance_false_positive"],
            "accepted_limitation",
            _count_sentence("End-to-end relevance false positives", observations["relevance_false_positive"])
            + f" Development precision is {_num(relevance.get('precision'))} against 0.85. "
            "The threshold was not lowered and gold labels were not changed to match the model.",
        ),
        _row(
            "relevance_false_negative",
            observations["relevance_false_negative"],
            "accepted_limitation",
            _count_sentence("End-to-end relevance false negatives", observations["relevance_false_negative"])
            + f" Development recall is {_num(relevance.get('recall'))} against 0.80. "
            "A prefilter drop counts as predicted not-relevant. Non-ok technical states stay excluded.",
        ),
        _row(
            "scope_boundary_disagreement",
            observations["scope_boundary_disagreement"],
            "accepted_limitation",
            _count_sentence(
                "Core versus adjacent disagreements, both still relevant",
                observations["scope_boundary_disagreement"],
            ) + " These do not move the relevance precision or recall gates. Labels were not edited to remove them.",
        ),
        _row(
            "provider_schema_rejection",
            observations["provider_schema_rejection"],
            "accepted_limitation",
            _count_sentence(
                "Provider outputs rejected for schema validation",
                observations["provider_schema_rejection"],
            ) + " A rejected output is excluded from the accepted-record schema rate and is not a successful validation. "
            "The one-attempt bound was not used to issue a repair or re-extraction call.",
        ),
        _row(
            "evidence_span_rejection",
            observations["evidence_span_rejection"],
            "corrective_action" if observations["evidence_span_rejection"] else "accepted_limitation",
            _count_sentence("Extraction cases withheld by the evidence gate", observations["evidence_span_rejection"])
            + (
                " The gate kept the invalid case out of stored analysis. The gold case stays unmatched, and no span was edited to force a match."
                if observations["evidence_span_rejection"] else
                " No evidence-gate rejection was recorded on this development run."
            ),
        ),
        _row(
            "unmatched_gold_case",
            observations["unmatched_gold_case"],
            "accepted_limitation",
            _count_sentence("Gold cases without an evidence-overlap match", observations["unmatched_gold_case"])
            + f" Report coverage is {_num(coverage.get('matched_cases'))} of {_num(coverage.get('gold_cases'))}. "
            "Unmatched gold cases are not scored as field matches. Gold quotes were not rewritten.",
        ),
        _row(
            "unmatched_model_case",
            observations["unmatched_model_case"],
            "accepted_limitation",
            _count_sentence("Stored model cases without an evidence-overlap match", observations["unmatched_model_case"])
            + " A stored case that misses its reference is not semantic approval and was not deleted to raise coverage.",
        ),
        _inference_row(unsupported),
        _empty_row(observations["accepted_empty_extraction"], project),
        _technical_row(report, observations),
        _agreement_row(agreement),
        _gold_size_row(project),
        _holdout_row(project),
        _schema_denominator_row(saved),
        _approval_row(observations["unmatched_model_case"], project),
        _prompt_row(prompts),
    ]
    return rows


def _inference_row(unsupported: dict) -> dict[str, object]:
    overall = unsupported.get("overall")
    fields = {
        key: value for key, value in unsupported.items()
        if key != "overall" and isinstance(value, (int, float)) and value > 0
    }
    return _row(
        "unsupported_inference",
        list(fields),
        "accepted_limitation",
        f"Overall unsupported-inference rate on matched cases is {_num(overall)}. "
        "A verbatim quote does not prove the value is supported. "
        + (
            "Fields above zero: " + ", ".join(f"{name}={_num(value)}" for name, value in sorted(fields.items())) + "."
            if fields else
            "No matched field with a positive unsupported-inference rate was reported."
        ),
    )


def _empty_row(empty: list[str], project: dict | None) -> dict[str, object]:
    if empty:
        return _row(
            "accepted_empty_extraction",
            empty,
            "accepted_limitation",
            _count_sentence("Eligible documents that succeeded with zero cases", empty)
            + " An accepted-empty response is a model outcome, not a dropped record. It was not retried.",
        )
    statement = "Eligible accepted-empty documents in this development run: 0."
    disposition = "accepted_limitation"
    if project is not None:
        disposition = "corrective_action"
        statement += (
            " extract/v4 replaced the earlier accepted-empty album, Memories, and poodle responses "
            "on this measurement. The earlier extract/v3 report was not rewritten. A stored case that "
            "does not overlap its reference remains an unmatched-case limitation."
        )
    return _row("accepted_empty_extraction", empty, disposition, statement)


def _technical_row(report: dict[str, object], observations: dict[str, list[str]]) -> dict[str, object]:
    other = observations["other_extraction_failure"]
    return _row(
        "excluded_technical_failure",
        other,
        "accepted_limitation",
        f"Relevance records excluded for a non-ok technical state: {_num(report.get('excluded_technical_failures'))}. "
        f"Provider schema rejections are counted in their own category: {len(observations['provider_schema_rejection'])}. "
        f"Evidence-gate rejections are counted in their own category: {len(observations['evidence_span_rejection'])}. "
        + _count_sentence("Other failed extraction documents", other)
        + " These failures stay out of every metric and are not counted as matches.",
    )


def _agreement_row(agreement: dict) -> dict[str, object]:
    pairs = agreement.get("pairs")
    return _row(
        "inter_reviewer_agreement",
        [],
        "accepted_limitation",
        f"Independent pre-adjudication pairs: {_num(pairs)}. "
        f"Raw agreement is {_num(agreement.get('raw_agreement'))} and Cohen's kappa is {_num(agreement.get('cohen_kappa'))}. "
        "One reviewer does not create agreement of zero or one, and no second coder was added.",
    )


def _gold_size_row(project: dict | None) -> dict[str, object]:
    if project is None:
        statement = (
            "This development evaluation does not claim the official gold size. "
            "Further gold labelling is closed. This run does not add documents."
        )
    else:
        statement = (
            f"Official gold is {project['official_gold_documents']} documents and "
            f"{project['official_gold_cases']} cases, reviewed by Sunayana. "
            "The owner closed the former 75-100 labelling volume. These approved labels are the final gold set. "
            "No documents were added, and existing labels were not edited."
        )
    return _row("gold_set_final", [], "accepted_limitation", statement)


def _holdout_row(project: dict | None) -> dict[str, object]:
    if project is None:
        statement = "This development ledger does not open, list, or rescore holdout documents."
    else:
        statement = (
            f"The consumed holdout measurement remains {project['consumed_holdout_matched']} of "
            f"{project['consumed_holdout_cases']} reference cases. The separate successor remains "
            f"{project['successor_holdout_matched']} of {project['successor_holdout_cases']} and does not "
            "replace that consumed claim. Those seats had prior development exposure. This ledger did not rescore them."
        )
    return _row("holdout_prior_exposure", [], "accepted_limitation", statement)


def _schema_denominator_row(saved: dict) -> dict[str, object]:
    denominator = saved.get("schema_denominator") or (
        "accepted records only; rejected provider outputs are excluded and reported separately"
    )
    return _row(
        "accepted_record_schema_denominator",
        [],
        "accepted_limitation",
        "The reported schema validation rate uses this denominator: "
        f"{denominator}. It does not establish that 100% of processed provider outputs passed validation.",
    )


def _approval_row(unmatched_model: list[str], project: dict | None) -> dict[str, object]:
    if project is None:
        statement = (
            "No semantic-approval list was supplied with this evaluation. "
            "Passing the quote gate does not approve a model case."
        )
        evidence: list[str] = []
    else:
        approved = list(project["approved_case_ids"])
        evidence = approved
        statement = (
            "Sunayana approved these development cases after the disclosed disagreements were shown: "
            + ", ".join(approved)
            + ". The cat summary-quote rejection and the schema failure were accepted and were not repaired. "
            "model_outputs_semantically_approved stays false. Approval was not extended by this ledger."
        )
        if unmatched_model:
            still_unapproved = [case_id for case_id in unmatched_model if case_id not in set(approved)]
            approved_unmatched = [case_id for case_id in unmatched_model if case_id in set(approved)]
            if still_unapproved:
                statement += " Unmatched stored cases remain unapproved: " + ", ".join(still_unapproved) + "."
            if approved_unmatched:
                statement += (
                    " Approved stored cases that still do not overlap a reference: "
                    + ", ".join(approved_unmatched) + "."
                )
    return _row("model_case_semantic_approval", evidence, "accepted_limitation", statement)


def _prompt_row(prompts: dict) -> dict[str, object]:
    measured = prompts.get("relevance")
    pin = prompts.get("extraction_manifest_relevance_pin")
    extract = prompts.get("extract")
    if measured and pin and measured != pin:
        return _row(
            "cross_stage_prompt_label",
            [],
            "corrective_action",
            f"The measured relevance prompt is {measured}, from the relevance-stage manifest. "
            f"The extraction manifest still records the registry relevance pin {pin}. "
            f"The measured extraction prompt is {extract}. "
            "This ledger uses the stage that ran each prompt. The historical report was not rewritten, and the active pins were not moved.",
        )
    if not measured:
        statement = "No separate relevance-stage manifest was supplied, so this ledger does not invent a relevance prompt version."
    else:
        statement = (
            f"Measured prompts agree with the recorded stage manifests: relevance {measured}, extract {extract}."
        )
    return _row("cross_stage_prompt_label", [], "accepted_limitation", statement)


def _row(category: str, evidence: list[str], disposition: str, statement: str) -> dict[str, object]:
    return {
        "category": category,
        "observed_count": len(evidence),
        "evidence": list(evidence),
        "disposition": disposition,
        "statement": statement,
    }


def _count_sentence(label: str, evidence: list[str]) -> str:
    if not evidence:
        return f"{label}: 0."
    return f"{label}: {len(evidence)} ({', '.join(evidence)})."


def _num(value: object) -> str:
    if value is None:
        return "null"
    return str(value)


def _value(value: object) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return None if raw is None else str(raw)


def _require_complete(categories: list[dict[str, object]]) -> None:
    found = [row["category"] for row in categories]
    if found != list(CATEGORY_IDS):
        raise ValueError("failure ledger categories are missing, extra, or reordered")
    for row in categories:
        if row["disposition"] not in {"corrective_action", "accepted_limitation"}:
            raise ValueError("a failure category lacks a written disposition")
        if not str(row["statement"]).strip():
            raise ValueError("a failure category lacks a written statement")


def _reject_source_text(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FORBIDDEN_EVIDENCE:
                raise ValueError("failure ledger must not copy document text")
            _reject_source_text(value)
    elif isinstance(payload, list):
        for item in payload:
            _reject_source_text(item)
