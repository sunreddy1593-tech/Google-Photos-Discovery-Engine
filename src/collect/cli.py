"""Terminal entry for workbook import and YouTube comment collection.

Workbook import stays :func:`src.collect.workbook.import_workbook`. YouTube
collection stays :func:`src.collect.youtube.collect_youtube_comments`. This
module only decides the process exit code and prints a count summary.

The author salt and the YouTube API key are arguments, never command-line
flags. ``main.py`` loads them through :class:`src.core.config.Settings`.
Neither value is printed or logged.

Exit codes:

* ``0`` — workbook import had no rejected rows, or a YouTube run finished
  within its document limit and request budget. A budget or document limit
  stop is still exit 0: those bounds were requested. Disabled comments and
  unavailable videos are recorded and do not by themselves fail the run.
* ``1`` — the workbook or video list is invalid, credentials are missing, or
  YouTube stopped for quota, rate limit, transport, or another API error.

PowerShell, with ``AUTHOR_SALT`` already in the environment or in ``.env``::

    python main.py collect --path "data\\manual\\Private\\Google_Photos_Pilot_Collection_Workbook.xlsx" --output "data\\processed\\pilot-import"

YouTube dry-run (no requests, no output files), after ``YOUTUBE_API_KEY`` is set::

    python main.py collect --youtube --videos "data\\manual\\youtube-videos.txt" --output "data\\processed\\youtube-import" --document-limit 50 --request-budget 20 --dry-run

Bounded live YouTube collection uses the same command without ``--dry-run``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.collect.workbook import ImportReport, import_workbook
from src.collect.youtube import (
    YoutubeCollectionError,
    YoutubeRunReport,
    collect_youtube_comments,
    public_message,
)
from src.core.errors import ConfigError, ValidationError

EXIT_OK: int = 0
EXIT_FAILURE: int = 1


def run_workbook_import(
    path: Path | str,
    output_dir: Path | str,
    *,
    author_salt: str,
) -> int:
    """Import one workbook and print a count summary.

    Returns :data:`EXIT_OK` or :data:`EXIT_FAILURE`. The summary lists counts
    only: no author names, no document text, and no salt.
    """
    try:
        result = import_workbook(path, author_salt=author_salt, output_dir=output_dir)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except FileNotFoundError:
        print(f"Workbook not found: {Path(path).name}", file=sys.stderr)
        return EXIT_FAILURE

    print(format_summary(result.report, output_dir), end="")
    return exit_code(result.report)


def exit_code(report: ImportReport) -> int:
    """``0`` only when the workbook imported cleanly."""
    if report.structure_errors or report.rows_rejected or report.search_log_issues:
        return EXIT_FAILURE
    return EXIT_OK


def format_summary(report: ImportReport, output_dir: Path | str) -> str:
    """Count summary safe to print on a terminal."""
    status = "Import complete" if exit_code(report) == EXIT_OK else "Import failed"
    lines = [
        status,
        f"  workbook             {report.workbook_name}",
        f"  rows read            {report.rows_read}",
        f"  rows accepted        {report.rows_accepted}",
        f"  rows rejected        {report.rows_rejected}",
        f"  warnings             {len(report.warnings)}",
        f"  search log read      {report.search_log_rows_read}",
        f"  search log valid     {report.search_log_rows_valid}",
        f"  search log issues    {len(report.search_log_issues)}",
        f"  output               {output_dir}",
    ]
    if report.structure_errors:
        lines.append(f"  structure errors     {len(report.structure_errors)}")
    return "\n".join(lines) + "\n"


_YOUTUBE_FAILURE_REASONS: frozenset[str] = frozenset(
    {"quota", "rate_limit", "transport_error", "api_error"}
)


def run_youtube_collection(
    video_file: Path | str,
    output_dir: Path | str,
    *,
    api_key: str,
    author_salt: str,
    document_limit: int,
    request_budget: int,
    dry_run: bool,
) -> int:
    """Collect YouTube comments, or print a dry-run plan. Counts only."""
    try:
        result = collect_youtube_comments(
            video_file,
            output_dir,
            api_key=api_key,
            author_salt=author_salt,
            document_limit=document_limit,
            request_budget=request_budget,
            dry_run=dry_run,
        )
    except ConfigError as exc:
        print(public_message(str(exc), api_key, author_salt), file=sys.stderr)
        return EXIT_FAILURE
    except (YoutubeCollectionError, ValidationError) as exc:
        print(public_message(str(exc), api_key, author_salt), file=sys.stderr)
        return EXIT_FAILURE
    except FileNotFoundError:
        print(f"Video list not found: {Path(video_file).name}", file=sys.stderr)
        return EXIT_FAILURE
    print(format_youtube_summary(result.report, output_dir), end="")
    if result.report.stopped_reason in _YOUTUBE_FAILURE_REASONS:
        return EXIT_FAILURE
    return EXIT_OK


def format_youtube_summary(report: YoutubeRunReport, output_dir: Path | str) -> str:
    """Count summary safe to print. No comment text, authors, or credentials."""
    if report.dry_run:
        status = "YouTube dry-run"
    elif report.stopped_reason in _YOUTUBE_FAILURE_REASONS:
        status = "YouTube collection stopped"
    else:
        status = "YouTube collection complete"
    disabled = sum(1 for video in report.videos if video.outcome == "comments_disabled")
    unavailable = sum(1 for video in report.videos if video.outcome == "video_unavailable")
    lines = [
        status,
        f"  videos in file       {report.videos_in_file}",
        f"  requests made        {report.requests_made}",
        f"  request budget       {report.request_budget}",
        f"  documents written    {report.documents_written}",
        f"  already present      {report.documents_already_present}",
        f"  document limit       {report.document_limit}",
        f"  comments disabled    {disabled}",
        f"  videos unavailable   {unavailable}",
        f"  stopped reason       {report.stopped_reason or 'none'}",
        f"  output               {output_dir}",
    ]
    return "\n".join(lines) + "\n"
