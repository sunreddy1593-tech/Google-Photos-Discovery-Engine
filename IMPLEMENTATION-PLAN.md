# Implementation Plan — Google Photos Remembered-Item Retrieval Discovery Engine

> Derived from `problem-statement.md` (authoritative spec) and `ARCHITECTURE.md` (system design).
> Document role: executable build plan, phase by phase. Version 1.1.
>
> Rules of engagement, from spec Section 29: one phase at a time, tests updated with every
> behaviour change, no phase declared done without showing the command and its output.
> Where this plan and `problem-statement.md` disagree, the spec wins.

---

## How to use this document

Each phase below has the same six parts, so it can be worked as a checklist:

1. **Goal** — the one sentence that describes what exists at the end.
2. **Owner** — `build` (Cursor writes code) or `research` (a human collects or labels).
3. **Work items** — checkboxes, ordered so each is testable when finished.
4. **Tests** — what must exist and pass, mapped to spec Section 25.
5. **Commands** — exactly what gets run and pasted into the phase report.
6. **Exit criteria** — the spec's acceptance criteria, plus the architecture invariants
   the phase is responsible for. A phase is not done until every box is checked.

Every phase carries a **prompt to paste**, following the pattern the spec establishes in
Section 30, so each phase starts from an unambiguous instruction. Phases 0 through 11 each
have one; that claim is checkable against this document rather than aspirational.

Spec Section 30's prompt implements **Phase 0 only**. Phase 1 has its own prompt below,
because it carries the contract split, the evidence-required field map, and the
observation-status rules, and it is the phase every later number depends on.

---

## 0. Before anything: the schedule problem

The build has twelve phases, but the **critical path is human research, not code**. Three
manual tasks gate everything downstream and cannot be accelerated by writing code faster:

| Research task | Volume | Gates | Realistic effort |
|---|---|---|---|
| Pilot corpus collection | 30–50 public documents, manual import | Phase 2 exit, and therefore Phases 3–5 | 6–10 hours |
| Gold-set labelling | 75–100 documents at the document level, plus case-level labels; 20% double-coded; dev/holdout split | Phase 6 quality gates | 14–24 hours |
| Duplicate-review pass | pilot pairs in the review band, short texts, cross-author matches | Phase 3 exit | 1–2 hours |
| Taxonomy review | first 50–100 qualifying cases | Phase 8, and therefore the whole app | 4–8 hours |

Gold labelling is now two passes rather than one, because document-level relevance and
case-level extraction are separate records (spec §15.11). The second pass is smaller — only
relevant documents get case labels — but it is the pass that makes extraction measurable at
all, so it is not optional.

Treat these as a parallel track. The spec requires *code* phases to be built one at a time;
it does not require the analyst to sit idle. Concretely:

- **Start pilot collection during Phase 0.** It needs a browser and a spreadsheet, not the
  repository. The CSV template from Phase 2 is the only dependency, and it is 15 minutes of
  work that can be pulled forward.
- **Start gold labelling during Phase 5**, on documents already imported, using the same
  template plus scope-class and expected-field columns.
- **Do not start taxonomy naming early.** This is the one exception: spec Section 20 requires
  clusters to follow pilot evidence, and pre-reading the corpus with cluster names in mind is
  precisely the bias the rule exists to prevent.

```text
Week 1        Week 2            Week 3              Week 4          Week 5
BUILD:  P0 P1 │ P2 P3      │ P4 P5          │ P6 P7        │ P8 P9 P10 P11
RESEARCH: ────┴─ pilot 30-50 ┴─ gold 75-100 ─┴─ scale 300 ──┴─ taxonomy review
          dedupe review ─┘   (2 passes, split)
GATES:              M1 (Sec 28) ──┘        QG (Sec 24 P6) ─┘     DoD (Sec 27) ─┘
```

Two hard gates interrupt the build. Neither is negotiable:

- **M1 — First milestone (spec Section 28), at the end of Phase 5.** 30 genuine documents →
  a full end-to-end run → every claim backed by a validated verbatim span → per-stage funnel
  reported → all schema and evidence tests passing. The qualifying-case count is **reported
  and diagnosed, not targeted**.
- **QG — Quality gate (spec Section 24, Phase 6).** Prefilter recall ≥ 0.90, end-to-end
  relevance precision ≥ 0.85, end-to-end relevance recall ≥ 0.80, 100% schema validation,
  100% span validation, on the frozen holdout split. If a gate misses, iterate on the
  development split and bump the version; do not relax the threshold.

### 0.1 Effort estimates

Rough sizing to sequence work, not a commitment. "Session" means one focused Cursor working
session of roughly 1–3 hours.

| Phase | Build sessions | Human hours | Notes |
|---|---|---|---|
| 0 Scaffold | 1 | 0 | mechanical |
| 1 Schemas + evidence | 3–4 | 0 | highest-value phase; eleven contracts and the evidence map; do not rush |
| 2 Manual import | 2 | 6–10 | human collection dominates |
| 3 Normalize + dedupe | 2–3 | 1–2 | now also builds the review queue; calibration is human judgement |
| 4 Relevance | 3 | 2 | first LLM phase; prompt iteration |
| 5 Extraction | 3–4 | 2 | largest schema surface |
| 6 Gold evaluation | 2–3 | 14–24 | human labelling dominates; two labelling passes |
| 7 Collectors + scale | 2–3 | 4 | fewer collectors than before: YouTube and Reddit only |
| 8 Taxonomy + analysis | 3–4 | 4–8 | cluster review is human |
| 9 Retrieval | 1–2 | 0 | synthesis is stretch |
| 10 Streamlit app | 3–4 | 2 | surfaces plus the public export profile |
| 11 Deploy + QA | 1–2 | 3 | link checks, screenshots, deck slide |

Phase 7 shrank and Phases 1, 3, and 6 grew. That is the intended trade: two collectors that
have documented mechanisms replace five that partly did not, and the time moves to the phases
that make the numbers defensible.

---

## 1. Decisions — settled, no blockers remain

ADR-1 through ADR-14 were recorded on 2026-09-18. The specification-consistency revision on
2026-09-21 superseded six of them and added ADR-15 through ADR-29. `DECISIONS.md` is the
register; `ARCHITECTURE.md` Section 22 is the summary table. **Phase 0 is unblocked.**

Settled values each phase must honour:

| ADR | Decision | Consumed by |
|---|---|---|
| ADR-12 | Recency window 12 months, rolling, configurable; display the resolved date boundary | Phase 8, Phase 10 |
| ADR-14 | Anthropic default; OpenAI adapter is **stretch**; no dual-provider consensus in Part 1 | Phase 4 (`config/models.yaml`) |
| ADR-15 | `CollectedDocument` / `DocumentDerived` / `DuplicateLink` split; no contract requires a later stage's field | Phases 1, 2, 3 |
| ADR-16 | Evidence-required field map plus closed exception list; `all_evidence_spans` derived | Phases 1, 5 |
| ADR-17 | `is_relevant` derived; evidence for every scope class; `DecisionTechnicalState` separate | Phases 1, 4 |
| ADR-18 | Append-only `StageEvent`; no lifecycle column | Phases 1, 2, and every stage after |
| ADR-19 | `taxonomy_version` only in `assignment_fingerprint` and taxonomy cache keys | Phases 4, 5, 8 |
| ADR-20 | `doc_id` from collection-time values; canonical duplicate is lowest `doc_id`; `case_id` tie-breaks | Phases 0 (`ids.py`), 2, 3, 5 |
| ADR-21 | Dedupe safety: `dedupe_min_tokens` default 25, cross-author guard, review states | Phase 3 (`config/analysis.yaml`) |
| ADR-22 | Source feasibility tiers; no "verified" claim without linked primary documentation. Verified 2026-09-21: YouTube and Reddit permitted; both app stores **closed**; forum stays manual on terms grounds | Phase 7 |
| ADR-23 | Public export is a minimum redacted excerpt with rebased offsets | Phase 0 (`.gitignore`), 3 (redaction), 10 (export) |
| ADR-24 | Review queue built in Phase 3 | Phase 3 |
| ADR-25 | Gold set: separate document and case labels, dev/holdout splits, named metric families | Phase 6 |
| ADR-26 | Rebuild equality is canonical content hashes; volatile fields excluded | Phases 0, 3, 11 |
| ADR-27 | MVP versus stretch scope separated | all phases |
| ADR-28 | First prompt is Phase 0 only; every phase has its own prompt | all phases |
| ADR-29 | M1 reports and diagnoses the case count; it does not target a band | Phase 5 |

Four obligations remain, attached to phases rather than blocking them:

- [ ] **Phase 3** — calibrate the ADR-21 similarity band and `dedupe_min_tokens` against the
      pilot corpus and amend the ADR. Watch short store reviews in particular: they collide at
      low Hamming distance without being duplicates, which is exactly why the minimum token
      length exists.
- [ ] **Phase 7** — exercise the YouTube and Reddit mechanisms and promote each from
      `permitted, documented, unexercised` to `exercised` in `DECISIONS.md`.
- [ ] **Phase 7** — confirm this research counts as non-commercial under the Reddit Data API
      Terms, and re-read the Reddit Data API Wiki from a browser to confirm the 100 QPM limit
      first-hand (ADR-22 consequence 7 records why that one figure is weaker than the others).
- [ ] **Phase 10** — record per-source redistribution terms, to decide where
      `excerpt_is_full_text` may be true.

The two store-mechanism obligations and the support-forum access obligation that previously sat
here were **closed** by the 2026-09-21 verification pass, not deferred. Both store APIs
authenticate the app's publisher, so there is no mechanism to find; the forum's URL form is
confirmed live and the blocker is Google's terms. See ADR-22 consequences 2 and 4. Do not
reopen them as backlog items.

### 1.1 MVP versus stretch

Spec §24.0 splits the build. This plan marks each phase accordingly, and the rule is
absolute: a stretch item is never started while an MVP item is unfinished, and never becomes
a dependency of one.

| Scope | Items |
|---|---|
| **MVP** | manual import · schemas and the evidence map · evidence validator · normalization · dedupe · relevance · extraction · gold evaluation · taxonomy · deterministic analysis · evidence browser · quality report · public export · Streamlit deployment |
| **Stretch** | second provider adapter · Ask synthesis · automated support-forum collector · automated store-review collectors · composite opportunity score · static `explorer.html` generation · embeddings |

If the schedule compresses, stretch items are cut. MVP scope is not reduced.

---

## Phase 0 — Project scaffold

**Goal:** a Python 3.12 repository with configuration, logging, tracking documents, and a
passing empty test suite. No collectors, no LLM, no Streamlit.

**Owner:** build.

### Work items

- [ ] `git init`; create `.gitignore` covering `.env`, `.streamlit/secrets.toml`,
      `data/raw/`, `data/interim/`, `__pycache__/`, `.pytest_cache/`, `*.db`.
- [ ] Move `reference files/` → `prototype/` (ADR-9). Read-only from here on; add a
      `prototype/README-DO-NOT-EDIT.md` noting its records are not validated evidence.
- [ ] `pyproject.toml` with bounded dependencies. Phase 0 installs the core set only;
      later phases add their own. Verify current versions at install time — these bounds are
      floors, not pins to reproduce blindly:

      pydantic>=2.7,<3 · pydantic-settings>=2.2,<3 · pyyaml>=6,<7 ·
      python-dotenv>=1,<2 · pytest>=8,<9 · pytest-cov>=5,<6

