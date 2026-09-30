"""Phase 4 seed-split governance, holdout lock, and the development smoke run."""

from __future__ import annotations

import ast
import csv
import inspect
import json
import socket
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.core.ids import raw_text_sha256, source_url_key
from src.llm.cache import ResponseCache
from src.llm.gateway import ModelGateway, ProviderBudgetError
from src.llm.providers.base import ProviderResponse
from src.models.enums import DecisionTechnicalState, ReasonCode, ScopeClass
from src.normalize.derive import derive_document
from src.pipeline.smoke_run import SmokeRunError, plan_smoke_run, run_smoke
from src.pipeline.stages import PHASE_INSTANT
from src.relevance.evaluate import evaluate_relevance
from src.relevance.lock import (
    HoldoutLocked,
    authorize_live_classification,
    build_prompt_lock,
    write_prompt_lock,
)
from src.relevance.smoke import (
    FORBIDDEN_SMOKE_COLUMNS,
    SMOKE_CALL_BUDGET,
    SmokeSelectionError,
    select_smoke_ids,
    write_smoke_manifest,
)
from src.relevance.split import (
    DEVELOPMENT_COUNTS,
    HOLDOUT_COUNTS,
    PHASE6_GOLD_SPLIT,
    SEED_SPLIT_ROLE,
    SPLIT_VERSION,
    SplitAssignment,
    assign_split,
)
from tests.synthetic import make_decision, make_document

ROOT = Path(__file__).resolve().parents[1]


class _Echo(BaseModel):
    ok: bool = True


class _Provider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def complete_structured(self, prompt, schema, params):
        self.calls += 1
        return ProviderResponse(
            text='{"ok": true}',
            input_tokens=1,
            output_tokens=1,
            model=params.model,
            provider=self.provider_name,
        )


def _assignment(doc_id: str, split: str, stratum: str) -> SplitAssignment:
    return SplitAssignment(doc_id=doc_id, split=split, stratum=stratum)


def _development_pool() -> tuple[SplitAssignment, ...]:
    rows = []
    rows.extend(
        _assignment(f"core-{index:02d}", "development", "core_incomplete_recall")
        for index in range(3)
    )
    rows.extend(
        _assignment(f"adjacent-{index:02d}", "development", "adjacent_known_item_retrieval")
        for index in range(3)
    )
    rows.extend(
        _assignment(f"out-{index:02d}", "development", "out_of_scope") for index in range(3)
    )
    rows.append(_assignment("holdout-core", "holdout", "core_incomplete_recall"))
    return tuple(rows)


def test_phase4_seed_split_is_not_the_phase6_gold_split() -> None:
    assert SEED_SPLIT_ROLE == "phase4-prompt-development"
    assert SPLIT_VERSION == "relevance-seed-split/v1"
    assert sum(DEVELOPMENT_COUNTS.values()) == 35
    assert sum(HOLDOUT_COUNTS.values()) == 15
    assert PHASE6_GOLD_SPLIT["method"] == "hash(doc_id)"
    assert PHASE6_GOLD_SPLIT["development_fraction"] == 0.4
    assert PHASE6_GOLD_SPLIT["holdout_fraction"] == 0.6
    assert PHASE6_GOLD_SPLIT["strata"] == ("source_platform", "scope_class")
    assert PHASE6_GOLD_SPLIT["role"] == "final-product-performance"
    source = inspect.getsource(assign_split)
    assert "hashlib" not in source
    assert "source_platform" not in source


