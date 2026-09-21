# Changelog

Material implementation changes by date (spec Section 1). Scope and schema
decisions live in `DECISIONS.md`; this file records what was built.

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
  record), and the `all_evidence_spans` union.
- **`tests/synthetic.py`** — fixture builders, every one of which stamps
  `evidence_tier = synthetic_test`.
- **296 tests** across `test_models.py`, `test_evidence.py`,
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
  have written.

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
retrieval, or Streamlit app. `src/extract/` holds the validator only — the
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
