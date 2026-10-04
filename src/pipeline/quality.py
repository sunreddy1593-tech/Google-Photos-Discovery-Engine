"""Bounded gold evaluation using existing stages; never a general batch runner.

The original Phase 4 split and legacy extraction pins are left intact. The
reserved gold holdout is historically development-exposed, which is disclosed.
Human approval is an input, not something produced by model validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.core.config import Settings
from src.core.versions import (
    EXTRACTION_PROMPT_CANDIDATE,
    EXTRACTION_PROMPT_CORRECTION,
    EXTRACTION_PROMPT_DEV_CANDIDATE,
    RELEVANCE_PROMPT_CANDIDATE,
    prompt_version,
    version_summary,
)
from src.gold.load import load_gold_cases, load_gold_documents, require_case_counts
from src.gold.evaluate import validate_gold_quotes
from src.gold.split import SplitMember, assign_gold_splits
from src.models.collected_document import CollectedDocument
from src.models.document_derived import DocumentDerived
from src.models.duplicate_link import DuplicateLink
from src.models.relevance import RelevanceDecision
from src.pipeline.extraction import run_extraction
from src.pipeline.extraction_development import development_ids
from src.pipeline.stages import run_phase4
from src.relevance.lock import authorize_live_classification, build_prompt_lock
from src.relevance.prompts import relevance_json_schema
from src.llm.providers.groq import groq_strict_schema, transmitted_schema_sha256

COLLECTED = Path("data/processed/pilot-import/collected_documents.jsonl")
DERIVED = Path("data/interim/phase3/documents_derived.jsonl")
LINKS = Path("data/interim/phase3/duplicate_links.jsonl")
SEED = Path("data/interim/phase4/relevance_seed_review.csv")
SEATING = Path("data/annotation/dev-starter-2026-10-03/manifest.json")
DEV_GOLD = Path("data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02/development-reference-02")
MODEL = "openai/gpt-oss-120b"
PROVIDER = "groq"
REL_TOKENS = 4096
EXTRACT_TOKENS = 8192
LIMITATION = (
    "Gold holdout was reserved from 35 previously processed Phase 4 development "
    "documents. Prior development exposure limits independence; this is not "
    "an untouched external test set. The original 15 Phase 4 holdout seats are separate."
)


class QualityBoundsError(ValueError):
    """A freeze, approval, or one-measurement bound was not satisfied."""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rooted(root: Path, path: Path | str) -> Path:
    """Resolve a CLI path from the project root before any hash comparison.

    A relative path is joined to ``root`` first. Resolving it from the current
    working directory made the same artifact look different from its stored path.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    return candidate.resolve()


def project_key(root: Path, path: Path | str) -> str:
    """Return the freeze/approval key for a relative or absolute project path."""
    return rooted(root, path).relative_to(Path(root).resolve()).as_posix()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def seats(root: Path) -> dict[str, list[str]]:
    development = set(development_ids(root / "data/interim/phase4/relevance_split_manifest.csv"))
    with (root / SEED).open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["doc_id"] in development]
    if {row["doc_id"] for row in rows} != development or len(rows) != len(development):
        raise QualityBoundsError("incomplete or duplicate original split metadata")
    assigned = assign_gold_splits([
        SplitMember(row["doc_id"], row["source_platform"], row["human_scope_class"])
        for row in rows
    ])
    result = {split: sorted(doc for doc, value in assigned.items() if value.value == split)
              for split in ("dev", "holdout")}
    original = read(root / SEATING)
    if set(result["dev"]) != {row["doc_id"] for row in original["documents"]}:
        raise QualityBoundsError("gold seating does not match the original ten-document pack")
    if len(result["dev"]) != 10 or len(result["holdout"]) != 25:
        raise QualityBoundsError("this route requires the existing 10/25 gold seating")
    return result


def selected_rows(path: Path, wanted: set[str]) -> list[dict]:
    result = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("doc_id") in wanted:
                    result.append(row)
    if {row["doc_id"] for row in result} != wanted or len(result) != len(wanted):
        raise QualityBoundsError("selected source coverage is incomplete or duplicated")
    return result


def freeze_files(root: Path) -> dict[str, str]:
    paths = list((root / "src").rglob("*.py")) + list((root / "config").glob("*.yaml"))
    paths += [root / path for path in (COLLECTED, DERIVED, LINKS, SEED, SEATING,
              Path("data/interim/phase4/relevance_split_manifest.csv"),
              DEV_GOLD / "documents.jsonl", DEV_GOLD / "cases.jsonl")]
    paths += list((root / "scripts").glob("*.py"))
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted(paths)}


