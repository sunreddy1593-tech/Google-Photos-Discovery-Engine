"""Semantic findings already recorded against saved model output.

These rows cite the review notes. They do not change ``retrieval_cases.jsonl``.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class SemanticFinding:
    """One recorded objection to a saved field."""

    doc_id: str
    case_id: str | None
    field: str
    risk: str
    summary: str
    source_note: str


#: Shown on every page. A case can be automatically valid and still carry one.
REVIEW_RISKS: tuple[str, ...] = (
    "retrieval_trigger must be the stated reason the item was needed, not the search method",
    "impact and severity need a quote that states that impact or severity",
    "problem_summary evidence must support every factual clause",
    "quotes must be one continuous span; invented or spliced text is invalid",
)


RECORDED_FINDINGS: tuple[SemanticFinding, ...] = (
    SemanticFinding(
        doc_id="google_support-d7f386f347b7",
        case_id="google_support-d7f386f347b7#c01",
        field="retrieval_trigger",
        risk="retrieval_trigger",
        summary=(
            "Stored value 'search backup' names the search. The attached quote "
            "does not state why the item was needed."
        ),
        source_note="data/interim/phase5/core-diagnostic-v2-detail-fix-semantic-review.md",
    ),
    SemanticFinding(
        doc_id="google_support-d7f386f347b7",
        case_id="google_support-d7f386f347b7#c01",
        field="problem_summary",
        risk="incomplete_summary",
        summary=(
            "The attached quote is the first sentence. It does not support "
            "'cannot locate' or 'in their backup'."
        ),
        source_note="data/interim/phase5/core-diagnostic-v2-detail-fix-semantic-review.md",
    ),
    SemanticFinding(
        doc_id="google_support-e1e5277da7e8",
        case_id="google_support-e1e5277da7e8#c01",
        field="retrieval_trigger",
        risk="retrieval_trigger",
        summary=(
            "Stored value 'car search option' is the search method, not a "
            "stated reason the item was needed."
        ),
        source_note="data/interim/phase5/pilot_v2_8192_correction_proposal.md",
    ),
    SemanticFinding(
        doc_id="google_support-e1e5277da7e8",
        case_id="google_support-e1e5277da7e8#c01",
        field="impact_signals",
        risk="unsupported_impact",
        summary=(
            "time_loss is attached to a quote that says the white Camaro is "
            "missing and does not state that time was consumed."
        ),
        source_note="data/interim/phase5/pilot_v2_8192_correction_proposal.md",
    ),
    SemanticFinding(
        doc_id="google_support-e1e5277da7e8",
        case_id="google_support-e1e5277da7e8#c01",
        field="problem_summary",
        risk="incomplete_summary",
        summary=(
            "The quote supports 'white Camaro' and 'missing' only. It does not "
            "contain 'photo' or 'car search option'."
        ),
        source_note="data/interim/phase5/pilot_v2_8192_correction_proposal.md",
    ),
    SemanticFinding(
        doc_id="google_support-2a080da4b930",
        case_id=None,
        field="cases",
        risk="empty_omission",
        summary=(
            "The saved response is a finished stop payload with zero cases. "
            "The source states a retrieval episode. Emptiness is the model's "
            "omission, and the payload was not repaired."
        ),
        source_note="STATUS.md",
    ),
    SemanticFinding(
        doc_id="reddit-23be97c93709",
        case_id="reddit-23be97c93709#u3bff3392",
        field="problem_summary",
        risk="spliced_quote",
        summary=(
            "The saved quote joins three passages with an ellipsis the source "
            "does not contain. The case stays out of analysis and was not repaired."
        ),
        source_note="data/interim/phase5/pilot_v2_8192_correction_proposal.md",
    ),
    SemanticFinding(
        doc_id="reddit-c49086caf891",
        case_id=None,
        field="provider",
        risk="unresolved_provider",
        summary=(
            "HTTP 400 json_validate_failed, invalid JSON, error at character "
            "3690. The body was not kept. That record does not establish token "
            "exhaustion or a charge. The review item stays open."
        ),
        source_note="STATUS.md",
    ),
    SemanticFinding(
        doc_id="youtube-8c01bd1e27bd",
        case_id=None,
        field="scope_class",
        risk="known_item_overclaim",
        summary=(
            "The model classified this comment as adjacent known-item retrieval. "
            "The review says the retained quote supports a location-search "
            "coverage regression, only 2024 results where all years were "
            "returned before, and does not name a particular known item. "
            "That classification is not an approved episode."
        ),
        source_note="data/interim/youtube-discussion-2026-10-03/relevance-review.md",
    ),
)
