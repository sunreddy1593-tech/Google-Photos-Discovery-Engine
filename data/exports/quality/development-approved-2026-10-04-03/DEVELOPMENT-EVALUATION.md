# Development evaluation — 2026-10-04

Development evaluation is complete for the ten approved reference documents.
The five numeric thresholds are met on this diagnostic sample. The final quality
gate remains pending: the owner chose to keep holdout locked and finish development
first. This report does not certify extraction quality or complete Phase 6.
M1's separately audited technical milestone remains complete.

## Inputs and preservation

References: `data/annotation/dev-starter-2026-10-03/sunayana-reviewed-01/development-reference-01/`
(10 documents, 6 cases). Human reviewer: Sunayana, with AI drafting disclosed.
There was no independent second coder, blinded coding or adjudication; agreement
is unavailable. The family-album core classification remains a disclosed
reviewer-directed scope exception, rather than a changed scope definition.

Saved extraction: `data/interim/phase5/development-corpus/3dc346ec030a/`.
Saved relevance: `data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl`.
Prefilter routing comes from `data/interim/phase4/stage_events.jsonl`.
Only the ten approved gold-dev source packets were loaded for source checks.
The 25 reserved gold-holdout sources and 15 original Phase 4 holdout sources
were not opened. No provider request was made.

Official `data/gold/documents.jsonl` and `cases.jsonl` remain empty; the existing
official dev/holdout reports remain pending and unchanged. Historical runs,
caches, approved labels, prompts, schemas and splits were not rewritten.
All 21 M1 input hashes, 98 protected annotation hashes and 26 final evaluation
input/code hashes were verified unchanged. The current report binds those 26
inputs under `saved_inputs.input_sha256`.

## Numeric results and denominators

- Schema validation: 1.00, threshold 1.00. Denominator: 12 accepted model records
  (10 technically ok relevance decisions plus 2 retained extraction cases).
  Failed extraction attempts do not become schema-valid records in this rate.
- Exact-source span validation: 1.00, threshold 1.00. Includes accepted relevance
  spans and the complete inline/external evidence union for the two retained cases.
  All supplied reference quotes also validate; gold quote failures: 0.
- Prefilter recall: 1.00, threshold 0.90, against the independently recorded
  `prefilter_should_pass` flag, rather than the model's relevance class.
- End-to-end relevance precision: 6/7 = 0.8571, threshold 0.85.
- End-to-end relevance recall: 6/6 = 1.00, threshold 0.80.

All ten documents have saved relevance predictions; non-ok relevance exclusions: 0.
Three-way scope accuracy is 7/10 = 0.70. `disagreements.csv` retains the three
development disagreements and their permitted source text: family album
(reference core / model adjacent, disclosed exception), Memories
(reference adjacent / model core), and the vague YouTube loss comment
(reference out of scope / model core).

## Extraction coverage and failures

Seven documents were extraction-eligible. Two produced retained cases, three
produced accepted empty responses, and two failed. Three other documents were
skipped as out of scope. Failure rate: 2/7 = 28.6%.

Only 2/6 reference cases matched accepted model cases (33.3% coverage).
There are four unmatched reference cases and no unmatched accepted model cases.
Field scores below are conditional on those two matches; they do not imply that
the four missing cases were extracted correctly.

- `google_support-2a080da4b930`: accepted empty response; missing the approved
  family-album reference episode. The core scope exception remains disclosed.
- `google_support-5b2ec98df32b`: accepted empty response; missing the approved
  Memories navigation episode.
- `reddit-87311c2633df`: extraction event failed with
  `evidence_validation_failed`; no accepted case. The approved poodle search
  episode remains unmatched.
- `reddit-bde62ddef9b5`: extraction event failed with
  `evidence_validation_failed`; no accepted case. The approved successful
  sleeping-video search remains unmatched.
