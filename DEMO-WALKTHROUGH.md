# Discovery-engine demonstration walkthrough

Current executable walkthrough: `docs/submission-readiness-2026-10-04.md`.
The app now includes separate evidence and comparison surfaces over six
already-approved development reference cases. Those human reference cases
do not change or approve saved model outputs. A curated Streamlit Cloud
package is prepared; it is not yet deployed. The older chains below remain
historical diagnostic examples.

This note shows an evaluator how one public post becomes a reviewed research record: source text, an exact quote, an extracted claim, then a semantic check of whether that quote supports the claim. Counts below are taken from `STATUS.md` and the saved review notes named in each table. They are not estimates.

The October demonstration is not Milestone 1. M1 is technically complete. The
bounded holdout measurement passed five numeric thresholds and recovered 5 of
15 reference cases; those seats had prior development exposure. Development
`extract/v3` recovered 2 of 6 reference cases and missed relevance precision.
No model case is semantically approved. This note does not authorize another
model call, a repeated holdout measurement, or a deploy.

## What to read as current

Start with the current result at the top of `STATUS.md`, then
`docs/quality-verification-2026-10-04.md` and
`docs/development-diagnosis-2026-10-04.md`. The chains below are historical
examples from the saved pilot and YouTube reviews. The 2026-10-03 notes are:

- `data/interim/phase5/core-diagnostic-v2-detail-fix-semantic-review.md`
- `data/interim/phase5/pilot_v2_8192_correction_proposal.md`
- `data/processed/youtube-discovery-2026-10-02/collection-review.md`
- `data/processed/youtube-discussion-2026-10-03/collection-review.md`
- `data/interim/youtube-discussion-2026-10-03/relevance-review.md`
- `data/interim/youtube-discussion-2026-10-03/extraction-review.md`

Older sections of `STATUS.md` still say the YouTube API is unexercised and that no research-batch model call was made. Those sentences predate the live batch recorded in the header and in the 2026-10-03 review notes. This walkthrough follows the dated notes for that batch.

Saved YouTube artifacts use fixed timestamps (extraction files dated 1 October; relevance `decided_at` of `2026-09-27T00:00:00Z`). The live run was 3 October. Do not read those fields as wall-clock times.

## Corpus

| Set | n | What it is | Source |
|---|---:|---|---|
| Manual pilot documents | 35 | Public records with permalinks and verbatim text, imported from the private workbook. Sources named: Google Photos Help, Google Play Store, Apple App Store, YouTube, Reddit. Per-source counts are not in `STATUS.md` or the review notes. | Phase 2 |
| Search-log sessions | 7 | Validated workbook rows. Not documents. | Phase 2 |
| Import result | 35 accepted, 0 rejected, 3 shared-URL warnings | A repeated URL is a listing or thread, not a duplicate document. | Phase 2 |
| Normalization | 35 derived, 0 redactions, 0 duplicate links | Closest pair Hamming distance 21. Five documents are under the 25-token dedupe minimum. A reviewer marked the 10 nearest pairs (distances 21–23) as distinct. | Phase 3, 2026-09-27 |
| Prefilter | 35 routed to classify, 0 dropped | Eight documents mention backup, deletion, storage, or account words. None matched two multi-word exclusion phrases. | Phase 4, 2026-09-27 |
| Human seed labels | 50 | 35 labeled 2026-09-27, 15 more on 2026-09-29. Not the Phase 6 gold set. | Phase 4 |
| Labels after adjudication | 12 core, 15 adjacent, 23 out of scope | All 50 rows remain. 21 development adjudications were approved: 13 unchanged, 7 reason-only corrections, 1 scope-and-reason correction (airshow). | 2026-09-30 adjudication |
| Frozen split membership | 35 development, 15 holdout | Created as development 8 core / 10 adjacent / 17 out of scope, holdout 4 / 4 / 7. After adjudication, development labels are 8 core, 11 adjacent, 16 out of scope. The split was not rebalanced. | Phase 4 |
| `relevance/v5` on development | 35 attempted | 6 cache hits, 29 external attempts, 34 valid decisions, 1 `provider_error` (`reddit-c49086caf891`). Scope agreement 28/35. Exact reason agreement 22/35. Core recall 8/8. Core precision 8/11. Development feedback, not product performance. Holdout was not scored. | Run `01455c8aab03` |
| Extraction seats | 5 development documents | The only documents sent through the five-document extraction pilot. Listed below. | Phase 5 |
| Semantically approved extraction cases | 0 | Automatic validity is not approval. | Five-document review and browser note |