- [ ] `src/core/config.py` — one typed settings object over `config/*.yaml` plus `.env`.
      Nothing outside this module reads `os.environ` (`ARCHITECTURE.md` §16.1).
- [ ] `src/core/logging.py` — structured logs with `run_id` and `stage` bound to context.
- [ ] `src/core/ids.py` — `sha1_short`, `raw_text_sha256`, `content_hash`, `author_hash`
      (HMAC with `AUTHOR_SALT`), `source_url_key`, `doc_id`, `case_id`, `evidence_id`,
      `link_id`, `event_id`, the three fingerprints, and `cache_key`
      (`ARCHITECTURE.md` §7, ADR-20). `doc_id` must be computable from collection-time values
      only — it must not accept a `content_hash` argument at all, so the dependency cannot
      reappear later.
- [ ] `src/core/hashing.py` — canonical content hashing for rebuild equality, with the
      volatile-field exclusion list from `ARCHITECTURE.md` §8.2 as data (ADR-26).
- [ ] `src/core/versions.py` — `SCHEMA_VERSION`, prompt-version registry, `RULESET_VERSION`,
      `NORMALIZER_VERSION`, `TAXONOMY_VERSION = "0-unassigned"`.
- [ ] `src/core/errors.py` — the exception hierarchy: `ValidationError`,
      `EvidenceError`, `ProviderError`, `ConfigError`.
- [ ] `config/sources.yaml`, `config/models.yaml`, `config/analysis.yaml`,
      `config/taxonomy.yaml` (empty clusters, `version: 0-unassigned`).
- [ ] `.env.example` — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AUTHOR_SALT`,
      `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `YOUTUBE_API_KEY`. Values empty.
- [ ] `data/` directory tree with `.gitkeep` files: `manual/ raw/ interim/ processed/
      gold/ exports/`.
- [ ] `STATUS.md`, `DECISIONS.md` (seeded with ADR-1…9), `CHANGELOG.md`.
- [ ] `main.py` — CLI skeleton with `--help` only; no stages wired yet.

### Tests

- [ ] `tests/test_config.py` — config loads; a missing required key raises `ConfigError`;
      absent optional secrets do not raise.
- [ ] `tests/test_architecture.py` — first two boundary rules: `core` imports nothing
      internal; no module imports a provider SDK.
- [ ] `tests/test_ids.py` — hashes are deterministic; `author_hash` changes with the salt;
      `doc_id` is computable with no derived value available; `source_url_key` normalizes
      tracking parameters and host case identically across runs.
- [ ] `tests/test_hashing.py` — canonical content hash ignores run IDs and timestamps and
      changes when a data field changes.

### Commands

```bash
python --version                 # expect 3.12.x
pip install -e ".[dev]"
pytest -q
git status --porcelain           # expect no .env, no data/raw, no *.db
```

### Exit criteria

- [ ] Python 3.12 environment works and `pytest` passes (spec §24 Phase 0).
- [ ] Secrets and local data are excluded from git — verified by `git status`, not assumed.
- [ ] No Streamlit, collector, or LLM code exists.
- [ ] `STATUS.md` records Phase 0 complete and Phase 1 as next.

### Prompt to paste

```text
Implement only Phase 0 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 0 and ARCHITECTURE.md sections 16 and 17.

Scaffold, config, logging, core id/hash helpers, version registry, tracking documents,
and the three Phase 0 tests. Move "reference files/" to "prototype/" unchanged.
Do not implement models, collectors, LLM calls, analysis, or Streamlit.

Report: files created, the pytest command and its full output, and any assumption
you had to make.
```

---

## Phase 1 — Schemas and evidence validation

**Goal:** every Pydantic contract, the controlled vocabularies, the evidence-required field
map, and a validator that provably rejects fabricated quotes and unevidenced claims. This is
the phase everything else inherits — spec Section 28 exists because a weak Phase 1 makes every
later number unverifiable.

**Owner:** build. **Scope:** MVP.

### Work items

- [ ] `src/models/enums.py` — every controlled vocabulary from spec §15 and §16:
      `SourcePlatform`, `SourceType`, `EvidenceTier`, `CollectionMethod`, `ScopeClass`,
      `ReasonCode` (with its inclusion / exclusion / review groups, §16.8),
      `KnownItemStatus`, `TargetAssetType`, `SubjectType` (§16.7), `Speaker`, `Outcome`,
      `ExtractorType`, `RememberedCue`, `ForgottenInfo`, `QueryStrategy` (including
      `no_query_formulated`), `SystemResponse`, `Workaround`, `ImpactSignal` (§16.6),
      `DimensionObservationStatus` (§16.9), `DecisionTechnicalState` (§16.10),
      `DuplicateKind` and `DuplicateReviewState` (§16.11), `Stage`, `StageStatus`,
      `OffsetState`, `ValidationState`, `GoldSplit`.
      Every enum keeps `other`. **No enum carries `unknown` or `none_stated`** — absence is
      `DimensionObservationStatus`, per §16's preamble.
- [ ] `src/models/collected_document.py` — spec §15.1 exactly. Immutable model config.
      **No `normalized_text`, `content_hash`, `redaction_spans`, `duplicate_of`, or
      `duplicate_kind`** (ADR-15).
- [ ] `src/models/document_derived.py` — spec §15.6, with the
      `len(raw_text_audit) == len(raw_text)` assertion.
- [ ] `src/models/duplicate_link.py` — spec §15.7, including `review_state`.
- [ ] `src/models/evidence.py` — `EvidenceSpan` per §15.2 and `ObservedValue` per §15.5,
      where `evidence` is required, not optional.
- [ ] `src/models/relevance.py` — `RelevanceDecision` per §15.3: `is_relevant` is a computed
      property of `scope_class`, any supplied value is discarded, evidence is non-empty for
      every class including `out_of_scope`, and a non-`ok` `technical_state` forces a null
      scope class and empty evidence (ADR-17).
- [ ] `src/models/retrieval_case.py` — `RetrievalCase` per §15.4 with every paired
      `*_observation` field. **No `candidate_cluster`, no `cluster_confidence`, no
      `taxonomy_version`.** Non-null `severity` requires non-empty `severity_evidence` (§17.7).
      `all_evidence_spans` is computed, not settable (ADR-16).
- [ ] `src/models/stage_event.py` — spec §15.8, append-only semantics (ADR-18).
- [ ] `src/models/cluster_assignment.py` — spec §15.9, the only contract with
      `taxonomy_version` (ADR-19).
- [ ] `src/models/gold.py` — `GoldDocumentLabel` and `GoldCase` per §15.11, with `split` and
      `pre_adjudication_labels` (ADR-25).
- [ ] `src/models/export.py` — `PublicExportRecord` per §15.12 (ADR-23).
- [ ] `src/models/evidence_map.py` — `EVIDENCE_REQUIRED` and `EVIDENCE_EXEMPT` as data
      (`ARCHITECTURE.md` §9.5, spec §15.10), plus the status-gate table.
- [ ] `src/extract/validator.py` —
      - `validate_span(span, raw_text, redaction_spans)`: the ladder in `ARCHITECTURE.md`
        §9.3 — exact match → offset repair → whitespace-normalised repair (storing the
        **original** substring) → reject. Rejects any span overlapping a redacted region.
        Missing offsets recovered when the occurrence is unique; an ambiguous tie is left
        unresolved and flagged, never guessed (spec §26.3).
      - `validate_record(record, spans)`: applies the evidence map and the status gate, and
        derives `all_evidence_spans`, rejecting any span attached to no field.
- [ ] Schema versioning: every model carries `schema_version` from `core.versions`.

**Design note worth honouring:** span validation needs the parent document's text, which a
Pydantic field validator cannot see. Keep it a service function called by the store layer at
the validity gate, not a model validator. This is why `validation_state` is a stored column
rather than an implicit property.

### Tests (spec §25 "Schemas" and "Evidence")

- [ ] `tests/test_models.py` — valid `CollectedDocument`; **it validates with no
      `DocumentDerived` or `DuplicateLink` anywhere in the process**; invalid URL, datetime,
      enum, and empty text each rejected; valid and invalid `RetrievalCase`; null and
      observation-status behaviour; `schema_version` present.
- [ ] Negative test: `RetrievalCase` field set contains no `candidate_cluster`,
      `cluster_confidence`, or `taxonomy_version`.
- [ ] Negative test: a `RelevanceDecision` whose `is_relevant` disagrees with `scope_class`
      is rejected; an `out_of_scope` decision with empty evidence is rejected; a
      `technical_state = provider_unavailable` record with a non-null `scope_class` is
      rejected.
- [ ] `tests/test_evidence.py` — exact quote and offsets succeed; **fabricated quote fails**;
      wrong offsets fail; duplicate quote occurrence handled explicitly, with the ambiguous-tie
      case left unresolved rather than guessed; whitespace repair preserves the original
      displayed text; span overlapping a redaction is rejected.
- [ ] `tests/test_evidence_map.py` — every field of `RelevanceDecision` and `RetrievalCase`
      appears in exactly **one** of `EVIDENCE_REQUIRED` and `EVIDENCE_EXEMPT`; each status in
      the gate table is exercised; `all_evidence_spans` equals the field-level union; a
      model-supplied `all_evidence_spans` is discarded; a span attached to no field fails.
- [ ] Negative test: `severity = 4` with empty `severity_evidence` raises.
- [ ] Negative tests for status conflicts: `stated` with no value; `not_stated` with a value;
      `not_stated` carrying evidence.
- [ ] All fixtures carry `evidence_tier = synthetic_test`.

### Commands

```bash
pytest tests/test_models.py tests/test_evidence.py tests/test_evidence_map.py -v
pytest -q --cov=src/models --cov=src/extract/validator
```

### Exit criteria

- [ ] Every schema has positive and negative tests (spec §24 Phase 1).
- [ ] Fabricated evidence fails validation — shown in test output.
- [ ] `CollectedDocument` validates with no later-stage field present — shown in test output.
- [ ] Every model field is classified as evidence-required or evidence-exempt.
- [ ] Missing facts remain null or empty with an observation status; nothing is defaulted into
      a value and no `unknown` placeholder exists.
- [ ] Synthetic fixtures are marked and excluded.
- [ ] Invariants I2, I3, I6, I11, I12, I13 are each covered by at least one test.

### Prompt to paste

```text
Implement only Phase 1 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 1 and ARCHITECTURE.md sections 6, 7, and 9.

Build every Pydantic contract in spec Section 15, every controlled vocabulary in
Section 16, the evidence-required field map and closed exception list from Section
15.10, and the evidence validator.

Hard requirements, each of which needs a test that fails without it:
- CollectedDocument must validate with no DocumentDerived, DuplicateLink, or any
  other later-stage value present anywhere.
- RetrievalCase must have no candidate_cluster, cluster_confidence, or
  taxonomy_version field.
- RelevanceDecision.is_relevant must be derived from scope_class; discard any
  supplied value and reject a stored conflict.
- Every relevance decision, including out_of_scope, requires non-empty evidence.
- A non-ok technical_state forces a null scope_class and empty evidence.
- No enum may contain "unknown" or "none_stated"; absence is expressed by
  DimensionObservationStatus.
- all_evidence_spans is derived as the union of field-level spans; a span attached
  to no field fails validation.
- Every field on RelevanceDecision and RetrievalCase appears in exactly one of the
  required or exempt lists, asserted by a test over the model definitions.

Do not implement collectors, the store layer, LLM calls, analysis, or Streamlit.
All fixtures must be marked evidence_tier = synthetic_test.

Report: files created, the pytest command and its full output, and any conflict you
found with problem-statement.md.
```

