# Decisions

> Required by `problem-statement.md` Section 1: important scope, schema, taxonomy, model,
> source, and scoring decisions are recorded here. Spec Section 29 item 16 requires material
> deviations from the specification to be recorded here as well.
>
> Format: one entry per decision, with the alternative that was rejected and the specification
> section affected. Entries are append-only. A superseded decision is marked **Superseded by
> ADR-n** rather than edited away, so the reasoning history survives.

Status legend: **Accepted** · **Accepted (default, calibration pending)** · **Superseded**

## Register index

| ADR | Subject | Status |
|---|---|---|
| 1 | JSONL source of truth, SQLite projection | Accepted |
| 2 | Evidence-backed labels as relational rows | Accepted |
| 3 | `raw_text_audit` on `RawDocument` | **Superseded by ADR-15** |
| 4 | `src/llm/` gateway | Accepted |
| 5 | `src/review/` and `src/pipeline/` packages | Accepted, amended by ADR-24 |
| 6 | `case_id` ordinals by evidence position | **Superseded by ADR-20** |
| 7 | `extraction_fingerprint` in the primary key | **Superseded by ADR-19** |
| 8 | Composite score off by default | Accepted |
| 9 | `reference files/` → read-only `prototype/` | Accepted |
| 10 | Commit full `raw_text_audit` | **Superseded by ADR-23** |
| 11 | Near-duplicate threshold band | **Superseded by ADR-21** |
| 12 | Recency window 12 months | Accepted |
| 13 | Comment permalinks "verified" | **Superseded by ADR-22** |
| 14 | Anthropic default provider | Accepted, amended by ADR-27 |
| 15 | Split `CollectedDocument` / `DocumentDerived` / `DuplicateLink` | Accepted |
| 16 | Evidence-required field map; `all_evidence_spans` derived | Accepted |
| 17 | `is_relevant` derived; evidence for every class; technical state | Accepted |
| 18 | Append-only `StageEvent` replaces the lifecycle column | Accepted |
| 19 | `taxonomy_version` scoped to taxonomy stages | Accepted |
| 20 | Identifiers derivable at their own stage; lowest-`doc_id` canonical | Accepted |
| 21 | Deduplication safety conditions | Accepted (defaults, calibration pending Phase 3) |
| 22 | Source feasibility tiers and documentation-linked verification | Accepted; corpus-size consequence amended by ADR-32 |
| 23 | Public-export excerpt profile | Accepted (redistribution terms pending Phase 10) |
| 24 | Review queue built in Phase 3 | Accepted |
| 25 | Gold-set redesign: splits, separated labels, metric families | Accepted, clarified by ADR-30 |
| 26 | Rebuild equality is canonical content hashes | Accepted |
| 27 | MVP versus stretch scope | Accepted; sequencing amended by ADR-32 |
| 28 | First prompt is Phase 0 only; every phase has a prompt | Accepted; one-phase rule amended by ADR-32 |
| 29 | M1 reports the case count rather than targeting it | Accepted |
| 30 | Phase 4 seed split is not the Phase 6 gold split | Accepted |
| 31 | Groq is a provisional Phase 4 relevance provider | Accepted |
| 32 | October 2026 demonstration schedule | Accepted; amends ADR-22 consequence 1, ADR-27 sequencing, and ADR-28's one-phase rule for three tracks |
| 33 | Individual submission uses one human reviewer with disclosed AI assistance | Accepted; amends internal double-coding requirements, without changing evidence or quality thresholds |
| 34 | M1 verified offline; full field-evidence accounting and separate quality gate | Accepted; supersedes historical incomplete status, without waiving checks |
| 35 | One bounded frozen gold verification; prior development exposure disclosed | Accepted; numeric thresholds measured, broader research remains incomplete; gold-set volume amended by ADR-37 |
| 36 | Parallel submission integration and a separate reference demonstration | Accepted |
| 37 | Approved 35-document gold set is final; 75–100 labelling volume is closed | Accepted |

---

## Implementation note — 2026-10-04: development diagnosis does not replace the freeze

The saved `extract/v3` development run was diagnosed offline. Accepted-empty
responses and one spliced relevance quote explain the four missing reference
cases. Two matched cases retain semantic disagreements. No saved model row,
approved label, split, or historical freeze hash was changed. Original bytes of
the freeze-bound files edited afterward are stored in
`data/interim/phase6/pre-correction-snapshot-2026-10-04-01/` and were verified
against `quality-freeze-2026-10-04-01/freeze.json` before editing.
`extract/v4` is an inactive candidate. It is not the measured correction and
has not been run. The consumed holdout measurement remains the numeric result
in ADR-35, with the same disclosed limits.

## Approved revision note — 2026-10-04: cat impact and development review

Sunayana explicitly approved a new reference version with cat impact unstated
and severity 3 retained, and approved the rest of the source review. Applied the
impact-only semantic reference correction in `sunayana-reviewed-02/`, preserving
all original files and the original seating manifest. The new reference export
has ten documents, six cases and 38 field quote attachments; removed only the
obsolete impact attachment. Severity evidence and all other case values remain.
No broader meaning for repeat_effort is substituted; the written definition
stays intact. The earlier pending-reference decision is resolved by this later
authorization. Remaining review findings/proposed model corrections are approved
in a separate run/hash-bound ledger, without changing model output or guards.
Offline reevaluation still recovers 2/6 cases; this correction is not extraction
recovery or quality certification. Development is not frozen, holdout stays
locked, and the final quality gate remains pending. Earlier notes are historical.

## Review note — 2026-10-04: development correction proposals are not applied decisions

The source-grounded development review at
`data/interim/phase6/development-review-2026-10-04-01/REVIEW.md` distinguishes
confirmed evidence instruction violations, semantic findings, omissions,
coding ambiguity and unresolved model behavior. It does not change original
cases, approved labels, numeric reports, review decisions, prompts or schemas.
The cat model's shorter social-sharing trigger is supported despite exact-string
disagreement. Conversely, the approved reference's repeat_effort value conflicts
with Section 16.6's requirement for separate sittings, absent from this source.
A separate reference revision is recommended for owner review; none is applied,
no broader definition is silently substituted, and severity 3 remains supported.
Development is not frozen; holdout remains locked and final certification pending.

## Implementation note — 2026-10-04: development-first quality evaluation

The owner explicitly chose "Keep holdout locked; finish development first".
The existing evaluator now receives actual saved development predictions through
an optional adapter; no provider, collection or cache operation is required.
Current production contracts/field gates and approved gold-dev source packets
are reused. The adapter refuses holdout seats before packet reads, incomplete
stage coverage and occupied output. Missing predictions remain pending rather
than being presented as a measured result.

Confirmed implementation defects were corrected: the CLI did not supply saved
predictions; structured gold multi-label entries were compared as whole objects;
omitted expected labels were miscounted as unsupported predicted labels. Current
reports disclose matched-case coverage, failures, unassessed reference fields,
single-reviewer AI assistance and the existing family-album scope exception.
The ten-document diagnostic meets five numeric thresholds but recovers only
2/6 reference cases. It is `development_only`, not final quality certification.
No threshold, prompt, schema, source label, scope definition or split was changed.

The corrected report is `data/exports/quality/development-approved-2026-10-04-03/`.
Earlier in-task reports remain immutable and have separate supersession notes.
Full suite: 1100 passed, 5 skipped. Official gold/reports and owner approvals
remain preserved; no finding is cleared by numeric agreement. Corrective
development review and a documented freeze precede any separately authorized
holdout step. Holdout stays locked and the final quality gate stays pending.

## Implementation note — 2026-10-04: direct owner approval of saved M1 cases

The owner explicitly approved the saved M1 model cases. Ten decisions name
Sunayana and bind run `3dc346ec030a` and immutable case hashes in
`data/interim/phase5/semantic-approval-2026-10-04-01/corrections.jsonl`.
This records the human decision without attributing an independent source
review to Codex. Two cases retain five semantic field objections; three retain
an existing document-level historical provider finding. Those findings stay
open and existing conclusion guards remain in force. The historical diagnostic
is not newly asserted to prove semantic error in the three current cases.
The ledger is scoped to the M1 run and is not connected to the older case-id-only
browser corrections path. A future UI integration must check the run binding,
retain findings, and preserve the gold-holdout source restriction. Original
cases, references, official gold and prior decisions remain unchanged. Owner
approval is not a measured Phase 6 quality-gate pass.

## ADR-34 — M1 verification and full field-evidence accounting

- **Date:** 2026-10-04.
- **Authorization:** Owner requested completion of M1. Existing Section 28
  requirements and ADR-29's observed case count remain in force.
- **Decision:** Record M1 complete against its five pipeline checks using the
  saved development-corpus run and a fresh offline verification report. This
  reconciles the older completed Phase 5 checklist with later incomplete notes.
  No gate, validation rule or quality threshold is waived. ADR-33's annotation
  method alone did not complete M1; this separate verification does.
- **Confirmed defect:** Reporting counted the case's serialized inline-only
  `all_evidence_spans` property, omitting external scalar-field evidence. Reuse
  `validate_record`'s authoritative union. Ten cases have 61 spans: 24 inline
  plus 37 external. The historical 24-span artifact is preserved.
- **Evidence:** All ten cases pass current contracts and field gates; all 61
  spans match successful retained source-validation verdicts. Twenty spans are
  freshly checked against approved gold-dev packets. The five stages each cover
  all 35 development documents. Full offline suite: 1087 passed, 5 skipped.
  Audit report: `data/exports/milestones/m1-2026-10-04/report.json`.
- **Limits:** Retained verdicts provide historical substring-validation evidence
  for sources now reserved as gold holdout; their source text is not reopened.
  Source availability is not re-fetched. Six failed and seven accepted-empty
  extraction documents remain diagnostic results. Automatic validity does not
  establish semantic support for every interpretation. Approved human reference
  labels are separate and do not approve the saved model cases.
- **Rejected:** Re-running paid extraction to reconcile documentation, silently
  repairing historical model output, counting valid failed-attempt spans as
  analysis, treating M1 as a Phase 6 quality pass, or relaxing requirements to
  close the milestone. No provider request or holdout scoring was performed.
- **Preservation:** Runs, caches, approved reviews, original splits, prompts,
  schemas and official gold remain unchanged. The new report is a separate
  artifact, not an amendment to the saved run or a semantic-review decision.

