# Changelog

## 2026-10-06 - Catch up missed scheduled runs and publication

Enable catch-up and network availability on the three existing Windows tasks,
retaining daily times and interactive logon. Queue instances and use a shared
Windows mutex to serialize research and publication across all three tasks,
so simultaneous catch-up jobs wait instead of hitting the pipeline overlap
guard. Preserve the research exit code on publication failure. Original task
settings are backed up locally. Windows scheduling delays and coalescing limit
catch-up; this does not promise every historical slot or unattended logged-out
execution. Collection/model limits, n8n and integrations are unchanged.

## 2026-10-06 - Publish snapshots automatically after scheduled batches

The existing Windows command now publishes the current public scheduled and
comparison snapshots to GitHub after successful or partial research runs.
An isolated sparse checkout limits commits to snapshot pointers and version
bodies, reuses the privacy/atomic snapshot contracts, and preserves unrelated
local work. Unchanged snapshots, newer remote results and changed reference
versions are skipped. One regular push; no force, retry or collection/model call.
Local publication status is durable and failures preserve the research exit
code and deployed snapshots. Existing Git credentials supply authentication.

## 2026-10-06 - Package public snapshots for Streamlit Cloud

Cloud lacked the gitignored local scheduled and automated comparison snapshots.
Added a separate tracked deployment bundle, an offline privacy-checked packaging
script, and local-first/Cloud-fallback selection. The UI labels deployment copies
as saved results. Existing atomic publication, versions, caches and Refresh
buttons are reused. Curated packages now include both snapshots. Scheduler tasks,
budgets, model calls, n8n, Sheets and frozen data are unchanged.
Live verification also found and fixed automated bucket rendering: the page now
reads the snapshot's `core` and `adjacent` keys instead of scope-enum strings.

## 2026-10-05 - Install pydantic for the Streamlit Cloud app

Community Cloud installs `requirements.txt` and was missing `pydantic`, so
`app.py` failed at import with `ModuleNotFoundError`. The bound matches the
curated cloud package (`pydantic>=2.8,<3`).

## 2026-10-05 - Human-reviewed n8n reference and automated comparison

Recorded the owner's detailed review of the 48 saved n8n threads as an
immutable, hash-verified reference (`n8n-reviewed-reference/01`,
`data/exports/reference/n8n-reviewed-reference-01/`), built from the saved
export only, with explicit field mappings, explicit unknowns and no inferred
fields. Added `REFERENCE_STANDARD_VERSION` to the version registry and to
scheduler pins. Added `src/export/reviewed_reference.py`,
`src/export/reference_standard.py` and `src/export/reference_standard_build.py`:
future public records are assessed with deterministic evidence checks
(supported retrieval trigger, impact and summary; continuous quotes at valid
offsets; no rejected text; no recorded finding; source link; not a reviewed
document; no duplicate case) and published atomically to
`data/exports/public/reference-standard-snapshot/`. Each case records the
reference, prompt, schema and model versions and `semantically_approved:
false`. Separate counts for human-reviewed records, automatically valid,
eligible, flagged, unverifiable, failed or incomplete and reference-overlap
cases. The scheduler refreshes that snapshot best-effort after its own publish;
the refresh cannot fail a run and makes no request. The Streamlit "Reference
standard" section shows the two labelled views with the snapshot and reference
versions in the cache key, fragment refresh and a Refresh button. Scheduled
sub-batches are exported through the existing builder when they exist. Cloud
package allowlist now ships the reader modules and the reference artifact.
Prompts, schema, model, token settings, budgets, gold data and frozen splits
are unchanged; no n8n or Google Sheets file was edited or called. Focused
tests: 29 new, 313 passed with related suites. Full suite: 1302 passed, 5
skipped, 0 failed. `git diff --check` clean apart from line-ending warnings.
No commit, push, deploy or live run.

## 2026-10-05 - Fix duplicate YouTube reply collection and two test failures

Unchanged complete reply threads are no longer requested again. The scheduled
collector receives stored reply counts, and the parent manifest records the
finished status. Collection no longer imports the analysis package. The
reference UI test follows the radio navigation. Full suite: 1267 passed, 5
skipped, 0 failed. The 08:00 run had already spent its 20 requests and was not
repeated.

## 2026-10-05 - Bounded scheduler for non-n8n sources

Added `main.py schedule` and Windows Task Scheduler entries for 08:00, 14:00
and 20:00 Asia/Kolkata. A 50-document batch is processed as existing
research-batch sub-batches of 20, 20 and 10. The 20-document runner guard is
unchanged. YouTube comments are the only collected source. Reddit, store and
support collectors stay unavailable, and n8n is not called. Unchanged source
items are tracked so they are not reprocessed. Per-run limits are 20 collection
requests and 100 model attempts; daily limits are 60 and 300. Reservations are
durable. Overlapping runs are refused. Snapshots publish atomically and the
Streamlit page separates automatic validity from semantic approval.

Dry-run `df6cfde5ae72` made zero requests and wrote zero records. The three
tasks are enabled and have not run. Focused tests: 12 passed. Full suite:
1263 passed, 5 skipped, 2 pre-existing failures
(`test_collect_imports_only_core_models_and_itself` and
`test_reference_app_and_saved_search`). Git diff --check passed with
line-ending warnings only. No prompt, schema, token, gold, holdout or n8n
change. No commit, push or deploy.

## 2026-10-04 - Reddit collection skipped

The owner directed the project not to exercise Reddit. Self-service API keys
are no longer issued, new access requires approval, and new public-API requests
stop after 2026-10-31. No access request will be filed and no Reddit request
was made. The collector still skips when credentials are absent. The 17 Reddit
documents already in the corpus remain manual imports.

## 2026-10-04 - Phase 7 YouTube collection and source funnel

Exercised YouTube comment collection: 40 comment-read requests, 266 new
documents. Deduped corpus is 318 documents across five platforms, with YouTube
above the 40% concentration line. Added a Reddit OAuth client that skips when
credentials are absent and stops on a rate-limit response; no Reddit request
was made. The scaled run checkpoints each source and writes the collection
funnel. Manual store and support imports stay in the corpus. No store or
support-forum collector, no `search.list` call, and no relevance or extraction
run. Focused collector tests: 49 passed.

## 2026-10-04 - corrected n8n collection node verified on one live thread

After the owner published the replacement node code, checked required settings,
the dedicated endpoint, fresh destinations and a zero-call/zero-record dry-run.
Ran one reserved collection attempt: HTTP 200, execution 15, one item, no
failures, one source fetch attested, zero model calls and no retry. Existing
collection/privacy/persistence saved one document with the exact 489-character
original text, hashed author and original source/publication/collection dates.
Replies remain unfetched. Offline reimport dry-run recognized the existing item
without writing a duplicate or changing its bytes. The 2021 publication date
is retained; the route-test post is not counted here as recent feedback.

Preserved the earlier failure, parser replay, all labels/splits/cache/reviews
and prior runs. Added safe provenance diagnostics and updated integration status
with its prior metadata snapshot. The one-attempt diagnostic now retains only
the four known parser failure codes; arbitrary returned text remains suppressed.
Focused mocked tests: 31 passed. Full suite: 1230 passed, 5 skipped. Git diff
--check passed with line-ending warnings only. No model processing, holdout access, quality
completion, commit, push or local deployment. Updated architecture, backlog and
n8n documentation with the actual one-thread verification limits.

## 2026-10-04 - original-post parser fixed from saved fetch output offline

Diagnosed the owner's execution-14 fetch export: valid html field, no static
QAPage JSON-LD, and an exact original plain body in thread_view[1][12]. Added
paste-ready replacement code for the existing Extract original post node and
reused it in the workflow builder, preserving all saved workflow exports.
Literal escapes and JSON are decoded as data; page scripts never run. Thread
and canonical identity, field shapes, plain-text and ambiguity checks fail
closed. Replies are excluded and remain explicitly unfetched. Original title,
publication microseconds and author-profile mapping are traced to the saved
renderer. Existing import/privacy/request guards are unchanged.

Offline replay recovered the exact 489-character original and passed the
existing importer in dry-run mode: one document seen, zero records written,
zero new webhook/source/model requests. Preserved hashes, original text and
safe diagnostics privately, and backed up prior integration metadata. Cloud
node update/publication and corrected live verification remain pending.
Focused mocked tests: 27 passed; architecture/collection checks: 275 passed,
5 skipped. Final full suite: 1226 passed, 5 skipped. Git diff --check passed
with line-ending warnings only. A full-suite failure exposed a stale Phase 4 package-absence check;
replaced it with import isolation for the existing saved-analysis packages,
without changing implementation, research status or quality thresholds.
Updated architecture, implementation plan and n8n mapping/application steps.
No original run, cache, label, review, gold/split, model prompt or credential
changed; no holdout access, provider request, commit, push or deployment.

## 2026-10-04 - one n8n live collection check, source failure retained

Used the owner's selected thread 106429666 for one dedicated webhook POST.
HTTP 200 returned collection contract and execution 14; the workflow reported
one page fetch, zero model calls, zero items and no_verified_plain_original_post.
Zero collected documents, no retry or additional source/model request. Retained
the supplied language-query URL and the query-free request URL. Added a
one-attempt diagnostic wrapper over the existing collector, with secret-safe
metadata and a pre-send reservation. Mocked collector/diagnostic tests: 12 passed.
Actual source text remains unverified; diagnosing it requires the already-saved
fetch node output. Updated local integration status with a prior metadata backup.
No labels, model outputs, cache, evaluation, commit or push changed.

## 2026-10-04 - gold labelling volume closed at the approved set

The owner closed the internal 75–100 document labelling target. The approved
official gold set, 35 documents and 21 cases, is final (ADR-37). Labels, splits,
thresholds, and the consumed holdout measurement were not changed. No documents
were added.

## 2026-10-04 - n8n collection endpoint configured locally

