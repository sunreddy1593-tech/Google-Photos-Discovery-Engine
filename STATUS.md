# Status

> Updated after each approved phase (spec Section 29.15).

| | |
|---|---|
| **Completed phase** | Phase 3 — normalization and deduplication (2026-09-27) |
| **Current phase** | Phase 4 — in progress. Offline relevance infrastructure only. Not complete. |
| **Tests** | 682 passing, 4 skipped, 0 failing. `tests/test_relevance.py` and `tests/test_pipeline_runner.py`: 26 passing. |
| **Coverage** | 100% of `src/models/`. Phase 4 covered by `tests/test_relevance.py`, `tests/test_llm_gateway.py`, and `tests/test_pipeline_runner.py` |
| **Last verified** | 2026-09-27 |
| **Blockers** | Recalibrate the ADR-11 band on the scaled corpus. The pilot had no positive or in-band pairs, so duplicate recall is not estimated. |
| **Next command** | See "Next command" below |

---

## Phase 3 — complete

Normalization, deduplication, and the pilot calibration review are done.
Phase 4 infrastructure is in progress and is not complete. The Hamming 3/6 thresholds and `dedupe_min_tokens`
stay at their defaults, retained provisionally. ADR-11 records the amendment.
The scaled-corpus phase must calibrate again when positive or in-band pairs
exist.

`python main.py run --stages normalize,dedupe` reads the Phase 2
`collected_documents.jsonl` and writes gitignored files under
`data/interim/phase3/`. Collected documents are not modified. `raw_text` is
unchanged. `raw_text_audit` is length-preserving. The canonical document of a
duplicate group is the lowest `doc_id` (ADR-20). A shared listing or thread
URL is not a duplicate.

Pilot run, 2026-09-27, 35 documents:

| | |
|---|---|
| Documents derived | 35 |
| Documents with redactions | 0 |
| Redaction spans | 0 |
| Duplicate links | 0 |
| Auto-confirmed | 0 |
| Pending review | 0 |
| Hamming 0–3 | 0 |
| Hamming 4–6 | 0 |

Closest pair was Hamming distance 21. Five documents are under
`dedupe_min_tokens` (25) and none were similar enough to open a review item.
`duplicate_review.csv` stays the operational queue and is header-only.
`data/interim/phase3/duplicate_calibration.csv` holds the 10 nearest
out-of-band pairs, distances 21–23. The researcher classified all 10 as
distinct. Those decisions stay on the sheet across reruns and do not create
links or review-queue items. Duplicate links remain empty.

Human calibration: 10/10 negative controls distinct. Threshold retained
provisionally. Recalibration is carried into the scaled-corpus phase.

Targeted tests: `pytest tests/test_normalize.py tests/test_dedupe.py tests/test_review_queue.py tests/test_architecture.py -q` → 130 passed. Full suite: `pytest -q` → 612 passed.

---

## Phase 2 — complete

The manual pilot corpus is 35 genuine public records in the private workbook:
Google Photos Help, Google Play Store, Apple App Store, YouTube, and Reddit.
The workbook also holds 7 valid search-log sessions. `main.py collect` loads
`AUTHOR_SALT` through configuration and calls `import_workbook`. Phase 3 is
now complete. Phase 4 infrastructure is in progress and is not complete.

Final import: 35 rows read, 35 accepted, 0 rejected, 3 `repeated_source_url`
warnings, 7 search-log rows read, 7 valid, 0 issues. Each repeated URL is a
shared listing or thread permalink. Distinct `source_item_id` values keep the
records separate.

| Criterion | Evidence |
|---|---|
| 35 pilot document rows read and accepted, 0 rejected | `test_pilot_workbook_accepts_all_documents_and_reports_shared_urls` derives the count from non-empty `source_item_id` rows and requires at least 30 |
| Shared listing and thread URLs warn and do not reject | same test: repeated-URL groups are derived from `source_url` and matched to the importer's `repeated_source_url` warnings, including Excel rows 7 and 8 |
| `raw_text` matches the worksheet XML for every accepted row | same test, compared through the xlsx XML rather than the importer's reader |
| No raw author name in the documents file (outside `raw_text`), the report, or the log | same test, plus `test_raw_author_names_are_absent_from_outputs_and_logs` |
| Same author and salt hash the same; a different salt hashes differently; a blank author stays null | `test_author_hash_is_deterministic_and_uses_the_stored_platform`, `test_optional_blanks_stay_null`, and the pilot test |
| `AUTHOR_SALT` has no production default, is not a CLI argument, and is absent from the terminal, the report, and the log | `test_cli_missing_salt_fails_without_a_default`, `test_cli_does_not_accept_a_salt_argument`, `test_cli_success_prints_counts_and_hides_secrets` |
| Search log: exact headers, dates, non-negative counts, `documents_kept` not above `results_scanned`; those rows are not documents | `test_search_log_rejects_bad_counts_and_stays_out_of_documents` |
| CLI exits 0 only when nothing was rejected and the workbook is valid | `test_cli_success_prints_counts_and_hides_secrets`, `test_cli_rejected_rows_exit_nonzero`, `test_cli_invalid_workbook_and_search_log_exit_nonzero` |
| Import does not load Phase 3 | `test_import_does_not_load_phase3_modules` and `test_collect_imports_only_core_models_and_itself` |

