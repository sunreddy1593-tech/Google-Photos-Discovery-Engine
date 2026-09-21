#!/usr/bin/env python
"""CLI entry point for the discovery-engine pipeline.

Phase 0 wires the argument surface only. Every subcommand is declared so the
pipeline's shape is visible and ``--help`` is useful, and every one refuses to run
with the phase that will implement it. A subcommand that silently did nothing
would be worse than one that says it is not built.

Run ``python main.py --help`` for the command list.
"""

from __future__ import annotations

import argparse
import sys
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
            "Phase 0 scaffold: no stage is wired yet."
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

    for name, (help_text, phase) in COMMANDS.items():
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