Recorded the owner's dedicated production URL in local settings, preserving
the existing key and author salt. One-document/one-fetch configuration dry-run
passed: zero webhook requests, source requests, model calls and collected
records; no collection output parent. Updated local integration status while
retaining its previous metadata. Actual Cloud authentication and source access
remain unverified until a real thread is selected. No paid/model or webhook
call, label change, commit, push or publication was performed in this setup.

## 2026-10-04 - reviewed-reference demo, bounded n8n bridge and authorized v4 run

Added a separate original-post community-collection/v1 adapter and inactive
n8n workflow, using existing IDs, author hashing, collection records and
persistence. Limits, missing-key guards, exact-text validation, reimport
behavior and zero-call dry-run have mocked tests. Old tagging webhook is refused.
No n8n Cloud call was made; live connection and source compatibility are pending.

Added a minimum-excerpt export of six already-approved development reference
cases (38 evidence fragments), traceable field comparisons and memory/journey
views. Model semantic approval stays absent. Removed spending-capable workflow
actions from the read-only Community insights surface, retaining original
workflow/data and prior UI code in a local snapshot. Prepared a fresh curated
Streamlit Cloud package ending -03 with no credentials, raw source or holdout
text; public deployment was not performed.

Added explicit development-only candidate routing with version-separated
cache identity and unchanged active pins. The authorized extract/v4-only run
used six requests, ten relevance cache hits, no retries: five accepted cases,
one accepted-empty response, all finish_reason=stop. Recorded usage is
76,079 input / 25,338 output tokens; estimated $0.026115. Offline scoring
matches 4/6, compared with saved v3 2/6; precision remains 0.8333. Recorded
semantic findings without editing outputs, labels or the consumed holdout.
The optional relevance/v6 route remains inactive and unmeasured; the one-run
approval is consumed. Updated current aggregate metadata while archiving the
previous pointer; historical reports are retained.

Validation: full suite 1157 passed, 5 skipped; focused mocked tests 40 passed;
isolated final package nine surfaces and saved searches passed with external
network access denied. Zero-call development/collection dry-runs and hash-only
preservation passed (660 baseline files; 21 frozen measurement artifacts).
`git diff --check` passed with CRLF warnings only. No commit, push or deployment.

## 2026-10-04 - submission quality report and offline ask

Added a Quality report section that labels development and holdout gate numbers
separately, and an Ask section that searches saved excerpts with synthesis
absent. Research coverage, precision, semantic approval, gold size, n8n
collection, and public deployment were not changed. No provider call.

## 2026-10-04 - development failure diagnosis and inactive extract/v4 candidate

Diagnosed all six approved development reference cases against the saved
`extract/v3` run. Three omissions are accepted-empty responses, one is a
relevance quote rejection, and two cases match with remaining semantic
disagreements. No saved output, label, split, or freeze hash was rewritten.
Valid out-of-scope extraction skips now carry `skip_cause` and do not open an
evidence-failure review. Evaluation path keys resolve from the project root
before hash comparison. `extract/v4` can be rendered and is neither the active
pin nor the measured correction. The submission methodology shows the
development miss beside the holdout aggregate, and states that n8n tagged rows
are not collection records. Full suite: 1133 passed, 5 skipped. A development
dry-run made zero calls and wrote no stage records. No live request, holdout
repeat, commit, or deploy.

## 2026-10-04 - bounded frozen quality measurement completed

Added the scoped quality route over the existing gold seating and existing
prefilter/relevance/extraction stages. It uses ModelGateway, exact cache
identity, corrected Groq nullable schema, first-attempt reservations and
persistence; relevance/v5 and extract/v3 use Groq openai/gpt-oss-120b with
4096/8192 output tokens, SDK retries 0 and gateway attempts 1. Legacy pilot,
diagnostic and development-corpus pins remain extract/v2. Scoped extraction
records its effective version in run IDs, case fingerprints and manifests.
Dry-runs write no records and make no calls. Fresh-output and missing-key
guards precede requests; frozen code/settings/source hashes, exact human
approval hashes and exclusive measurement/scoring claims protect holdout.

Prepared 25 source-first holdout drafts without prediction-based labeling.
Sunayana explicitly reviewed and approved them. Official gold now holds 35
document labels and 21 cases, preserving dev/holdout seating and unchanged
development labels. Original empty files and historical pending reports are
retained. The 25 gold-holdout seats were previously development-exposed;
unseen generalization and the 75–100 research target are not established.

Actual calls: 9 development plus 16 holdout, no retries; 30 relevance cache
hits. Holdout numeric gates pass (schema/span/prefilter 1.00, relevance
precision/recall 0.9286). Extraction matches 5/15 references, with 5 failed
attempts and 4 accepted-empty documents. Four provider failures have unknown
usage/billing. Schema/span rates use accepted records, not all provider outputs;
the stronger all-processed-output requirement is not claimed to pass. Four
provider errors and one evidence-rejected document produce six failure records
because that document has two rejected cases. Recorded-usage list-price
subtotal $0.05544735 is incomplete.
No holdout error-analysis CSV, prompt tuning from holdout, rewritten model
cases or implicit semantic approval. Reports/pointers and current app
methodology distinguish these results. Initial offline scoring with relative
paths refused before reporting; absolute paths scored the saved run once.

Tests cover bounds, cache reuse, first attempts, key/output guards, dry-run,
freeze drift, actual human approval, unchanged drafts, completed-artifact
hashes, one measurement and aggregate app presentation. Full suite:
1131 passed, 5 skipped. Historical artifacts verified; no commit, push or deploy.

## 2026-10-04 - prepared extract/v3 correction, still inactive

Added a renderable `extract/v3` prompt that keeps the `extract/v2` evidence
rules and adds the ten clarifications from the approved development review.
The active extraction pin stays `extract/v2`, so historical v1 and v2 rendering
and the five-document corrected-schema cache stay valid. Moving the pin to v3
makes that cache confirmation fail closed before any provider call. Added
mocked regressions for version isolation, cache identity, per-field evidence,
spliced quotes, ambiguous offsets, and synthetic episode fixtures. Those tests
do not measure live extraction quality. No gold-dev-only dry-run mode exists,
so neither the 35-document corpus nor the five-document pilot was run. Full
suite: 1112 passed, 5 skipped. No provider call, holdout access, reference or
split edit, commit, or deploy. Development is not frozen and the final quality
gate remains pending.

## 2026-10-04 - approved reference revision 02 and review decisions

Applied the owner's explicit reference correction in a new pack/export:
`sunayana-reviewed-02/development-reference-02/`. Cat impact is empty/not_stated;
severity 3 and its evidence remain. Removed exactly one obsolete impact field
attachment (39 to 38 total). All other case values, scopes, counts, identities,
seating/splits and prior files are preserved. Reused existing annotation
validation/emission; ten reviews validate and six cases retain exact source quotes.
Recorded approval of the remaining six-document review findings and correction
proposals separately in `development-review-approval-2026-10-04-01/`, bound to
run/review hashes. No model row is rewritten or failed candidate promoted.

Fresh saved-model evaluation at
`data/exports/quality/development-reference-revision-02-2026-10-04-01/` meets
five numeric development thresholds, with coverage unchanged at 2/6 and
inference/disagreement diagnostic unchanged at 41.2%. Impact recall/F1 are
undefined because the matched references now contain no stated impact labels;
the model's time_loss remains unsupported. Severity matched accuracy stays 1.00.
All 166 protected input hashes are unchanged. No production code change or
new full-suite run; last suite remains 1100 passed, 5 skipped. Zero provider
requests, holdout source access, prompt/schema/cache/split edits, official gold
updates, commits or pushes. Development is not frozen; final quality gate
remains pending and M1 remains complete.

## 2026-10-04 - source-grounded development correction proposal

Reviewed all four missing reference episodes and the two accepted model matches
against six allowed gold-dev source packets. Wrote a separate review/proposal
with source offsets, exact retained failure diagnostics and input hashes under
`data/interim/phase6/development-review-2026-10-04-01/`. It is an AI-assisted
proposal, not new human approval, a label change or repaired model output.
Confirmed two empty-response omissions, poodle spliced/altered quotes and
ambiguous offsets/missing outcome evidence, and missing exact_query field
evidence for the successful sleeping-video case. Current gates behave correctly.
Separated unsupported claims, missed fields, incomplete summary attachments,
supported shorter motive wording and ambiguous reference coding. Documented a
new reference concern: approved cat repeat_effort lacks separate sittings under
the written definition; a new strict reference revision is proposed but not
applied. Severity 3 remains supported. No numeric scores were revised.

Local artifact verification reused existing saved-development and span validators:
25 unique exact review anchors, 20 exact retained spans, two invalid saved quotes
absent from source. All 21 M1, 98 protected annotation and 26 evaluation input
hashes remain unchanged. No production code change or new full-suite run; last
full suite remains 1100 passed, 5 skipped. No model request, holdout source read,
prompt/schema/cache/label/split change, commit or push. Development is not frozen;
M1 remains complete, final quality gate remains pending. Recorded proposed
offline acceptance fixtures and the smallest future prompt clarification,
without implementing or executing it.

## 2026-10-04 - saved development evaluation; holdout remains locked

Connected `scripts/evaluate.py` to saved model predictions through a development-
only adapter reusing current contracts, record gates and approved source packets.
Requires all four saved-input options, refuses holdout packets/occupied output,
includes relevance and full inline/external case evidence, preserves pending
status without predictions, and reports missing cases/failures independently.
Fixed structured gold multi-label comparison, omitted-label inference accounting,
and unassessed summary reporting. Version: `gold-evaluation/v2`; thresholds,
prompts, schemas, labels and splits are unchanged.

Current output: `data/exports/quality/development-approved-2026-10-04-03/`.
Ten documents/six reference cases: schema/span validation and prefilter recall
1.00, relevance precision 0.8571 and recall 1.00. All five numeric thresholds
are met only on this development diagnostic. Accepted extraction coverage is
2/6, with two technical rejections and two missing episodes in empty responses.
The two matched cases retain field disagreements; unsupported-inference
diagnostic 7/17 (41.2%), summary unassessed. Earlier in-task reports are preserved
with supersession notes. Documented corrective actions and single-reviewer/small-
sample limitations; no independent semantic adjudication is claimed.

