"""Offline assembly of extraction responses into existing case contracts.

No completion, persistence or review mutation occurs here. A future pipeline
stage can obtain ExtractionPayload through ModelGateway, then call this pure
boundary and persist its cases, field spans and failures using existing stores.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime

from pydantic import ValidationError

from src.core.ids import (
    case_id_ordered,
    case_id_unordered,
    case_sort_key,
    extraction_fingerprint,
)
from src.core.versions import SCHEMA_VERSION
from src.extract.schema import ExtractionCasePayload, ExtractionPayload, QuotePayload
from src.extract.validator import (
    RecordValidation,
    SpanValidation,
    validate_record,
    validate_span,
)
from src.models.document_derived import DocumentDerived
from src.models.enums import (
    DecisionTechnicalState,
    EvidenceOwnerType,
    ExtractorType,
    OffsetState,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import RetrievalCase

_LABEL_FIELDS = (
    "target_subjects", "remembered_cues", "forgotten_information",
    "query_strategies", "system_responses", "workarounds", "impact_signals",
)


@dataclass(frozen=True)
class ExtractionResult:
    """Retained candidate and verdict; only ok cases may enter analysis.

    Schema failures retain the candidate and every span checked so far, but have
    no RetrievalCase. Evidence failures keep a pending, review-required case.
    The orchestration layer must consume requires_review, not discard failures.
    """

    case_id: str
    candidate: ExtractionCasePayload
    case: RetrievalCase | None
    external_spans: tuple[EvidenceSpan, ...]
    span_validations: tuple[SpanValidation, ...]
    record_validation: RecordValidation | None
    technical_state: DecisionTechnicalState
    error_fields: tuple[str, ...] = ()

    @property
    def requires_review(self) -> bool:
        return self.technical_state is not DecisionTechnicalState.ok

    @property
    def review_reason_code(self) -> ReasonCode | None:
        if self.record_validation is not None:
            return self.record_validation.review_reason_code
        if self.requires_review:
            return ReasonCode.schema_validation_failed
        return None

    @property
    def all_evidence_spans(self) -> tuple[EvidenceSpan, ...]:
        if self.record_validation is not None:
            return self.record_validation.all_evidence_spans
        return tuple(verdict.span for verdict in self.span_validations)


@dataclass(frozen=True)
class _Prepared:
    candidate: ExtractionCasePayload
    canonical: str
    # Locations are external rows, inline dimension entries, or severity entries.
    located: tuple[tuple[str, int, SpanValidation], ...]
    error_fields: tuple[str, ...] = ()

    @property
    def sort_key(self) -> tuple[int, int, str, str] | None:
        spans = [verdict.span for _, _, verdict in self.located]
        if self.error_fields or not spans or any(not span.is_resolved for span in spans):
            return None
        return min(
            case_sort_key(span.start_char, span.end_char, span.quote, self.canonical)
            for span in spans
        )


def _prepare(candidate: ExtractionCasePayload, document: DocumentDerived) -> _Prepared:
    canonical = json.dumps(candidate.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    owner = case_id_unordered(document.doc_id, canonical)
    located: list[tuple[str, int, SpanValidation]] = []
    quotes: list[tuple[str, int, str, EvidenceOwnerType, QuotePayload]] = [
        ("external", index, quote.field_name, EvidenceOwnerType.retrieval_case, quote)
        for index, quote in enumerate(candidate.field_evidence)
    ]
    for field in _LABEL_FIELDS:
        quotes.extend(
            (field, index, field, EvidenceOwnerType.observed_value, label.evidence)
            for index, label in enumerate(getattr(candidate, field))
        )
    quotes.extend(
        ("severity", index, "severity", EvidenceOwnerType.severity, quote)
        for index, quote in enumerate(candidate.severity_evidence)
    )
    for location, index, field, owner_type, quote in quotes:
        try:
            span = EvidenceSpan(
                doc_id=document.doc_id, owner_id=owner, owner_type=owner_type,
                field_name=field, quote=quote.quote, start_char=quote.start_char,
                end_char=quote.end_char, speaker=quote.speaker,
                offset_state=(OffsetState.missing_unresolved if quote.start_char is None
                              else OffsetState.supplied_exact),
            )
        except ValidationError:
            # Never store Pydantic's error input or an exception string in logs.
            return _Prepared(candidate, canonical, tuple(located), (field,))
        located.append((location, index, validate_span(
            span, document.raw_text_audit, document.redaction_spans,
        )))
    return _Prepared(candidate, canonical, tuple(located))


def _rebind(span: EvidenceSpan, owner: str) -> EvidenceSpan:
    data = span.model_dump()
    data.update(owner_id=owner, evidence_id="")
    return EvidenceSpan.model_validate(data)


def _exact_query_supported(value: str, spans: tuple[EvidenceSpan, ...], text: str) -> bool:
    """Conservative direct-quote / query-line check, anchored to its evidence.

    A matching word elsewhere is insufficient. Unrecognized delimiters need
    review, never conversion into a paraphrase or a fabricated exact query.
    """
    escaped = re.escape(value)
    patterns = [re.escape(left) + "(" + escaped + ")" + re.escape(right)
                for left, right in (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`"))]
    patterns.append(r"(?im)^\s*(?:query|search query|search term)\s*:\s*(" + escaped + r")\s*$")
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            start, end = match.span(1)
            if any(span.field_name == "exact_query" and span.is_valid
                   and span.start_char <= start and span.end_char >= end for span in spans):
                return True
    return False


def assemble_cases(
    payload: ExtractionPayload,
    document: DocumentDerived,
    decision: RelevanceDecision,
    *,
    model_name: str,
    prompt_version: str,
    extracted_at: datetime,
) -> tuple[ExtractionResult, ...]:
    """Validate zero/one/many cases without touching text, labels or providers.

    Identifiers are assigned after the existing span ladder resolves offsets.
    Any unresolved span causes the #u fallback. Resolved cases use the existing
    four-part position/quote/payload sort key, independently of response order.
    """
    if payload.doc_id != document.doc_id or decision.doc_id != document.doc_id:
        raise ValueError("extraction and relevance must concern the target document")
    if (decision.technical_state is not DecisionTechnicalState.ok
            or decision.validation_state is not ValidationState.valid
            or decision.scope_class not in {ScopeClass.core_incomplete_recall,
                                           ScopeClass.adjacent_known_item_retrieval}):
        raise ValueError("extraction requires a valid in-scope relevance decision")
    if not model_name.strip() or not prompt_version.startswith("extract/"):
        raise ValueError("model name and versioned extraction prompt are required")
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise ValueError("extracted_at must be timezone-aware")

    prepared = [_prepare(candidate, document) for candidate in payload.cases]
    if len({item.canonical for item in prepared}) != len(prepared):
        raise ValueError("duplicate extraction candidates require review")
    prepared.sort(key=lambda item: (item.sort_key is None, item.sort_key or (), item.canonical))
    fingerprint = extraction_fingerprint(
        model_name, prompt_version, SCHEMA_VERSION, document.content_hash,
    )
    results: list[ExtractionResult] = []
    ordinal = 0
    for item in prepared:
        if item.sort_key is None:
            owner = case_id_unordered(document.doc_id, item.canonical)
        else:
            ordinal += 1
            owner = case_id_ordered(document.doc_id, ordinal)
        data = item.candidate.model_dump()
        data.pop("field_evidence")
        external: list[EvidenceSpan] = []
        verdicts: list[SpanValidation] = []
        for location, index, verdict in item.located:
            bound = _rebind(verdict.span, owner)
            verdicts.append(replace(verdict, span=bound, candidate=_rebind(verdict.original, owner)))
            if location == "external":
                external.append(bound)
            elif location == "severity":
                data["severity_evidence"] = tuple(
                    _rebind(v.span, owner) for loc, _, v in item.located if loc == "severity"
                )
            else:
                data[location][index]["evidence"] = bound
        data.update(
            case_id=owner, doc_id=document.doc_id, scope_class=decision.scope_class,
            extractor_type=ExtractorType.llm, model_name=model_name,
            prompt_version=prompt_version, extraction_fingerprint=fingerprint,
            extracted_at=extracted_at,
        )
        errors = item.error_fields
        case = None
        if not errors:
            try:
                case = RetrievalCase.model_validate(data)
            except ValidationError as exc:
                errors = tuple(sorted({str(error["loc"][0]) if error["loc"] else "case"
                                       for error in exc.errors(include_input=False)}))
        if errors:
            results.append(ExtractionResult(
                owner, item.candidate, None, tuple(external), tuple(verdicts), None,
                DecisionTechnicalState.schema_validation_failed, errors,
            ))
            continue
        gate = validate_record(case, external, decision)
        if case.exact_query is not None and not _exact_query_supported(
            case.exact_query, tuple(external), document.raw_text_audit,
        ):
            gate = replace(
                gate, ok=False,
                errors=(*gate.errors, "exact_query lacks directly quoted or delimited target evidence"),
                reason_codes=(*gate.reason_codes, ReasonCode.evidence_validation_failed),
                invalid_fields=(*gate.invalid_fields, "exact_query"),
            )
        case = gate.apply(case)
        results.append(ExtractionResult(
            owner, item.candidate, case, tuple(external), tuple(verdicts), gate,
            DecisionTechnicalState.ok if gate.ok else DecisionTechnicalState.evidence_validation_failed,
        ))
    return tuple(results)
