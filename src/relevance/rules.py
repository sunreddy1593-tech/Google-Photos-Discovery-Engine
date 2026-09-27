"""High-recall deterministic prefilter.

A result is a routing decision. It is not a ``RelevanceDecision`` and it is not
a research claim. Obvious backup, sync, storage, billing, deletion, corruption,
and account-access posts can be marked as exclusion candidates when at least
two distinct signals match and the post has no retrieval language. One keyword
is never enough to drop a document. A post that mixes retrieval language with
backup or deletion language always continues to the classifier.

The three scope classes stay available downstream. This stage names
``out_of_scope`` only as a candidate on an obvious exclusion. It does not
choose between core and adjacent.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.versions import RULESET_VERSION
from src.models.enums import ReasonCode, ScopeClass

ROUTE_CLASSIFY = "classify"
ROUTE_OBVIOUS_EXCLUSION = "obvious_exclusion_candidate"
ROUTE_SKIPPED_NON_CANONICAL = "skipped_non_canonical"

LABEL_RETAINED = "retained_for_recall"
LABEL_SINGLE = "single_signal_retained"
LABEL_MIXED = "mixed_retrieval_and_exclusion"

_BACKUP = ReasonCode.storage_backup_or_sync.value
_DELETE = ReasonCode.deletion_or_corruption.value
_BILLING = ReasonCode.billing_or_subscription.value
_ACCOUNT = ReasonCode.account_access.value


@dataclass(frozen=True)
class Signal:
    signal_id: str
    family: str
    phrase: str
    reason_code: str


@dataclass(frozen=True)
class SignalHit:
    signal_id: str
    family: str
    phrase: str
    reason_code: str


@dataclass(frozen=True)
class PrefilterResult:
    """Routing for one document. ``passed`` means the classifier may run."""

    doc_id: str
    route: str
    passed: bool
    candidate_scope_class: str | None
    matched_signals: tuple[SignalHit, ...]
    reason_labels: tuple[str, ...]
    drop_reason_code: str | None
    ruleset_version: str
    canonical_doc_id: str | None = None

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> "PrefilterResult":
        raw_hits = payload.get("matched_signals") or []
        hits = tuple(
            SignalHit(
                signal_id=str(hit["signal_id"]),
                family=str(hit["family"]),
                phrase=str(hit["phrase"]),
                reason_code=str(hit["reason_code"]),
            )
            for hit in raw_hits  # type: ignore[union-attr]
        )
        labels = payload.get("reason_labels") or []
        return cls(
            doc_id=str(payload["doc_id"]),
            route=str(payload["route"]),
            passed=bool(payload["passed"]),
            candidate_scope_class=(
                None
                if payload.get("candidate_scope_class") is None
                else str(payload["candidate_scope_class"])
            ),
            matched_signals=hits,
            reason_labels=tuple(str(label) for label in labels),  # type: ignore[union-attr]
            drop_reason_code=(
                None
                if payload.get("drop_reason_code") is None
                else str(payload["drop_reason_code"])
            ),
            ruleset_version=str(payload["ruleset_version"]),
            canonical_doc_id=(
                None
                if payload.get("canonical_doc_id") is None
                else str(payload["canonical_doc_id"])
            ),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "route": self.route,
            "passed": self.passed,
            "candidate_scope_class": self.candidate_scope_class,
            "matched_signals": [
                {
                    "signal_id": hit.signal_id,
                    "family": hit.family,
                    "phrase": hit.phrase,
                    "reason_code": hit.reason_code,
                }
                for hit in self.matched_signals
            ],
            "reason_labels": list(self.reason_labels),
            "drop_reason_code": self.drop_reason_code,
            "ruleset_version": self.ruleset_version,
            "canonical_doc_id": self.canonical_doc_id,
        }


# Multi-word phrases. A lone "backup", "deleted", "storage", or "sync" is not
# in this list, so it cannot drop a document on its own.
EXCLUSION_SIGNALS: tuple[Signal, ...] = (
    Signal("backup_failed", "backup_sync", "backup failed", _BACKUP),
    Signal("not_backing_up", "backup_sync", "not backing up", _BACKUP),
    Signal("backup_not_working", "backup_sync", "backup not working", _BACKUP),
    Signal("waiting_to_backup", "backup_sync", "waiting to backup", _BACKUP),
    Signal("not_syncing", "backup_sync", "not syncing", _BACKUP),
    Signal("sync_failed", "backup_sync", "sync failed", _BACKUP),
    Signal("sync_error", "backup_sync", "sync error", _BACKUP),
    Signal("upload_stuck", "backup_sync", "upload stuck", _BACKUP),
    Signal("storage_full", "storage", "storage full", _BACKUP),
    Signal("storage_is_full", "storage", "storage is full", _BACKUP),
    Signal("out_of_storage", "storage", "out of storage", _BACKUP),
    Signal("not_enough_storage", "storage", "not enough storage", _BACKUP),
    Signal("buy_more_storage", "storage", "buy more storage", _BACKUP),
    Signal("upgrade_storage", "storage", "upgrade storage", _BACKUP),
    Signal("accidentally_deleted", "deletion", "accidentally deleted", _DELETE),
    Signal("permanently_deleted", "deletion", "permanently deleted", _DELETE),
    Signal("cannot_restore", "deletion", "cannot restore", _DELETE),
    Signal("cant_restore", "deletion", "can't restore", _DELETE),
    Signal("photos_corrupted", "corruption", "photos corrupted", _DELETE),
    Signal("file_corrupted", "corruption", "file is corrupted", _DELETE),
    Signal("corrupted_files", "corruption", "corrupted files", _DELETE),
    Signal("charged_my", "billing", "charged my", _BILLING),
    Signal("payment_failed", "billing", "payment failed", _BILLING),
    Signal("cancel_my_subscription", "billing", "cancel my subscription", _BILLING),
    Signal("subscription_charge", "billing", "subscription charge", _BILLING),
    Signal("billing_problem", "billing", "billing problem", _BILLING),
    Signal("cant_sign_in", "account", "can't sign in", _ACCOUNT),
    Signal("cannot_sign_in", "account", "cannot sign in", _ACCOUNT),
    Signal("cannot_log_in", "account", "cannot log in", _ACCOUNT),
    Signal("account_locked", "account", "account locked", _ACCOUNT),
    Signal("locked_out", "account", "locked out", _ACCOUNT),
    Signal("password_reset", "account", "password reset", _ACCOUNT),
)

RETRIEVAL_PHRASES: tuple[str, ...] = (
    "can't find",
    "cannot find",
    "cant find",
    "couldn't find",
    "could not find",
    "can't locate",
    "cannot locate",
    "looking for",
    "don't remember",
    "do not remember",
    "can't remember",
    "cannot remember",
    "cant remember",
    "forgot the",
    "forgotten",
    "no idea what",
    "what to search",
    "what to type",
    "somewhere in my",
    "somewhere in",
    "ask photos",
    "face grouping",
    "didn't recognize",
    "did not recognize",
    "nothing comes up",
    "no results",
    "missing photo",
    "missing photos",
    "lost photo",
    "lost the photo",
    "used to have",
)

_PHOTO_WORDS = ("photo", "photos", "picture", "pictures", "video", "videos", "album", "image", "images")
_SEARCH_WORDS = ("search", "searching", "searched")


def prefilter_document(
    doc_id: str,
    normalized: str,
    *,
    canonical_doc_id: str | None = None,
) -> PrefilterResult:
    """Route one canonical document. Non-canonical callers pass the skip id."""
    if canonical_doc_id is not None:
        return PrefilterResult(
            doc_id=doc_id,
            route=ROUTE_SKIPPED_NON_CANONICAL,
            passed=False,
            candidate_scope_class=None,
            matched_signals=(),
            reason_labels=("non_canonical_duplicate",),
            drop_reason_code=None,
            ruleset_version=RULESET_VERSION,
            canonical_doc_id=canonical_doc_id,
        )
    return _route_text(doc_id, normalized)


def _route_text(doc_id: str, normalized: str) -> PrefilterResult:
    text = " ".join(normalized.lower().split())
    hits = tuple(
        SignalHit(signal.signal_id, signal.family, signal.phrase, signal.reason_code)
        for signal in EXCLUSION_SIGNALS
        if signal.phrase in text
    )
    retrieval = _has_retrieval(text)
    distinct = {hit.signal_id for hit in hits}

    if retrieval and hits:
        labels: tuple[str, ...] = (LABEL_MIXED,)
        route = ROUTE_CLASSIFY
        passed = True
        candidate = None
        drop = None
    elif len(distinct) >= 2 and not retrieval:
        labels = tuple(sorted({hit.reason_code for hit in hits}))
        route = ROUTE_OBVIOUS_EXCLUSION
        passed = False
        candidate = ScopeClass.out_of_scope.value
        drop = _primary_reason(hits)
    elif len(distinct) == 1:
        labels = (LABEL_SINGLE,)
        route = ROUTE_CLASSIFY
        passed = True
        candidate = None
        drop = None
    else:
        labels = (LABEL_RETAINED,)
        route = ROUTE_CLASSIFY
        passed = True
        candidate = None
        drop = None

    return PrefilterResult(
        doc_id=doc_id,
        route=route,
        passed=passed,
        candidate_scope_class=candidate,
        matched_signals=tuple(sorted(hits, key=lambda hit: hit.signal_id)),
        reason_labels=labels,
        drop_reason_code=drop,
        ruleset_version=RULESET_VERSION,
    )


def _has_retrieval(text: str) -> bool:
    if any(phrase in text for phrase in RETRIEVAL_PHRASES):
        return True
    has_search = any(f" {word} " in f" {text} " for word in _SEARCH_WORDS)
    has_photo = any(f" {word} " in f" {text} " for word in _PHOTO_WORDS)
    return has_search and has_photo


def _primary_reason(hits: tuple[SignalHit, ...]) -> str:
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.reason_code] = counts.get(hit.reason_code, 0) + 1
    return sorted(counts, key=lambda code: (-counts[code], code))[0]