def test_overall_accuracy_keeps_abstentions_and_covered_metrics_exclude_them() -> None:
    from src.relevance.seed import SeedRow

    def label(doc_id: str, scope: str, reason: str) -> SeedRow:
        return SeedRow(
            doc_id=doc_id,
            source_platform="reddit",
            source_type="post",
            title=doc_id,
            privacy_safe_excerpt="excerpt",
            prefilter_route="classify",
            prefilter_reason_codes="retained_for_recall",
            human_scope_class=scope,
            human_reason_code=reason,
            human_notes="note",
        )

    labels = (
        label("doc-hit", "core_incomplete_recall", "known_item_with_incomplete_recall"),
        label("doc-failed", "core_incomplete_recall", "known_item_query_unformulable"),
        label("doc-missing", "adjacent_known_item_retrieval", "known_item_with_precise_recall_failure"),
    )
    assignments = tuple(
        _assignment(row.doc_id, "development", row.human_scope_class) for row in labels
    )
    hit = make_decision(doc_id="doc-hit", decision_id="decision-hit", evidence=_span("doc-hit", "decision-hit"))
    failed = make_decision(
        doc_id="doc-failed",
        decision_id="decision-failed",
        scope_class=None,
        reason_code=ReasonCode.provider_unavailable,
        confidence=None,
        evidence=(),
        technical_state=DecisionTechnicalState.provider_unavailable,
        needs_human_review=True,
    )
    report = evaluate_relevance(
        labels,
        (hit, failed),
        assignments,
        split_name="development",
    )
    assert report.document_count == 3
    assert report.missing_doc_ids == ("doc-missing",)
    assert report.overall_exact_scope_accuracy == pytest.approx(1 / 3, abs=1e-6)
    assert report.covered_only_exact_scope_accuracy == 1.0
    assert report.confusion["core_incomplete_recall"]["core_incomplete_recall"] == 1
    assert report.confusion["core_incomplete_recall"]["abstained"] == 1
    assert report.confusion["core_incomplete_recall"]["out_of_scope"] == 0
    assert report.per_class["core_incomplete_recall"].recall == 1.0
    assert report.per_class["core_incomplete_recall"].predicted == 1
    assert report.technical_failure_rate == pytest.approx(1 / 3, abs=1e-6)
    assert report.abstention_rate == pytest.approx(2 / 3, abs=1e-6)


def test_smoke_selection_is_two_per_class_and_hides_labels(tmp_path: Path) -> None:
    pool = _development_pool()
    first = select_smoke_ids(tuple(reversed(pool)))
    second = select_smoke_ids(pool)
    assert first == second
    assert first == (
        "adjacent-00",
        "adjacent-01",
        "core-00",
        "core-01",
        "out-00",
        "out-01",
    )
    path = tmp_path / "relevance_smoke_manifest.csv"
    write_smoke_manifest(path, pool)
    original = path.read_bytes()
    write_smoke_manifest(path, pool)
    assert path.read_bytes() == original
    header = original.decode("utf-8").splitlines()[0].split(",")
    assert FORBIDDEN_SMOKE_COLUMNS.isdisjoint(header)
    assert "human_scope_class" not in original.decode("utf-8")
    assert "human_notes" not in original.decode("utf-8")
    stored = list(csv.DictReader(original.decode("utf-8").splitlines()))
    assert [row["doc_id"] for row in stored] == list(first)
    assert {row["split"] for row in stored} == {"development"}

    swapped = original.decode("utf-8").replace("core-00", "core-02", 1)
    path.write_bytes(swapped.encode("utf-8"))
    preserved = path.read_bytes()
    write_smoke_manifest(path, pool)
    assert path.read_bytes() == preserved


def test_holdout_classification_requires_a_matching_prompt_lock(tmp_path: Path) -> None:
    assert (
        authorize_live_classification(
            split_name="development",
            holdout_unlocked=False,
            lock_path=None,
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
        )
        == "development"
    )
    with pytest.raises(HoldoutLocked, match="holdout unlock"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=False,
            lock_path=tmp_path / "missing.json",
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
        )
    with pytest.raises(HoldoutLocked, match="prompt-lock"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=True,
            lock_path=tmp_path / "missing.json",
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
        )
    lock = build_prompt_lock(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
    )
    lock["human_notes"] = "a private note"
    poisoned = tmp_path / "poisoned.json"
    poisoned.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(HoldoutLocked, match="label or text"):
        authorize_live_classification(
            split_name="all",
            holdout_unlocked=True,
            lock_path=poisoned,
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
        )
    clean = tmp_path / "lock.json"
    write_prompt_lock(clean, build_prompt_lock(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
    ))
    body = clean.read_text(encoding="utf-8")
    assert "human_notes" not in body
    assert "privacy_safe_excerpt" not in body
    assert authorize_live_classification(
        split_name="holdout",
        holdout_unlocked=True,
        lock_path=clean,
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
    ) == "holdout"