`google_photos_help`, the label on the workbook's instructions sheet, is stored
as `google_support`. That is the contract value and the source name in
`config/sources.yaml`. Each use is a `workbook_platform_alias` warning.
Excel datetimes have no timezone; naive values are attached to UTC. A
timestamp that already carries an offset keeps it. The search-log note that
mentions IST is commentary, not a timezone field.

`search_log` is validated and reported. Its rows are not `CollectedDocument`
records. Headers must match exactly. Dates parse the same way as document
dates. `results_scanned` and `documents_kept` must be non-negative, and
`documents_kept` must not exceed `results_scanned`. A bad search-log value
does not reject the documents; the CLI still exits non-zero because the
workbook audit failed. A missing sheet or a renamed header accepts nothing.

`AUTHOR_SALT` comes from the environment or `.env`. It is not a command
argument, it has no hardcoded default, and it is scrubbed from the report and
the log. Tests pass it as an argument to `import_workbook`.

Pilot import, with `AUTHOR_SALT` already in the environment or in `.env`:

```powershell
python main.py collect --path "data\manual\Private\Google_Photos_Pilot_Collection_Workbook.xlsx" --output "data\processed\pilot-import"
```

Exit 0 means no rejected document rows, no search-log issues, and no structural
errors. `repeated_source_url` warnings still exit 0. Exit 1 is an invalid
workbook, a configuration failure, or rejected rows. The terminal prints counts
only.

The private workbook (`data/manual/private/`), `.env` (`AUTHOR_SALT`), and
processed import output (`data/processed/*`) are gitignored. Raw author names
stay in the private workbook and are hashed out of processed output. None of
those files is committed.

### What this slice added

```text
src/collect/   __init__.py  workbook.py  cli.py
tests/         test_workbook_import.py  test_collect_cli.py
main.py        collect subcommand only; later commands still refuse
```

`openpyxl` is the Phase 2 dependency. `httpx` stays out until a collector
makes an HTTP call.

---

## Phase 1 — complete

Exit criteria from `IMPLEMENTATION-PLAN.md` Phase 1, each verified by a command
rather than asserted:

| Criterion | Evidence |
|---|---|
| Every schema has positive and negative tests | `pytest tests/test_models.py -v` → 186 passed, at least one rejection test per contract |
| Fabricated evidence fails validation | `test_evidence.py::test_fabricated_quote_is_rejected` |
| `CollectedDocument` validates with no later-stage field present | `test_models.py::test_collected_document_validates_with_no_later_stage_module_imported` runs in a subprocess and asserts `sys.modules` never gained a derived contract |
| Every model field is classified evidence-required or evidence-exempt | `test_evidence_map.py::test_every_field_is_classified_exactly_once` iterates `model_fields` for both contracts |
| Missing facts stay null or empty with an observation status | `test_models.py::test_defaults_are_not_stated_rather_than_a_value` plus the status-gate parametrisation in `test_evidence_map.py` |
| No `unknown` placeholder exists | `test_models.py::test_no_enum_carries_a_placeholder_member` runs once per enum over every member |
| Synthetic fixtures are marked | `test_models.py::test_every_fixture_document_is_marked_synthetic` and `test_a_synthetic_fixture_cannot_be_mistaken_for_direct_user_evidence` |
| Invariants I2, I3, I6, I11, I12, I13 covered | I2/I3 in `test_evidence.py`, I6 in `test_models.py`, I11 in `test_models.py` and `test_architecture.py`, I12 in `test_evidence_map.py`, I13 in `test_models.py` |

### What exists

