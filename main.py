#!/usr/bin/env python
"""CLI entry point for the discovery-engine pipeline.

``collect --path`` imports a pilot workbook. ``collect --youtube`` reads a
video-URL list and collects published comments into ``CollectedDocument``
records. The import and the collector live in ``src/collect``; this file only
parses arguments and passes secrets through from configuration.

``AUTHOR_SALT`` and ``YOUTUBE_API_KEY`` are read from the environment or
``.env``. They are not command arguments and they are not printed.

Run ``python main.py collect --help`` for both collection modes.
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
            "collect imports a workbook or collects YouTube comments."
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
            "Import a pilot workbook, or collect published YouTube comments, "
            "into CollectedDocument records. AUTHOR_SALT and YOUTUBE_API_KEY "
            "come from the environment or .env and are never printed or "
            "accepted as arguments. YouTube collection does not classify "
            "relevance or extract cases."
        ),
    )
    collect.add_argument(
        "--path",
        default=None,
        help="Path to the pilot workbook (.xlsx). Workbook mode.",
    )
    collect.add_argument(
        "--youtube",
        action="store_true",
        help="Collect published comments for a video URL list. Not workbook import.",
    )
    collect.add_argument(
        "--videos",
        default=None,
        help="Text file with one public YouTube video URL per line.",
    )
    collect.add_argument(
        "--document-limit",
        type=int,
        default=None,
        help="Maximum new CollectedDocument rows this YouTube run may write.",
    )
    collect.add_argument(
        "--request-budget",
        type=int,
        default=None,
        help="Maximum YouTube Data API requests this run may make.",
    )
    collect.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the collection plan and write nothing. Makes no requests.",
    )
    collect.add_argument(
        "--source",
        default=None,
        help="Configured source name: youtube or reddit.",
    )
    collect.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Alias of --document-limit for a single source.",
    )
    collect.add_argument(
        "--scaled",
        action="store_true",
        help="Checkpointed YouTube and Reddit collection, then a source funnel.",
    )
    collect.add_argument(
        "--resume",
        action="store_true",
        help="Skip a source whose checkpoint in --output is already finished.",
    )
    collect.add_argument(
        "--output",
        required=True,
        help="Directory for collected documents and the collection report",
    )
    collect.set_defaults(handler=_collect)
    collect.add_argument("--n8n-export", type=Path, help="Import an original-post collection JSON envelope")
    collect.add_argument("--n8n-collect", type=Path, help="Bounded collection-only webhook; file of thread URLs")
    collect.add_argument(
        "--reddit",
        action="store_true",
        help="Collect Reddit read-only when limits are set. Skips when credentials are absent.",
    )

    run = subparsers.add_parser(
        "run",
        help=f"{COMMANDS['run'][0]} [Phase 3]",
        description=(
            "Run normalize and dedupe, the Phase 4 relevance stages, or extract. "
            "Unrestricted live extraction is refused. --pilot prepares the "
            "five-document development extraction pilot. --diagnostic prepares "
            "one synthetic extraction request. The command prints counts only."
        ),
    )
    run.add_argument(
        "--stages",
        required=True,
        help=(
            "Comma-separated stages. Implemented: normalize,dedupe, "
            "prefilter and relevance, or extract"
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
    run.add_argument(
        "--cache",
        default=None,
        help="Relevance response cache. The default is the output directory's sibling cache.",
    )
    run.add_argument(
        "--call-budget",
        type=int,
        default=None,
        help="Maximum external provider attempts for this run. Cache hits are not attempts.",
    )
    run.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=(
            "Gateway attempts per document. 1 means one attempt and no retry. "
            "The default is config/models.yaml. The six-document smoke budget is unchanged. "
            "The extraction pilot requires 1. The extraction diagnostic requires 1."
        ),
    )
    run.add_argument(
        "--pilot",
        action="store_true",
        help=(
            "Five-document development extraction pilot. "
            "Unrestricted live extraction stays refused. "
            "The pilot uses Groq, one attempt, and at most five external calls."
        ),
    )
    run.add_argument(
        "--diagnostic",
        action="store_true",
        help=(
            "One synthetic extraction request. "
            "Cannot be combined with --pilot or pointed at real documents. "
            "Uses Groq, one attempt, and one external call."
        ),
    )
    run.add_argument(
        "--pilot-doc",
        default=None,
        metavar="DOC_ID",
        help="With --pilot, diagnose one of the two failed core seats; one external call, no retry.",
    )
    run.add_argument(
        "--pilot-max-tokens",
        type=int,
        default=None,
        metavar="8192",
        help=(
            "Opt into an 8192-token completion limit. With --pilot-doc, one core seat "
            "and one call. Without it, the five-document manifest, requiring "
            "--call-budget 4 and --max-retries 1."
        ),
    )
    run.add_argument(
        "--development-corpus",
        action="store_true",
        help=(
            "Extract the full frozen development split. "
            "Holdout documents are refused. One attempt, no retry, "
            "and the 8192-token completion limit. "
            "--call-budget must equal the eligible document count. "
            "Unrestricted live extraction stays refused."
        ),
    )
    run.add_argument(
        "--research-batch",
        action="store_true",
        help=(
            "At most 20 documents that are not in the frozen seed split. "
            "Dry-run makes no provider call. Live relevance and extraction "
            "require --call-budget and --max-retries 1. The five-document "
            "pilot is not used."
        ),
    )
    run.add_argument(
        "--document-limit",
        type=int,
        default=None,
        help="Research batch size. Required with --research-batch. Maximum 20.",
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

    browse = subparsers.add_parser(
        "browse",
        help="Open the local evidence browser",
        description=(
            "Read saved development outputs and serve a local page. "
            "Holdout text is not loaded. No model is called and no API key is read."
        ),
    )
    browse.add_argument("--host", default="127.0.0.1")
    browse.add_argument("--port", type=int, default=8765)
    browse.set_defaults(handler=_browse)

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
    """Dispatch workbook import or YouTube collection. Secrets stay in configuration."""
    if args.limit is not None and args.document_limit is None:
        args.document_limit = args.limit
    if args.source == "youtube":
        args.youtube = True
    elif args.source == "reddit":
        args.reddit = True
    elif args.source not in {None, "manual"}:
        print("Unknown collection source. Use youtube, reddit, or manual.", file=sys.stderr)
        return 1
    if args.scaled:
        return _collect_scaled(args)
    if args.reddit:
        if any((args.n8n_export, args.n8n_collect, args.path, args.youtube)):
            print("Choose exactly one collection mode.", file=sys.stderr)
            return 1
        return _collect_reddit(args)
    if args.n8n_export or args.n8n_collect:
        if sum(bool(value) for value in (args.n8n_export, args.n8n_collect, args.path, args.youtube)) != 1:
            print("Choose exactly one collection mode.", file=sys.stderr)
            return 1
        import json
        from src.collect.community import import_payload, collect_webhook
        try:
            settings = load_settings()
            salt = settings.secrets.require("author_salt", needed_for="community collection")
            if args.document_limit is None:
                raise ValueError("Community collection requires --document-limit (1–20)")
            if args.n8n_export:
                result = import_payload(json.loads(args.n8n_export.read_text(encoding="utf-8")),
                                        Path(args.output), author_salt=salt,
                                        document_limit=args.document_limit, dry_run=args.dry_run)
            else:
                if args.request_budget is None:
                    raise ValueError("Community webhook requires --request-budget (1–20)")
                result = collect_webhook(args.n8n_collect, Path(args.output),
                    webhook_url=settings.secrets.require("n8n_collection_webhook_url", needed_for="collection-only n8n"),
                    key=settings.secrets.require("n8n_webhook_key", needed_for="authenticated n8n collection"),
                    author_salt=salt, document_limit=args.document_limit,
                    request_budget=args.request_budget, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 0
        except (ValueError, OSError, ConfigError):
            print("Community collection refused. Check bounds, credentials and original-post contract; no retry.", file=sys.stderr)
            return 1
    if args.youtube and args.path:
        print("Pass either --path or --youtube, not both.", file=sys.stderr)
        return 1
    if args.dry_run and not (args.youtube or args.reddit):
        print("--dry-run applies to YouTube, Reddit, or scaled collection.", file=sys.stderr)
        return 1
    if args.youtube:
        return _collect_youtube(args)
    if not args.path:
        print(
            "Workbook import requires --path. YouTube collection requires --youtube.",
            file=sys.stderr,
        )
        return 1
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


def _collect_reddit(args: argparse.Namespace) -> int:
    """Skip when credentials are absent. A bounded live call needs both limits."""
    from src.collect.reddit import collect_reddit, collect_reddit_live

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    secrets = settings.secrets
    if args.document_limit is None or args.request_budget is None:
        report = collect_reddit(
            client_id=secrets.reddit_client_id,
            client_secret=secrets.reddit_client_secret,
            user_agent=secrets.reddit_user_agent,
            author_salt=secrets.author_salt or "unused",
        )
    else:
        try:
            report = collect_reddit_live(
                client_id=secrets.reddit_client_id,
                client_secret=secrets.reddit_client_secret,
                user_agent=secrets.reddit_user_agent,
                author_salt=secrets.author_salt or "",
                output_dir=args.output,
                document_limit=args.document_limit,
                request_budget=args.request_budget,
                dry_run=bool(args.dry_run),
            )
        except (ConfigError, ValueError, OSError) as exc:
            print(f"Reddit collection stopped: {exc.__class__.__name__}", file=sys.stderr)
            return 1
    print(report.reason)
    print(f"  requests made        {report.requests_made}")
    print(f"  documents written    {len(report.documents)}")
    return 0


def _collect_scaled(args: argparse.Namespace) -> int:
    """Collect YouTube and Reddit within bounds, then record the source funnel."""
    import json

    from src.collect.reddit import collect_reddit_live, credentials_present
    from src.collect.scaled import (
        BASELINE_COLLECTIONS,
        CORPUS_TARGET,
        dedupe,
        load_rows,
        run_scaled_collection,
    )
    from src.collect.youtube import collect_youtube_comments

    if args.document_limit is None or args.request_budget is None:
        print(
            "Scaled collection requires --document-limit and --request-budget.",
            file=sys.stderr,
        )
        return 1
    try:
        settings = load_settings()
        author_salt = settings.secrets.require(
            "author_salt", needed_for="author hashing during scaled collection"
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    secrets = settings.secrets
    existing = [Path(path) for path in BASELINE_COLLECTIONS]
    baseline = dedupe(load_rows(existing))
    shortfall = max(0, CORPUS_TARGET - len(baseline))
    youtube_limit = min(args.document_limit, shortfall + 50) if shortfall else 0
    reddit_on = credentials_present(
        secrets.reddit_client_id,
        secrets.reddit_client_secret,
        secrets.reddit_user_agent,
    )
    youtube_on = bool(secrets.youtube_api_key)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "baseline_documents": len(baseline),
                    "youtube_document_limit": youtube_limit if youtube_on else 0,
                    "youtube": "configured" if youtube_on else "source disabled",
                    "reddit": "configured" if reddit_on else "source disabled",
                    "requests_made": 0,
                    "documents_written": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    output = Path(args.output)
    videos = args.videos or "config/youtube_seed_videos.txt"

    def youtube() -> dict[str, object]:
        if not youtube_on or youtube_limit < 1:
            return {
                "source": "youtube",
                "status": "skipped",
                "reason": "source disabled" if not youtube_on else "corpus target already met",
                "requests_made": 0,
                "documents_written": 0,
                "stopped_reason": None,
            }
        result = collect_youtube_comments(
            videos,
            output / "youtube",
            api_key=secrets.youtube_api_key or "",
            author_salt=author_salt,
            document_limit=youtube_limit,
            request_budget=args.request_budget,
        )
        stopped = result.report.stopped_reason
        status = "collected"
        if stopped in {"rate_limit", "quota"}:
            status = "rate_limited"
        elif stopped in {"api_error", "transport_error"}:
            status = "failed"
        return {
            "source": "youtube",
            "status": status,
            "reason": stopped or "collected",
            "requests_made": result.report.requests_made,
            "documents_written": result.report.documents_written,
            "stopped_reason": stopped,
        }

    def reddit() -> dict[str, object]:
        if not reddit_on:
            return {
                "source": "reddit",
                "status": "skipped",
                "reason": "source disabled: Reddit credentials are absent",
                "requests_made": 0,
                "documents_written": 0,
                "stopped_reason": None,
            }
        report = collect_reddit_live(
            client_id=secrets.reddit_client_id,
            client_secret=secrets.reddit_client_secret,
            user_agent=secrets.reddit_user_agent,
            author_salt=author_salt,
            output_dir=output / "reddit",
            document_limit=min(100, args.document_limit),
            request_budget=min(40, args.request_budget),
        )
        if report.skipped:
            return {
                "source": "reddit",
                "status": "skipped",
                "reason": report.reason,
                "requests_made": 0,
                "documents_written": 0,
                "stopped_reason": None,
            }
        status = "collected"
        if report.stopped_reason == "rate_limited":
            status = "rate_limited"
        elif report.stopped_reason == "source_blocked":
            status = "failed"
        return {
            "source": "reddit",
            "status": status,
            "reason": report.stopped_reason or "collected",
            "requests_made": report.requests_made,
            "documents_written": len(report.documents),
            "stopped_reason": report.stopped_reason,
        }

    summary = run_scaled_collection(
        output_dir=output,
        existing_paths=existing,
        youtube=youtube,
        reddit=reddit,
        resume=bool(getattr(args, "resume", False)),
        run_id="phase7-scaled",
    )
    public = {
        key: summary[key]
        for key in (
            "documents",
            "by_platform",
            "by_source_type",
            "source_types",
            "concentration_over_threshold",
            "corpus_target_met",
            "sources",
            "model_stages_run",
        )
    }
    print(json.dumps(public, indent=2, sort_keys=True))
    return 0


def _collect_youtube(args: argparse.Namespace) -> int:
    """Bounded YouTube comment collection. No relevance or extraction stage."""
    from src.collect.cli import run_youtube_collection

    if not args.videos:
        print("YouTube collection requires --videos.", file=sys.stderr)
        return 1
    if args.document_limit is None or args.request_budget is None:
        print(
            "YouTube collection requires --document-limit and --request-budget.",
            file=sys.stderr,
        )
        return 1
    try:
        settings = load_settings()
        api_key = settings.secrets.require(
            "youtube_api_key", needed_for="YouTube comment collection"
        )
        author_salt = settings.secrets.require(
            "author_salt", needed_for="author hashing at YouTube collection"
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    return run_youtube_collection(
        args.videos,
        args.output,
        api_key=api_key,
        author_salt=author_salt,
        document_limit=args.document_limit,
        request_budget=args.request_budget,
        dry_run=bool(args.dry_run),
    )


def _research_settings():
    try:
        return load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return None


def _research_dry_run(args: argparse.Namespace) -> int:
    from src.pipeline.research_batch import (
        ResearchBatchError,
        format_research_plan,
        plan_research_batch,
    )

    settings = _research_settings()
    if settings is None:
        return 1
    try:
        plan = plan_research_batch(
            args.input,
            args.output,
            document_limit=args.document_limit,
            dedupe_config=settings.analysis.dedupe,
            model_name=settings.models.groq_relevance_model,
        )
    except ResearchBatchError as exc:
        print(f"Research batch error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Collected documents not found: {Path(args.input).name}", file=sys.stderr)
        return 1
    print(
        format_research_plan(
            plan,
            output_dir=args.output,
            model_name=settings.models.groq_relevance_model,
            max_tokens=settings.models.max_tokens,
        ),
        end="",
    )
    if plan.provenance_failures:
        return 1
    if plan.provider_calls or plan.files_written:
        print("Research batch dry-run made a call or wrote a file.", file=sys.stderr)
        return 1
    return 0


def _research_normalize(args: argparse.Namespace) -> int:
    from src.pipeline.research_batch import ResearchBatchError, selected_documents
    from src.pipeline.runner import format_summary, run_normalize_dedupe

    settings = _research_settings()
    if settings is None:
        return 1
    try:
        from src.pipeline.research_batch import assert_output_separate

        output = assert_output_separate(args.output)
        documents = selected_documents(args.input, document_limit=args.document_limit)
    except ResearchBatchError as exc:
        print(f"Research batch error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Collected documents not found: {Path(args.input).name}", file=sys.stderr)
        return 1
    if not documents:
        print("Research batch normalize: 0 documents outside the frozen split")
        return 0
    result = run_normalize_dedupe(documents, settings.analysis.dedupe, output / "normalize")
    print(format_summary(result), end="")
    return 0


def _research_relevance(args: argparse.Namespace) -> int:
    from src.models.document_derived import DocumentDerived
    from src.models.duplicate_link import DuplicateLink
    from src.pipeline.research_batch import (
        CACHE_DIR,
        RESEARCH_PROVIDER,
        ResearchBatchError,
        plan_research_batch,
        selected_documents,
    )
    from src.pipeline.stages import format_phase4_summary, run_phase4

    if args.call_budget is None or args.max_retries != 1:
        print(
            "Research batch relevance requires --call-budget and --max-retries 1.",
            file=sys.stderr,
        )
        return 1
    settings = _research_settings()
    if settings is None:
        return 1
    provider_name, model_name, env_name, api_key = _relevance_runtime(settings, RESEARCH_PROVIDER)
    if provider_name != RESEARCH_PROVIDER or model_name != settings.models.groq_relevance_model:
        print("Research batch relevance uses Groq openai/gpt-oss-120b.", file=sys.stderr)
        return 1
    try:
        from src.pipeline.research_batch import assert_output_separate

        output = assert_output_separate(args.output)
        plan = plan_research_batch(
            args.input,
            output,
            document_limit=args.document_limit,
            dedupe_config=settings.analysis.dedupe,
            model_name=model_name,
        )
    except ResearchBatchError as exc:
        print(f"Research batch error: {exc}", file=sys.stderr)
        return 1
    if plan.provenance_failures:
        print("Research batch error: collection records failed provenance checks", file=sys.stderr)
        return 1
    if args.call_budget != plan.relevance_requests:
        print(
            f"Research batch relevance allows {plan.relevance_requests} external requests.",
            file=sys.stderr,
        )
        return 1
    if plan.relevance_requests == 0:
        print("Research batch relevance: 0 requests")
        return 0
    if not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1
    normalize = output / "normalize"
    derived_path = normalize / "documents_derived.jsonl"
    links_path = normalize / "duplicate_links.jsonl"
    if not derived_path.is_file():
        print("Normalize the research batch before relevance.", file=sys.stderr)
        return 1
    documents = selected_documents(args.input, document_limit=args.document_limit)
    derived = [
        DocumentDerived.model_validate_json(line)
        for line in derived_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    links = [
        DuplicateLink.model_validate_json(line)
        for line in links_path.read_text(encoding="utf-8").splitlines()
        if links_path.is_file() and line.strip()
    ]
    result = run_phase4(
        documents,
        derived,
        links,
        output_dir=output / "relevance",
        stages=["prefilter", "relevance"],
        dry_run=False,
        offline=False,
        provider_name=provider_name,
        model_name=model_name,
        api_key=api_key,
        author_salt=settings.secrets.author_salt,
        temperature=settings.models.temperature,
        max_tokens=settings.models.max_tokens,
        timeout_seconds=settings.models.timeout_seconds,
        max_retries=1,
        input_usd_per_million=settings.models.estimated_input_usd_per_million,
        output_usd_per_million=settings.models.estimated_output_usd_per_million,
        cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
        confidence_review_below=settings.analysis.relevance.confidence_review_below,
        config_hash=settings.config_hash(),
        project_root=settings.project_root,
        cache_dir=Path(args.cache) if args.cache else CACHE_DIR,
        provider_call_budget=args.call_budget,
    )
    print(format_phase4_summary(result), end="")
    return 0


def _research_extract(args: argparse.Namespace) -> int:
    from src.models.document_derived import DocumentDerived
    from src.models.relevance import RelevanceDecision
    from src.pipeline.extraction import extraction_exit_code, format_extraction_summary, run_extraction
    from src.pipeline.research_batch import (
        CACHE_DIR,
        RESEARCH_MODEL,
        RESEARCH_PROVIDER,
        ResearchBatchError,
        assert_output_separate,
        load_frozen_ids,
        selected_documents,
    )

    if args.call_budget is None or args.max_retries != 1:
        print(
            "Research batch extraction requires --call-budget and --max-retries 1.",
            file=sys.stderr,
        )
        return 1
    settings = _research_settings()
    if settings is None:
        return 1
    provider_name, model_name, env_name, api_key = _relevance_runtime(settings, RESEARCH_PROVIDER)
    if provider_name != RESEARCH_PROVIDER or model_name != RESEARCH_MODEL:
        print("Research batch extraction uses Groq openai/gpt-oss-120b.", file=sys.stderr)
        return 1
    try:
        output = assert_output_separate(args.output)
        documents = selected_documents(args.input, document_limit=args.document_limit)
        frozen = load_frozen_ids()
    except ResearchBatchError as exc:
        print(f"Research batch error: {exc}", file=sys.stderr)
        return 1
    if any(document.doc_id in frozen for document in documents):
        print("Research batch extraction refused a frozen-split document.", file=sys.stderr)
        return 1
    if not documents:
        print("Research batch extraction: 0 eligible documents")
        return 0
    decisions_path = output / "relevance" / "relevance_decisions.jsonl"
    derived_path = output / "normalize" / "documents_derived.jsonl"
    if not decisions_path.is_file() or not derived_path.is_file():
        print("Relevance output for this research batch was not found.", file=sys.stderr)
        return 1
    decisions = [
        RelevanceDecision.model_validate_json(line)
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    derived = {
        row.doc_id: row
        for line in derived_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [DocumentDerived.model_validate_json(line)]
    }
    from src.pipeline.extraction import resolve_extraction_inputs

    eligible = [
        item.doc_id
        for item in resolve_extraction_inputs(
            [document.doc_id for document in documents], decisions, []
        )
        if item.eligible
    ]
    if args.call_budget != len(eligible):
        print(
            f"Research batch extraction allows {len(eligible)} external requests.",
            file=sys.stderr,
        )
        return 1
    if not eligible:
        print("Research batch extraction: 0 eligible documents")
        return 0
    if (output / "extract").exists():
        print("Research batch extraction output already exists. Use a fresh batch output parent.", file=sys.stderr)
        return 1
    if not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1
    result = run_extraction(
        doc_ids=eligible,
        model_decisions=decisions,
        human_decisions=[],
        derived_by_id=derived,
        approved_labels={},
        output_dir=output / "extract",
        dry_run=False,
        offline=False,
        provider_name=provider_name,
        model_name=model_name,
        api_key=api_key,
        temperature=settings.models.temperature,
        max_tokens=settings.models.max_tokens,
        timeout_seconds=settings.models.timeout_seconds,
        max_retries=1,
        input_usd_per_million=settings.models.estimated_input_usd_per_million,
        output_usd_per_million=settings.models.estimated_output_usd_per_million,
        cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
        cache_dir=Path(args.cache) if args.cache else CACHE_DIR,
        call_budget=args.call_budget,
        denylist=tuple(secret for secret in (api_key, settings.secrets.author_salt) if secret),
        config_hash=settings.config_hash(),
        project_root=settings.project_root,
    )
    print(format_extraction_summary(result), end="")
    return extraction_exit_code(result)


def _run_research_batch(args: argparse.Namespace) -> int:
    """Dry-run plans every stage. Live stages stay separate and budgeted."""
    if args.pilot or args.diagnostic or args.pilot_doc or args.pilot_max_tokens is not None:
        print("The research batch does not use the extraction pilot or diagnostic.", file=sys.stderr)
        return 1
    if args.holdout_unlock or args.split != "development":
        print("The research batch does not read or unlock the holdout.", file=sys.stderr)
        return 1
    if args.limit is not None:
        print("The research batch uses --document-limit, not --limit.", file=sys.stderr)
        return 1
    if not args.input or not args.output or args.document_limit is None:
        print(
            "Research batch requires --input, --output, and --document-limit.",
            file=sys.stderr,
        )
        return 1
    stages = [part.strip() for part in str(args.stages).split(",") if part.strip()]
    if args.dry_run:
        if stages != ["normalize", "dedupe", "prefilter", "relevance", "extract"]:
            print(
                "Research batch dry-run uses "
                "--stages normalize,dedupe,prefilter,relevance,extract.",
                file=sys.stderr,
            )
            return 1
        return _research_dry_run(args)
    if stages == ["normalize", "dedupe"]:
        return _research_normalize(args)
    if stages == ["prefilter", "relevance"]:
        return _research_relevance(args)
    if stages == ["extract"]:
        return _research_extract(args)
    print(
        "Live research batch stages are normalize,dedupe or prefilter,relevance or extract.",
        file=sys.stderr,
    )
    return 1


def _run(args: argparse.Namespace) -> int:
    """Dispatch implemented stages. Later stages still refuse."""
    if args.research_batch:
        if args.development_corpus:
            print("The research batch does not extract the development split.", file=sys.stderr)
            return 1
        return _run_research_batch(args)
    stages = [part.strip() for part in str(args.stages).split(",") if part.strip()]
    if args.pilot_doc and (stages != ["extract"] or not args.pilot or args.diagnostic):
        print("--pilot-doc requires --stages extract --pilot and cannot use --diagnostic.", file=sys.stderr)
        return 1
    if args.pilot_max_tokens is not None and (
        stages != ["extract"] or not args.pilot or args.diagnostic
    ):
        print("--pilot-max-tokens requires --stages extract --pilot.", file=sys.stderr)
        return 1
    if stages == ["normalize", "dedupe"]:
        return _run_phase3(args)
    if stages in (["prefilter"], ["relevance"], ["prefilter", "relevance"]):
        return _run_phase4(args, stages)
    if stages == ["taxonomy", "analyze"]:
        return _run_offline_analysis()
    if stages == ["extract"]:
        if args.development_corpus and (args.pilot or args.diagnostic):
            print(
                "The development corpus does not use the extraction pilot or diagnostic.",
                file=sys.stderr,
            )
            return 1
        return _run_extract(args)
    print(
        "Implemented stages are normalize,dedupe, prefilter and relevance, "
        "extract, or taxonomy,analyze.",
        file=sys.stderr,
    )
    return 1


def _run_offline_analysis() -> int:
    """Print the unassigned taxonomy. No provider call and no cluster names."""
    from src.taxonomy.assign import assign_cases
    from datetime import datetime, timezone

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    version = settings.taxonomy.version
    rows = assign_cases(
        [],
        taxonomy_version=version,
        clusters=list(settings.taxonomy.clusters),
        assigned_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
    )
    print(f"taxonomy version     {version}")
    print(f"named clusters       {len(settings.taxonomy.clusters)}")
    print(f"assignments written  {len(rows)}")
    print("provider calls       0")
    print("Composite opportunity score stays off.")
    return 0


def _run_extract(args: argparse.Namespace) -> int:
    """Dry-run, null-provider, or the bounded five-document pilot.

    A live extraction of the full candidate manifest is not authorized.
    """
    import csv

    from src.models.document_derived import DocumentDerived
    from src.models.relevance import RelevanceDecision
    from src.pipeline.extraction import (
        format_extraction_summary,
        load_approved_labels,
        resolve_extraction_inputs,
        run_extraction,
    )
    from src.pipeline.human_relevance import load_human_decisions

    if args.split != "development" or args.holdout_unlock:
        print(
            "Holdout locked: extraction uses the development candidate manifest only.",
            file=sys.stderr,
        )
        return 1
    if args.development_corpus:
        return _run_extract_development(args)
    if args.pilot and args.diagnostic:
        print(
            "The extraction diagnostic cannot be combined with the five-document pilot.",
            file=sys.stderr,
        )
        return 1
    if args.diagnostic:
        return _run_extract_diagnostic(args)
    if args.pilot:
        return _run_extract_pilot(args)
    if not args.dry_run and not args.offline:
        print(
            "Live extraction is not authorized. Use --dry-run or --offline.",
            file=sys.stderr,
        )
        return 1
    manifest_path = Path(
        "data/interim/phase4/development/01455c8aab03/extraction_candidate_manifest.csv"
    )
    decisions_path = Path(
        "data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl"
    )
    human_path = Path(
        "data/interim/phase4/development/01455c8aab03/human_relevance_decisions.jsonl"
    )
    derived_path = (
        Path(args.derived) if args.derived else Path("data/interim/phase3/documents_derived.jsonl")
    )
    if not manifest_path.is_file() or not decisions_path.is_file():
        print("Extraction inputs were not found.", file=sys.stderr)
        return 1
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        doc_ids = [row["doc_id"] for row in csv.DictReader(handle)]
    model_decisions = [
        RelevanceDecision.model_validate_json(line)
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    human_decisions = list(load_human_decisions(human_path))
    labels = load_approved_labels("data/interim/phase4/relevance_seed_review.csv")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    parent = Path(args.output) if args.output else Path("data/interim/phase5")
    derived_by_id: dict[str, DocumentDerived] = {}
    if not args.dry_run:
        wanted = {
            item.doc_id
            for item in resolve_extraction_inputs(doc_ids, model_decisions, human_decisions)
            if item.eligible
        }
        if derived_path.is_file():
            for line in derived_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = DocumentDerived.model_validate_json(line)
                if row.doc_id in wanted:
                    derived_by_id[row.doc_id] = row
    result = run_extraction(
        doc_ids=doc_ids,
        model_decisions=model_decisions,
        human_decisions=human_decisions,
        derived_by_id=derived_by_id,
        approved_labels=labels,
        output_dir=parent,
        limit=args.limit,
        dry_run=bool(args.dry_run),
        offline=bool(args.offline),
        resume=args.resume,
        provider_name="null",
        model_name=settings.models.extraction_model,
        temperature=settings.models.temperature,
        max_tokens=settings.models.max_tokens,
        timeout_seconds=settings.models.timeout_seconds,
        max_retries=1 if args.max_retries is None else args.max_retries,
        input_usd_per_million=settings.models.estimated_input_usd_per_million,
        output_usd_per_million=settings.models.estimated_output_usd_per_million,
        cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
        cache_dir=Path(args.cache) if args.cache else parent / "cache",
        call_budget=args.call_budget,
        project_root=Path.cwd(),
    )
    print(format_extraction_summary(result), end="")
    if result.blocked:
        print("blocked              " + ", ".join(result.blocked))
    from src.pipeline.extraction import extraction_exit_code

    return extraction_exit_code(result)


def _run_extract_development(args: argparse.Namespace) -> int:
    """Extract every frozen development document. Holdout text is not loaded."""
    import json

    from src.core.versions import prompt_version
    from src.models.relevance import RelevanceDecision
    from src.pipeline.extraction import PROMPT_ID as EXTRACT_PROMPT_ID, format_extraction_summary, load_approved_labels
    from src.pipeline.extraction_development import (
        CORPUS_MAX_RETRIES,
        CORPUS_MAX_TOKENS,
        DECISIONS_PATH,
        DEFAULT_CACHE,
        DEFAULT_OUTPUT,
        DERIVED_PATH,
        FUNNEL_SOURCES,
        HUMAN_DECISIONS_PATH,
        DevelopmentBoundsError,
        analysis_evidence_spans,
        corpus_run_directory,
        count_stage_events,
        development_ids,
        format_funnel,
        holdout_ids,
        load_derived_for,
        run_development_extraction,
        verbatim_span_failures,
    )
    from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER
    from src.pipeline.human_relevance import load_human_decisions

    if args.pilot or args.diagnostic or args.pilot_doc or args.pilot_max_tokens is not None:
        print(
            "The development corpus does not use the extraction pilot or diagnostic.",
            file=sys.stderr,
        )
        return 1
    if args.split != "development" or args.holdout_unlock:
        print(
            "Holdout locked: development corpus extraction uses development documents only.",
            file=sys.stderr,
        )
        return 1
    if args.limit is not None or args.resume or args.offline:
        print(
            "The development corpus does not take --limit, --resume, or --offline.",
            file=sys.stderr,
        )
        return 1
    if args.provider not in (None, PILOT_PROVIDER):
        print("The development corpus uses Groq.", file=sys.stderr)
        return 1
    if args.max_retries not in (None, CORPUS_MAX_RETRIES):
        print(
            "The development corpus allows one attempt and no gateway retry.",
            file=sys.stderr,
        )
        return 1
    if args.input or args.links:
        print("The development corpus does not accept collection overrides.", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
        provider_name, model_name, env_name, api_key = _relevance_runtime(settings, PILOT_PROVIDER)
        if provider_name != PILOT_PROVIDER or model_name != PILOT_MODEL:
            print(
                f"The development corpus uses {PILOT_PROVIDER} and {PILOT_MODEL}.",
                file=sys.stderr,
            )
            return 1
        documents = development_ids()
        locked = holdout_ids()
        if not DECISIONS_PATH.is_file():
            print("Development relevance decisions were not found.", file=sys.stderr)
            return 1
        model_decisions = [
            RelevanceDecision.model_validate_json(line)
            for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        human_decisions = list(load_human_decisions(HUMAN_DECISIONS_PATH))
        labels = load_approved_labels("data/interim/phase4/relevance_seed_review.csv")
    except (ConfigError, DevelopmentBoundsError) as exc:
        print(f"Development corpus error: {exc}", file=sys.stderr)
        return 1

    from src.pipeline.extraction import resolve_extraction_inputs

    eligible = sum(
        1
        for item in resolve_extraction_inputs(list(documents), model_decisions, human_decisions)
        if item.eligible
    )
    if args.call_budget != eligible:
        print(
            f"The development corpus allows {eligible} external requests.",
            file=sys.stderr,
        )
        return 1
    parent = Path(args.output) if args.output else DEFAULT_OUTPUT
    cache_dir = Path(args.cache) if args.cache else DEFAULT_CACHE
    derived_path = Path(args.derived) if args.derived else DERIVED_PATH
    derived_by_id = {}
    if not args.dry_run:
        if not derived_path.is_file():
            print("Derived development documents were not found.", file=sys.stderr)
            return 1
        wanted = {
            item.doc_id
            for item in resolve_extraction_inputs(list(documents), model_decisions, human_decisions)
            if item.eligible
        }
        derived_by_id = load_derived_for(derived_path, wanted)
        if locked and set(derived_by_id) & set(locked):
            print("Holdout locked: derived holdout text was refused.", file=sys.stderr)
            return 1
    try:
        result = run_development_extraction(
            doc_ids=documents,
            development=documents,
            holdout=locked,
            model_decisions=model_decisions,
            human_decisions=human_decisions,
            derived_by_id=derived_by_id,
            approved_labels=labels,
            output_dir=parent,
            cache_dir=cache_dir,
            provider_name=provider_name,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=CORPUS_MAX_TOKENS,
            timeout_seconds=float(settings.models.timeout_seconds),
            max_retries=CORPUS_MAX_RETRIES,
            call_budget=eligible,
            dry_run=bool(args.dry_run),
            api_key=None if args.dry_run else api_key,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            config_hash=settings.config_hash(),
            project_root=settings.project_root,
        )
    except DevelopmentBoundsError as exc:
        print(f"Development corpus error: {exc}", file=sys.stderr)
        return 1
    print("Development corpus extraction")
    print(f"  documents            {len(documents)}")
    print(f"  prompt               {EXTRACT_PROMPT_ID} {prompt_version(EXTRACT_PROMPT_ID)}")
    print(f"  provider             {provider_name}")
    print(f"  model                {model_name}")
    print(f"  max retries          {CORPUS_MAX_RETRIES}")
    print(f"  max tokens           {CORPUS_MAX_TOKENS}")
    print(f"  call budget          {eligible}")
    print(f"  cache                {cache_dir}")
    live_output = corpus_run_directory(
        parent,
        documents,
        model_name=model_name,
        temperature=settings.models.temperature,
        max_tokens=CORPUS_MAX_TOKENS,
    )
    print(f"  planned live output  {live_output}")
    print(format_extraction_summary(result), end="")
    funnel = count_stage_events(FUNNEL_SOURCES, set(documents))
    if not args.dry_run:
        extract_events = live_output / "stage_events.jsonl"
        funnel.update(count_stage_events(((extract_events, frozenset({"extract"})),), set(documents)))
        cases = []
        case_path = live_output / "retrieval_cases.jsonl"
        if case_path.is_file():
            cases = [
                json.loads(line)
                for line in case_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        ledger = []
        span_path = live_output / "evidence_spans.jsonl"
        if span_path.is_file():
            ledger = [
                json.loads(line)
                for line in span_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        analysis_spans = analysis_evidence_spans(cases, ledger)
        texts = {doc_id: row.raw_text_audit for doc_id, row in derived_by_id.items()}
        failures = verbatim_span_failures(analysis_spans, texts)
        rejected_attempts = sum(
            1 for span in ledger if span.get("validation_state") != "valid"
        )
        print(f"  analysis spans       {len(analysis_spans)}")
        print(f"  nonvalid claim spans {failures}")
        print(f"  rejected attempt spans {rejected_attempts}")
        (live_output / "stage_funnel.json").write_text(
            json.dumps(
                {
                    "documents": len(documents),
                    "stages": funnel,
                    "analysis_spans": len(analysis_spans),
                    "nonvalid_claim_spans": failures,
                    "rejected_attempt_spans": rejected_attempts,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(format_funnel(funnel), end="")
    problems = result.failed_candidates - len(result.blocked)
    return int(problems > 0)


def _run_extract_diagnostic(args: argparse.Namespace) -> int:
    """Plan or, when separately authorized, send one synthetic extraction request.

    Real documents, approved labels, and the five-document pilot stay unused.
    """
    from src.core.versions import prompt_version
    from src.pipeline.extraction import PROMPT_ID as EXTRACT_PROMPT_ID, format_extraction_summary
    from src.pipeline.extraction_diagnostic import (
        DEFAULT_CACHE,
        DEFAULT_OUTPUT,
        DIAGNOSTIC_CALL_BUDGET,
        DIAGNOSTIC_DOC_ID,
        DIAGNOSTIC_MAX_RETRIES,
        DiagnosticBoundsError,
        planned_output_dir,
        run_extraction_diagnostic,
    )
    from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER

    if args.limit is not None or args.derived or args.input or args.links or args.resume:
        print(
            "The extraction diagnostic does not accept real documents or another run.",
            file=sys.stderr,
        )
        return 1
    if args.offline:
        print("The extraction diagnostic does not run offline.", file=sys.stderr)
        return 1
    if args.provider not in (None, PILOT_PROVIDER):
        print("The extraction diagnostic uses Groq.", file=sys.stderr)
        return 1
    if args.call_budget not in (None, DIAGNOSTIC_CALL_BUDGET):
        print(
            f"The extraction diagnostic allows {DIAGNOSTIC_CALL_BUDGET} external request.",
            file=sys.stderr,
        )
        return 1
    if args.max_retries not in (None, DIAGNOSTIC_MAX_RETRIES):
        print(
            "The extraction diagnostic allows one attempt and no gateway retry.",
            file=sys.stderr,
        )
        return 1
    try:
        settings = load_settings()
        provider_name, model_name, env_name, api_key = _relevance_runtime(settings, PILOT_PROVIDER)
        if provider_name != PILOT_PROVIDER or model_name != PILOT_MODEL:
            print(
                f"The extraction diagnostic uses {PILOT_PROVIDER} and {PILOT_MODEL}.",
                file=sys.stderr,
            )
            return 1
    except ConfigError as exc:
        print(f"Extraction diagnostic error: {exc}", file=sys.stderr)
        return 1

    parent = Path(args.output) if args.output else DEFAULT_OUTPUT
    cache_dir = Path(args.cache) if args.cache else DEFAULT_CACHE
    try:
        live_output = planned_output_dir(
            parent,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            dry_run=False,
            offline=False,
        )
    except DiagnosticBoundsError as exc:
        print(f"Extraction diagnostic error: {exc}", file=sys.stderr)
        return 1
    if not args.dry_run and not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1
    try:
        result = run_extraction_diagnostic(
            output_dir=parent,
            cache_dir=cache_dir,
            provider_name=provider_name,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=settings.models.max_tokens,
            timeout_seconds=float(settings.models.timeout_seconds),
            max_retries=DIAGNOSTIC_MAX_RETRIES,
            call_budget=DIAGNOSTIC_CALL_BUDGET,
            dry_run=bool(args.dry_run),
            api_key=None if args.dry_run else api_key,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            config_hash=settings.config_hash(),
            project_root=settings.project_root,
        )
    except DiagnosticBoundsError as exc:
        print(f"Extraction diagnostic error: {exc}", file=sys.stderr)
        return 1
    print("Extraction diagnostic")
    print("  documents            1")
    print(f"  doc ids              {DIAGNOSTIC_DOC_ID}")
    print(f"  prompt               {EXTRACT_PROMPT_ID} {prompt_version(EXTRACT_PROMPT_ID)}")
    print(f"  provider             {provider_name}")
    print(f"  model                {model_name}")
    print(f"  max retries          {DIAGNOSTIC_MAX_RETRIES}")
    print(f"  call budget          {DIAGNOSTIC_CALL_BUDGET}")
    print(f"  cache                {cache_dir}")
    print(f"  planned live output  {live_output}")
    print(format_extraction_summary(result), end="")
    from src.pipeline.extraction import extraction_exit_code

    return extraction_exit_code(result)


def _run_extract_pilot(args: argparse.Namespace) -> int:
    """Plan or, when separately authorized, run the five-document pilot.

    The full candidate manifest stays refused for a live call. This path
    uses the existing extraction stage, gateway, cache, and budget.
    """
    from src.core.versions import prompt_version
    from src.models.document_derived import DocumentDerived
    from src.models.relevance import RelevanceDecision
    from src.pipeline.extraction import (
        PROMPT_ID as EXTRACT_PROMPT_ID,
        format_extraction_summary,
        load_approved_labels,
        resolve_extraction_inputs,
    )
    from src.pipeline.extraction_pilot import (
        CANDIDATE_MANIFEST,
        DEFAULT_CACHE,
        DEFAULT_MANIFEST,
        DEFAULT_OUTPUT,
        FIVE_DOCUMENT_LIMIT_BUDGET,
        PILOT_CALL_BUDGET,
        PILOT_MAX_RETRIES,
        PILOT_MODEL,
        PILOT_PROVIDER,
        SINGLE_DOCUMENT_CALL_BUDGET,
        SINGLE_DOCUMENT_IDS,
        five_document_token_limit,
        PilotBoundsError,
        PilotSelectionError,
        ensure_pilot_manifest,
        load_split_rows,
        planned_output_dir,
        run_extraction_pilot,
        resolve_pilot_max_tokens,
        select_pilot_ids,
    )
    from src.pipeline.human_relevance import load_human_decisions

    if args.limit is not None:
        print("The extraction pilot does not take --limit.", file=sys.stderr)
        return 1
    if args.provider not in (None, PILOT_PROVIDER):
        print("The extraction pilot uses Groq.", file=sys.stderr)
        return 1
    limited = five_document_token_limit(args.pilot_doc, args.pilot_max_tokens)
    if limited:
        if args.call_budget != FIVE_DOCUMENT_LIMIT_BUDGET:
            print(
                "The five-document 8192-token pilot requires --call-budget 4.",
                file=sys.stderr,
            )
            return 1
        if args.max_retries != PILOT_MAX_RETRIES:
            print(
                "The five-document 8192-token pilot requires --max-retries 1.",
                file=sys.stderr,
            )
            return 1
        call_budget = FIVE_DOCUMENT_LIMIT_BUDGET
    else:
        call_budget = SINGLE_DOCUMENT_CALL_BUDGET if args.pilot_doc else PILOT_CALL_BUDGET
        if args.call_budget not in (None, call_budget):
            print(
                f"The extraction pilot allows {call_budget} external requests.",
                file=sys.stderr,
            )
            return 1
        if args.max_retries not in (None, PILOT_MAX_RETRIES):
            print("The extraction pilot allows one attempt and no gateway retry.", file=sys.stderr)
            return 1
    if args.pilot_doc and args.pilot_doc not in SINGLE_DOCUMENT_IDS:
        print("Single-document diagnosis is limited to the two failed core seats.", file=sys.stderr)
        return 1
    if args.pilot_doc and any(value is not None for value in (args.input, args.derived, args.links)):
        print("Single-document diagnosis does not accept input overrides.", file=sys.stderr)
        return 1
    if args.resume:
        print("The extraction pilot does not resume another run.", file=sys.stderr)
        return 1
    decisions_path = Path(
        "data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl"
    )
    human_path = Path(
        "data/interim/phase4/development/01455c8aab03/human_relevance_decisions.jsonl"
    )
    if not CANDIDATE_MANIFEST.is_file() or not decisions_path.is_file():
        print("Extraction inputs were not found.", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
        provider_name, model_name, env_name, api_key = _relevance_runtime(settings, PILOT_PROVIDER)
        max_tokens = resolve_pilot_max_tokens(
            settings.models.max_tokens,
            pilot_doc_id=args.pilot_doc,
            pilot_max_tokens=args.pilot_max_tokens,
        )
        if provider_name != PILOT_PROVIDER or model_name != PILOT_MODEL:
            print(f"The extraction pilot uses {PILOT_PROVIDER} and {PILOT_MODEL}.", file=sys.stderr)
            return 1
        rows = load_split_rows(CANDIDATE_MANIFEST)
        candidate_ids = [row["doc_id"] for row in rows]
        model_decisions = [
            RelevanceDecision.model_validate_json(line)
            for line in decisions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        human_decisions = list(load_human_decisions(human_path))
        labels = load_approved_labels("data/interim/phase4/relevance_seed_review.csv")
        resolved = resolve_extraction_inputs(candidate_ids, model_decisions, human_decisions)
        selected = select_pilot_ids(resolved, labels)
        splits = {row["doc_id"]: (row["split"], row["split_version"]) for row in rows}
        ensure_pilot_manifest(DEFAULT_MANIFEST, selected, splits)
        if args.pilot_doc and args.pilot_doc not in selected:
            raise PilotBoundsError("the requested document is not in the validated pilot manifest")
    except (ConfigError, PilotSelectionError, PilotBoundsError) as exc:
        print(f"Extraction pilot error: {exc}", file=sys.stderr)
        return 1

    parent = Path(args.output) if args.output else DEFAULT_OUTPUT
    cache_dir = Path(args.cache) if args.cache else DEFAULT_CACHE
    requested_ids = (args.pilot_doc,) if args.pilot_doc else selected
    try:
        live_output = planned_output_dir(
            parent,
            requested_ids,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=max_tokens,
            dry_run=False,
            offline=False,
        )
    except PilotBoundsError as exc:
        print(f"Extraction pilot error: {exc}", file=sys.stderr)
        return 1
    if not args.dry_run and not args.offline and not api_key:
        print(f"{env_name} is not set.", file=sys.stderr)
        return 1

    derived_by_id: dict[str, DocumentDerived] = {}
    if not args.dry_run or limited:
        derived_path = (
            Path(args.derived)
            if args.derived
            else Path("data/interim/phase3/documents_derived.jsonl")
        )
        if derived_path.is_file():
            wanted = set(requested_ids)
            for line in derived_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = DocumentDerived.model_validate_json(line)
                if row.doc_id in wanted:
                    derived_by_id[row.doc_id] = row
    try:
        result = run_extraction_pilot(
            doc_ids=selected,
            model_decisions=model_decisions,
            human_decisions=human_decisions,
            derived_by_id=derived_by_id,
            approved_labels=labels,
            output_dir=parent,
            cache_dir=cache_dir,
            provider_name=provider_name,
            model_name=model_name,
            temperature=settings.models.temperature,
            max_tokens=max_tokens,
            timeout_seconds=float(settings.models.timeout_seconds),
            max_retries=PILOT_MAX_RETRIES,
            call_budget=call_budget,
            pilot_doc_id=args.pilot_doc,
            pilot_max_tokens=args.pilot_max_tokens,
            dry_run=bool(args.dry_run),
            offline=bool(args.offline),
            api_key=None if args.dry_run or args.offline else api_key,
            input_usd_per_million=settings.models.estimated_input_usd_per_million,
            output_usd_per_million=settings.models.estimated_output_usd_per_million,
            cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
            config_hash=settings.config_hash(),
            project_root=settings.project_root,
        )
    except (PilotBoundsError, PilotSelectionError) as exc:
        print(f"Extraction pilot error: {exc}", file=sys.stderr)
        return 1
    print("Extraction pilot")
    print(f"  documents            {len(requested_ids)}")
    print("  doc ids              " + ", ".join(requested_ids))
    print(f"  prompt               {EXTRACT_PROMPT_ID} {prompt_version(EXTRACT_PROMPT_ID)}")
    print(f"  provider             {provider_name}")
    print(f"  model                {model_name}")
    print(f"  max retries          {PILOT_MAX_RETRIES}")
    print(f"  max tokens           {max_tokens}")
    print(f"  call budget          {call_budget}")
    print(f"  cache                {cache_dir}")
    print(f"  planned live output  {live_output}")
    print(format_extraction_summary(result), end="")
    from src.pipeline.extraction import extraction_exit_code

    return extraction_exit_code(result)


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
    all_documents = list(documents)
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
            split_assignments = load_split_manifest(manifest_path)
            split_name = authorize_live_classification(
                split_name=args.split,
                holdout_unlocked=bool(args.holdout_unlock),
                lock_path=args.prompt_lock,
                provider=provider_name,
                model=model_name,
                temperature=settings.models.temperature,
                max_tokens=settings.models.max_tokens,
                transmitted_schema_sha256=_transmitted_schema_sha256(provider_name),
            )
            allowed = set(doc_ids_for_split(split_assignments, split_name))
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
        from src.relevance.context import (
            DocumentLink,
            cross_split_families,
            guarded_parent_contexts,
        )
        from src.relevance.interpretation import context_comparability

        documents_by_id = {document.doc_id: document for document in documents}
        derived_by_id = {row.doc_id: row for row in derived}
        split_by_id = {assignment.doc_id: assignment.split for assignment in split_assignments}
        parent_contexts = guarded_parent_contexts(
            [document.doc_id for document in documents],
            tuple(
                DocumentLink(
                    document.doc_id,
                    document.source_item_id,
                    document.parent_thread_id,
                )
                for document in all_documents
            ),
            split_by_id,
            lambda doc_id: documents_by_id[doc_id].title,
            lambda doc_id: derived_by_id[doc_id].raw_text_audit,
            lambda doc_id: derived_by_id[doc_id].content_hash,
        )
        context_report = {
            "context_status": {
                doc_id: context.status for doc_id, context in parent_contexts.items()
            },
            "context_identity": {
                doc_id: {
                    "parent_doc_id": context.parent_doc_id,
                    "content_hash": context.content_hash,
                }
                for doc_id, context in parent_contexts.items()
                if context.status == "included"
            },
            "context_comparability": {
                doc_id: context_comparability(doc_id, model_context=context.status)
                for doc_id, context in parent_contexts.items()
            },
            "cross_split_families": list(
                cross_split_families(
                    tuple(
                        DocumentLink(
                            document.doc_id,
                            document.source_item_id,
                            document.parent_thread_id,
                        )
                        for document in all_documents
                    ),
                    split_by_id,
                )
            ),
            "evaluation_limitation": (
                "Some parent and reply documents sit on different sides of the "
                "development/holdout split. Missing parent context is reported. "
                "Holdout text is not read. The split was not changed."
            ),
        }
    else:
        parent_contexts = None
        context_report = None
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
        input_usd_per_million=settings.models.estimated_input_usd_per_million,
        output_usd_per_million=settings.models.estimated_output_usd_per_million,
        cached_input_usd_per_million=settings.models.estimated_cached_input_usd_per_million,
        confidence_review_below=settings.analysis.relevance.confidence_review_below,
        config_hash=settings.config_hash(),
        project_root=settings.project_root,
        parent_contexts=parent_contexts,
        cache_dir=Path(args.cache) if args.cache else None,
        provider_call_budget=args.call_budget,
        max_retries=(
            settings.models.max_retries if args.max_retries is None else args.max_retries
        ),
        context_report=context_report,
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


def _transmitted_schema_sha256(provider: str) -> str | None:
    """Digest of the schema this provider sends. Anthropic does not rewrite it."""
    if provider != "groq":
        return None
    from src.llm.providers.groq import transmitted_schema_sha256
    from src.relevance.prompts import relevance_json_schema

    return transmitted_schema_sha256(relevance_json_schema())


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
    from src.relevance.split import SplitError, ensure_split_manifest, load_split_manifest
    from src.review.queue import ReviewItem

    seed_path = Path(args.seed)
    if not seed_path.is_file():
        print(f"Seed review not found: {seed_path.name}", file=sys.stderr)
        return 1
    try:
        labels = load_seed_review(seed_path)
        manifest_path = Path(args.manifest)
        if manifest_path.is_file():
            # Strata record the labels at split creation. Approved development
            # adjudication must not reassign targets or rewrite that snapshot.
            assignments = load_split_manifest(manifest_path)
            if {row.doc_id for row in assignments} != {row.doc_id for row in labels}:
                raise SplitError(
                    "the saved split does not cover the current seed documents; "
                    "it was not rewritten"
                )
        else:
            assignments = ensure_split_manifest(manifest_path, seed_path)
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
        context_payload = payload.get("context_report") if isinstance(payload.get("context_report"), dict) else {}
    else:
        context_payload = {}

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
            context_comparability=(
                context_payload.get("context_comparability")
                if isinstance(context_payload.get("context_comparability"), dict)
                else None
            ),
            cross_split_families=tuple(
                family
                for family in context_payload.get("cross_split_families") or ()
                if isinstance(family, dict)
            ),
            evaluation_limitation=(
                context_payload.get("evaluation_limitation")
                if isinstance(context_payload.get("evaluation_limitation"), str)
                else None
            ),
        )
    except EvaluationError as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 1
    write_evaluation_artifacts(args.output, report)
    print(format_evaluation_summary(report), end="")
    return 0


def _browse(args: argparse.Namespace) -> int:
    """Serve the read-only evidence page. Does not load settings or secrets."""
    from src.browse.serve import serve

    if args.host != "127.0.0.1":
        print("The evidence browser binds to 127.0.0.1 only.", file=sys.stderr)
        return 1
    serve(host=args.host, port=args.port)
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
