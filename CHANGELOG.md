# Changelog

Material implementation changes by date (spec Section 1). Scope and schema
decisions live in `DECISIONS.md`; this file records what was built.

---

## 2026-09-27 — Phase 2 closed: 35-record pilot corpus

Documentation only. The importer, tests, private workbook, and processed
output were left as they were. Phase 3 was not started.

The manual pilot corpus is 35 genuine public records: Google Photos Help,
Google Play Store, Apple App Store, YouTube, and Reddit. The workbook has 7
valid search-log sessions.

Final import: 35 rows read, 35 accepted, 0 rejected, 3 `repeated_source_url`
warnings, 7 search-log rows read, 7 valid, 0 issues. The repeated URLs are
shared listing or thread permalinks. Distinct `source_item_id` values keep
each record's identity.

`test_pilot_workbook_accepts_all_documents_and_reports_shared_urls` derives
the expected record count and the repeated-URL groups from the workbook.
`pytest tests/test_workbook_import.py -q` → 23 passed. `pytest -q` → 548 passed.

The private workbook, raw author names, `AUTHOR_SALT` (`.env`), and processed
import output stay gitignored and are not committed.

---

## 2026-09-26 — Phase 2: workbook import command

Closes the pilot importer. `main.py collect` loads `AUTHOR_SALT` from the
environment or `.env` and calls `import_workbook`. The import stays in
`src/collect`. No extraction, relevance, evidence spans, clustering, or
retrieval work was added.

### Added

- **`src/collect/cli.py`** — exit code and a count-only terminal summary.
  Exit 0 when the workbook has no structural errors, no rejected document
  rows, and no search-log issues. Exit 1 for an invalid workbook, a missing
  salt, a missing file, or rejected rows. The salt is not a command argument.
- **Search-log count rule.** `documents_kept` must not exceed
  `results_scanned`. Both must already be non-negative. A failing audit row
  is reported and is not turned into a `CollectedDocument`.
- **Salt scrubbing.** The salt is removed from the report and the log along
  with author display names. It is not written into the documents file.
  There is no hardcoded production default. Tests pass the salt directly.
- **Tests** for hashing, a second salt, blank authors, a missing salt, search-log
  counts, CLI success, CLI failure, and the absence of names and the salt from
  stdout, stderr, logs, and reports. Full suite: 548 passing.

### Pilot command

`AUTHOR_SALT` is already in the environment or in `.env` (the value is not
part of the command):

```powershell
python main.py collect --path "data\manual\Private\Google_Photos_Pilot_Collection_Workbook.xlsx" --output "data\processed\pilot-import"
```

Run on 2026-09-26: exit 0, 7 read, 7 accepted, 0 rejected, 3 warnings
(platform alias on the document sheet, platform alias on the search log, and
the shared URL on rows 7 and 8). Search log: 1 row, 25 scanned, 7 kept, no
issues. Four author names hashed with the supplied salt; three blank authors
stayed null. A second salt produced different hashes for those four. Output
under `data/processed/pilot-import` is gitignored.

### Not built, deliberately

No CSV/JSONL importer, SQLite store, stage events, normalization, dedupe,
relevance, extraction, clustering, or review queue. The 30–50 document corpus
is still the research task. Phase 3 was not started.

---

## 2026-09-26 — Phase 2: manual pilot-workbook import

Imports `data/manual/private/Google_Photos_Pilot_Collection_Workbook.xlsx`
into the Phase 1 `CollectedDocument` contract. The models, the evidence
ladder, and the Phase 1 tests were left as they were. `tests/test_architecture.py`
now allows `src/collect` and still rejects every later package; that guard
was the Phase 1 "nothing else exists yet" check, and Phase 2 is the phase
that creates this package.

### Added

- **`src/collect/workbook.py`** — reads the `documents` sheet by header name,
  writes `collected_documents.jsonl` plus `import_report.json` and
  `import_report.txt`. Counts, warnings, duplicate ids, repeated URLs, and
  per-row rejection reasons are in both reports. `author_name_raw` is hashed
  with the existing HMAC helper and then dropped. The name is scrubbed from
  the report and from log lines.