Focused tests: 33 passed; full suite: 1100 passed, 5 skipped. All 21 M1 input
hashes, 98 protected annotation hashes and 26 final evaluation input/code hashes
are unchanged. Official gold remains empty; original reports, runs, caches and
review decisions are preserved. No provider request, holdout source access,
commit or push. M1 remains complete; Phase 6/final quality gate remain pending.

## 2026-10-04 - recorded owner approval for saved M1 model cases

Sunayana directly approved the ten saved model cases in run `3dc346ec030a`.
Created a separate run/case-hash-bound correction ledger and approval note in
`data/interim/phase5/semantic-approval-2026-10-04-01/`. Five cases have no
recorded finding; five remain blocked by existing export/browser rules (two
semantic-evidence objection cases and three cases carrying a historical
document-level provider finding). No finding or model value was changed. The
five affected Google Support fields match the previously reviewed pilot values.
Approval is not a new independent source review or a quality-gate measurement.
All 21 M1 artifact input hashes remain unchanged. No application behavior change
or new test run; the latest full suite remains 1087 passed, 5 skipped. Existing
prepared exports, original runs, caches, approved reference labels, splits and
official gold are preserved. No provider call, holdout source read, commit or push.

## 2026-10-04 - M1 verified offline; complete field-evidence count

Closed the five Section 28 M1 checks using saved development run `3dc346ec030a`
and the current full offline suite (1087 passed, 5 skipped). Added
`scripts/audit_m1.py` and a fresh report/readable record in
`data/exports/milestones/m1-2026-10-04/`, with input hashes and explicit limits.
Fixed the development-corpus reporting path to reuse the existing record gate's
inline-plus-external union: 61 analysis spans, not the historical inline-only 24.
All ten accepted cases pass the current gate; all 61 spans match retained valid
verdicts. Twenty spans also pass fresh approved gold-dev source checks.
Reserved holdout source text was not loaded. Regression tests cover complete
counts, exclusion of failed attempts, missing field evidence, repeated cases,
missing retained verdicts, failing tests, holdout packet refusal and output
preservation. Prior outputs, caches, approved reviews, prompts, schemas, split
assignments and official gold remain unchanged; 98 protected annotation files
have unchanged hashes. No provider call, commit, push or deployment.
M1 completion is distinct from semantic approval and the pending quality gate.

## 2026-10-04 - owner-authorized single-reviewer annotations

Recorded approval of all current drafts and Sunayana's explicit authorization
for one human reviewer in this individual project (ADR-33). Prepared ten files
with document/case `labeler_id` Sunayana and retained AI drafting provenance.
Preserved original seating and all prior drafts; the new review manifest openly
waives procedural double-code flags and retains their historical values.
Existing validation/emission produced a fresh development reference export:
10 documents, 6 cases. No guards, label schemas, evidence rules, split assignments
or evaluation thresholds changed. Focused tests: 22 passed. No fabricated second
reviewer, adjudication or agreement. Official gold and reports remain unchanged.
No external request, holdout text access, commit or push. M1 remains incomplete.

## 2026-10-04 - sleeping-video approval and family-album core instruction

Created annotation revision 03 with two additional scoped human decisions.
Recorded approval of the sleeping-video core/one-case summary and applied the
family-album core instruction. The latter is flagged as a scope-criteria
exception because the source does not demonstrate incomplete recall under
Section 9.1; no forgotten cues, field evidence, definition or prompt was changed.
Proposed totals: 3 core, 3 adjacent, 4 out of scope, 6 cases. All 10 files
validate and all 39 spans still match. Case values, earlier revisions and the
first four decision records are preserved. Official gold and reports remain
unchanged. No provider call, evaluation, independent second review, holdout
text access, commit or push. Quality gates and M1 remain pending/incomplete.

## 2026-10-04 - scoped human annotation decisions

Recorded Sunayana's review of items 3, 7, 9 and 10 in a new revision and a
decision ledger. Changed Memories scope to adjacent and proposed a single
source-grounded case with two exact evidence spans. Accepted the poodle
example's later first-person grounding, cat severity 3, and the short YouTube
insufficient-evidence exclusion. Other unapproved fields remain AI drafts;
no independent double-coding or adjudication is claimed. Revision 02 contains
2 core, 4 adjacent, 4 out-of-scope documents and 6 proposed cases; all 10 files
validate. Focused tests: 22 passed. Earlier drafts, original packets, splits,
official gold and quality reports are preserved. No provider call, holdout text
access, evaluation, commit or push. New Memories case details and required
second human reviews remain open.

## 2026-10-03 - AI-assisted starter annotations for approval

Prepared a separate, unapproved draft pack for all 10 development starter
documents, including five cases and exact source quote offsets. The proposals
contain 2 core, 3 adjacent and 5 out-of-scope labels. `REVIEW.md` exposes source
text, field values, supporting quotes, rationale and uncertainties. Each draft
identifies its AI provenance; no human review, double-coding or adjudication is
claimed. Original packet/gold/split hashes are retained in `provenance.json`.
Draft validation passed for all 10 files; the original pack remains pending with
0 reviews. Focused tests: 22 passed. No provider request, evaluation, official
gold promotion, existing decision change, holdout text access, commit or push.
Approval and the two genuine independent second reviews remain pending.

## 2026-10-03 - development annotation pack

Added a blank 10-document pack at `data/annotation/dev-starter-2026-10-03/`.
The documents are the gold-`dev` seats from `gold-split/v1` inside the frozen
Phase 4 development split. Packets contain source text, provenance, and empty
gold fields. Model predictions are stored separately. Completed reviews are
checked with `scripts/validate_annotations.py`, including exact quote offsets.
No gold labels were created. Full suite: 1078 passed, 5 skipped.

## 2026-10-03 - Phase 6 gold evaluation

Added gold loaders, the `gold-split/v1` assignment rule, evidence-overlap case
matching, and `scripts/evaluate.py`. Scalar accuracy requires value and
observation status. Multi-label scores report micro and macro separately. A
prefilter drop counts as not relevant. Holdout error analysis is refused. An
empty gold set reports `pending` rather than zeros. No gold labels were
created, and the quality-gate thresholds were not changed. Full suite: 1070
passed, 5 skipped.

## 2026-10-03 - Phase 5 human case overrides

Added append-only `CaseOverride` rows and `v_current_cases`. A valid human case
supersedes the model case; the model row stays. A quote that is not verbatim
stays pending and does not become current. No development case was overridden.
Historical calls `4a8c7175f992` and `024f9b18b60f` still have no recorded usage;
their cost was not estimated. Saved rejection diagnostics are HTTP 400
`json_validate_failed`. Evidence-gate failures stay out of the analysis file.
Full suite: 1042 passed, 5 skipped.

## 2026-10-03 - development corpus extraction, milestone M1

Extracted the frozen 35-document development split once, through the existing
`extract/v2` gate, Groq `openai/gpt-oss-120b`, an 8192-token limit, and one
attempt. Holdout documents were refused. The run is
`data/interim/phase5/development-corpus/3dc346ec030a`: 17 provider calls, 4
cache hits, 10 analysis cases, 24 verbatim valid spans, 6 evidence failures
kept out of the analysis file, and 14 out-of-scope documents skipped. Recorded
list-price estimate USD 0.055115 is not billing. Prompts, schemas, labels, and
the split were not changed, and no case was semantically approved. Full suite:
1035 passed, 5 skipped.

## 2026-10-03 - read-only submission app

Added Streamlit 1.65.0 through `pyproject.toml` and a read-only `app.py` with
overview, evidence, comparison, and methodology sections. The app reads prepared
exports built by `python -m src.export.build` from `config/submission_manifest.json`.
It does not open raw collection files, credentials, or unfiltered provider
diagnostics, and it does not call a model, YouTube, or n8n. Development and
YouTube runs stay separate. Zero cases are semantically approved. An n8n
destination mapping is documented in `docs/n8n_import_mapping.md`; no sample
export was available, so no adapter was written. Full suite: 1025 passed,
5 skipped. Phase 10 and M1 remain incomplete.

## 2026-10-03 - offline failure reporting and execution guards

Research-batch extraction now returns a failure exit status on a rejected attempt
and refuses an existing extraction destination before calls or writes. Live relevance
and extraction record their UTC run-start time instead of fixed fixture dates;
offline modes remain deterministic and tests may inject a timestamp. Empty rejected
generation diagnostics are explicitly `empty`. The failed request's schema digest
matches the current corrected wire schema. The provider rejection cause remains
unknown; no prompt/schema changes or paid retries were made. Historical artifacts
and review decisions remain unchanged. Tests: 73 focused, 1008 full-suite passed,
5 skipped. M1 remains incomplete.

## 2026-10-03 - bounded YouTube batch processed

Collected 20 comments with two YouTube requests and verified provenance offline.
Relevance made 20 model calls, all technically valid: 19 out of scope and one
adjacent classification requiring semantic review. One authorized extraction
request failed with Groq HTTP 400 `json_validate_failed`; no case, usable output,
or usage was retained. No retry. Recorded relevance estimate: USD 0.018501;
combined usage and billing unknown. Saved fixed event timestamps are inaccurate
for the actual October 3 execution. Runs, labels and the frozen split remain
preserved. M1 remains incomplete.

Material implementation changes by date (spec Section 1). Scope and schema
decisions live in `DECISIONS.md`; this file records what was built.

## 2026-10-01 - bounded research-batch integration

`main.py run --research-batch` plans at most 20 collected documents that are
not in the frozen seed split. It reuses normalization, privacy-preserving
derivation, deduplication, `run_phase4`, and `run_extraction`. It does not
use the five-document pilot, the one-document diagnostic, or the holdout.
Dry-run writes nothing and makes no provider call. Live relevance and
extraction require a call budget equal to that stage's count and one gateway
attempt.

Every collected JSONL on disk is inside the frozen split. The dry-run of the
50-document import excluded 50, selected 0, and recorded 0 provenance
failures. Maximum external requests for that input are 0. No model call was
made. Full suite: 988 passed, 5 skipped. M1 remains incomplete.

