"""Terminal entry for workbook import.

The import itself stays in :func:`src.collect.workbook.import_workbook`.
This module only decides the process exit code and prints a count summary.

The author salt is an argument, never a command-line flag. ``main.py`` loads
it through :class:`src.core.config.Settings`, which reads ``AUTHOR_SALT`` from
the environment or ``.env``. The value is not printed and is not logged.

Exit codes:

* ``0`` — the workbook imported with no rejected document rows, no search-log
  issues, and no structural errors. Warnings, including a shared thread URL,
  still exit 0.
* ``1`` — the workbook is invalid, rows were rejected, or the salt is missing.

PowerShell, with ``AUTHOR_SALT`` already in the environment or in ``.env``::

    python main.py collect --path "data\\manual\\Private\\Google_Photos_Pilot_Collection_Workbook.xlsx" --output "data\\processed\\pilot-import"
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.collect.workbook import ImportReport, import_workbook
from src.core.errors import ConfigError

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
