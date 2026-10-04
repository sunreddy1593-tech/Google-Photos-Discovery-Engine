"""Research data contracts (spec Section 15) and controlled vocabularies (16).

Every production record validates through a model in this package. Three
properties hold across all of them, and each is asserted by a test rather than
left to convention:

- **No contract requires a field a later stage produces** (invariant I11). This is
  what lets ``CollectedDocument`` be complete at import with no normalizer,
  deduplicator, or classifier in existence.
- **Absence is a status, never a placeholder** (invariant I6). No vocabulary here
  contains ``unknown`` or ``none_stated``; a missing fact is a null value plus a
  :class:`~src.models.enums.DimensionObservationStatus`.
- **Substantive claims carry field-level evidence** (invariant I12). The map in
  :mod:`src.models.evidence_map` says which fields those are, and
  :mod:`src.extract.validator` enforces it against the document text.

**Why the re-exports are lazy.** Eager imports in this file would mean that
``from src.models.collected_document import CollectedDocument`` loads
``DocumentDerived`` and ``DuplicateLink`` as a side effect of the package's
``__init__`` running. Invariant I11 would then be true of the field lists and
false of the running program, and the Phase 2 importer — whose whole point is
that it needs nothing from Phase 3 — would import Phase 3 anyway. PEP 562
attribute access keeps the convenience of ``from src.models import X`` without
that coupling, and ``tests/test_models.py`` asserts the isolation in a
subprocess.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from src.models.cluster_assignment import ClusterAssignment
    from src.models.collected_document import CollectedDocument
    from src.models.document_derived import DocumentDerived, RedactionSpan
    from src.models.duplicate_link import DuplicateLink
    from src.models.evidence import EvidenceBackedLabel, EvidenceSpan, ObservedValue
    from src.models.export import ExportedEvidenceSpan, PublicExportRecord
    from src.models.gold import GoldCase, GoldDocumentLabel, PreAdjudicationLabel
    from src.models.relevance import RelevanceDecision, derive_is_relevant
    from src.models.retrieval_case import RetrievalCase
    from src.models.stage_event import StageEvent

#: Public name -> the module that defines it.
_EXPORTS: Final[dict[str, str]] = {
    "ClusterAssignment": "cluster_assignment",
    "CollectedDocument": "collected_document",
    "DocumentDerived": "document_derived",
    "RedactionSpan": "document_derived",
    "DuplicateLink": "duplicate_link",
    "EvidenceBackedLabel": "evidence",
    "EvidenceSpan": "evidence",
    "ObservedValue": "evidence",
    "ExportedEvidenceSpan": "export",
    "PublicExportRecord": "export",
    "GoldCase": "gold",
    "GoldDocumentLabel": "gold",
    "PreAdjudicationLabel": "gold",
    "RelevanceDecision": "relevance",
    "derive_is_relevant": "relevance",
    "RetrievalCase": "retrieval_case",
    "StageEvent": "stage_event",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Resolve a contract on first use (PEP 562)."""
    try:
        module_name = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    from importlib import import_module

    return getattr(import_module(f"{__name__}.{module_name}"), name)


def __dir__() -> list[str]:
    return list(__all__)
