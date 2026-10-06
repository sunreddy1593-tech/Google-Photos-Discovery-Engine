# Status

Scheduled catch-up, 2026-10-06: the existing 08:00, 14:00 and 20:00 Windows
tasks now enable StartWhenAvailable, require a network and queue overlapping
instances. The shared Windows mutex in `scripts/run_queued_discovery.py`
serializes research and publication across the three tasks. A missed task
can start after the computer is awake and Sunayana signs in, subject to the
Windows catch-up delay; every historical missed occurrence is not guaranteed.
Times, interactive logon, request budgets and collection/model stages remain
unchanged. Original task XML is backed up locally before settings changes.
Verification: all three installed tasks report catch-up/network enabled and
Queue; triggers, principals, actions and other settings match their saved XML.
Focused tests: 29 passed with mocked research/publication and an isolated
Windows mutex test. Full suite: 1329 passed, 5 skipped; diff check clean.
No live research run was manually triggered. See `docs/cloud-snapshots.md`.

Automatic Cloud snapshot publication, 2026-10-06: the existing scheduled command
now runs `scripts/publish_cloud_snapshots.py` after successful/partial research
runs. Enabled for the existing GitHub remote/main in `config/cloud_publication.json`.
Only privacy-scanned public snapshots are committed from an isolated sparse
checkout; private and unrelated staged work stays local. Publication failure
preserves the research exit code and the last Cloud snapshot. Status is recorded
at `data/interim/cloud-publication/CURRENT.json`. No new scheduled task, n8n
change, collection/model call or budget change. See `docs/cloud-snapshots.md`.
Verification: full suite 1324 passed, 5 skipped; diff check clean. A live
publication-only check authenticated to GitHub and returned `unchanged` for
the already deployed snapshots, with no collection or model call.

Streamlit Cloud snapshot fix, 2026-10-06: added privacy-scanned deployment copies
of the current scheduled and automated-comparison snapshots under
`data/exports/public/cloud-snapshots/`. The app prefers local snapshots and
falls back to these tracked copies on Cloud, with a saved-deployment notice.
Refresh retains snapshot-aware caching. Automatic publication added later
packages and pushes subsequent local results; the scheduler does not run on Streamlit Cloud. See
`docs/cloud-snapshots.md`. No integration, scheduler or private-data changes.
Validation: focused suites 316 passed, 5 skipped; full suite 1311 passed,
5 skipped; `git diff --check` clean.
Cloud verification showed both snapshots and a working Refresh button. Fixed
an additional comparison rendering mismatch: buckets now read `core`/`adjacent`
from the snapshot (3/2 cases), with a focused UI regression test.

Streamlit Cloud, 2026-10-05: the live app failed at import with
`ModuleNotFoundError: No module named 'pydantic'`. Community Cloud installs
`requirements.txt`, which did not list pydantic. `pydantic>=2.8,<3` is now in
that file. Reboot the app if the push does not start a rebuild on its own.

Human-reviewed n8n reference standard, 2026-10-05: the 48 n8n threads that
Sunayana reviewed in detail are recorded as an immutable reference,
`data/exports/reference/n8n-reviewed-reference-01/` (version
`n8n-reviewed-reference/01`, built from the saved export
`n8n/discovery_sheet_template - insights.csv`, 48 records, 23 retrieval
problems, 25 not; her statement in the implementation conversation is the
approval basis; review date not stated). The three later threads in
`data/insights_seed.csv` are listed as not covered. Future records are
assessed against that standard by `src/export/reference_standard.py` with
deterministic evidence checks and published atomically to the gitignored
`data/exports/public/reference-standard-snapshot/`. The Streamlit "Reference
standard" section shows "Human-reviewed reference" and "Automatically
classified using the human-reviewed standard" as separate views with separate
counts; the automated view never sets semantic approval and claims no
accuracy. Current snapshot `d92016973f6e0260`: 16 cases assessed, 5 eligible,
2 flagged, 9 failed or incomplete, 0 scheduled sub-batches yet. The scheduler
refreshes the snapshot best-effort after publishing its own; budgets, prompts,
schema and model are unchanged. No n8n workflow, webhook, sheet or integration
file was touched or called. Full suite: 1302 passed, 5 skipped, 0 failed.
Details: `docs/n8n-reviewed-reference-standard-2026-10-05.md`.

Bug fixes, 2026-10-05: collection no longer refetches replies whose stored
count is already complete and unchanged. The scheduler passes that reply state
into the collector, and the parent manifest is written after the run status is
final. `src/collect/scaled.py` no longer imports `src.analyze`. The reference
app test uses the radio control the app actually renders. Full suite: 1267
passed, 5 skipped, 0 failed.

The 08:00 task `1f80baf403e0` finished before this fix. It used 20 collection
requests, wrote 0 new documents, and recorded 87 comments already present.
Status was partial, shortfall 50. Those 20 requests stay consumed. The 14:00
and 20:00 tasks will use the corrected collector. No extra live run was started.

Scheduled non-n8n runs, 2026-10-05: three Windows tasks are enabled and have
not run. Each launches
`C:\Users\sunayana\Downloads\Google Photos discovery engine\scripts\run_scheduled_discovery.cmd`,
which changes to the project directory and runs
`C:\Users\sunayana\Downloads\Google Photos discovery engine\.venv\Scripts\python.exe`
on `main.py schedule`. Local times are 08:00, 14:00 and 20:00; the machine
timezone is India Standard Time, so those times are Asia/Kolkata. Next runs
are 05-10-2026 08:00:00, 14:00:00 and 20:00:00. Logon mode is interactive only.
At initial registration, catch-up was disabled; the 2026-10-06 update above
enables it. Battery start and stop restrictions are
off. The first registration split the path at the space in `Google Photos`;
that registration was replaced before any task ran. The verified command is
the full `.cmd` path, with working directory
`C:\Users\sunayana\Downloads\Google Photos discovery engine`.

Pause one task with `schtasks /Change /TN "GooglePhotosDiscovery-0800" /DISABLE`
(same form for `GooglePhotosDiscovery-1400` and `GooglePhotosDiscovery-2000`).
`/ENABLE` turns it back on. `schtasks /End /TN "..."` stops a running task.
`schtasks /Delete /TN "..." /F` removes it. The computer must be awake and
Sunayana logged on, with network access. `.env` must still contain
`YOUTUBE_API_KEY`, `AUTHOR_SALT` and `GROQ_API_KEY`. The seed file
`config/youtube_seed_videos.txt` and frozen split
`data/interim/phase4/relevance_split_manifest.csv` must remain. Those inputs
were present for the dry-run. No credential value is recorded here.

Bounds for each run: 50 new unique documents, split 20/20/10, 20 collection
requests and 100 model attempts. Across the three daily runs: 60 collection
requests and 300 model attempts. One gateway attempt per uncached document per
stage. SDK retries stay off. Cache hits consume no request budget. The ledger
is `data/interim/scheduler/budget-ledger.json`. Run output is
`data/interim/scheduled-runs/{run_id}/`. The public snapshot is
`data/exports/public/scheduled-snapshot/CURRENT.json` and is gitignored.
Active pins stay Groq `openai/gpt-oss-120b`, `relevance/v5`, `extract/v2`,
schema 1.0.0, temperature 0.0 and max_tokens 4096. Only the existing YouTube
comment collector is scheduled. Reddit, Google support, Play Store and App
Store are reported unavailable. n8n is excluded. `youtube.enabled` stays false.

Dry-run `df6cfde5ae72` at 2026-10-05T00:03:13+05:30 made 0 collection requests,
0 model attempts and wrote 0 records. Estimated cost was 0.000000. No
scheduler, run or snapshot directory was created. No manual live collection or
model call was made; the three scheduled times are the authorized live runs.
Focused scheduler tests: 12 passed. Full suite: 1263 passed, 5 skipped, 2
failed. Both failures are outside this change: `src/collect/scaled.py` imports
`src.analyze.funnel`, and `tests/test_reference_demo.py` looks up a
`segmented_control` named `section` while `app.py` uses `st.radio`. Git diff
--check passed with line-ending warnings only. AppTest covers snapshot refresh
and the separation of automatic validity from semantic approval. A local
Streamlit session on port 8502 showed Overview with the unpublished-snapshot
caption and Documents still at 35, then Scheduled runs with the heading
"Scheduled processing", the message "No scheduled processing snapshot has been
published.", a Refresh button, and the read-only notice. No snapshot exists
yet, so the populated metrics were not shown in the browser. No commit, push
or deploy.

Phase 7 collection, 2026-10-04: YouTube comment collection was exercised with
40 `commentThreads.list` / `comments.list` requests and wrote 266 new documents.
The deduped corpus is 318 documents across five platforms (YouTube 272, Google
support 21, Reddit 17, Play Store 5, App Store 3). YouTube is above the 40%
concentration line. Play and App Store rows are the existing manual imports.
No store or support-forum collector was added, and `search.list` was not
called. Reddit is skipped by owner direction: self-service API keys are no
longer issued, and this project will not request access. Reddit made zero
requests and stays unexercised. The 17 Reddit rows are manual imports. Collection funnel:
`data/processed/phase7-corpus-2026-10-04/funnel_by_source.json`. Relevance and
extraction were not run. `youtube.enabled` stays false. Focused collector
tests: 49 passed. No commit or deployment.

n8n corrected-node live verification, 2026-10-04 (supersedes the pending Cloud
update below): after the owner reported publishing the replacement Code node,
one bounded check of thread 106429666 returned HTTP 200, execution 15, one item
and zero failures. One webhook POST; one source fetch attested; zero model calls
attested and zero local provider calls; no retry. One CollectedDocument was
saved in a fresh community-webhook-parser-v2-check-2026-10-04-01 processed parent.
The original 489-character body matches the saved source byte-for-byte. The
author is hashed, source/date provenance validates, and replies remain unfetched.
An offline reimport dry-run writes zero duplicates and preserves record bytes.
Publication is 2021-04-16; this historical route-test post is not claimed as
recent feedback. No relevance/extraction, gold/split, cache or review change.
Prior failed execution 14 and all offline artifacts remain intact. Credential,
fresh-output and zero-call dry-run guards passed before the single request.
Focused mocked tests: 31 passed, including safe retention of all four known
parser failure codes. Full suite: 1230 passed, 5 skipped. Git diff --check
passed with line-ending warnings only. No further collection request was made. Details:
docs/n8n-parser-v2-live-check-2026-10-04-01.md.

n8n offline parser correction, 2026-10-04 (supersedes the pending fetch-output
diagnosis below): the owner supplied the saved Fetch original page JSON from
execution 14. The html field contains the thread page, but no static QAPage
block; its renderer generates that markup later. Original plain text exists at
thread_view[1][12]. Corrected collection node code preserves QAPage support and
safely decodes that JSON bootstrap, checking thread and canonical identity and
refusing unknown shapes, HTML bodies, ambiguity or reply substitution. Offline
replay recovers the exact 489-character original. Existing importer dry validation
accepts one document with zero writes. New webhook/source/model requests: 0/0/0.
Collection records written: 0. The first live failure and all prior runs, keys,
labels, cache, review decisions and quality results are preserved. Author names
are excluded from diagnostic output; source artifacts remain local-only.
The owner must replace only Extract original post with
`n8n/extract-original-post-v2.js` and publish the existing workflow. Cloud node
installation and corrected live verification remain pending. No workflow was
executed here. Focused tests: 27 passed; architecture plus collection tests:
275 passed, 5 skipped. Final full suite: 1226 passed, 5 skipped. Git diff
--check passed with line-ending warnings only. The first full suite identified an obsolete Phase 4
package-absence assertion; it now enforces saved-analysis import isolation for
the already-existing packages. No research phase or quality gate is closed by
that test correction. Details: docs/n8n-parser-fix-2026-10-04-01.md.

n8n first bounded live check, 2026-10-04 (supersedes the connection setup entry):
one authenticated POST to the dedicated collection endpoint returned HTTP 200
and contract community-collection/v1, execution 14. The workflow attests one
source-page fetch and zero model calls. It returned zero items and one handled
failure, no_verified_plain_original_post; zero documents were imported. The
client made no model call and no retry. This establishes the response contract
and successful keyed request, not successful source collection or an invalid-key
security test. The supplied ?hl=en URL and the query-free requested URL are
both retained in the plan. No thread text, label or model case was inferred.
Source extraction needs offline inspection of execution 14's Fetch original
page output; no second fetch or workflow execution was made. Diagnostic and
empty collection artifacts are preserved under the matching community-webhook-
test-2026-10-04-01 interim/processed directories. Mocked collection/diagnostic
tests: 12 passed. Prior runs, keys, labels, cache and current quality results
were retained. Details: docs/n8n-live-check-2026-10-04-01.md.

n8n connection setup, 2026-10-04: the owner supplied the dedicated production
endpoint `/webhook/discovery-original-posts-v1`. Its URL was saved in local
configuration without changing the existing key, author salt or other settings.
The bounded CLI configuration dry-run passed with one synthetic planning URL:
webhook requests 0, source-page requests 0, model calls 0, collection records 0;
the collection output parent was not created. This verifies local readiness,
not Cloud authentication, publication or source compatibility. One actual
thread URL is needed for the first bounded collection verification. The previous
integration-status metadata is preserved in the submission-preparation folder.
All unrelated current development/successor results and review decisions below
are retained. No provider or webhook request was made during this setup.

Current result, 2026-10-04, after the authorized `relevance/v6` + `extract/v4`
development run and a separate holdout successor. This supersedes earlier
2026-10-04 sentences that report development coverage 2/6, precision 0.8333,
an unmeasured `relevance/v6` candidate, or no semantic approval. Those earlier
measurements were not rewritten.

Development run `d7581cf180be` recovered 4 of 6 reference cases. Relevance
precision is 6/7 (0.8571) and passes 0.85. Schema, span, and prefilter rates
are 1.00, with 0 excluded technical failures and 12 provider calls. The YouTube
document is now out of scope. Cat relevance is accepted, and extraction then
rejected the summary span, so no cat case was stored. The poodle case is stored
and does not overlap its reference. One out-of-scope support post is predicted
adjacent. The 0.85 threshold was not lowered. Labels and saved model rows were
not edited. The earlier `extract/v3` development report remains 2 of 6 and
precision 0.8333 at `data/exports/quality/dev-v3-2026-10-04-01`. The separate
`extract/v4` experiment remains 4 of 6 with precision 0.8333 because it reused
`relevance/v5`. Report: `data/exports/quality/dev-v6-2026-10-04-01/report.json`.