- **`search_log` stays an audit.** Headers and values are checked. Those rows
  are not documents.
- **`openpyxl`** (`>=3.1,<4`) to read xlsx without taking on pandas.
- **22 tests** in `tests/test_workbook_import.py`, including the private pilot
  file when it is present. Full suite: 536 passing.

### Pilot result

7 document rows read, 7 accepted, 0 rejected. The waterfall thread and the
original-poster reply share one URL (sheet rows 7 and 8); that is a warning.
Their `source_item_id` values differ, and the reply's `parent_thread_id` is
the thread id. All seven `raw_text` values match the worksheet XML, including
curly apostrophes, non-breaking spaces, and blank lines. Author display names
from the sheet are absent from the documents file outside `raw_text`, from
both reports, and from the log.

### Interpretations

1. **`google_photos_help` is stored as `google_support`.** The instructions
   sheet uses the first token. Spec Section 15.1 and `config/sources.yaml`
   use the second for Google Photos Help. The mapping is one explicit alias
   and a warning on every row that uses it. Any other unknown platform is
   rejected.
2. **`language` is `language_reported`, and `researcher_notes` go in
   `metadata`.** Neither name is a `CollectedDocument` field. Notes are not
   turned into clusters.
3. **Naive Excel datetimes are attached to UTC.** The contract requires an
   aware datetime, and the workbook has no timezone column. An ISO value that
   already has an offset keeps that offset. A bad date rejects the row and
   quotes the original cell plus the spreadsheet row; it is not stored as null.
4. **Styled blank template rows are not documents.** The sheet is formatted
   out to row 51. Only rows with a value are read, which is why the pilot
   count is 7.
5. **A repeated URL warns. A repeated `source_item_id` rejects every copy.**
   The thread and the reply are the first case. Two rows that claim the same
   item id are the second, and neither is kept, because choosing one would be
   a guess.
6. **Workbook instructions mark `source_item_id`, `language`, and
   `collection_query` required.** The contract allows those three to be null.
   The importer follows the workbook's own required list. Authors, titles,
   publication dates, parent ids, ratings, and notes stay null when the cell
   is blank.

### Not built, deliberately

No CSV/JSONL importer, SQLite store, stage events, normalization, dedupe,
relevance, extraction, clustering, or review queue. The workbook command is
recorded in the entry above. The 30–50 document corpus is still the research
task. Phase 3 was not started.

---

## 2026-09-26 — Phase 1 hardening audit

Audit of the models, evidence map, and validator against the revised
`problem-statement.md`, `ARCHITECTURE.md`, and `IMPLEMENTATION-PLAN.md`. No
Phase 2 work. Three of the six requirements were already met; three were not,
and two of those failures were silent.

### Defects found and fixed

1. **`dedupe_spans` silently deleted a rejected span.** `evidence_id` is derived
   from the owner, field, quote, and offsets, so the same claim validated twice
   with different outcomes collides with itself. The helper kept whichever
   arrived first, so a fabricated span vanished whenever a valid twin happened
   to be stored ahead of it — and `all_evidence_spans` then reported the record
   as fully evidenced. This was the forbidden field-dropping arriving through a
   three-line helper nobody would think to audit. De-duplication now keeps the
   *least* trusted duplicate, so collapsing two spans can never improve either
   one's standing.
2. **Neither contract could record that it had failed.** `RecordValidation`
   returned the verdict, but nothing was written to the record, so "mark the
   parent invalid/pending" had no field to write to and the only other way to
   handle bad evidence was to drop the field. `RelevanceDecision` and
   `RetrievalCase` now carry `validation_state`, defaulting to `pending` —
   unchecked until the validator checks it, exactly like `EvidenceSpan`.