```text
src/models/   enums.py  evidence_map.py  base.py  evidence.py
              collected_document.py  document_derived.py  duplicate_link.py
              relevance.py  retrieval_case.py  stage_event.py
              cluster_assignment.py  gold.py  export.py
src/extract/  validator.py            span ladder, record gate, span union,
                                      analysis gate
tests/        synthetic.py  test_models.py  test_evidence.py  test_evidence_map.py
```

`src/models/__init__.py` re-exports through `__getattr__` rather than eager
imports. Eager imports would make `import src.models.collected_document` pull in
every later-stage contract, which is exactly what invariant I11's test forbids.

### What deliberately does not exist

No collectors, no normalizer, no deduplication, no `src/llm/`, no store layer, no
analysis, no retrieval, no `app.py`. No review queue either: Phase 1 produces
the routing decision, and ADR-24 builds the queue in Phase 3, when the first
review items exist. `src/extract/` holds the validator and nothing else; the
extraction prompt and its runner are Phase 5.

### The evidence ladder, as built

`validate_span` tries four rungs in order and records which one answered, so a
later report can separate clean extraction from salvaged extraction:

1. **Exact** — `quote == source_text[start_char:end_char]`. Accepted unchanged.
2. **Offset repair** — quote found verbatim elsewhere. One occurrence is
   repaired silently; several occurrences are resolved to the one nearest the
   claimed offset. A genuine tie is *not* guessed: the span becomes
   `ambiguous_tied` / `pending` and routes to human review.
3. **Whitespace repair** — found only after whitespace normalization. Offsets
   move to the real text; `quote` keeps the document's characters, not the
   normalized ones, so the displayed excerpt is still verbatim.
4. **Rejection** — not present at all. `fabricated`, and the **record** is
   invalidated. The affected field is never quietly dropped so the rest of the
   record can be accepted: dropping it would leave the field unevidenced, which
   the status gate rejects in turn, so both exits are closed and the only route
   forward is review.

A span overlapping a redaction is rejected at every rung, including when the
quote itself is exact, because the underlying text was destroyed by redaction
and cannot be re-verified.

### What happens after rung 4

Rejecting the span is only the first step. ARCHITECTURE Section 9.3 rung 4
continues: "the parent record is invalidated, the failure is logged, and the
document enters the review queue", and spec Section 17.12 adds that nothing
invalid reaches the analysis dataset. Each leg is now enforced rather than
described:

| Leg | Where it lives | Test |
|---|---|---|
| Record invalidated | `validate_record` fails on **any** non-valid span attached to the record, and `RecordValidation.apply` writes `validation_state` back onto it | `test_a_rejected_span_invalidates_the_record_it_belongs_to` |
| Error and field recorded | `RecordValidation.invalid_fields` and `.retained_spans` carry the affected fields and the surviving candidates as data | `test_the_invalid_candidate_is_retained_for_review` |
| Failure logged | `_log_invalidation` emits one structured warning carrying `review_reason_code`, `invalid_fields`, and `retained_span_ids` | `test_the_failure_is_logged_with_the_fields_a_report_filters_on` |
| Enters review | `RecordValidation.requires_review` and `.review_reason_code` are the routing decision as data; Phase 3 builds the queue that consumes it (ADR-24) | `test_an_invalidated_record_is_routed_to_review` |
| No analysis output | `gate_for_analysis` raises `EvidenceError`; `select_valid_for_analysis` omits the record | `test_no_invalid_candidate_appears_in_a_valid_output_query` |
| Until corrected | The same record passes once the fabricated span is removed | `test_correcting_the_fabrication_reopens_the_gate` |

**The affected field is never simply dropped.** This is the requirement that
shapes the rest: an invalid span cannot be resolved by discarding the field it
supports and accepting the remainder. Both exits are closed. The record cannot
be marked `valid` while the bad span is attached — a model-level rule on both
contracts, so a store bypassing the validator still cannot write one — and
detaching the span leaves the field unevidenced, which the status gate rejects
in turn. The only route forward is review.

Two filing details are deliberate. An unresolved `ambiguous_tied` span is filed
under `evidence_offsets_unresolved` rather than `evidence_validation_failed`,
because the quote is real and only its position is unknowable, so the review it
needs is a different job from adjudicating a fabrication. And a failing record
becomes `pending`, not `rejected`: it is unconfirmed rather than wrong.