The internal ambition of 300 documents across four source types is not the corpus. The submission corpus for the manual import is 35 documents.

Latest full test suite recorded on 2026-10-03: 1008 passed, 5 skipped, 0 failed. That is a code check, not an extraction-quality result.

## Five-document extraction funnel

Run `data/interim/phase5/pilot-v2-8192-01/024f9b18b60f`. Prompt `extract/v2`, Groq `openai/gpt-oss-120b`, max tokens 8192. Five eligible development documents. One cache hit (`google_support-d7f386f347b7`). Four provider calls. Four cache misses.

Recorded usage: 35,381 input tokens and 7,325 output tokens, estimated list cost USD 0.009702. One provider call has no recorded usage, so `usage_totals_complete` is false. That figure is not a total for every call and is not billing.

| Document | Technical outcome | In `retrieval_cases.jsonl` | Semantic approval |
|---|---|---|---|
| `google_support-d7f386f347b7` | `ok`. Cached transcript case `#c01`. | Yes | No |
| `google_support-e1e5277da7e8` | `ok`. Camaro case `#c01`. | Yes | No |
| `google_support-2a080da4b930` | `ok`, zero cases, `finish_reason=stop`. | No case | No episode was extracted. The empty payload is a recorded omission, not a finding that the post has no episode. |
| `reddit-23be97c93709` | `evidence_validation_failed`. Spliced summary quote. | No | No. The case stays out of analysis. |
| `reddit-c49086caf891` | `provider_error`. HTTP 400 `json_validate_failed`. | No | No claim was retained. |

New open review items from this run: `fe81d5c8e426` and `b7031346833a`. `STATUS.md` also says four earlier review items remain open. It does not list those four ids in that sentence.

An earlier local browser check in `STATUS.md` reported 35 development documents shown, 15 holdout withheld, 16 excluded as out of scope, 2 failed extractions, 2 automatically valid cases, 35 human relevance labels, 3 unresolved review items, and 0 semantically approved cases. That page is a read of saved development output. It is not Phase 10, and the “3 unresolved” figure is an earlier snapshot than the two new items above.

## Partial YouTube sample

Two bounded collections. Neither is a representative sample.

| Batch | API requests | Saved comments | What the review says |
|---|---:|---:|---|
| 2026-10-02, two seed videos | 2 (no reply request; the first thread had zero replies, the second had no threads) | 1 | The Korean comment invites viewers to share recovery tips and promotes a guide. It does not describe the author’s own retrieval episode. Insufficient for problem comparison. |
| 2026-10-03 discussion batch | 2 (one thread list, one reply list) | 20 | The document limit stopped collection during Dottotech’s video. Howfinity’s video was not started. Order-dependent sample from one video. One thread with five replies was fetched to completion. The video-level report stays incomplete. |

Offline dry-run before the model stages: 20 documents outside the frozen split, 0 provenance failures, 0 redaction spans, 0 duplicate links, all 20 queued by the prefilter, 0 model requests.

Relevance run `a8515d4d5758`: 20 calls, 0 cache hits, all 20 technically ok and automatically valid. 19 out of scope, 1 adjacent, 0 core. Recorded usage 61,931 input tokens and 15,353 output tokens; estimated list cost USD 0.018501, not billing. These are model decisions, not human-approved labels. No decision requested human review. The one adjacent document, `youtube-8c01bd1e27bd`, was still sent to extraction because it met the extraction rule.

