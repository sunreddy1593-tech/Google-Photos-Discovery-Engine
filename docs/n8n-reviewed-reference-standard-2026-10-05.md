# Human-reviewed n8n reference and the automated comparison (2026-10-05)

## What was done

Sunayana stated in the implementation conversation of 2026-10-05 that she had
personally reviewed the existing 48 n8n threads in detail, including their
relevance, classifications, summaries and evidence quotes, and asked for that
review to be recorded as the approval basis for those exact records. Future
records are classified by the existing stages and assessed against that
standard automatically; they appear in a separately labelled view and do not
inherit human approval.

No n8n workflow, webhook, spreadsheet, integration module, credential or
endpoint was modified, invoked or requested. No collection or model call was
made. All inputs were already-saved local files.

## Reference artifact

Path: `data/exports/reference/n8n-reviewed-reference-01/` (`reference.json`,
`records.jsonl`, `APPROVAL.md`). Version `n8n-reviewed-reference/01`,
registered as `REFERENCE_STANDARD_VERSION` in `src/core/versions.py` and
recorded in scheduler pins.

Inputs and hashes:

- Primary: `n8n/discovery_sheet_template - insights.csv`, sha256
  `22f1463584509c5590985129c4271757954338cfd98f9e2e83f2f2db94f2f848`. 48 rows,
  48 distinct thread URLs, scraped 2026-10-03T13:46Z to 14:32Z.
- Cross-check: `data/insights_seed.csv`, sha256
  `24797e10de8937b71311aaf6bdb0aff0dcf5ed3e4acffcb59d543a35e05d18fc`. 51 rows.
  All 48 reviewed rows are present and identical apart from TRUE/FALSE casing.
  Threads `106429666`, `471259711` and `471279651` (scraped 2026-10-04) are
  not covered by the review and are not in the reference.
- `records.jsonl` sha256
  `7d8ddc7ee0c9757d6af7c5c55523f95961af6b82d89b1dad654670deb1e21e29`.

Counts: 48 records, exactly the number the owner named. 23 marked retrieval
problem, 25 not. 22 records carry a key quote, 26 do not. 47 carry a summary,
one does not. Every load recomputes the record hashes; a changed byte makes
the reference unavailable rather than silently different. The builder refuses
to overwrite an existing folder and refuses duplicate threads.

The review date was not stated and is recorded as `not stated by the owner`.
The artifact `created_at` is the build time, not the review time.

## Field mapping (n8n sheet to application contracts)

| n8n field | application field | status |
| --- | --- | --- |
| `source` | `source_platform` (`google_support`) | supported |
| `url` | `source_url`, `source_url_key`, `source_item_id`, `expected_doc_id` | supported |
| `title` | `title` | supported |
| `is_retrieval_problem` | `reviewed_relevance` (binary) | supported |
| `photo_type` | `target_asset_type` (only `screenshot`) | partial |
| `intent` | none | preserved as text |
| `cues_remembered` | `remembered_cues` | unsupported, preserved as text |
| `cues_forgotten` | `forgotten_information` | unsupported, preserved as text |
| `query_tried` | `exact_query`, `query_strategies` | unsupported, preserved as text |
| `failure_stage` | none | preserved as text |
| `workaround` | `workarounds` | unsupported, preserved as text |
| `key_quote` | evidence quote | supported, not verifiable |
| `summary` | `problem_summary` | supported as paraphrase |
| `scraped_at` | `collected_at` | supported |

The reviewed flag is binary. Core incomplete recall and adjacent known-item
retrieval are not inferred from it; in the other direction, both application
classes collapse onto `retrieval_problem` only for the mapped equivalent shown
beside each automated case. Unavailable on every record: original post text,
author, published date, quote offsets, severity, impact signals, scope class,
reason code, replies, review date. None is inferred.

Quote verification: the export carries no original post text, so 0 of 22
quotes are verified against source text here. `quote_verification_unavailable`
is 48. A weak consistency check against the saved title is recorded (18 quotes
equal the title, 20 fall within it) and is labelled as not verification.

## Automated classification against the standard

`src/export/reference_standard.py` assesses prepared public cards, which have
already passed the existing evidence gate, privacy scan and holdout exclusion.
It makes no model call and never sets semantic approval. Resemblance to a
reference record is not consulted; relevance stays with the classifier.

Eligibility rules (recorded in each snapshot):

1. Extraction case that passed the automatic evidence gate.
2. Scope class core or adjacent; the two stay in separate buckets, and
   out-of-scope decisions are counted separately.
3. Every evidence quote equals the exported excerpt at its stored offsets and
   the offsets reconcile with document coordinates.
4. No rejected, invented, abbreviated or spliced model text attached.
5. A stated `retrieval_trigger` has its own span and no recorded objection.
6. Stated impact signals or severity have their own spans and no objection.
7. A `problem_summary` has supporting evidence and no objection.
8. No recorded semantic finding stands against the case.
9. Public source link present.
10. The document is not one of the human-reviewed reference records
    (matched by expected `doc_id` or URL); those stay in the human view.
11. A case id already assessed in the same snapshot is skipped.
12. Passing these checks is not human approval.

