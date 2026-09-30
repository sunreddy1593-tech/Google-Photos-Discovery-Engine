#!/usr/bin/env python
"""CLI entry point for the discovery-engine pipeline.

``collect`` imports a pilot workbook. The import lives in ``src/collect``;
this file only parses arguments and passes the author salt through from
configuration. Every other subcommand is declared so ``--help`` shows the
pipeline, and refuses to run with the phase that will implement it.

``AUTHOR_SALT`` is read from the environment or ``.env``. It is not a
command argument and it is not printed.

Run ``python main.py collect --help`` for the workbook import.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, NoReturn

from src.core.config import ConfigError, load_settings
from src.core.logging import bind_context, configure_logging, get_logger
from src.core.versions import SCHEMA_VERSION, TAXONOMY_VERSION

#: Subcommand -> (help text, phase that implements it).
COMMANDS: Final[dict[str, tuple[str, int]]] = {
    "collect": ("Collect or import documents from a configured source", 2),
    "normalize": ("Normalize, redact, and hash documents into DocumentDerived", 3),
    "dedupe": ("Link exact and near duplicates; open review items", 3),
    "prefilter": ("Deterministic high-recall prefilter", 4),
    "relevance": ("Classify scope and relevance", 4),
    "extract": ("Extract evidence-backed retrieval cases", 5),
    "evaluate": ("Score the pipeline against the gold set", 6),
    "taxonomy": ("Generate and assign taxonomy clusters", 8),
    "analyze": ("Build funnel, memory map, journeys, and opportunities", 8),
    "export": ("Write the public export profile and the run manifest", 10),
    "rebuild": ("Replay from raw files and the response cache; compare hashes", 11),
    "run": ("Run several stages in order with checkpointing", 7),
}


def _not_implemented(command: str) -> NoReturn:
    help_text, phase = COMMANDS[command]
    print(
        f"'{command}' is not implemented yet.\n"
        f"  Purpose: {help_text}\n"
        f"  Arrives in: Phase {phase}\n"
        f"Phase 0 built the scaffold, configuration, logging, identifier helpers, "
        f"and the version registry only.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Google Photos remembered-item retrieval discovery engine. "
            "collect imports a workbook; later stages are declared and not built."
        ),
        epilog=(
            "Configuration lives in config/*.yaml; secrets in .env "
            "(see .env.example). The deterministic stages and the evaluator app "
            "both run without an API key."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"google-photos-retrieval-engine 0.1.0 "
            f"(schema {SCHEMA_VERSION}, taxonomy {TAXONOMY_VERSION})"
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    collect = subparsers.add_parser(
        "collect",
        help=f"{COMMANDS['collect'][0]} [Phase 2]",
        description=(
            "Import a pilot workbook into CollectedDocument records. "
            "AUTHOR_SALT is taken from the environment or .env and is never "
            "printed or accepted as an argument."
        ),
    )
    collect.add_argument(
        "--path",
        required=True,
        help="Path to the pilot workbook (.xlsx)",
    )
    collect.add_argument(
        "--output",
        required=True,
        help="Directory for the documents file and the import report",
    )
    collect.set_defaults(handler=_collect)

    run = subparsers.add_parser(
        "run",
        help=f"{COMMANDS['run'][0]} [Phase 3]",
        description=(
            "Run normalize and dedupe, or the offline Phase 4 prefilter and "
            "relevance stages. The command prints counts only."
        ),
    )
    run.add_argument(
        "--stages",
        required=True,
        help=(
            "Comma-separated stages. Implemented: normalize,dedupe "
            "or prefilter and relevance, in that order"
        ),
    )
    run.add_argument(
        "--input",
        default=None,
        help="collected_documents.jsonl from Phase 2 (default: the pilot import)",
    )
    run.add_argument(
        "--output",
        default=None,
        help="Directory for stage outputs",
    )
    run.add_argument(
        "--derived",
        default=None,
        help="documents_derived.jsonl from Phase 3",
    )
    run.add_argument(
        "--links",
        default=None,
        help="duplicate_links.jsonl from Phase 3",
    )
    run.add_argument("--limit", type=int, default=None, help="Process at most N documents")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts without writing or calling a provider",
    )
    run.add_argument("--resume", default=None, metavar="RUN_ID", help="Skip completed relevance work")
    run.add_argument(
        "--offline",
        action="store_true",
        help="Force the null provider. No network call is made.",
    )
    run.add_argument(
        "--split",
        choices=["development", "holdout", "all"],
        default="development",
        help=(
            "Live relevance classification defaults to development. "
            "Holdout requires --holdout-unlock and a prompt lock. "
            "Offline and dry-run runs are not filtered."
        ),
    )
    run.add_argument(
        "--holdout-unlock",
        action="store_true",
        help="Allow a live holdout classification. A prompt lock is still required.",
    )
    run.add_argument(
        "--prompt-lock",
        default="data/interim/phase4/relevance_prompt_lock.json",
        help="Prompt-lock artifact required for a live holdout classification",
    )
    run.add_argument(
        "--provider",
        choices=["groq", "anthropic"],
        default=None,
        help="Relevance provider. The default is config/models.yaml.",
    )
    run.set_defaults(handler=_run)

    smoke = subparsers.add_parser(
        "smoke",
        help="Development-only six-document relevance smoke run [Phase 4]",
        description=(
            "Classify the six development smoke documents, or plan that run "
            "with --dry-run. Holdout documents are rejected. The output "
            "directory is run-specific and is not the historical null-provider run."
        ),
    )
    smoke.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the smoke plan. No provider call and no files are written.",
    )
    smoke.add_argument(
        "--manifest",
        default="data/interim/phase4/relevance_smoke_manifest.csv",
        help="Six-document development smoke manifest",
    )
    smoke.add_argument(
        "--split-manifest",
        default="data/interim/phase4/relevance_split_manifest.csv",
        help="Phase 4 development/holdout manifest",
    )
    smoke.add_argument(
        "--output",
        default="data/interim/phase4/smoke",
        help="Parent directory. The run writes a new subdirectory under it.",
    )
    smoke.add_argument(
        "--historical",
        default="data/interim/phase4",
        help="Historical null-provider directory. Smoke will not write there.",
    )
    smoke.add_argument(
        "--cache",
        default="data/interim/cache",
        help="Existing relevance response cache",
    )
    smoke.add_argument(
        "--provider",
        choices=["groq", "anthropic"],
        default=None,
        help="Relevance provider. The default is config/models.yaml.",
    )
    smoke.set_defaults(handler=_smoke_relevance)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Score stored relevance decisions against the seed review [Phase 4]",
        description=(
            "Compare stored relevance decisions with the approved seed labels. "
            "This does not classify documents and does not call a provider. "
            "Phase 6 gold evaluation is not implemented."
        ),
    )
    evaluate.add_argument(
        "--split",
        required=True,
        choices=["development", "holdout", "all"],
        help="Which seed split to score",
    )
    evaluate.add_argument(
        "--seed",
        default="data/interim/phase4/relevance_seed_review.csv",
        help="Approved seed review CSV",
    )
    evaluate.add_argument(
        "--decisions",
        default="data/interim/phase4/relevance_decisions.jsonl",
        help="Stored relevance decisions. Missing file means every document is missing.",
    )
    evaluate.add_argument(
        "--manifest",
        default="data/interim/phase4/relevance_split_manifest.csv",
        help="Development/holdout manifest. A valid file is kept.",
    )
    evaluate.add_argument(
        "--reviews",
        default="data/interim/phase4/review_queue.jsonl",
        help="Review queue used only to count prefilter/classifier conflicts",
    )
    evaluate.add_argument(
        "--run-manifest",
        default="data/interim/phase4/run_manifest.json",
        help="Existing run manifest for cache, token, and cost totals",
    )
    evaluate.add_argument(
        "--output",
        default="data/interim/phase4",
        help="Directory for relevance_evaluation.json and relevance_evaluation.md",
    )
    evaluate.set_defaults(handler=_evaluate_relevance)

    for name, (help_text, phase) in COMMANDS.items():
        if name in {"collect", "run", "evaluate", "smoke"}:
            continue
        sub = subparsers.add_parser(
            name, help=f"{help_text} [Phase {phase}]", description=help_text
        )
        sub.add_argument("--limit", type=int, help="Process at most N records")
        sub.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would happen without writing or calling a provider",
        )
        if name in {"collect", "run"}:
            sub.add_argument("--source", help="Configured source name")
        if name in {"run", "rebuild"}:
            sub.add_argument("--resume", metavar="RUN_ID", help="Resume a run")

    check = subparsers.add_parser(
        "check-config",
        help="Validate config/*.yaml and report credential presence [Phase 0]",
        description=(
            "Load and validate configuration. Reports which credentials are "
            "present as booleans, never their values."
        ),
    )
    check.set_defaults(handler=_check_config)

    return parser


def _collect(args: argparse.Namespace) -> int:
    """Dispatch workbook import. The salt stays inside configuration."""
    from src.collect.cli import run_workbook_import

    try:
        settings = load_settings()
        author_salt = settings.secrets.require(
            "author_salt", needed_for="author hashing at workbook import"
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    return run_workbook_import(args.path, args.output, author_salt=author_salt)


def _run(args: argparse.Namespace) -> int:
    """Dispatch implemented stages. Later stages still refuse."""
    stages = [part.strip() for part in str(args.stages).split(",") if part.strip()]
    if stages == ["normalize", "dedupe"]:
        return _run_phase3(args)
    if stages in (["prefilter"], ["relevance"], ["prefilter", "relevance"]):
        return _run_phase4(args, stages)
    print(
        "Implemented stages are normalize,dedupe or prefilter and relevance, "
        "in that order.",
        file=sys.stderr,
    )
    return 1


def _run_phase3(args: argparse.Namespace) -> int:
    from src.pipeline.runner import (
        DEFAULT_INPUT,
        DEFAULT_OUTPUT,
        format_summary,
        load_collected_documents,
        run_normalize_dedupe,
    )

    source = Path(args.input) if args.input else DEFAULT_INPUT
    destination = Path(args.output) if args.output else DEFAULT_OUTPUT
    if not source.is_file():
        print(f"Collected documents not found: {source.name}", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    documents = load_collected_documents(source)
    if args.limit is not None:
        documents = documents[: args.limit]
    if args.dry_run:
        print(f"dry-run: normalize,dedupe would process {len(documents)} documents")
        return 0
    result = run_normalize_dedupe(documents, settings.analysis.dedupe, destination)
    print(format_summary(result), end="")
    return 0


def _run_phase4(args: argparse.Namespace, stages: list[str]) -> int:
    from src.models.duplicate_link import DuplicateLink
    from src.pipeline.runner import DEFAULT_INPUT, load_collected_documents
    from src.pipeline.stages import format_phase4_summary, run_phase4

    source = Path(args.input) if args.input else DEFAULT_INPUT
    destination = Path(args.output) if args.output else Path("data/interim/phase4")
    derived_path = (
        Path(args.derived) if args.derived else Path("data/interim/phase3/documents_derived.jsonl")
    )
    links_path = (
        Path(args.links) if args.links else Path("data/interim/phase3/duplicate_links.jsonl")
    )
    if not source.is_file():
        print(f"Collected documents not found: {source.name}", file=sys.stderr)
        return 1
    if not derived_path.is_file():
        print(f"Derived documents not found: {derived_path.name}", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    from src.models.document_derived import DocumentDerived

    documents = load_collected_documents(source)
    derived = [
        DocumentDerived.model_validate_json(line)
        for line in derived_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    links = []
    if links_path.is_file():
        links = [
            DuplicateLink.model_validate_json(line)
            for line in links_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    offline = bool(args.offline) or bool(args.dry_run)
    provider_name, model_name, env_name, api_key = _relevance_runtime(
        settings, getattr(args, "provider", None)
    )
    if "relevance" in stages and not offline:
        from src.relevance.lock import HoldoutLocked, authorize_live_classification
        from src.relevance.split import SplitError, doc_ids_for_split, load_split_manifest

        manifest_path = Path("data/interim/phase4/relevance_split_manifest.csv")
        try:
            split_name = authorize_live_classification(
                split_name=args.split,
                holdout_unlocked=bool(args.holdout_unlock),
                lock_path=args.prompt_lock,
                provider=provider_name,
                model=model_name,
                temperature=settings.models.temperature,
                max_tokens=settings.models.max_tokens,
            )
            allowed = set(doc_ids_for_split(load_split_manifest(manifest_path), split_name))
        except (HoldoutLocked, SplitError) as exc:
            print(f"Holdout locked: {exc}", file=sys.stderr)
            return 1
        documents = [document for document in documents if document.doc_id in allowed]
        derived = [row for row in derived if row.doc_id in allowed]
        if not documents:
            print("No documents in the authorized split.", file=sys.stderr)
            return 1
        if not api_key:
            print(f"{env_name} is not set.", file=sys.stderr)
            return 1
    result = run_phase4(
        documents,
        derived,
        links,
        output_dir=destination,
        stages=stages,
        limit=args.limit,
        dry_run=bool(args.dry_run),
        resume=args.resume,
        offline=offline,
        provider_name=provider_name,
        model_name=model_name,
        api_key=None if offline else api_key,
        author_salt=settings.secrets.author_salt,
        temperature=settings.models.temperature,
        max_tokens=settings.models.max_tokens,
        timeout_seconds=float(settings.models.timeout_seconds),
        max_retries=settings.models.max_retries,
        input_usd_per_million=settings.models.estimated_input_usd_per_million,
        output_usd_per_million=settings.models.estimated_output_usd_per_million,
        cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
        confidence_review_below=settings.analysis.relevance.confidence_review_below,
        config_hash=settings.config_hash(),
        project_root=settings.project_root,
    )
    print(format_phase4_summary(result), end="")
    return 0


def _smoke_relevance(args: argparse.Namespace) -> int:
    """Plan or run the six-document development smoke. Dry-run makes no call."""
    from src.pipeline.smoke_run import SmokeRunError, plan_smoke_run
    from src.relevance.smoke import SmokeSelectionError, ensure_smoke_manifest
    from src.relevance.split import SplitError, load_split_manifest

    split_path = Path(args.split_manifest)
    if not split_path.is_file():
        print(f"Split manifest not found: {split_path.name}", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
        provider_name, model_name, env_name, api_key = _relevance_runtime(
            settings, args.provider
        )
        assignments = load_split_manifest(split_path)
        doc_ids = ensure_smoke_manifest(args.manifest, assignments)
        plan = plan_smoke_run(
            doc_ids,
            assignments,
            output_parent=args.output,
            historical_dir=args.historical,
            cache_dir=args.cache,
            provider=provider_name,
            model=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            dry_run=True if args.dry_run else False,
            offline=bool(args.dry_run),
        )
    except (SmokeSelectionError, SplitError, SmokeRunError, ConfigError) as exc:
        print(f"Smoke error: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print("Relevance smoke dry-run")
        print(f"  documents            {len(plan.doc_ids)}")
        print(f"  output               {plan.output_dir}")
        print(f"  prompt               {plan.prompt_id} {plan.prompt_version}")
        print(f"  provider             {plan.provider}")
        print(f"  model                {plan.model}")
        print(f"  temperature          {plan.temperature}")
        print(f"  effective temperature { _effective_temperature(plan.provider, plan.temperature) }")
        print(f"  max tokens           {plan.max_tokens}")
        print(f"  cache                {plan.cache_dir}")
        print(f"  call budget          {plan.call_budget}")
        print("  provider calls       0")
        return 0

    if not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1

    from src.models.document_derived import DocumentDerived
    from src.models.duplicate_link import DuplicateLink
    from src.pipeline.runner import DEFAULT_INPUT, load_collected_documents
    from src.llm.providers.base import ProviderFatalError
    from src.pipeline.smoke_run import run_smoke

    source = DEFAULT_INPUT
    derived_path = Path("data/interim/phase3/documents_derived.jsonl")
    links_path = Path("data/interim/phase3/duplicate_links.jsonl")
    if not source.is_file() or not derived_path.is_file():
        print("Collected or derived documents were not found.", file=sys.stderr)
        return 1
    documents = load_collected_documents(source)
    derived = [
        DocumentDerived.model_validate_json(line)
        for line in derived_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    links = []
    if links_path.is_file():
        links = [
            DuplicateLink.model_validate_json(line)
            for line in links_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    try:
        finished = run_smoke(
            documents,
            derived,
            links,
            assignments,
            doc_ids,
            output_parent=args.output,
            historical_dir=args.historical,
            cache_dir=args.cache,
            provider=provider_name,
            model=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            dry_run=False,
            offline=False,
            api_key=api_key,
            project_root=settings.project_root,
            max_retries=settings.models.max_retries,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            list_price_source=settings.models.list_price_source,
            list_price_retrieved_on=settings.models.list_price_retrieved_on,
        )
    except (SmokeSelectionError, SmokeRunError, ProviderFatalError) as exc:
        print(f"Smoke error: {exc}", file=sys.stderr)
        return 1
    print(f"Relevance smoke wrote {finished.output_dir}")
    print(f"  provider calls       {finished.provider_calls}")
    print(f"  call budget          {finished.call_budget}")
    return 0


def _relevance_runtime(settings, override: str | None) -> tuple[str, str, str, str | None]:
    """Provider, model, environment-variable name, and key. The key may be absent."""
    provider, model, env_name = settings.models.relevance_choice(override)
    return provider, model, env_name, getattr(settings.secrets, env_name.lower(), None)


def _effective_temperature(provider: str, requested: float) -> float:
    if provider == "groq":
        from src.llm.providers.groq import effective_temperature

        return effective_temperature(requested)
    return float(requested)


def _evaluate_relevance(args: argparse.Namespace) -> int:
    """Score stored decisions. This path does not construct a provider."""
    import json

    from src.models.enums import ReasonCode
    from src.models.relevance import RelevanceDecision
    from src.relevance.evaluate import (
        EvaluationError,
        OperationStats,
        evaluate_relevance,
        format_evaluation_summary,
        write_evaluation_artifacts,
    )
    from src.relevance.seed import SeedReviewError, load_seed_review
    from src.relevance.split import SplitError, ensure_split_manifest
    from src.review.queue import ReviewItem

    seed_path = Path(args.seed)
    if not seed_path.is_file():
        print(f"Seed review not found: {seed_path.name}", file=sys.stderr)
        return 1
    try:
        labels = load_seed_review(seed_path)
        assignments = ensure_split_manifest(args.manifest, seed_path)
    except (SeedReviewError, SplitError) as exc:
        print(f"Split error: {exc}", file=sys.stderr)
        return 1

    decisions: list[RelevanceDecision] = []
    decisions_path = Path(args.decisions)
    if decisions_path.is_file():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions.append(RelevanceDecision.model_validate_json(line))

    conflict_ids: list[str] = []
    reviews_path = Path(args.reviews)
    if reviews_path.is_file():
        for line in reviews_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = ReviewItem.model_validate_json(line)
            if item.reason_code is ReasonCode.prefilter_classifier_conflict:
                conflict_ids.append(item.target_id)

    operations = OperationStats()
    manifest_path = Path(args.run_manifest)
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        cache = payload.get("cache") or {}
        tokens = payload.get("tokens") or {}
        operations = OperationStats(
            provider_calls=int(cache.get("provider_calls") or 0),
            cache_hits=int(cache.get("hits") or 0),
            cache_misses=int(cache.get("misses") or 0),
            input_tokens=int(tokens.get("input_tokens") or 0),
            output_tokens=int(tokens.get("output_tokens") or 0),
            estimated_cost_usd=float(tokens.get("estimated_cost_usd") or 0.0),
        )

    threshold = 0.7
    try:
        settings = load_settings()
        threshold = settings.analysis.relevance.confidence_review_below
    except ConfigError:
        threshold = 0.7

    try:
        report = evaluate_relevance(
            labels,
            decisions,
            assignments,
            split_name=args.split,
            confidence_review_below=threshold,
            conflict_decision_ids=conflict_ids,
            operations=operations,
        )
    except EvaluationError as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 1
    write_evaluation_artifacts(args.output, report)
    print(format_evaluation_summary(report), end="")
    return 0


def _check_config(_args: argparse.Namespace) -> int:
    """Validate configuration and summarize it without revealing any secret."""
    log = get_logger("cli")
    try:
        settings = load_settings()
    except ConfigError as exc:
        log.error("configuration invalid", extra={"reason": str(exc)})
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    present = sorted(
        field
        for field in (
            "anthropic_api_key",
            "groq_api_key",
            "openai_api_key",
            "author_salt",
            "reddit_client_id",
            "reddit_client_secret",
            "youtube_api_key",
        )
        if settings.secrets.has(field)
    )

    log.info(
        "configuration loaded",
        extra={
            "config_dir": str(settings.config_dir),
            "config_hash": settings.config_hash(),
            "provider": settings.models.provider,
            "taxonomy_version": settings.taxonomy.version,
            "cluster_count": len(settings.taxonomy.clusters),
            "enabled_sources": sorted(settings.enabled_sources()),
            "credentials_present": present,
        },
    )

    # ASCII only: this runs on a Windows console whose default code page cannot
    # encode an em-dash, and a UnicodeEncodeError in a config check would be an
    # absurd way to fail.
    print(f"Configuration OK ({settings.config_dir})")
    print(f"  config hash          {settings.config_hash()[:16]}")
    print(f"  provider             {settings.models.provider}")
    print(
        f"  taxonomy             {settings.taxonomy.version} "
        f"({len(settings.taxonomy.clusters)} clusters)"
    )
    print(
        f"  enabled sources      "
        f"{', '.join(sorted(settings.enabled_sources())) or 'none'}"
    )
    print(
        f"  credentials present  "
        f"{', '.join(present) or 'none (deterministic mode)'}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    if args.command is None:
        parser.print_help()
        return 0

    handler = getattr(args, "handler", None)
    if handler is None:
        _not_implemented(args.command)

    with bind_context(stage=args.command):
        return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
