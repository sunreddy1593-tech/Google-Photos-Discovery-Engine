"""Synthetic bounded verification; socket access is forbidden."""
import json
import socket
from pathlib import Path

import pytest

from src.core.config import Secrets, load_settings
from src.core.versions import prompt_version
from src.llm.providers.base import ProviderResponse, rate_limited
from src.models.gold import GoldDocumentLabel
from src.normalize.derive import derive_document
from src.pipeline import quality
from tests.synthetic import NOW, RAW_TEXT_AUDIT, make_document

pytestmark = pytest.mark.synthetic


def test_relative_project_paths_match_absolute_hash_keys(tmp_path: Path) -> None:
    target = tmp_path / "data" / "packet.json"
    target.parent.mkdir()
    target.write_text('{"doc_id":"synthetic"}\n', encoding="utf-8")
    relative = Path("data/packet.json")
    with pytest.raises(ValueError):
        relative.resolve().relative_to(tmp_path.resolve())
    assert quality.project_key(tmp_path, relative) == "data/packet.json"
    assert quality.rooted(tmp_path, relative) == target.resolve()
    assert quality.sha(quality.rooted(tmp_path, relative)) == quality.sha(target)
ROOT = Path(__file__).resolve().parents[1]
IDS = ["reddit-synthetic-one", "reddit-synthetic-two"]


def write(path, data, rows=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in data) if rows else json.dumps(data), encoding="utf-8")


class Provider:
    provider_name = "groq"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def complete_structured(self, prompt, schema, params):
        doc = schema["properties"]["doc_id"]["enum"][0]
        self.calls.append((doc, params.max_tokens, prompt))
        if self.fail:
            raise rate_limited("synthetic rate limit")
        if "cases" in schema["properties"]:
            payload = {"doc_id": doc, "cases": []}
        else:
            payload = {"doc_id": doc, "scope_class": "core_incomplete_recall",
                       "reason_code": "known_item_with_incomplete_recall",
                       "reason_summary": "A synthetic search failed.", "confidence": 0.9,
                       "evidence": {"quote": RAW_TEXT_AUDIT[:90], "start_char": 0, "end_char": 90}}
        return ProviderResponse(text=json.dumps(payload), input_tokens=10, output_tokens=5,
                                model=params.model, provider="groq")


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    monkeypatch.setattr(quality, "seats", lambda root: {"dev": IDS, "holdout": IDS})
    settings = load_settings(project_root=tmp_path, config_dir=ROOT / "config", env_file=tmp_path / "absent")
    settings = settings.model_copy(update={"secrets": Secrets(_env_file=None, groq_api_key="synthetic-key")})
    docs = [make_document(doc_id=doc) for doc in IDS]
    write(tmp_path / quality.COLLECTED, [doc.model_dump(mode="json") for doc in docs], rows=True)
    write(tmp_path / quality.DERIVED, [derive_document(doc, derived_at=NOW).model_dump(mode="json") for doc in docs], rows=True)
    write(tmp_path / quality.LINKS, [], rows=True)
    return settings


def run(settings, tmp_path, **extra):
    return quality.run_quality(settings=settings, split="dev", output=tmp_path / "out",
                               cache=tmp_path / "cache", call_budget=4, **extra)


def test_scoped_v3_uses_real_gateway_cache_budget_and_manifest(fixture, tmp_path):
    provider = Provider()
    result = run(fixture, tmp_path, provider=provider)
    assert result["provider_calls"] == 4
    assert [row[1] for row in provider.calls] == [4096, 4096, 8192, 8192]
    assert "extract/v3" in provider.calls[2][2]
    manifest = quality.read(Path(result["extraction"]["output_dir"]) / "run_manifest.json")
    assert manifest["versions"]["prompt_versions"]["extract"] == "extract/v3"
    assert prompt_version("extract") == "extract/v2"
    assert result["human_overrides_used"] is False
    # Same identities in a fresh output reuse both stages; no paid requests.
    second = quality.run_quality(settings=fixture, split="dev", output=tmp_path / "other",
        cache=tmp_path / "cache", call_budget=4, provider=provider)
    assert second["provider_calls"] == 0
    assert second["relevance"]["cache_hits"] == second["extraction"]["cache_hits"] == 2
    assert len(provider.calls) == 4


def test_rate_limits_preserve_first_attempt_and_never_retry(fixture, tmp_path):
    provider = Provider(fail=True)
    result = run(fixture, tmp_path, provider=provider)
    assert [row[0] for row in provider.calls] == IDS
    assert result["provider_calls"] == 2
    assert result["extraction"]["attempted"] == 0