Verdicts: `eligible`, `flagged` (valid but at least one objection),
`unverifiable` (no exported source context, so quotes cannot be checked),
`failed_or_incomplete` (failed or empty attempts and invalid cases),
`excluded_reference_overlap`. Each case records reference version, relevance
and extraction prompt versions, schema version, model, dataset and run id,
an `assessment_identity` hash over those values, the checks, and
`semantically_approved: false`, `human_reviewed: false`. Where an export
recorded an owner approval elsewhere, that is kept as
`recorded_semantic_approval_elsewhere` and is not treated as approval by this
layer.

Prompts, schema, model, temperature and token settings are unchanged
(relevance/v5, extract/v2, schema 1.0.0). The reference version does not enter
the provider cache key because the model request is unchanged; it enters the
assessment identity and the Streamlit cache key. A later prompt change would
be a new assessment identity.

## Snapshot build and publication

`src/export/reference_standard_build.py` reads the prepared public export
(`data/exports/submission/demo-2026-10-04-03`, same precedence as the app) and
any saved scheduled sub-batch under `data/interim/scheduled-runs/`. Sub-batches
are exported through the existing `build_submission` builder with
`split_policy: outside_frozen_split`, so holdout documents and frozen-split
overlaps are excluded by the same code path. The snapshot is published with
`publish_snapshot` to `data/exports/public/reference-standard-snapshot/`
(gitignored, like the scheduled snapshot): one version folder, then an atomic
pointer replace. An identical snapshot is left unchanged. A reference that
fails to verify, or a payload that fails the privacy scan, publishes nothing
and leaves the previous pointer current.

The scheduler calls `refresh_after_scheduled_run` after its own snapshot is
published. The call is best effort: errors are recorded on the report as
`automated_comparison` and never change the run status. No request, model
call or budget reservation is involved.

Offline scripts: `scripts/build_reviewed_reference.py` (one-time artifact
build) and `scripts/build_reference_standard_snapshot.py` (snapshot rebuild).

Snapshot `d92016973f6e0260` published 2026-10-05 from saved exports only:
16 cases assessed, 7 automatically valid, 5 eligible (3 core, 2 adjacent; all
five are development-quality-v6 cases that also carry an owner approval
recorded in that export), 2 flagged (`google_support-d7f386f347b7#c01` and
`google_support-e1e5277da7e8#c01`, unsupported retrieval trigger plus summary
or impact objections), 9 failed or incomplete, 0 unverifiable, 0 reference
overlap, 0 duplicates. Relevance decisions across those exports: 14 core, 13
adjacent, 37 out of scope, 1 invalid. No scheduled sub-batch has reached the
relevance stage yet (the 08:00 run collected 0 new documents), so no
scheduled dataset is in this snapshot.

## Streamlit

The "Reference standard" section has two tabs: "Human-reviewed reference" and
"Automatically classified using the human-reviewed standard". The automated
tab carries the note that results passed automatic checks and were not
individually reviewed, shows separate counts (human-reviewed records,
automatically valid, eligible, flagged, failed or incomplete, unverifiable,
reference overlap excluded, duplicates skipped), core and adjacent buckets
over the existing comparison dimensions, mapped reference equivalents, source
links, highlighted evidence excerpts, per-case versions and reasons, and the
eligibility rules. The cache key includes the snapshot version and the
reference version; the section uses the same fragment refresh interval and a
Refresh button (`refresh_reference_standard`). No accuracy is claimed.
Credentials, raw private files, author identifiers and collection or model
controls are not on the page. The cloud package allowlist now includes the
reader modules and the reference artifact (and the snapshot when present).

## Verification

- `tests/test_reference_standard.py`: 29 tests covering record identity and
  refusal to overwrite, tamper detection, count discrepancy and duplicate
  refusal, explicit mappings and unknowns, the saved 48-record artifact
  verifying against its inputs, assessment identity changing with reference
  and prompt versions, eligible cases entering without human approval,
  recorded approval not inherited, each unsupported field and invalid evidence
  condition flagged, altered quotes and bad offsets flagged, reference overlap
  exclusion, scope separation, duplicate skipping, empty states, atomic
  publication with version awareness and failure keeping the previous
  snapshot, scheduled sub-batch discovery through the export builder with
  holdout text absent, scheduler budgets unchanged and no second model review
  call, best-effort refresh that cannot fail a run, no network or integration
  imports in the new modules, and the Streamlit section with both labels,
  counts, empty state, versioned reload and Refresh.
- Focused run: 313 passed, 5 skipped across the new file and the architecture,
  scheduler, app, export and reference-demo suites.
- Full suite: 1302 passed, 5 skipped, 0 failed.
- `git diff --check`: clean apart from line-ending warnings.
- No file under `n8n/`, `community_insights.py`, or any integration module
  was modified. No n8n, webhook or Google Sheets request was made.

## Limitations

- The reference carries sheet text only; quotes are not verified against
  original posts and offsets do not exist for them.
- The reviewed binary flag does not separate core from adjacent.
- The automated layer can only check what the public export carries. A case
  without exported source context is `unverifiable`, not eligible.
- Eligibility is a deterministic evidence check, not a measurement of
  agreement with the reference. No accuracy figure is produced.
- The quality freeze hashes `src/**/*.py`, so the pre-existing
  `check_freeze` input-hash mismatch after code changes still applies.