---

## Phase 2 — Manual import and pilot corpus

**Goal:** an idempotent CSV/JSONL importer writing immutable `CollectedDocument` records, plus
30–50 genuine public documents collected by hand.

**Owner:** build **and** research, in parallel. **Scope:** MVP — this is the guaranteed
baseline collection path (spec §11.4), not a fallback.

### Build work items

- [ ] `src/store/database.py` — SQLite connection, DDL for `collected_documents`,
      `ingest_batches`, `stage_events`; a guard that raises on any `UPDATE`/`DELETE` against
      `collected_documents` and `stage_events` (invariants I1, I14).
- [ ] `src/store/migrations.py` — versioned, forward-only migrations.
- [ ] `src/store/views.py` — the view definitions from `ARCHITECTURE.md` §6.2, created now
      even though most are empty, so later phases query stable names.
- [ ] `src/collect/base.py` — `Collector` protocol returning `RawBatch`; shared provenance
      stamping (`collection_method`, `collection_query`, `batch_id`).
- [ ] `src/collect/manual.py` — CSV and JSONL import: per-row validation, author hashing at
      the boundary, `source_url_key` and `raw_text_sha256` computation, `doc_id` derivation
      from collection-time values only (ADR-20), append to `data/raw/`, then project into
      SQLite. Invalid rows are collected into a report, never silently skipped.
- [ ] `src/pipeline/events.py` — `StageEvent` emission helper, used by import and by every
      later stage (ADR-18).
- [ ] `data/manual/TEMPLATE.csv` + a short column guide — **build this first and hand it to
      the analyst on day one**, since collection is the critical path.
- [ ] `scripts/validate_dataset.py` — first version: schema-validate everything on disk.
- [ ] Wire `main.py import --path ... --source ...`.

### Research work items

- [ ] Collect 30–50 genuine public documents across at least three source types, favouring
      Reddit, Google Photos Help, and store reviews for **direct user** evidence.
- [ ] For every row: direct permalink, verbatim `raw_text`, `source_platform`,
      `source_type`, **`evidence_tier`**, published date where visible, and the search query
      used to find it.
- [ ] Tier honestly at collection time. The prototype's main defect was counting tech-press
      articles as user evidence (`ARCHITECTURE.md` §20.2 item 3); the fix only works if the
      tier is set correctly on the way in.
- [ ] Hand-label a small seed set with expected scope class, for a smoke check in Phase 4.
- [ ] Keep a collection log: source, query, date, how many results were scanned versus kept.
      This becomes the Phase 11 methodology section.

### Tests (spec §25 "Import" and "Privacy")

- [ ] `tests/test_manual_import.py` — valid CSV and JSONL; missing fields; malformed rows;
      duplicate import is idempotent; IDs are stable across re-import; **import succeeds with
      `src/normalize/` and `src/dedupe/` absent from the import path**.
- [ ] `tests/test_store.py` — `UPDATE` on `collected_documents` raises; `UPDATE` on
      `stage_events` raises; re-import produces identical `doc_id` values; the
      `collected_documents` column set matches the Phase 1 model with no derived column.
- [ ] `tests/test_stage_events.py` — import emits `started` and `succeeded` events; a failed
      row emits `failed` with a reason code; events are never rewritten.
- [ ] Privacy: `author_hash` deterministic under a fixed salt; no plaintext author appears
      in any processed export.

### Commands

```bash
python main.py import --path data/manual/pilot-01.csv --source manual_csv
python main.py import --path data/manual/pilot-01.csv --source manual_csv   # idempotent
python scripts/validate_dataset.py
pytest tests/test_manual_import.py tests/test_store.py -v
```

### Exit criteria

- [ ] Import is idempotent; a second run adds zero rows (spec §24 Phase 2).
- [ ] Invalid rows are reported with row numbers and reasons.
- [ ] Import requires nothing that Phase 3 produces — demonstrated by the test above.
- [ ] No plaintext usernames in processed exports.
- [ ] At least 30 collected pilot documents present, with counts broken down by
      `source_platform` and `evidence_tier`.

### Prompt to paste

```text
Implement only Phase 2 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 2 and ARCHITECTURE.md sections 5, 6, and 7.

Build the SQLite store with the collected_documents, ingest_batches, and stage_events
tables, forward-only migrations, the view definitions, the Collector protocol, the
CSV/JSONL manual importer, the stage-event helper, the analyst CSV template, and
scripts/validate_dataset.py.

Hard requirements:
- Manual import is the guaranteed baseline collection path, not a fallback.
- Import must work with no normalization, hashing, dedupe, or classification code in
  the path. Assert this with a test.
- doc_id is derived from collection-time values only: source_item_id, else
  source_url_key, else a hash over source_name, author_hash, published_at and
  raw_text_sha256. It must never take content_hash.
- UPDATE and DELETE against collected_documents and stage_events must raise.
- Re-importing the same file adds zero rows and produces identical doc_id values.
- Author hashing happens at the import boundary; no plaintext username is stored.

Do not implement normalization, dedupe, relevance, extraction, analysis, or Streamlit.

Report: files created, the test command and full output, the import command run twice
with row counts, and the pilot document counts by source_platform and evidence_tier.
```

---

## Phase 3 — Normalization and deduplication

**Goal:** derived text, length-preserving redaction, canonical URLs, stable hashes,
duplicates linked rather than deleted, and **the review queue that duplicate review items go
into**.

**Owner:** build, with one human calibration decision. **Scope:** MVP.

### Work items

- [ ] `src/normalize/text.py` — NFKC, whitespace collapse, `normalized_text`, language
      detection (optional dependency; fall back to the supplied `language`).
- [ ] `src/normalize/privacy.py` — **length-preserving** PII masking producing
      `raw_text_audit` and `redaction_spans` (`ARCHITECTURE.md` §9.2). Patterns: email,
      phone, `@handle`, long digit runs. Assert `len(raw_text_audit) == len(raw_text)` —
      this assertion is what keeps every evidence offset valid.
- [ ] `src/normalize/canonicalize.py` — canonical URL: strip `utm_*` and tracking params,
      normalise host, resolve known share-link forms; derive `parent_thread_id` where the
      URL exposes it.
- [ ] `src/normalize/tokens.py` — `token_count` over `normalized_text`, which the
      minimum-length guard depends on.
- [ ] `src/dedupe/exact.py` — same-source-item detection via `(source_platform,
      source_item_id)` and `source_url_key`, then `content_hash` grouping.
      **The canonical document of a group is the lowest `doc_id` by byte-wise ascending
      comparison** (ADR-20) — not the first collected, which depends on run order rather than
      on the documents.
- [ ] `src/dedupe/near_duplicate.py` — 64-bit simhash over 3-word shingles, banded blocking,
      configurable threshold, ambiguous band routed to review; classify `duplicate_kind` as
      `same_source_item` / `exact_text` / `near` / `cross_post` / `quoted_repeat`.
- [ ] `src/dedupe/safety.py` — the spec §19.6 safety conditions, all of which must hold before
      an automatic decision (ADR-21):
      - both documents at or above `dedupe_min_tokens` (default 25);
      - **not** both author hashes present and different;
      - similarity outside the review band;
      - not a quoted repeat.
      Any failure sets `review_state = pending_review` with the matching reason code.
- [ ] `src/review/queue.py` — **built here, not in Phase 4** (ADR-24). Dedupe is the first
      stage that produces review items, so the queue must exist before Phase 4 has anything to
      add to it. Entries carry `target_type`, `target_id`, `reason_code`, priority, and
      resolution state.
- [ ] `documents_derived`, `duplicate_links`, and `review_queue` tables. **No `doc_state`
      column** — progress is `stage_events` (ADR-18).
- [ ] Wire `main.py run --stages normalize,dedupe`.

### Research work item

- [ ] Calibrate the near-duplicate band **and** `dedupe_min_tokens` on the pilot corpus:
      review every pair the default flags and every pair in the review band, then record the
      chosen values as an amendment to ADR-21 in `DECISIONS.md`. Short store reviews are the
      case to watch: they collide at low Hamming distance without being duplicates, which is
      what the token minimum exists to catch.
- [ ] Work the duplicate review queue to empty, or record the remaining backlog — it appears
      on its own funnel line either way.

### Tests (spec §25 "Deduplication")

- [ ] `tests/test_normalize.py` — raw text unchanged after normalization; redaction
      preserves length; offsets valid against both `raw_text` and `raw_text_audit`;
      canonical URL strips tracking params.
- [ ] `tests/test_dedupe.py` — same-source-item re-ingestion under a different URL form;
      exact duplicates; near duplicates; cross-posts; quoted text inside replies routed to
      review; duplicates linked and still present; re-run produces identical IDs and identical
      duplicate assignments.
- [ ] `tests/test_dedupe.py` — **shuffling ingestion order leaves every `canonical_doc_id`
      unchanged.** This is the test that the first-collected rule could never have passed.
- [ ] `tests/test_dedupe.py` — identical short text from two different `author_hash` values is
      **not** auto-collapsed; a pair below `dedupe_min_tokens` is never auto-marked; review-band
      pairs open queue items and are excluded from the duplicate count until resolved.
- [ ] `tests/test_review_queue.py` — dedupe opens items with correct reason codes; resolution
      appends rather than rewrites.

### Commands

```bash
python main.py run --stages normalize,dedupe
python main.py run --stages normalize,dedupe          # idempotent, same hashes
sqlite3 data/interim/engine.db "select duplicate_kind, review_state, count(*) from duplicate_links group by 1,2;"
sqlite3 data/interim/engine.db "select reason_code, count(*) from review_queue group by 1;"
pytest tests/test_normalize.py tests/test_dedupe.py tests/test_review_queue.py -v
```

### Exit criteria

- [ ] Raw text unchanged (spec §24 Phase 3).
- [ ] Duplicates linked, not deleted, and duplicate status is a `DuplicateLink` rather than a
      lifecycle state.
- [ ] Re-running produces identical IDs and duplicate assignments, including under shuffled
      ingestion order.
- [ ] Identical short text from different authors routed to review, not collapsed.
- [ ] Quoted repeats routed to review.
- [ ] The review queue exists and holds the duplicate review items produced in this phase.
- [ ] `dedupe_min_tokens` and the similarity band are in `config/analysis.yaml` and recorded in
      the ADR-21 amendment.
- [ ] Analysis can exclude duplicates without losing auditability — demonstrated by
      querying `v_confirmed_duplicates` and `v_duplicates_pending`.

### Prompt to paste

```text
Implement only Phase 3 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 3 and ARCHITECTURE.md sections 6, 7.2, 9.2, and 11.

Build normalization producing DocumentDerived, length-preserving PII redaction,
canonical URLs, content hashing, simhash, token counting, exact and near-duplicate
detection writing DuplicateLink rows, and the review queue.

Hard requirements, each needing a test:
- len(raw_text_audit) == len(raw_text), and evidence offsets stay valid against both.
- The canonical document of a duplicate group is the lowest doc_id by byte-wise
  ascending comparison. Shuffling ingestion order must not change any
  canonical_doc_id.
- Identical text from two different author_hash values is never auto-collapsed; it
  goes to review.
- No automatic near-duplicate decision below dedupe_min_tokens, default 25, read from
  config/analysis.yaml.
- Quoted repeats and review-band similarities go to review and are excluded from the
  duplicate count until resolved.
- Build the review queue in this phase. Duplicate review items are produced here and
  must have somewhere to live before Phase 4.
- No doc_state column. Emit StageEvent rows instead.

Do not implement the prefilter, relevance, LLM calls, extraction, analysis, or
Streamlit.

Report: files created, the test command and full output, duplicate counts by kind and
review state, review-queue counts by reason code, and the calibration values you
propose for ADR-21.
```

