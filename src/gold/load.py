"""Load gold documents and gold cases from separate files."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.models.gold import GoldCase, GoldDocumentLabel


class GoldSetError(ValueError):
    """The gold files disagree with each other."""


def load_jsonl_models(path: Path | str, model: type):
    """Read one JSONL file. A missing file is an empty gold set."""
    source = Path(path)
    if not source.is_file():
        return ()
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(model.model_validate_json(line))
    return tuple(rows)


def load_gold_documents(path: Path | str) -> tuple[GoldDocumentLabel, ...]:
    """One document label per line. Duplicate document ids are rejected."""
    rows = load_jsonl_models(path, GoldDocumentLabel)
    seen: set[str] = set()
    for row in rows:
        if row.doc_id in seen:
            raise GoldSetError(f"duplicate gold document label: {row.doc_id}")
        seen.add(row.doc_id)
    return rows


def load_gold_cases(path: Path | str) -> tuple[GoldCase, ...]:
    """Case labels. They do not have to exist for every document."""
    return load_jsonl_models(path, GoldCase)


def require_case_counts(
    documents: tuple[GoldDocumentLabel, ...] | list[GoldDocumentLabel],
    cases: tuple[GoldCase, ...] | list[GoldCase],
) -> None:
    """``expected_case_count`` must match the case file, including zero."""
    found = Counter(case.doc_id for case in cases)
    for document in documents:
        actual = found.pop(document.doc_id, 0)
        if actual != document.expected_case_count:
            raise GoldSetError(
                f"{document.doc_id} expects {document.expected_case_count} gold cases "
                f"and the case file has {actual}"
            )
    if found:
        extra = ", ".join(sorted(found))
        raise GoldSetError(f"gold cases have no document label: {extra}")