## 2026-10-01 - local evidence browser

`main.py browse` serves a read-only page at `http://127.0.0.1:8765/` from the
saved development outputs. Holdout text is not loaded. Excerpts are redacted
audit text, highlighted at stored offsets. The five-document run shows 35
development documents, 16 out of scope, 2 failed extractions, 2 automatically
valid cases, 35 human relevance labels, and 3 open review items. Semantic
approval is 0. Those two valid cases stay labeled as not approved, and the
recorded findings for retrieval trigger, impact, summary evidence, and the
spliced quote stay on the page. Core and adjacent model output stay separate.
No provisional problem group is proposed. No human correction is recorded, and
`retrieval_cases.jsonl` is not rewritten. No model call is made. Full suite:
1003 passed, 5 skipped. This does not complete Phase 10 or M1.

## 2026-10-01 - read-only YouTube comment collector

`main.py collect --youtube` reads a video-URL list and writes `CollectedDocument`
records through the official YouTube Data API methods `commentThreads.list` and
`comments.list`. Workbook import via `collect --path` is unchanged. Reply
completeness is recorded only when the API reports no replies or when reply
pages were fetched to the end. Author channel ids are hashed and not stored.
Reimport appends no duplicate source item. A document limit and a request budget
are both required. Missing credentials fail before any request or output
directory. Dry-run makes no requests and writes nothing. The collector does not
classify relevance or extract cases.

Tests use mocked API responses. Full suite: 970 passed, 5 skipped. No live
YouTube or model call was made. The mechanism remains documented and unexercised.
M1 remains incomplete.

## 2026-10-01 - free source collection routes reassessed

Added `SOURCE-COLLECTION-AUDIT-2026-10-01.md` with actual endpoints, current
robots/terms evidence, open-source code inspection, provenance limits, and
separate community discovery/fetching findings. Amended ADR-22 and source
feasibility wording to remove permanent closure as the current conclusion.
Community access requirements remain unresolved; the inspected Play RPC and
Apple RSS routes are robots-blocked, and publisher API access is not available.
No data requests, collected records, adapters, or model calls resulted. No
runtime tests or collector dry-run are claimed for this documentation change.
The concurrent YouTube implementation and shared source configuration were
not edited by this audit. Historical corpus, labels, split, and holdout remain
outside its scope. No commit or push.

---

## 2026-10-01 - five-document 8192-token run reviewed offline

Reviewed the completed run `data/interim/phase5/pilot-v2-8192-01/024f9b18b60f` without
another provider call. It recorded one cache hit, four provider calls, 35,381 input tokens,
7,325 output tokens, and an estimated list cost of USD 0.009702, with one call missing
usage. Two cases passed automatic validation, one document returned no cases, one spliced
summary was rejected, and one request failed JSON validation with no retained body.

Semantic review does not approve the Camaro case: `retrieval_trigger` is the search method,
`time_loss` is not stated, `query_strategies` omits the stated car search, and the summary
quote does not cover every claim. The empty album response is not justified by the source.
The rejected Reddit quote remains spliced and unrepaired. The other Reddit failure stays an
unresolved HTTP 400 `json_validate_failed`; its diagnostic does not establish truncation or
billing. The correction proposal separates implementation limits, instruction violations,
semantic findings, and unresolved provider behavior. No prompt, schema, label, manifest,
split, cache, or review row was changed. M1 remains incomplete.

## 2026-10-01 - five-document 8192-token mode prepared offline

`--pilot --pilot-max-tokens 8192` can use the existing five-seat manifest when
`--call-budget 4` and `--max-retries 1` are set. Before any call or output write, the
corrected-schema cache entry for `google_support-d7f386f347b7` must match the request
and pass local response validation; otherwise the run fails closed and does not request
that document. The ordinary 4096-token five-call pilot and the one-call diagnostic stay.
SDK retries, prompt pins, the manifest, labels, and the missing-key and fresh-output
guards stay. Offline mode is refused for this path.

The semantic review note records that automatic validation of
`google_support-d7f386f347b7#c01` is not semantic approval: `retrieval_trigger` is
unsupported, and `problem_summary`'s attached evidence does not cover the locating or
backup claim. The saved case, labels, cache, and review decisions were not modified.

Mocked tests cover cache reuse, missing/incompatible/unusable cache, the four-call
maximum, first-attempt reservation, invalid options, and a zero-call dry-run. Full
suite: 958 passed, 5 skipped, zero failed. The CLI
dry-run reported five documents, 8192 tokens, budget 4, zero provider calls, and zero
files. The live command was not executed. Extraction quality and M1 remain unassessed.

## 2026-10-01 - one authorized request verifies the detail-fix schema

Ran the authorized one-document diagnostic exactly once after confirming offline that the
transmitted schema types non-subject label detail as null only, subject detail as string or
null, and that the destination parent was absent. Output is
`data/interim/phase5/core-diagnostic-v2-detail-fix-01/84608e7b3eb7` with twelve files; its
run id repeats the earlier v2 id because run ids exclude the wire-schema digest.

Recorded: one provider call, one cache miss, zero cache hits, `finish_reason=stop`, 11,757
input / 4,667 output tokens, estimated list cost USD 0.004564, and complete usage totals.
One case was assembled, validated and stored as analysis-valid, with no failure, candidate,
review-queue or disagreement rows and a succeeded checkpoint and stage event. Detail is
null on every returned label; the allowed subject-detail string path was not exercised.
Nine candidate spans validated as `supplied_exact` without repair, deduping to seven unique
spans because the model repeated two label quotes through `field_evidence`. All seven quotes
are exact substrings of the target document at their stated offsets, and each stated field
carries one valid span while the eight unstated dimensions carry none.

No code changed. Earlier runs, the 86 existing cache entries and all review decisions are
preserved; exactly one cache entry was added. No retry, prompt/label/split change, holdout
access, commit or push occurred. One document does not establish extraction quality,
semantic accuracy or M1, and the earlier open review items remain open.

## 2026-10-01 - subject-only detail schema and failure reporting fix

Align the extraction request schema with the existing ObservedValue contract: all six
non-subject label dimensions require null detail; target_subjects retains optional text.
Reject invalid detail locally without coercion. Groq's existing wire-schema digest
isolates the corrected request in cache. No prompt instruction or case/evidence contract
change. Run IDs remain unchanged; use a fresh output parent for any authorized live run.

Preserve assembly schema failures in document summaries/manifests/events instead of
misclassifying them as evidence failures; schema failures take precedence for mixed
documents, while per-case findings remain distinct. Add thirteen offline regressions.
Update the historical prompt regression to use a frozen schema input and the nullable
schema checks to reflect six fewer scalar/null unions.

Relevant tests: 325 passed. Full suite: 949 passed, 5 skipped, zero failed. One-document
8192-token dry-run: zero calls, zero records, no destination creation. Original v2 run
and extraction cache preserved. No provider calls, holdout access, commits or pushes.
The prior v2 diagnostic recorded eight accepted spans but zero valid cases; quality and
M1 remain unassessed. Failed-request historical usage/billing remain unknown.

## 2026-10-01 - user-approved extract/v2 evidence correction

Registered extract/v2 and implemented the exact approved evidence instruction addition:
separate summary support, continuous verbatim quotes without inserted ellipses/spliced
passages, and no evidence for unstated/inapplicable fields. Preserve historical extract/v1
rendering byte-for-byte; reject unsupported versions. Both bounded extraction paths pin
the approved active version while retaining existing provider/model/call/retry/cache/key/
output controls. Existing version-aware cache/run/extraction-fingerprint identities
isolate the new prompt. Schemas, validators, enums, global token settings, labels and
manifest/split remain unchanged.

Added sixteen synthetic mocked regressions and updated existing active-version/cache
fixtures while retaining a legacy v1 cache seed. Relevant tests: 312 passed. Full suite:
936 passed, 5 skipped, zero failed. Core, five-document and synthetic diagnostic dry-runs
selected v2 with zero calls and zero records; their output parents remain absent.
`git diff --check` passed; status was inspected. Final read-only preservation inventory
covers 91 existing data/config/contract files, excluding the authorized prompt/registry
changes; the pilot manifest keeps its original hash. Architecture, plan, status and
decision records reflect the approved change. No provider call, saved-run/cache/label/
split modification, holdout read, commit or push occurred. Live v2 behavior, extraction
quality, historical failure billing and M1 remain unassessed. A future one-document
command is recorded in STATUS.md without live authorization.

---

## 2026-10-01 - completed diagnostic reviewed; extraction failures surfaced

The authorized 8192-token result was present when the CLI checked its destination;
the guard refused an additional invocation. Saved run `797b223ff9f9` records one
provider call, accepted structured output with `finish_reason=stop`, and zero valid
cases because two quotes were abbreviated and summary evidence was missing. Recorded
usage is 11,600 input / 2,837 output tokens, estimated list price USD 0.003442; actual
billing and historical failure usage remain unknown.

Fixed failure reporting and exit statuses across extraction CLI paths, early-stop
attempt counts, and retention of typed invalid candidates in the additive
`extraction_candidates.jsonl` artifact. Accepted empty output remains successful;
invalid candidates remain outside analysis. A guarded cache replay into a fresh review
directory made zero provider calls and retained one pending candidate in twelve output
files. Original runs/cache are preserved. Seven added mocked cases passed: relevant
tests 296 passed; full suite 920 passed, 5 skipped. No further provider request, prompt/
schema/validator/label/split edit, holdout unlock, commit or push occurred. Model evidence
errors, extraction quality and M1 remain unresolved; these implementation fixes do not
establish that all extraction errors are fixed.

Both final dry-runs made zero calls and wrote zero records; `git diff --check` passed
and status was inspected. All 79 protected hashes, sizes and write times matched.
An inactive `extract/v2` instruction proposal records the remaining evidence correction
for approval without changing the active prompt or enabling another request.

---

## 2026-10-01 - completion-limit diagnostic option prepared offline

