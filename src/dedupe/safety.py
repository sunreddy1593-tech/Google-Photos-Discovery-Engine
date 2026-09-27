"""Safety conditions for an automatic duplicate decision (spec Section 19.6).

All four ADR-21 conditions must hold before ``review_state`` can be
``auto_confirmed``. The first failure in the specification's order supplies
the reason code. A quoted repeat is never automatic.

A cross-platform pair is also never automatic. ``author_hash`` mixes in
``source_platform``, so hash equality cannot show that one person wrote both
posts, and hash inequality cannot show that they are two people.
"""

from __future__ import annotations

from src.core.config import DedupeConfig
from src.models.enums import ReasonCode


def review_reason(
    *,
    token_count_left: int,
    token_count_right: int,
    author_left: str | None,
    author_right: str | None,
    hamming: int,
    content_hashes_equal: bool,
    quoted: bool,
    cross_platform: bool,
    config: DedupeConfig,
) -> ReasonCode | None:
    """Return the reason a pair must be reviewed, or ``None`` when it may be automatic.

    ``None`` means every safety condition held. Callers still refuse to
    auto-confirm a quoted repeat; this function reports that case itself.
    ``cross_platform`` is checked after the author-distinctness rule, so two
    stored hashes that differ keep ``different_authors_identical_text``. A
    cross-platform pair whose hashes match, or whose authors are missing, is
    ``low_confidence``: the match is not an identity claim.
    """
    if quoted:
        return ReasonCode.quoted_repeat_ambiguous
    if (
        token_count_left < config.min_tokens
        or token_count_right < config.min_tokens
    ):
        return ReasonCode.short_text_below_dedupe_minimum
    authors_differ = bool(author_left and author_right and author_left != author_right)
    if authors_differ and not config.allow_cross_author_auto:
        return ReasonCode.different_authors_identical_text
    if cross_platform:
        return ReasonCode.low_confidence
    if (
        not content_hashes_equal
        and config.simhash_duplicate_max < hamming <= config.simhash_review_band_max
    ):
        return ReasonCode.near_duplicate_in_review_band
    return None