---

## Phase 4 — Relevance classification

**Goal:** a high-recall deterministic prefilter, an evidence-carrying LLM scope classifier,
the LLM gateway with caching and repair, and the pipeline runner that makes runs resumable.

**Owner:** build. First phase that spends money — dry-run before every real run.
**Scope:** MVP, except the OpenAI adapter, which is stretch (ADR-14, ADR-27).

### Work items

- [ ] `src/relevance/rules.py` — deterministic prefilter, `ruleset_version` recorded.
      **Tune for recall, not precision** (spec §19.1): a document this drops never gets a
      classifier opinion, so its drop reasons are stored and measured against the gold set in
      Phase 6 rather than trusted. Obvious excludes: backup, sync, storage, billing,
      deletion, corruption, account access.
- [ ] `src/llm/providers/base.py` — `complete_structured(prompt, schema, params)` protocol.
- [ ] `src/llm/providers/anthropic.py` and `null.py`. The `null` provider is the production
      path when no key is configured, returning a clean "unavailable" rather than raising
      (`ARCHITECTURE.md` §10). `openai.py` is **stretch** — build it only once the MVP path is
      green.
- [ ] `src/llm/cache.py` — content-addressed cache under `data/interim/cache/`, key per
      spec §19.5 and `ARCHITECTURE.md` §8. Provider, model, prompt id and version, schema
      version, `content_hash`, and decoding parameters. **`taxonomy_version` is not in this
      key** — it belongs only to the taxonomy stages (ADR-19). Store the request, raw response,
      provider, model, and timestamp so a corpus can be replayed offline.
- [ ] `src/llm/repair.py` — the repair ladder state machine (`ARCHITECTURE.md` §10.1).
      "Safe cleanup" is syntax only: fenced code, trailing commas, smart quotes. **No step
      may change a value, drop a field, or relax an enum.**
- [ ] `src/llm/gateway.py` — the single entry point: cache lookup, retry with backoff,
      timeout, token accounting, repair orchestration.
- [ ] `src/relevance/prompts.py` — versioned prompt (`relevance/v1`) demanding a scope class,
      a reason code, a confidence, and a verbatim evidence span for **every** decision,
      including `out_of_scope`. The prompt must **not** ask for `is_relevant` (ADR-17), and it
      must cover the spec §9.1 case of a known item with no formulable query.
- [ ] `src/relevance/classifier.py` — returns `RelevanceDecision` with `is_relevant` derived
      from `scope_class`, discarding any supplied value. Maps every non-success outcome to a
      `DecisionTechnicalState` with a null scope class and empty evidence. Confidence below the
      configured threshold, a prefilter/classifier contradiction, or a non-`ok` technical state
      opens a review item.
- [ ] Extend `src/review/queue.py` (built in Phase 3) with the relevance review reason codes.
- [ ] `src/pipeline/runner.py`, `stages.py`, `manifest.py` — checkpointing via
      `stage_checkpoints`, `--resume`, `--limit`, `--dry-run`, `StageEvent` emission, and
      run-manifest writing with per-stage funnel counts and canonical output hashes
      (spec §19.5, §26).
- [ ] Add dependencies: `anthropic>=0.34,<1`, `openai>=1.40,<2`, `tenacity>=8,<10`.

### Tests (spec §25 "Relevance")

- [ ] `tests/test_relevance.py` — core incomplete-recall case classified `core`; a known item
      the user could not turn into a query classified `core` with reason code
      `known_item_query_unformulable`; adjacent exact-recall search defect classified
      `adjacent`; backup/billing/storage/deletion/editing complaints excluded; editorial
      capability example excluded; uncertain case routed to review.
- [ ] `tests/test_relevance.py` — **any** decision without evidence is rejected, including
      `out_of_scope`; a model response containing `is_relevant` has it discarded; a
      provider-unavailable and a parse-failed attempt each produce a technical state with a
      null scope class, and neither is counted as `out_of_scope`.
- [ ] `tests/test_llm_gateway.py` — cache key changes with model, prompt version, schema
      version, and content; **it does not change with taxonomy version**; a cache hit makes
      zero provider calls; the `null` provider degrades cleanly with no key set and yields
      `technical_state = provider_unavailable`.
- [ ] `tests/test_pipeline_runner.py` — `--dry-run` writes nothing; `--resume` skips
      completed checkpoints; a manifest is written with funnel counts.
- [ ] Provider calls are mocked throughout. No test hits a live API.

### Commands

```bash
python scripts/check_credentials.py
python main.py run --stages prefilter --limit 50
python main.py run --stages relevance --limit 5 --dry-run
python main.py run --stages relevance --limit 50
sqlite3 data/interim/engine.db "select scope_class, count(*) from relevance_decisions group by 1;"
pytest tests/test_relevance.py tests/test_llm_gateway.py tests/test_pipeline_runner.py -v
```

### Exit criteria

- [ ] **Every** decision carries evidence, including `out_of_scope` (spec §24 Phase 4).
- [ ] `is_relevant` is derived and never read from the model response.
- [ ] Provider-unavailable and parse-failed records carry a technical state, are counted
      separately, and are excluded from every metric.
- [ ] Low-confidence items are in the review queue and reviewable.
- [ ] Obvious storage, backup, billing, and deletion complaints are excluded — show the
      counts by `reason_code`.
- [ ] Core and adjacent cases remain separate in storage and in every query.
- [ ] The pipeline runs end-to-end with `--dry-run` and with no API key present.

### Prompt to paste

```text
Implement only Phase 4 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 4 and ARCHITECTURE.md sections 4.2, 8, 10, and 11.

Build the deterministic prefilter, the src/llm gateway (cache, retry, repair ladder,
the Anthropic adapter and the null provider), the relevance classifier returning
RelevanceDecision, the relevance review reason codes on the Phase 3 queue, and the
pipeline runner with checkpoint, resume, limit, and dry-run.

Hard requirements, each needing a test:
- Every decision carries evidence, including out_of_scope. The prompt asks for a
  verbatim span for the exclusion too.
- The prompt must not ask for is_relevant. Derive it from scope_class and discard any
  supplied value.
- Provider unavailable, timeout, parse failure, and schema failure each produce a
  DecisionTechnicalState with a null scope_class and empty evidence, counted separately
  and never as out_of_scope.
- The cache key must NOT include taxonomy_version. Assert that changing taxonomy
  version does not invalidate a relevance cache entry.
- A known item the user cannot formulate a query for classifies as
  core_incomplete_recall with reason code known_item_query_unformulable.
- Tune the prefilter for recall, not precision, and store drop reasons.

The OpenAI adapter is stretch scope. Do not build it in this phase.
Do not implement extraction, taxonomy, analysis, retrieval, or Streamlit.
Mock all provider calls in tests. Do not relax validation to make output pass.

Report: files created, the test command and full output, the counts by scope_class and
by reason_code from the 50-document run, the technical-failure counts, and the
estimated token spend.
```

---

## Phase 5 — Structured extraction  →  **GATE M1**

**Goal:** validated `RetrievalCase` records with every substantive field backed by a
verbatim span, and the first milestone from spec Section 28 demonstrably met.

**Owner:** build, then a joint review of the gate.

### Work items

- [ ] `src/extract/prompts.py` — versioned extraction prompt (`extract/v1`) covering the full
      spec §15.4 field set. The prompt must state the negative rules explicitly, because these
      are the failures that corrupt research data: do not infer forgotten information from
      silence (§17.5); store `exact_query` only when directly quoted (§17.3); leave severity
      null unless behaviour or consequence justifies it (§18); never paraphrase into `quote`.
- [ ] `src/extract/extractor.py` — runs on relevant core and adjacent documents only; emits
      zero, one, or many cases per document (§8.5); receives `raw_text_audit` so offsets align
      and no unredacted PII leaves the machine.
- [ ] Extend `src/extract/validator.py` — full record gate: schema, every span, the
      evidence-required field map and status gate (ADR-16), the severity-evidence rule, enum
      membership, derived `all_evidence_spans`, and `case_id` ordinal assignment by
      first-evidence position with the full tie-break chain and the `#u` fallback for
      unresolved offsets (ADR-20).
- [ ] Persist `retrieval_cases`, `case_labels` (one row per `ObservedValue`, ADR-2),
      `evidence_spans`, and `extraction_failures`.
- [ ] `src/review/overrides.py` — append-only human overrides with author, rationale, and
      optional evidence, applied as the top precedence layer in `v_current_cases`;
      `extractor_type = human`.
- [ ] No cluster field exists on the case, so there is nothing to leave null (spec §15.4,
      invariant I10). The extraction prompt must not mention clusters or the taxonomy.

### Tests (spec §25 "Extraction")

- [ ] `tests/test_extraction.py` — exact query preserved; missing query stays null with
      `not_stated`; forgotten information not inferred from silence, and `not_stated` versus
      `explicitly_none` distinguishable in storage; unsupported severity rejected; an invalid
      model response enters repair then failure handling.
- [ ] `tests/test_extraction.py` — the extraction cache key changes with model, prompt, schema,
      or content, and **does not change with taxonomy version**; the taxonomy-assignment key
      does.
- [ ] `tests/test_extraction.py` — every evidence-required field lacking evidence with a
      `stated` status is rejected; a field with `not_stated` carrying evidence is rejected;
      `all_evidence_spans` is derived and a supplied value is discarded.
- [ ] Multi-case document produces multiple cases with stable, position-ordered `case_id`s,
      including the identical-offset tie case and the unresolved-offset `#u` case.
- [ ] A human override supersedes the model record in `v_current_cases` while the original
      row survives.

### Commands

```bash
python main.py run --stages extract --limit 5 --dry-run
python main.py run --stages extract
python scripts/validate_dataset.py --strict
sqlite3 data/interim/engine.db "select validation_state, count(*) from retrieval_cases group by 1;"
sqlite3 data/interim/engine.db "select count(*) from evidence_spans where validation_state!='valid';"
pytest tests/test_extraction.py -v
```

### Exit criteria (spec §24 Phase 5)

- [ ] No invalid record entered processed data.
- [ ] Exact queries are never fabricated.
- [ ] Every evidence quote validates against raw text — the count of non-valid spans is zero.
- [ ] Every evidence-required field has field-level evidence or a permitting observation
      status.
- [ ] Absent facts carry an observation status and a null or empty value.
- [ ] No case carries a cluster label or a taxonomy version.
- [ ] Model, prompt, and schema versions are stored on every record; `taxonomy_version` is
      deliberately absent.

### GATE M1 — spec Section 28, do not proceed until all five hold

- [ ] ≥ 30 genuine public documents processed.
- [ ] The pipeline ran end to end, import through extraction.
- [ ] 100% of extracted claims backed by a validated verbatim span.
- [ ] Per-stage funnel counts reported from `stage_events`.
- [ ] All schema and evidence tests passing.

**The qualifying-case count is reported, not targeted** (ADR-29). Earlier drafts required
15–25 cases here. That was a trap: the only reliable lever for moving the count is the
strictness of the prompts, and tuning prompts until the count lands in a band means fitting
the instrument to a desired reading — with the evidence rules as the thing that quietly gets
relaxed.