Read the user's new one-document run `core-diagnostic-01/4a8c7175f992` without modifying
it. The saved HTTP 400 `json_validate_failed` message explicitly identifies completion
truncation at the recorded 4096-token limit. The transient summary contains valid JSON
with a missing application field; no generated body was retained. The cause applies to
this attempt, not the earlier two failures. Its usage totals are explicitly incomplete,
and failed-request billing remains unknown.

Added `--pilot-max-tokens 8192` only for the existing one-core-document diagnostic,
retaining the ordinary configured limit, strict schema and one-call/no-retry controls.
The existing decoding-aware cache and run identities distinguish the opt-in limit.
Thirteen additional mocked regression cases cover SDK forwarding, refusal bounds,
cache isolation, failed-output rejection and key/occupied-directory guards. Relevant
tests: 289 passed; full suite: 913 passed, 5 skipped. Both dry-runs made zero calls and
wrote zero output files; the new live destination is absent. All 67 protected files
retained hashes, sizes and write times, including the eleven new diagnostic artifacts.
`git diff --check` passed and status was inspected. Documentation now records the actual
run and proposed next command. No additional provider call, prompt/schema/label/split
change, holdout access, commit or push occurred. The 8192 live check requires separate
authorization; its success, extraction quality and M1 remain unassessed.

---

## 2026-10-01 - safe diagnostics and one-document controls prepared offline

Extended existing provider/gateway/cache/extraction code with safe request identity, bounded transient rejected-output inspection, optional finish reasons and explicit recorded-usage scope/completeness. No failed generation text, values, error input/context or invented field names are retained; a rejected response remains failed. Existing cache identities and legacy entries remain intact. Reported numeric usage is counted even when content is withheld; unrecorded usage and actual billing remain unknown.

`--pilot-doc` restricts the existing pilot path to either failed core seat, validating the unchanged full manifest first and enforcing one attempt/call with existing guards. The default five-document bounds remain. Twenty-two new mocked regressions passed; relevant tests: 276 passed; full suite: 900 passed, 5 skipped. Both dry-runs made zero calls and wrote zero files. The live command in `STATUS.md` was not executed. All 56 protected hashes, sizes and write times matched, with no additions/removals. `git diff --check` passed and status was inspected. No prompt, schema, validator, enum, approved label, split or saved run was edited; no provider call, holdout read, commit or push occurred. Historical causes/billing, extraction quality and M1 remain unresolved.

---

## 2026-10-01 - P0 extraction audit and resume fixes applied offline

Future span verdicts now retain the candidate quote and offsets alongside the resolved span and repair flag. Evidence-failure rows retain all gate reason codes, invalid fields and retained span ids, with bounded source/secret-filtered prose; the single filed reason and existing fields remain compatible. Failed extraction outcomes now receive failed checkpoints consistent with stage events, so general resume reprocesses them through the cache. Unassembled failures route to `extraction_attempt` / `run_id:doc_id`, while blocked relevance and assembled-case targets remain unchanged. The provider-error reason vocabulary and all P1 changes are deferred.

Eleven new mocked regression cases cover null/wrong/exact/whitespace span provenance, co-occurring gate findings, bounded prose, cached failure resume, blocked/empty outcomes and run-scoped routing with legacy-item retention. Relevant extraction/gateway/evidence/review tests: 254 passed. Full suite: 878 passed, 5 skipped. The five-document pilot dry-run made zero provider calls and wrote zero files; its output parent remains absent. Existing readers parsed all eleven saved pilot artifacts. The original mis-targeted review rows stay open with a reconciliation note in `STATUS.md`; no saved run or cache entry was rewritten. All 56 protected-file hashes, sizes and write times matched, with no addition or removal; this includes 44 saved run files and four extraction cache entries. `git diff --check` passed and status was inspected. No prompt, schema, validator, enum, label or split changed, and no provider, holdout, commit or push action occurred. Extraction quality and M1 remain unassessed.

Recorded pilot usage covers reported response usage; tokens and billing for rejected calls remain unknown. The proposal's approximate unrecorded-token estimate is not a measured fact and is not added to the run.

---

## 2026-10-01 - pilot outcome interpretation and plan aligned offline

Updated architecture and implementation snapshots to reflect the separately executed five-document pilot and marked only its execution/review checklist item complete. Recorded the distinction between the old ambiguous-schema rejection and the two new `json_validate_failed` errors. Clarified that interpreted summaries still require verbatim supporting evidence and that extraction's generic review routing does not invalidate the upstream relevance decisions. No production code, prompt, saved run, cache entry, label or split changed in this follow-up. More precise review routing and any separately authorized versioned extraction correction remain pending; no further provider call or M1/quality claim occurred.

Four existing offline evidence/status/persistence regressions passed. `git diff --check` passed, and status was inspected. The full suite was not rerun for documentation-only changes; the latest full-suite result remains 867 passed and 5 skipped.

---

## 2026-10-01 - five-document extraction pilot executed once

One authorized development pilot ran with a fresh parent, `data/interim/phase5/pilot-nullable-fix`, and stopped after five provider calls. There were 0 cache hits and 0 analysis-valid cases. Two documents returned HTTP 400 `json_validate_failed`, one returned an accepted empty case list, and two assembled cases failed evidence validation because summary or trigger quotes were not verbatim or conflicted with observation status. Prior pilot and diagnostic outputs were preserved. No prompt, label, split, holdout, commit, or push occurred. The result is a technical execution record, not an extraction-quality or M1 claim.

---

## 2026-10-01 - revised extraction schema accepted by synthetic diagnostic

The user executed the bounded diagnostic once with output under `data/interim/phase5/diagnostic-nullable-fix`. Read-only verification found technical state `ok`, one provider call, an empty failure file, and a cached response with the correct synthetic document identity and `cases: []`. The previous `anyOf` request rejection did not recur for this request. Zero cases is an allowed response; this establishes schema compatibility for the synthetic request, not real-document extraction quality or M1. No code changed and no additional provider call occurred during verification. A real-document pilot still requires separate authorization and a fresh output parent.

---

## 2026-10-01 - extraction nullable wire conversion fixed offline

Groq's authorized one-request synthetic diagnostic rejected extraction's `anyOf` branches with HTTP 400 and `error_param=response_format`. Extraction now opts into equivalent nullable scalar type arrays in the existing request-schema helper, including the original enum values plus null for nullable enum references. All 19 extraction nullable unions are converted; strict required properties, bounds and evidence rules remain intact. Application models, prompt instructions/versions, relevance conversion, labels, split and request/retry caps are unchanged. The transmitted-schema digest changes cache identity without removing legacy entries.

Mocked extraction/gateway tests: 131 passed. Full suite: 867 passed, 5 skipped. Both dry-runs made zero provider calls and wrote zero files. All 22 original failed-run files retained their SHA-256 hashes. No live retry, holdout access, commit or push occurred. Provider acceptance of the new representation awaits a separately authorized single synthetic check with a fresh output parent. No extraction-quality or M1 claim is made.

---

## 2026-10-01 - one-request synthetic extraction diagnostic prepared

`run --stages extract --diagnostic` plans one Groq request for a synthetic document through the existing extraction stage. The five-document pilot bounds are unchanged, and the diagnostic cannot be combined with `--pilot` or pointed at real documents. It uses `openai/gpt-oss-120b`, unchanged `extract/v1` strict schema, SDK retries disabled, one gateway attempt, and one external request. A missing key and an occupied output directory are rejected before the fresh directory `data/interim/phase5/diagnostic/577e727e72cc` is created. Failure rows keep the allowlisted diagnostic. Mocked tests passed. Targeted extraction and gateway tests: 119 passed. Full suite: 858 passed, 5 skipped, 0 failed. The dry-run made 0 provider calls and wrote 0 files. The live command was not executed, and no quality or M1 claim is made.

---

## 2026-10-01 - extraction request audited offline

The Groq request for `openai/gpt-oss-120b` and `extract/v1` was compared locally with synthetic text. The transmitted strict schema matches the schema embedded in the prompt. Objects require every property and set `additionalProperties` false; nullable unions keep null. The installed SDK 0.37.1 accepts the model, temperature floor, schema name, and strict `json_schema` parameters, and it does not enumerate the strict-schema subset. No local defect was confirmed, and request construction was not changed. The preserved pilot artifact was not modified. The five source documents are 173–826 characters, so the shared HTTP 400 is not explained by context length. Nullable `$ref` unions, the 34-property case object, and the 14,551-byte schema remain hypotheses until one authorized provider response supplies `error_code`, `error_param`, and a sanitized message. Targeted tests: 109 passed. Full suite: 846 passed, 5 skipped, 0 failed. The dry-run made 0 provider calls and wrote 0 files.

---

## 2026-10-01 - extraction failures retain allowlisted gateway diagnostics

A local terminal log identifies the failed pilot command and five gateway lines of `invalid_request` with HTTP 400. The preserved artifact at `data/interim/phase5/pilot/fc97bf40783c` still has only generic `provider_error` rows. New persistence cannot reconstruct diagnostics that run did not store, and the directory was left unchanged.

Extraction failure rows and stage events now keep the existing allowlisted diagnostic. String fields that contain source text or a credential are omitted, while category and HTTP status stay. `test_provider_diagnostic_persists_status_without_source_or_credentials` proves that with a mock. Targeted extraction and gateway tests: 109 passed. Full suite: 846 passed, 5 skipped, 0 failed. The pilot dry-run made 0 provider calls and wrote 0 files. `git diff --check` exited 0. No live retry, quality claim, or M1 claim is made.

---

## 2026-10-01 - existing failed pilot artifact inspected offline

Read-only inspection found an existing live-mode pilot artifact at `data/interim/phase5/pilot/fc97bf40783c`. Its manifest records five provider attempts, five generic `provider_error` failures, zero cases, and zero token usage. No stored HTTP status or detailed diagnostic establishes the cause. Gateway invocation counts do not prove requests reached the external service. The artifact was preserved. No provider calls were made during this inspection; any retry requires separate authorization and a fresh output parent. Offline controls remain verified by the previously recorded 845 passed / 5 skipped suite.

