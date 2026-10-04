"""Bounded research-batch planning. No test makes a provider call."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import main
from src.core.config import load_settings
from src.core.ids import author_hash, author_salt_id, doc_id, raw_text_sha256, source_url_key
from src.models.collected_document import CollectedDocument
from src.models.enums import CollectionMethod, EvidenceTier, SourcePlatform, SourceType
from src.pipeline.research_batch import (
    REVIEW_CHECKLIST,
    ResearchBatchError,
    plan_research_batch,
)

SALT = "batch-test-salt"
TEXT = "I cannot find the photo of the birthday cake from last summer."
WHEN = datetime(2026, 10, 1, tzinfo=UTC)


def _document(item: str, *, text: str = TEXT, tier: EvidenceTier = EvidenceTier.synthetic_test) -> CollectedDocument:
    platform = SourcePlatform.youtube.value
    url = f"https://www.youtube.com/watch?v=abcdefghijk&lc={item}"
    return CollectedDocument(
        doc_id=doc_id(platform, source_item_id=item),
        ingest_batch_id="batch-test",
        source_platform=SourcePlatform.youtube,
        source_type=SourceType.video_comment,
        evidence_tier=tier,
        source_item_id=item,
        parent_thread_id="thread-test",
        source_url=url,  # type: ignore[arg-type]
        source_url_key=source_url_key(url),
        source_name="YouTube",
        author_hash=author_hash(SALT, platform, "UCchanneltest"),
        author_salt_id=author_salt_id(SALT),
        published_at=WHEN,
        collected_at=WHEN,
        raw_text=text,
        raw_text_sha256=raw_text_sha256(text),
        collection_query=url,
        collection_method=CollectionMethod.api,
        metadata={"video_id": "abcdefghijk", "replies_complete": True},
    )


def _write(path: Path, documents: list[CollectedDocument]) -> None:
    path.write_text(
        "".join(document.model_dump_json() + "\n" for document in documents),
        encoding="utf-8",
    )


def _split(path: Path, doc_ids: list[str]) -> None:
    lines = ["doc_id,split,stratum,split_version"]
    lines.extend(f"{doc_id},development,core_incomplete_recall,relevance-seed-split/v1" for doc_id in doc_ids)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plan(tmp_path: Path, documents: list[CollectedDocument], **kwargs: object):
    source = tmp_path / "collected_documents.jsonl"
    _write(source, documents)
    split = tmp_path / "split.csv"
    _split(split, list(kwargs.get("frozen", [])))
    settings = load_settings()
    return plan_research_batch(
        source,
        tmp_path / "out",
        document_limit=int(kwargs.get("limit", 20)),
        dedupe_config=settings.analysis.dedupe,
        frozen_split=split,
        allow_synthetic=bool(kwargs.get("allow_synthetic", True)),
    )


@pytest.mark.synthetic
def test_dry_plan_reuses_stages_and_makes_no_call(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [_document("comment-new")])

    assert plan.selected == 1
    assert plan.excluded_frozen == 0
    assert plan.provider_calls == 0
    assert plan.files_written == 0
    assert plan.relevance_requests == plan.prefilter_classify
    assert plan.extraction_request_ceiling == plan.prefilter_classify
    assert plan.relevance_requests <= 20
    assert not (tmp_path / "out").exists()
    assert "retrieval_trigger" in REVIEW_CHECKLIST[0]
    assert "spliced" in REVIEW_CHECKLIST[3]


@pytest.mark.synthetic
def test_frozen_split_documents_are_excluded(tmp_path: Path) -> None:
    document = _document("comment-frozen")
    plan = _plan(tmp_path, [document], frozen=[document.doc_id])

    assert plan.selected == 0
    assert plan.excluded_frozen == 1
    assert plan.provider_calls == 0


@pytest.mark.synthetic
def test_provenance_failure_selects_nothing(tmp_path: Path) -> None:
    document = _document("comment-bad")
    broken = document.model_copy(update={"raw_text_sha256": "a" * 64})
    plan = _plan(tmp_path, [broken])

    assert plan.selected == 0
    assert plan.provenance_failures[0].reasons == ("raw_text_sha256",)
    assert plan.provider_calls == 0


@pytest.mark.synthetic
def test_document_limit_caps_the_batch_at_twenty(tmp_path: Path) -> None:
    documents = [_document(f"comment-{index:02d}") for index in range(21)]
    plan = _plan(tmp_path, documents, limit=20)

    assert plan.selected == 20
    assert plan.held_back == 1
    with pytest.raises(ResearchBatchError, match="20"):
        _plan(tmp_path, documents, limit=21)


@pytest.mark.synthetic
def test_output_inside_phase5_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "collected_documents.jsonl"
    _write(source, [_document("comment-new")])
    with pytest.raises(ResearchBatchError, match="frozen"):
        plan_research_batch(
            source,
            Path("data/interim/phase5/research-batch"),
            document_limit=20,
            dedupe_config=load_settings().analysis.dedupe,
            frozen_split=tmp_path / "missing-split-not-read.csv",
            allow_synthetic=True,
        )


@pytest.mark.synthetic
def test_cli_dry_run_rejects_pilot_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "collected_documents.jsonl"
    _write(source, [_document("comment-cli", tier=EvidenceTier.synthetic_test)])
    output = tmp_path / "batch-out"
    code = main.main(
        [
            "run",
            "--research-batch",
            "--stages",
            "normalize,dedupe,prefilter,relevance,extract",
            "--input",
            str(source),
            "--output",
            str(output),
            "--document-limit",
            "20",
            "--dry-run",
            "--pilot",
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "pilot" in captured.err
    assert not output.exists()


@pytest.mark.synthetic
def test_cli_dry_run_on_new_document_makes_no_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "collected_documents.jsonl"
    _write(source, [_document("comment-live-shape", tier=EvidenceTier.direct_user)])
    output = tmp_path / "batch-out"
    before = Path("data/interim/phase4/relevance_split_manifest.csv").read_bytes()
    code = main.main(
        [
            "run",
            "--research-batch",
            "--stages",
            "normalize,dedupe,prefilter,relevance,extract",
            "--input",
            str(source),
            "--output",
            str(output),
            "--document-limit",
            "20",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "provider calls       0" in captured.out
    assert "files written        0" in captured.out
    assert "Semantic review checklist" in captured.out
    assert "retrieval_trigger" in captured.out
    assert not output.exists()
    assert Path("data/interim/phase4/relevance_split_manifest.csv").read_bytes() == before
    assert "comment-live-shape" not in captured.out
    json.loads(source.read_text(encoding="utf-8"))


@pytest.mark.synthetic
def test_cli_rejects_synthetic_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "collected_documents.jsonl"
    _write(source, [_document("comment-synthetic")])
    output = tmp_path / "batch-out"
    code = main.main(
        [
            "run",
            "--research-batch",
            "--stages",
            "normalize,dedupe,prefilter,relevance,extract",
            "--input",
            str(source),
            "--output",
            str(output),
            "--document-limit",
            "20",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "synthetic_test" in captured.out
    assert "provider calls       0" in captured.out
    assert not output.exists()


@pytest.mark.synthetic
def test_cli_refuses_holdout_unlock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main.main(
        [
            "run",
            "--research-batch",
            "--stages",
            "normalize,dedupe",
            "--input",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(tmp_path / "out"),
            "--document-limit",
            "20",
            "--holdout-unlock",
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "holdout" in captured.err
    assert not (tmp_path / "out").exists()


def _argv(source: Path, output: Path, stages: str, **extra: str) -> list[str]:
    argv = [
        "run",
        "--research-batch",
        "--stages",
        stages,
        "--input",
        str(source),
        "--output",
        str(output),
        "--document-limit",
        "20",
    ]
    for key, value in extra.items():
        argv.extend([f"--{key.replace('_', '-')}", value])
    return argv


@pytest.mark.synthetic
def test_relevance_budget_mismatch_makes_no_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "collected_documents.jsonl"
    document = _document("comment-budget", tier=EvidenceTier.direct_user)
    _write(source, [document])
    output = tmp_path / "batch-out"
    plan = _plan(tmp_path, [document], limit=20)
    assert plan.relevance_requests >= 1

    def refuse_live(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider call")

    monkeypatch.setattr("src.llm.providers.groq.GroqProvider.complete_structured", refuse_live)
    monkeypatch.setattr("src.pipeline.stages.ModelGateway", refuse_live)
    code = main.main(
        _argv(
            source,
            output,
            "prefilter,relevance",
            call_budget=str(plan.relevance_requests + 1),
            max_retries="1",
            provider="groq",
        )
    )
    captured = capsys.readouterr()

    assert code == 1
    assert str(plan.relevance_requests) in captured.err
    assert not (output / "relevance").exists()


@pytest.mark.synthetic
def test_fake_relevance_and_extraction_stay_inside_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.llm.gateway import GatewayResult, UsageTotals
    from src.models.enums import DecisionTechnicalState, EvidenceOwnerType, ValidationState
    from src.pipeline.extraction_pilot import run_extraction_pilot
    from tests.synthetic import make_decision, make_span

    source = tmp_path / "collected_documents.jsonl"
    document = _document("comment-fake", tier=EvidenceTier.direct_user)
    _write(source, [document])
    output = tmp_path / "batch-out"
    plan = _plan(tmp_path, [document])
    assert plan.relevance_requests == 1

    calls: list[int] = []

    class CountingGateway:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            self.call_budget = kwargs.get("call_budget")
            self.provider_name = kwargs.get("provider_name", "groq")
            self.max_tokens = kwargs.get("max_tokens", 4096)
            self.temperature = kwargs.get("temperature", 0.0)
            self.usage = UsageTotals()
            self.denylist = ()
            self.calls = 0

        def complete(self, **_kwargs: object) -> GatewayResult:
            self.calls += 1
            calls.append(self.calls)
            budget = self.call_budget if isinstance(self.call_budget, int) else 0
            if self.calls > budget:
                raise AssertionError("provider call budget exceeded")
            self.usage.provider_calls += 1
            return GatewayResult(
                technical_state=DecisionTechnicalState.provider_error,
                message="mocked",
                provider_calls=1,
            )

    def refuse_pilot(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("five-seat pilot")

    def refuse_live(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("live provider")

    monkeypatch.setattr(main, "_relevance_runtime", lambda _settings, _override: (
        "groq",
        "openai/gpt-oss-120b",
        "GROQ_API_KEY",
        "test-key-not-sent",
    ))
    monkeypatch.setattr("src.llm.providers.groq.GroqProvider.complete_structured", refuse_live)
    monkeypatch.setattr("src.pipeline.stages.ModelGateway", CountingGateway)
    monkeypatch.setattr("src.pipeline.extraction.ModelGateway", CountingGateway)
    monkeypatch.setattr("src.pipeline.extraction_pilot.run_extraction_pilot", refuse_pilot)
    assert run_extraction_pilot is not None

    normalize_code = main.main(_argv(source, output, "normalize,dedupe"))
    assert normalize_code == 0
    relevance_code = main.main(
        _argv(
            source,
            output,
            "prefilter,relevance",
            call_budget="1",
            max_retries="1",
            provider="groq",
            cache=str(tmp_path / "cache"),
        )
    )
    assert relevance_code == 0
    assert calls == [1]

    decision = make_decision(
        doc_id=document.doc_id,
        decision_id="decision-batch-test",
        validation_state=ValidationState.valid,
        evidence=(
            make_span(
                "scope_class",
                "cannot find the photo",
                owner_id="decision-batch-test",
                owner_type=EvidenceOwnerType.relevance_decision,
                text=TEXT,
                doc_id=document.doc_id,
            ),
        ),
    )
    relevance_dir = output / "relevance"
    (relevance_dir / "relevance_decisions.jsonl").write_text(
        decision.model_dump_json() + "\n",
        encoding="utf-8",
    )
    split_before = Path("data/interim/phase4/relevance_split_manifest.csv").read_bytes()
    five_seat = Path(
        "data/interim/phase4/development/01455c8aab03/extraction_candidate_manifest.csv"
    )
    five_before = five_seat.read_bytes() if five_seat.is_file() else None
    opened: list[str] = []
    real_open = Path.open

    def tracking_open(self: Path, *args: object, **kwargs: object):
        rendered = str(self)
        if "01455c8aab03" in rendered or "extraction_pilot" in rendered:
            opened.append(rendered)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    extract_code = main.main(
        _argv(
            source,
            output,
            "extract",
            call_budget="1",
            max_retries="1",
            provider="groq",
            cache=str(tmp_path / "cache"),
        )
    )
    captured = capsys.readouterr()

    assert extract_code == 1, captured.err
    assert calls == [1, 1]
    saved = {path.name: path.read_bytes() for path in (output / "extract").rglob("*") if path.is_file()}
    repeat_code = main.main(_argv(
        source, output, "extract", call_budget="1", max_retries="1", provider="groq",
        cache=str(tmp_path / "cache"),
    ))
    assert repeat_code == 1
    assert "already exists" in capsys.readouterr().err
    assert calls == [1, 1]
    assert saved == {path.name: path.read_bytes() for path in (output / "extract").rglob("*") if path.is_file()}
    assert opened == []
    assert Path("data/interim/phase4/relevance_split_manifest.csv").read_bytes() == split_before
    if five_before is not None:
        assert five_seat.read_bytes() == five_before
    assert not (Path("data/interim/phase5") / "research-batch").exists()


def test_existing_import_selects_nothing_outside_the_split(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = Path("data/processed/pilot-import/collected_documents.jsonl")
    output = tmp_path / "research-batch"
    split = Path("data/interim/phase4/relevance_split_manifest.csv")
    before = split.read_bytes()
    code = main.main(
        [
            "run",
            "--research-batch",
            "--stages",
            "normalize,dedupe,prefilter,relevance,extract",
            "--input",
            str(source),
            "--output",
            str(output),
            "--document-limit",
            "20",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert "selected             0" in captured.out
    assert "provenance failures  0" in captured.out
    assert "provider calls       0" in captured.out
    assert "files written        0" in captured.out
    assert "maximum external     0" in captured.out
    assert "retrieval_trigger" in captured.out
    assert "spliced" in captured.out
    assert not output.exists()
    assert split.read_bytes() == before