def test_smoke_budget_membership_dry_run_and_historical_isolation(tmp_path: Path) -> None:
    pool = _development_pool()
    selected = select_smoke_ids(pool)
    historical = tmp_path / "phase4"
    historical.mkdir()
    decisions = historical / "relevance_decisions.jsonl"
    decisions.write_text('{"doc_id":"old-null"}\n', encoding="utf-8")
    original = decisions.read_bytes()
    provider = _Provider()
    plan = run_smoke(
        [],
        [],
        [],
        pool,
        selected,
        output_parent=tmp_path / "smoke",
        historical_dir=historical,
        cache_dir=tmp_path / "cache",
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
        dry_run=True,
        provider_instance=provider,
    )
    assert provider.calls == 0
    assert plan.provider_calls == 0
    assert plan.call_budget == SMOKE_CALL_BUDGET
    assert not plan.output_dir.exists()
    assert decisions.read_bytes() == original
    other = plan_smoke_run(
        selected,
        pool,
        output_parent=tmp_path / "smoke",
        historical_dir=historical,
        cache_dir=tmp_path / "cache",
        provider="anthropic",
        model="other-model",
        temperature=0.0,
        max_tokens=4096,
        dry_run=True,
    )
    assert plan.output_dir != other.output_dir
    assert plan.output_dir != historical
    assert other.output_dir != historical

    with pytest.raises(SmokeSelectionError, match="more than 6"):
        run_smoke(
            [],
            [],
            [],
            pool,
            selected + ("core-02",),
            output_parent=tmp_path / "smoke",
            historical_dir=historical,
            cache_dir=tmp_path / "cache",
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
            dry_run=True,
            provider_instance=provider,
        )
    assert provider.calls == 0
    outside = ("holdout-core",) + selected[1:]
    with pytest.raises(SmokeSelectionError, match="outside the development split"):
        run_smoke(
            [],
            [],
            [],
            pool,
            outside,
            output_parent=tmp_path / "smoke",
            historical_dir=historical,
            cache_dir=tmp_path / "cache",
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
            dry_run=True,
            provider_instance=provider,
        )
    assert provider.calls == 0
    occupied = plan_smoke_run(
        selected,
        pool,
        output_parent=tmp_path / "occupied",
        historical_dir=historical,
        cache_dir=tmp_path / "cache",
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
        dry_run=False,
    )
    occupied.output_dir.mkdir(parents=True)
    (occupied.output_dir / "relevance_decisions.jsonl").write_text(
        '{"doc_id":"already"}\n',
        encoding="utf-8",
    )
    with pytest.raises(SmokeRunError, match="refusing to merge"):
        plan_smoke_run(
            selected,
            pool,
            output_parent=tmp_path / "occupied",
            historical_dir=historical,
            cache_dir=tmp_path / "cache",
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.0,
            max_tokens=4096,
            dry_run=False,
        )
    assert decisions.read_bytes() == original