- `youtube-17fd27447275`: accepted empty response agrees with expected case
  count 0, although its model relevance class is a false positive.

The two retained matches are `reddit-0d477b54fb9b#c01` and
`reddit-c2c00b25a88b#c01`. No failed model output was repaired or substituted.
These failure records establish local validation rejection; they do not establish
provider token exhaustion, unrecorded usage or billing.

## Field disagreement and semantic limits

Outcome value and observation accuracy are both 0.00 on the two matched cases.
Known-item status, asset type, severity and reformulation-count scalar accuracy
are 1.00 on those matches. Micro F1: subjects 1.00, forgotten information 1.00,
remembered cues 0.40, query strategies 0.00, impact signals 0.00,
system responses 0.6667 and workarounds 0.6667. Micro and macro remain separate
in `report.json`.

The unsupported-inference diagnostic is 7/17 = 41.2% of assessed non-empty
field instances. It flags disagreement with reference values or missing/invalid
structural support. This is not a fresh independent semantic adjudication.
Retrieval trigger, outcome, query strategies, impact signals and query paraphrase
have disagreement rate 1.00 for their assessed instances; remembered cues is 0.50.
Omitted expected labels affect recall, rather than being counted as unsupported
predicted labels. `problem_summary` is unassessed (null): the current gold contract
has no reference summary value. A matching verbatim span alone does not establish
that a summary's entire meaning is supported.

The existing owner approval ledger and open browser findings are separate from
this comparison. This evaluation does not clear a finding, rescind an approval,
alter a label or confer conclusion approval on any saved case.

## Corrective work before freezing development

1. Review the four omitted/rejected reference episodes against their retained
   development diagnostics. Preserve empty responses and rejected quotations;
   propose fixes separately, without weakening the evidence gate.
2. Trace the two matched cases' field disagreements back to their reference
   values and source spans. Review retrieval trigger as the stated reason the
   item was needed, unsupported impact/severity, every summary claim, and invented
   or spliced quotes. Record any proposed corrections separately with provenance.
3. If a prompt change is then authorized, version it and add offline fixtures for
   the confirmed failure categories before any bounded paid verification. No
   prompt/schema change or paid retry is authorized by this evaluation.
4. Freeze a documented development configuration and limitations before a later,
   separately authorized holdout-labeling/evaluation step. Final quality
   certification remains pending while holdout is locked and unlabeled.

## Implemented evaluator fixes and verification

The CLI previously loaded labels without saved model predictions. Its new optional
four-input development adapter now feeds the existing evaluator real saved
predictions, cases, recorded routing and approved dev text. It reuses current
contracts and field gates, refuses holdout packets and occupied output, reports
missing cases and failures, and preserves pending status when predictions are absent.

Scoring now compares structured gold multi-label entries by their label values.
It also distinguishes omitted expected labels from unsupported predicted labels,
and leaves fields without an available reference value unassessed rather than
inventing semantic agreement. Evaluation version: `gold-evaluation/v2`.

Focused tests: 33 passed. Full suite: 1100 passed, 5 skipped, no failures/errors.
JUnit: `data/interim/verification/quality-development-2026-10-04/final-full-suite.xml`.
The prior in-task reports ending `-01` and `-02` remain preserved but are
superseded by this corrected `-03` evaluation.

## Repeatable offline command

The measured run used this command with destination ending `-03`. For a future
offline recheck, use a fresh destination (the proposed destination below has not
been created). This evaluates saved outputs and does not execute models.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py `
  --gold data/annotation/dev-starter-2026-10-03/sunayana-reviewed-01/development-reference-01 `
  --split dev `
  --saved-run data/interim/phase5/development-corpus/3dc346ec030a `
  --relevance data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl `
  --pack data/annotation/dev-starter-2026-10-03/sunayana-reviewed-01 `
  --prefilter-events data/interim/phase4/stage_events.jsonl `
  --out data/exports/quality/development-offline-recheck-01
```