Report the count with its funnel and diagnose it per spec §28, investigating four stages
separately rather than reaching for the extraction prompt:

| Stage | Question | Evidence to read |
|---|---|---|
| Sampling | Did collection find retrieval discussions at all? | collection log: results scanned versus kept, per query and source |
| Prefilter | Is the high-recall stage dropping real cases? | prefilter drop reasons; prefilter recall against gold in Phase 6 |
| Classification | Are core documents landing in `out_of_scope`, or vice versa? | reason-code distribution; the `out_of_scope` evidence spans, which now exist and are readable |
| Extraction | Are relevant documents yielding zero or too many cases? | extraction failures, repair exhaustion, unresolved-offset review items, multi-case span distinctness |

Fix the stage the evidence implicates, bump that stage's version, and record the reasoning in
`DECISIONS.md`.

### Prompt to paste

```text
Implement only Phase 5 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 5 and ARCHITECTURE.md sections 9.3, 9.5, 10.1, and 11.

Build the versioned extraction prompt, the extractor, the full-record validator gate,
persistence of retrieval_cases / case_labels / evidence_spans / extraction_failures,
and append-only human overrides.

Hard requirements, each needing a test:
- Enforce the evidence-required field map and the observation-status gate from spec
  Section 15.10. A stated field without evidence fails; a not_stated field carrying
  evidence fails.
- all_evidence_spans is derived as the union of field-level spans. Discard any
  model-supplied value and reject a span attached to no field.
- No cluster field and no taxonomy_version on the case. The prompt must not mention
  clusters or the taxonomy.
- The extraction cache key and extraction_fingerprint must exclude taxonomy_version.
  Assert that changing taxonomy version does not invalidate a cached extraction.
- case_id ordinals sort by first-evidence start_char, then end_char, then sha1(quote),
  then sha1(payload). A case with unresolved offsets gets the doc_id#u<hash> form, is
  never valid, and enters review.
- The prompt states the negative rules explicitly: do not infer forgotten information
  from silence, store exact_query only when directly quoted, leave severity null
  unless behaviour or consequence justifies it, never paraphrase into quote.

Do not implement taxonomy assignment, analysis, retrieval, or Streamlit.
Mock all provider calls in tests.

Report: files created, the test command and full output, validation-state counts, the
count of non-valid evidence spans, the per-stage funnel, and the qualifying-case count
with your diagnosis of which stage explains it. Do not tune prompts to move the count
into a band.
```

---

## Phase 6 — Gold-set evaluation  →  **GATE QG**

**Goal:** honest measurement of the pipeline against human labels, and documented corrective
action for every failure category.

**Owner:** research (labelling) then build (metrics). **Scope:** MVP.

### Research work items — two separate labelling passes

**Pass 1, document level.** Label 75–100 documents with a `GoldDocumentLabel` each:
scope class, reason code, `prefilter_should_pass`, and `expected_case_count`.

- [ ] Include relevant **and** excluded examples, multiple sources, and deliberate boundary
      cases — adjacent search defects, editorial examples, known items with no formulable
      query, and the storage/billing noise that dominates raw feeds.
- [ ] Set `prefilter_should_pass` on its own judgement: would a correct high-recall filter let
      this through? This is what makes prefilter recall measurable independently of the
      classifier, and a prefilter drop is otherwise invisible to every later stage.

**Pass 2, case level.** For each relevant document, label **zero, one, or several**
`GoldCase` rows.

- [ ] Zero is a valid and expected label. A document can be relevant at the document level and
      still yield no extractable case, and a gold set that cannot express this cannot measure
      over-extraction at all.
- [ ] Give each gold case its expected `{observation, value}` pairs and the verbatim quotes the
      reviewer considers sufficient support. Those quotes are validated by the production
      validator — a paraphrase in a gold label is a defect in the gold set.

**Both passes.** Double-code at least 20% with a second reviewer and **retain every
independent label** in `pre_adjudication_labels`. Inter-coder disagreement is itself a finding
about definition clarity, and it disappears the moment you adjudicate, so it has to be
captured first.

### Splits — define before labelling, freeze before measuring

- [ ] Assign each document deterministically by a hash of `doc_id`: roughly 40% `dev`, 60%
      `holdout`, stratified across source platform and scope class.
- [ ] The **dev** split is the only data used for prompt iteration, threshold tuning, and error
      analysis. Read it freely.
- [ ] The **holdout** split is frozen. Read it once per reported configuration. Every number in
      the final quality report and the submission comes from it. Iterating against the holdout
      turns a measurement into a fitting exercise, which is the same error as relabelling gold
      documents to match the model, just harder to notice.
- [ ] Record the split rule and seed in the gold files and the run manifest.

### Build work items

- [ ] `data/gold/documents.jsonl` and `data/gold/cases.jsonl` formats + loaders, keyed by
      `doc_id` (ADR-25).
- [ ] Deterministic, stratified split assignment.
- [ ] Case-matching: align extracted cases to gold cases by evidence-span overlap, so a correct
      extraction that emits cases in a different order is not penalised. Version this rule with
      the evaluation script.
- [ ] `scripts/evaluate.py` — the metric families from spec §24 Phase 6:
      - **scalar accuracy** on `scope_class`, `known_item_status`, `target_asset_type`,
        `outcome`, `severity`, `reformulation_count`, and every `*_observation` field, where
        both value and observation status must match;
      - **multi-label precision, recall, F1** on `target_subjects`, `remembered_cues`,
        `forgotten_information`, `query_strategies`, `system_responses`, `workarounds`,
        `impact_signals`, reported **micro and macro separately** — macro exposes rare-label
        failure that micro hides;
      - **prefilter recall** from gold `prefilter_should_pass`;
      - **end-to-end relevance precision, recall, F1**, where prefilter and classifier are
        measured together and a prefilter drop counts as predicted not-relevant;
      - **unsupported inference rate**: of extracted values with a non-empty value, the share
        whose evidence is missing, invalid, or on adjudication does not support the value —
        per field and overall;
      - **evidence-span validation rate**;
      - **inter-reviewer agreement**: raw agreement and Cohen's kappa on `scope_class` from
        `pre_adjudication_labels`, reported before adjudication;
      - confusion matrix; failure, review, and duplicate rates.
- [ ] Exclude records with a non-`ok` `technical_state` from every metric and print the excluded
      count beside the metrics.
- [ ] Label every output with the split it came from.
- [ ] Error-analysis export (CSV), **dev split only**: every disagreement with the document
      text, the model's reason, and the gold label — this is the artifact that drives prompt
      iteration.

### Tests

- [ ] `tests/test_gold.py` — document and case labels load independently; a document with zero
      gold cases participates in relevance metrics and contributes no case metrics; a document
      with several gold cases matches order-independently; split assignment is deterministic and
      stratified; gold `expected_evidence` quotes validate against `raw_text`.
- [ ] `tests/test_evaluation.py` — every metric family computed correctly on a tiny synthetic
      gold set; scalar accuracy requires both value and status to match; micro and macro differ
      as expected on an imbalanced fixture; prefilter recall reads gold, not classifier output;
      unsupported inference rate computed per field; agreement computed pre-adjudication; an
      empty gold set produces an honest "pending" result rather than zeros or a crash.

### Commands

```bash
python scripts/evaluate.py --gold data/gold --split dev     --out data/exports/quality/dev/
python scripts/evaluate.py --gold data/gold --split holdout --out data/exports/quality/holdout/
pytest tests/test_gold.py tests/test_evaluation.py -v
```

### GATE QG — spec Section 24 Phase 6 quality gates, measured on the **holdout** split

- [ ] 100% of processed records pass schema validation.
- [ ] 100% of evidence spans pass exact-source validation.
- [ ] **Prefilter recall ≥ 0.90.**
- [ ] **End-to-end relevance precision ≥ 0.85.**
- [ ] **End-to-end relevance recall ≥ 0.80.**
- [ ] Scalar accuracy and multi-label precision/recall/F1 reported per field.
- [ ] Unsupported inference rate reported per field and overall.
- [ ] Inter-reviewer agreement reported before adjudication.
- [ ] Technical-failure exclusions reported with their count.
- [ ] Every failure category has a documented corrective action or an accepted, written
      limitation.

The recall gates sit beside the precision gate deliberately. Precision alone is trivially
satisfied by a pipeline that admits almost nothing — it would produce an excellent-looking
quality report over a corpus that had silently thrown most of the evidence away, and the
prefilter is where that happens without leaving a trace.

If a gate misses: iterate on the **dev** split using the error-analysis export, bump
`relevance/v1` → `v2` or the ruleset version, re-run (the cache means only changed prompts cost
money), and re-measure. **Do not lower a threshold, do not relabel gold documents to match the
model, and do not iterate against the holdout.**

### Prompt to paste

```text
Implement only Phase 6 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 6.

Build the two gold label formats and loaders, deterministic stratified dev/holdout
split assignment, evidence-overlap case matching, and scripts/evaluate.py.

Hard requirements, each needing a test:
- Document-level relevance labels and case-level extraction labels are separate
  records and separate files.
- A document may have zero, one, or many gold cases. Zero must be expressible and must
  still participate in relevance metrics.
- The holdout split is frozen: the script must refuse to emit error-analysis output for
  the holdout split, so prompt iteration cannot read it.
- Scalar accuracy requires both the value and the observation status to match.
- Multi-label fields get micro AND macro precision, recall, and F1, reported separately.
- Prefilter recall is computed from the gold prefilter_should_pass label, not from
  classifier output.
- Relevance precision and recall are end-to-end: a prefilter drop counts as predicted
  not-relevant.
- Unsupported inference rate is reported per field and overall.
- Inter-reviewer agreement is computed from pre_adjudication_labels, before
  adjudication.
- Records with a non-ok technical_state are excluded from every metric and the excluded
  count is printed.
- Gates: prefilter recall >= 0.90, relevance precision >= 0.85, relevance recall >= 0.80.
- An empty gold set yields an honest "pending" result, not zeros.

Do not implement taxonomy, analysis, retrieval, or Streamlit.

Report: files created, the test command and full output, both split reports, and which
gates pass or miss. Do not adjust a threshold to make a gate pass.
```

---

## Phase 7 — Source collectors and scaled run

**Goal:** at least 300 collected documents across at least four source types, collected
through compliant means, with the funnel recorded per source.

**Owner:** build, one collector at a time, in the order set by the **feasibility tiers** in
spec §11.4.

### Collector order and approach

The order is driven by whether a permitted mechanism is *documented*, not by how easy a
library makes a source look. That is the correction ADR-22 records: the previous plan ranked
the two store collectors first and labelled them "low risk", when neither has a documented
mechanism for reading reviews of an app the collector does not own. Ease of implementation was
being read as low risk, and those are different properties — **availability is not
permission**.

A verification pass on 2026-09-21 checked all five sources against live vendor documentation and
settled the ordering below. It confirmed the two sources the plan had treated as secondary and
closed the two it had ranked first, which is the clearest possible argument for the rule. The
store row now reads **closed** rather than "pending documentation": both vendors gate reviews
behind publisher authentication, so the constraint is ownership rather than cost or throughput and
no Phase 7 effort will change it.

