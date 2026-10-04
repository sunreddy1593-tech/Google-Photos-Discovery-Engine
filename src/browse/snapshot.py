"""Build a read-only view of saved development research outputs.

Holdout rows are counted and then discarded. Collected ``raw_text`` is never
stored. Display text is the redacted ``raw_text_audit`` excerpt.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.browse.findings import RECORDED_FINDINGS, SemanticFinding

HOLDOUT = "holdout"
DEVELOPMENT = "development"
CONFIRMED = frozenset({"auto_confirmed", "human_confirmed"})
CONTEXT = 160
EXCERPT_CAP = 480

CORE = "core_incomplete_recall"
ADJACENT = "adjacent_known_item_retrieval"
OUT = "out_of_scope"


@dataclass(frozen=True)
class BrowserPaths:
    """Local inputs. Missing files become empty states, not errors."""

    collected: Path = Path("data/processed/pilot-import/collected_documents.jsonl")
    derived: Path = Path("data/interim/phase3/documents_derived.jsonl")
    links: Path = Path("data/interim/phase3/duplicate_links.jsonl")
    split: Path = Path("data/interim/phase4/relevance_split_manifest.csv")
    labels: Path = Path("data/interim/phase4/relevance_seed_review.csv")
    relevance: Path = Path(
        "data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl"
    )
    human_relevance: Path = Path(
        "data/interim/phase4/development/01455c8aab03/human_relevance_decisions.jsonl"
    )
    extraction: Path = Path("data/interim/phase5/pilot-v2-8192-01/024f9b18b60f")
    phase4_reviews: Path = Path(
        "data/interim/phase4/development/01455c8aab03/review_queue.jsonl"
    )
    phase3_reviews: Path = Path("data/interim/phase3/review_queue.jsonl")
    corrections: Path = Path("data/interim/phase5/human_corrections.jsonl")


@dataclass(frozen=True)
class QuoteView:
    field_name: str
    text: str
    validation_state: str
    offset_matches: bool


@dataclass(frozen=True)
class Correction:
    case_id: str
    field: str
    original_value: str
    corrected_value: str
    reviewer: str
    note: str


@dataclass(frozen=True)
class EvidenceCard:
    doc_id: str
    case_id: str | None
    scope_class: str
    human_scope: str
    source_platform: str
    source_url: str
    excerpt: str
    excerpt_start: int
    highlights: tuple[tuple[int, int], ...]
    values: tuple[tuple[str, str], ...]
    quotes: tuple[QuoteView, ...]
    review_status: str
    automatically_valid: bool
    findings: tuple[SemanticFinding, ...]
    enters_conclusions: bool


@dataclass(frozen=True)
class ScopeComparison:
    scope_class: str
    label: str
    model_cases: int
    targets: tuple[tuple[str, int], ...]
    cues: tuple[tuple[str, int], ...]
    strategies: tuple[tuple[str, int], ...]
    responses: tuple[tuple[str, int], ...]
    outcomes: tuple[tuple[str, int], ...]
    sources: tuple[tuple[str, int], ...]
    empty_reason: str


@dataclass(frozen=True)
class ProvisionalGroup:
    label: str
    case_ids: tuple[str, ...]
    provisional: bool = True


@dataclass(frozen=True)
class Snapshot:
    collected: int
    withheld_holdout: int
    excluded: int
    failed: int
    automatically_valid: int
    semantically_approved: int
    human_reviewed: int
    unresolved: int
    collected_records: int
    analysis_documents: int
    confirmed_duplicates: int
    pending_duplicates: int
    cards: tuple[EvidenceCard, ...]
    core: ScopeComparison
    adjacent: ScopeComparison
    conclusion_cases: int
    groups: tuple[ProvisionalGroup, ...]
    group_reason: str
    corrections: tuple[Correction, ...]
    findings: tuple[SemanticFinding, ...]
    missing: tuple[str, ...] = field(default=())


def build_snapshot(paths: BrowserPaths | None = None) -> Snapshot:
    """Load development artifacts. Holdout text is not retained."""
    paths = paths or BrowserPaths()
    missing: list[str] = []
    splits = _split(paths.split, missing)
    split_loaded = paths.split.is_file()
    holdout = {doc_id for doc_id, split in splits.items() if split == HOLDOUT}
    development = {doc_id for doc_id, split in splits.items() if split == DEVELOPMENT}

    documents = _documents(paths.collected, holdout, development, split_loaded, missing)
    audits = _audits(paths.derived, holdout, development, split_loaded, missing)
    links = _links(paths.links, missing)
    labels = _labels(paths.labels, holdout, missing)
    decisions = _jsonl(paths.relevance, missing)
    human = _jsonl(paths.human_relevance, missing)
    extraction = paths.extraction
    inputs = _jsonl(extraction / "extraction_inputs.jsonl", missing)
    failures = _jsonl(extraction / "extraction_failures.jsonl", missing)
    cases = _jsonl(extraction / "retrieval_cases.jsonl", missing)
    reviews = (
        _jsonl(extraction / "review_queue.jsonl", missing)
        + _jsonl(paths.phase4_reviews, missing)
        + _jsonl(paths.phase3_reviews, missing)
    )
    corrections = _corrections(paths.corrections)
    canonical = _canonical(links)
    approved = {row.case_id for row in corrections if row.field == "semantic_approval"}

    visible_findings = tuple(
        item
        for item in RECORDED_FINDINGS
        if item.doc_id in documents or item.doc_id in {row.get("doc_id") for row in inputs}
    )
    cards = _cards(
        documents,
        audits,
        labels,
        inputs,
        failures,
        cases,
        reviews,
        visible_findings,
        approved,
        canonical,
    )
    dev_ids = [doc_id for doc_id in documents if doc_id in development or not development]
    if development:
        dev_ids = [doc_id for doc_id in documents if doc_id in development]
    analysis_ids = {canonical.get(doc_id, doc_id) for doc_id in dev_ids}
    excluded = _excluded(dev_ids, labels, decisions)
    failed_ids = {
        str(row.get("doc_id"))
        for row in inputs
        if str(row.get("technical_state")) not in {"ok", ""}
    }
    failed_ids.update(str(row.get("doc_id")) for row in failures)
    open_reviews = [row for row in reviews if row.get("state") == "open"]
    valid_cards = [card for card in cards if card.automatically_valid]
    conclusion = [card for card in cards if card.enters_conclusions]
    groups, reason = _groups(conclusion)

    return Snapshot(
        collected=len(dev_ids),
        withheld_holdout=len(holdout),
        excluded=excluded,
        failed=len(failed_ids),
        automatically_valid=len(valid_cards),
        semantically_approved=len(conclusion),
        human_reviewed=sum(1 for doc_id in dev_ids if labels.get(doc_id)),
        unresolved=len(open_reviews),
        collected_records=len(dev_ids),
        analysis_documents=len(analysis_ids),
        confirmed_duplicates=sum(1 for row in links if row.get("review_state") in CONFIRMED),
        pending_duplicates=sum(1 for row in links if row.get("review_state") == "pending_review"),
        cards=tuple(cards),
        core=_compare(CORE, "Core", valid_cards, canonical),
        adjacent=_compare(ADJACENT, "Adjacent", valid_cards, canonical),
        conclusion_cases=len(conclusion),
        groups=groups,
        group_reason=reason,
        corrections=tuple(corrections),
        findings=visible_findings,
        missing=tuple(missing),
    )


def _cards(
    documents: dict[str, dict[str, str]],
    audits: dict[str, str],
    labels: dict[str, str],
    inputs: list[dict[str, object]],
    failures: list[dict[str, object]],
    cases: list[dict[str, object]],
    reviews: list[dict[str, object]],
    findings: tuple[SemanticFinding, ...],
    approved: set[str],
    canonical: dict[str, str],
) -> list[EvidenceCard]:
    by_doc_input = {str(row.get("doc_id")): row for row in inputs}
    failure_docs = {str(row.get("doc_id")) for row in failures}
    case_docs = {str(row.get("doc_id")) for row in cases}
    ordered = sorted(set(documents) | set(by_doc_input) | failure_docs | case_docs)
    cards: list[EvidenceCard] = []
    for doc_id in ordered:
        doc_cases = [row for row in cases if str(row.get("doc_id")) == doc_id]
        doc_findings = tuple(item for item in findings if item.doc_id == doc_id)
        if not doc_cases:
            cards.append(
                _empty_card(
                    doc_id,
                    documents.get(doc_id, {}),
                    audits.get(doc_id, ""),
                    labels.get(doc_id, ""),
                    by_doc_input.get(doc_id, {}),
                    doc_id in failure_docs,
                    doc_findings,
                    reviews,
                )
            )
            continue
        for case in doc_cases:
            cards.append(
                _case_card(
                    case,
                    documents.get(doc_id, {}),
                    audits.get(doc_id, ""),
                    labels.get(doc_id, ""),
                    doc_findings,
                    reviews,
                    approved,
                    canonical,
                )
            )
    return cards


def _case_card(
    case: dict[str, object],
    document: dict[str, str],
    audit: str,
    human_scope: str,
    findings: tuple[SemanticFinding, ...],
    reviews: list[dict[str, object]],
    approved: set[str],
    canonical: dict[str, str],
) -> EvidenceCard:
    del canonical
    case_id = str(case.get("case_id") or "")
    doc_id = str(case.get("doc_id") or "")
    case_findings = tuple(
        item for item in findings if item.case_id in {None, case_id}
    )
    spans = _spans(case)
    excerpt, start, highlights, quotes = _excerpt(audit, spans)
    automatically_valid = str(case.get("validation_state")) == "valid"
    enters = automatically_valid and case_id in approved and not case_findings
    status = _review_status(doc_id, case_id, reviews, automatically_valid, case_findings, enters)
    return EvidenceCard(
        doc_id=doc_id,
        case_id=case_id,
        scope_class=str(case.get("scope_class") or ""),
        human_scope=human_scope,
        source_platform=document.get("source_platform", ""),
        source_url=document.get("source_url", ""),
        excerpt=excerpt,
        excerpt_start=start,
        highlights=highlights,
        values=_values(case),
        quotes=quotes,
        review_status=status,
        automatically_valid=automatically_valid,
        findings=case_findings,
        enters_conclusions=enters,
    )


def _empty_card(
    doc_id: str,
    document: dict[str, str],
    audit: str,
    human_scope: str,
    extraction_input: dict[str, object],
    failed: bool,
    findings: tuple[SemanticFinding, ...],
    reviews: list[dict[str, object]],
) -> EvidenceCard:
    state = str(extraction_input.get("technical_state") or "")
    scope = str(extraction_input.get("scope_class") or "")
    excerpt = audit[:EXCERPT_CAP] if audit else ""
    status = "failed" if failed or (state and state != "ok") else "no stored case"
    if findings:
        status = "unresolved"
    return EvidenceCard(
        doc_id=doc_id,
        case_id=None,
        scope_class=scope,
        human_scope=human_scope,
        source_platform=document.get("source_platform", ""),
        source_url=document.get("source_url", ""),
        excerpt=excerpt,
        excerpt_start=0,
        highlights=(),
        values=(),
        quotes=(),
        review_status=_review_status(doc_id, None, reviews, False, findings, False) or status,
        automatically_valid=False,
        findings=findings,
        enters_conclusions=False,
    )


def _review_status(
    doc_id: str,
    case_id: str | None,
    reviews: list[dict[str, object]],
    automatically_valid: bool,
    findings: tuple[SemanticFinding, ...],
    enters: bool,
) -> str:
    open_rows = [
        row
        for row in reviews
        if row.get("state") == "open" and _review_targets(row, doc_id, case_id)
    ]
    parts: list[str] = []
    if automatically_valid:
        parts.append("automatically valid; not semantically approved")
    if enters:
        parts = ["semantically approved by a recorded human correction"]
    if findings:
        parts.append("semantic findings remain open")
    if open_rows:
        reasons = ", ".join(sorted({str(row.get("reason_code")) for row in open_rows}))
        parts.append(f"unresolved review ({reasons})")
    return "; ".join(parts) if parts else "not in this extraction run"


def _review_targets(row: dict[str, object], doc_id: str, case_id: str | None) -> bool:
    target = str(row.get("target_id") or "")
    if case_id is not None and target == case_id:
        return True
    tokens = set(target.replace(":", " ").replace("#", " ").split())
    return doc_id in tokens


def _values(case: dict[str, object]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for name in (
        "target_asset_type",
        "retrieval_trigger",
        "outcome",
        "severity",
        "problem_summary",
    ):
        observation = str(case.get(f"{name}_observation") or "")
        value = case.get(name)
        if value not in (None, "", [], ()):
            rows.append((name, f"{value} ({observation or 'stored'})"))
    for name in (
        "remembered_cues",
        "query_strategies",
        "system_responses",
        "impact_signals",
    ):
        labels = case.get(name) or []
        if isinstance(labels, list) and labels:
            rendered = ", ".join(_label_value(item) for item in labels)
            observation = str(case.get(f"{name}_observation") or "stored")
            rows.append((name, f"{rendered} ({observation})"))
    return tuple(rows)


def _label_value(item: object) -> str:
    if isinstance(item, dict):
        value = item.get("value")
        if isinstance(value, dict):
            return str(value.get("value") or value)
        return str(value)
    return str(item)


def _spans(case: dict[str, object]) -> list[dict[str, object]]:
    spans = case.get("all_evidence_spans") or []
    if not isinstance(spans, list):
        return []
    return [span for span in spans if isinstance(span, dict)]


def _excerpt(
    audit: str, spans: list[dict[str, object]]
) -> tuple[str, int, tuple[tuple[int, int], ...], tuple[QuoteView, ...]]:
    located: list[tuple[int, int, dict[str, object]]] = []
    quotes: list[QuoteView] = []
    for span in spans:
        start = span.get("start_char")
        end = span.get("end_char")
        quote = str(span.get("quote") or "")
        field_name = str(span.get("field_name") or "")
        state = str(span.get("validation_state") or "")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            quotes.append(QuoteView(field_name, quote, state, False))
            continue
        slice_text = audit[start:end] if audit else ""
        matches = bool(audit) and slice_text == quote
        quotes.append(QuoteView(field_name, slice_text or quote, state, matches))
        if matches:
            located.append((start, end, span))
    if not audit:
        return "", 0, (), tuple(quotes)
    if not located:
        return audit[:EXCERPT_CAP], 0, (), tuple(quotes)
    origin = max(0, min(start for start, _, _ in located) - CONTEXT)
    stop = min(len(audit), max(end for _, end, _ in located) + CONTEXT)
    excerpt = audit[origin:stop]
    highlights = tuple((start - origin, end - origin) for start, end, _ in located)
    return excerpt, origin, highlights, tuple(quotes)


def _compare(
    scope: str,
    label: str,
    cards: list[EvidenceCard],
    canonical: dict[str, str],
) -> ScopeComparison:
    chosen = [card for card in cards if card.scope_class == scope and card.automatically_valid]
    if not chosen:
        return ScopeComparison(
            scope, label, 0, (), (), (), (), (), (),
            f"No automatically valid {label.lower()} case is stored.",
        )
    return ScopeComparison(
        scope_class=scope,
        label=label,
        model_cases=len(chosen),
        targets=_count(chosen, "target_asset_type"),
        cues=_count(chosen, "remembered_cues"),
        strategies=_count(chosen, "query_strategies"),
        responses=_count(chosen, "system_responses"),
        outcomes=_count(chosen, "outcome"),
        sources=_sources(chosen, canonical),
        empty_reason="",
    )


def _count(cards: list[EvidenceCard], field_name: str) -> tuple[tuple[str, int], ...]:
    counter: Counter[str] = Counter()
    for card in cards:
        for name, value in card.values:
            if name != field_name:
                continue
            raw = value.rsplit(" (", 1)[0]
            for part in raw.split(", "):
                if part:
                    counter[part] += 1
    return tuple(counter.most_common())


def _sources(cards: list[EvidenceCard], canonical: dict[str, str]) -> tuple[tuple[str, int], ...]:
    seen: set[str] = set()
    counter: Counter[str] = Counter()
    for card in cards:
        doc_id = canonical.get(card.doc_id, card.doc_id)
        if doc_id in seen:
            continue
        seen.add(doc_id)
        counter[card.source_platform or "unknown"] += 1
    return tuple(counter.most_common())


def _groups(conclusion: list[EvidenceCard]) -> tuple[tuple[ProvisionalGroup, ...], str]:
    if not conclusion:
        return (), (
            "No extraction case is semantically approved, so no provisional "
            "problem group is proposed."
        )
    buckets: dict[str, list[str]] = {}
    for card in conclusion:
        asset = next((value for name, value in card.values if name == "target_asset_type"), "unstated asset")
        outcome = next((value for name, value in card.values if name == "outcome"), "unstated outcome")
        label = f"provisional: {asset.split(' (', 1)[0]} / {outcome.split(' (', 1)[0]}"
        buckets.setdefault(label, []).append(card.case_id or card.doc_id)
    groups = tuple(
        ProvisionalGroup(label, tuple(case_ids))
        for label, case_ids in sorted(buckets.items())
    )
    return groups, "Grouped only from cases with a recorded semantic approval. Provisional."


def _excluded(
    doc_ids: list[str],
    labels: dict[str, str],
    decisions: list[dict[str, object]],
) -> int:
    model_scope = {
        str(row.get("doc_id")): str(row.get("scope_class") or "")
        for row in decisions
        if row.get("technical_state") == "ok"
    }
    count = 0
    for doc_id in doc_ids:
        scope = labels.get(doc_id) or model_scope.get(doc_id, "")
        if scope == OUT:
            count += 1
    return count


def _canonical(links: list[dict[str, object]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in links:
        if row.get("review_state") not in CONFIRMED:
            continue
        doc_id = str(row.get("doc_id") or "")
        canonical = str(row.get("canonical_doc_id") or "")
        if doc_id and canonical:
            mapping[doc_id] = canonical
    return mapping


def _split(path: Path, missing: list[str]) -> dict[str, str]:
    if not path.is_file():
        missing.append(str(path))
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["doc_id"]: row["split"]
            for row in csv.DictReader(handle)
            if row.get("doc_id") and row.get("split")
        }


def _documents(
    path: Path,
    holdout: set[str],
    development: set[str],
    split_loaded: bool,
    missing: list[str],
) -> dict[str, dict[str, str]]:
    if not split_loaded:
        return {}
    rows = _jsonl(path, missing)
    kept: dict[str, dict[str, str]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "")
        if not doc_id or doc_id in holdout:
            continue
        if development and doc_id not in development:
            continue
        kept[doc_id] = {
            "source_platform": str(row.get("source_platform") or ""),
            "source_url": str(row.get("source_url") or ""),
            "source_type": str(row.get("source_type") or ""),
        }
    return kept


def _audits(
    path: Path,
    holdout: set[str],
    development: set[str],
    split_loaded: bool,
    missing: list[str],
) -> dict[str, str]:
    if not split_loaded:
        return {}
    kept: dict[str, str] = {}
    for row in _jsonl(path, missing):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id or doc_id in holdout:
            continue
        if development and doc_id not in development:
            continue
        audit = row.get("raw_text_audit")
        if isinstance(audit, str):
            kept[doc_id] = audit
    return kept


def _labels(path: Path, holdout: set[str], missing: list[str]) -> dict[str, str]:
    if not path.is_file():
        missing.append(str(path))
        return {}
    kept: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row.get("doc_id") or ""
            if not doc_id or doc_id in holdout:
                continue
            scope = (row.get("human_scope_class") or "").strip()
            if scope:
                kept[doc_id] = scope
    return kept


def _links(path: Path, missing: list[str]) -> list[dict[str, object]]:
    return _jsonl(path, missing)


def _corrections(path: Path) -> list[Correction]:
    if not path.is_file():
        return []
    rows: list[Correction] = []
    for row in _jsonl(path, []):
        rows.append(
            Correction(
                case_id=str(row.get("case_id") or ""),
                field=str(row.get("field") or ""),
                original_value=str(row.get("original_value") or ""),
                corrected_value=str(row.get("corrected_value") or ""),
                reviewer=str(row.get("reviewer") or ""),
                note=str(row.get("note") or ""),
            )
        )
    return rows


def _jsonl(path: Path, missing: list[str]) -> list[dict[str, object]]:
    if not path.is_file():
        missing.append(str(path))
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows
