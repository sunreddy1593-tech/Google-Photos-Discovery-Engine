# Development diagnosis — 2026-10-04

Offline review of the saved `extract/v3` development run against the approved
ten-document reference. No holdout source or individual holdout prediction was
used. Saved model rows were not rewritten.

Inputs:

- `data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02/development-reference-02/`
- `data/interim/phase6/quality-dev-v3-2026-10-04-01/`
- `data/exports/quality/dev-v3-2026-10-04-01/`

The report recovers **2 of 6** reference cases. Relevance precision is **5/6
(0.8333)** and misses 0.85. Recall is 1.00 among records that were technically
ok. The cat relevance failure is excluded from that denominator, so it is not
counted as a relevance false negative. Schema and span rates are 1.00 on
accepted records.

## Six reference cases

| Reference | Routing | Extraction | Cause of the coverage result |
|---|---|---|---|
| `google_support-2a080da4b930` album | ok, adjacent; gold is the disclosed core exception | succeeded, `finish_reason=stop`, 0 cases | Accepted-empty response |
| `google_support-5b2ec98df32b` Memories | ok, core; gold is adjacent | succeeded, `stop`, 0 cases | Accepted-empty response |
| `reddit-0d477b54fb9b` older photo | ok, core, agrees with gold | 1 accepted case | Matched. Semantic disagreements remain |
| `reddit-87311c2633df` poodle | ok, adjacent, agrees with gold | succeeded, `stop`, 0 cases | Accepted-empty response |
| `reddit-bde62ddef9b5` sleeping video | ok, core, agrees with gold | 1 accepted case | Matched. Semantic disagreements remain |
| `reddit-c2c00b25a88b` cat | `evidence_validation_failed` | skipped, not eligible | Relevance technical rejection |

Case alignment did not drop a saved case. Both accepted cases matched their
reference. The YouTube document `youtube-17fd27447275` is gold out of scope and
was predicted core, then returned an accepted-empty extraction. That false
positive is the development precision miss. It is not one of the six reference
cases, and it did not create an extra accepted case.

## What kind of failure each one is

**Accepted-empty album, Memories, and poodle.** The calls were eligible and
finished with `stop`. The model returned no case. `extract/v3` already tells
the model to include a short album-scoped face search, a Memories revisit, and
the later poodle Ctrl+F attempt. This is unresolved provider behavior. One
instruction ambiguity remains: the v3 help-request rule can be read as erasing
the episode rather than only withholding `exact_query`, `query_paraphrase`, and
a performed query strategy. That is the reason for the inactive `extract/v4`
candidate. It was not activated or measured.

**Cat relevance rejection.** The retained quote joins two sentences and omits
"I remember being able to find such straightforward pictures with ease." The
evidence gate rejected that splice. Extraction correctly did not run. This is
an instruction violation caught by the existing gate, not an implementation
defect and not an accepted-empty extraction.

**Matched older photo.** `retrieval_trigger` is filled with the sentence that
describes the item, which the reference leaves unstated. The summary says the
user wants to locate an older photo, but its only attached quote is "I don't
remember when I took the photo." The model also adds an external-search
strategy, a subject `other`, and `exact_time` where the reference uses
`exact_date`. Outcome `not_found` is omitted. These are instruction and coding
disagreements. The quote gate accepts the verbatim forgotten-time sentence and
does not judge whether it supports every summary clause.

**Matched sleeping video.** The accepted quote is continuous and in the source.
The summary covers the video and the forgotten time. The model adds
`person_identity` and a stated person subject, which the reference leaves
uncertain, and it omits the successful "and up it pops" system response.
`exact_query` agrees. This is a semantic disagreement, not a spliced saved quote.

No accepted development case in this run invented a quote that failed the
source check. Impact is unstated on both matched references, and the model did
not add an impact signal there. The cat severity of 3 was never reached
because extraction did not run.

## Code changes

A valid out-of-scope decision was persisted with the same evidence-failure
review item as a rejected relevance decision. Future runs record
`skip_cause=out_of_scope` or `relevance_not_accepted`. A valid exclusion does
not open an evidence-failure review. The stage-event schema still requires a
review-group reason on every skipped extraction, so that reason code remains.
The three valid out-of-scope development documents are storage, deletion, and
editing posts. They are not reference cases. The historical run files were not
rewritten.

Relative evaluation paths are joined to the project root before approval-hash
comparison. The consumed freeze hashes were not updated. Original bytes of the
edited freeze-bound files are in
`data/interim/phase6/pre-correction-snapshot-2026-10-04-01/` and matched the
freeze before editing.

## Verification

Full suite: **1133 passed, 5 skipped**. Development dry-run of the existing
ten-document route: provider calls 0, output directory not created. Mocked
tests do not show that a live model follows `extract/v4`.