---

## 2026-10-01 - synthetic evidence-isolation fixtures corrected

The evidence-isolation tests now bind their synthetic relevance spans to the target document and decision owner. No production code or shared fixture helper changed. Focused tests: 3 passed. Full suite: 845 passed, 5 skipped, 0 failed, superseding the failed run below. The repeated pilot dry-run made 0 provider calls, wrote 0 files and preserved the manifest bytes. The planned live output directory `data/interim/phase5/pilot/fc97bf40783c` already exists in the workspace and was left untouched; its existing-directory guard prevents reusing it. Any separately authorized future run needs a fresh output parent. No live execution was performed in this follow-up and no quality or M1 claim is made.

---

## 2026-10-01 - extraction pilot verified offline

The restored virtual environment ran the offline pilot checks. These counts are from that run and are not the earlier 841 passed / 5 skipped or 107 targeted results.

`run_extraction_pilot` refuses any existing run-specific directory before a provider call, including a partial directory with no `run_manifest.json`. `test_pilot_rejects_partial_existing_output_before_calls` covers that case with a mock provider and 0 calls. Targeted extraction and gateway tests passed 108. The full suite was 3 failed, 842 passed, and 5 skipped. The failures are in `tests/test_extraction_evidence_isolation.py`: `make_decision` leaves the evidence span on `reddit-000000000001` when the decision id is overridden, so `RelevanceDecision` rejects the synthetic documents. That failure is unresolved.

The same five development documents remain selected: `google_support-d7f386f347b7` and `google_support-e1e5277da7e8` are the first agreeing core seats by `doc_id`; `reddit-23be97c93709` and `reddit-c49086caf891` are the validated human adjacent decisions; `google_support-2a080da4b930` is the first remaining agreeing adjacent seat by `doc_id`. The dry-run made 0 provider calls and wrote 0 files. The pilot manifest hash was unchanged, and `data/interim/phase5/pilot` was not created. The configured call is still Groq `openai/gpt-oss-120b`, `extract/v1`, strict structured output, SDK retries disabled, one gateway attempt, a five-request cap, and `data/interim/cache`. A missing key is rejected before output creation, fatal authentication stops the run, and an existing output directory is refused. No extraction quality is claimed, and milestone M1 is not complete. The live command was not run.

---

## 2026-10-01 - five-document extraction pilot prepared offline

The output-directory guard rejects an existing pilot directory even when it lacks `run_manifest.json`. Its mocked regression test was added with that preparation. The suite totals in this entry are the earlier preparation run, not the later verification.

The existing extract command can plan a five-document development pilot without opening a second extraction path. Unrestricted live extraction stays refused. The pilot manifest is `data/interim/phase5/extraction_pilot_manifest.csv`: `google_support-2a080da4b930`, `google_support-d7f386f347b7`, `google_support-e1e5277da7e8`, `reddit-23be97c93709`, and `reddit-c49086caf891`, with document id and split metadata only. The two reddit rows are the validated human adjacent decisions. The other three seats are the first agreeing core and adjacent documents by `doc_id`. `google_support-3d15a7ae4cd0` and `google_support-5b2ec98df32b` stay out, and their labels were not edited.

The bounded call is Groq, `openai/gpt-oss-120b`, `extract/v1`, strict structured output, SDK retries disabled, one gateway attempt, and at most five external requests. The existing cache is `data/interim/cache`. A future live run would write `data/interim/phase5/pilot/fc97bf40783c` only when `GROQ_API_KEY` is present. The dry-run made 0 provider calls and wrote 0 files. No extraction quality is claimed, and milestone M1 is not complete. Live execution was not authorized and was not run.

---

## 2026-10-01 - extraction stage wired through the existing pipeline

`extract/v1` is registered beside `relevance/v5`. The `run --stages extract` command uses the candidate manifest and the effective relevance decision. A validated human decision takes precedence. The pending waterfall decision does not. The gateway owns completion, cache, repair, retry, and usage. Valid cases are the only analysis-ready rows. Failures stay in the extraction failure file and the review queue.

No live extraction ran. Dry-run wrote nothing and made 0 provider calls. The null-provider run recorded unavailability for 18 eligible documents and wrote 0 cases under `data/interim/phase5/8a6c025fdfce`. `google_support-3d15a7ae4cd0` remains blocked. Five other eligible decisions still disagree with the approved seed labels; neither side was edited. Phase 4 remains in progress, Phase 5 integration is in progress, and milestone M1 is not complete.

---

## 2026-10-01 - human relevance overrides for extraction

Human relevance overrides are append-only and keep the original decision id, the approved scope and reason, the researcher, the rationale, the approval provenance, and a target quote. The human decision is separate: `decided_by` is human, model name and prompt version are null, and confidence is null unless the researcher supplies it. Evidence goes through the existing ladder. An unvalidated or unsupported quote stays pending and does not replace the model decision.

The three blocked candidates in run `01455c8aab03` were reconciled from the approved seed labels. `reddit-23be97c93709` and `reddit-c49086caf891` now have validated human decisions. `google_support-3d15a7ae4cd0` stays pending because the reply text does not support the known-item journey without the parent. Eighteen of 19 extraction candidates have an eligible effective decision. The model decisions and the model-only evaluation were not changed. No provider was called. Extraction has not run. Phase 4 remains in progress, and Phase 5 has not started.

---

## 2026-09-30 - extraction handoff prepared offline

The completed `relevance/v5` development run
`data/interim/phase4/development/01455c8aab03` was checked offline against
the approved labels. Stored totals match the recorded checkpoint: 35
targets, 6 cache hits, 29 external attempts, 34 valid decisions, 1
abstaining technical failure, 0 missing predictions, scope 28/35, reason
22/35, core recall 8/8, and core precision 8/11.

`extraction_handoff.md` records the six scope disagreements, the one
technical failure, the six reason-only disagreements, evidence-support
limits, supplied parent context, and the two cross-split families.
`extraction_candidate_manifest.csv` lists 19 development records approved
as core or adjacent, with document id and split metadata only. Three of
those records are stored as out of scope or `provider_error` and do not
satisfy extraction's current valid in-scope prerequisite. No override,
decision rewrite, prompt change, or provider call was made. The holdout
stays locked. Phase 4 remains in progress. Extraction has not run, and
Phase 5 has not started.

---

## 2026-09-30 - relevance/v5 development evaluation

One live classification of the frozen 35 development records ran at
`data/interim/phase4/development/01455c8aab03`. The command used Groq,
`openai/gpt-oss-120b`, `relevance/v5`, the existing cache, `--call-budget 35`,
and `--max-retries 1`. It was not repeated. The prompt, labels, notes,
manifests, and decoding settings were not changed.

The run made 6 cache hits and 29 external attempts. Thirty-four decisions are
valid. `reddit-c49086caf891` is one `provider_error` after a single HTTP 400
JSON-validation failure. There are 0 missing predictions. This run recorded
88929 input tokens, 39145 output tokens, and an estimated list price of USD
0.036826. Actual billed cost is unknown. The six cache hits are the earlier
v5 smoke responses; their historical token totals are not part of this run.
The account is paid.

The existing evaluator scored these 35 decisions against the approved labels.
Overall scope agreement is 28/35 and exact reason agreement is 22/35. Core
recall is 8/8 and core precision is 8/11. Compared with the adjudicated v4
evaluation, 12 predictions are unchanged, 12 agree on more fields, 7 agree on
fewer, and 4 change with no net agreement gain. The holdout was not evaluated.
This is development evaluation, not product performance. Phase 5 has not
started.

---

## 2026-09-30 - relevance/v5 development smoke

One live development smoke ran at
`data/interim/phase4/smoke/3417ebc5ea87`. The command was
`.\.venv\Scripts\python.exe main.py smoke`. Provider and model stayed Groq
and `openai/gpt-oss-120b`. The prompt stayed `relevance/v5` and was not
tuned. Six unique development targets were classified: 6 external attempts,
0 cache hits, 6 valid decisions, 0 failures, and 0 unattempted records.
The budget was 6. This run recorded 19033 input tokens, 10392 output tokens,
and an estimated list price of USD 0.00909. Actual billed cost is unknown.
The account is paid.

The earlier v4 smoke at `data/interim/phase4/smoke/10aa3135aaea` was not
modified and was not a cache hit. Its historical 16309 input tokens, 5236
output tokens, and USD 0.005588 estimate are separate from this run.

On these six approved labels, v4 agrees on scope for 6/6 and reason for 3/6.
v5 agrees on scope for 5/6 and reason for 5/6. The specific praise exclusion
and the approved transcript and Camaro reason codes are the gains. The
waterfall reply, whose development parent was supplied, is the scope loss.
Transcript and Camaro boundary uncertainty remains. The other 29 development
records were not treated as missing. No holdout text was read, the holdout
was not unlocked, and Phase 5 has not started. This is development feedback,
not unbiased product performance.

---

## 2026-09-30 - relevance/v5 prepared offline

Phase 4 remains in progress. `relevance/v5` is the registered relevance
prompt. It has not been evaluated with live predictions. No provider was
called, and no smoke or development classification was run.

The revision states general reason-selection rules: a failed formulated
search is not inability to formulate a query; known photos and sets do not
need a filename; core requires supported incomplete recall or difficulty
expressing cues; a feature request or organization request can still be a
retrieval problem; missing, lost, and recovery wording do not prove a cause;
and evidence must support the decision rather than only be verbatim.
Approximate ranges and named-object boundaries are not universal rules.
Document ids, expected answers, and human notes are not in the prompt.

The version bump changes the cache key and the holdout prompt hash. Older
locks and cache entries stay valid for their own versions and are not reused
for v5. Groq, `openai/gpt-oss-120b`, strict schema, the per-request doc_id
enum, nullable offset keys, application validation, parent-context
safeguards, SDK `max_retries=0`, and the call budget are unchanged. Review
routing and the 0.7 confidence cutoff are unchanged. The holdout was not
unlocked. Phase 5 has not started.