def test_explicit_v4_candidate_reuses_relevance_but_isolates_extraction_cache(fixture, tmp_path):
    provider=Provider()
    baseline=run(fixture,tmp_path,provider=provider)
    result=quality.run_quality(settings=fixture,split="dev",output=tmp_path/"candidate",
        cache=tmp_path/"cache",call_budget=4,provider=provider,candidate_prompt="extract/v4")
    assert result["provider_calls"]==2
    assert result["relevance"]["cache_hits"]==2 and result["extraction"]["cache_hits"]==0
    assert result["extraction_prompt"]=="extract/v4"
    manifest=quality.read(Path(result["extraction"]["output_dir"])/"run_manifest.json")
    assert manifest["versions"]["prompt_versions"]["extract"]=="extract/v4"
    assert baseline["extraction_prompt"]=="extract/v3" and prompt_version("extract")=="extract/v2"


def test_v6_candidate_misses_relevance_cache_and_keeps_the_active_pin(fixture, tmp_path):
    provider = Provider()
    run(fixture, tmp_path, provider=provider)
    result = quality.run_quality(
        settings=fixture, split="dev", output=tmp_path / "candidate",
        cache=tmp_path / "cache", call_budget=4, provider=provider,
        candidate_prompt="extract/v4", candidate_relevance="relevance/v6",
    )
    assert result["provider_calls"] == 4
    assert result["relevance"]["cache_hits"] == 0
    assert result["extraction"]["cache_hits"] == 0
    assert result["relevance_prompt"] == "relevance/v6"
    assert result["extraction_prompt"] == "extract/v4"
    assert "one continuous verbatim span" in provider.calls[4][2]
    assert "Prompt relevance/v6." in provider.calls[4][2]
    manifest = quality.read(Path(result["relevance"]["output_dir"]) / "run_manifest.json")
    assert manifest["versions"]["prompt_versions"]["relevance"] == "relevance/v6"
    assert prompt_version("relevance") == "relevance/v5"
    assert prompt_version("extract") == "extract/v2"


def test_successor_is_refused_on_development_and_without_approval(fixture, tmp_path):
    with pytest.raises(quality.QualityBoundsError, match="successor"):
        quality.run_quality(
            settings=fixture, split="dev", output=tmp_path / "out", cache=tmp_path / "cache",
            call_budget=4, provider=Provider(), successor=True,
            candidate_prompt="extract/v4", candidate_relevance="relevance/v6",
        )
    with pytest.raises(quality.QualityBoundsError, match="approval"):
        quality.run_quality(
            settings=fixture, split="holdout", output=tmp_path / "holdout", cache=tmp_path / "cache",
            call_budget=4, provider=Provider(), successor=True,
            candidate_prompt="extract/v4", candidate_relevance="relevance/v6",
        )
    assert not (tmp_path / "out").exists() and not (tmp_path / "holdout").exists()


def test_candidate_relevance_holdout_refused_before_output(fixture, tmp_path):
    with pytest.raises(quality.QualityBoundsError, match="gold-dev"):
        quality.run_quality(
            settings=fixture, split="holdout", output=tmp_path / "out",
            cache=tmp_path / "cache", call_budget=4,
            candidate_relevance="relevance/v6", provider=Provider(),
        )
    assert not (tmp_path / "out").exists()


def test_v5_candidate_is_development_only(fixture, tmp_path):
    provider = Provider()
    result = run(fixture, tmp_path, provider=provider, candidate_prompt="extract/v5", dry_run=True)
    assert result["provider_calls"] == result["records_written"] == 0
    assert result["dry_run"] is True
    assert prompt_version("extract") == "extract/v2"
    with pytest.raises(quality.QualityBoundsError, match="development split only"):
        quality.run_quality(
            settings=fixture, split="holdout", output=tmp_path / "holdout",
            cache=tmp_path / "cache", call_budget=4, candidate_prompt="extract/v5",
            provider=Provider(),
        )
    with pytest.raises(quality.QualityBoundsError, match="extract/v4 only"):
        quality.run_quality(
            settings=fixture, split="holdout", output=tmp_path / "successor",
            cache=tmp_path / "cache", call_budget=4, successor=True,
            candidate_prompt="extract/v5", candidate_relevance="relevance/v6",
            provider=Provider(),
        )
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "holdout").exists()
    assert not (tmp_path / "successor").exists()


