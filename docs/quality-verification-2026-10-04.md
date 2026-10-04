# Bounded quality verification — 2026-10-04

ADR-37, later the same day, accepted this 35-document / 21-case gold set as
final and closed the 75–100 labelling volume. The measurement below was not
rerun or rewritten.

The authorized experiment is complete and consumed. Sunayana reviewed all
25 source-first holdout drafts and explicitly approved them before measurement.
All five **numeric evaluator thresholds** passed on those seats. This does not
establish strong extraction quality, semantic approval of model cases, or
wholly unseen generalization.

## Reference and independence

The existing `gold-split/v1` seats remain unchanged: 10 dev and 25 gold-holdout
documents drawn from the 35 Phase 4 development documents. The latter 25 had
prior development exposure. The original 15 Phase 4 holdout documents are
separate; their text was not copied into this pack or sent in this experiment.
No retrospective split change makes these 25 an untouched test set.

The approved development reference contributes 10 documents and six cases,
copied unchanged. The approved holdout reference contributes 25 documents and
15 cases; 110 attached quotes passed exact source-offset checks. Total official
gold: **35 documents, 21 cases**. ADR-37 accepts this size as the final gold
set. These are AI-assisted labels reviewed by the sole human
Sunayana under ADR-33, not independent double-coding; agreement is null.

Approval and its bound source/label hashes are retained in
`data/annotation/holdout-review-2026-10-04-01/human-approval.json`.
The reviewed sources, drafts and ambiguities remain in that pack's
`APPROVAL.md`. Approval of reference labels does not approve model outputs.

## Configuration and safeguards

ADR-35 scopes this route to existing seating and existing normalization-derived
audit records, duplicate links, prefilter, relevance, extraction, ModelGateway,
cache and persistence. There is no replacement framework or general live runner.

- Provider/model: Groq `openai/gpt-oss-120b`.
- Relevance `relevance/v5`: 4096 output tokens.
- Extraction `extract/v3`: corrected schema, 8192 output tokens.
- Requested temperature 0; existing Groq adapter transmits 1e-8.
- SDK retries 0; one gateway attempt per document per stage.
- Request ceilings: dev 20, holdout 50; one first-attempt reservation per seat
  in each stage. Cache hits consume no provider request. No human relevance
  override promotes a document into extraction.
- Exact cache identity includes prompt/version, model, content, temperature,
  token limit and transmitted schema. Historical v2 extraction cache entries
  cannot satisfy v3 requests. Legacy CLI modes keep their v2 pins.
- Missing credentials and existing output parents fail before calls/output.
  Dry-run makes zero calls and writes zero stage records.
- Code, settings, sources, seating, approved dev labels and development report
  were hashed before holdout. Human approval binds exact reference and packet
  hashes. Exclusive measurement and scoring claims prohibit repeating this
  frozen experiment, including after an interrupted run.

Freeze: `data/interim/phase6/quality-freeze-2026-10-04-01/freeze.json`.
The measurement, completion and evaluation claims are beside it. Do not edit
frozen code/settings and silently reuse this freeze.

## Actual results

Development run: `data/interim/phase6/quality-dev-v3-2026-10-04-01/`.
Nine new requests (three relevance, six extraction), seven relevance cache hits.
One relevance evidence rejection; extraction accepted two cases and four empty
responses. Coverage 2/6 reference cases. Development relevance precision 5/6
(0.8333) missed its threshold. This miss is retained, not replaced by holdout
scores. The frozen candidate did not acquire a development-pass claim.

Holdout run: `data/interim/phase6/quality-holdout-v3-2026-10-04-01/`.
Sixteen new requests (two relevance, fourteen extraction), 23 relevance cache
hits. All 25 relevance records were technically ok; no relevance technical
exclusions affect the denominator. Across all 25 documents, TP=13, FP=1, FN=1.
Precision and recall are both **13/14 = 0.928571**, passing 0.85 and 0.80.
Prefilter recall **1.00** passes 0.90.

Fourteen extraction document attempts: nine succeeded, five failed. Four
succeeded with empty case arrays; five accepted cases match five of fifteen
reference cases. Ten reference cases are unmatched; no extra accepted model
case is unmatched. Eleven out-of-scope documents were skipped.

The five failed documents comprise four provider errors and one evidence-gate
failure. The latter document has two rejected case records: six retained
failure records are **not six failed document attempts**. Ten extraction
attempts recorded finish reason `stop`; four provider errors have no recorded
finish reason or token usage. Do not infer token exhaustion or charges.

Schema and span rates **1.00** use the existing evaluator's accepted-record
denominator: 25 relevance records plus five accepted cases. Rejected provider
outputs are excluded and their failure counts remain visible. Consequently,
the stronger assertion that every processed provider output passed validation
is not established. Per-field scores and unsupported-inference diagnostics
are conditional on the five aligned cases, not the fifteen reference cases.
Exact quotes can still support an incorrect interpretation.