| Order | Collector | Tier (spec §11.4) | Method | Precondition |
|---|---|---|---|---|
| — | `manual.py` | **guaranteed baseline** | analyst CSV / JSONL | already built in Phase 2; remains available and tested throughout |
| 1 | `youtube.py` | **supported automated** | YouTube Data API v3 | primary documentation linked in `DECISIONS.md` (ADR-22). Traverse by `parentId`, **not** the `id` filter; build `watch?v={videoId}&lc={commentId}`. Comment reads cost 1 unit against 10,000/day, but `search.list` is a separate 100-calls/day bucket — **seed video IDs from a curated list, do not paginate search** |
| 2 | `reddit.py` | **optional, credential-dependent** | official Reddit Data API, read-only | registered OAuth credentials present — required **even for read-only**, because unauthenticated traffic from a hosted netblock is blocked. 100 queries/minute per client ID; honour `X-Ratelimit-*` headers. Free tier is **non-commercial only**. With no credentials the source is skipped cleanly and the run continues |
| 3 | `support_forum.py` | **manual by default** | none documented | automated collection needs a *permission* basis, not a working URL. The `thread/{threadId}?msgid={replyId}` form is confirmed live and is not robots-disallowed, but Google's ToS bars scraping content belonging to other users, so this stays manual. Thread *search* is robots-disallowed, so discovery cannot be automated either |
| — | `play_store.py`, `app_store.py` | **experimental** | **closed** | **never built.** Both official APIs authenticate the app's *publisher*, so reviews of an app we do not publish are unreachable — no quota increase or paid tier changes this (ADR-22). Manual import permanently. Do not substitute the Apple review RSS feed: it is undocumented, robots-disallowed, and returns zero reviews |

The corpus target must be reachable through manual import plus YouTube alone. Every other
collector is an accelerator, so losing one changes the schedule rather than the deliverable.

Compliance is a hard constraint, not a preference (spec §11.3): prefer official APIs, respect
robots.txt and rate limits, and never bypass authentication or anti-bot controls. A blocked
source degrades to manual import; it does not get worked around.

### Work items

- [ ] For each collector built: implement against `Collector`, stamp full provenance
      (`collection_method`, `collection_query`, `source_item_id`, `parent_thread_id`,
      `source_url`, `source_url_key`), respect configured rate limits, and handle failure by
      stopping that source, emitting a `StageEvent` with `source_blocked` or `rate_limited`, and
      recording the reason in the manifest.
- [ ] Mocked tests per collector using **recorded** fixture payloads; no live calls in tests.
- [ ] `scripts/check_credentials.py` — verify each configured source's credentials before a run,
      and report a missing optional credential as "source disabled", not as an error.
- [ ] `scripts/audit_sources.py` — per-source counts, tier mix, date ranges, feasibility tier,
      and the 40% concentration check (spec §11.2).
- [ ] Record each source's **verification status** in `DECISIONS.md`: `permitted, documented and
      exercised`, `permitted, documented, unexercised`, `undocumented`, or `closed`. A mechanism
      that has not been run in this repository is not "verified", and the Phase 7 report must say
      which is which. Promote YouTube and Reddit from `unexercised` to `exercised` only after a
      real run, and do not downgrade a `closed` source to "pending" (ADR-22).
- [ ] Scaled run with checkpointing; funnel recorded by source.
- [ ] Add dependencies only for collectors actually built: `praw`,
      `google-api-python-client`, `httpx`.

### Tests (spec §25)

- [ ] One test module per collector built: parses recorded fixtures into valid
      `CollectedDocument`s; handles rate-limit and error responses safely; produces stable
      `doc_id`s.
- [ ] Reddit with no credentials configured skips cleanly and does not fail the run.
- [ ] Before the Reddit collector relies on them, re-read the Reddit Data API Wiki from a browser
      and confirm the 100 QPM limit first-hand — the figure in ADR-22 came from indexed copies
      because the page is Cloudflare-gated (ADR-22 consequence 7). Do not cite the archived
      `reddit-archive` wiki, which still says 60 requests/minute.
- [ ] Manual import still works — the guaranteed path is tested, not assumed.

### Commands

```bash
python scripts/check_credentials.py
python main.py collect --source youtube --limit 100
python main.py collect --source reddit --limit 100      # skips cleanly with no credentials
python main.py run --stages all --resume <run_id>
python scripts/audit_sources.py
pytest tests/test_collect_*.py -v
```

### Exit criteria (spec §24 Phase 7)

- [ ] Each collector is independently testable.
- [ ] Rate limits and failures handled safely.
- [ ] Manual import remains available and tested as the guaranteed path.
- [ ] No source is described as verified without primary documentation linked in
      `DECISIONS.md`, and each source's verification status is stated.
- [ ] No collector exists for a source with no documented permitted mechanism.
- [ ] The full funnel is recorded by source.
- [ ] ≥ 300 collected documents processed across ≥ 4 source types, manual import counting
      toward the target.
- [ ] Source concentration measured; if any source exceeds 40% of included cases, the
      imbalance is disclosed and the source-balanced view is available (spec §11.2).

### Prompt to paste

```text
Implement only Phase 7 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 7 and problem-statement.md Section 11.4.

Build collectors strictly in feasibility-tier order. In this phase that means exactly two:
1. youtube.py against YouTube Data API v3. Traverse replies by parentId, never the id
   filter, which is documented as Google+-only. The reply tree is one level deep.
   Build the permalink as watch?v={videoId}&lc={commentId}. Seed video IDs from a
   curated list: comment reads cost 1 quota unit against 10,000/day, but search.list is
   a separate 100-calls/day bucket, so discovery is the binding constraint.
2. reddit.py against the official Reddit Data API, read-only. Registered OAuth
   credentials are required even for read-only access, and the collector must skip
   cleanly when they are absent. Honour the X-Ratelimit-* response headers.
Then scripts/check_credentials.py, scripts/audit_sources.py, and the scaled run.

Do NOT build play_store.py, app_store.py, or support_forum.py, and do not add them to a
backlog. A verification pass on 2026-09-21 established that both store APIs authenticate
the app's publisher, so reviews of an app this project does not publish cannot be read
through any tier, quota increase, or paid plan. The support forum has no documented API,
and while its thread URLs are addressable and not robots-disallowed, Google's terms bar
scraping content belonging to other users. All three sources are collected through
manual.py, permanently.

Specifically forbidden: substituting an unofficial scraping library for a missing
official API, and using the legacy Apple review RSS feed at
itunes.apple.com/{cc}/rss/customerreviews/ — it is undocumented, disallowed by that
host's robots.txt, and returns zero review entries.

Hard requirements:
- Manual import stays the guaranteed baseline and stays tested.
- Every collector stamps full provenance and emits StageEvent rows.
- A blocked or rate-limited source stops, records the reason in the manifest, and lets
  other sources continue.
- All collector tests use recorded fixture payloads. No test hits a live API.
- Record each source's verification status in DECISIONS.md as "permitted, documented and
  exercised", "permitted, documented, unexercised", "undocumented", or "closed". Do not
  write "verified" without a link to primary vendor documentation.

Report: files created, the test command and full output, per-source counts and tier mix
from audit_sources.py, the source-concentration result, and the verification status of
each source.
```

---

## Phase 8 — Taxonomy discovery and analysis

**Goal:** a taxonomy derived from pilot evidence rather than assumed, and the four analysis
outputs the spec requires.

**Owner:** research (cluster review) then build (analysis).

### Research work items — do this first, in this order

- [ ] Read the first 50–100 qualifying cases' `problem_summary` values with cluster labels
      **absent** (spec §20.1 steps 1–2).
- [ ] Group by target, memory cue, behaviour, failure, and impact (step 3).
- [ ] Write provisional cluster definitions **with boundaries and exclusions** (step 4).
- [ ] Test inter-cluster overlap; merge or split (step 5).
- [ ] Write the result into `config/taxonomy.yaml` as `version: 1` and record the derivation
      in `DECISIONS.md`.

The spec's Section 20 hypotheses (associative-memory translation, time/place anchors, face
cues, text fragments, utility clutter, broad results, conversational responses replacing
retrieval, blind reformulation) are **hypotheses to test against the corpus, not a starting
taxonomy**. The prototype's six hard-coded `problem_type` values are exactly what this phase
must not reproduce (`ARCHITECTURE.md` §20.2 item 5).

### Build work items

- [ ] `src/taxonomy/candidates.py` — propose groupings from label co-occurrence and summary
      similarity to *support* human review. It does not name clusters.
- [ ] `src/taxonomy/assign.py` — assign against a named taxonomy version; `other` and
      `uncertain` always available; rows keyed `(case_id, taxonomy_version)`.
- [ ] Computed `established` flag: ≥ 5 independent documents across ≥ 2 source types
      (spec §20.1 step 6). Computed, never hand-authored.
- [ ] Confirm the assignment pass re-runs **no extraction**: `taxonomy_version` is only in
      `assignment_fingerprint` and the taxonomy cache key (ADR-19), so publishing `version: 1`
      must not invalidate a single cached extraction.
- [ ] `src/analyze/funnel.py` — spec §21.1 lines computed **per stage from `stage_events`**,
      not from a lifecycle column, plus the manifest reconciliation. Duplicate links and
      pending-review links are their own lines, and a document appears at every stage it
      reached.
- [ ] `src/analyze/memory_map.py` — cues × forgotten cross-tab, reading `*_observation` from
      the schema and keeping `not_stated` and `explicitly_none` distinct. The analysis layer
      must not define its own status values (`ARCHITECTURE.md` §13.4).
- [ ] `src/analyze/journeys.py` — need → cue → strategy → response → reformulation/workaround
      → outcome → impact.
- [ ] `src/analyze/opportunities.py` — all components from `ARCHITECTURE.md` §13.3 separately;
      unique cases / threads / authors side by side; source-balanced view. The composite score
      is **stretch scope** (ADR-27): off by default, weights from config, with sensitivity
      analysis (weight perturbation and leave-one-source-out). Do not build it while any MVP
      item is unfinished.
- [ ] Add `pandas>=2.2,<3`.

### Tests (spec §25 "Analysis")

- [ ] `tests/test_analysis.py` — duplicates excluded from prevalence; pending-review duplicate
      links excluded from the duplicate count and reported separately; contextual and
      second-hand sources excluded from direct-user counts; unique thread and author counts
      correct; source-balanced calculation correct; output deterministic across runs.
- [ ] `tests/test_analysis.py` — every observation status visible, `not_stated` and
      `explicitly_none` never merged, and **every status appearing in a cross-tab is a schema
      enum member**; records with a non-`ok` technical state excluded with the count reported.
- [ ] `tests/test_stage_events.py` — the funnel reconciles with `stage_events` and the manifest;
      one document appears at every stage it reached, including simultaneously as a duplicate
      and as a valid extraction.
- [ ] `tests/test_taxonomy.py` — a cluster with 4 documents or 1 source type is **not**
      `established`; re-assignment under a new version preserves prior rows; **publishing a new
      taxonomy version triggers zero extraction cache misses**.
- [ ] Severity means report their own denominator alongside the case count.

### Commands

```bash
python main.py run --stages taxonomy,analyze
python -c "from src.analyze.funnel import build; print(build())"
pytest tests/test_analysis.py tests/test_taxonomy.py tests/test_stage_events.py -v
```

### Exit criteria (spec §24 Phase 8)

- [ ] No cluster presented as established without sufficient independent evidence.
- [ ] Cluster labels exist only in `cluster_assignments`.
- [ ] A taxonomy revision costs an assignment pass and no re-extraction.
- [ ] Core and adjacent cases analysable separately.
- [ ] The funnel is computed per stage from stage events and reconciles with the manifest.
- [ ] Duplicate-thread inflation controlled and visible.
- [ ] Every displayed metric reproducible from committed processed data.

### Prompt to paste

```text
Implement only Phase 8 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 8 and ARCHITECTURE.md sections 12 and 13.