def test_smoke_decisions_are_written_beside_the_historical_run(tmp_path: Path) -> None:
    pool = _development_pool()
    selected = select_smoke_ids(pool)
    historical = tmp_path / "phase4"
    historical.mkdir()
    decisions = historical / "relevance_decisions.jsonl"
    decisions.write_text('{"doc_id":"old-null"}\n', encoding="utf-8")
    original = decisions.read_bytes()
    documents = []
    derived = []
    for doc_id in selected:
        text = f"Hello from the park [{doc_id}]"
        url = f"https://www.reddit.com/r/googlephotos/comments/{doc_id}/"
        document = make_document(
            doc_id=doc_id,
            title="A public title",
            raw_text=text,
            raw_text_sha256=raw_text_sha256(text),
            source_url=url,
            source_url_key=source_url_key(url),
            source_item_id=doc_id,
            author_hash="cafebabecafebabe",
        )
        documents.append(document)
        derived.append(derive_document(document, derived_at=PHASE_INSTANT))
    quote = "Hello from the park"
    provider = _JsonProvider(
        selected,
        quote,
        {row.doc_id: row.raw_text_audit.index(quote) for row in derived},
    )
    finished = run_smoke(
        documents,
        derived,
        [],
        pool,
        selected,
        output_parent=tmp_path / "smoke",
        historical_dir=historical,
        cache_dir=tmp_path / "cache",
        provider="fake",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=4096,
        dry_run=False,
        provider_instance=provider,
        project_root=tmp_path,
    )
    assert provider.calls == 6
    assert finished.provider_calls == 6
    written = finished.output_dir / "relevance_decisions.jsonl"
    assert written.is_file()
    assert written.resolve() != decisions.resolve()
    assert decisions.read_bytes() == original
    stored = [
        json.loads(line)
        for line in written.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {row["doc_id"] for row in stored} == set(selected)
    assert "old-null" not in written.read_text(encoding="utf-8")
    record = json.loads((finished.output_dir / "smoke_run.json").read_text(encoding="utf-8"))
    assert record["prompt_id"] == "relevance"
    assert record["prompt_version"] == "relevance/v4"
    assert record["call_budget"] == 6
    assert record["provider_calls"] == 6
    assert "human_notes" not in json.dumps(record)
    assert "human_scope_class" not in "\n".join(provider.prompts)
    assert "human_notes" not in "\n".join(provider.prompts)


def test_provider_budget_stops_before_the_seventh_call(tmp_path: Path) -> None:
    provider = _Provider()
    gateway = ModelGateway(
        provider,
        ResponseCache(tmp_path / "cache"),
        provider_name="fake",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=32,
        timeout_seconds=1,
        max_retries=1,
        input_usd_per_million=0,
        output_usd_per_million=0,
        call_budget=6,
    )
    for index in range(6):
        gateway.complete(
            prompt="classify",
            schema={"type": "object"},
            response_model=_Echo,
            content_hash=f"hash-{index}",
            prompt_id="relevance",
            prompt_version="relevance/v1",
        )
    with pytest.raises(ProviderBudgetError):
        gateway.complete(
            prompt="classify",
            schema={"type": "object"},
            response_model=_Echo,
            content_hash="hash-6",
            prompt_id="relevance",
            prompt_version="relevance/v1",
        )
    assert provider.calls == 6


def test_smoke_dry_run_command_makes_no_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("live network call")

    monkeypatch.setattr(socket, "create_connection", blocked)
    from src.relevance.seed import SeedRow, write_seed_review
    from src.relevance.split import ensure_split_manifest

    rows = []
    for index in range(12):
        rows.append(_seed(f"core-{index:02d}", "core_incomplete_recall", "known_item_with_incomplete_recall"))
    for index in range(14):
        rows.append(
            _seed(
                f"adjacent-{index:02d}",
                "adjacent_known_item_retrieval",
                "known_item_with_precise_recall_failure",
            )
        )
    for index in range(24):
        rows.append(_seed(f"out-{index:02d}", "out_of_scope", "storage_backup_or_sync"))
    seed = tmp_path / "relevance_seed_review.csv"
    write_seed_review(seed, rows)
    manifest = tmp_path / "relevance_split_manifest.csv"
    ensure_split_manifest(manifest, seed)
    from main import main

    code = main(
        [
            "smoke",
            "--dry-run",
            "--manifest",
            str(tmp_path / "relevance_smoke_manifest.csv"),
            "--split-manifest",
            str(manifest),
            "--output",
            str(tmp_path / "smoke"),
            "--historical",
            str(tmp_path / "phase4"),
            "--cache",
            str(tmp_path / "cache"),
        ]
    )
    assert code == 0
    smoke = (tmp_path / "relevance_smoke_manifest.csv").read_text(encoding="utf-8")
    assert "human_scope_class" not in smoke
    tree = ast.parse((ROOT / "src/relevance/smoke.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("src.llm") for name in imported)


def _seed(doc_id: str, scope: str, reason: str) -> "SeedRow":
    from src.relevance.seed import SeedRow

    return SeedRow(
        doc_id=doc_id,
        source_platform="reddit",
        source_type="post",
        title=doc_id,
        privacy_safe_excerpt="excerpt",
        prefilter_route="classify",
        prefilter_reason_codes="retained_for_recall",
        human_scope_class=scope,
        human_reason_code=reason,
        human_notes="note",
    )


def _span(doc_id: str, decision_id: str):
    from src.models.enums import EvidenceOwnerType
    from tests.synthetic import make_span

    return (
        make_span(
            "scope_class",
            "I could not remember the exact date",
            owner_id=decision_id,
            owner_type=EvidenceOwnerType.relevance_decision,
            doc_id=doc_id,
        ),
    )


class _JsonProvider:
    provider_name = "fake"

    def __init__(self, doc_ids: tuple[str, ...], quote: str, starts: dict[str, int]) -> None:
        self.doc_ids = doc_ids
        self.quote = quote
        self.starts = starts
        self.calls = 0
        self.prompts: list[str] = []

    def complete_structured(self, prompt, schema, params):
        doc_id = self.doc_ids[self.calls]
        self.calls += 1
        self.prompts.append(prompt)
        start = self.starts[doc_id]
        body = {
            "doc_id": doc_id,
            "scope_class": "core_incomplete_recall",
            "reason_code": "known_item_with_incomplete_recall",
            "reason_summary": "A remembered photo could not be retrieved.",
            "confidence": 0.9,
            "evidence": {
                "quote": self.quote,
                "start_char": start,
                "end_char": start + len(self.quote),
            },
        }
        return ProviderResponse(
            text=json.dumps(body),
            input_tokens=3,
            output_tokens=2,
            model=params.model,
            provider=self.provider_name,
        )