3. **A paraphrase could be exported as a quotation.**
   `ExportedEvidenceSpan.field_name` was only `min_length=1`, so a span naming
   `reason_summary` was admissible. That contract is what the evidence browser
   highlights, so the export could have put a model's own prose in quotation
   marks beside a real quote — the fabrication the whole evidence architecture
   exists to prevent, arriving at the last step. `field_name` must now be an
   evidence-required field.
4. **`STATUS.md` documented the behaviour the specification forbids** — "the
   field it supports is dropped rather than kept with weaker provenance".
   The code never did this, but the sentence was an invitation to implement it.

### Added

- **`RecordValidation.invalid_fields` and `.retained_spans`** — the affected
  fields and the surviving invalid candidates, as structured data rather than
  prose. A reviewer needs to know which claim is unsupported and what the model
  actually offered in support of it; an error string is for a log.
- **`RecordValidation.apply(record)`** — returns the record marked `valid`, or
  `pending` with `needs_human_review` set. Failure is `pending` rather than
  `rejected` because the record is unconfirmed rather than wrong, and review is
  a route back in (spec Section 19.4 step 5).
- **`SpanValidation.candidate` / `.original`** — the span exactly as it arrived.
  The ladder legitimately moves offsets and replaces a whitespace-normalised
  quote with the document's characters, so the outcome span is not always what
  the model claimed; a repair that leaves no trace of what it repaired is the
  silent rewriting spec Section 29.12 forbids.
- **`select_valid_for_analysis`** — Phase 1's stand-in for Phase 3's `v_*`
  views. It filters on `validation_state`, not on `needs_human_review`: the two
  differ on the reviewed-but-not-revalidated record and on the `pending` record
  nobody has looked at, both of which a review flag alone waves through.
- **Model-level gates on both contracts** — a record cannot be marked `valid`
  while holding a non-valid span, so a store that bypasses the validator still
  cannot write one. This is what closes the field-dropping exit for good: the
  record cannot be valid with the fabricated span attached, and detaching it
  leaves the field unevidenced, which the status gate then rejects. Both exits
  are shut, so the only way forward is review.
- **`_check_scope_inheritance`** — `RetrievalCase.scope_class` is
  evidence-exempt because it is inherited from a decision that already evidenced
  it, and that exemption is only honest while the inheritance is real. Without
  the check a case could assert any scope class, cite no span, and pass the
  gate: the exemption was a hole the size of the project's central claim.
  Enforced when the decision is supplied, since the case contract carries no
  `decision_id` and the validator cannot fetch it. Passing silently when the
  decision is absent is the honest behaviour; claiming to have checked would be
  worse than not checking.
- **`SCOPE_INHERITANCE_CONDITIONS` and `EVIDENCE_CONTAINER_FIELDS`** — the three
  inheritance conditions and the two unconditional container exemptions, kept as
  data beside the exemptions they qualify so the two cannot drift.
- **33 tests.** 509 passing, coverage of `src/models/` and
  `src/extract/validator.py` still 100%.

### Deliberately unchanged

`evidence` and `severity_evidence` remain exempt with no qualifying condition.
Requiring evidence for an evidence container is recursive — the span supporting
`severity_evidence` would itself need a span — and no record could satisfy it.
`reason_summary` remains an evidence-exempt paraphrase; the hardening is that it
can never substitute for evidence or be rendered as a quotation, both of which
are now tested rather than asserted.

One asymmetry is worth naming because it looks like an inconsistency:
`problem_summary` is a paraphrase *and* evidence-required, so its span quotes the
source text supporting the summary, and it stays exportable. `reason_summary` is
exempt, so a span naming it could only be quoting the model, and it does not.

---

## 2026-09-21 — Phase 1: schemas and evidence validation

### Added

- **`src/models/enums.py`** — every controlled vocabulary in spec Section 16, as
  `StrEnum` so a stored value is its own wire format. No member is an absence
  placeholder; absence is `DimensionObservationStatus`, which is itself an enum
  of *reasons* a value is missing rather than a single null.
- **`src/models/evidence_map.py`** — Section 15.10 as data: the contract-scoped
  evidence-required map, the closed exempt list by category, `STATUS_GATE` as a
  table of `StatusRule`, and `classify()`. A field added to either contract
  without a classification fails `tests/test_evidence_map.py`, which is the
  point: a scattered `if` is simply absent for a new field and nobody notices.