The consumed holdout measurement stays 5 of 15 at
`data/exports/quality/holdout-frozen-v3-2026-10-04-01` and was not rewritten.
A separate successor on the same 25 previously exposed seats recovered 7 of 15.
Its five numeric thresholds passed, relevance recall is 1.00, and one technical
failure is excluded. Eight gold cases remain unmatched. That successor does not
replace the consumed claim. Report:
`data/exports/quality/holdout-v6-2026-10-04-01/report.json`.

Sunayana approved the five stored development cases from run `d7581cf180be`
after the disclosed disagreements were shown: older photo, sleeping video,
album, Memories, and poodle. Those disagreement lists stay on the approval
records. The poodle approval does not create an evidence overlap, so coverage
stays 4 of 6. The cat summary-quote rejection, the schema failure, and the
out-of-scope extraction skips were accepted and were not repaired.
`model_outputs_semantically_approved` stays false. The overview counter reads
the selected dataset. `development-quality-v6` in
`data/exports/submission/demo-2026-10-04-03` counts those approvals.
`development-pilot` stays at 0 because that five-document run does not contain
these cases. Active pins remain `relevance/v5` and `extract/v2`. `relevance/v6`
and `extract/v4` are measured candidates and are not the registered pins.
Current pointer: `data/exports/quality/CURRENT.json`.

Official gold is final at 35 documents and 21 cases, one reviewer, agreement
null (ADR-37). The former 75–100 labelling volume is closed. These 25 holdout
seats were previously Phase 4 development documents. M1 remains the completed
technical milestone.
Phase 6 measurement is unchanged: two development gold cases and eight
successor holdout cases remain unmatched. The five stored development model
cases now have owner approval. The cat case stays rejected.
Failure categories for the development measurement are written at
`data/exports/quality/dev-v6-failure-ledger-2026-10-04-01/failure_categories.json`.
Each category has a corrective action or an accepted limitation. That ledger
does not add labels, approve the remaining model cases, lower a threshold, or
rescore holdout. Independent agreement and all-output schema validation
remain open. Further gold labelling does not.

The read-only demonstration includes six human-approved development reference
cases, 38 minimum evidence fragments, source links and offsets, field
comparisons, memory and journey views, and saved-excerpt search. Reference
approval does not approve model outputs. The live local view is
`data/exports/submission/demo-2026-10-04-03`. The prepared Cloud folder remains
`data/exports/public/streamlit-cloud-2026-10-04-03`; no deployment was performed.
Visitors cannot trigger model spending or collection. Private sources, gold,
holdout packets, annotations, keys, and provider payloads are excluded.

Offline build for the remaining plan phases, 2026-10-04: Reddit collection
skips when credentials are absent and parses a recorded listing without a
socket. `scripts/check_credentials.py` and `scripts/audit_sources.py` report
status and concentration without printing secrets or fetching pages. Taxonomy
candidates are unnamed groupings. Assignment writes no rows while
`config/taxonomy.yaml` is `0-unassigned`. Funnel, memory map, journeys, and
opportunity components run from saved records. The composite score stays off.
Lexical retrieval returns no records below its minimum score, and citation
checks keep the evidence panel to cited records. Grounded synthesis was not
added. These modules do not collect 300 documents, name clusters, approve the
remaining model cases, or deploy the app.

Remaining submission work: import the new n8n workflow, configure Header Auth,
verify one original post, publish the Cloud package, and smoke-test its URL.
Phase 10 cluster names and composite scores are not claimed. No commit or
publication is recorded here.

The owner's earlier extract/v4-only development run used 6 of at most 20
requests; that authorization is consumed. It accepted 5 cases and left the cat
on cached relevance evidence. Recorded usage for those six calls is 76,079
input / 25,338 output tokens, estimated $0.026115. Details:
`docs/development-v4-results-2026-10-04.md`. The later v6 development run is
the current development measurement. Legacy pins and the consumed v3 holdout
result remain unchanged.

The n8n collection bridge is implemented with existing CollectedDocument IDs,
privacy and persistence; bounded original-post imports and a one-POST webhook
client have mocked tests. The separate inactive workflow is
`n8n/discovery-original-posts-v1.json`, limited to 20 direct URLs/page requests,
with no model or spreadsheet nodes. The supplied old /webhook/photo-discovery
route is explicitly refused because it performs tagging. It was not called.
The owner still needs to import the new workflow in n8n Cloud, configure Header
Auth and save its dedicated production URL/key locally. Actual source-page
compatibility and live integration are unverified; unsupported text fails closed.
Workbook and YouTube collection remain available. No framework was added.

Earlier preparation note: connect and verify one n8n original post, publish
the curated Cloud package through the owner's accounts, and smoke-test its real
URL. Two development model cases now have recorded semantic approval; the other
model cases still need a specific human decision. Reliable extraction, unseen
validation and the larger internal gold target remain research limitations.
No new taxonomy/opportunity clusters or composite scores are claimed. Gold
remains 35 documents/21 cases, one authorized human reviewer; agreement is null.
M1 remains the previously completed technical milestone. Broader research and
Phase 10 are not marked complete. No commit, push or publication.

Final verification for this preparation: full suite **1157 passed, 5 skipped**;
focused mocked collection/reference/candidate/app checks **40 passed**. The
final -03 package passed all nine app surfaces plus found/absent saved searches
in isolation with external sockets and HTTP blocked (local Windows asyncio
sockets permitted). Package hash audit passed. Final candidate dry-run selected
10 dev documents, ceiling 20, calls 0, and created no output parent. Collection
dry-run wrote zero records. Hash-only preservation checked all 660 prior files:
only the two earlier authorized official gold population changes differ, with
original backups intact; all 21 frozen measurement files are unchanged.
`git diff --check` passes with line-ending warnings only. No retries or further
paid calls followed the six-request experiment.

Submission limitations, 2026-10-04, updated after the v6 measurement: the
research blockers were not closed by editing labels, saved output, thresholds,
or the consumed holdout measurement. Current development coverage is 4/6 and
precision is 0.8571 on `relevance/v6` + `extract/v4`. The consumed holdout
coverage remains 5/15; the separate successor is 7/15 and does not replace it.
Two named development model cases are semantically approved; the others are
not. Gold remains 35 documents with one reviewer. n8n tagged rows are still
not collected documents. Phase 10 clusters and a public deployment remain
unbuilt. The submission app Quality report labels every gate number with its
split, and Ask the evidence searches saved excerpts without a model. Those
surfaces do not change the measurements.

Historical development diagnosis, 2026-10-04, for the saved `extract/v3` run:
that run still recovers 2 of 6 reference cases, and its relevance precision
5/6 (0.8333) misses 0.85. The later v6 measurement above is current. Album, Memories, and poodle returned accepted-empty responses
after eligible, successful calls. The cat reference was not extracted because
relevance rejected a spliced quote. Older-photo and sleeping-video cases match,
with remaining trigger, summary, subject, and response disagreements. No
implementation defect dropped a case. Valid out-of-scope skips now record
`skip_cause=out_of_scope` and do not open a false evidence-failure review.
The stage-event schema still requires a review-group reason on every skipped
extraction. At the time of this diagnosis, `extract/v4` had not been run.
Relative
scoring paths now resolve from the project root. Original freeze-bound bytes
are in `data/interim/phase6/pre-correction-snapshot-2026-10-04-01/` and match
the existing freeze; those freeze hashes were not updated. Full suite:
**1133 passed, 5 skipped**. Development dry-run: 10 documents, ceiling 20,
provider calls 0, output directory not created. This does not certify
extraction quality. Details: `docs/development-diagnosis-2026-10-04.md`.

Consumed v3 measurement, 2026-10-04: the authorized quality verification is measured.
Development was checked with the scoped `extract/v3` correction, the candidate
was frozen, Sunayana reviewed and approved all 25 source-first holdout drafts,
and one bounded holdout measurement was completed. All five numeric thresholds
passed on those 25 seats: schema 1.00, spans 1.00, prefilter recall 1.00,
relevance precision 13/14 = 0.9286 and recall 13/14 = 0.9286. Full-document
delivery gives the same relevance result; no relevance technical failures were
excluded in this holdout run. Extraction matches only 5/15 reference cases.
This is numeric threshold passage, not approval of model-case semantics or
proof of wholly unseen generalization: these 25 seats were previously Phase 4
development documents. The original 15 Phase 4 holdout seats remain separate.
Schema/span rates use accepted records; rejected outputs are excluded and
reported separately. The stronger all-processed-output validation requirement
is not established by this metric. No unrestricted quality certification is
claimed.

Official gold now contains 35 human-approved, AI-assisted document labels and
21 reference cases (dev 10/6; holdout 25/15). The original empty official files
are retained under `data/gold/pre-quality-freeze-2026-10-04-01/`; existing
approved labels were copied unchanged. ADR-37 later accepted this labelled
set as final and closed the 75–100 volume. There is no independent second coder or
agreement score. Model outputs have not acquired semantic approval from the
reference-label approval.

Current pointers: `data/gold/CURRENT.json` and
`data/exports/quality/CURRENT.json`. The measured report and assessment are at
`data/exports/quality/holdout-frozen-v3-2026-10-04-01/`. Historical pending
reports remain unchanged. Details and commands: `docs/quality-verification-2026-10-04.md`.
Live totals: development 9 calls, holdout 16 calls, 25 total, no retries;
30 relevance cache hits. Holdout extraction: 14 attempted, 9 succeeded
(4 accepted-empty), 5 failed, 11 skipped, 5 accepted cases. Four provider
failures lack recorded token usage; billing remains unknown. The recorded-usage
list-price subtotal across both runs is $0.05544735, incomplete for those calls.
All 660 prior data files were checked: only the two intentionally populated
official gold files changed, and their original empty bytes were backed up.
Runs, existing cache entries, prior labels/reviews and both split manifests
were preserved. Full suite: **1131 passed, 5 skipped**. App methodology now
shows the aggregate measurement and its limitations; no holdout source or
prediction is loaded into that display. M1 remains the already-completed
technical milestone; Phase 6 research and broader submission work are not
marked complete. No commit, push or deployment.

The dated entries below are historical and are superseded by this current result.

Extraction prompt correction prepared, 2026-10-04: `extract/v3` renders the
approved development-review clarifications and is not the active pin. The
registry, pilot, diagnostic, and development-corpus bounds remain `extract/v2`.
`extract/v1` and `extract/v2` instruction renderings are unchanged. Cache
identity changes when the prompt version changes. The five-document
corrected-schema guard fails closed for a v3 request because that request's
cache key does not find the stored v2 entry, so it does not fall through to a
provider call. Mocked tests cover field-specific exact_query evidence, spliced
quotes, ambiguous repeated offsets, and synthetic fixtures for the album,
Memories, poodle, sleeping-video, older-photo, and cat episode types. A
verbatim negative-memory quote assigned to remembered approximate_time still
passes the quote gate; the prompt forbids that assignment, and the gate does
not judge meaning. Mocked responses do not prove a live model follows the
instructions and do not improve measured extraction quality. No gold-dev-only
zero-call dry-run exists. `--development-corpus` requires all 35 development
documents, and `--pilot` is the five-document mode. Neither was run, and no
reserved or holdout source was opened. No provider call, reference edit, split
edit, or historical artifact overwrite. Full suite: 1112 passed, 5 skipped.
`git diff --check` reported only existing CRLF warnings. Development is not
frozen. The final quality gate stays pending. M1 stays complete. Coverage
remains 2/6. Cat impact remains empty/not_stated and severity remains 3.

Approved reference revision 02, 2026-10-04: Sunayana authorized cat impact to be
unstated while retaining severity 3, and approved the rest of the source review.
Created a new `sunayana-reviewed-02/` pack and `development-reference-02/`
export: 10 documents, 6 cases, 38 exact field quote attachments. Only the cat's
impact value/status and obsolete impact attachment change semantically; severity
evidence and all other case values/scopes/splits remain. Original versions stay
intact. All ten revised reviews validate. Six approved review findings/correction
plans are separately recorded under
`data/interim/phase6/development-review-approval-2026-10-04-01/`; no model output
is repaired and rejected candidates are not promoted. The reference-definition
decision is resolved; later model corrective work remains open.
Offline reevaluation at
`data/exports/quality/development-reference-revision-02-2026-10-04-01/`
still meets all five numeric development thresholds: schema/span and prefilter
1.00, relevance precision 0.8571/recall 1.00. Coverage is unchanged at 2/6;
the model's time_loss remains unsupported. Impact recall/F1 are now null because
neither matched reference case has a stated impact label. No extraction recovery
is claimed. All 166 protected inputs remain unchanged. Zero provider requests,
holdout source reads, original label/cache/split edits, commits or pushes.
No production code change or new full-suite run; last suite remains 1100 passed,
5 skipped. Development is not frozen; final quality gate stays pending and M1
stays complete. Earlier pending-reference-decision statements are historical.

Development corrective review complete, 2026-10-04: reviewed the four missing
episodes and both accepted matches against six approved gold-dev source packets.
The separate proposal is
`data/interim/phase6/development-review-2026-10-04-01/REVIEW.md` (with findings,
exact offsets, retained gate errors and provenance in adjacent JSON files).
Two Google Support outputs omitted approved episodes. The poodle candidate
contains a spliced response quote, an altered trigger quote, ambiguous short
cue offsets and missing outcome evidence; the sleeping-video candidate lacks
exact_query's own field evidence. Gates correctly rejected those candidates.
Accepted cases retain unsupported interpretations, omissions and incomplete
summary attachments; no saved case was repaired. The cat's social-sharing
trigger is semantically supported despite strict string disagreement. The older
photo's forgotten date cannot support a remembered approximate-time cue.
A reference-definition issue is pending owner decision: the approved cat
`repeat_effort` label does not establish Section 16.6's separate sittings.
Propose a new reference revision with impact unstated, while retaining severity 3
and all originals; no revision is applied. The numeric 41.2% disagreement
diagnostic is not a human semantic-fabrication rate. Development is not frozen.
Verification: 25 exact unique review anchors, 20 exact retained case spans,
two invalid saved quotes absent from source; all 21 M1, 98 protected annotation
and 26 evaluation hashes unchanged. No production code change or new full-suite
run; the last full suite remains 1100 passed, 5 skipped. No provider request,
holdout source access, cache/label/split change, commit or push. Final quality
gate remains pending, holdout stays locked, M1 stays complete.