Build taxonomy candidate generation, versioned assignment writing ClusterAssignment
rows, the computed "established" flag, and the four analysis modules: funnel, memory
map, journeys, opportunities.

Hard requirements, each needing a test:
- The funnel is computed per stage from stage_events. One document must appear at every
  stage it reached, including simultaneously as a duplicate and as a valid extraction.
  There is no lifecycle column to group by.
- Pending-review duplicate links are a separate funnel line and are excluded from the
  duplicate count.
- The memory map reads *_observation values from the schema. not_stated and
  explicitly_none stay distinct. No analysis module may define a status value that is
  not a schema enum member.
- Cluster labels exist only in cluster_assignments. Nothing reads a cluster from a case.
- Publishing a new taxonomy version must cause zero extraction cache misses. Assert it.
- A cluster with fewer than 5 independent documents or fewer than 2 source types is not
  established, and the flag is computed, never authored.
- Severity means carry their own denominator.
- Records with a non-ok technical_state are excluded from metrics, with the count shown.

The composite opportunity score is stretch scope. Do not build it in this phase.
Do not implement retrieval or Streamlit.

Report: files created, the test command and full output, the funnel output, and the
cluster table with established flags and their evidence counts.
```

---

## Phase 9 — Evidence retrieval and grounded answering

**Goal:** a lexical retrieval baseline that returns nothing for unrelated questions, and
optional synthesis that can only cite records it actually retrieved.

**Owner:** build. **Scope:** the deterministic evidence panel is MVP; **grounded synthesis is
stretch** (ADR-27). Build ranking, thresholding, and the panel first, and confirm the panel is
complete on its own before writing `answer.py` — spec §22.3 requires the panel to render
before synthesis is attempted, so it must not depend on it.

### Work items

- [ ] `src/retrieve/rank.py` — BM25 over `problem_summary`, controlled labels, evidence
      quotes, and the `raw_text_audit` excerpt; stopword removal; simple variant handling;
      index cached under `data/interim/index/` keyed by dataset version.
- [ ] Structured filters applied **before** ranking: scope, source, asset type, date.
- [ ] Configurable `min_score`: below it, return an empty result and an honest refusal.
      This is the prototype's clearest retrieval defect — `sorted(...)[:k]` always returns k
      records regardless of quality (`ARCHITECTURE.md` §20.2 item 8).
- [ ] Per-source diversity cap within top-k.
- [ ] `src/retrieve/citations.py` — parse `[case_id]` tokens, validate against the retrieved
      set, one repair attempt, then reject. The evidence panel shows **cited ∩ retrieved**,
      not the retrieved list (item 9).
- [ ] `src/retrieve/answer.py` — synthesis through the gateway; prompt receives only
      retrieved records and their spans; answer cache keyed on
      `(question_normalized, dataset_version, model, prompt_version)`.
- [ ] Add `rank-bm25>=0.2.2,<1`.

### Tests (spec §25 "Retrieval and synthesis")

- [ ] `tests/test_retrieval.py` — a relevant question ranks the expected evidence; an
      unrelated question returns **no** evidence; the minimum score is enforced; an invalid
      model citation is rejected; displayed evidence equals actually-cited evidence; a missing
      API key falls back without crashing.
- [ ] Source diversity cap respected in top-k.

### Commands

```bash
python -c "from src.retrieve.rank import search; print(len(search('how do people find screenshots')))"
python -c "from src.retrieve.rank import search; print(search('best pizza in Naples'))"   # expect []
pytest tests/test_retrieval.py -v
```

### Exit criteria (spec §24 Phase 9)

- [ ] An unrelated query returns no evidence rather than arbitrary records.
- [ ] Only cited records appear under "Evidence used."
- [ ] AI failure falls back to deterministic evidence.
- [ ] The evidence panel is complete and useful with synthesis absent entirely.
- [ ] Retrieval and citation tests pass.

### Prompt to paste

```text
Implement only Phase 9 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 9 and ARCHITECTURE.md section 14.

Build src/retrieve/rank.py with structured filters applied before BM25 ranking, a
configurable min_score, a per-source diversity cap, and a cached index keyed by dataset
version. Then src/retrieve/citations.py for parsing and validating [case_id] tokens.

Hard requirements, each needing a test:
- Below min_score the system returns an empty result and an honest refusal. It must
  never return k records regardless of quality.
- Structured filters run before ranking, not after.
- The evidence panel is the intersection of cited and retrieved, not the retrieved list.
- An unsupported citation triggers one repair attempt, then rejection.
- The retrieval path must work with no API key and with synthesis absent.
- Index over problem_summary, controlled labels, evidence quotes, and the excerpt.
  No embeddings in this phase.

Grounded synthesis (src/retrieve/answer.py) is stretch scope. Build it only after the
deterministic panel is green, and keep the panel independent of it.

Report: files created, the test command and full output, and the results of a relevant
query and an unrelated query.
```

---

## Phase 10 — Evaluator-facing Streamlit application

**Goal:** the seven surfaces from spec Section 23, with the first six working without any
API key.

**Owner:** build.

### Work items

- [ ] `src/store/export.py` + `scripts/build_exports.py` — validated dataset export with a
      dataset version and canonical content hash, emitting `PublicExportRecord` rows under the
      **public-export profile** in spec §12.1 (ADR-23):
      - minimum redacted excerpt containing every validated span for the record, plus the
        configured context window (default ±160 characters);
      - offsets rebased to the excerpt, with `excerpt_start_char` recorded;
      - `excerpt_is_full_text` true only where a source's redistribution terms permit it, as
        recorded per source in `DECISIONS.md`;
      - `author_key` as a truncated hash; no usernames, no credentials, no unredacted PII;
      - unredacted `raw_text` never written to `data/exports/`.
- [ ] `app.py` reading committed exports only. It imports from `analyze`, `retrieve`, and
      `store.export` — never from `collect`, `relevance`, `extract`, or a provider SDK
      (`ARCHITECTURE.md` §17.1).
- [ ] Surface 1 — Overview: strategic question, corpus date range, source mix, processing
      funnel, direct-user versus contextual split, key limitations.
- [ ] Surface 2 — Opportunity comparison: ranked clusters, transparent components,
      source-balanced toggle, core/adjacent toggle, filters by asset type, cue, failure mode,
      source, and date. Provisional clusters visually distinct from established ones.
- [ ] Surface 3 — Memory map: cues × forgotten, cue combinations, unknown values visible.
- [ ] Surface 4 — Retrieval journeys: strategy → response → workaround → outcome → impact.
- [ ] Surface 5 — Evidence browser: excerpt with **offset-based** span highlighting, source
      link, scope decision, extracted dimensions, model and prompt version, review status,
      dataset download. Rendering must not re-search for the quote — that would be a second,
      unvalidated matching implementation.
- [ ] Surface 6 — Quality report: gold-set composition **with the dev/holdout split labelled on
      every number**, prefilter recall, end-to-end relevance precision/recall/F1, scalar accuracy
      and multi-label micro/macro metrics reported separately, unsupported inference rate,
      observation-status distribution per field, inter-reviewer agreement before adjudication,
      technical-failure counts, span validation rate, failure and review rates, duplicate rate by
      kind and review state including pending, limitations.
- [ ] Surface 7 — Ask the evidence: evidence-first, validated citations, honest
      insufficient-evidence responses, per-session question cap. **Grounded synthesis is stretch
      scope** — the surface must be complete and useful with synthesis absent.
- [ ] Every empty state from `ARCHITECTURE.md` §18 designed explicitly: no export, empty
      dataset, empty filter result, no established clusters, no gold set.
- [ ] Caching keyed on dataset version.
- [ ] Add `streamlit>=1.37,<2`.

### Tests (spec §25 "Application")

- [ ] `tests/test_app.py` using `streamlit.testing.v1.AppTest` — clean launch; launch with
      the environment stripped of secrets; empty dataset and empty filter states; download
      content matches the displayed dataset version; critical navigation and filtering.
- [ ] `tests/test_export_profile.py` — scan the **generated** export for username patterns, key
      patterns, emails, and phone numbers; assert no excerpt exceeds the configured window
      without `excerpt_is_full_text`; assert excerpt-relative offsets highlight correctly and map
      back to document offsets; assert `data/exports/` contains no unredacted `raw_text`.
- [ ] `tests/test_architecture.py` — `app.py` has no code path to `data/raw/`.

### Commands

```bash
python scripts/build_exports.py --tag v1
streamlit run app.py
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY streamlit run app.py    # six surfaces must work
pytest tests/test_app.py -v
```

### Exit criteria (spec §24 Phase 10)

- [ ] App launches from a clean environment.
- [ ] Deterministic views work without secrets — demonstrated with the key-stripped command.
- [ ] Missing AI keys do not crash the app.
- [ ] Empty filters and empty datasets handled.
- [ ] Source links and downloads work.
- [ ] The public export satisfies every rule in spec §12.1, verified against the generated
      artifact rather than by reading the exporter.
- [ ] The quality report labels every number with the split it came from.
- [ ] App tests cover critical paths.

### Prompt to paste

```text
Implement only Phase 10 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 10 and ARCHITECTURE.md sections 15 and 18.

Build the public export profile from spec Section 12.1, then app.py with the surfaces
from Section 23, reading committed exports only.

Hard requirements, each needing a test:
- The public export carries the minimum redacted excerpt containing the validated
  evidence spans plus the configured context window, with offsets rebased to the excerpt
  and excerpt_start_char recorded. Full text only where excerpt_is_full_text is true.
- No usernames, credentials, unredacted PII, emails, or phone numbers in the export.
  Test this against the generated bytes, not the exporter source.
- Unredacted raw_text never reaches data/exports/, and app.py has no code path to
  data/raw/.
- Evidence highlighting uses stored offsets. It must not re-search for the quote at
  render time.
- Every quality-report number is labelled with the split it came from.
- The first six surfaces work with the environment stripped of all API keys.
- Every empty state from ARCHITECTURE.md section 18 is designed explicitly.

Grounded synthesis on the Ask surface is stretch scope. The surface must be complete
with synthesis absent.