`gate_for_analysis` returns the spans rather than a boolean on purpose. An
`is_eligible()` predicate is a call an aggregation can forget and still get its
data; making the gate the only route to the evidence means analysis code cannot
obtain its quotes without passing through it. `select_valid_for_analysis`
filters on `validation_state` rather than `needs_human_review`, because the two
differ on the reviewed-but-not-revalidated record and on the `pending` record
nobody has looked at.

### Inherited `scope_class` (spec 15.4)

`RetrievalCase.scope_class` is evidence-exempt on the grounds that it is
inherited from a decision that already evidenced it. That exemption is only
honest while the inheritance is real, so `validate_record` checks all three
conditions in `SCOPE_INHERITANCE_CONDITIONS` when the decision is supplied: same
`doc_id`, matching `scope_class`, and the decision's `validation_state` is
`valid`. Each fails for its own reason — a decision about another document is
borrowing a verdict, a differing value is overruling rather than inheriting, and
a `pending` decision has no validated evidence to lend.

The check runs only when the decision is passed in, because the case contract
carries no `decision_id` and the validator cannot fetch the decision itself.
Passing silently when it is absent is the honest behaviour; claiming to have
checked would be worse than not checking.

### The two summary fields

`reason_summary` stays an evidence-exempt paraphrase, and two things keep that
from becoming a loophole. It can never substitute for evidence — every `ok`
decision needs a non-empty `evidence` tuple, and the record gate needs at least
one of those spans to be *valid*, so a long plausible summary buys nothing. And
it can never be rendered as a quotation: `ExportedEvidenceSpan.field_name` must
be an evidence-required field, so the export cannot put the model's own prose in
quotation marks beside a real quote.

`problem_summary` looks like an inconsistency and is not. It is a paraphrase
*and* an evidence-required field, so its span quotes the source text supporting
the summary rather than the summary itself — which is why it remains exportable
while `reason_summary` does not.

---

## Phase 4 — in progress

Relevance infrastructure is implemented and has been exercised offline.
Phase 4 is not complete. No Anthropic, OpenAI, or other paid provider was
called. The seed sheet was reviewed on 2026-09-27. Phase 5 has not started.

`python main.py run --stages prefilter --offline` reads the Phase 2 documents
and the Phase 3 derived rows. It writes gitignored files under
`data/interim/phase4/`. It does not modify `raw_text` or derived records.
Confirmed duplicates would be skipped; the pilot has none. Pending links
would still be classified.

Ruleset `prefilter/v1`. A document is an obvious exclusion candidate only
when at least two distinct multi-word exclusion signals match and the text
has no retrieval language. One keyword cannot drop a document. Retrieval
language together with backup or deletion language stays on the classify
route. The prefilter result is a routing record, not a `RelevanceDecision`.

Pilot prefilter, 2026-09-27, 35 documents:

| | |
|---|---|
| Documents | 35 |
| Canonical | 35 |
| Skipped confirmed duplicates | 0 |
| Routed to classify | 35 |
| Obvious exclusion candidates | 0 |
| Mixed retrieval and exclusion, retained | 0 |
| Single exclusion signal, retained | 0 |
| No exclusion signal, retained for recall | 35 |
| Matched exclusion signals | 0 |

Eight documents mention backup, deletion, storage, or account words. None
matched two multi-word exclusion phrases, so none were dropped. Posts that
also say they cannot find a photo stayed on the classify route.

Relevance dry-run wrote nothing and made no provider call. The null-provider
run classified all 35 canonical documents as `provider_unavailable`, with
empty evidence, null scope, 0 provider calls, 0 tokens, and an estimated
cost of 0. Those rows are not `out_of_scope`. No response was cached.

`data/interim/phase4/relevance_seed_review.csv` is the completed Phase 4
seed review. The first 35 rows were approved on 2026-09-27. The remaining
15 were labeled on 2026-09-29. The sheet now has 50 rows, one per current
pilot document. Every `doc_id` is present once. Every human scope, reason,
and note is filled. Inclusion codes appear only on core and adjacent rows.
Exclusion codes appear only on `out_of_scope`. No review code and no
free-text reason appears. The 35 earlier labels were not changed. The sheet
has no model prediction. It is not the Phase 6 gold set.

| Scope class | Rows |
|---|---|
| `core_incomplete_recall` | 12 |
| `adjacent_known_item_retrieval` | 14 |
| `out_of_scope` | 24 |
| Total | 50 |

An offline prefilter on 2026-09-29 read 50 documents, routed all 50 to
classification, and made 0 provider calls. It kept every human decision on
the same `doc_id`, including the original 35. Source columns were unchanged.

