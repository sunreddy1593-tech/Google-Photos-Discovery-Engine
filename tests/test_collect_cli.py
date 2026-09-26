"""CLI around workbook import.

The salt is supplied by configuration, the same way every other secret is.
These tests point the loader at an explicit env file and clear ``AUTHOR_SALT``
from the process, so a developer's ``.env`` cannot make a missing-salt case pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import main
from src.collect.cli import run_workbook_import
from src.core.config import load_settings
from src.core.ids import author_hash
from src.models.enums import SourcePlatform
from tests.test_workbook_import import (
    OTHER_SALT,
    SALT,
    SENTINEL,
    _assert_name_absent,
    _row,
    _search,
    _write_workbook,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = "UNIQUE_RAW_TEXT_MARKER_7c2e"
SHARED_URL = "https://www.reddit.com/r/googlephotos/comments/shared-thread/"


def _isolate_salt(monkeypatch: pytest.MonkeyPatch, env_file: Path) -> None:
    monkeypatch.delenv("AUTHOR_SALT", raising=False)
    settings = load_settings(env_file=env_file)
    monkeypatch.setattr(main, "load_settings", lambda: settings)


def _env(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.synthetic
def test_cli_success_prints_counts_and_hides_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "ok.xlsx"
    output = tmp_path / "out"
    _write_workbook(
        workbook,
        [
            _row(
                source_item_id="kept",
                author_name_raw=SENTINEL,
                raw_text=RAW,
            )
        ],
        search_rows=[_search(notes=f"saw {SENTINEL}")],
    )
    _isolate_salt(monkeypatch, _env(tmp_path / "salt.env", f"AUTHOR_SALT={SALT}\n"))

    code = main.main(
        [
            "--log-level",
            "DEBUG",
            "collect",
            "--path",
            str(workbook),
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "Import complete" in captured.out
    assert "rows read            1" in captured.out
    assert "rows accepted        1" in captured.out
    assert "rows rejected        0" in captured.out
    assert "search log issues    0" in captured.out
    documents = (output / "collected_documents.jsonl").read_text(encoding="utf-8")
    report_json = (output / "import_report.json").read_text(encoding="utf-8")
    report_text = (output / "import_report.txt").read_text(encoding="utf-8")
    for blob, where in (
        (captured.out, "stdout"),
        (captured.err, "stderr"),
        (report_json, "import report json"),
        (report_text, "import report text"),
    ):
        _assert_name_absent(blob, SENTINEL, where=where)
        _assert_name_absent(blob, SALT, where=where)
        _assert_name_absent(blob, RAW, where=where)
    _assert_name_absent(documents, SENTINEL, where="collected documents")
    _assert_name_absent(documents, SALT, where="collected documents")
    assert RAW in documents
    assert author_hash(SALT, SourcePlatform.reddit.value, SENTINEL) in documents


@pytest.mark.synthetic
def test_cli_repeated_url_warning_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "shared.xlsx"
    _write_workbook(
        workbook,
        [
            _row(source_item_id="post", source_url=SHARED_URL, author_name_raw=SENTINEL),
            _row(
                source_item_id="reply",
                source_url=SHARED_URL,
                parent_thread_id="post",
                title=None,
                author_name_raw=SENTINEL,
                raw_text="A reply on the same thread.",
            ),
        ],
    )
    _isolate_salt(monkeypatch, _env(tmp_path / "salt.env", f"AUTHOR_SALT={SALT}\n"))

    code = main.main(
        ["collect", "--path", str(workbook), "--output", str(tmp_path / "out")]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "rows rejected        0" in captured.out
    assert "warnings             " in captured.out
    assert "warnings             0" not in captured.out
    _assert_name_absent(captured.out + captured.err, SENTINEL, where="terminal")
    _assert_name_absent(captured.out + captured.err, SALT, where="terminal")


@pytest.mark.synthetic
def test_cli_rejected_rows_exit_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "bad-row.xlsx"
    _write_workbook(
        workbook,
        [_row(author_name_raw=SENTINEL, raw_text=None)],
    )
    _isolate_salt(monkeypatch, _env(tmp_path / "salt.env", f"AUTHOR_SALT={SALT}\n"))

    code = main.main(
        ["collect", "--path", str(workbook), "--output", str(tmp_path / "out")]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "Import failed" in captured.out
    assert "rows rejected        1" in captured.out
    _assert_name_absent(captured.out, SENTINEL, where="stdout")
    _assert_name_absent(captured.err, SENTINEL, where="stderr")
    _assert_name_absent(captured.out + captured.err, SALT, where="terminal")
    report = (tmp_path / "out" / "import_report.json").read_text(encoding="utf-8")
    _assert_name_absent(report, SENTINEL, where="import report json")
    _assert_name_absent(report, SALT, where="import report json")


@pytest.mark.synthetic
def test_cli_invalid_workbook_and_search_log_exit_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_sheet = tmp_path / "no-search.xlsx"
    _write_workbook(missing_sheet, [_row()], sheets=("documents",))
    _isolate_salt(monkeypatch, _env(tmp_path / "salt.env", f"AUTHOR_SALT={SALT}\n"))

    code = main.main(
        [
            "collect",
            "--path",
            str(missing_sheet),
            "--output",
            str(tmp_path / "missing"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "Import failed" in captured.out
    assert "structure errors     1" in captured.out

    over = tmp_path / "over.xlsx"
    _write_workbook(
        over,
        [_row(author_name_raw=SENTINEL, raw_text=RAW)],
        search_rows=[_search(results_scanned=1, documents_kept=4, notes=SALT)],
    )
    code = main.main(
        ["collect", "--path", str(over), "--output", str(tmp_path / "over-out")]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "search log issues    1" in captured.out
    assert "rows rejected        0" in captured.out
    report = (tmp_path / "over-out" / "import_report.json").read_text(encoding="utf-8")
    documents = (tmp_path / "over-out" / "collected_documents.jsonl").read_text(
        encoding="utf-8"
    )
    for blob, where in (
        (captured.out, "stdout"),
        (captured.err, "stderr"),
        (report, "import report json"),
    ):
        _assert_name_absent(blob, SALT, where=where)
        _assert_name_absent(blob, SENTINEL, where=where)
        _assert_name_absent(blob, RAW, where=where)
    assert RAW in documents
    assert SALT not in documents


@pytest.mark.synthetic
def test_cli_missing_salt_fails_without_a_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / "needs-salt.xlsx"
    _write_workbook(workbook, [_row(author_name_raw=SENTINEL)])
    _isolate_salt(monkeypatch, _env(tmp_path / "empty.env", "# no salt\n"))

    code = main.main(
        ["collect", "--path", str(workbook), "--output", str(tmp_path / "out")]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "AUTHOR_SALT" in captured.err
    assert "not set" in captured.err
    assert captured.out == ""
    _assert_name_absent(captured.err, SENTINEL, where="stderr")
    _assert_name_absent(captured.out + captured.err, SALT, where="terminal")
    _assert_name_absent(captured.out + captured.err, OTHER_SALT, where="terminal")
    assert not (tmp_path / "out").exists()


@pytest.mark.synthetic
def test_direct_call_rejects_an_empty_salt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workbook = tmp_path / "empty.xlsx"
    _write_workbook(workbook, [_row(author_name_raw=SENTINEL, raw_text=RAW)])

    code = run_workbook_import(workbook, tmp_path / "out", author_salt="")
    captured = capsys.readouterr()

    assert code == 1
    assert "AUTHOR_SALT" in captured.err
    assert captured.out == ""
    _assert_name_absent(captured.err, SENTINEL, where="stderr")
    _assert_name_absent(captured.err, RAW, where="stderr")
    assert not (tmp_path / "out").exists()


def test_cli_does_not_accept_a_salt_argument(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main.main(["collect", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--path" in help_text
    assert "--output" in help_text
    assert "--author-salt" not in help_text
    assert "AUTHOR_SALT" in help_text

    with pytest.raises(SystemExit) as rejected:
        main.main(
            [
                "collect",
                "--path",
                "workbook.xlsx",
                "--output",
                "out",
                "--author-salt",
                "visible-salt",
            ]
        )
    assert rejected.value.code != 0


def test_missing_workbook_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_salt(monkeypatch, _env(tmp_path / "salt.env", f"AUTHOR_SALT={SALT}\n"))

    code = main.main(
        [
            "collect",
            "--path",
            str(tmp_path / "missing.xlsx"),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "Workbook not found" in captured.err
    _assert_name_absent(captured.out + captured.err, SALT, where="terminal")


def test_processed_outputs_stay_out_of_git() -> None:
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/processed/*" in ignored
