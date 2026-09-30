"""Local notes that must not change the headline agreement denominator.

These flags describe comparison limits. They are not model instructions and
they do not alter approved labels.
"""

from __future__ import annotations

WATERFALL_DOC_ID = "google_support-3d15a7ae4cd0"
TRANSCRIPT_DOC_ID = "google_support-d7f386f347b7"
CAMARO_DOC_ID = "google_support-e1e5277da7e8"

CONTEXT_INCOMPLETE = "context_incomplete"
OVERLAPPING_REASONS = "overlapping_inclusion_reasons"
CORE_ADJACENT_BOUNDARY = "core_adjacent_boundary"


def context_comparability(doc_id: str, *, model_context: str) -> dict[str, str]:
    """Separate stored seed text, model context, and known human-review context.

    The waterfall seed row stores the reply only. The human label was reviewed
    with the linked parent thread, so a reply-only row does not mean the
    reviewer lacked that parent.
    """
    if doc_id == WATERFALL_DOC_ID:
        return {
            "seed_row_text": "reply_only",
            "model_context": model_context,
            "known_human_review_context": "linked_parent_thread",
        }
    return {
        "seed_row_text": "target_document",
        "model_context": model_context,
        "known_human_review_context": "target_document",
    }


def interpretation_flags(doc_id: str, *, context_status: str) -> tuple[str, ...]:
    """Concerns reported beside exact agreement, not instead of it.

    A reply-only seed row is not a human/model context disagreement.
    ``context_incomplete`` means the model was not given parent text.
    """
    flags: list[str] = []
    if doc_id == WATERFALL_DOC_ID and context_status != "included":
        flags.append(CONTEXT_INCOMPLETE)
    if doc_id == TRANSCRIPT_DOC_ID:
        flags.append(OVERLAPPING_REASONS)
    if doc_id == CAMARO_DOC_ID:
        flags.append(CORE_ADJACENT_BOUNDARY)
    return tuple(flags)


def agreement_summary(
    rows: tuple[tuple[str, bool, bool], ...],
    *,
    context_status: dict[str, str],
) -> dict[str, object]:
    """Exact scope and reason counts keep every supplied row in the denominator."""
    flagged = {
        doc_id: interpretation_flags(doc_id, context_status=context_status.get(doc_id, "none"))
        for doc_id, _, _ in rows
        if interpretation_flags(doc_id, context_status=context_status.get(doc_id, "none"))
    }
    return {
        "document_count": len(rows),
        "scope_agreement": sum(1 for _, scope, _ in rows if scope),
        "reason_agreement": sum(1 for _, _, reason in rows if reason),
        "interpretation_flags": flagged,
        "context_comparability": {
            doc_id: context_comparability(
                doc_id,
                model_context=context_status.get(doc_id, "none"),
            )
            for doc_id, _, _ in rows
        },
    }