## ADR-33 — Single human reviewer with disclosed AI assistance

- **Date:** 2026-10-04
- **Status:** Accepted by direct owner instruction.
- **Authorization:** The owner approved the current drafts and said there is no
  second reviewer for this individual project; files should name her as reviewer.
- **Decision:** Sunayana is the sole human reviewer of the ten approved starter
  annotations. AI assistance is disclosed in notes and pack provenance. No second
  coder is invented and no blinded coding, adjudication or inter-reviewer agreement
  is claimed. Raw agreement and Cohen's kappa are unavailable, not zero or one.
- **Implementation:** `sunayana-reviewed-01/labels/Sunayana/` holds ten approved
  records and six cases. The original seating manifest is retained byte-for-byte;
  a new review manifest explicitly waives procedural double-code flags under the
  owner's authorization. IDs and all split assignments are identical. Existing
  validator/emitter behavior is reused without changing its guards.
- **Limits:** One-person AI-assisted review provides no independent inter-coder
  validation. Ten development documents do not establish general quality. The
  family-album core scope exception remains disclosed; no evidence is invented
  to support it. Gold/reference export is separate from saved model cases.
- **Unchanged:** Evidence gates, evaluation thresholds, source privacy, approved
  seed labels, holdout restrictions and earlier decisions. M1 remains incomplete.

## ADR-1 — Append-only JSONL is the source of truth; SQLite is a rebuildable projection

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §15.1 (raw immutability), §26 (reproducibility)
- **Decision:** Raw documents are written once to `data/raw/{platform}/{YYYY-MM}/{batch}.jsonl`
  and never modified. `data/interim/engine.db` is a projection built from those files plus the
  LLM response cache, and may be deleted and rebuilt at any time.
- **Rationale:** Makes raw immutability structural rather than a matter of discipline, and makes
  `main.py rebuild` a real reproducibility test — replaying the corpus must reproduce identical
  export hashes.
- **Rejected:** Database as system of record. Simpler day to day, but immutability becomes a
  convention that any stray `UPDATE` breaks, and losing the database loses the corpus.

## ADR-2 — Evidence-backed labels are stored as relational rows, not JSON arrays

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §15.5, §21.2, §21.4
- **Decision:** Each `{value, evidence}` label pair from §15.5 becomes a row in `case_labels`
  with a foreign key to `evidence_spans`. Pydantic models still expose nested objects; the store
  flattens on write and rehydrates on read.
- **Rationale:** The memory-map cross-tab and every distribution in §21.4 become direct aggregate
  queries with the evidence join intact, and "every label has evidence" becomes a database
  constraint instead of a code path.
- **Rejected:** JSON columns. Fewer tables, but aggregation logic moves into Python and the
  evidence link is no longer enforceable.

## ADR-3 — Add derived `raw_text_audit` and `redaction_spans` to `RawDocument`

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-15 (2026-09-21)** — the length-preserving redaction technique is
  retained unchanged; only the field placement was wrong. Putting `raw_text_audit` and
  `redaction_spans` on the collection contract made that contract depend on a Phase 3 output, so
  manual import could not produce a valid document without the normalizer. The fields now live on
  `DocumentDerived` (spec §15.6).
- **Spec sections:** §15.1 (derived fields permitted), §15.2 (offset validity), §12 (privacy)
- **Decision:** Redaction replaces each PII span with a mask of **identical character length**,
  producing `raw_text_audit` plus a `redaction_spans` list. Evidence offsets therefore remain
  valid against both `raw_text` and `raw_text_audit`. Spans overlapping a redacted region are
  rejected at validation. `raw_text_audit` is the text sent to model providers.
- **Rationale:** Resolves a genuine conflict in the specification: §15.2 requires
  `quote == raw_text[start:end]` while §12 requires PII removal, and ordinary redaction shifts
  every offset downstream of the edit. Length-preserving masking satisfies both, and it keeps
  unredacted personal data off third-party APIs at no cost.
- **Rejected:** Redact-then-recompute-offsets (fragile, and silently wrong when it fails);
  redact nothing (violates §12).

## ADR-4 — `src/llm/` gateway replaces `src/extract/cache.py`

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §14 (module split may evolve), §19.5, §13.1
- **Decision:** Caching, retry, repair, and provider adapters live in `src/llm/`. Prompts stay
  per stage in `relevance/prompts.py` and `extract/prompts.py` as specified.
- **Rationale:** Relevance classification, extraction, and Ask synthesis all need the same cache
  and repair behaviour. Leaving the cache under `extract/` forces either duplication or a
  stage-to-stage import, which violates the separation §13.1 requires.
- **Rejected:** Cache under `extract/` as literally listed in §14.

## ADR-5 — Add `src/review/` and `src/pipeline/` packages

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §14, §19.2, §19.4, §19.5, §26
- **Decision:** The human-review queue and overrides live in `src/review/`; the stage runner,
  checkpointing, and run manifest live in `src/pipeline/`.
- **Rationale:** The specification requires both a review queue and a run manifest but gives
  neither a home in §14. Both are cross-cutting and belong to no single stage.
- **Rejected:** Scattering review and run-manifest logic across the stage packages.

## ADR-6 — `case_id` ordinals are anchored to first-evidence character position

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-20 (2026-09-21)** — position anchoring is retained. What was
  missing was any rule for the two cases that actually occur: two cases whose first evidence spans
  sit at identical offsets, which happens when one sentence supports two distinct retrieval needs,
  and a case whose offsets cannot be resolved at all. Without tie-breaks the ordinal fell back to
  whatever order the sort received, reintroducing the model-output-order instability this ADR was
  written to remove.
- **Spec sections:** §15.4, §8.5
- **Decision:** `case_id = {doc_id}#c{ordinal:02d}`, where the ordinal is assigned by ascending
  `start_char` of the case's first evidence span.
- **Rationale:** A model may emit two cases from one document in either order across runs.
  Anchoring the ordinal to text position keeps the ID stable, which matters because `case_id` is
  what the Ask surface cites and what evaluators bookmark.
- **Rejected:** Model output order (IDs churn between runs, breaking citations).

## ADR-7 — `extraction_fingerprint` participates in the primary key

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-19 (2026-09-21)** — fingerprint-in-the-primary-key is retained.
  `taxonomy_version` should never have been one of the fingerprint's inputs: extraction does not
  read the taxonomy, so a taxonomy revision changed every case's fingerprint and forced a full
  paid re-extraction to produce byte-identical results — and created a standing incentive not to
  revise the taxonomy at all, against spec §20.
- **Spec sections:** §19.5, §20.1 step 9, §26
- **Decision:** `retrieval_cases` is keyed `(case_id, extraction_fingerprint)`, where the
  fingerprint hashes model, prompt version, schema version, taxonomy version, and content hash.
  `v_current_cases` resolves which row is live, with human overrides taking precedence.
- **Rationale:** Prompt and schema revisions can coexist with prior versions without either
  overwriting history or double-counting cases.
- **Rejected:** Overwrite in place (loses reproducibility across prompt versions).

## ADR-8 — Composite opportunity score is off by default; components always shown

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §21.5
- **Decision:** Unique cases, unique threads, unique authors, source count, mean severity with
  its own denominator, unresolved rate, and recency share are always displayed separately. Any
  composite score is opt-in, weighted from `config/analysis.yaml`, published with its formula,
  and accompanied by a sensitivity analysis (weight perturbation and leave-one-source-out).
- **Rationale:** §21.5 explicitly rejects reliance on `count × average severity`. Making the
  components the default, rather than adding a warning next to a score, is the version of that
  rule that survives deadline pressure.
- **Rejected:** Score-first ranking, which is what the reference prototype does.

## ADR-9 — `reference files/` becomes read-only `prototype/`

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §14, §30
- **Decision:** The directory is moved to `prototype/` unchanged and never edited. Its 16 records
  are not validated research evidence and never enter the pipeline. `explorer.html` is
  regenerated from the committed export for the Phase 11 backup snapshot rather than hand-edited.
- **Rationale:** Matches the structure in §14 and the instruction in §30, while keeping the
  reference available.
- **Rejected:** Deleting it (loses the reference); editing it in place (loses the baseline the
  rebuild is measured against).

---

## ADR-10 — Commit `raw_text_audit`; keep unredacted `raw_text` local-only

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-23 (2026-09-21)** — the local-versus-committed split and the
  analysis-reproduction-is-not-re-collection distinction are both retained and strengthened. What
  changed is the payload: committing the **full** `raw_text_audit` for every document publishes far
  more source text than verifying the evidence requires, and length-preserving masking removes PII
  patterns the detectors caught, not everything a post might reveal about its author. ADR-23
  narrows the committed text to the minimum excerpt containing the validated spans.
- **Spec sections:** §12 (privacy), §27 (reproducible dataset build), §15.1
- **Decision:** The validated export committed to the repository contains `raw_text_audit`
  (length-preserving redacted text, per ADR-3), `normalized_text`, `redaction_spans`,
  `content_hash`, and all evidence offsets. Unredacted `raw_text` stays in `data/raw/`, which is
  gitignored and never pushed. `.gitignore` enforces this from Phase 0.
- **Rationale:** Because masking preserves length, evidence offsets validate against the
  committed text exactly as they do locally. An external evaluator can therefore verify every
  quote, rebuild the analysis, and reproduce the export hashes without ever receiving unredacted
  personal data. This satisfies the Definition-of-Done reproducibility requirement and §12
  simultaneously rather than trading one against the other.
- **Consequence:** What an external party can rebuild is the *analysis*, not the *collection*.
  Re-collection requires their own credentials and will not reproduce the corpus, because public
  posts get edited and deleted. The README methodology section must state this plainly rather
  than implying full end-to-end reproducibility.
- **Rejected:** Committing unredacted raw text (violates §12); committing no raw text at all
  (evaluators cannot verify a single quote, which defeats §31).

## ADR-11 — Near-duplicate threshold: simhash Hamming ≤ 3 duplicate, 4–6 to review

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-21 (2026-09-21)** — the Hamming band survives as a default. A
  similarity threshold alone was insufficient: it had no guard against collapsing identical short
  text written independently by two different users, which is the single most valuable prevalence
  signal in the corpus and is destroyed irreversibly and invisibly. ADR-21 adds a minimum token
  length, a cross-author guard, and explicit review states.
