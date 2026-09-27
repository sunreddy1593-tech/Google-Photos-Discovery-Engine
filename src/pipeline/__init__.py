"""Stage runner. Normalization and deduplication only."""

from src.pipeline.runner import (
    DEFAULT_INPUT,
    DEFAULT_OUTPUT,
    Phase3Result,
    format_summary,
    load_collected_documents,
    run_normalize_dedupe,
)

__all__ = [
    "DEFAULT_INPUT",
    "DEFAULT_OUTPUT",
    "Phase3Result",
    "format_summary",
    "load_collected_documents",
    "run_normalize_dedupe",
]