- **`src/models/base.py`** — `ResearchModel` (`extra="forbid"`, `frozen=True`)
  and `VersionedModel`, which adds `schema_version`. Sequence fields are
  `tuple`, not `list`, so a frozen model is frozen all the way down.
- **`src/models/evidence.py`** — `EvidenceSpan` and `ObservedValue`, aliased
  `EvidenceBackedLabel` because Section 15.5's heading uses that name.
- **The eleven contracts** — `collected_document`, `document_derived`,
  `duplicate_link`, `relevance`, `retrieval_case`, `stage_event`,
  `cluster_assignment`, `gold`, `export`.
- **`src/extract/validator.py`** — `validate_span` (the four-rung ladder),
  `validate_record` (the evidence map and status gate applied to a whole
  record), the `all_evidence_spans` union, and `gate_for_analysis`, which
  returns a record's evidence or refuses to return anything.
- **The whole of ARCHITECTURE Section 9.3 rung 4, not just the rejection.** A
  rejected span invalidates its parent record, the failure is logged as a
  structured warning, `RecordValidation.requires_review` and
  `.review_reason_code` carry the routing decision, and `gate_for_analysis`
  withholds analysis output until the record is corrected. The first version
  stopped at rejecting the span: `validate_record` asked only whether each
  required field had *at least one* valid span, so a field carrying one good
  quote and one fabricated one passed the gate. That record would have been
  stored as valid, the fabrication would have been indistinguishable from
  verified evidence, and it would never have appeared in the fabrication rate —
  which is the single finding the project exists to measure (spec Section 18,
  risk R8).
- **`tests/synthetic.py`** — fixture builders, every one of which stamps
  `evidence_tier = synthetic_test`.
- **309 tests** across `test_models.py`, `test_evidence.py`,
  `test_evidence_map.py`, and four additions to `test_architecture.py`.
  Coverage of `src/models/` and `src/extract/validator.py` is 100%.

### Enforced structurally rather than documented

- **`RetrievalCase` has no `candidate_cluster`, `cluster_confidence`, or
  `taxonomy_version` field.** A test asserts their absence from `model_fields`,
  and `extra="forbid"` turns an attempt to pass one into an error rather than a
  silently ignored keyword. Cluster membership lives in `ClusterAssignment`,
  which is the only contract carrying `taxonomy_version`.
- **`is_relevant` is a `@computed_field`, not a stored column** (I13). A
  supplied value is discarded by a `mode="before"` validator and a stored
  conflict is rejected, so the two can never disagree in the database.
- **`src/models/__init__.py` re-exports lazily through `__getattr__`.** With
  eager imports, `import src.models.collected_document` pulled in every
  later-stage contract, and I11's test — which asserts a clean `sys.modules` in
  a subprocess — failed. Phase independence had to be real, not just true of the
  field list.
- **A span whose `field_name` is in neither map fails validation**, so a model
  cannot invent a field name that no validator will ever consult.
- **An ambiguous duplicate quote is never guessed.** Two equidistant matches
  produce `ambiguous_tied` / `pending` and route to human review, because
  picking one would silently attribute the claim to a sentence the user may not
  have written. It is filed under `evidence_offsets_unresolved`, not
  `evidence_validation_failed` — the quote is real and only its position is
  unknowable, so the review it needs is a different job from adjudicating a
  fabrication, and collapsing the two would make the fabrication rate wrong in
  both directions.
- **`gate_for_analysis` returns the evidence union rather than a boolean.** An
  `is_eligible()` predicate is a call an aggregation can forget while still
  getting its data. Making the gate the only route to a record's spans means
  analysis code cannot obtain its quotes without passing through it.
- **A fabrication outranks every other finding when a record is filed for
  review.** A record often fails several ways at once and a queue item needs
  one code; `_REVIEW_PRIORITY` orders them by how much they undermine the
  record, so an invented quote is never filed as a status conflict merely
  because that check ran first.