Review risks remain: retrieval_trigger confused with search method, unsupported
impact/severity, incomplete summary evidence, and invented or spliced quotes.
Semantic review and corrections remain traceable separate records; saved
model responses are not repaired.

Total **25 new requests**, no retries, 30 relevance cache hits. Recorded-usage
list-price subtotal **$0.05544735** across both runs excludes unknown usage from
four provider failures. It is incomplete and is not a billing statement.
Holdout extraction recorded 124,298 input / 26,776 output tokens; dev extraction
recorded 74,513 / 14,788. Relevance recorded dev 9,600 / 2,350 and holdout
6,373 / 1,459. Missing counts are not filled with zeros.

## Executed commands and destinations

These describe the completed experiment; they are **not instructions to repeat
paid calls**. Output freshness and the consumed holdout claims refuse reuse.

Development dry-run used the same flags as the live command plus `--dry-run`
and a separate unused output parent. Both split dry-runs made zero calls and
wrote zero collection/stage records. The live stage commands were:

```powershell
.\.venv\Scripts\python.exe scripts\quality_run.py --split dev --out data/interim/phase6/quality-dev-v3-2026-10-04-01 --cache data/interim/cache --call-budget 20
.\.venv\Scripts\python.exe scripts\quality_run.py --freeze-out data/interim/phase6/quality-freeze-2026-10-04-01/freeze.json --development-report data/exports/quality/dev-v3-2026-10-04-01/report.json
.\.venv\Scripts\python.exe scripts\prepare_quality_holdout.py --freeze data/interim/phase6/quality-freeze-2026-10-04-01/freeze.json --out data/annotation/holdout-review-2026-10-04-01
.\.venv\Scripts\python.exe scripts\quality_run.py --split holdout --out data/interim/phase6/quality-holdout-v3-2026-10-04-01 --cache data/interim/cache --call-budget 50 --freeze data/interim/phase6/quality-freeze-2026-10-04-01/freeze.json --pack data/annotation/holdout-review-2026-10-04-01 --gold data/gold/quality-freeze-2026-10-04-01 --approval data/annotation/holdout-review-2026-10-04-01/human-approval.json
```

Drafting, human review, reference validation/export and the holdout dry-run
occurred between preparation and live measurement. Scoring is offline. The
successful once-only holdout scoring command used absolute input paths:

```powershell
$qualityRoot = (Get-Location).Path
.\.venv\Scripts\python.exe scripts\evaluate.py --gold "$qualityRoot/data/gold/quality-freeze-2026-10-04-01" --split holdout --out data/exports/quality/holdout-frozen-v3-2026-10-04-01 --saved-run "$qualityRoot/data/interim/phase6/quality-holdout-v3-2026-10-04-01/extraction/34d4a0c91984" --relevance "$qualityRoot/data/interim/phase6/quality-holdout-v3-2026-10-04-01/relevance/relevance_decisions.jsonl" --pack "$qualityRoot/data/annotation/holdout-review-2026-10-04-01" --prefilter-events "$qualityRoot/data/interim/phase6/quality-holdout-v3-2026-10-04-01/relevance/stage_events.jsonl" --freeze "$qualityRoot/data/interim/phase6/quality-freeze-2026-10-04-01/freeze.json" --approval "$qualityRoot/data/annotation/holdout-review-2026-10-04-01/human-approval.json"
```

An initial relative-input scoring invocation was refused before report output
or calls. Small future integration fix: normalize evaluation input paths before
hash-guard path comparison. It was not applied after freeze and measurement;
the measured code and guards remain intact. No holdout error-analysis CSV was
produced, and no holdout-guided prompt tuning or provider retry occurred.

## Publication, preservation and testing

`data/exports/quality/CURRENT.json` points to the current development report,
holdout `report.json` and `ASSESSMENT.json`. Historical pending reports are
unchanged. `data/gold/CURRENT.json` records the versioned approved gold source
and byte hashes. Original empty official gold files are preserved in
`data/gold/pre-quality-freeze-2026-10-04-01/`.

Preservation audit: 660 prior data files checked; only the two intentionally
populated official gold files changed, with exact original backups verified.
Existing runs, cache entries, labels, reviews and split manifests remain.
The submission app reads only aggregate current-quality metadata on its
methodology page; that display does not load holdout source/predictions or
call providers. M1 remains technically complete. Phase 6 research and broader
submission work are not marked complete.

Focused app/quality/saved-run tests: **31 passed**. Full suite:
**1131 passed, 5 skipped**, using `.\.venv\Scripts\python.exe`.
Mocked tests cover cache reuse, stage budgets, first-attempt reservations,
missing-key/fresh-output guards, zero-call dry-run, frozen-hash drift,
human approval requirements, source-only packets, repeat-measurement refusal,
completed-artifact tampering and aggregate app display. No commit, push or
deployment.

A later offline diagnosis of the six development reference cases is
`docs/development-diagnosis-2026-10-04.md`. It does not change this measurement,
the freeze hashes, or the holdout result.
