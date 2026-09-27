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
            "Run normalize and dedupe. Other stage lists are not implemented. "
            "The command prints counts only."
        ),
    )
    run.add_argument(
        "--stages",
        required=True,
        help="Comma-separated stages. The implemented list is normalize,dedupe",
    )
    run.add_argument(
        "--input",
        default=None,
        help="collected_documents.jsonl from Phase 2 (default: the pilot import)",
    )
    run.add_argument(
        "--output",
        default=None,
        help="Directory for derived records, links, and the review CSV",
    )
    run.set_defaults(handler=_run)

    for name, (help_text, phase) in COMMANDS.items():
        if name in {"collect", "run"}:
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
    """Dispatch normalize,dedupe. Import logic stays in src.pipeline."""
    from src.pipeline.runner import (
        DEFAULT_INPUT,
        DEFAULT_OUTPUT,
        format_summary,
        load_collected_documents,
        run_normalize_dedupe,
    )

    stages = [part.strip() for part in str(args.stages).split(",") if part.strip()]
    if stages != ["normalize", "dedupe"]:
        print(
            "Only --stages normalize,dedupe is implemented.",
            file=sys.stderr,
        )
        return 1

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
    result = run_normalize_dedupe(
        load_collected_documents(source),
        settings.analysis.dedupe,
        destination,
    )
    print(format_summary(result), end="")
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