Extraction run `ae60feaa840d`: one call on `youtube-8c01bd1e27bd`, one cache miss, zero valid cases, no retry. Groq HTTP 400, `json_validate_failed`, rejected output of zero characters, invalid JSON at position zero, `application_state=not_checked`. No generated text was kept. Usage for this call is unavailable. Across relevance and extraction the batch made 21 model requests. Combined billing is unknown.

Preliminary screening in the collection review, not an approved label: `youtube-8c01bd1e27bd` reports that location search now returns only 2024 results and previously returned all years. That is a coverage complaint. It does not establish incomplete recall of one known photo. `youtube-b8581b3842fb` is about duplicate-photo management. `youtube-90c7aa2b6c9b` is about finding a video on the channel. Other comments are appreciation, tutorial timestamps, or unrelated support requests.

The relevance review says the retained quote matches the source exactly, and that the model’s reason summary treats the coverage complaint as a known-item failure. The review notes do not paste that comment. There is no extracted claim to approve.

## Walkthrough

### 1. Transcript photo — valid record, unsupported claims

**Source.** Development document `google_support-d7f386f347b7`, 173 characters. Case `google_support-d7f386f347b7#c01`, stored from run `data/interim/phase5/core-diagnostic-v2-detail-fix-01/84608e7b3eb7` and reused as the cache hit in the five-document run. The semantic review copies the source as:

> A photo of a transcript of exam results that was a work between January and April 2019. I have searched for it all over my back up albut can't seem to find it. Kindly assist

**Exact quotes that the gate accepted.** Both are verbatim substrings.

- `retrieval_trigger` quote: `I have searched for it all over my back up albut can't seem to find it.`
- `problem_summary` quote: `A photo of a transcript of exam results that was a work between January and April 2019.`

Nine candidate spans were `supplied_exact` and valid. Seven unique quotes sit at the recorded offsets. Technical state `ok`, `validation_state` `valid`, `needs_human_review` false. That is the first run that stored an analysis-valid case.

**Extracted claims the review does not approve.**

- `retrieval_trigger` = `search backup`. The field is why the item was needed, when the post states that reason. The quote describes the search and the miss. The supported observation is `not_stated`.
- `problem_summary` says the user cannot locate a photo of a transcript from January to April 2019 in their backup. The attached quote supports the photo, the transcript, and the date range. It does not support “cannot locate” or “in their backup”; those words are in the second sentence, which is not this field’s evidence.

**Semantic review.** Passing the evidence gate did not approve either claim. The same mis-filing of a search method as `retrieval_trigger` was left unchanged when the five-document run reused this cache entry.

### 2. White Camaro — valid record, mixed support

**Source.** `google_support-e1e5277da7e8#c01` in the five-document run. The correction proposal does not reproduce the whole post. It does reproduce one attached quote.

**Exact quote.**

> while it pulled up every other car I’ve ever owned, the white Camaro is missing

**Extracted claims.**

- `problem_summary`: the user could not locate the photo of their white Camaro using the car search option. The quote supports “missing” and “white Camaro”. It does not contain “photo” or “car search option”. Both phrases occur earlier in the same paragraph.
- `retrieval_trigger` = `car search option`. That is the search method, not a stated reason the item was needed. No reason is stated.
- `impact_signals` = `time_loss`. The quote does not mention time. `severity` stayed `not_stated`, which the review accepts.
- `query_strategies` = `not_stated`. The review says this is not justified: the source says the user went back using the car search option, and that method was filed as the trigger instead. The enum value that quote supports is `other`.

**Semantic review.** The case is in `retrieval_cases.jsonl` and is not approved. Claims the review treats as supported, and therefore not part of the defect list: a photo of an old Camaro from the 2000s, subject `vehicle`, and partial car results in which the Camaro is absent.

### 3. Snapseed backup — quote rejected before analysis

**Source.** `reddit-23be97c93709`, candidate `reddit-23be97c93709#u3bff3392`.