Review items open when confidence is below `relevance.confidence_review_below`
(0.7), when a prefilter candidate scope disagrees with the classifier, when
evidence is missing, fabricated, or ambiguous, or when the provider response
is still invalid after syntax-only JSON repair. The queue is the existing
append-only review queue, in the Phase 4 output directory. Earlier human
resolutions are kept.

The relevance cache key is provider, model, decoding parameters
(`temperature`, `max_tokens`), prompt id and version (`relevance/v1`), schema
version, ruleset version, and document content hash. `taxonomy_version` is
not included. A cache hit makes no provider call.

### Specification notes for this slice

- Spec Section 19.5 and ARCHITECTURE Section 8 omit `ruleset_version` from
  the cache key. `decision_fingerprint` already includes it. Relevance passes
  it. Callers that omit it, including a future extraction stage, keep the
  previous key.
- ARCHITECTURE lists an OpenAI adapter. ADR-14 and the Phase 4 plan mark it
  as stretch. It was not built. `tenacity` was not added.
- Spec Section 19.4 steps 3 and 4 ask for another model call. This slice
  repairs only JSON syntax. An invalid enum or a preamble is a technical
  failure plus a review item.
- Spec Section 21.1 wants a prefilter drop reason on the stage event. Spec
  Section 16.8, as implemented, rejects exclusion codes on stage events. An
  exclusion code is accepted only when the stage is `prefilter` and the
  status is `dropped`.
- `timeout`, `provider_error`, and `skipped_dry_run` have no reason code in
  Section 16.8. The decision keeps that technical state. The reason code is
  `provider_unavailable`.
- Spec Section 5.2 keeps duplicates flowing. This stage classifies canonical
  documents. A confirmed duplicate is skipped and the event names the
  canonical `doc_id`. A pending or rejected link is still classified.
- The prompt requires verbatim evidence for `out_of_scope` as well as for
  core and adjacent, because `RelevanceDecision` requires evidence whenever
  `technical_state` is `ok`.
- The run manifest is under `data/interim/phase4/`, not `data/exports/runs`.
  The pilot output stays local.
- `RelevancePayload.reason_code` accepts any `ReasonCode`, including a review
  code paired with a scope class. `RelevanceDecision._check_reason_code_group`
  rejects that pairing. This is recorded and not changed in the seed-review
  integration.

---

## Research track — pilot collection complete

The private workbook holds 35 genuine public records with direct permalinks and
verbatim text, across Google Photos Help, Google Play Store, Apple App Store,
YouTube, and Reddit, plus 7 search-log sessions. It stays local and uncommitted.

- [x] Collect 30–50 genuine public documents with direct permalinks and verbatim
      text. Manual import is the guaranteed baseline; the 300-document target
      must be reachable through manual import plus YouTube alone (Section 11.4).
- [ ] Do **not** start taxonomy naming. Spec Section 20 requires clusters to
      follow pilot evidence, and pre-reading the corpus with cluster names in
      mind is precisely the bias the rule prevents.

---

## Next command

```powershell
python main.py run --stages prefilter --offline
python main.py run --stages relevance --dry-run --offline
python main.py run --stages relevance --offline
```

```bash
pytest tests/test_relevance.py tests/test_llm_gateway.py tests/test_pipeline_runner.py tests/test_architecture.py -q
pytest -q
```

The 50-record seed review was checked on 2026-09-29. Offline prefilter
routed all 50 documents to classification, preserved every human label by
`doc_id`, and made 0 provider calls. Phase 4 is not complete. No live model
was called. Phase 5 has not started. The sheet has 12 core, 14 adjacent, and
24 out of scope.

```bash
pytest tests/test_relevance.py tests/test_pipeline_runner.py -q
pytest -q
```

Both were green on 2026-09-29: 26 passed in the two Phase 4 files; the full
suite passed 682, with 4 skipped. The 3/6 duplicate thresholds stay
provisional until the scaled corpus is calibrated.

## Known issues

`RelevancePayload` can accept a review reason code together with a scope
class. `RelevanceDecision` rejects that pairing when the decision is built.
The payload schema was not tightened during seed-review integration.

Phase 1 interpretations and the four places where the specification's
field lists did not match its own model definitions are recorded in
`CHANGELOG.md` under "Interpretations" and "Conflicts found in the
specification"; the machine-readable version of the fourth lives in
`EXEMPT_ADDITIONS_RATIONALE` in `src/models/evidence_map.py`.