Development evaluation complete, 2026-10-04: at the owner's direction, holdout
remains locked. `data/exports/quality/development-approved-2026-10-04-03/`
contains the current measured report, development disagreements and readable
`DEVELOPMENT-EVALUATION.md`. The ten approved reference documents have six cases.
Five numeric thresholds are met on this small development sample: schema/span
validation and prefilter recall 1.00, relevance precision 6/7 (0.8571), recall
6/6 (1.00). This is development evidence, not final quality certification.
Extraction recovered only 2/6 reference cases: two rejected attempts and two
accepted-empty omissions explain the other four. Outcome, cues, query and impact
disagreements remain visible; summary semantic support is unassessed by the
current reference contract. No label or approval was changed to improve a score.
The evaluator now actually consumes saved predictions and full field evidence;
structured multi-label comparison and omission/inference accounting are fixed.
Focused tests: 33 passed. Full suite: 1100 passed, 5 skipped, no failures/errors;
JUnit is under `data/interim/verification/quality-development-2026-10-04/`.
All 21 M1 and 98 protected annotation hashes remain unchanged, as do all 26
final evaluation inputs. Zero external requests; official gold and prior reports
are preserved. M1 stays complete. Phase 6 and the final quality gate stay pending.
Earlier in-task evaluations ending `-01` and `-02` are preserved and marked
superseded; `-03` is the current result.

Owner approval of saved M1 model cases, 2026-10-04: Sunayana's direct approval
is recorded for all ten cases in run `3dc346ec030a`, separately under
`data/interim/phase5/semantic-approval-2026-10-04-01/`. Each approval binds the
run and original case/file hashes; no model row was rewritten. Five cases have
no recorded finding. Existing browser/export rules still block five: two Google
Support cases with five semantic field objections, and three Reddit cases with
an inherited document-level historical provider finding. That provider finding
is not evidence that the three new cases are semantically wrong; it remains an
unresolved historical diagnostic and the existing guard was not bypassed.
The five affected Google Support field values are unchanged from the reviewed
pilot. No finding is resolved by the general approval. The scoped approval ledger
does not silently apply to other runs or rewrite the older prepared app exports.
No new independent source review, provider request, holdout source read, label/
split/prompt/schema change, commit or push. All 21 M1 input hashes remain
unchanged. M1 stays complete; the quality gate remains pending. This supersedes
the earlier absence of a recorded owner approval for the ten saved model cases,
while retaining all open findings and separate human reference labels.

M1 verified complete, 2026-10-04 (ADR-34): the saved 35-document development
run passes all five Section 28 checks. The offline audit is
`data/exports/milestones/m1-2026-10-04/report.json`; its readable record is
`data/exports/milestones/m1-2026-10-04/M1.md`. All ten saved analysis cases
pass current schema/field gates. Corrected evidence count: 61 spans (24 inline
plus 37 external), all backed by retained successful source-validation verdicts;
20 spans were also checked against approved gold-dev source packets. Reserved
holdout source text stays closed. The old 24-span run report remains intact.
Normalize/dedupe/prefilter: 35 succeeded each. Relevance: 34 succeeded, one
unavailable with an existing human effective decision. Extraction: 15 succeeded,
six failed, 14 skipped; seven accepted empty documents, ten cases in eight
documents. Failures and empty responses are reported, not hidden or repaired.
Full offline suite: 1087 passed, 5 skipped, 0 failures/errors. Regression tests
cover the full inline/external union and audit refusal conditions. The 98 files
protected by the previous annotation provenance record remain unchanged.
No external request, holdout source read, label/prompt/schema/split change,
commit, push or deployment occurred. M1 is the technical pipeline milestone;
the Phase 6 quality gate remains pending and saved model-case semantic approval
is not inferred from automatic validity or approved human reference labels.
Earlier M1-incomplete statements below are historical and superseded by this
verification; they do not describe the current milestone status.

Approved single-reviewer annotations, 2026-10-04: Sunayana approved the current
drafts and authorized one-person review for the individual submission (ADR-33).
`data/annotation/dev-starter-2026-10-03/sunayana-reviewed-01/labels/Sunayana/`
contains all 10 approved AI-assisted review files. The existing emitter wrote
10 documents and 6 cases to its fresh `development-reference-01/` directory.
All files validate; 22 focused tests passed. Original seating/splits and all
earlier drafts are preserved; procedural second-review requirements are explicitly
waived only in the new review manifest. No second coder, adjudication or agreement
is claimed. The family-album scope exception remains disclosed. Official gold
and existing evaluation reports are unchanged. No model call or holdout access
occurred. Quality certification and M1 remain pending/incomplete. Historical
second-review blockers below are superseded by this owner-authorized method.

Annotation review revision 03, 2026-10-04: recorded Sunayana's approval of
the sleeping-video core/one-case summary and direction to classify the family-
album document as core. Proposed totals are 3 core, 3 adjacent, 4 out of scope,
with 6 cases. The family-album source does not demonstrate incomplete recall;
its user-directed core label is explicitly recorded as a scope-criteria exception
in `ai-assisted-draft-03/scope_exceptions.json`. Case fields and all 39 exact
spans are unchanged; all 10 revised files validate. Six scoped human decisions
are retained. Earlier revisions and official gold are preserved. No evaluation,
provider call, holdout text access or independent second review occurred. Other
unapproved fields, the new Memories case confirmation and required second human
reviews remain open. Quality gates and M1 remain pending/incomplete.

Scoped annotation review, 2026-10-04: Sunayana's four decisions are recorded in
`data/annotation/dev-starter-2026-10-03/ai-assisted-draft-02/human_decisions.jsonl`.
Memories scope changed to adjacent; the poodle example's real-episode grounding,
cat severity 3, and short YouTube exclusion were accepted. Revision 02 proposes
2 core, 4 adjacent and 4 out-of-scope documents, with 6 cases. The new Memories
case/reason/count remain proposed for confirmation; other unreviewed fields
and documents are not blanket-approved. All 10 revised files validate; 22 focused
tests passed. Original draft 01 and the blank pack are preserved. Official gold
and evaluation reports remain unchanged. No independent second human reviews,
adjudication, provider calls or evaluation were added. Quality gates and M1 remain
pending/incomplete.

AI-assisted annotation drafts, 2026-10-03: prepared all 10 starter documents
under `data/annotation/dev-starter-2026-10-03/ai-assisted-draft-01/` for human
approval. Proposed labels are 2 core, 3 adjacent, 5 out of scope, with 5 cases.
All 10 drafts pass local contract/quote validation; 22 focused annotation/gold/
evaluation tests passed. These are explicitly AI-assisted drafts, not independent
human labels or semantic approvals. The original pack still has 0 reviews and is
pending; official gold, evaluation reports and prior decisions are unchanged.
No provider call or draft evaluation was made. Memories navigation, the poodle
example, the short YouTube comment and severity coding require particular review.
The two designated double-code documents still require independent human review.
Quality gates and M1 remain incomplete. Latest full-suite count below is historical.

Development annotation pack, 2026-10-03: `data/annotation/dev-starter-2026-10-03/`
holds 10 blank gold-dev packets. `gold-split/v1` seated them inside the 35
Phase 4 development documents. The 15 Phase 4 holdout documents were not
copied. Model predictions are in a separate folder. `data/gold/` is still
empty, so the quality gate stays pending. This batch does not complete the
75–100 document gold set or milestone M1. ADR-37 later closed that volume at
the approved 35-document set. Full suite: 1078 passed, 5 skipped.

Phase 6 evaluation code, 2026-10-03: `scripts/evaluate.py` scores a gold split
and refuses holdout error analysis. The gold files have no labels, so both
`data/exports/quality/dev/report.json` and the holdout report are `pending`.
The relevance-seed split was not reused as gold. Prefilter recall 0.90,
relevance precision 0.85, and relevance recall 0.80 were not measured and were
not lowered. Full suite: 1070 passed, 5 skipped.

Phase 5 remainder, 2026-10-03: human case overrides are append-only.
`v_current_cases` prefers a valid human row and leaves the model row in place.
A pending quote does not replace it. No development case received an override.
The 10 analysis cases pass `validate_record`; their 24 spans match the source.
Two historical calls, runs `4a8c7175f992` and `024f9b18b60f`, have no recorded
usage. Their charges stay unknown and were not estimated. Saved diagnostics for
those calls are HTTP 400 `json_validate_failed`, not an outage. Review rows were
not resolved. Six eligible documents remain evidence-gate failures. Semantic
approval and the Phase 6 quality gate are still open. Full suite: 1042 passed,
5 skipped.

Milestone M1, 2026-10-03: the frozen development split, 35 documents, was
extracted once through the existing evidence gate. Run
`data/interim/phase5/development-corpus/3dc346ec030a`. Normalize, dedupe, and
prefilter each recorded 35 succeeded events. Relevance recorded 34 succeeded
and 1 unavailable. Extraction recorded 15 succeeded, 6 failed, and 14 skipped.
21 documents were eligible; 14 out-of-scope documents were not sent to the
model. The run made 17 provider calls and reused 4 cached responses. It stored
10 analysis cases (4 core, 6 adjacent) and 24 evidence spans. All 24 match the
source at their stored offsets and are validation state `valid`. Eight rejected
or pending spans stay in the attempt ledger and are not analysis claims. Seven
eligible documents returned an accepted empty case list. Recorded usage for the
17 calls is 200,782 input tokens and 45,822 output tokens, estimated list price
USD 0.055115. That figure is not billing. The one unavailable relevance event
is `reddit-c49086caf891`; its existing human adjacent decision was the
effective input, and the model decision was not edited. Eleven label
disagreements were recorded and the approved labels were left unchanged.
Holdout text was not loaded. Prompts, schemas, and the frozen split were not
changed. Automatic span validation is not semantic approval: no case was
semantically approved, including the new cases. The submission app still shows
the earlier five-document export. Full suite: 1035 passed, 5 skipped.

Offline diagnosis, 2026-10-03: the failed YouTube extraction's corrected wire
schema was reproduced with the same digest; no local schema mismatch was found.
The empty provider rejection remains unresolved. Fixed the research-batch failure
exit status, existing-extraction-output guard, hard-coded live timestamps, and
empty-generation diagnostic classification. Historical runs and decisions are
unchanged. No retry or live request was made. Full suite: 1008 passed, 5 skipped.
See `data/interim/youtube-discussion-2026-10-03/offline-diagnosis.md`.

Latest live research batch, 2026-10-03: YouTube discussion collection saved 20
comments with two API requests. Offline provenance checks passed; no duplicates
or redactions were reported. All records are outside the frozen evaluation split.
Relevance run `a8515d4d5758` made 20 calls: 19 out of scope, one adjacent,
zero core. Extraction run `ae60feaa840d` made one call and failed with HTTP 400
`json_validate_failed`; no case was saved and no retry occurred. Extraction usage
is unavailable, so the USD 0.018501 relevance estimate is not a complete batch
cost or billing figure. Fixed saved timestamps differ from actual execution dates.
See `data/interim/youtube-discussion-2026-10-03/extraction-review.md`.
Semantic approval remains incomplete. No approved labels or split were changed.

Submission app, 2026-10-03: `app.py` is a read-only Streamlit view of prepared
exports in `data/exports/submission/`. It does not read raw collection files,
call a model, call YouTube, or run n8n. The development export has 35 documents,
15 withheld evaluation documents, 5 extraction attempts, 2 automatically valid
cases, 0 semantically approved cases, 2 failed attempts, and 1 empty response.
The YouTube discussion export has 20 documents outside the frozen split, 20
relevance attempts (19 out of scope, 1 adjacent), 1 failed extraction, and 0
cases. Those sets are not added together. Streamlit 1.65.0 is installed from
`pyproject.toml`. Phase 10 remains incomplete. Launch, on a port other
than the local browser's 8765:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8766 --server.headless true
```

> Updated after each approved phase (spec Section 29.15).

Source reassessment, 2026-10-01: the [free collection audit](SOURCE-COLLECTION-AUDIT-2026-10-01.md)
replaces the prior blanket permanent-closure conclusions. Google Photos
community access requirements remain unresolved; the inspected Google Play
and Apple review routes are blocked. No data probe qualified: zero data
requests and zero records per source, no new adapter. This is documentation
research, not source collection, extraction quality, or M1 completion. The
concurrent YouTube work is separately verified by its implementing agent.

| | |
|---|---|
| **Completed phase** | Phase 3 — normalization and deduplication (2026-09-27) |
| **Current phase** | Frozen quality measurement completed after human holdout-label approval. Five numeric thresholds passed on 25 previously development-exposed holdout seats; extraction coverage 5/15. Official gold is final at 35 documents/21 cases (ADR-37). Unseen validation and new model-case semantic review remain incomplete. M1 remains the existing technical milestone. |
| **Tests** | Latest full verification, 2026-10-04: 1131 passed, 5 skipped. Groq SDK retries remain disabled (`max_retries=0`). Installed `groq` is 0.37.1. Installed `streamlit` is 1.65.0. |
| **Coverage** | 100% of `src/models/`. Phase 4 and the extraction stage are covered by `tests/test_relevance.py`, `tests/test_relevance_evaluation.py`, `tests/test_relevance_governance.py`, `tests/test_relevance_overrides.py`, `tests/test_extraction.py`, `tests/test_extraction_foundation.py`, `tests/test_extraction_pilot.py`, `tests/test_extraction_eight_k_pilot.py`, `tests/test_llm_gateway.py`, `tests/test_pipeline_runner.py`, and `tests/test_groq_provider.py` |
| **Last verified** | 2026-10-04 |
| **Blockers** | Numeric measurement is complete. Extraction recovered 5/15 holdout cases, five attempts failed, and four new provider failures lack usage. Previously development-exposed seats do not establish unseen generalization. Gold labelling is closed at the approved set. Existing semantic objections, duplicate recalibration and the remaining submission work remain open. Phase 10 is incomplete. |
| **Next command** | See "Next command" below |

---

## Phase 5 - five-document 8192-token run reviewed offline (2026-10-01)

The authorized command had already written `data/interim/phase5/pilot-v2-8192-01/024f9b18b60f`
before this review. This follow-up made no provider call and did not modify the run, cache,
labels, manifest, split, or review decisions. The proposal is
`data/interim/phase5/pilot_v2_8192_correction_proposal.md`.

Recorded execution: five eligible development documents, one cache hit
(`google_support-d7f386f347b7`), four provider calls, four cache misses. `extract/v2`,
Groq `openai/gpt-oss-120b`, max tokens 8192. Recorded usage is 35,381 input tokens and
7,325 output tokens, estimated list cost USD 0.009702. `provider_calls_without_recorded_usage`
is 1 and `usage_totals_complete` is false, so that estimate is not a total for every call
and is not billing.

Outcomes: `ok` for the cached transcript case, the new Camaro case
`google_support-e1e5277da7e8#c01`, and `google_support-2a080da4b930` with zero cases;
`evidence_validation_failed` for `reddit-23be97c93709`; `provider_error` for
`reddit-c49086caf891`. Two cases are in `retrieval_cases.jsonl`. New open review items are
`fe81d5c8e426` and `b7031346833a`. Earlier review rows were not resolved.