def test_candidate_holdout_refused_before_output(fixture,tmp_path):
    with pytest.raises(quality.QualityBoundsError,match="gold-dev"):
        quality.run_quality(settings=fixture,split="holdout",output=tmp_path/"out",
            cache=tmp_path/"cache",call_budget=4,candidate_prompt="extract/v4",provider=Provider())
    assert not (tmp_path/"out").exists()


def test_candidate_dry_run_zero_calls(fixture,tmp_path):
    provider=Provider()
    result=run(fixture,tmp_path,provider=provider,candidate_prompt="extract/v4",dry_run=True)
    assert result["provider_calls"]==result["records_written"]==0
    assert not provider.calls and not (tmp_path/"out").exists()


def test_dry_run_zero_calls_zero_records_and_missing_key_allowed(fixture, tmp_path):
    settings = fixture.model_copy(update={"secrets": Secrets(_env_file=None, groq_api_key=None)})
    provider = Provider()
    result = run(settings, tmp_path, provider=provider, dry_run=True)
    assert result["provider_calls"] == result["records_written"] == len(provider.calls) == 0
    assert not (tmp_path / "out").exists() and not (tmp_path / "cache").exists()


def test_missing_key_fails_before_output_or_cache(fixture, tmp_path):
    from src.core.errors import ConfigError
    settings = fixture.model_copy(update={"secrets": Secrets(_env_file=None, groq_api_key=None)})
    with pytest.raises(ConfigError):
        run(settings, tmp_path, provider=Provider())
    assert not (tmp_path / "out").exists() and not (tmp_path / "cache").exists()


@pytest.mark.parametrize("budget", [-1, 0, 3, 5])
def test_invalid_budget_before_any_output(fixture, tmp_path, budget):
    with pytest.raises(quality.QualityBoundsError):
        quality.run_quality(settings=fixture, split="dev", output=tmp_path / "out",
                            cache=tmp_path / "cache", call_budget=budget, provider=Provider())
    assert not (tmp_path / "out").exists()