def create_freeze(root: Path, path: Path, development_report: Path) -> dict:
    if path.parent.exists():
        raise QualityBoundsError("freeze requires a fresh directory")
    report = read(development_report)
    if report.get("quality_gate_status") != "development_only" or report.get("status") != "measured":
        raise QualityBoundsError("freeze requires an actual measured development report")
    versions = report.get("saved_inputs", {}).get("versions", {}).get("prompt_versions", {})
    if versions.get("extract") != EXTRACTION_PROMPT_CORRECTION:
        raise QualityBoundsError("development must first measure the corrected extraction version")
    wire_hash = transmitted_schema_sha256(groq_strict_schema(relevance_json_schema()))
    payload = {
        "freeze_version": "quality-freeze/v1", "frozen": True,
        "created_at": datetime.now(UTC).isoformat(), "provider": PROVIDER, "model": MODEL,
        "requested_temperature": 0.0, "sdk_retries": 0, "gateway_attempts": 1,
        "relevance_max_tokens": REL_TOKENS, "extraction_max_tokens": EXTRACT_TOKENS,
        "extraction_prompt": EXTRACTION_PROMPT_CORRECTION,
        "versions": version_summary(), "seats": seats(root),
        "development_report": development_report.relative_to(root).as_posix(),
        "development_report_sha256": sha(development_report),
        "input_sha256": freeze_files(root), "limitations": [LIMITATION],
        "relevance_lock": build_prompt_lock(provider=PROVIDER, model=MODEL, temperature=0.0,
            max_tokens=REL_TOKENS, transmitted_schema_sha256=wire_hash),
    }
    payload["versions"]["prompt_versions"]["extract"] = EXTRACTION_PROMPT_CORRECTION
    write_new(path, payload)
    write_new(path.parent / "relevance_lock.json", payload["relevance_lock"])
    return payload


def check_freeze(root: Path, path: Path) -> dict:
    payload = read(path)
    if payload.get("freeze_version") != "quality-freeze/v1" or payload.get("frozen") is not True:
        raise QualityBoundsError("not a valid frozen configuration")
    expected = {"provider": PROVIDER, "model": MODEL, "requested_temperature": 0.0,
                "sdk_retries": 0, "gateway_attempts": 1, "relevance_max_tokens": REL_TOKENS,
                "extraction_max_tokens": EXTRACT_TOKENS,
                "extraction_prompt": EXTRACTION_PROMPT_CORRECTION}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise QualityBoundsError("frozen settings do not match this bounded route")
    if payload.get("input_sha256") != freeze_files(root) or payload.get("seats") != seats(root):
        raise QualityBoundsError("code, configuration, sources, or seating changed after freeze")
    if sha(root / payload["development_report"]) != payload["development_report_sha256"]:
        raise QualityBoundsError("frozen development report changed")
    authorize_live_classification(split_name="holdout", holdout_unlocked=True,
        lock_path=path.parent / "relevance_lock.json", provider=PROVIDER, model=MODEL,
        temperature=0.0, max_tokens=REL_TOKENS,
        transmitted_schema_sha256=payload["relevance_lock"]["transmitted_schema_sha256"])
    return payload


def check_holdout_approval(root: Path, freeze: Path, pack: Path, gold: Path, approval: Path) -> dict:
    frozen = check_freeze(root, freeze)
    receipt = read(approval)
    if (receipt.get("human_approved") is not True or receipt.get("reviewer") != "Sunayana"
            or not receipt.get("approval_statement") or receipt.get("freeze_sha256") != sha(freeze)):
        raise QualityBoundsError("holdout labels require an explicit, retained human approval")
    manifest = read(pack / "manifest.json")
    wanted = set(frozen["seats"]["holdout"])
    if {row["doc_id"] for row in manifest["documents"] if row["gold_split"] == "holdout"} != wanted:
        raise QualityBoundsError("holdout pack must contain every reserved seat")
    docs = load_gold_documents(gold / "documents.jsonl")
    cases = load_gold_cases(gold / "cases.jsonl")
    if {row.doc_id for row in docs if row.split.value == "holdout"} != wanted:
        raise QualityBoundsError("approved gold holdout coverage is incomplete")
    if any(row.labeler_id != "Sunayana" for row in docs) or any(row.labeler_id != "Sunayana" for row in cases):
        raise QualityBoundsError("gold must record the actual approving human reviewer")
    require_case_counts(docs, cases)
    required_paths = [pack / "manifest.json", gold / "documents.jsonl", gold / "cases.jsonl"]
    required_paths += [pack / "packets" / f"{doc}.json" for doc in sorted(wanted)]
    for item in required_paths:
        if receipt.get("approved_sha256", {}).get(project_key(root, item)) != sha(rooted(root, item)):
            raise QualityBoundsError("approval does not bind the exact labels and source packets")
    for doc_id in wanted:
        packet = read(pack / "packets" / f"{doc_id}.json")
        if packet.get("gold_split") != "holdout" or packet.get("doc_id") != doc_id:
            raise QualityBoundsError("invalid holdout packet identity")
    texts = {doc: read(pack / "packets" / f"{doc}.json")["source_text"] for doc in wanted}
    if validate_gold_quotes(cases, texts):
        raise QualityBoundsError("approved gold contains non-verbatim evidence")
    return frozen