The Camaro case passed the evidence gate. Semantic review does not approve it.
`retrieval_trigger` `car search option` is the search method, not a stated reason the item
was needed. `impact_signals` `time_loss` is attached to a quote that says the white Camaro
is missing and does not state that time was consumed. `query_strategies` is `not_stated`
even though the source names the car search option; that method was filed as the trigger.
The `problem_summary` quote supports "white Camaro" and "missing" only. It does not contain
"photo" or "car search option".

The empty response for `google_support-2a080da4b930` is a finished `stop` payload with
zero cases. The contract allows that shape when a document has no retrieval episode. This
source states one: finding a family member in a non-shared album, no face search inside
that album, and scrolling hundreds of photos. Emptiness is the model's omission. The
pipeline correctly kept the empty payload as success.

`reddit-23be97c93709` was rejected for a spliced `problem_summary` quote. The saved quote
joins three real passages with `...`, and the source has no ellipsis. The omitted text is
` and Google Photos backs up without putting pictures in any folder and so ` and
` and others are mixed in with thousands of other pictures. `. The quote was not repaired.
Other spans on that candidate validated. The case remains out of analysis.

`reddit-c49086caf891` retains HTTP 400 `invalid_request` / `json_validate_failed`, message
`Failed to generate JSON`, `finish_reason` null, `request_id` null, and a rejected-output
summary of 3,690 characters of invalid JSON with the error at position 3,690.
`application_state` is `not_checked`. The body was not kept. Those fields do not establish
token exhaustion, a missing token count, or a charge. The review reason
`provider_unavailable` is the existing name for `provider_error`, not an outage finding.

No prompt or schema change was made. No further live command is authorized. M1 remains
incomplete.

## Phase 5 - five-document 8192-token mode prepared offline (2026-10-01)

Historical preparation entry. The live command it names has since run, at the directory
recorded above.



Semantic review of the saved case `google_support-d7f386f347b7#c01` is in
`data/interim/phase5/core-diagnostic-v2-detail-fix-semantic-review.md`. Automatic
validation stored the case as valid. That is not semantic approval. `retrieval_trigger`
value `search backup` is unsupported: its quote is verbatim, and the field is why the
user needed the item, which the post does not state. `problem_summary`'s attached quote
is only the first sentence, so it does not support "cannot locate" or "in their backup".
The saved case, approved labels, cache entry, and review decisions were not modified.

`--pilot --pilot-max-tokens 8192` may now use the existing five-document manifest. This
mode requires `--call-budget 4` and `--max-retries 1`. The ordinary pilot remains 4096
tokens and five calls. The single-document diagnostic remains one call. Before any
provider call or output creation, the corrected-schema cache entry for
`google_support-d7f386f347b7` must match the request that would be sent, including the
8192-token limit and schema digest, and pass local response validation. A missing,
mismatched, or unusable entry fails closed and is not requested. At most four documents
are uncached, and the gateway reserves one first attempt for each. SDK retries stay
disabled. Missing-key, fresh-output, model, and prompt guards stay. Offline mode is
refused on this path. The manifest was not rewritten.

Full suite: 958 passed, 5 skipped, zero failed. The dry-run reported five development documents, `extract/v2`, Groq
`openai/gpt-oss-120b`, max tokens 8192, call budget 4, zero attempts, zero provider
calls, and zero files written. Its summary run id is `fdb5db10a383` because a dry-run
uses a different identity from the live run. The planned live directory
`data/interim/phase5/pilot-v2-8192-01/024f9b18b60f` was not created. The manifest hash
remains `635fdfadbb9cf139652937e4aa4d8fd112f7947c1cf4fd9fab97a78846aeb73a`. No live
request, holdout unlock, commit, or push occurred. Extraction quality and M1 remain
unassessed. Future command, not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --pilot-max-tokens 8192 --provider groq --split development --cache data/interim/cache --call-budget 4 --max-retries 1 --output data/interim/phase5/pilot-v2-8192-01
```

## Phase 5 - one-call detail-fix diagnostic accepted one case (2026-10-01)

The user authorized one external request and the prepared command ran exactly once.
Before it ran, the corrected wire schema was confirmed offline: the six non-subject
label definitions transmit `detail` as `"type": "null"`, `SubjectLabelPayload` transmits
`["string", "null"]`, and the destination parent was absent. Output is
`data/interim/phase5/core-diagnostic-v2-detail-fix-01/84608e7b3eb7`, twelve files. The run
id repeats the earlier v2 id because run ids exclude the wire-schema digest; the fresh
parent is what keeps the two runs separate.

Recorded operations: one candidate, one eligible document, one attempt, one provider call,
one cache miss, zero cache hits, `finish_reason=stop`, 11,757 input tokens, 4,667 output
tokens, estimated list cost USD 0.004564, `provider_calls_without_recorded_usage=0` and
`usage_totals_complete=true`. That is reported usage for this request, not a billing
measurement. No retry and no second request occurred.

One case, `google_support-d7f386f347b7#c01`, was assembled. Its technical state is `ok`,
its `validation_state` is `valid`, `needs_human_review` is false, and it is stored in
`retrieval_cases.jsonl`. There are no rejection reasons to report:
`extraction_failures.jsonl`, `extraction_candidates.jsonl`, `review_queue.jsonl` and
`label_disagreements.jsonl` are all empty, the checkpoint is `succeeded`, and the stage
event is `succeeded` with a null reason code. This is the first run to store an
analysis-valid case.

Detail is null on every label the model returned, including the single `remembered_cues`
label that previously carried forbidden text. The `target_subjects` label also returned
null detail, so the allowed subject-detail string path was not exercised by this request.

Nine candidate spans were validated and all nine passed: every one is `supplied_exact`
with `repair_applied=false` and `validation_state=valid`. The union is seven unique spans,
because the model supplied `target_subjects` and `remembered_cues` evidence both inline
and again through `field_evidence`; `dedupe_spans` collapses those by `evidence_id` and
keeps the inline `observed_value` row. All seven quotes are exact substrings of the
173-character target document at their stated offsets, and the request identity's
`content_hash` matches that document. Each stated field carries supporting evidence:
`known_item_status`, `target_asset_type`, `target_subjects`, `retrieval_trigger`,
`remembered_cues`, `outcome` and `problem_summary` have one valid span each, and the eight
`not_stated` dimensions carry none, as the status gate requires.

Three transport details remain, none of which blocked this run. Run ids still exclude the
wire-schema digest, so a fresh output parent stays mandatory. `field_evidence` still
accepts field names that also carry inline evidence, so a duplicated quote is validated
twice before dedupe. `FieldEvidencePayload` omits `severity` by design, because severity
uses its own `severity_evidence` channel. No other schema/application mismatch was found.

Preservation: the nine earlier phase 5 run directories retain their file counts and write
times, the 86 existing cache entries are untouched, and exactly one cache entry was added.
No review decision, label, prompt, split or holdout access changed, and no commit or push
occurred. `git status --short` has 39 changed/untracked entries, all from preceding work
and these documentation edits.

This verifies that the corrected schema produced one accepted, fully evidenced case on one
development document. It does not establish extraction quality, semantic label accuracy, a
success rate across documents, or M1. The remaining four documents and the earlier open
review items are unaddressed, and no retry was performed.

## Phase 5 - subject-only detail contract correction (2026-10-01)

Historical entry; the live diagnostic it prepared has since run as recorded above, and its
proposed output parent is now occupied.

The user executed the prepared v2 diagnostic at
`data/interim/phase5/core-diagnostic-v2-01/84608e7b3eb7`. Its saved record shows one
provider call, finish_reason stop, 11,810 input tokens, 3,630 output tokens, estimated
list cost USD 0.003949, and zero analysis-valid cases. All eight spans passed. Both
remembered-cue labels contained non-null detail, forbidden by the existing ObservedValue
contract. Assembly stored schema_validation_failed; the document summary incorrectly
collapsed it to evidence_validation_failed. Span validity does not establish semantic
support or extraction quality. The original twelve files and six extraction cache files
are preserved, including the rejected response and open review item c5725d5f87ac.

After the user's fix authorization, the model-facing label schema now requires null
detail for all six non-subject dimensions. Subject labels retain optional string detail.
Python validation rejects forbidden values without dropping them. Prompt instructions,
application case/evidence contracts, enums, approved labels and split remain unchanged.
The corrected schema is embedded in the prompt and sent as strict structured output;
its digest separates the Groq cache entry. Prompt version remains extract/v2 and record
schema version remains 1.0.0 because this aligns transport with the existing contract.
Run IDs do not include the wire-schema digest, so a fresh output parent is required.

Document summaries, manifests and stage events now report assembly schema failures as
schema_validation_failed. Schema failure takes precedence for a mixed-case document;
individual case failures and review reasons remain retained separately.

Thirteen new offline regressions cover all six dimensions, allowed subject detail,
rejected rather than coerced response detail, mixed-case failure reporting, and cache
identity separation. Relevant tests: 325 passed. Full suite using
`.\.venv\Scripts\python.exe`: 949 passed, 5 skipped, zero failed.
The one-document 8192-token CLI dry-run reported one eligible document, zero attempts,
zero provider calls and zero records. Its proposed parent
`data/interim/phase5/core-diagnostic-v2-detail-fix-01` was not created.

No live request, holdout access, commit or push occurred for this fix. A further live
request needs separate authorization. M1 and extraction quality remain unassessed.
Future bounded command (not executed):

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --pilot-doc google_support-d7f386f347b7 --pilot-max-tokens 8192 --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/core-diagnostic-v2-detail-fix-01
```

## Phase 5 - authorized extract/v2 correction implemented (2026-10-01, historical preparation)

The following records the earlier preparation state. The diagnostic above subsequently
ran; its occupied output must not be reused. The schema-dependent prompt hash below
describes that earlier schema. The current regression freezes the schema input to verify
the unchanged v1 instruction template independently of transport corrections.

The user approved the instruction addition in
`data/interim/phase5/extraction_evidence_correction_proposal.md`, then asked to continue
the preparation work. `extract/v2` is now active in the version registry. It explicitly
requires separate verbatim supporting evidence for interpreted summaries, one continuous
source substring per quote, no inserted ellipses/spliced passages, and empty values/
evidence for not_stated/not_applicable. Historical `extract/v1` rendering is preserved;
the synthetic baseline SHA-256 regression is
`5ed97240a5da470855793e1e14134bc0068a5c2c4ed3642b6f19046b33c9f392`.
Unknown prompt versions are refused. Pilot and synthetic diagnostic bounds pin the
approved v2 version. Version-aware cache keys, run ids and extraction fingerprints
isolate v2 without rewriting/reusing historical v1 responses.

Application/wire schemas, evidence ladder, enums, global model/token configuration,
approved labels, split and five-seat manifest remain unchanged. The same Groq
`openai/gpt-oss-120b`, strict schema, SDK retries zero, one gateway attempt, first-attempt
reservation, cache and key/fresh-output/fatal-authentication guards remain in effect.
The ordinary pilot still has cap five and configured max_tokens 4096; the explicit
8192-token option remains restricted to one failed core seat with cap one. Unrestricted
live extraction remains refused, and holdout remains locked.

Sixteen new synthetic mocked regressions verify unchanged historical rendering, approved
instructions, exact schema/target payloads, cache/run/fingerprint separation, approved
version guards, genuine source ellipses, inserted ellipses, spliced/fabricated quotes,
summary support and evidence conflicts for empty observation statuses. Existing active
version assertions and the nullable-schema cache fixture were updated while retaining
the legacy v1 seed entry. Relevant tests: 312 passed. Full suite using
`.\.venv\Scripts\python.exe`: 936 passed, 5 skipped, zero failed.

Three CLI dry-runs selected v2 and each reported zero provider calls and zero output
records. The core diagnostic had one eligible document, dry-run id `da81cc2b23d7`, and
planned live path `data/interim/phase5/core-diagnostic-v2-01/84608e7b3eb7`. The unchanged
five-document selection had dry-run id `174682acde58`, planned live id `bf6a66359b73`
under `pilot-v2-preparation`, and cap five. The synthetic diagnostic had dry-run id
`3ec267d9d24c`, planned live id `016e787cf30a` under `diagnostic-v2-preparation`, and cap
one. All three output parents remain absent. Dry-run's printed offline flag remains
false unless explicitly requested, but its early return makes zero provider calls.

Final SHA-256/size/write-time verification covers 91 existing data/config/contract files;
the inventory is `data/interim/phase5/extract_v2_preservation_snapshot.json`. The original
pilot manifest hash remains
`635fdfadbb9cf139652937e4aa4d8fd112f7947c1cf4fd9fab97a78846aeb73a`.
The authorized prompt/registry edits are excluded from that immutable inventory.
`git diff --check` passed and `git status --short` was inspected; the tree retains 38
changed/untracked entries including preceding work and the new test module.

No v2 provider call, saved run/cache/label/split edit, holdout access, commit or push
occurred. This verifies preparation and controls, not model adherence or extraction
quality; M1 remains unassessed. Prompt-change authorization does not authorize another
paid request. Exact future one-document command, prepared but not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --pilot-doc google_support-d7f386f347b7 --pilot-max-tokens 8192 --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/core-diagnostic-v2-01
```

