"""Deterministic prefilter and relevance classification."""

from src.relevance.rules import (
    ROUTE_CLASSIFY,
    ROUTE_OBVIOUS_EXCLUSION,
    ROUTE_SKIPPED_NON_CANONICAL,
    PrefilterResult,
    prefilter_document,
)

__all__ = [
    "ROUTE_CLASSIFY",
    "ROUTE_OBVIOUS_EXCLUSION",
    "ROUTE_SKIPPED_NON_CANONICAL",
    "PrefilterResult",
    "prefilter_document",
]
