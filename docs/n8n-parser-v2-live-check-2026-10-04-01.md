# Corrected collection node: one bounded live check

After the owner reported replacing, saving and publishing the collection Code
node, one verification was made against the same selected thread, 106429666.
The earlier failed execution 14 and offline parser artifacts remain intact.

Before the request, the dedicated endpoint and required settings were checked
without printing credentials. Both destinations were unused. An existing-adapter
dry-run made zero requests and wrote zero records. Mocked tests passed before
the live check. The diagnostic reserves its single attempt before sending.

Actual result: one authenticated webhook POST, HTTP 200, execution **15**,
contract community-collection/v1. The workflow attests one source-page fetch
and zero model calls. The local collector made zero model calls, no retry and
no redirect follow. It returned one item, no failures, and imported one document
through the existing CollectedDocument, ID, privacy and append-only conventions.
Source request counts are workflow attestations, not independent HTTP telemetry.
Invalid-key rejection was not separately exercised.

Document `google_support-1590722c07bb` preserves source item 106429666, direct
source URL, original title, 489-character body, source publication date and
collection date. Its source_text_path is thread_view[1][12], demonstrating the
corrected path on this one page. The text matches the owner's saved original
byte-for-byte; SHA-256 is
`699f570d36fbffd3fc0d0bf2c4dc6cebd3a5620f51b0256b69a5b0b00cb1158a`.
The author is hashed; no plaintext author field is persisted. Replies were not
fetched and completeness remains false. An offline reimport dry-run recognizes
the existing item, writes zero records and leaves the JSONL bytes unchanged.

Publication remains **2021-04-16T15:27:49.885Z**, collection is
2026-10-04T15:13:47.322Z. This is a historical test thread, not newly published
feedback. Corpus eligibility/recency must be reported honestly; this check
does not amend the configured recency window or approve a retrieval case.

Artifacts:

- `data/interim/community-webhook-parser-v2-check-2026-10-04-01/`: plan,
  supplied/requested URLs, first-attempt reservation, diagnostic, provenance
  checks and a snapshot of prior integration metadata.
- `data/processed/community-webhook-parser-v2-check-2026-10-04-01/`: one
  collected_documents.jsonl row and a uniquely named collection report.

No normalization, relevance classification or model extraction was run. No
gold/split, label, prompt, cache, historical record or review decision changed;
no holdout text was accessed. No commit, push or deployment was made locally.
The owner published the node update in their n8n account. This verifies that
selected thread only and does not resolve broader source-access permissions.

The diagnostic now retains the corrected parser's four known structural
failure codes while replacing arbitrary error text with unrecognized_failure.
Focused mocked collection/parser/diagnostic tests: **31 passed**. Full suite:
**1230 passed, 5 skipped**. Git diff --check passed with line-ending warnings
only. Current results are also recorded in STATUS.md and CHANGELOG.md.
