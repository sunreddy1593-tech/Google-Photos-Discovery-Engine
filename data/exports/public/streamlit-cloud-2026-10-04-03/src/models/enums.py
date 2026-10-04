"""Controlled vocabularies (spec Sections 15 and 16).

Two rules govern every vocabulary in this module, and both are asserted by tests
rather than left to discipline.

**No member means "we do not know".** Spec Section 16's preamble removes
``QueryStrategy.unknown``, ``SystemResponse.unknown``, ``Workaround.none_stated``,
``TargetAssetType.unknown``, ``Outcome.unknown``, ``KnownItemStatus.unclear``, and
``Speaker.unknown``. Absence is recorded by :class:`DimensionObservationStatus` on
the paired ``*_observation`` field, with the value left null or empty. This keeps
one meaning per member: everything below is something a user actually said, so a
distribution chart counts statements rather than a mixture of statements and gaps.

``other`` survives in every Section 16 dimension, because "the user said something
this list does not cover" is a genuinely different fact from "the user said
nothing".

**Member names match their values.** The wire value is the identity of a
controlled term, so a rename is a vocabulary change and should look like one in
the diff. ``Stage.import_`` is the single exception: ``import`` is a Python
keyword and cannot be an attribute name.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --------------------------------------------------------------------------- #
# Collection provenance (spec 15.1)
# --------------------------------------------------------------------------- #


class SourcePlatform(StrEnum):
    """Where a document came from (spec Section 15.1)."""

    play_store = "play_store"
    app_store = "app_store"
    reddit = "reddit"
    google_support = "google_support"
    youtube = "youtube"
    forum = "forum"
    social = "social"
    editorial = "editorial"
    manual_other = "manual_other"


class SourceType(StrEnum):
    """What kind of item a document is (spec Section 15.1)."""

    review = "review"
    post = "post"
    comment = "comment"
    support_thread = "support_thread"
    forum_reply = "forum_reply"
    video_comment = "video_comment"
    editorial_article = "editorial_article"
    other = "other"


class EvidenceTier(StrEnum):
    """Evidential weight of a whole document (spec Section 10).

    The tier is a ceiling on what any span inside the document can contribute:
    a ``contextual_editorial`` document cannot supply direct-user prevalence no
    matter what its spans say (ARCHITECTURE Section 9.4).

    ``synthetic_test`` marks fixtures. Every fixture in the test suite carries it
    and every research query excludes it, which is invariant I9 — a property of
    the data, not a convention about where files live.
    """

    direct_user = "direct_user"
    second_hand = "second_hand"
    contextual_editorial = "contextual_editorial"
    synthetic_test = "synthetic_test"


class CollectionMethod(StrEnum):
    """How a document was obtained (spec Section 15.1)."""

    api = "api"
    permitted_scraper = "permitted_scraper"
    manual_csv = "manual_csv"
    manual_jsonl = "manual_jsonl"
    manual_copy = "manual_copy"
    other = "other"


# --------------------------------------------------------------------------- #
# Relevance (spec 9, 15.3)
# --------------------------------------------------------------------------- #


class ScopeClass(StrEnum):
    """Scope decision for a document (spec Section 9).

    Deliberately three members and no failure member. When no decision was
    produced the scope class is null and the reason lives in
    :class:`DecisionTechnicalState`, so a provider outage can never be counted as
    a finding about a user (spec Section 15.3).
    """

    core_incomplete_recall = "core_incomplete_recall"
    adjacent_known_item_retrieval = "adjacent_known_item_retrieval"
    out_of_scope = "out_of_scope"


class DecisionTechnicalState(StrEnum):
    """Whether a decision or extraction attempt actually happened (spec 16.10).

    Orthogonal to the finding. Any value other than ``ok`` means no finding
    exists; such records are reported on their own funnel line and excluded from
    every prevalence, precision, and recall calculation (invariant I15).
    """

    ok = "ok"
    provider_unavailable = "provider_unavailable"
    provider_error = "provider_error"
    timeout = "timeout"
    rate_limited = "rate_limited"
    response_parse_failed = "response_parse_failed"
    schema_validation_failed = "schema_validation_failed"
    evidence_validation_failed = "evidence_validation_failed"
    skipped_dry_run = "skipped_dry_run"


class DecidedBy(StrEnum):
    """Who or what produced a relevance decision (spec Section 15.3)."""

    rules = "rules"
    llm = "llm"
    human = "human"


class ExtractorType(StrEnum):
    """Who or what produced a retrieval case (spec Section 15.4)."""

    human = "human"
    llm = "llm"
    rules = "rules"
    hybrid = "hybrid"


# --------------------------------------------------------------------------- #
# Reason codes (spec 16.8)
# --------------------------------------------------------------------------- #


class ReasonCode(StrEnum):
    """One vocabulary, three groups (spec Section 16.8).

    Used by ``RelevanceDecision.reason_code``, ``DuplicateLink.review_reason_code``,
    ``StageEvent.reason_code``, and the Phase 3 review queue. A code from the
    wrong group is a validation error, which is why the groups below are data and
    not documentation.
    """

    # -- inclusion: valid when scope_class is core or adjacent ---------------- #
    known_item_with_incomplete_recall = "known_item_with_incomplete_recall"
    known_item_query_unformulable = "known_item_query_unformulable"
    known_item_cue_not_recognized = "known_item_cue_not_recognized"
    known_item_with_precise_recall_failure = "known_item_with_precise_recall_failure"
    known_item_retrieval_journey_described = "known_item_retrieval_journey_described"

    # -- exclusion: valid only when scope_class is out_of_scope --------------- #
    no_known_item_target = "no_known_item_target"
    no_retrieval_need_or_attempt = "no_retrieval_need_or_attempt"
    storage_backup_or_sync = "storage_backup_or_sync"
    billing_or_subscription = "billing_or_subscription"
    deletion_or_corruption = "deletion_or_corruption"
    account_access = "account_access"
    editing_sharing_or_printing = "editing_sharing_or_printing"
    organization_unrelated_to_retrieval = "organization_unrelated_to_retrieval"
    general_ai_objection_without_retrieval = "general_ai_objection_without_retrieval"
    casual_browsing_without_known_target = "casual_browsing_without_known_target"
    editorial_or_hypothetical_example = "editorial_or_hypothetical_example"
    web_search_not_user_library = "web_search_not_user_library"
    insufficient_evidence_for_a_case = "insufficient_evidence_for_a_case"
    out_of_scope_language = "out_of_scope_language"
    other_out_of_scope = "other_out_of_scope"

    # -- review and processing: never a completed decision's reason ---------- #
    low_confidence = "low_confidence"
    prefilter_classifier_conflict = "prefilter_classifier_conflict"
    evidence_validation_failed = "evidence_validation_failed"
    repair_ladder_exhausted = "repair_ladder_exhausted"
    severity_without_evidence = "severity_without_evidence"
    observation_status_conflict = "observation_status_conflict"
    near_duplicate_in_review_band = "near_duplicate_in_review_band"
    short_text_below_dedupe_minimum = "short_text_below_dedupe_minimum"
    different_authors_identical_text = "different_authors_identical_text"
    quoted_repeat_ambiguous = "quoted_repeat_ambiguous"
    multi_case_offset_tie = "multi_case_offset_tie"
    evidence_offsets_unresolved = "evidence_offsets_unresolved"
    provider_unavailable = "provider_unavailable"
    response_parse_failed = "response_parse_failed"
    schema_validation_failed = "schema_validation_failed"
    rate_limited = "rate_limited"
    source_blocked = "source_blocked"


INCLUSION_REASON_CODES: Final[frozenset[ReasonCode]] = frozenset(
    {
        ReasonCode.known_item_with_incomplete_recall,
        ReasonCode.known_item_query_unformulable,
        ReasonCode.known_item_cue_not_recognized,
        ReasonCode.known_item_with_precise_recall_failure,
        ReasonCode.known_item_retrieval_journey_described,
    }
)

EXCLUSION_REASON_CODES: Final[frozenset[ReasonCode]] = frozenset(
    {
        ReasonCode.no_known_item_target,
        ReasonCode.no_retrieval_need_or_attempt,
        ReasonCode.storage_backup_or_sync,
        ReasonCode.billing_or_subscription,
        ReasonCode.deletion_or_corruption,
        ReasonCode.account_access,
        ReasonCode.editing_sharing_or_printing,
        ReasonCode.organization_unrelated_to_retrieval,
        ReasonCode.general_ai_objection_without_retrieval,
        ReasonCode.casual_browsing_without_known_target,
        ReasonCode.editorial_or_hypothetical_example,
        ReasonCode.web_search_not_user_library,
        ReasonCode.insufficient_evidence_for_a_case,
        ReasonCode.out_of_scope_language,
        ReasonCode.other_out_of_scope,
    }
)

REVIEW_REASON_CODES: Final[frozenset[ReasonCode]] = frozenset(
    set(ReasonCode) - INCLUSION_REASON_CODES - EXCLUSION_REASON_CODES
)


# --------------------------------------------------------------------------- #
# Case dimensions (spec 15.4, 16.1-16.7)
# --------------------------------------------------------------------------- #


class KnownItemStatus(StrEnum):
    """How firmly the user establishes a specific remembered item exists.

    The former ``unclear`` member is gone (spec Section 16 preamble): an
    ambiguous statement is ``known_item_status = null`` with
    ``known_item_status_observation = uncertain``.
    """

    explicit = "explicit"
    probable = "probable"


class TargetAssetType(StrEnum):
    """What kind of file the remembered item is (spec Section 15.4).

    Independent of :class:`SubjectType`, which is what the item is *about*.
    """

    photo = "photo"
    video = "video"
    screenshot = "screenshot"
    document_image = "document_image"
    mixed = "mixed"
    other = "other"


class SubjectType(StrEnum):
    """What the remembered item is about (spec Section 16.7).

    A screenshot of a receipt is ``target_asset_type = screenshot`` with
    ``SubjectType = receipt_or_invoice``; conflating the two loses exactly the
    distinction the memory map needs.
    """

    person = "person"
    pet_or_animal = "pet_or_animal"
    document_or_paperwork = "document_or_paperwork"
    receipt_or_invoice = "receipt_or_invoice"
    medicine_or_medical = "medicine_or_medical"
    id_card_or_credential_image = "id_card_or_credential_image"
    message_or_chat_capture = "message_or_chat_capture"
    app_or_web_capture = "app_or_web_capture"
    food_or_meal = "food_or_meal"
    place_or_venue = "place_or_venue"
    event_or_occasion = "event_or_occasion"
    vehicle = "vehicle"
    product_or_object = "product_or_object"
    artwork_whiteboard_or_notes = "artwork_whiteboard_or_notes"
    text_or_handwriting = "text_or_handwriting"
    nature_or_scenery = "nature_or_scenery"
    clothing_or_appearance = "clothing_or_appearance"
    other = "other"


class RememberedCue(StrEnum):
    """What the user explicitly remembers about the item (spec Section 16.1)."""

    person_identity = "person_identity"
    relationship = "relationship"
    approximate_time = "approximate_time"
    approximate_place = "approximate_place"
    event_or_occasion = "event_or_occasion"
    activity = "activity"
    object_or_subject = "object_or_subject"
    visual_appearance = "visual_appearance"
    text_fragment = "text_fragment"
    surrounding_context = "surrounding_context"
    emotion_or_feeling = "emotion_or_feeling"
    sequence_or_before_after = "sequence_or_before_after"
    source_or_device = "source_or_device"
    other = "other"


class ForgottenInfo(StrEnum):
    """What the user explicitly forgot or was unsure about (spec Section 16.2).

    Never inferred from non-mention. Silence is
    ``forgotten_information_observation = not_stated`` with an empty list.
    """

    exact_date = "exact_date"
    exact_time = "exact_time"
    place_name = "place_name"
    person_name = "person_name"
    object_name = "object_name"
    exact_text = "exact_text"
    album = "album"
    capture_device = "capture_device"
    file_type = "file_type"
    search_term = "search_term"
    storage_location = "storage_location"
    other = "other"


class QueryStrategy(StrEnum):
    """Search or browsing approaches the user describes (spec Section 16.3).

    ``no_query_formulated`` is a behaviour, not an absence of one: the user
    wanted a known item and states they could not turn memory into a search at
    all. Spec Section 9.1 classifies that as core scope, so the vocabulary has to
    be able to say it.
    """

    single_keyword = "single_keyword"
    multiple_keywords = "multiple_keywords"
    natural_language_description = "natural_language_description"
    person_or_face_search = "person_or_face_search"
    date_filter = "date_filter"
    place_filter = "place_filter"
    album_browsing = "album_browsing"
    category_browsing = "category_browsing"
    manual_scrolling = "manual_scrolling"
    repeated_reformulation = "repeated_reformulation"
    external_app_or_search = "external_app_or_search"
    asked_another_person = "asked_another_person"
    no_query_formulated = "no_query_formulated"
    other = "other"


class SystemResponse(StrEnum):
    """Returned behaviour or failure mode (spec Section 16.4)."""

    no_results = "no_results"
    irrelevant_results = "irrelevant_results"
    too_many_results = "too_many_results"
    partial_results = "partial_results"
    known_item_not_surfaced = "known_item_not_surfaced"
    summary_instead_of_asset = "summary_instead_of_asset"
    face_mismatch_or_omission = "face_mismatch_or_omission"
    text_not_recognized = "text_not_recognized"
    filter_or_scope_mismatch = "filter_or_scope_mismatch"
    could_not_form_query = "could_not_form_query"
    inconsistent_results = "inconsistent_results"
    other = "other"


class Workaround(StrEnum):
    """Action taken after a retrieval failure (spec Section 16.5).

    The former ``none_stated`` member is gone: a user who states they tried
    nothing is ``workarounds_observation = explicitly_none`` with an empty list
    and a span proving they said it.
    """

    rephrased_query = "rephrased_query"
    guessed_date = "guessed_date"
    manual_scrolling = "manual_scrolling"
    browsed_album = "browsed_album"
    used_people_view = "used_people_view"
    used_map_or_location_view = "used_map_or_location_view"
    added_caption_or_label = "added_caption_or_label"
    used_external_app = "used_external_app"
    asked_someone_else = "asked_someone_else"
    disabled_ai_feature = "disabled_ai_feature"
    saved_or_reorganized_content = "saved_or_reorganized_content"
    gave_up = "gave_up"
    other = "other"


class ImpactSignal(StrEnum):
    """Demonstrated or explicitly stated effect of the difficulty (spec 16.6).

    The input to the severity rubric in Section 18, and never inferred from tone.
    ``stated_distress`` in particular needs the user to describe the effect on
    themselves; a negative adjective is not the signal.
    """

    time_loss = "time_loss"
    repeat_effort = "repeat_effort"
    task_failure = "task_failure"
    task_delay = "task_delay"
    external_dependency = "external_dependency"
    urgency_or_deadline = "urgency_or_deadline"
    trust_loss = "trust_loss"
    stated_distress = "stated_distress"
    considered_or_made_switch = "considered_or_made_switch"
    believed_data_lost = "believed_data_lost"
    abandoned_goal = "abandoned_goal"
    financial_or_material_consequence = "financial_or_material_consequence"
    other = "other"


class Outcome(StrEnum):
    """How the retrieval attempt ended (spec Section 15.4).

    ``unresolved`` means the user stated the attempt ended without resolution —
    a finding. Silence is ``outcome = null`` with
    ``outcome_observation = not_stated``, which is why the former ``unknown``
    member is gone.
    """

    found = "found"
    partially_found = "partially_found"
    not_found = "not_found"
    abandoned = "abandoned"
    unresolved = "unresolved"


class DimensionObservationStatus(StrEnum):
    """Why a value is present or absent (spec Section 16.9).

    The single vocabulary that replaced every per-dimension ``unknown`` member.
    Two rules make it load-bearing:

    1. ``not_stated`` and ``explicitly_none`` are never merged. Merging them
       converts silence into a finding, which is the error spec Section 8.4
       forbids outright.
    2. The analysis layer reads this vocabulary and never defines its own. A
       status that matters to a chart has to exist here, be produced by
       extraction, and be evidenced.
    """

    stated = "stated"
    not_stated = "not_stated"
    explicitly_none = "explicitly_none"
    uncertain = "uncertain"
    not_applicable = "not_applicable"


# --------------------------------------------------------------------------- #
# Evidence (spec 15.2, 26.3)
# --------------------------------------------------------------------------- #


class EvidenceOwnerType(StrEnum):
    """Which kind of record a span supports (spec Section 15.2)."""

    relevance_decision = "relevance_decision"
    retrieval_case = "retrieval_case"
    observed_value = "observed_value"
    severity = "severity"
    gold_case = "gold_case"


class Speaker(StrEnum):
    """Whose words a span contains (spec Section 15.2, ARCHITECTURE 9.4).

    ``unattributed`` replaces the former ``unknown``: it says the source text
    does not attribute the words, which is a statement about the document rather
    than a gap in the analysis.
    """

    author = "author"
    quoted_other = "quoted_other"
    editorial_author = "editorial_author"
    unattributed = "unattributed"


class OffsetState(StrEnum):
    """How a span's offsets were arrived at (spec Sections 15.2, 26.3).

    Recording the route matters because three of these values mean a human or a
    heuristic moved the offsets, and an auditor needs to find those spans without
    re-deriving them.
    """

    supplied_exact = "supplied_exact"
    repaired_unique = "repaired_unique"
    repaired_nearest = "repaired_nearest"
    repaired_whitespace = "repaired_whitespace"
    missing_unresolved = "missing_unresolved"
    ambiguous_tied = "ambiguous_tied"


class ValidationState(StrEnum):
    """Whether a span or record passed the validity gate (spec Section 15.2).

    A stored column rather than an implicit property, because validating a span
    needs the parent document's text, which no field validator can see
    (IMPLEMENTATION-PLAN Phase 1 design note).
    """

    pending = "pending"
    valid = "valid"
    rejected = "rejected"


class RedactionType(StrEnum):
    """What kind of personal data a mask covers (spec Section 15.6).

    Spec Section 15.6 names the field but not its vocabulary; these members are
    the detector patterns IMPLEMENTATION-PLAN Phase 3 lists for
    ``src/normalize/privacy.py``. Phase 3 owns the detectors; Phase 1 owns only
    the term used to label a masked region.
    """

    email = "email"
    phone = "phone"
    handle = "handle"
    digit_run = "digit_run"
    other = "other"


# --------------------------------------------------------------------------- #
# Deduplication (spec 16.11)
# --------------------------------------------------------------------------- #


class DuplicateKind(StrEnum):
    """Relationship between two documents (spec Section 16.11)."""

    same_source_item = "same_source_item"
    exact_text = "exact_text"
    near = "near"
    cross_post = "cross_post"
    quoted_repeat = "quoted_repeat"


class DuplicateReviewState(StrEnum):
    """Confidence in a duplicate link (spec Section 16.11).

    ``pending_review`` is not counted as a duplicate in any analysis until it is
    resolved; it gets its own funnel line. ``human_rejected`` rows are retained,
    because "this pair was examined and found distinct" is exactly the evidence a
    reader needs to trust a duplicate rate.
    """

    auto_confirmed = "auto_confirmed"
    pending_review = "pending_review"
    human_confirmed = "human_confirmed"
    human_rejected = "human_rejected"


class DuplicateDetectionMethod(StrEnum):
    """How a duplicate link was detected (spec Section 15.7)."""

    source_item_key = "source_item_key"
    content_hash = "content_hash"
    simhash = "simhash"
    human = "human"


class DuplicateDecidedBy(StrEnum):
    """Who decided a duplicate link (spec Section 15.7).

    Narrower than :class:`DecidedBy` on purpose: no model participates in
    deduplication, so ``llm`` must not be expressible here.
    """

    rules = "rules"
    human = "human"


# --------------------------------------------------------------------------- #
# Pipeline events (spec 15.8)
# --------------------------------------------------------------------------- #


class StageEventTargetType(StrEnum):
    """What a stage event is about (spec Section 15.8)."""

    document = "document"
    case = "case"
    batch = "batch"


class Stage(StrEnum):
    """Pipeline stages that emit events (spec Section 15.8).

    ``import_`` is the one member whose name differs from its value, because
    ``import`` is a Python keyword. ``Stage("import")`` and ``Stage.import_.value``
    both give the wire value, which is the only form that reaches storage.
    """

    import_ = "import"
    normalize = "normalize"
    dedupe = "dedupe"
    prefilter = "prefilter"
    relevance = "relevance"
    extract = "extract"
    validate = "validate"
    taxonomy_assign = "taxonomy_assign"
    analyze = "analyze"
    export = "export"


class StageStatus(StrEnum):
    """Outcome of one stage attempt (spec Section 15.8).

    Failure and unavailability are ordinary statuses with reason codes, so they
    are countable on their own funnel lines rather than inferred from an absence.
    """

    started = "started"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    dropped = "dropped"
    unavailable = "unavailable"


# --------------------------------------------------------------------------- #
# Taxonomy and gold (spec 15.9, 15.11)
# --------------------------------------------------------------------------- #


class AssignmentMethod(StrEnum):
    """How a cluster assignment was made (spec Section 15.9)."""

    rules = "rules"
    llm = "llm"
    human = "human"


class GoldSplit(StrEnum):
    """Evaluation split (spec Section 24, Phase 6).

    ``dev`` is read freely for prompt iteration and error analysis. ``holdout``
    is frozen and read once per reported configuration; the Phase 6 evaluation
    script refuses to emit error analysis for it.
    """

    dev = "dev"
    holdout = "holdout"