`.\.venv\Scripts\python.exe -m pytest -q` passed 752, with 5 skipped.

---

## 2026-09-30 - Approved development adjudication integrated offline

The researcher approved all 21 development adjudications. Thirteen labels
were retained, seven reasons corrected, and the airshow scope and reason
corrected. Eight rows changed by `doc_id`; all source/generated fields,
original notes, row order and unreviewed labels remain unchanged.
All 50 rows validate: 12 core, 15 adjacent and 23 out of scope.

Pre-adjudication and adjudicated snapshots, the approval ledger, comparison
and new evaluation are local and ignored under
`data/interim/phase4/development/051b96043d3e/adjudicated-2026-09-30/`.
Historical run artifacts and split/smoke manifests are preserved. Membership
is still 35/15; development labels are now 8 core, 11 adjacent and
16 out of scope. The manifest's original strata remain a creation snapshot.

The offline evaluator loads an existing valid manifest and checks document-ID
coverage without deriving a new split from corrected labels. Initial split
creation and all holdout, prompt-lock and smoke controls remain unchanged.
Two regression cases prove byte-identical manifest preservation and rejection
of changed document identity, with network connections blocked.

Reevaluation of the same 35 stored decisions keeps scope agreement at 25/35
and changes reason agreement from 14/35 to 17/35. Core precision remains
7/13 and recall 7/8. Ten scope and eight additional reason disagreements
remain. This is development adjudication, not model improvement or final
product performance. Zero new provider calls are distinguished from
historical classification usage.

Targeted:
`\.venv\Scripts\python.exe -m pytest tests/test_relevance.py tests/test_relevance_evaluation.py tests/test_relevance_governance.py tests/test_pipeline_runner.py -q`
passed 46.
Full: `\.venv\Scripts\python.exe -m pytest -q`
passed 751, with 5 skipped.

No provider was called. The approved corrections were the only label edits;
original notes are retained, with current rationale in the separate ledger.
No prompt, schema, routing rule, split membership or historical decision
changed. No holdout text was inspected for adjudication, no holdout evaluation
or unlock occurred, and no commit was made. Phase 4 remains in progress;
Phase 5 has not started.

---

## 2026-09-30 — Groq adapter for the Phase 4 relevance smoke

Phase 4 remains in progress. Phase 5 has not started. No live provider was
called. The holdout was not unlocked.

ADR-31 adds Groq as a provisional relevance provider. Anthropic stays
implemented. The smoke configuration is `groq` and `openai/gpt-oss-120b`,
with `GROQ_API_KEY`. JSON Schema mode does not skip application validation.
A requested temperature of 0 is sent as `1e-8`, and that floor is part of the
Groq cache key. Retries count toward the six-call budget, and only when the
remaining budget is greater than the number of documents not yet attempted.
With six documents, each gets one attempt. Invalid credentials stop the run.
List price for `openai/gpt-oss-120b`, retrieved 2026-09-30 from Groq's
published price, is USD 0.15 input, USD 0.075 cached input, and USD 0.60
output per million tokens. Actual billed cost stays unknown unless the
provider reports it. Free-tier usage is not assumed.

The Groq client is constructed with `max_retries=0`. The completion request
has no retry override, so the gateway remains the only retry controller.
The declared dependency stays `groq>=0.13,<1`. That bound resolves to
0.37.1. The previously installed 1.7.0 was outside the bound and was
replaced with 0.37.1. A mocked HTTP 429 produces one SDK request.

One live smoke, `data/interim/phase4/smoke/29e62a353084`, made six external
attempts and zero cache hits. Every document is `provider_error` with a
null scope. No holdout document was classified. That run did not keep an
HTTP status, exception class, or request id. Later failures can store an
allowlisted diagnostic: category, SDK class name, HTTP status, provider
error type, and request id. The public message stays generic. USD 0.00 on
that run means no token counts were recorded, not that billing was verified.

The Groq adapter now copies the application schema into the strict wire
schema. `EvidencePayload` on that wire schema requires `quote`, `start_char`,
and `end_char`, and the offsets stay nullable. Application validation is
unchanged. The transmitted-schema digest is part of the Groq cache key and
of a Groq prompt lock. Older cache files stay in place and are not reused.
One development document, `app_store-5e60a403ce06`, was then classified
once. The provider returned HTTP 400 `invalid_request_error`. The run was
not repeated. A second single-document attempt kept the sanitized
`error.message`: the generated object omitted `start_char` and `end_char`.
That attempt was not repeated. The relevance prompt was then `relevance/v3`. Groq requests embed the same
strict schema they send. That schema requires both offset keys, with null
when an offset is unknown, and limits `doc_id` to the document being
classified. One diagnostic of `app_store-5e60a403ce06` validated as
`out_of_scope`. The six-document development smoke then ran once at
`data/interim/phase4/smoke/c89938c1af59`. It made 5 external attempts and
1 cache hit. All six decisions are valid. Scope agreed with the approved
labels on 4 records and reason codes on 2. The prompt was not tuned
afterward, and the holdout was not unlocked.

`relevance/v4` then added general scope rules and, for a development parent
only, separated parent context. One development smoke ran at
`data/interim/phase4/smoke/10aa3135aaea`: 6 external attempts, 0 cache hits,
6 valid decisions. Scope agreed on 6 of 6 and reason codes on 3 of 6,
against the same approved labels. Input tokens were 16309, output tokens
5236, and the estimated list price was USD 0.005588. Actual billed cost is
unknown. The parent of `google_support-3d15a7ae4cd0` is development document
`google_support-808ba579f266` and was sent as separate context. Threads
`1px47il` and `xl693t` cross the development/holdout boundary. That limit
was recorded and the split was not changed. Holdout text was not sent.
This comparison is development feedback, not an unbiased performance
estimate. Phase 5 has not started.

The same `relevance/v4` configuration then classified all 35 development
documents once, at `data/interim/phase4/development/051b96043d3e`, with the
existing cache, one gateway attempt per document, and a cap of 35 external
calls. Six cache hits reused the smoke responses. Twenty-nine external
attempts produced the run's tokens: 79093 input, 26821 output, estimated
list price USD 0.027957. Actual billed cost is unknown. All 35 decisions
are valid. Scope agreed on 25/35 and reason codes on 14/35. Core precision
was 7/13 and core recall 7/8. The waterfall seed row stores the reply only;
the human review used the linked parent thread, and the model received that
development parent. Threads `1px47il` and `xl693t` still cross the split.
This is a development evaluation. The holdout was not evaluated.

---

## 2026-09-29 — Phase 4 holdout protection and smoke preparation

Phase 4 remains in progress. Phase 5 has not started. No live model was
called. The 15-record holdout has not been used for prompt tuning. No Phase 4
seed result is final product performance.

ADR-30 clarifies ADR-25. `relevance-seed-split/v1` is a 35/15
scope-stratified prompt-development split. It does not replace the Phase 6
hash-based gold split. Covered-only class metrics use `ok` predictions.
Non-ok decisions and null scopes are abstentions. They stay in the overall
accuracy denominator, together with missing predictions.

Live relevance classification defaults to development records. Holdout
classification requires `--holdout-unlock` and a prompt lock of configuration
hashes, not labels. `python main.py smoke --dry-run` plans the six
development documents and makes 0 provider calls. A live smoke writes a new
directory and does not merge into the historical null-provider decisions.
The provider-call budget is six.

Targeted tests: `pytest tests/test_relevance.py tests/test_relevance_evaluation.py tests/test_pipeline_runner.py -q` → 36 passed. `pytest tests/test_relevance_governance.py -q` → 8 passed. Full suite: `pytest -q` → 710 passed, 4 skipped.

---

## 2026-09-29 — Phase 4 relevance evaluation preparation

Phase 4 remains in progress. Phase 5 has not started. No live or paid model
was called. The 15-record holdout has not been used for prompt tuning. No
performance claim is supported.

The approved seed sheet is split by `doc_id` under version
`relevance-seed-split/v1`. Development has 35 documents: 8 core, 10
adjacent, and 17 out of scope. Holdout has 15: 4 core, 4 adjacent, and
7 out of scope. Within a scope class, ids are sorted and holdout seats are
`floor(i * n / k)`. A valid manifest is preserved. An invalid one is
rejected and left in place. The manifest is
`data/interim/phase4/relevance_split_manifest.csv`.

`python main.py evaluate --split development|holdout|all` scores stored
decisions against the approved labels. It does not classify and it does not
call a provider. Reports are `relevance_evaluation.json` and
`relevance_evaluation.md` in the same directory. A null scope or a non-ok
technical state is an abstention, kept in the overall-accuracy denominator.
Covered-only accuracy is separate. Missing predictions are listed. Unknown
document ids fail validation.

The stored decisions are still the null-provider run: 35
`provider_unavailable` rows and 15 documents with no decision. Scoring
`all` reports abstention 1.0, technical-failure rate 0.7, overall accuracy
0.0, 0 provider calls, 0 tokens, and estimated cost 0. That is the stored
baseline, not a model score.

This split is not the ADR-25 gold split. ADR-25 uses a hash of `doc_id`,
about 40/60, stratified by platform and scope, and it drops non-ok rows
from every metric. Those rules were not applied here.

Targeted tests: `pytest tests/test_relevance.py tests/test_pipeline_runner.py -q` → 26 passed. `pytest tests/test_relevance_evaluation.py -q` → 10 passed. Full suite: `pytest -q` → 696 passed, 4 skipped.

---

## 2026-09-29 — Phase 4 seed review completed for 50 records

Phase 4 remains in progress. Phase 5 has not started. No live or paid model
was called.

The remaining 15 blank rows in `data/interim/phase4/relevance_seed_review.csv`
now have human scope, reason, and notes. The 35 labels approved on
2026-09-27 were not changed. Source columns were not changed. The sheet has
50 unique document ids: 12 `core_incomplete_recall`, 14
`adjacent_known_item_retrieval`, and 24 `out_of_scope`. Every human field is
filled. Inclusion codes are used only with core and adjacent. Exclusion codes
are used only with `out_of_scope`. No review code or free-text reason is
present.

