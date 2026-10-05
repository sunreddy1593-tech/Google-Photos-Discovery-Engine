"""Bounded scheduled runs. No test makes a live provider or YouTube request."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from streamlit.testing.v1 import AppTest

from src.core.config import load_settings
from src.core.ids import author_hash, author_salt_id, doc_id, raw_text_sha256, source_url_key
from src.export.build import build_submission
from src.export.scheduled_status import load_snapshot, publish_snapshot, read_snapshot_version
from src.llm.cache import CacheEntry, ResponseCache
from src.llm.providers.base import ProviderCallError
from src.models.collected_document import CollectedDocument
from src.models.enums import CollectionMethod, DecisionTechnicalState, EvidenceTier, SourcePlatform, SourceType
from src.normalize.derive import derive_document
from src.pipeline.runner import RULESET_INSTANT
from src.pipeline.scheduled_run import (
    COLLECTION_REQUESTS_PER_DAY,
    COLLECTION_REQUESTS_PER_RUN,
    MODEL_ATTEMPTS_PER_DAY,
    MODEL_ATTEMPTS_PER_RUN,
    TARGET_DOCUMENTS,
    SchedulePaths,
    _Ledger,
    _process_with_existing_stages,
    _relevance_cached,
    next_scheduled_at,
    run_scheduled,
    sub_batch_sizes,
)
from tests.test_submission_export import _fixture

SALT = "batch-test-salt"
TEXT = "I cannot find the photo of the birthday cake from last summer when I search Google Photos."
WHEN = datetime(2026, 10, 5, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
APP = Path(__file__).resolve().parents[1] / "app.py"


def _document(item: str, *, text: str = TEXT, collector: str = "") -> CollectedDocument:
    platform = SourcePlatform.youtube.value
    url = f"https://www.youtube.com/watch?v=abcdefghijk&lc={item}"
    metadata = {"video_id": "abcdefghijk", "replies_complete": True}
    if collector:
        metadata["collector"] = collector
    return CollectedDocument(
        doc_id=doc_id(platform, source_item_id=item),
        ingest_batch_id="n8n-excluded" if collector == "n8n" else "scheduled-test",
        source_platform=SourcePlatform.youtube,
        source_type=SourceType.video_comment,
        evidence_tier=EvidenceTier.direct_user,
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
        metadata=metadata,
    )


def _paths(tmp_path: Path, frozen: list[str] | None = None) -> SchedulePaths:
    video = tmp_path / "videos.txt"
    video.write_text("https://www.youtube.com/watch?v=abcdefghijk\n", encoding="utf-8")
    split = tmp_path / "split.csv"
    lines = ["doc_id,split,stratum,split_version"]
    lines.extend(
        f"{item},holdout,core_incomplete_recall,relevance-seed-split/v1" for item in frozen or []
    )
    split.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "holdout-text.txt").write_text("HOLD OUT TEXT MUST NOT BE READ", encoding="utf-8")
    return SchedulePaths(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        output_root=tmp_path / "runs",
        snapshot_root=tmp_path / "snapshot",
        video_file=video,
        frozen_split=split,
        cache_dir=tmp_path / "cache",
        known_corpus=(),
    )


def _settings(**secrets: str | None):
    loaded = load_settings()
    current = {
        "youtube_api_key": "test-youtube-key",
        "author_salt": SALT,
        "groq_api_key": "test-groq-key",
    }
    current.update(secrets)
    return loaded.model_copy(update={"secrets": loaded.secrets.model_copy(update=current)})


def _collector(documents: list[CollectedDocument], *, requests: int = 1, already: int = 0):
    calls: list[int] = []

    def collect(video_file: Path, output_dir: Path, **kwargs: object):
        del video_file
        calls.append(int(kwargs["request_budget"]))
        path = Path(output_dir) / "collected_documents.jsonl"
        path.write_text("".join(item.model_dump_json() + "\n" for item in documents), encoding="utf-8")

        class _Report:
            requests_made = requests
            documents_written = len(documents)
            documents_already_present = already

        class _Result:
            report = _Report()

        return _Result()

    return collect, calls


def _processor(store: list[list[str]]):
    def process(**kwargs: object) -> dict[str, object]:
        documents = list(kwargs["documents"])
        store.append([document.doc_id for document in documents])
        return {
            "duplicate_links": 0,
            "in_scope": 1,
            "adjacent": 0,
            "out_of_scope": 0,
            "extracted_cases": 1,
            "automatically_valid_cases": 1,
            "failures": [],
            "incomplete": [],
            "unprocessed_doc_ids": [],
            "model_attempts": 0,
            "estimated_cost_usd": 0.0,
            "usage_known": True,
            "unreviewed_cases": [
                {
                    "case_id": "case-1",
                    "doc_id": documents[0].doc_id,
                    "source_url": str(documents[0].source_url),
                    "automatically_valid": True,
                    "semantically_approved": True,
                    "evidence": [
                        {
                            "field_name": "problem_summary",
                            "quote": "birthday cake",
                            "start_char": 24,
                            "end_char": 37,
                        }
                    ],
                }
            ],
        }

    return process


@pytest.mark.synthetic
def test_fifty_documents_use_three_bounded_sub_batches(tmp_path: Path) -> None:
    assert sub_batch_sizes(50) == [20, 20, 10]
    assert sub_batch_sizes(35) == [20, 15]
    assert max(sub_batch_sizes(50)) <= 20
    documents = [_document(f"comment-{index:03d}") for index in range(50)]
    collect, calls = _collector(documents, requests=4)
    seen: list[list[str]] = []
    report = run_scheduled(
        _paths(tmp_path),
        dry_run=False,
        now=WHEN,
        settings=_settings(),
        collector=collect,
        process_batch=_processor(seen),
        pid=1200,
        pid_alive=lambda pid: pid == 1200,
    )
    assert calls == [COLLECTION_REQUESTS_PER_RUN]
    assert report.new_documents == 50
    assert report.shortfall == 0
    assert report.status == "completed"
    assert report.sub_batches == (20, 20, 10)
    assert [len(batch) for batch in seen] == [20, 20, 10]
    manifest = json.loads((Path(report.output_dir) / "parent_manifest.json").read_text(encoding="utf-8"))
    assert manifest["sub_batches"] == [20, 20, 10]
    assert "extraction_pilot" not in Path("src/pipeline/scheduled_run.py").read_text(encoding="utf-8")


@pytest.mark.synthetic
def test_shortfall_is_reported_without_padding(tmp_path: Path) -> None:
    documents = [_document(f"only-{index}") for index in range(12)]
    collect, _calls = _collector(documents, requests=2, already=3)
    seen: list[list[str]] = []
    report = run_scheduled(
        _paths(tmp_path),
        dry_run=False,
        now=WHEN,
        settings=_settings(),
        collector=collect,
        process_batch=_processor(seen),
        pid=1201,
        pid_alive=lambda pid: pid == 1201,
    )
    assert report.partial
    assert report.new_documents == 12
    assert report.shortfall == 38
    assert report.status == "partial"
    assert "shortfall 38" in report.message
    assert sum(len(batch) for batch in seen) == 12
    snapshot = load_snapshot(tmp_path / "snapshot")
    assert snapshot["shortfall"] == 38
    assert snapshot["human_approved_cases"] == 0
    assert snapshot["unreviewed_cases"][0]["semantically_approved"] is False
    assert snapshot["unreviewed_cases"][0]["automatically_valid"] is True


@pytest.mark.synthetic
def test_second_run_skips_unchanged_documents(tmp_path: Path) -> None:
    first, _calls = _collector([_document("same"), _document("fresh")], requests=2)
    seen: list[list[str]] = []
    paths = _paths(tmp_path)
    settings = _settings()
    run_scheduled(
        paths,
        dry_run=False,
        now=WHEN,
        settings=settings,
        collector=first,
        process_batch=_processor(seen),
        pid=1202,
        pid_alive=lambda pid: False,
    )
    second, calls = _collector([_document("same"), _document("fresh"), _document("later")], requests=1, already=2)
    later = WHEN.replace(hour=14)
    report = run_scheduled(
        paths,
        dry_run=False,
        now=later,
        settings=settings,
        collector=second,
        process_batch=_processor(seen),
        pid=1203,
        pid_alive=lambda pid: False,
    )
    assert calls
    processed = [doc_id for batch in seen for doc_id in batch]
    assert processed.count(_document("same").doc_id) == 1
    assert _document("later").doc_id in processed
    assert report.new_documents == 1


@pytest.mark.synthetic
def test_reservations_survive_a_new_ledger_object(tmp_path: Path) -> None:
    path = tmp_path / "budget-ledger.json"
    first = _Ledger(path)
    assert first.reserve(day="2026-10-05", run_id="run-a", kind="collection", count=20, doc_ids=()).count == 20
    assert first.reserve(day="2026-10-05", run_id="run-a", kind="collection", count=20, doc_ids=()) is None
    second = _Ledger(path)
    assert second.consumed("2026-10-05") == (20, 0)
    assert second.reserve(day="2026-10-05", run_id="run-b", kind="collection", count=20, doc_ids=()).count == 20
    assert second.reserve(day="2026-10-05", run_id="run-c", kind="collection", count=20, doc_ids=()).count == 20
    assert second.reserve(day="2026-10-05", run_id="run-d", kind="collection", count=1, doc_ids=()) is None
    assert second.consumed("2026-10-05") == (COLLECTION_REQUESTS_PER_DAY, 0)
    model = second.reserve(
        day="2026-10-05",
        run_id="run-b",
        kind="model",
        stage="relevance",
        count=MODEL_ATTEMPTS_PER_RUN,
        doc_ids=tuple(f"doc-{index}" for index in range(MODEL_ATTEMPTS_PER_RUN)),
    )
    assert model is not None and model.count == MODEL_ATTEMPTS_PER_RUN
    assert second.reserve(day="2026-10-05", run_id="run-b", kind="model", stage="extract", count=1, doc_ids=("more",)) is None
    third = _Ledger(path)
    assert third.consumed("2026-10-05")[1] == MODEL_ATTEMPTS_PER_RUN
    assert MODEL_ATTEMPTS_PER_DAY == 300


@pytest.mark.synthetic
def test_cache_hit_makes_no_provider_call_and_reserves_nothing(tmp_path: Path) -> None:
    document = _document("cached-comment")
    derived = derive_document(document, derived_at=RULESET_INSTANT)
    settings = _settings()
    paths = _paths(tmp_path)
    from src.core.versions import SCHEMA_VERSION, prompt_version
    from src.llm.providers.groq import cache_decoding_params, groq_request_schema
    from src.pipeline.research_batch import RESEARCH_MODEL, RESEARCH_PROVIDER
    from src.relevance.prompts import PROMPT_ID, relevance_json_schema
    from src.core.ids import cache_key
    from src.core.versions import RULESET_VERSION

    schema = groq_request_schema(relevance_json_schema(), doc_id=document.doc_id)
    key = cache_key(
        provider=RESEARCH_PROVIDER,
        model=RESEARCH_MODEL,
        prompt_id=PROMPT_ID,
        prompt_version=prompt_version(PROMPT_ID),
        schema_version=SCHEMA_VERSION,
        content_hash_value=derived.content_hash,
        decoding_params=cache_decoding_params(
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            schema=schema,
        ),
        ruleset_version=RULESET_VERSION,
    )
    ResponseCache(paths.cache_dir).write(
        CacheEntry(
            cache_key=key,
            provider=RESEARCH_PROVIDER,
            model=RESEARCH_MODEL,
            prompt_id=PROMPT_ID,
            prompt_version=prompt_version(PROMPT_ID),
            schema_version=SCHEMA_VERSION,
            ruleset_version=RULESET_VERSION,
            content_hash=derived.content_hash,
            decoding_params={},
            request_text="cached",
            raw_response="{}",
            input_tokens=0,
            output_tokens=0,
            cached_at=WHEN.isoformat(),
        ),
        denylist=(),
    )
    assert _relevance_cached(
        ResponseCache(paths.cache_dir),
        document,
        derived,
        model=RESEARCH_MODEL,
        temperature=settings.models.temperature,
        max_tokens=settings.models.max_tokens,
    )

    class _Provider:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0

        def complete_structured(self, prompt: str, schema: object, params: object) -> object:
            del prompt, schema, params
            self.calls += 1
            raise AssertionError("cache hit must not call the provider")

    provider = _Provider()
    ledger = _Ledger(paths.state_dir / "budget-ledger.json")
    _process_with_existing_stages(
        documents=[document],
        output_dir=tmp_path / "sub",
        paths=paths,
        settings=settings,
        ledger=ledger,
        run_id="cache-run",
        now=WHEN,
        provider=provider,
    )
    assert provider.calls == 0
    assert ledger.consumed("2026-10-05")[1] == 0


@pytest.mark.synthetic
def test_provider_failure_is_not_retried_or_repeated(tmp_path: Path) -> None:
    class _Provider:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0

        def complete_structured(self, prompt: str, schema: object, params: object) -> object:
            del prompt, schema, params
            self.calls += 1
            raise ProviderCallError("down", DecisionTechnicalState.provider_error)

    provider = _Provider()
    document = _document("retry-comment")
    paths = _paths(tmp_path)
    settings = _settings()

    def process(**kwargs: object) -> dict[str, object]:
        return _process_with_existing_stages(provider=provider, **kwargs)

    collect, _calls = _collector([document], requests=1)
    run_scheduled(
        paths,
        dry_run=False,
        now=WHEN,
        settings=settings,
        collector=collect,
        process_batch=process,
        pid=1300,
        pid_alive=lambda pid: False,
    )
    assert provider.calls == 1
    again, _again_calls = _collector([document], requests=1)
    run_scheduled(
        paths,
        dry_run=False,
        now=WHEN.replace(hour=14),
        settings=settings,
        collector=again,
        process_batch=process,
        pid=1301,
        pid_alive=lambda pid: False,
    )
    assert provider.calls == 1


@pytest.mark.synthetic
def test_overlap_makes_no_request_and_stale_lock_does_not_repeat_reservation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.state_dir.mkdir()
    (paths.state_dir / "run.lock").write_text(
        json.dumps({"pid": 77, "acquired_at": WHEN.isoformat()}),
        encoding="utf-8",
    )
    collect, calls = _collector([_document("overlap")])
    report = run_scheduled(
        paths,
        dry_run=False,
        now=WHEN,
        settings=_settings(),
        collector=collect,
        process_batch=_processor([]),
        pid=88,
        pid_alive=lambda pid: pid == 77,
    )
    assert report.status == "skipped_overlap"
    assert calls == []
    assert not paths.output_root.exists()

    paths.state_dir.joinpath("run.lock").unlink()
    reserved = _document("reserved-comment")
    _Ledger(paths.state_dir / "budget-ledger.json").reserve(
        day="2026-10-05",
        run_id="crashed",
        kind="model",
        stage="relevance",
        count=1,
        doc_ids=(reserved.doc_id,),
    )
    seen: list[list[str]] = []
    fresh, _fresh_calls = _collector([reserved, _document("other-comment")], requests=1)
    (paths.state_dir / "run.lock").write_text(
        json.dumps({"pid": 404, "acquired_at": WHEN.isoformat()}),
        encoding="utf-8",
    )
    recovered = run_scheduled(
        paths,
        dry_run=False,
        now=WHEN,
        settings=_settings(),
        collector=fresh,
        process_batch=_processor(seen),
        pid=89,
        pid_alive=lambda pid: False,
    )
    assert recovered.status != "skipped_overlap"
    assert seen == [[_document("other-comment").doc_id]]
    assert _Ledger(paths.state_dir / "budget-ledger.json").consumed("2026-10-05")[1] == 1
    assert any(reserved.doc_id in item for item in recovered.incomplete_work)


@pytest.mark.synthetic
def test_missing_credentials_stop_before_requests_and_output(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    collect, calls = _collector([_document("unused")])
    report = run_scheduled(
        paths,
        dry_run=False,
        now=WHEN,
        settings=_settings(youtube_api_key=None),
        collector=collect,
        pid=90,
        pid_alive=lambda pid: False,
    )
    assert report.status == "missing_inputs"
    assert "YOUTUBE_API_KEY" in report.missing_inputs
    assert calls == []
    assert not paths.output_root.exists()
    assert not paths.snapshot_root.exists()

    missing_video = SchedulePaths(
        project_root=paths.project_root,
        state_dir=paths.state_dir,
        output_root=paths.output_root,
        snapshot_root=paths.snapshot_root,
        video_file=tmp_path / "missing-youtube-videos.txt",
        frozen_split=paths.frozen_split,
        cache_dir=paths.cache_dir,
    )
    named = run_scheduled(
        missing_video,
        dry_run=True,
        now=WHEN,
        settings=_settings(),
        collector=collect,
    )
    assert "missing-youtube-videos.txt" in named.message


@pytest.mark.synthetic
def test_dry_run_makes_no_call_and_writes_no_record(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    collect, calls = _collector([_document("dry")])
    report = run_scheduled(
        paths,
        dry_run=True,
        now=WHEN,
        settings=_settings(),
        collector=collect,
        pid=91,
        pid_alive=lambda pid: False,
    )
    assert report.status == "dry_run"
    assert report.collection_requests_used == 0
    assert report.model_attempts_used == 0
    assert calls == []
    assert not paths.state_dir.exists()
    assert not paths.output_root.exists()
    assert not paths.snapshot_root.exists()
    assert next_scheduled_at(WHEN).hour == 14


@pytest.mark.synthetic
def test_snapshot_publish_keeps_the_previous_pointer_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "snapshot"
    first = {"snapshot_version": "run-1", "new_documents": 10, "shortfall": 40, "raw_text": "secret body", "api_key": "hidden"}
    second = {"snapshot_version": "run-2", "new_documents": 50, "shortfall": 0, "human_approved_cases": 4}
    publish_snapshot(root, first)
    publish_snapshot(root, second)
    assert read_snapshot_version(root) == "run-2"
    assert load_snapshot(root)["new_documents"] == 50
    assert load_snapshot(root)["human_approved_cases"] == 0
    saved = (root / "versions" / "run-1" / "snapshot.json").read_text(encoding="utf-8")
    assert "secret body" not in saved
    assert "hidden" not in saved

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", _fail)
    with pytest.raises(OSError):
        publish_snapshot(root, {"snapshot_version": "run-3", "new_documents": 1})
    assert read_snapshot_version(root) == "run-2"
    assert load_snapshot(root)["new_documents"] == 50


@pytest.mark.synthetic
def test_n8n_and_frozen_documents_are_excluded(tmp_path: Path) -> None:
    frozen = _document("frozen-comment")
    n8n = _document("n8n-comment", collector="n8n")
    kept = _document("kept-comment")
    collect, _calls = _collector([frozen, n8n, kept], requests=1)
    seen: list[list[str]] = []
    report = run_scheduled(
        _paths(tmp_path, frozen=[frozen.doc_id]),
        dry_run=False,
        now=WHEN,
        settings=_settings(),
        collector=collect,
        process_batch=_processor(seen),
        pid=1400,
        pid_alive=lambda pid: False,
    )
    assert seen == [[kept.doc_id]]
    assert any(item["source"] == "n8n" and item["status"] == "excluded" for item in report.excluded_sources)
    assert all(item.get("source") != "n8n" or item.get("status") == "excluded" for item in report.sources)
    assert "src.collect.community" not in Path("src/pipeline/scheduled_run.py").read_text(encoding="utf-8")
    holdout = tmp_path / "holdout-text.txt"
    assert "HOLD OUT TEXT" in holdout.read_text(encoding="utf-8")


@pytest.mark.synthetic
def test_scheduled_page_refreshes_snapshot_without_approving_cases(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    build_submission(_fixture(tmp_path), export_dir, root=tmp_path)
    snapshot_root = tmp_path / "snapshot"
    publish_snapshot(
        snapshot_root,
        {
            "snapshot_version": "ui-1",
            "status": "partial",
            "partial": True,
            "last_run_at": "2026-10-05T08:05:00+05:30",
            "next_run_at": "2026-10-05T14:00:00+05:30",
            "new_documents": 12,
            "duplicates": 3,
            "target_documents": 50,
            "shortfall": 38,
            "in_scope": 2,
            "adjacent": 1,
            "out_of_scope": 4,
            "extracted_cases": 2,
            "automatically_valid_cases": 1,
            "human_approved_cases": 9,
            "stage_failures": ["relevance budget is exhausted"],
            "incomplete_work": ["doc-held was not requested again"],
            "collection_requests_used": 4,
            "model_attempts_used": 6,
            "estimated_cost_usd": None,
            "usage_known": False,
            "sources": [
                {"source": "youtube", "status": "collected", "requests": 4, "documents_written": 12, "reason": "comments"},
                {"source": "reddit", "status": "unavailable", "requests": 0, "documents_written": 0, "reason": "no access"},
            ],
            "excluded_sources": [{"source": "n8n", "status": "excluded", "reason": "not called"}],
            "review_checks": ["quotes must be one continuous span; invented or spliced text is invalid"],
            "unreviewed_cases": [
                {
                    "case_id": "scheduled-case-1",
                    "doc_id": "doc-scheduled",
                    "source_url": "https://www.youtube.com/watch?v=abcdefghijk&lc=scheduled",
                    "automatically_valid": True,
                    "semantically_approved": True,
                    "evidence": [
                        {"field_name": "retrieval_trigger", "quote": "birthday cake", "start_char": 24, "end_char": 37}
                    ],
                }
            ],
        },
    )
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["export_dir"] = str(export_dir)
    app.session_state["scheduled_snapshot_root"] = str(snapshot_root)
    app.session_state["scheduled_autorefresh"] = False
    app.run()
    assert not app.exception
    app.radio(key="section").set_value("Scheduled runs").run()
    assert not app.exception
    text = "\n".join(
        block.value
        for blocks in (app.markdown, app.caption, app.warning, app.error)
        for block in blocks
    )
    assert "Batch shortfall: 38" in text
    assert "Awaiting semantic review" in text
    assert "scheduled-case-1" in text
    assert "birthday cake" in text
    assert "Semantically approved: false." in text
    assert any(metric.label == "Human approved" and metric.value == "0" for metric in app.metric)
    assert any(metric.label == "Automatically valid" and metric.value == "1" for metric in app.metric)
    assert any(metric.label == "Estimated cost" and metric.value == "unknown" for metric in app.metric)
    assert not any(button.label == "Collect" for button in app.button)
    app.radio(key="section").set_value("Problem comparison").run()
    comparison = "\n".join(
        block.value for blocks in (app.markdown, app.info) for block in blocks
    )
    assert "scheduled-case-1" not in comparison

    publish_snapshot(
        snapshot_root,
        {
            "snapshot_version": "ui-2",
            "status": "completed",
            "partial": False,
            "last_run_at": "2026-10-05T14:05:00+05:30",
            "next_run_at": "2026-10-05T20:00:00+05:30",
            "new_documents": 50,
            "duplicates": 0,
            "target_documents": 50,
            "shortfall": 0,
            "in_scope": 0,
            "adjacent": 0,
            "out_of_scope": 0,
            "extracted_cases": 0,
            "automatically_valid_cases": 0,
            "human_approved_cases": 0,
            "stage_failures": [],
            "incomplete_work": [],
            "collection_requests_used": 2,
            "model_attempts_used": 0,
            "estimated_cost_usd": 0.0,
            "usage_known": True,
            "sources": [],
            "excluded_sources": [],
            "review_checks": [],
            "unreviewed_cases": [],
        },
    )
    app.radio(key="section").set_value("Scheduled runs").run()
    app.button(key="refresh_scheduled").click().run()
    assert not app.exception
    assert any(metric.label == "New documents" and metric.value == "50" for metric in app.metric)