- **Spec sections:** §17.11, §26 (threshold in configuration), §24 Phase 3
- **Decision:** 64-bit simhash over 3-word shingles of `normalized_text`. Hamming distance ≤ 3 is
  marked `near` duplicate; 4–6 opens a human-review item; > 6 is distinct. The value lives in
  `config/analysis.yaml`.
- **Rationale:** A conservative starting band that catches cross-posts and quoted repeats without
  collapsing genuinely different reports of the same failure — the error that would quietly
  destroy prevalence counts.
- **Calibration obligation:** During Phase 3, review every pair the default flags and every pair
  in the review band on the pilot corpus, then record the final value as an amendment to this
  entry. The threshold is not settled until that review happens; short store-review texts in
  particular tend to collide at low Hamming distance without being duplicates.
- **Phase 3 calibration amendment (2026-09-27):** The 35-document pilot was evaluated. No pair
  fell in the automatic band (Hamming 0–3). No pair fell in the review band (Hamming 4–6). The
  ten nearest eligible negative controls had distances 21–23. The researcher reviewed all ten
  and classified all ten as distinct. The 3/6 thresholds are retained provisionally. The pilot
  supports the threshold's conservatism, but it contains no positive duplicate examples, so
  duplicate recall cannot yet be estimated. This is not a comprehensive validation. Calibration
  must be repeated during the scaled-corpus phase when genuine positive or in-band pairs become
  available.
- **Rejected:** A single hard cutoff with no review band (forces a false binary on exactly the
  ambiguous cases that need a human).

## ADR-12 — Recency window: 12 months, rolling, configurable

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §21.4 (recent versus historical occurrence), §26
- **Decision:** "Recent" means published within 12 months of the corpus collection date. The
  window lives in `config/analysis.yaml` and the app displays the resolved date boundary rather
  than the word "recent" alone.
- **Rationale:** §21.4 requires the recent/historical split without defining it. Twelve months is
  long enough to accumulate cases per cluster and short enough to separate current behaviour from
  2021-era complaints.
- **Secondary view:** If the corpus shows an inflection around the Ask Photos rollout, add a
  second, clearly labelled split at that date as an amendment. It is a more meaningful boundary
  for this specific problem, but it is a product-event boundary, not a recency boundary, and
  conflating the two would make the "recent versus historical" column mean two things at once.