Report: files created, the test command and full output, the key-stripped launch command
and its result, and the export-profile scan result.
```

---

## Phase 11 — Deployment and submission QA

**Goal:** a public link an evaluator opens with no setup, and numbers that agree everywhere.

**Owner:** build and research jointly.

### Work items

- [ ] Public GitHub repository; verify no secrets and no plaintext author identities are
      committed (`git log -p` scan for key patterns, not just a glance at HEAD).
- [ ] Commit the public-profile export plus its run manifest. Unredacted raw data stays local.
- [ ] Deploy to Streamlit Community Cloud; add the API key as a deployment secret only.
- [ ] `README.md` — setup, methodology, corpus composition, limitations, and how to rebuild the
      analysis. The prototype's README is a good structural model; the methodology and
      limitations sections are the substantive additions. Two statements are required verbatim in
      substance (spec §12.1):
      - **analysis reproduction is supported** — given the committed export and cached
        responses, a third party reproduces identical canonical content hashes with no API key;
      - **source re-collection is not supported and not possible** — posts get edited and
        deleted, feeds return different windows, and some sources need credentials that cannot be
        shared. Claiming end-to-end reproducibility would be the same category of error as
        claiming corpus frequency represents all users.
- [ ] Record per-source redistribution terms, settling where `excerpt_is_full_text` may be true
      (ADR-23 amendment).
- [ ] State the MVP/stretch outcome: which stretch items were built and which were cut (ADR-27).
- [ ] Regenerate `explorer.html` from the committed export as the zero-dependency backup
      evidence snapshot — **stretch scope** (ADR-9, ADR-27, `ARCHITECTURE.md` §15).
- [ ] Verify every `source_url` resolves; record dead links rather than deleting the evidence.
- [ ] One-slide explanation for the final deck.
- [ ] Screenshots of all seven surfaces.
- [ ] **Reconciliation pass:** the funnel counts in the manifest, the app, the README, and
      the deck must be the same numbers. The app reads its funnel from the manifest
      (`ARCHITECTURE.md` §16.2), so any disagreement means a stale export — rebuild rather
      than hand-edit.
- [ ] Final claims audit: every statement limited to the analyzed corpus, using the
      Section 21.6 phrasing. Search the README and app copy for "of users", "most users",
      and "causes".

### Commands

```bash
python scripts/build_exports.py --tag submission
python scripts/audit_sources.py --check-links
pytest -q                                     # full suite, green
git ls-files | grep -Ei "\.env$|secrets" || echo "clean"
```

### Exit criteria (spec §24 Phase 11)

- [ ] Public link opens without login.
- [ ] No secrets committed.
- [ ] All deterministic features work without evaluator setup.
- [ ] Dataset, app, README, and methodology numbers agree.
- [ ] `rebuild` reproduces identical canonical content hashes; manifest volatility does not fail
      the check (ADR-26).
- [ ] Links verified.
- [ ] Claims limited to the analyzed corpus, and the analysis-reproduction versus
      source-re-collection distinction is stated in the README.
- [ ] Every source mechanism described as verified links primary documentation in
      `DECISIONS.md`, with its verification status stated.

### Prompt to paste

```text
Implement only Phase 11 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 11.

Complete deployment and submission QA: public repository, committed public-profile
export plus run manifest, Streamlit Cloud deployment with the key as a deployment secret
only, README with setup and methodology, link verification, screenshots, and the
reconciliation pass.

Hard requirements:
- Only the public-profile export is committed. data/raw/ stays local and gitignored.
  Scan git history, not just HEAD, for key and secret patterns.
- Run main.py rebuild and show that canonical content hashes match. A manifest differing
  only in run ID, timestamps, durations, and token counts must still pass.
- The README must state plainly that analysis reproduction is supported and that source
  re-collection is neither supported nor possible, with the reasons.
- The README must state which stretch items were built and which were cut.
- Every source mechanism described as verified must link primary vendor documentation in
  DECISIONS.md, with its verification status: permitted and exercised, permitted but
  unexercised, undocumented, or closed.
- Reconcile the funnel counts across manifest, app, README, and deck. A disagreement
  means a stale export: rebuild rather than hand-edit.
- Audit all copy for "of users", "most users", and "causes".

Regenerating explorer.html is stretch scope.

Report: the public URL, the full test suite output, the rebuild hash comparison, the
reconciliation table, the secret-scan result, and the list of stretch items built versus
cut.
```

---

## Risk register

Ordered by expected damage, with the mitigation built into a phase rather than left as
vigilance.

| # | Risk | Signal | Mitigation | Phase |
|---|---|---|---|---|
| R1 | Prefilter drops real cases; recall loss is invisible | prefilter recall below 0.90 | store drop reasons; gold `prefilter_should_pass` labels; a hard recall gate, not just a precision gate | 4, 6 |
| R2 | Not enough genuine direct-user documents; corpus fills with editorial | direct-user share below ~60% | tier at collection; Reddit and Help Community first; track the split in `audit_sources.py` | 2, 7 |
| R3 | Model paraphrases into `quote` and it slips through | span validation failures cluster | four-step ladder with hard rejection; validation is a gate, not a warning | 1, 5 |
| R4 | Taxonomy defined too early, findings become self-fulfilling | cluster names appear before Phase 8 | `taxonomy.yaml` ships empty; `RetrievalCase` has no cluster field to fill (ADR-19); cluster labels exist only in `ClusterAssignment`; I10 | 5, 8 |
| R5 | One source dominates and the ranking reflects the platform, not the problem | any source > 40% of included cases | concentration check plus non-dismissible disclosure and balanced view | 7, 8 |
| R6 | LLM spend runs past budget | token accounting in the manifest | content-addressed cache, `--limit`, `--dry-run` first, cheap model for prefilter-adjacent work | 4 |
| R7 | A collector is blocked mid-scale and the corpus is lopsided | collector failures in the manifest | manual CSV fallback; stop-and-record rather than retry-forever | 7 |
| R8 | Severity mostly null, so severity-based comparison is thin | severity non-null rate below ~40% | expected and acceptable — report the denominator; never infer severity to fill the column | 5, 8 |
| R9 | Human research slips and Phases 6–8 compress | pilot corpus incomplete at Phase 3 | start collection in Phase 0; the template is the only dependency | 0, 2 |
| R10 | Late-breaking scope creep toward solution design | designs appear in the app | spec §7 non-goals; Part 1 ends at opportunity comparison | all |
| R11 | Dedupe collapses two genuine users into one; the loss is invisible and irreversible | duplicate rate rising while unique authors fall | `dedupe_min_tokens`, cross-author guard, review band; every automatic decision has a safety precondition (ADR-21) | 3 |
| R12 | Case count misses the old 15–25 band and prompts get loosened to reach it | evidence rules relaxing between prompt versions | M1 reports and diagnoses the count per stage instead of targeting it (ADR-29) | 5 |
| R13 | A stretch item consumes the time an MVP item needed | Ask synthesis or a store collector in progress with the quality report unbuilt | explicit MVP/stretch split; stretch may never be an MVP dependency (ADR-27) | all |
| R14 | An experimental source is treated as low risk because a library makes it easy | a scraper appears for a source with no documented mechanism | feasibility tiers; no collector without linked primary documentation; the two store sources are recorded as **closed** rather than pending, so there is no backlog item inviting a scraper (ADR-22) | 7 |
| R18 | A working URL or a permissive `robots.txt` is mistaken for permission | a collector justified by "the endpoint responds" or "robots.txt allows it" | §11.4 rule 7 — the two checks are independent and the stricter governs; the support forum is the worked example (ADR-22) | 7 |
| R15 | Full post text gets committed for convenience, breaching §12 | excerpt length growing, or `excerpt_is_full_text` defaulting true | excerpt profile enforced by a test over the generated artifact (ADR-23) | 10 |
| R16 | A provider outage is silently recorded as `out_of_scope`, deflating relevance | `out_of_scope` count spiking during a run with API errors | `DecisionTechnicalState` separate from scope, on its own funnel line (ADR-17) | 4 |
| R17 | Holdout split gets read during prompt iteration | error-analysis exports containing holdout documents | the evaluation script refuses to emit error analysis for the holdout split (ADR-25) | 6 |

R8 deserves emphasis because it will look like a defect and is not one: spec Section 18 says
null severity is better than unsupported precision. A corpus where most cases have null
severity is a corpus that obeyed the rubric.

---

## Tracking artifacts

Updated as part of each phase's definition of done, not retroactively.

**`STATUS.md`** — rewritten at each phase boundary:

```markdown
## Status
Completed phase: 3 — normalization and deduplication
Current phase:   4 — relevance classification
Tests:           68 passing, 0 failing
Corpus:          41 collected documents, 3 source types, 4 duplicate links, 2 pending review
Blockers:        none — ADR-21 calibration done, amendment recorded
Next command:    python main.py run --stages relevance --limit 5 --dry-run
```

**`DECISIONS.md`** — one entry per decision: date, decision, rationale, alternative rejected,
spec section affected. Seed with ADR-1…29 from `ARCHITECTURE.md` §22 in Phase 0, carrying the
superseded markers. Every prompt version bump, threshold change, taxonomy version, source
verification status, and redistribution-terms finding gets an entry.

**`CHANGELOG.md`** — dated material implementation changes.

---

## Definition-of-Done traceability

Spec Section 27's checklist mapped to the phase that satisfies it, so nothing is discovered
missing at submission time.

| Definition-of-Done item | Satisfied in |
|---|---|
| Every MVP capability built; stretch items marked included or cut | 0–11, stated in 11 |
| ≥ 300 collected documents across ≥ 4 source types | 2 (manual baseline), 7 |
| Per-stage funnel from stage events, with duplicate, pending-review, technical-failure, core, adjacent, excluded, reviewed, included counted separately | 8 (funnel), 11 (reconciliation) |
| Every processed record validates against the schema | 1, 5 |
| Every evidence quote verified against raw text | 1, 5 |
| Every evidence-required field has field-level evidence or a permitting observation status | 1, 5 |
| Direct-user and contextual sources separated | 2 (tiering), 8 (views) |
| 75–100 document gold set, document and case labels separate, dev/holdout splits | 6 |
| Prefilter recall ≥ 0.90, relevance precision ≥ 0.85, relevance recall ≥ 0.80 on holdout | 6 |
| Scalar accuracy, multi-label micro/macro metrics, unsupported inference rate reported | 6, 10 (quality surface) |
| Inter-reviewer agreement reported before adjudication | 6, 10 |
| Taxonomy derived and refined after pilot review, existing only in `cluster_assignments` | 8 |
| Opportunity areas supported by independent cases across multiple source types | 8 |
| Duplicate and source concentration controlled | 3, 8 |
| Evaluator can inspect evidence excerpts and open source links | 10 |
| Deterministic app works without an API key | 10 |
| Public export satisfies spec §12.1, verified against the artifact | 10 |
| Rebuild reproduces identical canonical content hashes | 3, 11 |
| Unrelated Ask queries return no evidence or an honest refusal | 9 |
| Generative answers cite only validated record IDs (where synthesis is built) | 9 |
| Public evaluator link works without setup | 11 |
| Repository has README, methodology, tests, config examples, reproducible analysis build | 11 |
| No secrets or plaintext author identities committed | 0, 2, 11 |
| Claims limited to the analyzed corpus; analysis reproduction versus re-collection stated | 8, 11 |
| Every "verified" source mechanism links primary documentation | 7, 11 |

---

## Standing constraints

These apply in every phase and are the ones most likely to erode under time pressure
(spec §29):

1. Work only the requested phase. Show a plan before editing.
2. Never state that something works without showing the command and its output.
3. Never insert fabricated research data to make the interface look complete.
4. Never silently relax validation to make model output pass.
5. When evidence is missing, leave the value null or empty and set the observation status.
   Never invent an `unknown` placeholder.
6. Never hard-code credentials, model names, local paths, dates, or opportunity conclusions.
7. Synthetic fixtures stay marked `synthetic_test` and excluded from every research output.
8. Update `STATUS.md` at each phase boundary; record deviations in `DECISIONS.md`.
9. Never tune a prompt to move a count into a desired range. Report the count and diagnose the
   stage that explains it.
10. Never start a stretch item while an MVP item is unfinished.
11. Never describe a source mechanism as verified without linking its primary documentation in
    `DECISIONS.md`.
12. Never read the holdout gold split for anything except a final reported measurement.
13. Never write a contract field that a later stage produces.