## Phase 5 - 8192 diagnostic completed; review persistence and reporting fixed (2026-10-01)

The user authorized one 8192-token diagnostic and online investigation. The intended
parent was absent at the initial check, but the command subsequently refused its
occupied destination before invoking the provider. A completed run was present at
`data/interim/phase5/core-diagnostic-8192-01/797b223ff9f9`; no second request was attempted.
Its artifacts record exactly one eligible document, one provider call/cache miss,
zero cache hits and zero valid cases. It uses the unchanged `extract/v1` prompt and
strict wire schema with `max_tokens=8192`, and retains `finish_reason=stop`. This request
returned structured output without the previous HTTP 400/truncation error. That outcome
does not establish a general success rate or the causes of historical failures.

The case `google_support-d7f386f347b7#ua6f68421` failed evidence validation. Six spans
validated; two `target_asset_type` / `remembered_cues` quotes abbreviated the source
with literal `...` and were rejected. `problem_summary` had no evidence. The gate
correctly withheld the case, and review item `04d66b128c28` remains open. Recorded
usage is 11,600 input and 2,837 output tokens; estimated list price is USD 0.003442.
`usage_totals_complete=true` describes reported usage for this request, not actual
billing. Earlier failed-request usage/billing and the speculative 23,000-token figure
remain unknown.

Confirmed reporting/review gaps are now corrected through existing pipeline code:
the summary prints failed-candidate and technical-state counts; extraction CLI paths
return failure status when candidates failed, while accepted empty responses remain
successful. Attempt counts now describe processed outcomes when fatal authentication
stops early. Future runs also write `extraction_candidates.jsonl`, retaining typed
invalid candidates and any pending assembled case for review, separate from analysis.
Missing assembled cases remain explicit nulls. Existing candidate rows survive resume;
accepted current cases remove matching pending rows without resolving review items.
This additive artifact makes future run output twelve files; existing eleven-file runs
are unchanged. No unsupported quote is repaired or accepted by these fixes.

A replay using only the target development document and existing cache, with a transport
guard that refuses all requests, wrote
`data/interim/phase5/core-diagnostic-8192-review-01/797b223ff9f9`: zero provider calls,
one cache hit, one retained pending review candidate, zero analysis-valid cases and
twelve output files. Original artifacts and cache were not rewritten. Seven additional
mocked regression cases passed; relevant tests: 296 passed; full suite using
`.\.venv\Scripts\python.exe`: 920 passed, 5 skipped. Both final dry-runs made zero calls
and wrote zero output records; their output parents remain absent. `git diff --check`
passed and `git status --short` was inspected (37 existing changed/untracked entries).
All 79 protected files retained hashes, sizes and write times, including the completed
8192 run and its new cache entry. The fresh twelve-file review replay is additional.