`python main.py run --stages prefilter --offline` on 2026-09-29 kept all 50
rows and all 50 human decisions, matched by `doc_id`. Provider calls: 0.

Targeted tests: `pytest tests/test_relevance.py tests/test_pipeline_runner.py -q` → 26 passed. Full suite: `pytest -q` → 682 passed, 4 skipped.

---

## 2026-09-27 — Phase 4 seed review integrated

Phase 4 remains in progress. Phase 5 has not started. No live or paid model
was called.

The researcher completed `data/interim/phase4/relevance_seed_review.csv` on
2026-09-27. The sheet has 35 rows: 4 `core_incomplete_recall`, 12
`adjacent_known_item_retrieval`, and 19 `out_of_scope`. Every document id is
unique. Every human scope, reason, and note is filled. Inclusion codes are
used only with core and adjacent. Exclusion codes are used only with
`out_of_scope`. No review code or free-text reason is present. The approved
labels were not edited.

An offline `prefilter` rerun preserves those three human fields by `doc_id`.
Regenerated source columns matched the reviewed sheet. A blank or repeated
`doc_id` is now rejected, and the existing file is left in place.

The pilot has fewer core incomplete-recall cases than intended. Collect 8–12
additional strong core cases before treating the dataset as sufficiently
balanced.

`RelevancePayload` still accepts a review reason code on a scoped response.
`RelevanceDecision` rejects that pairing. That gap is recorded and was not
changed here.

Targeted tests: `pytest tests/test_relevance.py tests/test_llm_gateway.py tests/test_pipeline_runner.py tests/test_architecture.py -q` → 166 passed, 4 skipped. Full suite: `pytest -q` → 682 passed, 4 skipped.

---

## 2026-09-27 — Phase 4A offline infrastructure

Phase 4 is in progress and is not complete. Phase 5 has not started. No
Anthropic, OpenAI, or other paid classification was run.

The runner now accepts `prefilter` and `relevance`, including `--limit`,
`--dry-run`, `--resume`, and `--offline`. Dry-run writes nothing and calls
no provider. A missing key or `--offline` uses the null provider and records
`provider_unavailable` with null scope and empty evidence. Those rows are
not counted as `out_of_scope`.

Ruleset `prefilter/v1` routes a document to the classifier unless at least
two distinct multi-word exclusion signals match and the text has no
retrieval language. One keyword cannot drop a document. Mixed retrieval and
backup or deletion language continues. The result is routing, not a research
claim. Confirmed duplicates are skipped. `raw_text` and Phase 3 derived
records are not modified.

Prompt `relevance/v1` asks for `doc_id`, scope class, a controlled reason
code, a short summary, confidence, and a verbatim evidence span. It does not
ask for `is_relevant`. The user post is quoted as untrusted data. Evidence
for an `ok` decision, including `out_of_scope`, goes through the existing
evidence ladder. Fabricated or ambiguous spans become technical failures
with empty evidence and a review item. Syntax-only JSON repair does not
change values.

The relevance cache key includes provider, model, decoding parameters,
prompt version, schema version, ruleset version, and content hash. It does
not include taxonomy version. A hit makes no provider call. The cache
refuses to store an API key or the author salt.

Review uses the existing append-only queue. Items open for low confidence
(below 0.7), a prefilter/classifier contradiction, missing or ambiguous
evidence, an unsafe span, or output that is still invalid after repair.
Earlier resolutions are preserved.

Pilot, offline, 35 documents: 35 routed to classify, 0 obvious exclusions,
0 mixed-signal retains, 0 single-signal retains, 0 confirmed duplicates
skipped. Dry-run wrote 0 files and made 0 provider calls. The null provider
wrote 35 `provider_unavailable` decisions, 0 provider calls, 0 tokens, and
estimated cost 0. No response was cached.

`data/interim/phase4/relevance_seed_review.csv` has 35 rows and blank human
fields. It has no model prediction. It is not the Phase 6 gold set. Labeling
is pending.

Targeted Phase 4 tests and the full suite passed: 678 passed, 4 skipped.

---

## 2026-09-27 — Phase 3 closed: pilot calibration recorded

Phase 3 is complete. Phase 4 has not started. Thresholds, matching, canonical
selection, duplicate links, the operational review queue, and funnel counts
are unchanged.

The researcher reviewed all 10 nearest negative controls in
`data/interim/phase3/duplicate_calibration.csv` and marked each `distinct`.
No pair was in Hamming 0–3 or 4–6. The controls were distances 21–23. ADR-11
now records that the 3/6 band is retained provisionally. The pilot has no
positive duplicate examples, so duplicate recall is not estimated. Calibration
repeats on the scaled corpus.

A rerun keeps `researcher_decision` and `researcher_notes` for the same two
`doc_id` values, in either column order. Blank, `distinct`, and `duplicate`
are the only accepted decisions. An invalid value is rejected and the existing
file is left in place. Calibration decisions do not create links or
review-queue items.

Targeted tests: 130 passed. Full suite: 612 passed.

---

## 2026-09-27 — Phase 3 calibration sheet

Phase 3 stays in progress. ADR-11 is not amended. Duplicate detection,
thresholds, canonical selection, link assignment, and the review queue are
unchanged.

`duplicate_review.csv` remains the operational queue and lists only
`DuplicateLink` rows. The pilot queue is still header-only: no pair is inside
Hamming 0–3 or 4–6.

`data/interim/phase3/duplicate_calibration.csv` is a separate local sheet. It
contains every in-band pair, plus the 10 nearest pairs farther than the review
band. The pilot sheet has those 10 controls. Distances start at 21. Researcher
decision and notes are blank. Excerpts come from `raw_text_audit`. The controls
are not links, are not counted as duplicates, and do not open review items.
Human review of the sheet is still pending.

---

## 2026-09-27 — Phase 3 dedupe audit

Phase 3 stays in progress. ADR-11 and ADR-21 were not amended.

### Canonical selection

Unchanged. The current Phase 3 plan, ADR-20, spec Section 26.1, and
`DuplicateLink.canonical_doc_id` all select the lowest `doc_id`. They reject
first-collected because `collected_at` follows ingestion order. A null
`collected_at` cannot reach dedupe: import requires the timestamp, and the
model field is not optional. `doc_id` is the tie-break only in the sense that
it is the whole rule; equal timestamps do not switch the comparison over to
collection time.

### Exact content

Unchanged, and it already matches the plan. Identical `content_hash` values
always produce one `exact_text` link per non-canonical member. Both documents
stay stored. Different `author_hash` values do not remove that link. Spec
Section 19.6 and ADR-21 say the link is `pending_review` with
`different_authors_identical_text` rather than `auto_confirmed`. That is the
written safety rule, not a new exemption from content-hash grouping.

### Cross-post

Corrected. `author_hash` is `HMAC(salt, source_platform | username)`, so it is
platform-scoped. Equal hashes across platforms are not produced for one
username and are not treated as proof of one person.

The deterministic rule: different platforms plus an exact or near content
match, and not a quoted repeat, is `cross_post`. It is never
`auto_confirmed`. When the stored hashes differ, the reason is
`different_authors_identical_text`. When they match or an author is missing,
the reason is `low_confidence`. Quoted repeats stay `quoted_repeat`. Short
text still fails the token minimum first. Hamming 4–6 on one platform stays
in the review band.

### ADR names

The Hamming 3/6 band is ADR-11, retained as the ADR-21 default. The token
minimum and the cross-author guard are ADR-21. `config/analysis.yaml` now
says that. Calling the safety package ADR-21 is correct; ADR-11 is superseded
and was not renamed in `DECISIONS.md`.

---

## 2026-09-27 — Phase 3 started: normalization and deduplication

Not complete. ADR-11 and ADR-21 are unchanged. No relevance, extraction,
taxonomy, analysis, retrieval, or Streamlit work.

### Added

- **`src/normalize/`** — NFKC and whitespace collapse, length-preserving
  redaction (`#` masks, same character length), offline canonical URLs, word
  `token_count`, 64-bit simhash, and `content_hash` via the existing helper.
  `language_detected` carries `language_reported` when no detector is
  available. `CollectedDocument` and `raw_text` are not modified.
- **`src/dedupe/`** — exact, near, cross-post, quoted-repeat, and
  same-source-item links. The canonical document is the lowest `doc_id`.
  Safety conditions come from `config/analysis.yaml`. A shared listing or
  thread URL does not create a link. Documents are not deleted.
- **`src/review/queue.py`** — open items for pending links. Resolution appends
  a row.
- **`src/pipeline/runner.py`** and `main.py run --stages normalize,dedupe`.
  Outputs are JSONL plus `duplicate_review.csv` under `data/interim/phase3/`,
  which is gitignored. Timestamps are the ruleset instant, so a second run
  matches byte for byte.
- **Tests** in `tests/test_normalize.py`, `tests/test_dedupe.py`, and
  `tests/test_review_queue.py`. Targeted: 27 passed. Full suite: 606 passed.

### Pilot

35 documents derived. 0 redaction spans. 0 duplicate links. 0 pairs at
Hamming 0–3 and 0 at 4–6 (minimum distance 21). The review CSV has a header
and no pairs. Calibration is still pending; this run does not amend ADR-11.

### Interpretations

1. **Canonical selection follows ADR-20, not first-collected.** The
   `DuplicateLink` contract and `canonical_doc_id()` already define the lowest
   `doc_id`. Collection time is not a tie-break.
2. **Same-source-item is platform identity, not URL equality.** Two records
   that share a listing or thread URL and have different `source_item_id`
   values stay distinct. A share link is the same item only when one side has
   no item id and that id is present in both canonical URLs.
3. **No SQLite projection in this slice.** Phase 2's local output is JSONL.
   Derived rows, links, stage events, and the review queue are JSONL in
   `data/interim/`. The prevalence views are not built yet.
4. **Redirects that need a network call are not resolved.** Canonical URLs
   fold known share hosts and drop tracking parameters offline.

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