**Exact saved quote.** The correction proposal copies it as:

> I backed up a large portion of my gallery ... all my Snapseed edited photos ... I've tried searching "edited" and things like that to no avail.

The full string is not in the source, and the source contains no ellipsis. The three fragments do occur, in that order. Between the first and second, the source has ` and Google Photos backs up without putting pictures in any folder and so `. Between the second and third, it has ` and others are mixed in with thousands of other pictures. `. Offsets were null. `repair_applied` is false. The quote was not repaired.

**Extracted claim.** A `problem_summary` built by joining three passages. Other spans on that candidate validated. The case was still withheld.

**Semantic review.** There is no analysis record to approve. A verbatim fragment is not a license to splice.

### 4. Family member in a non-shared album — empty extraction

**Source.** `google_support-2a080da4b930`. The review describes the post; it does not paste a verbatim quote. Described content: the author is trying to find one family member in a non-shared album, face search inside that album is unavailable, and the remaining path is scrolling through hundreds of photos.

**Exact quote.** Not copied in the review notes. No quote was retained because the model returned `cases: []`.

**Extracted claim.** None. Technical state `ok`, `finish_reason=stop`.

**Semantic review.** The contract allows zero cases when a document has no retrieval episode. This document has one. Emptiness is the model’s omission. The pipeline correctly kept that empty payload as success. Success here means “the response was well-formed,” not “the post has nothing to extract.”

### 5. YouTube location search — classification only, extraction failed

**Source.** `youtube-8c01bd1e27bd`, outside the frozen 50-document split. One of 20 comments from the partial Dottotech sample.

**Exact quote.** The relevance review says the retained quote matches the source and supports a location-search coverage regression (only 2024 results, previously all years). The review notes do not include the comment text, so it is not copied here.

**Extracted claim.** None. The single extraction call failed before a case was saved.

**Semantic review.** The model’s reason summary interprets the coverage complaint as a precise failure for a known item. The review says the quote does not name a particular known item or a concrete older photo. That classification must not be reported as an approved known-item episode. Automatic validity of the relevance decision (technical state ok, no human-review flag) is not that approval.

## Automatic validation and semantic approval

| Check | Question it answers | What it does not answer |
|---|---|---|
| Span ladder | Does this quote occur in the target document at a resolvable offset? Exact match, offset repair, or whitespace repair. A quote that is absent is `fabricated` and invalidates the record. An inserted `...` is not repaired. | Whether the quote means what the label says. |
| Status and evidence rules | Does a stated field have evidence, and does a `not_stated` field have none? | Whether the chosen enum is the right reading. |
| Analysis gate | Is `validation_state` valid, so the case may sit in `retrieval_cases.jsonl`? | Whether a person accepts the interpretation. |
| Semantic review | Does the quote support every factual clause of the claim? Is `retrieval_trigger` the stated need rather than the search method? Does an impact label such as `time_loss` quote the user saying time was consumed? | It does not rewrite the saved case, the quote, the label, or the split. |

Groq’s own structured-output documentation, cited in `STATUS.md`, separates schema compliance from semantic accuracy. The evidence errors above are model contract violations. They are not a reason to relax the gate.

A case can be automatically valid and still be the wrong claim. The transcript and Camaro rows are that case. A response can be technically `ok` and still have dropped a real episode. The album post is that case. A rejected splice never becomes a finding just because three pieces of it are real.

## Where the two tracks sit

User research and the product MVP are separate fellowship work. Spec section 1.1 says they are not a reason to relax evidence rules or to design a Google Photos solution. `STATUS.md` and the review notes contain no survey counts, so this demonstration does not confirm or contradict a survey answer.