### Interpretations

Places the specification left a choice open. None is a deviation, but a reader
could reasonably have decided differently:

1. **Whitespace repair keeps the document's characters in `quote`, not the
   normalized ones.** The rung exists so a line-wrapped quote is not thrown
   away, but the excerpt is later shown in quotation marks, and a quotation that
   differs from the source — even only in whitespace — is not verbatim. Offsets
   move; the displayed text is re-read from the document.
2. **A span overlapping a redaction is rejected even when the quote matches
   exactly.** Redaction destroys the underlying text, so an exact match against
   the redacted string proves the span agrees with the redaction, not with what
   the user wrote. It cannot be re-verified, so it is not evidence.
3. **`Stage.import_` carries a trailing underscore.** `import` is a keyword; the
   stored value is still `"import"`.
4. **Several offsets are repaired silently when the quote occurs exactly once.**
   `repair_applied` records that it happened, so Phase 5 can report clean versus
   salvaged extraction separately rather than the two being indistinguishable.

### Conflicts found in the specification

- **Section 15.10's exempt list is called closed, but it does not cover every
  field of the two contracts it governs**, while the same section requires every
  field to appear in exactly one of the two lists. Four fields fall outside its
  five categories: `evidence` and `severity_evidence` (span containers —
  requiring evidence for an evidence field is circular), `RetrievalCase.
  scope_class` (the inherited, already-validated decision, whose span lives on
  `RelevanceDecision`), and `reason_summary` (a paraphrase of why, never
  displayed as a quotation). Each is exempt under a separately named category so
  the addition is visible, with a per-field rationale in
  `EXEMPT_ADDITIONS_RATIONALE` that a reviewer can disagree with line by line.
- **Section 15.5's heading calls the contract an evidence-backed label while the
  field tables call it an observed value.** Implemented once as `ObservedValue`
  with `EvidenceBackedLabel` as an alias, rather than leaving a reader to guess
  whether two contracts exist.

### Not built, deliberately

No collectors, normalizer, deduplication, LLM gateway, store layer, analysis,
retrieval, or Streamlit app. **No review queue**: Phase 1 produces the routing
decision on `RecordValidation`, and ADR-24 builds the queue in Phase 3, when the
first review items actually exist. `src/extract/` holds the validator only — the
extraction prompt and its runner are Phase 5 — and
`tests/test_architecture.py` asserts both the absence of the later packages and
that `src/models/` imports nothing outside `src/core/` and itself.

---

## 2026-09-21 — Phase 0: project scaffold

### Added

- **`pyproject.toml`** — Python 3.12, bounded dependencies (`pydantic`,
  `pydantic-settings`, `pyyaml`, `python-dotenv`; `pytest` and `pytest-cov` under
  `dev`). Replaces the prototype's unpinned `requirements.txt`
  (`ARCHITECTURE.md` 20.2 item 15). Later phases add their own dependencies.
- **`src/core/errors.py`** — `EngineError` with `ConfigError`, `ValidationError`,
  `EvidenceError` (a subclass of `ValidationError`), and `ProviderError`.
- **`src/core/versions.py`** — `SCHEMA_VERSION`, `RULESET_VERSION`,
  `NORMALIZER_VERSION`, `TAXONOMY_VERSION = "0-unassigned"`, and an empty
  `PROMPT_VERSIONS` registry. `prompt_version()` raises on an unregistered id
  rather than defaulting, because a default would produce a cache key that does
  not move when a prompt changes.
- **`src/core/config.py`** — one typed settings object over `config/*.yaml` plus
  `.env`, and the only module permitted to read the environment.
- **`src/core/logging.py`** — JSON-per-line logs with `run_id` and `stage` bound
  through `contextvars`.
- **`src/core/ids.py`** — `sha1_short`, `raw_text_sha256`, `content_hash`,
  `author_hash`, `author_salt_id`, `source_url_key`, `doc_id`, `case_id`
  helpers, `case_sort_key`, `evidence_id`, `link_id`, `event_id`,
  `canonical_doc_id`, the three fingerprints, and `cache_key`.