def check_successor_labels(root: Path, pack: Path, gold: Path, approval: Path) -> None:
    """Bind a new holdout experiment to the existing human labels, not the consumed freeze."""
    receipt = read(approval)
    if (receipt.get("human_approved") is not True or receipt.get("reviewer") != "Sunayana"
            or not receipt.get("approval_statement")):
        raise QualityBoundsError("holdout labels require an explicit, retained human approval")
    wanted = set(seats(root)["holdout"])
    manifest = read(pack / "manifest.json")
    if {row["doc_id"] for row in manifest["documents"] if row["gold_split"] == "holdout"} != wanted:
        raise QualityBoundsError("holdout pack must contain every reserved seat")
    docs = load_gold_documents(gold / "documents.jsonl")
    cases = load_gold_cases(gold / "cases.jsonl")
    if {row.doc_id for row in docs if row.split.value == "holdout"} != wanted:
        raise QualityBoundsError("approved gold holdout coverage is incomplete")
    if any(row.labeler_id != "Sunayana" for row in docs) or any(row.labeler_id != "Sunayana" for row in cases):
        raise QualityBoundsError("gold must record the actual approving human reviewer")
    require_case_counts(docs, cases)
    required_paths = [pack / "manifest.json", gold / "documents.jsonl", gold / "cases.jsonl"]
    required_paths += [pack / "packets" / f"{doc}.json" for doc in sorted(wanted)]
    for item in required_paths:
        if receipt.get("approved_sha256", {}).get(project_key(root, item)) != sha(rooted(root, item)):
            raise QualityBoundsError("approval does not bind the exact labels and source packets")
    for doc_id in wanted:
        packet = read(pack / "packets" / f"{doc_id}.json")
        if packet.get("gold_split") != "holdout" or packet.get("doc_id") != doc_id:
            raise QualityBoundsError("invalid holdout packet identity")
    texts = {doc: read(pack / "packets" / f"{doc}.json")["source_text"] for doc in wanted}
    if validate_gold_quotes(cases, texts):
        raise QualityBoundsError("approved gold contains non-verbatim evidence")