| Track | What it contributes | What this demonstration can say |
|---|---|---|
| User research | Asks people what they remember and where finding a known photo got hard. Self-report. | The public-post chain keeps a quote attached to a claim and then checks the claim. That is a different instrument. With 0 semantically approved cases, the engine cannot yet be lined up against a survey result. |
| Product MVP | The build list is manual import, schemas, the evidence validator, normalization, dedupe, relevance, extraction, gold evaluation, taxonomy, deterministic analysis, an evidence browser, a quality report, a public export, and Streamlit deployment. Stretch items (Ask synthesis, embeddings, composite scores, extra collectors) stay deferred. | Import, schemas, validation, normalization, dedupe, a development relevance run, and a five-document extraction run exist. Gold evaluation, taxonomy, analysis, the quality report, public export, and deployment do not. The local page at `http://127.0.0.1:8765/` reads saved development JSONL. It is not the Phase 10 app. |
| This demonstration | Shows the evidence standard the MVP browser has to keep: source, quote, claim, and a human check, with failed rows left out of conclusions. | It does not propose a retrieval-problem group. No approved case exists to group. |

Development relevance agreement (28/35 scope, 22/35 reason on `relevance/v5`) is feedback on the development split after people inspected model output. It is not a holdout score and not a product-performance number.

## Limits

- Sample. 35 manual documents. Extraction was exercised on 5 of the 35 development seats, not on the 15-document holdout. YouTube added 1 comment from two videos, then 20 comments from one video, stopped by a document limit. Subgroups of one document are too small to support a rate.
- Selection. The workbook was hand-collected. The YouTube files are order-dependent API samples, not a draw from either audience. Store-review API routes inspected in the 2026-10-01 source audit are blocked. Google Photos community access is unresolved. That audit made zero data requests.
- Labels. Human scope labels exist for the 50 seed rows. They are not case-level extraction labels, and they are not double-coded gold. No case-level correction file exists. Saved model output was not rewritten.
- Model. One provider and one model (`openai/gpt-oss-120b`). Relevance prompt `relevance/v5`. Extraction prompt `extract/v2` on the runs above. No second coder on the semantic notes.
- Gate versus meaning. The gate accepts a verbatim quote that does not cover the summary. That is recorded as the ladder’s scope, not as a new defect to patch in this note.
- Truncation and failures. One 4096-token diagnostic on the transcript document failed because the provider reported that the completion limit was reached. That cause applies to that attempt only. The later YouTube extraction failure and `reddit-c49086caf891` (3,690 characters of invalid JSON, error at position 3,690, body not kept) do not establish token exhaustion. `provider_unavailable` on review item `b7031346833a` is the stored name for `provider_error`, not an outage finding.
- Language and privacy. The one saved Korean comment is a selection miss, not a retrieval case. Author names are hashed out of processed output. Holdout text was not read for this note.
- Snapshot. Manual normalization is the 2026-09-27 run. The YouTube discussion batch is the 2026-10-03 collection, with the timestamp caveat above.
- Cost. Every USD figure above is an estimated list price from recorded usage. Actual billed cost is unknown wherever `STATUS.md` says so.

## How to reproduce the reading

Do not rerun the five-document extraction. Do not start a new provider call, YouTube request, or holdout unlock from this note.

What already happened, in order:

1. Manual import of the private workbook into collected documents (35 accepted).
2. Normalize and dedupe (35 derived, no duplicate links).
3. Prefilter, then human seed labels and a frozen development/holdout split.
4. Development relevance with `relevance/v5` (35 documents). Holdout stays locked.
5. Extraction on five development seats. The 8192-token run stored two automatically valid cases, accepted one empty response, rejected one spliced quote, and recorded one unresolved JSON failure.
6. A person reviewed those saved cases against the source quotes and withheld semantic approval.
7. A separate research batch collected a partial YouTube comment sample, classified 20 comments, and failed the one extraction attempt.

The local evidence browser only reads those saved development files:

```powershell
.\.venv\Scripts\python.exe main.py browse --port 8765
```

The page is `http://127.0.0.1:8765/`. It does not call a model, load holdout text, or rewrite cases. Automatic validity is labeled as not semantic approval. Failed and unresolved records stay out of conclusions.