Official [Groq structured-output documentation](https://console.groq.com/docs/structured-outputs#best-practices)
distinguishes schema compliance from semantic accuracy. The current evidence errors
are model contract violations, not a reason to relax the gate. Prompts, schemas,
validators, approved labels, split and holdout lock remain unchanged. No commit or
push occurred. The single diagnostic authorization has been consumed by the recorded
run; no further provider request was made. All errors are not fixed: generation and
evidence behavior on the other documents remain unassessed, and this case still needs
review. Extraction quality and M1 remain unassessed.

At the time of this historical entry, the inactive proposal `data/interim/phase5/extraction_evidence_correction_proposal.md`
contains the exact proposed `extract/v2` addition: mandatory summary support,
continuous verbatim quotes, no inserted ellipses/spliced passages, and empty evidence
for not_stated/not_applicable. It requires separate prompt-change authorization under
the earlier "do not tune prompts" instruction. No prompt addition is active and no
further provider request is authorized by that proposal.

## Phase 5 - core diagnostic identifies completion truncation (2026-10-01)

Historical preparation entry; the 8192 diagnostic has since completed as recorded above.

The user executed the prepared one-document command once. Run
`data/interim/phase5/core-diagnostic-01/4a8c7175f992` records one candidate, one
eligible document (`google_support-d7f386f347b7`), one attempt/provider call/cache miss,
zero cache hits and zero valid cases. Its HTTP 400 `invalid_request` diagnostic has
`error_code=json_validate_failed`. The provider explicitly reports that the completion
token limit was reached and required content was omitted. Request identity records
`max_tokens=4096`; the sanitized provider message names missing wire-schema fields
`known_item_status` and `known_item_status_observation`. Transient inspection reports
491 characters of syntactically valid JSON, invalid application content, and a missing
`cases[0].problem_summary`. These are distinct vendor and application checks, not a
retained generated response. The failed generation was not accepted or cached.

This establishes the provider-reported cause for this new attempt only. It does not
retroactively establish either earlier core failure's cause. `finish_reason` and
`request_id` remain unknown. The checkpoint is failed, and the open review item
`8f11ab7d495a` targets the extraction attempt `4a8c7175f992:google_support-d7f386f347b7`.
The manifest records one provider call without usage and `usage_totals_complete=false`;
zero recorded tokens/cost do not establish zero consumption or billing. Historical
failed-request usage/billing and the proposal's speculative 23,000-token figure remain
unresolved.

Prepared `--pilot-max-tokens 8192` as an explicit option only with `--pilot --pilot-doc`
for a failed core seat. Other values and execution modes are refused. The ordinary
five-document pilot and `config/models.yaml` retain 4096. The option passes through the
existing extraction/gateway path, and the existing run/cache identities distinguish
the changed completion limit. Model, prompt, strict schema, evidence gates, temperature,
one-attempt/call bounds, cache, key and fresh-output guards remain intact. Increasing
this limit is an experiment; success at 8192 has not been established.

Thirteen additional mocked regression cases passed. Relevant extraction/gateway/evidence/
review tests: 289 passed. Full suite using `.\.venv\Scripts\python.exe`: 913 passed,
5 skipped, zero failed. The 8192 dry-run reported one eligible document, zero attempts/
provider calls and zero files written, with dry-run id `57eb77c3d466` and planned live
directory `data/interim/phase5/core-diagnostic-8192-01/797b223ff9f9`. That output parent
remains absent. The ordinary pilot dry-run still reports the original five IDs,
4096-token limit, cap five, zero calls and zero files written. All 67 protected files
retain hashes, sizes and write times: the original 56 plus all eleven new core-diagnostic
files. `git diff --check` passed; `git status --short` was inspected (37 existing changed/
untracked entries, including this work).

No additional provider call, prompt/schema/validator/enum/label/split change, holdout read,
commit or push occurred in this follow-up. Further live execution requires separate
authorization. Prepared future command, not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --pilot-doc google_support-d7f386f347b7 --pilot-max-tokens 8192 --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/core-diagnostic-8192-01
```

Preserve every saved run. Extraction quality and M1 remain unassessed.

## Phase 5 - safe diagnostics and one-document controls prepared offline (2026-10-01)

Historical preparation snapshot; the user subsequently executed the core diagnostic
reported above. Its formerly absent output directory is now occupied.

Future extraction inputs, failures and events retain request identity without prompt text or human labels/notes. Groq may inspect rejected output transiently up to 65,536 characters, retaining only character count, JSON state/error position and safe application-validation error types/paths. Up to 32 findings and 16 path components are retained with a total error count; invented names become `*`. Generated text, values, validation prose and error input/context remain omitted. The inspection does not accept, repair or cache a rejected response; application-valid output does not establish vendor wire-schema validity.

Known finish reasons are captured only when provided, including through new cache entries; old entries remain readable with an unknown finish reason. New extraction manifests label `usage_scope=recorded_provider_usage_only`, count `provider_calls_without_recorded_usage` across retries/fatal errors, and set `usage_totals_complete=false` when needed. Known numeric usage remains counted when content is withheld. These fields do not establish billing, and character counts are not converted to token estimates.

The existing pilot now supports `--pilot-doc` only for `google_support-d7f386f347b7` or `google_support-e1e5277da7e8`, after validating the unchanged full five-document manifest. It requires one attempt and cap one, preserves model/prompt/strict schema/cache/key/fresh-output guards, and refuses input overrides, resume, holdout, other stages and synthetic diagnostic mode. The default five-document pilot remains unchanged.

Relevant mocked tests: 276 passed. Full suite using `.\.venv\Scripts\python.exe`: 900 passed, 5 skipped. Both CLI dry-runs made zero calls and wrote zero files. The one-document dry-run had one eligible document, zero blocked, and dry-run id `10f2700c350b`; its planned live directory is `data/interim/phase5/core-diagnostic-01/4a8c7175f992`. The output parent remains absent. The ordinary pilot still selects the original five IDs with cap five. All 56 protected files retained hashes, sizes and write times, with none added or removed: 44 saved run files, four extraction cache entries and eight prompt/schema/validator/enum/version/manifest/label/proposal files. `git diff --check` passed and `git status --short` was inspected; the tree has 37 changed/untracked entries including previous work.

No provider call, prompt/schema/validator/enum/label/split change, holdout read, commit or push occurred. Both historical provider causes and their billing remain unknown; a new request cannot recover old charges. Live execution requires separate authorization under the user's earlier offline instruction. Prepared command, not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --pilot-doc google_support-d7f386f347b7 --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/core-diagnostic-01
```

Extraction quality and M1 remain unassessed. Candidate/pending-case persistence, precise provider-rejection vocabulary and other deferred P1 work remain pending.

## Phase 5 - P0 audit persistence, checkpoints and routing corrected offline (2026-10-01)

Applied the four P0 corrections from the adjacent correction proposal in `src/pipeline/extraction.py`, with regressions in `tests/test_extraction.py`. Future span verdicts retain candidate quotes, original offsets/offset state and repair flags alongside resolved values. Future evidence failures retain all reason codes, invalid fields and retained span ids, with gate prose bounded to 32 messages of 500 characters and filtered for the target audit text or denylisted secrets. The existing filed `validation_errors` and review priority stay unchanged. Non-`ok` checkpoints now fail consistently with stage events; blocked documents remain skipped and accepted empty responses remain succeeded. Resume reprocesses failed responses through the existing cache. This does not repair historical succeeded checkpoints, and pilot resume remains refused.

Future unassembled failures now target `extraction_attempt` with `run_id:doc_id`, retaining blocked relevance and assembled-case routes. Reconciliation for original open items `bcb6d8bbfb89` and `4a640dd99293`: they describe extraction HTTP 400 `json_validate_failed` failures for `google_support-d7f386f347b7` and `google_support-e1e5277da7e8`; they do not invalidate relevance decisions `b91599083512`/`8a60f77f4993` or their approved labels. Those saved rows stay open and unchanged. The reason mapping `provider_error` to `provider_unavailable` remains a separate pending vocabulary decision; no resolutions were appended.

Relevant mocked tests: 254 passed. Full suite using `.\.venv\Scripts\python.exe`: 878 passed, 5 skipped. The pilot dry-run selected the same five development documents, reported zero provider calls and zero files written, and left `data/interim/phase5/p0-offline-check` absent. All eleven latest-pilot artifacts still parse through existing readers, including the four review items and stage events. All 56 protected files retained SHA-256 hashes, sizes and write times: 44 files across four saved runs, four extraction cache entries, and eight prompt/schema/validator/enum/version/manifest/label/proposal files. No protected file was added or removed. `git diff --check` passed and `git status --short` was inspected; the worktree retains its 33 existing changed/untracked entries, including these edited extraction files.

The recorded 34,989 input / 5,629 output tokens and list-price estimate cover reported usage from the three responses, not a billing measurement for all five requests. Token usage and billing for the two failed requests remain unknown; the proposal's approximate 23,000 missing-input-token figure is a hypothesis, not recorded usage. P1 work and both provider causes remain unresolved. No provider calls, prompt/schema/validator changes, label/split edits, holdout reads, commits or pushes occurred. Extraction quality and M1 remain unassessed.

## Phase 5 - five-document pilot executed once (2026-10-01)

The dry-run selected exactly `google_support-d7f386f347b7`, `google_support-e1e5277da7e8`, `google_support-2a080da4b930`, `reddit-23be97c93709`, and `reddit-c49086caf891`. The manifest hash was unchanged. `data/interim/phase5/pilot-nullable-fix` did not exist. The live command then ran once and stopped: Groq `openai/gpt-oss-120b`, `extract/v1`, one attempt, cap 5, cache `data/interim/cache`. Output is `data/interim/phase5/pilot-nullable-fix/fc97bf40783c`. Previous pilot and diagnostic directories were not modified.

Technical execution: 5 eligible documents, 5 attempts, 5 provider calls, 0 cache hits, 5 cache misses, 0 analysis-valid cases. Recorded tokens were 34,989 input and 5,629 output, estimated list price 0.008127 USD. Outcomes were `ok` for `google_support-2a080da4b930` with zero cases; HTTP 400 `invalid_request` / `json_validate_failed` for `google_support-d7f386f347b7` and `google_support-e1e5277da7e8`; and `evidence_validation_failed` for the two Reddit documents. No raw response body was stored.

Offline review of the two assembled cases, against only those development documents: both carry the target `doc_id`. Fourteen span rows match the source at the repaired offsets. Three quotes are absent from the source and were rejected: both `problem_summary` strings, and the `reddit-c49086caf891` `retrieval_trigger` string. `problem_summary` is gated as `stated` and had no valid span. `retrieval_trigger` was `not_stated` while a span was attached. Both cases stay out of `retrieval_cases.jsonl`. Open review items: relevance decisions `b91599083512` and `8a60f77f4993` (`provider_unavailable`), and cases `reddit-23be97c93709#uffbf769f` and `reddit-c49086caf891#u0aa8208c` (`evidence_validation_failed`). This does not establish extraction quality. Milestone M1 is not complete.

---

## Phase 5 - offline interpretation of the latest pilot (2026-10-01)

Historical interpretation before the P0 fixes recorded above.

The two core failures retain `error_code=json_validate_failed`; they are generation/validation failures, distinct from the previous ambiguous-`anyOf` request rejection. The failed generated fields cannot be recovered from these diagnostics because the vendor's `failed_generation` body was not retained. The existing `extract/v1` instructions already require verbatim supporting quotes and empty values/no evidence for `not_stated`; the invalid Reddit outputs violated those contracts. Summary text may be an interpretation, but its supporting evidence must be a separate verbatim source quote.

The two `provider_unavailable` queue rows target relevance decisions because extraction currently routes failures without assembled cases to the upstream decision and maps `provider_error` to that generic reason. This does not show that either relevance decision or approved label is wrong, or that the provider was unavailable. Preserve the saved rows; assess future stage-specific routing separately. `ARCHITECTURE.md` and `IMPLEMENTATION-PLAN.md` now reflect the executed pilot and remaining blockers. This follow-up changes documentation only; no provider calls, prompt edits, label edits, split changes, holdout reads, commits or pushes occurred.

Four existing offline regressions passed: missing summary evidence, evidence attached to `not_stated`, fabricated quotes, and auditable schema/evidence/status failures. `git diff --check` passed, and `git status --short` was inspected. The full suite was not repeated for these documentation-only changes; its latest result remains 867 passed and 5 skipped.

## Phase 5 - revised schema accepted in one synthetic diagnostic (2026-10-01)

The user ran the prepared command against the fresh parent `data/interim/phase5/diagnostic-nullable-fix`. Run `577e727e72cc` records 1 eligible synthetic document, 1 provider call, 1 cache miss, 0 cache hits, and technical state `ok`. Its failure file is empty. Read-only inspection of the matching synthetic cache entry confirmed response keys `doc_id` and `cases`, the correct `reddit-synthetic-diagnostic` identity, and `cases: []`. The manifest records 11,562 input tokens and 287 output tokens. Its USD 0.001906 estimate is a list-price estimate, not actual billing.

This validates acceptance of the revised wire schema for that synthetic request. An empty cases array is allowed and is not a technical failure. It does not establish extraction quality on development documents or complete M1. Preserve the new diagnostic, the original rejected diagnostic, and the failed five-document pilot. Any new five-document pilot requires separate authorization and a fresh output parent. No additional provider calls or run-artifact edits occurred during this read-only follow-up; code and test results are unchanged.

---

## Phase 5 - nullable extraction wire schema fixed offline (2026-10-01)

Historical preparation entry; the separately executed synthetic compatibility check subsequently succeeded as recorded above.

The separately authorized synthetic run `577e727e72cc` made one provider attempt and was rejected with HTTP 400 `invalid_request`, `error_param=response_format`, and a message requiring disambiguation of `anyOf` branches. It produced zero cases. This establishes the rejected wire-schema shape, not extraction quality or M1.

Extraction now opts into scalar-or-null conversion in the existing Groq request-schema helper. All 19 nullable `anyOf` nodes in the extraction wire schema become equivalent `type` arrays including `null`. The three nullable scalar enum references are inlined with their original allowed values plus JSON null. Numeric bounds, null offset semantics, required fields, strict objects, and application validation remain intact. Object/complex unions are not rewritten. Relevance request conversion, application schemas, prompt instructions and versions, approved labels, split, model, budgets and retry settings are unchanged. See the implementation decision in `DECISIONS.md`.

Mocked regressions verify the transmitted schema matches the schema embedded in the prompt, valid synthetic cases pass existing assembly, invalid enums/ranges still fail, conversion is idempotent, and old cache entries remain byte-identical while the new wire-schema digest produces a new key. Focused extraction/gateway tests: 131 passed. Full suite: 867 passed, 5 skipped, 0 failed. Both pilot and diagnostic dry-runs made 0 provider calls and wrote 0 files. The diagnostic dry-run used `data/interim/phase5/diagnostic-nullable-fix`; that parent was not created. `git diff --check` passed.

SHA-256 hashes of all 22 files across the original pilot `fc97bf40783c` and synthetic diagnostic `577e727e72cc` matched before and after this work. No external requests, holdout reads, commits or pushes occurred during this fix. The changed wire digest moves the cache identity, but extraction run IDs do not include that digest; an eventual authorized check therefore needs a fresh output parent. Vendor acceptance remains unverified. Future command, prepared but not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --diagnostic --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/diagnostic-nullable-fix
```

---

## Phase 5 - one-request synthetic diagnostic prepared (2026-10-01)

Historical preparation entry: the diagnostic was subsequently executed once under separate authorization, rejected as recorded above, and its original output remains preserved.

`--diagnostic` on `run --stages extract` sends one synthetic document through `run_extraction`, the existing gateway, Groq adapter, cache, and failure persistence. It cannot be combined with `--pilot`, and it refuses `--derived`, `--input`, `--limit`, `--links`, and `--resume`, so it cannot be pointed at real documents or approved labels. Unrestricted live extraction stays refused. The strict `extract/v1` schema is unchanged.

The synthetic document is `reddit-synthetic-diagnostic`. Its relevance decision is valid, in scope, and its evidence span uses that same document id and decision id. The call is Groq `openai/gpt-oss-120b`, SDK `max_retries=0`, one gateway attempt, and an external cap of 1. The cache is `data/interim/cache`. A live run would write `data/interim/phase5/diagnostic/577e727e72cc`. A missing `GROQ_API_KEY` and an existing output directory are rejected before that directory is created. Output under `data/interim/phase5/pilot` is refused. The failed pilot artifact was not modified.

Mocked tests cover the one-call cap, no retry, missing-key rejection, occupied-directory rejection, isolation from preserved pilot output, allowlisted diagnostic persistence without credentials or source text, and a zero-call dry-run. Targeted extraction and gateway tests: 119 passed. Full suite: 858 passed, 5 skipped, 0 failed.

The dry-run was `.\.venv\Scripts\python.exe main.py run --stages extract --diagnostic --dry-run --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/diagnostic`. It reported 1 eligible document, 0 provider calls, and 0 files written. `data/interim/phase5/diagnostic` was not created. The dry-run id `9311979d8d81` was not created. No provider was called. Extraction quality and M1 remain unassessed. The live diagnostic requires separate authorization.

The exact future command, not executed:

`.\.venv\Scripts\python.exe main.py run --stages extract --diagnostic --provider groq --split development --cache data/interim/cache --call-budget 1 --max-retries 1 --output data/interim/phase5/diagnostic`

---

## Phase 5 - extraction request audited offline (2026-10-01)

The assembled Groq request for `openai/gpt-oss-120b` and `extract/v1` was inspected with synthetic text. No provider was called. `data/interim/phase5/pilot/fc97bf40783c` was not modified. The five-document manifest, cache, one gateway attempt, and five-request cap were left unchanged. No request-construction or schema-conversion defect was confirmed, so no production code changed.

Confirmed against the installed Groq SDK 0.37.1 and the local adapter:

- The call is `chat.completions.create` with model `openai/gpt-oss-120b`, which the SDK lists. Requested temperature 0 becomes the adapter floor `1e-8`, inside the documented 0–2 range. `max_tokens` is 4096. The SDK client is constructed with `max_retries=0`. `response_format` is `json_schema`, `strict` true, and the schema name is `relevance_payload`, which matches the SDK's name pattern and 64-character limit.
- Strict conversion sets `additionalProperties` false on all 11 objects and sets `required` to each object's properties. Nullable fields stay `anyOf` unions that include `{"type": "null"}`. There is no `allOf`, `oneOf`, `prefixItems`, dangling `$ref`, or `$ref` with sibling keywords. A second `groq_strict_schema` pass is identical. The schema embedded in the synthetic `extract/v1` prompt matches that transmitted schema.
- The same constraint keywords that appear here (`default`, `minimum`, `maximum`, `minLength`) also appear in the relevance schema this model already accepted. The five selected documents are 173 to 826 characters, so the shared HTTP 400 is not a context-length overflow.

The local SDK says strict mode accepts only a subset of JSON Schema and points at external structured-output documentation that is not in the install. It does not list forbidden keywords or a size limit. The vendor error body was not retained. These extraction-only shapes are therefore hypotheses, not confirmed causes: three nullable `$ref` unions, one object with 34 required properties, and a strict schema of 14,551 bytes against the relevance schema's 3,103 bytes.

The smallest separately authorized diagnostic is one request, not a retry of the five-document pilot. Use the same model, `extract/v1`, strict schema, and SDK `max_retries=0`, with one gateway attempt and synthetic text. Write to a fresh directory. Keep the returned `error_code`, `error_param`, and sanitized `error_message`. Do not execute that request until it is authorized. The occupied pilot directory will refuse the existing five-document command.

This audit's targeted extraction and gateway tests passed 109. The full suite passed 846 with 5 skipped and 0 failed. The pilot dry-run made 0 provider calls and wrote 0 files. Extraction quality and M1 remain unassessed.

---

## Phase 5 - failed pilot log inspected and diagnostics retained (2026-10-01)

The local terminal retained the originating command:

`.\.venv\Scripts\python.exe main.py run --stages extract --pilot --provider groq --split development --cache data/interim/cache --call-budget 5 --max-retries 1 --output data/interim/phase5/pilot`

It exited 0. At 2026-10-01T05:36:45Z through 05:36:47Z the gateway logged five `provider call failed` lines for `extract`, each with `technical_state` `provider_error`, `diagnostic_category` `invalid_request`, and `http_status` 400. The log does not retain a vendor message, request id, or schema path, so the specific invalid-request detail is unknown. No credentials or document text were present in those lines.

`data/interim/phase5/pilot/fc97bf40783c` is unchanged. Its failure rows still store only `provider_error` and its stage events still have no `provider_diagnostic`. SHA-256 hashes of its eleven files matched before and after this work. The new persistence cannot recover fields that run never wrote. Zero recorded tokens still do not establish billing.

Future extraction failures keep the existing allowlisted `ProviderDiagnostic` on `extraction_failures.jsonl` and stage-event detail. A string field that repeats the document audit text, the API key, or another denylisted secret is omitted; category and HTTP status remain. `test_provider_diagnostic_persists_status_without_source_or_credentials` covers that with a mock provider. Targeted extraction and gateway tests: 109 passed. Full suite: 846 passed, 5 skipped, 0 failed.

The dry-run reported 5 eligible documents, 0 provider calls, and 0 files written. `data/interim/phase5/pilot/93bd6597ff14` was not created. `git diff --check` exited 0, with only existing CRLF warnings. No provider was called, and the failed run was not retried. Extraction quality and M1 remain unassessed. The occupied destination will refuse the same live command; a separately authorized retry needs a fresh output parent.

---

## Phase 5 - existing failed pilot artifact inspected offline (2026-10-01)

Read-only inspection of `data/interim/phase5/pilot/fc97bf40783c` found a manifest with `dry_run: false`, `offline: false`, 5 provider attempts, 5 cache misses, 0 cache hits, and 0 valid cases. Each selected document has one recorded `provider_error` failure. Recorded token usage is zero. These counters represent gateway provider invocations, including possible local adapter failures; they do not prove every request reached Groq or establish actual billing. The stored failures contain only a generic error and no HTTP status or detailed provider diagnostic. The failure cause and originating execution are therefore unresolved. No run artifacts were changed and no provider was called by this inspection.

Preserve this directory. Before any separately authorized retry, investigate existing local execution logs and retain allowlisted gateway diagnostics through the existing extraction persistence path with mocked tests. Do not infer authentication, schema rejection, or provider outage from the generic errors. The current live command will refuse the occupied destination. Earlier statements that live extraction had not run describe prior preparation reports; the current workspace contains the failed live-mode artifact above. No extraction quality or M1 claim follows from it.

---

## Phase 5 - evidence-isolation fixtures corrected offline (2026-10-01)

The three previously failing evidence-isolation tests now construct relevance evidence with the same document and decision owner as their synthetic target, using synthetic target text. Production extraction code and the shared fixture helper were unchanged. The focused run passed all 3 tests; the full suite passed 845 tests with 5 skipped and 0 failed. This supersedes the failed verification below. Python execution required running outside the tool sandbox; the installed virtual environment worked there without repair.

The repeated pilot dry-run reported 5 eligible documents, 0 provider calls and 0 files written. Manifest bytes were unchanged. The dry-run output directory `93bd6597ff14` does not exist. Unlike the earlier verification, `data/interim/phase5/pilot/fc97bf40783c` already exists with output files in the current workspace. Its contents were not modified by this follow-up. The existing-directory guard will refuse a live command using that destination; preserve the existing output and choose a fresh output parent for any separately authorized future run. No provider calls, holdout access, commits or pushes occurred in this follow-up. Extraction quality and M1 remain unassessed.

---

## Phase 5 - extraction pilot verified offline (2026-10-01)

This historical offline check predates the fixture correction above. The totals here are from that run. They are not the historical 841 passed / 5 skipped preparation result, the 107 targeted tests from that preparation, or the 824 and 811 suite totals in the sections below.

`run_extraction_pilot` refuses an existing run-specific output directory before any provider call. The check is `destination.exists()`, so a partial directory with no `run_manifest.json` is refused as well. The mocked regression test is `test_pilot_rejects_partial_existing_output_before_calls` in `tests/test_extraction_pilot.py`. It creates the run directory, writes only `checkpoints.jsonl`, expects `PilotBoundsError`, and requires 0 provider calls. The partial file is left unchanged.

The five development seats are unchanged. Two are the first documents, by `doc_id`, whose approved scope and effective scope are both core: `google_support-d7f386f347b7` and `google_support-e1e5277da7e8`. Three are documents whose approved scope and effective scope are both adjacent: the validated human decisions `reddit-23be97c93709` and `reddit-c49086caf891`, plus the first remaining agreeing adjacent document by `doc_id`, `google_support-2a080da4b930`. `google_support-3d15a7ae4cd0` stays out because its human decision is pending. `google_support-5b2ec98df32b` stays out because its effective scope is core and its approved scope is adjacent. Labels, prompts, and the split were not changed.

The configured call remains Groq `openai/gpt-oss-120b`, `extract/v1`, and the existing strict Groq schema. SDK retries stay disabled. Gateway `--max-retries 1` is one attempt and no retry. `--call-budget 5` is the external cap and reserves one first attempt per uncached document. The cache is `data/interim/cache`. A missing `GROQ_API_KEY` is rejected before the output directory is created. A fatal authentication error stops the run. A fresh run directory is required; an existing one is refused. Requests do not carry human labels or notes.

Targeted command, 108 passed:

`.\.venv\Scripts\python.exe -m pytest tests/test_extraction.py tests/test_extraction_foundation.py tests/test_extraction_pilot.py tests/test_llm_gateway.py tests/test_groq_provider.py tests/test_review_queue.py -q --tb=line`

Full suite, 3 failed, 842 passed, 5 skipped:

`.\.venv\Scripts\python.exe -m pytest -q --tb=line`

The three failures are in `tests/test_extraction_evidence_isolation.py`. `make_decision` builds the evidence span with the default document id `reddit-000000000001` and then applies a different `doc_id`. `RelevanceDecision` rejects `reddit-synthetic-left` and `reddit-synthetic-target` because the span document does not match. This is unresolved. It is not an extraction result.

The dry-run was `.\.venv\Scripts\python.exe main.py run --stages extract --pilot --dry-run --provider groq --split development --cache data/interim/cache --call-budget 5 --max-retries 1 --output data/interim/phase5/pilot`. It reported 5 eligible documents, 0 blocked, 0 provider calls, 0 disagreements, and 0 files written. The pilot manifest bytes were unchanged: SHA-256 `635fdfadbb9cf139652937e4aa4d8fd112f7947c1cf4fd9fab97a78846aeb73a`, 331 bytes. `data/interim/phase5/pilot` did not exist before or after. Neither `fc97bf40783c` nor `93bd6597ff14` was created. `git diff --check` exited 0, with only existing CRLF warnings. This does not measure extraction quality. Milestone M1 is not complete. Live execution requires separate authorization and was not run.

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --provider groq --split development --cache data/interim/cache --call-budget 5 --max-retries 1 --output data/interim/phase5/pilot
```

---

## Phase 5 - five-document extraction pilot prepared offline (2026-10-01)

The preparation below predates the verification section. Its 841 passed / 5 skipped suite and 107 targeted tests are historical. The output-directory guard was added in this preparation and was checked in the later verification.

The pilot uses the existing extract stage, `ModelGateway`, `assemble_cases`, the response cache, and the call budget. It does not add another extractor. Unrestricted live extraction of the 19-document candidate manifest remains refused.

The seats come from that development candidate manifest, the effective relevance decision, and the approved scope. Two seats are the first documents, by `doc_id`, whose approved scope and effective scope are both core: `google_support-d7f386f347b7` and `google_support-e1e5277da7e8`. Three seats are documents whose approved scope and effective scope are both adjacent. Those seats include the validated human decisions `reddit-23be97c93709` and `reddit-c49086caf891`. The remaining adjacent seat is the first other agreeing document by `doc_id`, `google_support-2a080da4b930`. `google_support-3d15a7ae4cd0` stays out because its human decision is pending. `google_support-5b2ec98df32b` stays out because its effective scope is core and its approved scope is adjacent. Neither record nor its labels were changed.

`data/interim/phase5/extraction_pilot_manifest.csv` lists those five development ids with `doc_id`, `split`, and `split_version` only. The candidate manifest was not rewritten.

The configured call is Groq, `openai/gpt-oss-120b`, `extract/v1`, and the existing strict Groq schema. SDK retries stay disabled. Gateway `--max-retries 1` allows one attempt and no retry. `--call-budget 5` is the external cap, so one first attempt stays reserved for each uncached document. The cache is `data/interim/cache`. A live run would create `data/interim/phase5/pilot/fc97bf40783c`. A missing `GROQ_API_KEY` is rejected before that directory is created. A fatal authentication error stops the run. Requests do not carry human labels or notes. A response for another document is not stored as the target's case.

The dry-run was `.\.venv\Scripts\python.exe main.py run --stages extract --pilot --dry-run --provider groq --split development --cache data/interim/cache --call-budget 5 --max-retries 1 --output data/interim/phase5/pilot`. It reported 5 eligible documents, 0 blocked, 0 provider calls, 0 disagreements, and 0 files written. No output directory was created. This does not measure extraction quality. Milestone M1 is not complete. The live command below was not run.

```powershell
.\.venv\Scripts\python.exe main.py run --stages extract --pilot --provider groq --split development --cache data/interim/cache --call-budget 5 --max-retries 1 --output data/interim/phase5/pilot
```

The full suite is 841 passing and 5 skipped. Targeted extraction and gateway tests were 107 passing.

---

## Phase 5 - extraction integrated offline (2026-10-01)

The existing runner now accepts `--stages extract`. `extract/v1` is registered. Completions go through `ModelGateway`. The effective relevance decision is the validated human decision when one exists, and otherwise the stored model decision. `assemble_cases` remains the validation boundary.

The development candidate funnel is 19 approved in-scope documents, 18 eligible effective decisions, and 1 blocked document: `google_support-3d15a7ae4cd0`. Its human decision stays pending. The approved adjacent journey label is unchanged. Five eligible decisions still disagree with the approved seed label on scope or reason. Those decisions and labels were not changed.

`main.py run --stages extract --dry-run` made 0 provider calls and wrote 0 files. `main.py run --stages extract --offline --output data/interim/phase5` attempted the 18 eligible documents through the null provider, recorded `provider_unavailable`, and wrote 0 cases. Provider calls were 0. Output is `data/interim/phase5/8a6c025fdfce`. A live extract command is refused. Phase 4 remains in progress. Phase 5 integration is in progress. Milestone M1 is not complete.

The full suite is 824 passing and 5 skipped.

---

## Phase 4 - human relevance overrides prepared offline (2026-10-01)

Append-only human relevance overrides are in `src/review/overrides.py`. The pipeline builds the human `RelevanceDecision` in `src/pipeline/human_relevance.py` and checks the quote with the existing evidence ladder. A validated human decision takes precedence in `effective_decision`. The model decision is not rewritten, and the model-only evaluation is unchanged.

For run `01455c8aab03`, two of the three blocked candidates now have an eligible effective decision: `reddit-23be97c93709` and `reddit-c49086caf891`. Both are human, adjacent, `known_item_with_precise_recall_failure`, with null confidence. Their original out-of-scope decision and provider failure remain. `google_support-3d15a7ae4cd0` has an override and a pending human decision. Its reply does not name the known item, so the parent-dependent journey label was not marked valid. The effective decision stays the original out-of-scope model row. Eighteen of the 19 extraction candidates are eligible. One remains blocked. Details are in `human_relevance_reconciliation.md` beside the run. No provider was called. Extraction has not run. Phase 4 remains in progress. Phase 5 has not started.

The full suite on this tree is 811 passing and 5 skipped.

---

## Phase 4 - extraction handoff prepared offline (2026-09-30)

The stored `relevance/v5` run `01455c8aab03` was checked against the approved
labels by `doc_id`. The recorded totals stand: 35 targets, 6 cache hits, 29
external attempts, 34 valid decisions, 1 technical failure kept as an
abstention, 0 missing predictions, scope agreement 28/35, exact reason
agreement 22/35, core recall 8/8, and core precision 8/11. No historical
artifact was rewritten.

The handoff is
`data/interim/phase4/development/01455c8aab03/extraction_handoff.md`.
The candidate manifest is
`data/interim/phase4/development/01455c8aab03/extraction_candidate_manifest.csv`:
19 development records, 8 core and 11 adjacent, with `doc_id`, `split`, and
`split_version` only. It does not authorize an extraction call.

Three approved in-scope records do not meet the current validated-relevance
prerequisite: `google_support-3d15a7ae4cd0` and `reddit-23be97c93709` are
`out_of_scope`, and `reddit-c49086caf891` is `provider_error`. No override
was written and no decision was manufactured. `relevance/v5` is unchanged.
The holdout remains locked. No provider was called. Phase 4 remains in
progress. Extraction implementation is separate and has not run. Phase 5
has not started.

---

## Phase 4 - relevance/v5 development evaluation (2026-09-30)

One live development run completed at
`data/interim/phase4/development/01455c8aab03`. The command was
`.\.venv\Scripts\python.exe main.py run --stages relevance --provider groq --split development --cache data/interim/cache --call-budget 35 --max-retries 1 --output data/interim/phase4/development/01455c8aab03`.
It was not rerun. Groq, `openai/gpt-oss-120b`, and `relevance/v5` were unchanged.
SDK retries stayed disabled. Gateway `--max-retries 1` allowed one attempt and
no retry. The external cap was 35.

All 35 development targets were attempted: 6 cache hits, 29 external attempts,
34 valid decisions, 1 `provider_error`, and 0 missing predictions. The failure
is `reddit-c49086caf891`, one HTTP 400 `invalid_request_error`, with no second
attempt. This run's tokens are 88929 input and 39145 output. The estimated
list price is USD 0.036826. Actual billed cost is unknown. The six cache hits
reuse the v5 smoke responses. That smoke's historical 19033 input tokens,
10392 output tokens, and USD 0.00909 estimate are not included here. The
account is paid.

Against the approved labels, overall scope agreement is 28/35 and exact reason
agreement is 22/35. The abstention stays in both denominators. Core recall is
8/8 and core precision is 8/11. Twelve predictions match the adjudicated v4
outputs, twelve agree more than v4, seven agree less, and four change without
a net agreement gain. The transcript date-range reading and the Camaro
core/adjacent boundary remain open. Five development replies received a
development parent. Holdout text was not read. This is development evaluation,
not product performance. The prompt was not tuned. Phase 5 has not started.

---

## Phase 4 - relevance/v5 development smoke (2026-09-30)

One live smoke ran at `data/interim/phase4/smoke/3417ebc5ea87` with Groq
`openai/gpt-oss-120b` and `relevance/v5`. The command was
`.\.venv\Scripts\python.exe main.py smoke`. It used the existing cache and a
new directory. Six development targets were classified. There were 6 external
attempts, 0 cache hits, 6 valid decisions, 0 failures, and 0 unattempted
records. The call budget was 6. This run's tokens are 19033 input and 10392
output. The estimated list price is USD 0.00909. Actual billed cost is
unknown. Cached input tokens were not reported, so the estimate uses the
input rate. The account is paid; this is not free-tier usage.

The v4 smoke at `data/interim/phase4/smoke/10aa3135aaea` is unchanged. Its
historical usage, 16309 input tokens, 5236 output tokens, and USD 0.005588
estimated, was not reused, because the prompt version differs. Those amounts
are not part of the v5 total.

Against the approved labels, v4 scope agreement on these six is 6/6 and
reason agreement is 3/6. v5 scope agreement is 5/6 and reason agreement is
5/6. The praise review now uses `no_retrieval_need_or_attempt`. The transcript
and Camaro reason codes now match the approved codes. The waterfall reply
moved from the approved adjacent journey code to `no_retrieval_need_or_attempt`.
The transcript date-range reading and the Camaro core/adjacent boundary remain
unresolved. The waterfall reply received its development parent. No holdout
text was read. This is development feedback, not unbiased product performance.
The other 29 development records were not scored. The prompt was not tuned.
Phase 5 has not started.

---

## Phase 4 - relevance/v5 prepared offline (2026-09-30)

`relevance/v5` replaces `relevance/v4` in the prompt registry. The new
instructions are general: an unsuccessful formulated search is not, by
itself, an unformulable query; recognized photos, reference photos,
previously surfaced Memories, and identified sets can be targets without a
filename; core still requires supported incomplete recall or difficulty
expressing cues; organization advice and feature requests can address a
real retrieval problem; missing, lost, and recovery wording do not establish
a cause; a specific supported reason is preferred; and a verbatim quote must
also support the decision. Approximate date ranges and a named object plus
a failed broader search are not turned into universal rules.

The prompt version is part of the cache key and the holdout lock. A v4 lock
does not authorize a v5 run. The Groq model remains `openai/gpt-oss-120b`.
Strict structured output, the per-request `doc_id` enum, nullable required
offset keys, application validation, development-only parent context, SDK
retries disabled, and the existing call budget are unchanged. The confidence
threshold and review routing are unchanged. No provider was called. No live
smoke or development classification was run. The holdout was not unlocked.
Phase 5 has not started.

`.\.venv\Scripts\python.exe -m pytest -q` passed 752, with 5 skipped. The
skips are the architecture checks that allow `src/llm/providers/` as the
adapter location. `git diff --check` reported no whitespace errors.

---

## Phase 4 - approved development adjudication (2026-09-30)

The researcher approved all 21 development adjudications: 13 retain their
scope and reason, 7 correct only the reason, and the airshow record corrects
both scope and reason. The eight approved edits were integrated by `doc_id`.
All 50 seed rows remain complete and unique: 12 core, 15 adjacent and
23 out of scope. Source/generated columns, original notes and row order are
preserved. The other 29 rows, including all 15 holdout rows, are unchanged.

The pre-adjudication and adjudicated snapshots, 21-record approval ledger,
comparison and evaluation are local and ignored under
`data/interim/phase4/development/051b96043d3e/adjudicated-2026-09-30/`.
Notes predating corrected labels remain intact; the ledger has the current
rationale. Original run artifacts and split/smoke manifest hashes are unchanged.

Saved split strata describe the labels at split creation. Membership remains
35 development and 15 holdout; current adjudicated development counts are
8 core, 11 adjacent and 16 out of scope. The evaluator loads an existing
valid manifest and checks document-ID coverage without re-stratifying revised
labels. Initial split creation retains its fixed-count rules. Do not regenerate
or rebalance the split or smoke manifest from adjudicated labels.

The same 35 stored `relevance/v4` decisions were evaluated offline.
Scope agreement remains 25/35 (71.43%), overall and covered-only. Reason
agreement changes from 14/35 (40.00%) to 17/35 (48.57%). Core precision
remains 7/13 and recall 7/8. There are no missing predictions or technical
failures. Ten scope disagreements and eight additional reason disagreements
remain. Zero automated review items does not demonstrate calibrated
confidence or sufficient semantic-review coverage.

This is development adjudication after inspecting model outputs, not a
classifier improvement or unbiased product-performance estimate. Transcript
and Camaro boundary concerns and cross-split thread-family limitations remain.
No prompt, schema, routing rule or split membership changed. The holdout
was not evaluated or unlocked. Phase 4 remains in progress; Phase 5 has not started.

Provider calls during this task: 0. The new evaluation's Operations section
copies historical classification usage: 29 external attempts, 6 cache hits,
79093 input tokens, 26821 output tokens and USD 0.027957 estimated list cost.
Those are not new calls or usage; actual billed cost remains unknown.

Targeted:
`\.venv\Scripts\python.exe -m pytest tests/test_relevance.py tests/test_relevance_evaluation.py tests/test_relevance_governance.py tests/test_pipeline_runner.py -q`
passed 46. Full: `\.venv\Scripts\python.exe -m pytest -q`
passed 751, with 5 skipped. Two regression cases check frozen-manifest
preservation after label changes and rejection of changed document identity,
with network connections blocked.

Next: address remaining development errors and reason-selection consistency
using the approved comparison before considering another prompt revision.

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

### Evaluation preparation

Evaluation infrastructure is ready. The 15-record holdout has not been used
for prompt tuning. No live model has been called. No performance claim is
supported.

Split version `relevance-seed-split/v1`. Within each scope class, documents
are ordered by `doc_id`. Holdout seats are `floor(i * n / k)`. The local
manifest is `data/interim/phase4/relevance_split_manifest.csv`. A valid
existing manifest is kept byte for byte. An invalid one is rejected and is
not rewritten.

| Split | Core | Adjacent | Out of scope | Total |
|---|---|---|---|---|
| Development | 8 | 10 | 17 | 35 |
| Holdout | 4 | 4 | 7 | 15 |

`python main.py evaluate --split development|holdout|all` scores stored
decisions. It does not classify documents and it does not call a provider.
The report files are `data/interim/phase4/relevance_evaluation.json` and
`data/interim/phase4/relevance_evaluation.md`.

The decisions on disk are the earlier null-provider run: 35
`provider_unavailable` rows with null scope, and 15 documents with no
decision. Scoring `all` on 2026-09-29 reports 50 documents, 15 missing
predictions, abstention rate 1.0, technical-failure rate 0.7, overall
exact-scope accuracy 0.0, covered-only accuracy 0.0, 0 provider calls, 0
cache hits, 0 tokens, estimated cost 0, and no average latency. Those zeros
describe the stored null-provider rows. They are not a model score.

ADR-30 resolves the metric conflict. An `ok` prediction participates in the
three-class confusion matrix and in covered-only class metrics. A non-ok
decision or a null scope does not receive a predicted class and is excluded
from those covered-only metrics. It is an abstention, not `out_of_scope`,
and it stays in the overall end-to-end accuracy denominator. A missing
prediction does the same. Both accuracies are reported. Phase 6 gold metrics
remain the ADR-25 families.

### Holdout protection and smoke preparation

Live relevance classification defaults to the 35 development records. A live
holdout or all-split classification is rejected unless the caller passes
`--holdout-unlock` and a prompt-lock artifact whose prompt id, prompt
version, prompt hash, provider, model, temperature, and max tokens match the
run. The lock stores configuration and hashes only. Offline runs and
`evaluate` still read stored decisions, including the historical
null-provider file. No live holdout classification was run.

The development smoke manifest is
`data/interim/phase4/relevance_smoke_manifest.csv`, version
`relevance-smoke/v1`. It holds the first two development `doc_id`s in each
scope class and no human labels. A valid file is preserved.

Groq is a provisional Phase 4 relevance provider (ADR-31), configured as
`openai/gpt-oss-120b`. Anthropic remains implemented. This is not a claim
that Groq is better, and it is not a production default. One live smoke
ran on 2026-09-30: `data/interim/phase4/smoke/29e62a353084`. All six
development documents returned `provider_error` with a null scope. That is
not `out_of_scope` and not a model score. The holdout was not unlocked.
The outgoing Groq schema now requires the nullable evidence offsets. One
follow-up request, `data/interim/phase4/diagnostic/66cfe1d67820`, classified
`app_store-5e60a403ce06` and stopped after one call. The provider returned
HTTP 400, `invalid_request_error`. No request id was retained. A second
single-document attempt, `data/interim/phase4/diagnostic/66cfe1d67820-2`,
kept Groq's explanation: the generated evidence object omitted `start_char`
and `end_char`. It was not repeated. The relevance prompt was then `relevance/v3`. A fourth single-document
attempt, `data/interim/phase4/diagnostic/9a51269a90ed`, validated
`app_store-5e60a403ce06` as `out_of_scope`. It was not repeated.
The six-document development smoke then ran once at
`data/interim/phase4/smoke/c89938c1af59`: 5 external attempts, 1 cache hit,
6 valid decisions, 0 failures. Scope agreed on 4 of 6 records. Reason codes
agreed on 2 of 6. The holdout was not unlocked. A revised development smoke
then ran once at `data/interim/phase4/smoke/10aa3135aaea` with prompt
`relevance/v4`, the same Groq model, SDK retries disabled, and the existing
cache. It made 6 external attempts and 0 cache hits. All six decisions are
valid. Scope agreed on 6 of 6 records. Reason codes agreed on 3 of 6. Those
counts are development feedback, not an unbiased performance estimate.
Input tokens were 16309 and output tokens 5236. The estimated list price is
USD 0.005588. Actual billed cost is unknown. The parent of
`google_support-3d15a7ae4cd0` is the development document
`google_support-808ba579f266`; its title, text, and content hash were
supplied as separate context and included in the cache identity. Evidence
offsets stay on the reply. Two other thread families cross the
development/holdout boundary (`1px47il` and `xl693t`). That limit is
recorded. The split was not changed, and holdout text was not read for
context. Approved labels were not changed. The same prompt then classified
all 35 development documents once at
`data/interim/phase4/development/051b96043d3e`. The command used Groq
`openai/gpt-oss-120b`, the existing cache, `--max-retries 1`, and
`--call-budget 35`. SDK retries stayed disabled. The run made 6 cache hits
and 29 external attempts. All 35 decisions are valid. There were 0 technical
failures, 0 missing predictions, and 0 review items. Overall and covered-only
exact scope accuracy are both 25/35 (0.714286). Exact reason agreement is
14/35 (0.400000). Core precision is 7/13 and core recall is 7/8. This run's
token totals are 79093 input and 26821 output, estimated list price USD
0.027957. The six cache hits reuse the v4 smoke responses; those historical
token counts (16309 input and 5236 output) are not included here. Actual
billed cost is unknown. The waterfall reply's seed row stores the reply
only. The human label was reviewed with the linked parent thread, and the
model was given that development parent. Those are recorded as separate
facts. Five development replies received a development parent. No holdout
parent text was read. The cross-split families `1px47il` and `xl693t` remain
an evaluation limitation. This is a development evaluation, not a performance
claim. The holdout was not evaluated. Phase 5 has not started.
A requested temperature of 0 is sent as `1e-8`. The six-call
budget reserves one attempt for each of the six documents. A retry is allowed
only when calls remain after that reservation. Invalid credentials stop the
run. List price, retrieved 2026-09-30 from Groq's published price for this
model, is USD 0.15 per million input tokens, USD 0.075 per million cached
input tokens, and USD 0.60 per million output tokens. Missing cached-token
counts use the input rate. Actual billed cost stays unknown unless the
provider reports it. The list price is not a free-tier claim.

```powershell
python main.py smoke --dry-run
```

That dry run makes 0 provider calls. A later live smoke writes a new
directory under `data/interim/phase4/smoke/` and does not merge into the
historical `relevance_decisions.jsonl`. The budget is six provider calls.

Human labels are not placed in the prompt or a provider payload. The
classifier does not read the seed sheet. The evaluator loads the labels when
it scores stored decisions. The split reads scope class only to assign
seats, and that assignment stays in the local manifest.

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
- ADR-30 records the resolution. `relevance-seed-split/v1` is prompt
  development only. Phase 6 keeps the hash-based, platform-and-scope gold
  split. Phase 4 covered-only metrics use `ok` predictions. Overall
  end-to-end accuracy keeps abstentions. `data/gold` and
  `scripts/evaluate.py` were not created.

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

## Demonstration schedule (ADR-32)

Assignment requirement: analyze real public feedback and compare retrieval problems
with traceable evidence. Internal ambition, not a submission gate: 300 documents
across four source types. Actual corpus: 35 manually imported public documents.
YouTube is documented and unexercised. M1 is not complete.

The executable backlog is in `IMPLEMENTATION-PLAN.md` under "Demonstration backlog".
YouTube collection is implemented and covered by mocked tests. It has not been
run against the live API. Workbook import is unchanged.

Dry-run, after `YOUTUBE_API_KEY` and `AUTHOR_SALT` are in `.env`. `VIDEOS` is a
text file with one public video URL per line. This writes nothing and makes no
requests:

```powershell
.\.venv\Scripts\python.exe main.py collect --youtube --videos VIDEOS --output data\processed\youtube-import --document-limit 50 --request-budget 20 --dry-run
```

The bounded live command is the same line without `--dry-run`. It was not
executed. Do not use the pilot-import directory as `--output`.

The local evidence browser reads the saved development outputs. It does not
call a model, load holdout text, or rewrite cases. Verified at
`http://127.0.0.1:8765/`: 35 collected development documents, 15 holdout
withheld, 16 excluded as out of scope, 2 failed extractions, 2 automatically
valid cases, 35 human relevance labels, 3 unresolved review items, and 0
semantically approved cases. No provisional group is proposed.

```powershell
.\.venv\Scripts\python.exe main.py browse --port 8765
```

## Research batch

`main.py run --research-batch` reuses normalization, deduplication, relevance,
and extraction. It is not the five-document pilot. Output stays under
`data/interim/research-batch`. The frozen split, approved labels, and prior
phase runs stay in place.

Dry-run of `data/processed/pilot-import/collected_documents.jsonl` with
`--document-limit 20`: 50 excluded as frozen, 0 selected, 0 provenance
failures, 0 provider calls, 0 files written, maximum external requests 0.
The 22-document and 35-document imports were the same shape: every id is in
the split. `data/interim/research-batch` was not created. No model call was
made. There is no YouTube collection file to add.

```powershell
.\.venv\Scripts\python.exe main.py run --research-batch --stages normalize,dedupe,prefilter,relevance,extract --input data\processed\pilot-import\collected_documents.jsonl --output data\interim\research-batch --document-limit 20 --dry-run
```

That command was executed. It is the current offline check for this corpus.
Do not run the live relevance or extraction commands against these files:
their request counts are 0.

After a collected JSONL has documents outside the split, run the same dry-run
with that `--input`. Use the printed `relevance requests` and
`extraction ceiling` as the two budgets. Combined, they are at most 40.
Provider `groq`, model `openai/gpt-oss-120b`, temperature 0 (Groq sends
`1e-8`), max tokens 4096, `--max-retries 1`. Cache is `data\interim\cache`.
A hit is not an external request. New content misses. These commands were
not executed:

```powershell
.\.venv\Scripts\python.exe main.py run --research-batch --stages normalize,dedupe --input COLLECTED --output data\interim\research-batch --document-limit 20
.\.venv\Scripts\python.exe main.py run --research-batch --stages prefilter,relevance --input COLLECTED --output data\interim\research-batch --document-limit 20 --provider groq --cache data\interim\cache --call-budget RELEVANCE_REQUESTS --max-retries 1
.\.venv\Scripts\python.exe main.py run --research-batch --stages extract --input COLLECTED --output data\interim\research-batch --document-limit 20 --provider groq --cache data\interim\cache --call-budget ELIGIBLE_COUNT --max-retries 1
```

Do not pass `--pilot`. Normalize writes `normalize\`. Relevance writes
`relevance\`. Extraction writes `extract\`. Review checklist, printed by the
dry-run: `retrieval_trigger` is the stated need, not the search method;
impact and severity need a quote that states them; `problem_summary` evidence
must support every factual clause; quotes must be one continuous span.

Do not open the holdout, change approved labels or the split, or rerun the
five-document extraction.

## Next command

The single frozen measurement has been consumed and scored. Do not rerun it:
the claim and scoring guards refuse another measurement. Inspect the current
report through `data/exports/quality/CURRENT.json` and the app's Methodology
and limitations page. No further provider request is needed for this result.
Further corrections belong to development, with a new configuration and a
genuinely untouched evaluation cohort before an unseen-performance claim.

### Historical development-only proposal (superseded)

Current development diagnostic uses approved reference revision 02 at
`data/exports/quality/development-reference-revision-02-2026-10-04-01/`.
The reference-definition decision is resolved and the correction findings are
approved separately. Implement/test corrective work before freezing development. Holdout stays
locked. A repeatable offline recheck uses saved outputs and a fresh destination;
the proposed command below is not a live model run and has not been executed:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py `
  --gold data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02/development-reference-02 `
  --split dev `
  --saved-run data/interim/phase5/development-corpus/3dc346ec030a `
  --relevance data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl `
  --pack data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02 `
  --prefilter-events data/interim/phase4/stage_events.jsonl `
  --out data/exports/quality/development-reference-02-offline-recheck-01
```

The historical five-document run is preserved and must not be rerun implicitly.
No prompt change or new provider request is authorized by this evaluation.

### Historical Phase 4 commands and findings

The commands and observations below describe earlier work; they are not current run
instructions or authorization to use holdout or make provider calls.

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
`doc_id`, and made 0 provider calls. Evaluation infrastructure is ready.
The 15-record holdout has not been used for prompt tuning. No live model
has been called, and no performance claim is supported. Phase 4 is not
complete. Phase 5 has not started.

```bash
python main.py smoke --dry-run
python main.py evaluate --split all
pytest tests/test_relevance.py tests/test_relevance_evaluation.py tests/test_pipeline_runner.py -q
pytest -q
```

On 2026-09-29 the Phase 4 pytest command passed 36, and the full suite
passed 710, with 4 skipped. `tests/test_relevance_governance.py` passed 8.
On 2026-09-30, after the `relevance/v4` context and prompt changes, the full
suite passed 748, with 5 skipped. After the development-run budget controls,
the full suite passed 749, with 5 skipped. After the approved adjudication
checks, the full suite passed 751, with 5 skipped. After preparing
`relevance/v5` offline, with no live predictions, the full suite passed 752,
with 5 skipped.
The smoke dry-run made 0 provider calls. The 3/6 duplicate thresholds stay
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