def test_fresh_output_guard(fixture, tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(quality.QualityBoundsError, match="fresh"):
        run(fixture, tmp_path, provider=Provider())


def test_holdout_missing_approval_is_closed_even_in_dry_run(fixture, tmp_path):
    with pytest.raises(quality.QualityBoundsError, match="requires freeze"):
        quality.run_quality(settings=fixture, split="holdout", output=tmp_path / "out",
                            cache=tmp_path / "cache", call_budget=4, dry_run=True)
    assert not (tmp_path / "out").exists()


@pytest.fixture
def frozen(fixture, tmp_path, monkeypatch):
    marker = tmp_path / "marker.txt"
    marker.write_text("frozen", encoding="utf-8")
    monkeypatch.setattr(quality, "freeze_files", lambda root: {"marker.txt": quality.sha(marker)})
    report = tmp_path / "dev/report.json"
    write(report, {"status": "measured", "quality_gate_status": "development_only",
                   "saved_inputs": {"versions": {"prompt_versions": {"extract": "extract/v3"}}}})
    freeze = tmp_path / "freeze/freeze.json"
    quality.create_freeze(tmp_path, freeze, report)
    pack, gold, approval = tmp_path / "pack", tmp_path / "gold", tmp_path / "approval.json"
    write(pack / "manifest.json", {"documents": [{"doc_id": doc, "gold_split": "holdout", "phase4_split": "development"} for doc in IDS]})
    for doc in IDS:
        write(pack / "packets" / f"{doc}.json", {"doc_id": doc, "gold_split": "holdout",
              "phase4_split": "development", "source_text": RAW_TEXT_AUDIT})
    documents = [GoldDocumentLabel(doc_id=doc, split="holdout", scope_class="core_incomplete_recall",
                 reason_code="known_item_with_incomplete_recall", prefilter_should_pass=True,
                 expected_case_count=0, labeler_id="Sunayana", labeled_at=NOW) for doc in IDS]
    write(gold / "documents.jsonl", [doc.model_dump(mode="json") for doc in documents], rows=True)
    write(gold / "cases.jsonl", [], rows=True)
    bound = [pack / "manifest.json", gold / "documents.jsonl", gold / "cases.jsonl",
             *sorted((pack / "packets").glob("*.json"))]
    write(approval, {"human_approved": True, "reviewer": "Sunayana", "approval_statement": "Synthetic approval",
                    "freeze_sha256": quality.sha(freeze),
                    "approved_sha256": {p.relative_to(tmp_path).as_posix(): quality.sha(p) for p in bound}})
    return dict(freeze=freeze, pack=pack, gold=gold, approval=approval)


def test_freeze_detects_code_or_data_change(fixture, frozen, tmp_path):
    (tmp_path / "marker.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(quality.QualityBoundsError, match="changed after freeze"):
        quality.check_holdout_approval(tmp_path, **frozen)


def test_ai_draft_approval_false_cannot_unlock(fixture, frozen, tmp_path):
    receipt = quality.read(frozen["approval"])
    receipt["human_approved"] = False
    write(frozen["approval"], receipt)
    with pytest.raises(quality.QualityBoundsError, match="explicit"):
        quality.check_holdout_approval(tmp_path, **frozen)


def test_modified_labels_are_not_approved(fixture, frozen, tmp_path):
    with (frozen["gold"] / "cases.jsonl").open("a") as handle:
        handle.write("\n")
    with pytest.raises(quality.QualityBoundsError, match="exact labels"):
        quality.check_holdout_approval(tmp_path, **frozen)


def test_holdout_claim_once_dry_run_no_claim(fixture, frozen, tmp_path):
    provider = Provider()
    kwargs = dict(settings=fixture, split="holdout", output=tmp_path / "holdout",
                  cache=tmp_path / "cache", call_budget=4, provider=provider, **frozen)
    quality.run_quality(**kwargs, dry_run=True)
    claim = frozen["freeze"].parent / "measurement_claim.json"
    assert not claim.exists() and provider.calls == []
    result = quality.run_quality(**kwargs)
    assert claim.exists() and result["provider_calls"] == 4
    from src.gold.saved_run import load_saved_holdout
    args = dict(root=tmp_path, doc_ids=set(IDS), run=Path(result["extraction"]["output_dir"]),
                relevance=kwargs["output"] / "relevance/relevance_decisions.jsonl",
                prefilter_events=kwargs["output"] / "relevance/stage_events.jsonl", **frozen)
    loaded = load_saved_holdout(**args)
    assert loaded.metadata["holdout_source_text_loaded"] is True
    assert len(loaded.predictions) == 2 and loaded.metadata["accepted_empty_documents"] == 2
    (kwargs["output"] / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(quality.QualityBoundsError, match="artifacts changed"):
        load_saved_holdout(**args)
    kwargs["output"] = tmp_path / "second-holdout"
    with pytest.raises(quality.QualityBoundsError, match="already been claimed"):
        quality.run_quality(**kwargs)
    assert len(provider.calls) == 4 and not kwargs["output"].exists()


def test_source_first_pack_has_no_predictions_or_human_approval(fixture, frozen, tmp_path):
    from scripts.prepare_quality_holdout import prepare
    destination = tmp_path / "blank-pack"
    prepare(root=tmp_path, freeze=frozen["freeze"], output=destination)
    assert quality.read(destination / "manifest.json")["predictions_in_pack"] is False
    assert quality.read(destination / "review_policy.json")["human_approved"] is False
    for doc in IDS:
        packet = quality.read(destination / "packets" / f"{doc}.json")
        assert packet["source_text"] == RAW_TEXT_AUDIT
        assert packet["gold_document"]["scope_class"] is None
        assert packet["gold_split"] == "holdout"


def test_approval_export_requires_statement_and_preserves_drafts(fixture, frozen, tmp_path):
    from scripts.approve_quality_holdout import approve
    for name in ("documents.jsonl", "cases.jsonl"):
        write(tmp_path / quality.DEV_GOLD / name, [], rows=True)
    for doc in IDS:
        write(frozen["pack"] / "drafts" / f"{doc}.json", {
            "doc_id": doc, "split": "holdout", "scope_class": "core_incomplete_recall",
            "reason_code": "known_item_with_incomplete_recall", "prefilter_should_pass": True,
            "expected_case_count": 0, "cases": [], "labeler_id": "AI-unapproved-draft",
        })
    before = {p: quality.sha(p) for p in (frozen["pack"] / "drafts").glob("*.json")}
    output, receipt = tmp_path / "approved-gold", tmp_path / "actual-approval.json"
    kwargs = dict(root=tmp_path, freeze=frozen["freeze"], pack=frozen["pack"], output=output, receipt=receipt)
    with pytest.raises(ValueError, match="actual approval"):
        approve(**kwargs, statement="")
    assert not output.exists() and not receipt.exists()
    approve(**kwargs, statement="Synthetic owner's approval after source review")
    quality.check_holdout_approval(tmp_path, freeze=frozen["freeze"], pack=frozen["pack"],
                                   gold=output, approval=receipt)
    assert {p: quality.sha(p) for p in before} == before
    assert quality.read(receipt)["reviewer"] == "Sunayana"