def run_quality(*, settings: Settings, split: str, output: Path, cache: Path,
                call_budget: int, dry_run: bool = False, freeze: Path | None = None,
                pack: Path | None = None, gold: Path | None = None,
                approval: Path | None = None, provider=None, candidate_prompt: str | None = None,
                candidate_relevance: str | None = None, successor: bool = False) -> dict:
    root = settings.project_root
    if split not in {"dev", "holdout"}:
        raise QualityBoundsError("only existing gold-dev and reserved gold-holdout seats are allowed")
    if successor and split != "holdout":
        raise QualityBoundsError("a successor measurement is only for a new holdout experiment")
    if successor and (candidate_prompt != EXTRACTION_PROMPT_CANDIDATE or candidate_relevance != RELEVANCE_PROMPT_CANDIDATE):
        raise QualityBoundsError("the successor holdout uses relevance/v6 and extract/v4 only")
    if candidate_prompt is not None and candidate_prompt not in {
        EXTRACTION_PROMPT_CANDIDATE,
        EXTRACTION_PROMPT_DEV_CANDIDATE,
    }:
        raise QualityBoundsError("Only the explicit extract/v4 candidate is allowed")
    if candidate_prompt == EXTRACTION_PROMPT_DEV_CANDIDATE and (split != "dev" or successor):
        raise QualityBoundsError("extract/v5 is allowed on the development split only")
    if candidate_relevance is not None and candidate_relevance != RELEVANCE_PROMPT_CANDIDATE:
        raise QualityBoundsError("Only the explicit relevance/v6 candidate is allowed")
    if candidate_prompt is not None and split != "dev" and not successor:
        raise QualityBoundsError("Only the explicit extract/v4 candidate is allowed, on gold-dev only")
    if candidate_relevance is not None and split != "dev" and not successor:
        raise QualityBoundsError("Only the explicit relevance/v6 candidate is allowed, on gold-dev only")
    effective_extract = candidate_prompt or EXTRACTION_PROMPT_CORRECTION
    effective_relevance = candidate_relevance or prompt_version("relevance")
    assigned = seats(root)
    wanted = set(assigned[split])
    if call_budget != 2 * len(wanted):
        raise QualityBoundsError("budget must reserve one relevance and one extraction attempt per seat")
    if output.exists():
        raise QualityBoundsError("output parent must be fresh")
    if settings.models.temperature != 0.0 or settings.models.relevance_choice()[:2] != (PROVIDER, MODEL):
        raise QualityBoundsError("configured provider, model, and temperature must match the evaluation pins")
    if split == "holdout":
        if successor:
            if not all((pack, gold, approval)):
                raise QualityBoundsError("successor holdout requires the approved pack, gold, and approval receipt")
            check_successor_labels(root, pack, gold, approval)
        else:
            if not all((freeze, pack, gold, approval)):
                raise QualityBoundsError("holdout requires freeze, source pack, approved gold, and approval receipt")
            check_holdout_approval(root, freeze, pack, gold, approval)
            if (freeze.parent / "measurement_claim.json").exists():
                raise QualityBoundsError("this frozen holdout configuration has already been claimed")
    if dry_run:
        return {"split": split, "documents": len(wanted), "maximum_provider_calls": call_budget,
                "provider_calls": 0, "records_written": 0, "dry_run": True}
    api_key = settings.secrets.require("groq_api_key", needed_for="bounded quality evaluation")
    documents = [CollectedDocument.model_validate(row) for row in selected_rows(root / COLLECTED, wanted)]
    derived = [DocumentDerived.model_validate(row) for row in selected_rows(root / DERIVED, wanted)]
    links = []
    for line in (root / LINKS).read_text(encoding="utf-8").splitlines():
        if line.strip():
            link = DuplicateLink.model_validate_json(line)
            if link.doc_id in wanted:
                links.append(link)
    if split == "holdout":
        by_id = {row.doc_id: row for row in derived}
        for doc in wanted:
            if read(pack / "packets" / f"{doc}.json")["source_text"] != by_id[doc].raw_text_audit:
                raise QualityBoundsError("approved packet source differs from the actual extraction source")
        if successor:
            # The claim stays inside this new output. The consumed freeze is not reused.
            write_new(output / "successor_claim.json", {
                "approval_sha256": sha(approval),
                "prompts": {"relevance": effective_relevance, "extract": effective_extract},
                "claimed_at": datetime.now(UTC).isoformat(),
                "prior_measurement": "consumed and unchanged",
            })
        else:
            # Exclusive claim before the first request. An interrupted run consumes
            # this measurement; it cannot be silently retried using another output.
            write_new(freeze.parent / "measurement_claim.json", {
            "freeze_sha256": sha(freeze), "approval_sha256": sha(approval),
            "output": output.relative_to(root).as_posix(), "claimed_at": datetime.now(UTC).isoformat(),
        })
    pricing = dict(input_usd_per_million=settings.models.estimated_input_usd_per_million,
                   output_usd_per_million=settings.models.estimated_output_usd_per_million,
                   cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million)
    common = dict(provider_name=PROVIDER, model_name=MODEL, api_key=api_key, provider=provider,
                  temperature=0.0, timeout_seconds=settings.models.timeout_seconds, max_retries=1,
                  cache_dir=cache, config_hash=settings.config_hash(), project_root=root, **pricing)
    relevance = run_phase4(documents, derived, links, output_dir=output / "relevance",
                          stages=["prefilter", "relevance"], max_tokens=REL_TOKENS,
                          author_salt=settings.secrets.author_salt,
                          confidence_review_below=settings.analysis.relevance.confidence_review_below,
                          provider_call_budget=len(wanted),
                          relevance_prompt_version=candidate_relevance, **common)
    decisions = [RelevanceDecision.model_validate_json(line) for line in
                 (output / "relevance/relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    extraction = run_extraction(doc_ids=sorted(wanted), model_decisions=decisions, human_decisions=[],
                               derived_by_id={row.doc_id: row for row in derived},
                               output_dir=output / "extraction", max_tokens=EXTRACT_TOKENS,
                               prompt_version_value=effective_extract,
                               call_budget=len(wanted), denylist=tuple(filter(None, [settings.secrets.author_salt])), **common)
    summary = {"split": split, "documents": len(wanted), "maximum_provider_calls": call_budget,
               "provider_calls": relevance.provider_calls + extraction.provider_calls,
               "relevance": asdict(relevance), "extraction": asdict(extraction),
               "human_overrides_used": False, "limitations": [LIMITATION],
               "provider": PROVIDER, "model": MODEL, "extraction_prompt": effective_extract,
               "relevance_prompt": effective_relevance,
               "sdk_retries": 0, "gateway_attempts": 1}
    # Paths from dataclasses are local destinations, never credentials or raw text.
    summary = json.loads(json.dumps(summary, default=str))
    write_new(output / "summary.json", summary)
    if split == "holdout" and not successor:
        write_new(freeze.parent / "measurement_completed.json", {
            "freeze_sha256": sha(freeze), "approval_sha256": sha(approval),
            "artifact_sha256": {p.relative_to(root).as_posix(): sha(p)
                                for p in sorted(output.rglob("*")) if p.is_file()},
        })
    return summary
