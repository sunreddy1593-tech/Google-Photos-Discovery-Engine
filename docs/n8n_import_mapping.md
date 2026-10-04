# n8n community-thread import mapping

Current live verification, 2026-10-04: the owner published the replacement;
one bounded collection check returned execution 15, one exact original post,
no failures, one page fetch attested and zero model calls. Existing importer
privacy/provenance checks and an offline duplicate dry-run passed. This
supersedes the pending installation/live-verification wording below. Replies
remain unfetched; no model stages ran. See
`docs/n8n-parser-v2-live-check-2026-10-04-01.md` for actual limits and dates.

## Current parser verification, 2026-10-04

Execution 14 returned the collection contract but zero original posts. The
owner's saved Fetch original page output confirmed a parser defect: QAPage
markup is dynamically generated, while the original plain post is present in
thread_view. Replacement node code is `n8n/extract-original-post-v2.js`.
An offline replay recovered the exact 489-character original and passed the
existing importer's dry validation with zero requests and zero collection
records. Cloud node installation and corrected live verification are pending.
See `docs/n8n-parser-fix-2026-10-04-01.md` for field provenance and paste steps.
The earlier implementation/commands below remain available; their original
untested-connection wording is historical. Existing source-access assessment,
privacy, reply incompleteness and budget requirements remain unchanged.

## Implemented bridge, 2026-10-04

The earlier future-adapter note below is historical. `src/collect/community.py`
and `main.py collect` now support original-post collection envelopes and one
bounded collection-only n8n webhook request. The saved tagging workflow and
sheet rows remain unchanged. The live n8n connection is not yet exercised.

Envelope: `contract=community-collection/v1`, `model_calls=0`, nonempty
`execution_id`, integer `requests_made`, `items` and optional `failures`.
Each item carries direct `source_url`, matching numeric `source_item_id`,
`raw_text`, `text_kind=original_post`, timezone-aware `collected_at` and
`replies_complete=false`; title, author_name and published_at are optional.
The adapter copies text exactly, hashes authors with existing salt rules,
derives existing deterministic IDs and stores collection provenance. Author
names are dropped. Dates are not inferred. Workflow summaries are refused.
Reimporting a source URL does not append a duplicate; changed original text
fails closed for separate review. Batch output must be fresh for live webhook
collection. Import reports are unique, preserving earlier reports.

Tested offline import/dry-run commands:

```powershell
.\.venv\Scripts\python.exe main.py collect --n8n-export path/to/collection.json --document-limit 20 --dry-run --output data/processed/community-import-plan
.\.venv\Scripts\python.exe main.py collect --n8n-export path/to/collection.json --document-limit 20 --output data/processed/community-import-01
```

After publishing the **separate** collection-only workflow and setting
`N8N_COLLECTION_WEBHOOK_URL`, `N8N_WEBHOOK_KEY` and `AUTHOR_SALT` in `.env`:

```powershell
.\.venv\Scripts\python.exe main.py collect --n8n-collect path/to/thread-urls.txt --document-limit 1 --request-budget 1 --dry-run --output data/processed/community-live-01
.\.venv\Scripts\python.exe main.py collect --n8n-collect path/to/thread-urls.txt --document-limit 1 --request-budget 1 --output data/processed/community-live-01
```

The webhook client makes at most one POST, without retries or redirects; the
workflow makes at most one page fetch per listed URL. At the maximum bound this
is 1 webhook + 20 source-page requests, no model requests. The CLI dry-run makes
zero requests and writes zero records. Missing settings fail before requests
or output creation. HTTP errors are not retried; no old-route fallback exists.
The original `/webhook/photo-discovery` route is explicitly refused because it
may call Groq and default to 50 tags. Contract/start-acknowledgement mismatches,
unrequested source items or excess request attestations refuse persistence.

Next use existing research-batch stages, outside frozen evaluation seats:

```powershell
.\.venv\Scripts\python.exe main.py run --research-batch --stages normalize,dedupe,prefilter,relevance,extract --input data/processed/community-live-01/collected_documents.jsonl --output data/interim/community-batch-plan-01 --document-limit 20 --split development --provider groq --call-budget 20 --max-retries 1 --cache data/interim/cache --dry-run
```

This combined command is a zero-call plan. Live research stages remain separate
and each requires its own first-attempt request budget. For at most 20 new
documents, relevance plus extraction has a ceiling of 40 model requests, not
an unlimited extraction run. Inspect actual selected counts before authorizing
live processing. Existing research-batch pins remain relevance/v5 and extract/v2,
with their existing token bounds; v4 is only the explicit gold-dev experiment.

Official node references checked before preparation:
[Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/),
[Respond to Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/),
[HTML](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.html/).

## Historical destination proposal

The owner has an n8n workflow that fetches Google Photos Help Community threads.
This note is the destination contract for a future adapter. It is not an adapter.

No sample export from that workflow is in this repository. Do not invent its
columns, and do not run the workflow from the app or from a collector, until a
sample file is saved and its fields are checked against the list below.

## What a sample must show before any adapter is written

A sample export has to be a file we can open locally. For each thread or reply
it must show, in the workflow's own column names:

- the direct source URL
- the original post or reply text, unmodified
- a stable source item id, if the workflow has one
- the time the workflow collected the row, if it has one
- any title the source page showed

If the sample uses different names, the adapter maps those names onto the
fields below. The mapping is written only after the sample is seen.

## Destination: `CollectedDocument`

Original source text and provenance stay on the collected document. These are
the fields an adapter would fill. Names in the left column are ours.

| Destination field | What it must contain |
|---|---|
| `source_platform` | `google_support` |
| `source_type` | `support_thread` for a thread, or `forum_reply` for a reply |
| `source_url` | Direct permalink, copied exactly |
| `source_url_key` | The existing importer's URL key, derived from `source_url` |
| `source_item_id` | The source's own id, when the sample has one |
| `parent_thread_id` | The parent thread id for a reply, when the sample has one |
| `source_name` | `Google Photos Help` |
| `title` | Source title, when present |
| `raw_text` | Original community text, verbatim. Not a workflow summary |
| `raw_text_sha256` | SHA-256 of that `raw_text` |
| `published_at` | Source time, when present, with a timezone |
| `collected_at` | Collection time, with a timezone |
| `collection_method` | `manual_jsonl` until a reviewed adapter exists |
| `evidence_tier` | `direct_user` only when the text is a person's own report |
| `language_reported` | Left empty unless the sample itself reports a language |
| `author_hash` | Salted hash. A username is not stored |
| `author_salt_id` | Which salt was used, never the salt |
| `doc_id` | The existing deterministic id from collection-time values |
| `ingest_batch_id` | The import batch |

`normalized_text`, `content_hash`, redactions, and duplicate links are not
collection fields. Normalization produces them later.

## What must stay out of the collected document

Workflow summaries, tags, and classifications are unreviewed annotations.
They do not go in `raw_text`. They are not human relevance labels, not
extraction cases, and not semantic approvals. If a sample contains them, a
future adapter may store them beside the document as annotations with
`reviewed: false`. This app will not treat those annotations as findings.

The frozen evaluation split, approved labels, and saved runs are not updated
by an import.