- **Rejected:** Anchoring the primary window to the Ask Photos rollout (couples a general recency
  metric to one feature's timeline).

## ADR-13 — Comment-level permalinks are available for both YouTube and Google support forums

- **Date:** 2026-09-18
- **Status:** **Superseded by ADR-22 (2026-09-21)** — this entry claimed "verified against current
  documentation" and cited no documentation, which makes the claim unverifiable by the next reader.
  A verification pass on 2026-09-21 checked both halves against live sources, and the outcome is
  worth recording precisely, because both URL forms turned out to be **correct**. The YouTube half
  is carried into ADR-22 with links, including confirmation that the `id` filter is Google+-only and
  that reply trees are one level deep. The support-forum `msgid` form is also confirmed live — it is
  set and read back by Google's own shipped frontend JavaScript — so what was actually wrong here
  was the *epistemics*, not the URL: an uncited "verified" for an undocumented parameter that
  carries no stability commitment. ADR-22 keeps the source on manual import for a different reason
  than this entry anticipated, namely Google's terms rather than addressability, and separately
  corrects the risk labelling of the two store collectors, which verification closed outright.
- **Spec sections:** §17.10, §11.3, §15.1
- **Decision:** Both sources may contribute comment-level and reply-level documents, because both
  expose stable per-comment identifiers that satisfy §17.10.
  - **YouTube:** `commentThreads.list` returns `snippet.topLevelComment.id` for top-level
    comments; `comments.list?parentId=...` returns each reply's `id`. The permalink is
    constructed as `https://www.youtube.com/watch?v={videoId}&lc={commentId}`. The API does not
    return this URL, so the collector builds it and stores it as `source_url`, with
    `source_item_id = commentId` and `parent_thread_id = videoId`.
  - **Google support forums:** a reply is addressable as
    `https://support.google.com/{product}/thread/{threadId}?hl=en&msgid={replyId}`, with
    `source_item_id = replyId` and `parent_thread_id = threadId`.
- **Rationale:** §17.10 permits multiple comments in one thread to be separate documents only
  when each has a comment-level ID or permalink. Both sources meet that bar, so thread-level-only
  collection is not necessary and would discard the reply text where most retrieval detail sits.
- **Caveats carried into Phase 7:**
  - The `comments.list` `id` filter is documented as returning `operationNotSupported` for
    non-Google+ comments; the collector must use `parentId` traversal, not `id` lookup.
  - YouTube Data API quota is the practical limit on volume, not the API surface. Confirmed
    2026-09-21 against the [quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost):
    `commentThreads.list` and `comments.list` cost **1 unit** each against a default pool of
    **10,000 units/day**, so comment reading is effectively unconstrained at this corpus size.
    `search.list` sits in a **separate bucket of 100 calls/day**, which makes *video discovery*,
    not comment retrieval, the binding constraint. Phase 7 should seed video IDs from a curated
    list rather than paginating search.
  - The support-forum `msgid` has **no official API**. This entry proposed parsing it from the
    public thread page under §11.3's permitted-scraper rules, with manual CSV as the fallback.
    **ADR-22 reverses that default:** manual import is the only path, because Google's terms bar
    scraping content belonging to other users regardless of whether `robots.txt` allows the path.
    The `msgid` parameter itself is confirmed live and is retained for *constructing* `source_url`
    on manually imported forum documents.
- **Rejected:** Thread-level-only collection for both sources (would have collapsed many distinct
  users into one document and lost per-user evidence).

## ADR-14 — Default model provider is Anthropic; no second-provider agreement check in Part 1

- **Date:** 2026-09-18
- **Status:** Accepted
- **Spec sections:** §19.3 (provider-neutral interface), §26, §29 item 11
- **Decision:** `config/models.yaml` sets Anthropic as the default provider, matching the
  reference prototype. The gateway stays provider-neutral with adapters for Anthropic, OpenAI,
  and a `null` offline provider. Model names appear only in configuration, never in source code.
  Dual-provider agreement checking on boundary cases is **out of scope for Part 1**.
- **Rationale:** One provider keeps the Phase 6 quality measurement interpretable — precision is
  attributable to a prompt and a model rather than to an ensemble. The OpenAI adapter is built
  anyway to prove the interface is genuinely neutral and to provide an escape hatch if rate
  limits or availability become a problem mid-run.
- **Rationale for deferring agreement checks:** Human double-coding of 20% of the gold set (§24
  Phase 6) already provides the inter-rater signal that a second model would approximate, and it
  provides it against ground truth rather than against another model's guess.
- **Rejected:** Dual-provider consensus in Part 1 (doubles cost and complicates the quality
  report without improving ground truth).

---

# Specification-consistency revision — 2026-09-21

ADR-15 through ADR-29 come from a consistency review of `problem-statement.md`,
`ARCHITECTURE.md`, and `IMPLEMENTATION-PLAN.md`. No implementation code existed at the time, so
every change below is a specification change rather than a refactor.

## ADR-15 — Split the collection contract into `CollectedDocument`, `DocumentDerived`, and `DuplicateLink`

- **Date:** 2026-09-21
- **Status:** Accepted
- **Supersedes:** ADR-3 (field placement only; the redaction technique is retained)
- **Spec sections:** §15.0, §15.1, §15.6, §15.7, §13.1
- **Decision:** Three contracts replace the single `RawDocument`:
  - `CollectedDocument` — immutable collection-time provenance and raw text only, including
    `raw_text_sha256` and `source_url_key`, both pure functions of collected values.
  - `DocumentDerived` — `normalized_text`, `raw_text_audit`, `redaction_spans`, `canonical_url`,
    `content_hash`, `simhash`, `token_count`, `language_detected`, `normalizer_version`.
  - `DuplicateLink` — the duplicate relationship, kind, similarity, method, and review state.
  The governing rule is now explicit: **no contract may require a field that a later stage
  produces**, asserted by a test that validates a `CollectedDocument` with no derived record
  present anywhere.
- **Rationale:** The single contract required `normalized_text`, `content_hash`, `duplicate_of`,
  and `duplicate_kind` — all Phase 3 outputs — on a record written in Phase 2. Three concrete
  consequences followed. Manual import, which spec §11.4 now designates the guaranteed baseline,
  could not produce a valid document without running the normalizer. Phase 1 could not be
  completed and tested without anticipating Phase 3. And duplicate status, which is a
  relationship between two documents, was stored as a property of one of them, leaving nowhere to
  record a review state or a pair that was examined and rejected.
- **Rejected:** Keeping one wide contract with the derived fields optional. Optional-but-expected
  fields drift into required by usage, and nothing would have failed a test when they did.

## ADR-16 — Evidence-required field map, closed exception list, derived `all_evidence_spans`

- **Date:** 2026-09-21
- **Status:** Accepted
- **Spec sections:** §15.10, §17.1, §17.16, §16.9
- **Decision:** Evidence enforcement becomes data. `src/models/evidence_map.py` holds
  `EVIDENCE_REQUIRED` and `EVIDENCE_EXEMPT`:
  - **Required**, each needing at least one valid field-level span: `scope_class`,
    `known_item_status`, `target_asset_type`, `target_subjects`, `retrieval_trigger`,
    `remembered_cues`, `forgotten_information`, `exact_query`, `query_paraphrase`,
    `query_strategies`, `reformulation_count`, `system_responses`, `workarounds`, `outcome`,
    `impact_signals`, `severity`, `problem_summary`.
  - **Exempt**, a closed list containing only identifiers, provenance, versions, uncertainty
    metadata, and derived fields.
  - The requirement is gated by `DimensionObservationStatus`: `stated`, `explicitly_none`, and
    `uncertain` require evidence; `not_stated` and `not_applicable` require its absence and an
    empty value.
  - `all_evidence_spans` is the **derived** de-duplicated union of field-level spans. A
    model-supplied value is discarded, and a span attached to no field fails validation.
  - A test walks the Pydantic field sets and asserts every field appears in exactly one list.
- **Rationale:** "Every substantive extracted field must be supported by a verbatim span" was a
  sentence, not a mechanism, and several named fields — `known_item_status`,
  `target_asset_type`, `outcome`, `impact_signals`, `query_strategies` — had no evidence
  relationship at all in the contract. Worse, `all_evidence_spans` as the *only* evidence
  relationship allowed a model to satisfy the requirement in bulk: attach six plausible quotes to
  the case, leave every individual field unevidenced, and pass. The record looks thoroughly
  sourced and no single claim in it is traceable, which is the exact failure spec §31 exists to
  prevent.
- **Rejected:** Per-field checks written inline in the extractor. They cannot be audited as a set,
  and a newly added field silently escapes them.

## ADR-17 — `is_relevant` derived; evidence for every scope class; technical state separated

- **Date:** 2026-09-21
- **Status:** Accepted
- **Spec sections:** §15.3, §16.10, §17.14, §17.15, §17.18, §19.2
- **Decision:** Three changes to `RelevanceDecision`:
  1. `is_relevant = scope_class in {core_incomplete_recall, adjacent_known_item_retrieval}`,
     computed after parsing. The prompt does not ask for it, any supplied value is discarded, and
     a stored disagreement is rejected by a `CHECK` constraint and a test.
  2. **Every** decision requires non-empty evidence, including `out_of_scope`.
  3. Provider unavailability, timeout, parse failure, schema failure, and evidence failure are
     recorded in a separate `DecisionTechnicalState`. A non-`ok` state forces a null
     `scope_class`, empty evidence, and its own funnel line; it is never `out_of_scope`.
- **Rationale:** `scope_class` and `is_relevant` were independently predicted, so a single record
  could assert `out_of_scope` and `is_relevant = true` with nothing in the system able to arbitrate
  — and either value might be the one a downstream query read. Requiring evidence only for
  "relevant" decisions meant the *exclusion* decisions, which determine what leaves the corpus
  entirely, were the least accountable judgements in the pipeline. And with no technical state, a
  provider outage had to be encoded as some scope class; whichever was chosen, an infrastructure
  problem would present as a research finding, in the direction that flatters the corpus.
- **Rejected:** Keeping `is_relevant` predicted with a consistency warning. A warning that fires
  during a 300-document run is a warning that gets filtered.

## ADR-18 — Append-only `StageEvent` replaces the `doc_state` lifecycle

- **Date:** 2026-09-21
- **Status:** Accepted
- **Spec sections:** §15.8, §21.1, §13
- **Decision:** There is no lifecycle column. Every stage appends `StageEvent` rows carrying
  `target_type`, `target_id`, `stage`, `status` (`started`, `succeeded`, `failed`, `skipped`,
  `dropped`, `unavailable`), `reason_code`, `attempt`, `run_id`, and `occurred_at`. Current status
  at a stage is the latest event for that `(target_id, stage)` pair, exposed as `v_stage_status`.
  The §21.1 funnel is computed per stage. Duplicate status stays in `DuplicateLink` and is not a
  stage.
- **Rationale:** The states in the old `doc_state` were not mutually exclusive, so a single column
  had to discard true facts. A document can be a duplicate **and** successfully extracted;
  `duplicate_marked` and `extraction_valid` are both true, and whichever the column keeps, the
  funnel is wrong — either duplicates vanish from the duplicate line once extracted, or
  extractions vanish once a duplicate link appears. A document that failed extraction once and
  succeeded on retry has two facts and one column. And a document's position is genuinely plural:
  it is imported *and* normalized *and* classified *and* extracted, permanently. Spec §21.1 asks
  for those lines separately, which a mutually-exclusive column cannot deliver.
- **Rejected:** A lifecycle column plus a separate duplicate flag. That fixes one collision and
  leaves the retry and multi-stage-presence problems untouched.

## ADR-19 — `taxonomy_version` scoped to taxonomy stages only

- **Date:** 2026-09-21
- **Status:** Accepted
- **Supersedes:** ADR-7 (fingerprint-in-key retained; inputs corrected)
- **Spec sections:** §19.5, §26.2, §15.4, §15.9, §20.1
- **Decision:** `taxonomy_version` is removed from `extraction_fingerprint` and from the
  prefilter, relevance, extraction, and Ask synthesis cache keys. It appears only in
  `assignment_fingerprint` and the taxonomy candidate-generation and assignment cache keys.
  `RetrievalCase` loses its `taxonomy_version`, `candidate_cluster`, and `cluster_confidence`
  fields entirely; cluster labels exist only in `ClusterAssignment`.
- **Rationale:** Extraction never reads the taxonomy, so including the taxonomy version in its
  key meant publishing taxonomy `v2` invalidated every cached extraction and re-ran the entire
  corpus through a paid model to produce byte-identical output. Beyond the waste, that creates a
  standing financial reason not to revise the taxonomy — in direct opposition to spec §20, which
  requires the taxonomy to be refined against evidence and re-assigned across the corpus.
  Removing `candidate_cluster` from the case is the structural half of the same point: with no
  field, there is nothing for a later prompt revision to start filling in "just provisionally".
- **Rejected:** Keeping the field null through Phase 5 and relying on discipline (the previous
  arrangement). A nullable field on a hot path is an invitation.

## ADR-20 — Identifiers derivable at their own stage; lowest-`doc_id` canonical; case-ID tie-breaks

- **Date:** 2026-09-21
- **Status:** Accepted
- **Supersedes:** ADR-6 (position anchoring retained; tie and failure rules added)
- **Spec sections:** §26.1, §26.3
- **Decision:**
  1. `doc_id` derives from collection-time values only: `source_item_id`, else `source_url_key`,
     else `sha1(source_name | author_hash_or_"anon" | published_at_iso_or_"" | raw_text_sha256)`.
     It must **not** accept `content_hash`; the helper's signature excludes it.
  2. The canonical document of a duplicate group is the **lowest `doc_id`** under byte-wise
     ascending comparison, replacing "first collected".
  3. `case_id` ordinals sort by `start_char`, then `end_char`, then `sha1(quote)`, then
     `sha1(canonical_case_payload)`. A case with unresolvable offsets gets
     `{doc_id}#u{sha1(payload)[:8]}`, is never valid, and enters review with
     `evidence_offsets_unresolved`.
  4. A quote with missing offsets is located when the occurrence is unique, or nearest a supplied
     hint; an ambiguous tie with no hint is left unresolved and reviewed, never guessed.
- **Rationale:** `content_hash` in the `doc_id` fallback made the identifier undefinable at
  import, so manual import depended on the normalizer and a normalizer revision silently changed
  manual rows' identities. "First collected" was not a property of the documents at all — it
  depended on source order, pagination, checkpoint resumption, and analyst paste order — so two
  runs over the same corpus could pick different canonical documents and show an evaluator a
  different `source_url` for the same evidence, violating the Phase 3 criterion that re-running
  produces identical duplicate assignments. And picking the first occurrence of an ambiguous quote
  would produce an arbitrary offset that passes validation, which is worse than a visible gap
  because it looks verified.
- **Rejected:** Lowest `content_hash` as the canonical rule — unavailable at import, and it ties
  when text is identical, which is precisely the duplicate case.

## ADR-21 — Deduplication safety conditions

- **Date:** 2026-09-21
- **Status:** **Accepted (defaults, calibration pending Phase 3)**
- **Supersedes:** ADR-11 (band retained as a default)
- **Spec sections:** §19.6, §26.5, §15.7, §16.11
- **Decision:** Re-ingestion of the same source item is always a duplicate — same natural key
  resolves to the same `doc_id` and adds no row; a different natural key produces a
  `same_source_item` link, auto-confirmed. Every **other** automatic decision requires all four
  safety conditions:
  | Condition | Default | Reason code on failure |
  |---|---|---|
  | both `token_count >= dedupe_min_tokens` | 25 | `short_text_below_dedupe_minimum` |
  | not (both `author_hash` present and different) | — | `different_authors_identical_text` |
  | similarity outside the review band | Hamming ≤ 3 confident, 4–6 review | `near_duplicate_in_review_band` |
  | not a quoted repeat | — | `quoted_repeat_ambiguous` |
  `review_state` is one of `auto_confirmed`, `pending_review`, `human_confirmed`,
  `human_rejected`. Pending links are excluded from the duplicate count *and* the collapse logic
  and appear on their own funnel line. Rejected links are retained.
- **Rationale:** The two errors are not symmetric. Failing to collapse a duplicate inflates a
  count and is visible and reversible. Collapsing two genuine users is invisible and
  irreversible — and the specific case it destroys is the most valuable signal in the corpus: two
  people independently writing "can't find my photos" are the strongest possible prevalence
  evidence, and they are exactly what short-text simhash collision merges. Short store reviews
  have too little text for the hash to discriminate, which is why length is a precondition rather
  than an input to the score.
- **Calibration obligation:** In Phase 3, review every pair the defaults flag and every pair in
  the review band on the pilot corpus, then amend this entry with the final `dedupe_min_tokens`
  and band values. **Phase 3 pilot result (2026-09-27), recorded on ADR-11:** no in-band pairs;
  the ten nearest controls (Hamming 21–23) were all judged distinct. `dedupe_min_tokens` and the
  3/6 band are unchanged and provisional. The pilot does not estimate duplicate recall. Repeat
  the calibration on the scaled corpus.
- **Rejected:** Similarity thresholds alone; a single hard cutoff with no review band.

## ADR-22 — Source feasibility tiers; no verification claim without primary documentation

### Amendment — route-specific reassessment, 2026-10-01

The owner authorized reassessing the blanket closure conclusions while retaining
robots, terms, and access restrictions. The [source audit](SOURCE-COLLECTION-AUDIT-2026-10-01.md)
supersedes the three source rows and consequences 2–4 below wherever they claim
permanent closure, universally empty Apple feeds, or an unconditional Google
terms ban. Those passages remain a historical record, not current instructions.
The same correction applies to the rationale and rejected-options wording below.

Current findings: Google Photos community is **technically available but access
requirements unresolved**; Google Play and Apple review collection are **blocked
for the inspected routes**. Publisher APIs require access this project does not
have. The inspected Play RPC and Apple RSS paths are robots-disallowed. Supplied
community thread URLs are not robots-disallowed, while native search/internal
API paths are; fetching permission and discovery must be evaluated separately.
No source data probe was made: zero data requests and zero records per source.
No adapter is verified or enabled. A future documented permitted route may be
reassessed; unofficial library availability alone is not permission or collection.
Primary endpoint, policy, and collector-code evidence is linked in the audit.

### Original decision record — 2026-09-21

- **Date:** 2026-09-21
- **Status:** Accepted
- **Supersedes:** ADR-13
- **Spec sections:** §11.4, §11.3, §17.10
- **Decision:** Every source carries a feasibility tier, and a tier may be raised only by adding
  primary vendor documentation to this entry. Every row below was checked against live vendor
  documentation on **2026-09-21**.

| Source | Tier | Verification status | Primary documentation |
|---|---|---|---|
| Manual CSV / JSONL | **guaranteed baseline** | n/a — built in this repository | — |
| YouTube comments | **supported automated** | permitted, documented, and **exercised** on 2026-10-04 | [`commentThreads.list`](https://developers.google.com/youtube/v3/docs/commentThreads/list) · [`comments.list`](https://developers.google.com/youtube/v3/docs/comments/list) · [quota costs](https://developers.google.com/youtube/v3/determine_quota_cost) |
| Reddit posts and comments | **optional, credential-dependent** | permitted, documented, **unexercised**; **skipped 2026-10-04** — self-service keys are no longer issued, and this project will not request access | [Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data) · [API reference](https://www.reddit.com/dev/api/) · [Data API Terms](https://redditinc.com/policies/data-api-terms) |
| Google Play Store reviews | **experimental** | **closed for apps we do not publish** | [Play Developer API `reviews`](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews) · [`reviews.list`](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/list) · [Reply to Reviews](https://developers.google.com/android-publisher/reply-to-reviews) — "your app" · [`play.google.com/robots.txt`](https://play.google.com/robots.txt) · [Google ToS](https://policies.google.com/terms) |
| Apple App Store reviews | **experimental** | **closed for apps we do not publish**; legacy RSS feed **returns zero reviews** | [App Store Connect `GET /v1/apps/{id}/customerReviews`](https://developer.apple.com/documentation/appstoreconnectapi/get-v1-apps-_id_-customerreviews) · [rate limits](https://developer.apple.com/documentation/appstoreconnectapi/identifying-rate-limits) · [Apple Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) |
| Google Photos Help Community | **manual import by default** | **no documented API**; URL form live but undocumented; ToS bars scraping others' content | [`support.google.com/robots.txt`](https://support.google.com/robots.txt) · [Google ToS](https://policies.google.com/terms) |

- **Consequences:**
  1. Manual import is the guaranteed baseline. The internal 300-document ambition must remain
     reachable through manual import plus YouTube alone. ADR-32 removes it as an assignment
     completion rule and reports the actual corpus instead.
  2. **Both app stores are structurally closed, not merely undocumented.** Each vendor's only
     official review API is gated by *publisher authentication* — Google Play's `reviews` resource
     requires the `androidpublisher` scope plus a "Reply to reviews" grant inside the caller's own
     Play Console, and Apple's `customerReviews` hangs off the `apps` collection of the caller's own
     App Store Connect account. This is the decisive point for planning: **no quota increase, paid
     tier, or access request changes the answer**, because the limit is ownership rather than
     throughput or cost. Neither collector is built or scheduled, and no amount of Phase 7 effort
     will open them. The previous plan ranked these two **first** and called them "low risk",
     confusing ease of implementation with permission. Availability is not permission.
  3. **Do not use the legacy Apple review RSS feed.** `itunes.apple.com/{cc}/rss/customerreviews/...`
     is undocumented by Apple, is disallowed by `itunes.apple.com/robots.txt` (`Disallow: /*/rss/*`),
     and on 2026-09-21 returned HTTP 200 with **zero review entries** for five well-known app IDs
     across two storefronts, both sort orders, both formats, and the paginated variant. Third-party
     posts still claiming it works are wrong. Its formal deprecation date could not be confirmed
     from a first-party notice; the empty responses were observed directly.
  4. **The support-forum blocker is terms, not addressability.** ADR-13's
     `support.google.com/{product}/thread/{threadId}?msgid={replyId}` form is **confirmed live** —
     `msgid` is set and read back by Google's own shipped frontend JavaScript to focus a specific
     reply, and `support.google.com/robots.txt` disallows only `/*/search`, `/*/api`, `/*/apis`,
     `/*/forum-attachment`, and the `search.py`/`search.go` paths, so `/photos/thread/*` is not
     robots-disallowed. ADR-13's error was therefore narrower than first recorded: the URL form was
     right, but it was **undocumented** and cited nothing, so it carried no stability commitment.
     The source still defaults to manual import, because Google's Terms separately prohibit
     "scraping content that doesn't belong to you" — a clause that robots.txt compliance does not
     satisfy, and forum posts belong to their authors. Note also that thread *search* is
     robots-disallowed while the thread index is not, which constrains discovery independently.
  5. **Permitted is not exercised.** Reddit stays `permitted, documented, unexercised`.
     On 2026-10-04 the owner directed the project to skip it: Reddit no longer issues
     self-service API keys, new access requires approval, and new public-API requests
     stop being accepted after 2026-10-31. This project will not file that request.
     The collector remains and skips while credentials are absent. The 17 Reddit
     documents already in the corpus are manual imports. YouTube was exercised on
     2026-10-04: 40 `commentThreads.list` / `comments.list` requests wrote 266 new
     comments. Seed choice used `channels.list`, `playlistItems.list`, and one
     `videos.list` call. `search.list` was not called. `youtube.enabled` stays false.
  6. Collector design constraints confirmed for Phase 7: YouTube's `id` filter is documented as
     Google+-only on both method pages, so replies must be traversed by `parentId`, and the reply
     tree is **one level deep** ("YouTube currently supports replies only for top-level
     comments"). Reddit requires registered OAuth credentials **even for read-only** access,
     because unauthenticated traffic from a hosted provider's netblock is blocked, and its free
     tier permits 100 queries/minute per client ID for **non-commercial** use only. If this
     research is ever framed as commercial, Reddit needs a separate agreement.
  7. **One citation in this table is weaker than the others, and the rule requires saying so.**
     Reddit's Data API Wiki is behind Cloudflare bot verification and could not be loaded directly
     on 2026-09-21, so the 100 queries/minute figure and the rolling-10-minute averaging window come
     from search-indexed copies of that page rather than from a fetch of the page itself. The
     figures agree across the indexed wiki text and Reddit's own r/redditdev announcement, and the
     OAuth requirement *was* confirmed from a page that loaded. Re-read on 2026-10-04 from the
     official Reddit Data API Wiki: free-tier access is 100 queries per minute per OAuth client
     id, averaged over a 10-minute window, and clients must honor `X-Ratelimit-Used`,
     `X-Ratelimit-Remaining`, and `X-Ratelimit-Reset`. The collector relies on those headers.
     Related trap: the
     archived `reddit-archive` GitHub wiki still states 60 requests/minute. That page is stale and
     must not be cited.
- **Rationale:** ADR-13 said "verified against current documentation" and cited nothing, so the
  next reader could not check it and the project could not tell a confirmed mechanism from a
  remembered one. A verification claim without a citation is not a weak claim; it is not a claim.
  The verification pass that produced the table above justifies the rule twice over: it upheld the
  two sources the plan treated as secondary and closed the two it had ranked first.
- **Rejected:** Substituting an unofficial scraping library for a missing official API. Spec §11.3
  forbids bypassing access controls, and an unofficial library's existence says nothing about
  permission. For Play specifically the web route is doubly barred — the `batchexecute` endpoint
  sits under `Disallow: /_` and `/store/getreviews` in `play.google.com/robots.txt`, and Google's
  ToS prohibit automated access that violates robots.txt *and*, separately, scraping content that
  is not yours. Apple's Terms of Use name "page-scrape", "robot", and "spider" explicitly.

## ADR-23 — Public-export excerpt profile

- **Date:** 2026-09-21
- **Status:** Accepted (per-source redistribution terms pending Phase 10)
- **Supersedes:** ADR-10
- **Spec sections:** §12.1, §15.12, §27
- **Decision:** Two profiles with different rules. The **local research profile**
  (`data/raw/`, `data/interim/`) holds the complete collected corpus and is never committed,
  pushed, or deployed. The **public export profile** (`data/exports/public/`) is the only
  committed artifact and carries, per record:
  - the minimum redacted excerpt containing every validated evidence span, plus a configured
    context window (default ±160 characters);
  - `excerpt_start_char` and evidence offsets **rebased to the excerpt**, so highlighting works
    and any span maps back to document coordinates;
  - `excerpt_is_full_text = true` only where a source's redistribution terms explicitly permit
    full text, recorded per source here;
  - provenance, `source_url`, `canonical_url`, dates, and `author_key` (a truncated salted hash);
  - no usernames, no display names, no credentials, no salt, no unredacted PII.
  Enforcement is a test that scans the **generated artifact**, not a review of the exporter.
  Additionally: **analysis reproduction is promised; source re-collection is not.** The README must
  state both.
- **Rationale:** ADR-10 committed full `raw_text_audit` for every document, which publishes far
  more source text than verifying the evidence requires. Length-preserving masking removes the PII
  patterns the detectors matched — not everything a post reveals about its author, and not
  quantities of redistributed third-party text. Excerpting keeps the property that made ADR-10
  worth having, namely that an external evaluator can verify every quote against committed text,
  while publishing only the text that verification actually needs.
- **Rejected:** Committing full text (over-publishes); committing no text (an evaluator cannot
  verify a single quote, defeating spec §31); committing quotes with no surrounding context (a
  quote without context cannot be judged for whether it supports the claim).

## ADR-24 — The review queue is built in Phase 3

- **Date:** 2026-09-21
- **Status:** Accepted
- **Amends:** ADR-5
- **Spec sections:** §24 Phase 3, §19.6
- **Decision:** `src/review/queue.py` is a Phase 3 deliverable. Phase 4 extends it with relevance
  reason codes rather than creating it.
- **Rationale:** Deduplication is the first stage that produces review items — review-band
  similarity, short text, cross-author matches, ambiguous quoted repeats — and the plan created
  the queue in Phase 4. Phase 3 therefore had review decisions and nowhere to record them, and the
  only two workarounds were deferring duplicate review into Phase 4 or auto-resolving the
  ambiguous band. The second is exactly the irreversible error ADR-21 exists to prevent.
- **Rejected:** Deferring duplicate review to Phase 4.

## ADR-25 — Gold-set redesign: separated labels, frozen holdout, named metric families

- **Date:** 2026-09-21
- **Status:** Accepted, clarified by ADR-30 (2026-09-29)
- **Spec sections:** §15.11, §24 Phase 6, §23.7
- **Decision:**
  1. `GoldDocumentLabel` (relevance, one per document) and `GoldCase` (extraction, **zero, one, or
     many** per document) are separate records in separate files.
  2. Deterministic split by hash of `doc_id`: ~40% `dev` for prompt iteration, ~60% frozen
     `holdout` for final reporting, stratified by source platform and scope class. The evaluation
     script refuses to emit error-analysis output for the holdout split.
  3. Metric families: scalar accuracy on `(observation, value)` pairs; multi-label precision,
     recall, and F1 reported **micro and macro separately**; prefilter recall from a gold
     `prefilter_should_pass` label; end-to-end relevance precision and recall counting a prefilter
     drop as predicted not-relevant; unsupported inference rate per field and overall;
     evidence-span validation rate; inter-reviewer agreement (raw plus Cohen's kappa) from
     `pre_adjudication_labels`, reported **before** adjudication.
  4. Gates: **prefilter recall ≥ 0.90**, **end-to-end relevance precision ≥ 0.85**, **end-to-end
     relevance recall ≥ 0.80**.
  5. Records with a non-`ok` `technical_state` are excluded from every metric, with the excluded
     count reported.
- **Rationale:** A single flat gold file could not express a relevant document that yields no
  case, so over-extraction was unmeasurable. One split meant prompt iteration and final reporting
  read the same labels, which makes the final number a fitted number. One "accuracy" figure over
  scalar and multi-label fields is not interpretable, and micro-only multi-label scores hide
  rare-label failure. Prefilter recall needed its own gold label because a prefilter drop is
  invisible to every later stage. And a precision-only gate is trivially satisfied by a pipeline
  that admits almost nothing — it would produce an excellent quality report over a corpus that had
  silently discarded most of its evidence, which is why a recall gate now sits beside it.
- **Rejected:** One gold file with optional case fields; precision-only gating; reporting only
  post-adjudication agreement (adjudication removes the disagreement, so the ambiguity of the
  definitions becomes unmeasurable).

## ADR-26 — Rebuild equality is identical canonical content hashes

- **Date:** 2026-09-21
- **Status:** Accepted
- **Spec sections:** §26.4
- **Decision:** `main.py rebuild` asserts identical **canonical content hashes** for every
  exported artifact, not byte-identical run manifests. Artifacts are canonicalized before hashing
  — records sorted by primary key, keys sorted, numbers normalized — with volatile fields removed:
  `run_id`, execution timestamps (`occurred_at`, `derived_at`, `decided_at`, `extracted_at`,
  `assigned_at`, run start and end), durations, token and request counts, hostname, PID, local
  paths, and cache hit status. `collected_at` and `published_at` are **not** excluded: they are
  properties of the document. The exclusion list is written into the manifest.
- **Rationale:** A manifest legitimately differs between runs, so a byte-identical requirement
  fails for reasons unrelated to the data. The predictable response to a test that cries wolf is
  to weaken or skip it — and at that point genuine non-determinism stops being caught, which is
  the entire purpose of the check. Excluding volatile fields explicitly, and recording which ones,
  makes the equality claim both passable and falsifiable.
- **Rejected:** Byte-identical manifests; hashing whole files without canonicalization (key order
  and float formatting then produce spurious failures).

## ADR-27 — MVP versus stretch scope

- **Date:** 2026-09-21
- **Status:** Accepted; sequencing amended by ADR-32 for the October 2026 demonstration
- **Amends:** ADR-14 (the OpenAI adapter moves to stretch)
- **Spec sections:** §24.0
- **Decision:** **MVP:** manual import, schemas, evidence validator, normalization, dedupe,
  relevance, extraction, gold evaluation, taxonomy, deterministic analysis, evidence browser,
  quality report, public export, Streamlit deployment. **Stretch:** second provider adapter, Ask
  synthesis, automated support-forum collector, automated store-review collectors, composite
  opportunity scoring, static `explorer.html` generation, embeddings. A stretch item is never
  started while an MVP item is unfinished and never becomes an MVP dependency. If the schedule
  compresses, stretch is cut; MVP scope is not reduced.
- **Rationale:** Every stretch item above is attractive and none of them changes a research claim.
  Without the split, the predictable failure is a polished Ask surface beside an unbuilt quality
  report — which spec §28 already warns about in the abstract but never operationalized.
- **Rejected:** One undifferentiated backlog with priorities.

## ADR-28 — First Cursor prompt implements Phase 0 only; every phase carries a prompt

- **Date:** 2026-09-21
- **Status:** Accepted; one-phase rule amended by ADR-32 for three demonstration tracks
- **Spec sections:** §30, §29 item 4
- **Decision:** Spec §30's prompt implements Phase 0 only. `IMPLEMENTATION-PLAN.md` carries a
  paste-ready prompt for every phase, 0 through 11.
- **Rationale:** The §30 prompt asked for Phases 0 **and** 1 while §29 item 4 requires working only
  the explicitly requested phase — the specification contradicted itself in its own starting
  instruction. Phase 1 now carries eleven contracts, the evidence-required field map, and the
  observation-status rules, and it is the phase every later number depends on; bundling it with
  scaffolding is how it gets rushed. Separately, the plan claimed each phase carried a prompt while
  only two did. Both halves of that claim are now true rather than one of them being quietly
  dropped.
- **Rejected:** Removing the "every phase has a prompt" statement instead of writing the prompts.
  The prompts are the plan's main mechanism for keeping one phase's scope from bleeding into the
  next.

## ADR-29 — M1 reports and diagnoses the case count instead of targeting 15–25

- **Date:** 2026-09-21
- **Status:** Accepted
- **Spec sections:** §28, §11.1
- **Decision:** Milestone M1 requires ≥ 30 documents, a full end-to-end run, 100% of claims backed
  by validated spans, a per-stage funnel, and passing tests. The qualifying-case count is
  **reported and diagnosed, not targeted.** Four stages are investigated separately — sampling,
  prefilter, classification, extraction — each with named diagnostic evidence. Document counts
  remain targets; case counts are measurements.
- **Rationale:** The only reliable lever for moving the case count is the strictness of the
  prompts, so a 15–25 band is an instruction to tune prompts until the instrument gives the desired
  reading. The first thing to loosen would be the evidence rules in §17, and the result would be a
  corpus that hit its number and could not be trusted. The count is genuinely informative — it is
  just informative about which stage needs attention, not about whether the project is on track.
- **Rejected:** Keeping the band as guidance with a warning not to tune toward it. A numeric range
  in a milestone is read as a target regardless of the surrounding prose.

## ADR-30 — Phase 4 seed split and abstention metrics do not amend the gold set

- **Date:** 2026-09-29
- **Status:** Accepted
- **Clarifies:** ADR-25
- **Spec sections:** §24 Phase 4, §24 Phase 6, §23.7
- **Decision:**
  1. `relevance-seed-split/v1` is a Phase 4 prompt-development split only. It assigns 35
     development records and 15 holdout records, stratified by scope class. Within a scope
     class, documents are ordered by `doc_id` and holdout seats are `floor(i * n / k)`.
  2. This split does not replace or amend the Phase 6 gold-set split. Phase 6 still uses the
     independently specified hash of `doc_id`, about 40 percent development and 60 percent
     holdout, stratified by source platform and scope class. The open question of the exact
     gold ratio remains a Phase 6 decision.
  3. No Phase 4 seed result may be presented as final product performance. The seed holdout
     has not been used for prompt tuning.
  4. For the Phase 4 seed evaluator, an `ok` prediction with a scope participates in the
     three-class confusion matrix and in covered-only class metrics. A non-`ok` decision or a
     null scope does not receive a predicted class. Those rows are excluded from covered-only
     class metrics. They are abstentions and remain in the denominator of overall end-to-end
     exact-scope accuracy. A missing prediction does the same. Both accuracies are reported.
     Phase 6 gold metrics remain the families in ADR-25, including the rule that a non-`ok`
     technical state is excluded from those gold metrics and the excluded count is reported.
- **Rationale:** The 50-record seed is the set available for prompt development. Using it as if
  it were the frozen gold split would make a later quality report a fitted number. Keeping
  abstentions in the overall denominator stops a run that never decides from looking accurate
  on the rows it happened to finish. Covered-only metrics still describe the decisions that
  were actually completed.
- **Rejected:** Replacing ADR-25's hash split with the 35/15 seed split. Dropping non-`ok`
  rows from the Phase 4 overall accuracy. Treating a null scope as `out_of_scope`.

## ADR-31 — Groq is a provisional Phase 4 relevance provider

- **Date:** 2026-09-30
- **Status:** Accepted
- **Does not amend:** ADR-14. Anthropic remains an implemented adapter.
- **Spec sections:** §19, §24 Phase 4
- **Decision:** The Phase 4 relevance smoke may call Groq through the existing gateway.
  The active configuration is provider `groq`, model `openai/gpt-oss-120b`, and
  `GROQ_API_KEY`. Structured output uses JSON Schema mode for `RelevancePayload`.
  Application validation is unchanged: a bad scope/reason pair, a bad confidence, or a
  span that is not verbatim becomes a technical failure or a review item, never
  `out_of_scope`. A requested temperature of 0 is sent as the fixed floor `1e-8`. The
  cache key and the run manifest record that floor. The prompt lock still identifies
  the requested temperature from configuration. Groq and Anthropic cache entries do not
  overlap. Every external attempt, including a retry, counts toward the six-call smoke
  budget. A 429 uses `Retry-After` when it is a number of seconds, capped at 60.
  Waiting does not count as a call. A retry is allowed only when the remaining
  external-call budget is greater than the number of documents that have not yet
  been attempted. With six documents and a budget of six, each document gets one
  attempt, and a 429 does not consume the next document's attempt. Invalid
  credentials stop the run. Actual billed cost is recorded only when the provider
  supplies it. The list-price estimate is separate. Free-tier usage is not assumed.
  This choice is provisional. It is not a claim that Groq is better than Anthropic,
  and it is not a production default.
- **List price, retrieved 2026-09-30:** Groq's published list price for
  `openai/gpt-oss-120b` is USD 0.15 per million input tokens, USD 0.075 per
  million cached input tokens, and USD 0.60 per million output tokens. Source:
  Groq published list price for `openai/gpt-oss-120b`. If a response does not
  report cached input tokens, the estimate bills every input token at USD 0.15.
  The estimate is not copied into actual billed cost.
- **Rationale:** The smoke needs one live provider, a hard call budget, and a cache
  identity that will not replay an Anthropic response as a Groq response. Leaving
  Anthropic in place keeps the original adapter available without a second code path.
- **Rejected:** Replacing Anthropic. Using the OpenAI SDK to reach Groq. Treating every
  Groq response as free. Letting structured output skip the evidence ladder.

---

## Pending

No open blocking decisions. Two obligations are outstanding and attached to their phases:

| Obligation | Attached to | Amends | Owner |
|---|---|---|---|
| Calibrate `dedupe_min_tokens` and the similarity band on the pilot corpus | Phase 3 | ADR-21 | project owner |
| Record per-source redistribution terms, settling where `excerpt_is_full_text` may be true | Phase 10 | ADR-23 | project owner |

Closed 2026-10-04 by owner direction: do not exercise Reddit and do not request an API key. Self-service key creation is closed, and new public-API requests stop after 2026-10-31. The non-commercial free-tier question is moot because no Reddit API call will be made. YouTube was already exercised the same day.

Three obligations previously listed here were **closed** by the 2026-09-21 verification pass rather
than dropped: documenting a permitted Play Store mechanism, documenting a permitted App Store
mechanism, and confirming the support-forum reply-URL form. The first two are closed negatively —
both APIs are gated by publisher ownership, so there is nothing further to find (ADR-22
consequence 2). The third is closed affirmatively — the URL form is confirmed live, and the reason
the source stays on manual import is the terms-of-service clause, not the URL (ADR-22
consequence 4).

### Unresolved decisions

One genuine decision is not settled by this revision and does not need to be before Phase 6:

| Question | Why it is open | Needed by |
|---|---|---|
| The exact dev/holdout split ratio and stratification keys | 40/60 stratified by source platform and scope class is a reasonable default, but the right ratio depends on how many gold documents land in each scope class, which is unknown until labelling starts. Too small a holdout makes the final numbers noisy; too small a dev split makes prompt iteration blind. | Phase 6, before labelling begins |

---

## Implementation decision — 2026-10-01: nullable extraction wire encoding

- **Status:** Implemented and verified offline; vendor acceptance pending separate authorization.
- **Spec sections:** §15.10, §19.4–19.5, §26.2. No application contract or accepted ADR is amended.
- **Evidence:** The separately authorized one-request synthetic diagnostic was rejected
  with HTTP 400 `invalid_request`, parameter `response_format`, and a message requiring
  `anyOf` branch disambiguation. The preserved run is `577e727e72cc`.
- **Decision:** Extraction opts into nullable scalar type arrays in the existing Groq
  request-schema conversion. All 19 scalar-or-null extraction unions are represented
  as `type: [scalar, null]`. Nullable local scalar enum references are inlined with
  the original allowed values plus JSON null. Bounds, strict objects, required keys,
  Pydantic application validation, and evidence gates stay intact. Other compositions
  are untouched; relevance keeps its existing conversion.
- **Identity:** The transmitted-schema digest changes the cache key. Legacy cache
  entries and failed-run artifacts remain intact. Prompt instructions and registered
  `extract/v1` remain unchanged; the embedded wire schema changes alongside the SDK
  request. Run IDs do not include that digest, so any authorized live verification
  needs a new output parent rather than reuse of an occupied run directory.
- **Rejected:** Adding artificial discriminator fields to the response contract,
  removing nulls or enum/range restrictions, changing prompts or labels, altering
  relevance/holdout behavior, deleting legacy cache, or retrying the provider as part
  of this offline fix.
- **Verification:** Mocked request/prompt equality, idempotence, application constraints,
  cache-key migration, and legacy-entry preservation pass. Vendor acceptance and
  extraction quality are not established by these tests; M1 remains incomplete.

### Verification follow-up — 2026-10-01

The user executed one request with the revised schema under the fresh output parent
`data/interim/phase5/diagnostic-nullable-fix`. Its saved technical state is `ok` and
the matching cached response has the correct synthetic document identity and
`cases: []`. This establishes vendor acceptance for that request and supersedes the
pending compatibility status above. It does not measure real-document extraction
quality. Further diagnostic or pilot requests require separate authorization;
the preceding failed-run artifacts remain preserved.

## Implementation decision — 2026-10-01: safe rejected-output diagnostics

Future Groq failures may inspect rejected text transiently up to 65,536 characters,
without retaining the generated text, values, error messages or input/context. The
allowlist is character count, JSON state/error position, application-validation types
and fixed-schema field paths (32 findings, 16 components; unknown names become `*`).
This diagnostic does not accept/repair a failure or replace vendor strict validation.
Optional known finish reasons and request digests identify future attempts; legacy
cache entries remain readable and cache identities stay unchanged. Usage completeness
describes recorded gateway observations, never actual billing or inferred token counts.

One failed core seat may be selected through `--pilot-doc` after the unchanged five-seat
manifest is validated, with cap one and one attempt. Existing guards and default pilot
bounds remain; this is offline preparation, not live authorization. Prompts, schemas,
evidence gates, labels, split and accepted ADRs are unchanged. Historical errors/billing
remain unknown, and M1/extraction quality are not established.

### Verification follow-up — 2026-10-01: completion truncation

The user's one-core-document run `core-diagnostic-01/4a8c7175f992` retained an explicit
provider message identifying completion truncation at the recorded 4096-token limit.
That finding applies to the new attempt only; historical failure causes/charges remain
unknown. The failed generation remains rejected and uncached, with no raw body retained.

Prepared an explicit `--pilot-max-tokens 8192` option only for a single failed core seat,
using the unchanged full manifest and one-call/no-retry controls. Other values/modes are
refused. Default configuration, prompt/schema, evidence gates, labels, split and accepted
ADRs remain unchanged. Existing decoding-aware cache/run identities distinguish this
experiment; no saved run or cache entry is rewritten. Mocked checks and zero-call dry-runs
passed; live execution still requires separate authorization and does not reconstruct
historical billing. The new limit's sufficiency, extraction quality and M1 remain
unassessed.

### Verification follow-up — 2026-10-01: completed 8192-token diagnostic

The completed one-call run `core-diagnostic-8192-01/797b223ff9f9` returned structured
output with `finish_reason=stop`. The output guard refused a duplicate invocation.
This demonstrates completion for that attempt only. Two abbreviated quotes and missing
summary evidence made its case invalid; the existing gate correctly withheld it.
The recorded list-price estimate is not an invoice, and historical charges remain unknown.

Reporting fixes expose failed-candidate/state counts and failure exit status, retaining
accepted empty output as success. Typed invalid candidates are now persisted separately
for review; they never enter analysis, and saved review resolutions are not rewritten.
A transport-guarded cache replay retained the pending case without another request.
Prompt/schema/validator, approved labels, split, holdout lock and accepted ADRs remain
unchanged. Future runs add one review-candidate artifact; historical run files remain
intact. Extraction quality and M1 remain unassessed.

## Implementation decision — 2026-10-01: authorized extract/v2 evidence instructions

The user authorized the exact instruction addition proposed in
`data/interim/phase5/extraction_evidence_correction_proposal.md`. Register `extract/v2`
as active and retain the unchanged `extract/v1` rendering as a historical baseline.
V2 explicitly requires separate verbatim summary support, continuous source quotes,
no inserted ellipses/spliced passages, and empty evidence for not_stated/not_applicable.
The only prompt-body change is the approved addition; unsupported version headers fail.

Pilot and synthetic diagnostic bounds pin the approved active version while retaining
existing provider/model/request caps, SDK/gateway retry settings, cache, key/output
guards and holdout lock. Version-aware cache/run/case fingerprints isolate new requests;
legacy entries and runs are not modified. Global token configuration, application/wire
schemas, evidence validator, approved labels and split remain unchanged.

Synthetic regressions exercise literal source ellipses, fabricated/spliced quotes,
summary support and forbidden evidence for empty observation statuses. They establish
instruction rendering and unchanged controls, not model adherence. Live execution is
not included in this prompt-change authorization. Extraction quality, historical failed
request billing and M1 remain unassessed.

## Implementation decision — 2026-10-01: align extraction detail with the existing contract

The user requested a fix after the v2 diagnostic exposed a transport/application mismatch:
the request schema allowed detail on remembered cues while ObservedValue allowed it only
on target_subjects. Enforce null detail on all six non-subject transport label dimensions
and retain subject-specific optional text. Reject invalid responses instead of stripping
detail or weakening the application gate. Saved runs, cached responses and review items
remain unchanged. This corrects transport to the existing contract; record schema 1.0.0
and extract/v2 instructions remain unchanged. The embedded/transmitted schema changes,
so Groq's schema digest supplies cache separation. Run IDs do not include this digest;
use a fresh output parent rather than resuming or overwriting an earlier run.

Document aggregation must preserve assembly schema_validation_failed instead of mapping
all reviewed cases to evidence_validation_failed. Schema failure takes precedence in a
mixed document's summary/event, while individual case artifacts preserve their findings.
Thirteen new offline regressions verify the fix; full suite: 949 passed, 5 skipped.
The zero-call diagnostic dry-run does not establish provider adherence or extraction
quality. A further live request requires separate authorization; M1 remains unassessed.

## Implementation decision — 2026-10-01: five-document 8192-token cache reuse

The corrected-schema response for `google_support-d7f386f347b7` is cached at 8192
tokens. A five-document check at the configured 4096-token limit would miss that entry
and could request the document again. `--pilot --pilot-max-tokens 8192` without
`--pilot-doc` therefore applies 8192 to the existing five-seat manifest and requires
`--call-budget 4` and `--max-retries 1`. Before any provider call or output creation,
the expected cache entry must match every request parameter and pass local
`ExtractionPayload` validation. A missing, incompatible, or unusable entry fails closed.
The ordinary pilot stays at 4096 tokens and five calls. The single-core diagnostic stays
at one call. SDK retries, prompt pins, the manifest, labels, and the fresh-output and
missing-key guards stay as they are. Offline mode is refused for this path. Automatic
validation of the cached case is not semantic approval. This entry did not authorize
the live command. The user later executed it; the results are in `STATUS.md`. Full
suite at the time of this entry: 958 passed, 5 skipped. Extraction quality and M1
remain unassessed.

## ADR-32 — October 2026 demonstration schedule

- **Date:** 2026-10-01
- **Status:** Accepted
- **Amends:** ADR-22 consequence 1 (the 300-document line is an internal ambition, not an assignment gate); ADR-27 (sequencing only, for the three tracks below); ADR-28 (one phase at a time, for those same tracks)
- **Spec sections:** §1.1, §5, §11.1, §24.0, §27
- **Decision:** The assignment requirement remains Section 5: analyze real public feedback and compare retrieval problems with traceable evidence. Provenance, privacy, evidence validation, and honest reporting stay in force. Milestone 1 and every unfinished phase stay incomplete.

  For the demonstration aimed at 2026-10-03 and the submission on 2026-10-07:

  1. YouTube comment collection, extraction review, and a basic evidence browser may proceed in parallel.
  2. At least 300 documents across four source types is an internal ambition. The submission reports the actual corpus and its limitations. Today that corpus is the 35-document manual pilot workbook, not an API collection.
  3. The only automated collector to start is YouTube comments, written as existing `CollectedDocument` records. Workbook import stays. YouTube remains `documented, unexercised` until a bounded API call is separately authorized.
  4. Chat synthesis, embeddings, composite opportunity scores, additional collectors, and architectural refactoring are deferred.
  5. The basic browser reads existing JSONL. It does not complete the quality report, public export, or Streamlit deployment.

- **Rationale:** User research and a product MVP share the same calendar. Waiting for every numbered phase leaves no demonstration. The assignment does not require a 300-document gate, a second collector, or a generative layer. Relaxing the phase order without relaxing evidence rules is the change that still answers Section 5.
- **Rejected:** Treating the demonstration as Milestone 1. Treating 35 workbook rows as 300 documents. Repairing saved model output so the browser looks complete. Opening the holdout or changing approved labels and splits to process a new batch.

## Implementation note — 2026-10-03: starter development annotation pack

The starter pack seats `gold-split/v1` on the 35 Phase 4 development documents,
using source platform and the existing human seed scope as the strata. Only the
10 gold-`dev` seats are copied, with blank gold fields. The existing seed scope
is not a gold label. The 25 gold-`holdout` seats among those 35, and all 15
Phase 4 holdout documents, stay out of the pack. Two documents whose seed scope
and model scope differ are marked for a second reviewer. The quality gate
remains pending.

## Implementation note — 2026-10-03: Phase 6 evaluation without a gold set

The gold split is `gold-split/v1`: within each source-and-scope stratum, documents
are ordered by the SHA-256 of `gold-split/v1` and `doc_id`, and the first two of
every five are `dev`. Evaluation reads the split stored on a label. It does not
reassign it, and it does not read the Phase 4 seed split as gold. There are no
gold labels yet, so the quality gate is pending. Thresholds stay 0.90, 0.85,
and 0.80.

## Implementation note — 2026-10-03: Phase 5 case overrides

A human case is a new row with `extractor_type = human`. It does not rewrite the
model case. `v_current_cases` uses it only when its validation state is valid.
No override was written for the development corpus, because that would invent a
review decision. Two historical failed calls have no usage fields in their saved
manifests; those charges remain unknown.

## Implementation note — 2026-10-03: development corpus extraction meets M1

The qualifying-case count is 10 analysis cases from 35 development documents.
It was not targeted. Sampling: no new collection; the frozen development split
is the 35-document corpus. Prefilter: 35 succeeded events and no drop event in
that split. Classification: 14 effective decisions are out of scope and were
skipped; 21 were eligible. One model relevance event remains unavailable
(`reddit-c49086caf891`); extraction used the existing human adjacent decision
and did not edit either row. Eleven disagreements with the approved labels were
recorded and the labels were not changed. Extraction: 17 new calls and 4 cache
hits; 6 documents failed the evidence gate and stayed out of
`retrieval_cases.jsonl`; 7 eligible documents stored zero cases; 8 documents
stored 10 cases. The prompt and schema were not loosened to raise that count.
Semantic approval was not granted.

## Implementation note — 2026-10-03: submission app, YouTube batch already saved

`STATUS.md` records the later bounded YouTube collection and the research-batch
model calls. This note does not reopen that work. `app.py` reads the prepared
export of those saved runs and of the development pilot. It does not change the
frozen split, approved labels, or review decisions. Phase 10 remains
incomplete. The development-corpus note above is the M1 record. The 2026-10-01
note below described the collector before that bounded call.

## Implementation note — 2026-10-04: YouTube exercised, Reddit skipped

A bounded live YouTube collection wrote 266 new comment documents in 40
comment-read requests. Combined with the existing manual imports, the deduped
corpus is 318 documents across five platforms: YouTube 272, Google support 21,
Reddit 17, Play Store 5, and App Store 3. YouTube is 272/318, above the 40%
concentration line, and that imbalance is recorded in
`data/processed/phase7-corpus-2026-10-04/funnel_by_source.json`. The Play and
App Store rows are the earlier manual imports. No store or support-forum
collector was added. On 2026-10-04 the owner directed the project to skip Reddit:
self-service API keys are no longer issued, and no access request will be filed.
Reddit made zero requests and stays unexercised. The 17 Reddit rows are manual
imports. No relevance or extraction call was made.
`youtube.enabled` stays false.

## Implementation note — 2026-10-01: YouTube collector, live API unexercised

`src/collect/youtube.py` implements the read-only collector from ADR-32 item 3.
It writes existing `CollectedDocument` records and leaves workbook import in
place. Tests mock `commentThreads.list` and `comments.list`. No live YouTube
request was made, so ADR-22's status for YouTube remains permitted, documented,
and **unexercised**. `config/sources.yaml` keeps `youtube.enabled` false.

## Implementation note — 2026-10-01: research batch, no new documents

`main.py run --research-batch` is the bounded path from ADR-32 for documents
that are not in the frozen seed split. It does not edit that split, the
approved labels, or prior runs. A dry-run of the collected imports selected
nothing, because every stored `doc_id` is already in the split. No provider
call was made. This note does not authorize a live model run and does not
complete Milestone 1.
## ADR-35 — Bounded frozen gold verification (2026-10-04)

The owner authorized completing development freeze, opening the required
holdout sources and making necessary bounded calls. Use the existing gold
seating and stages, not the legacy five-document pilot as a general runner.
Scope extract/v3 to this verification; preserve legacy extract/v2 behavior.
Pin relevance/v5, corrected schema and Groq openai/gpt-oss-120b, temperature 0
(effective 1e-8), 4096 relevance/8192 extraction output tokens, SDK retries 0
and gateway attempts 1. Budgets reserve one first attempt per seat per stage:
20 maximum development requests, 50 maximum holdout requests, cache hits free.

Freeze code/config/source/approved-dev-label hashes before the holdout run.
Prepare reference drafts from audit sources without model predictions, retain
the owner's actual approval, and bind exact labels and packets by hash.
Sunayana reviewed and approved all 25 proposed holdout labels. Sole-human,
AI-assisted labeling is disclosed; no independent coder agreement is invented.
Claim the measurement before calls and claim scoring before report output;
interruption or failure is not permission to retry the same frozen experiment.

The numeric measurement passed five thresholds on 25 reserved gold-holdout
seats, but those seats were previously Phase 4 development data. Do not describe
this as wholly unseen validation, complete the 75–100 research target, or
approve extraction semantics from a quote gate. Report 5/15 case coverage,
failed/empty outputs and unknown usage honestly. Keep all prior runs, caches,
reviews and split membership. Original 15 Phase 4 holdout seats remain separate.

## ADR-36 — Parallel submission integration and separate reference demo (2026-10-04)

**Accepted.** Owner authorized fixing submission gaps, preparing Streamlit
Community Cloud and integrating the n8n collection route. Preserve the original
tagging workflow, labels, model outputs and frozen one-shot measurement. Use
existing collection/stage/gateway/cache/persistence contracts rather than a
second framework. Source collection is a strict original-post envelope with
document/request bounds, author hashing, exact text and no model side effects.
Refuse the supplied old tagging endpoint; Cloud import, credentials and actual
page compatibility are still required. No live n8n verification is claimed.

Provide a separate public view of already-approved development references,
minimum exact evidence, field comparisons and journeys. Reference approval is
not semantic approval of a model case. Curate the Cloud package with an explicit
allowlist; do not publish source/gold/holdout/credentials. Prepare only; actual
account publication remains a separate owner step. No artificial taxonomy,
cluster count, prevalence estimate or composite score is substituted for missing
research. Collection, review and demonstration may progress in parallel; corpus
and gold targets are internal ambitions with actual limitations disclosed.

Sunayana separately authorized one dev-only v4 extraction experiment with at
most 20 requests. It completed six requests and consumed that authorization.
Four of six references match, versus v3 two of six; precision still 0.8333.
Preserve source-based semantic disagreements and the frozen holdout result.
Candidate routing is explicit, version-isolated and refused on holdout. The
paired relevance/v6 candidate is inactive/unmeasured and needs a new paid-run
authorization. Alternative rejected: silently activate candidates globally,
retry holdout, approve model cases from quote validity, or upload the whole
workspace to Cloud. Sections affected: 1, 24, 26 and submission/public-export
guidance; research evidence/quality requirements are not waived.

## ADR-37 — The approved gold set is final (2026-10-04)

**Accepted.** The owner does not have time to label 75–100 documents. The
labels already approved and stored as official gold are the final gold set:
35 documents and 21 cases, split 10/6 development and 25/15 holdout. No
further gold documents will be added for this submission.

This amends the internal volume in spec Sections 11.1, 24 Phase 6, and 27.
It does not edit a label to match a model, move a split, invent a second
reviewer, or treat 35 documents as if they were the former 75–100 volume.
ADR-35's measurement stays 35 documents. Prior holdout exposure, null
agreement, unmatched cases, and unapproved model cases remain disclosed.
Thresholds stay 0.90, 0.85, and 0.80.

**Rejected:** leaving the 75–100 volume open as unfinished required work, and
adding unapproved labels to make the count larger.