- **`src/core/hashing.py`** — canonical content hashing with `VOLATILE_FIELDS`
  as data, `artifact_hash` for order-independent collection hashing, and
  `exclusion_list()` for the run manifest (ADR-26).
- **`config/`** — `sources.yaml` (feasibility tiers per Section 11.4, nothing
  enabled), `models.yaml` (Anthropic, temperature 0), `analysis.yaml` (dedupe,
  export, retrieval thresholds), `taxonomy.yaml` (empty at `0-unassigned`).
- **`main.py`** — CLI surface with twelve declared stages, each refusing with the
  phase that will build it, plus a working `check-config`.
- **`data/`** tree, `.gitignore`, `.env.example`, `STATUS.md`, this file.
- **171 tests** across `test_config.py`, `test_ids.py`, `test_hashing.py`, and
  `test_architecture.py`.

### Changed

- `reference files/` → `prototype/`, contents unchanged (ADR-9), with
  `prototype/README-DO-NOT-EDIT.md` added to record that its 16 records are not
  validated research evidence.
- `IMPLEMENTATION-PLAN.md` Section 1 — the obligations list still asked Phase 7
  to document a Play Store or App Store mechanism and to confirm support-forum
  access. ADR-22's verification closed all three, so the list now carries the
  obligations that actually remain and states that the closed ones must not be
  reopened as backlog items.

### Enforced structurally rather than documented

Choices where the constraint is in a signature or a test, so a later edit has to
argue with it:

- **`doc_id` has no `content_hash` parameter** (ADR-20), so an import-time
  identifier cannot come to depend on a Phase 3 value.
  `test_doc_id_signature_rejects_content_hash` asserts the parameter's absence.
- **`extraction_fingerprint` has no `taxonomy_version` parameter** and
  `cache_key` takes it only opt-in (ADR-19), so extraction cannot pick it up
  implicitly.
- **`config/analysis.yaml` cannot set `allow_cross_author_auto: true`** — the
  loader refuses to start. Collapsing two genuine users is invisible and
  irreversible, and it destroys the strongest prevalence signal in the corpus
  (Section 19.6).
- **`taxonomy.yaml` cannot define clusters while its version is
  `0-unassigned`** — the loader refuses, enforcing invariant I10.
- **Unknown YAML keys are rejected**, so a typo is an error rather than a
  setting that silently does nothing.
- **`author_hash` refuses an empty salt**, because an unsalted hash over public
  usernames is trivially reversible while still looking hashed.

### Interpretations

Two places where the specification did not settle a detail. Neither is a
deviation, but both are choices a reader could reasonably have made differently:

1. **"Stripped punctuation" (Section 26.1) reads as "replaced by a word
   boundary", not "deleted".** Deletion would merge `photo,video` into
   `photovideo`, a token matching neither word. The cost is that `can't`
   canonicalizes to `can t`, so `can't` and `cant` produce different content
   hashes. That is correct for this function's purpose: `content_hash` detects
   *exact* duplicates — the same item re-ingested, or identical canonical text
   from one author — while textual near-matches are simhash's job, under the
   review band and its safety conditions. Documented in
   `canonicalize_for_hash` and asserted by two tests.
2. **`.gitignore` is tighter than Section 14.** Section 14 marks only `raw/` and
   `interim/` local-only, but `data/manual/` holds unredacted analyst-collected
   CSVs and `data/processed/` holds records carrying the full `raw_text_audit`,
   which ADR-23 declines to publish. Both are ignored. `data/gold/` and
   `data/exports/` remain committed.

### Not built, deliberately

No Pydantic research contracts, controlled vocabularies, evidence validator,
collectors, LLM gateway, database schema, analysis, retrieval, or Streamlit app.
Spec Section 29.4 requires one phase at a time, and
`tests/test_architecture.py::test_no_later_phase_packages_exist_yet` fails if any
of those packages appears.
