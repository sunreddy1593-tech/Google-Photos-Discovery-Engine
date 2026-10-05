# Human-reviewed reference: n8n-reviewed-reference/01

Records covered: 48 (owner statement: 48).
Count matches the owner's statement: true.

## Approval basis

Owner: Sunayana. Given in: implementation conversation of 2026-10-05 authorising the reviewed n8n reference standard. Recorded on: 2026-10-05.

> I have personally reviewed the existing 48 n8n threads in detail, including their relevance, classifications, summaries and evidence quotes. Record that review as the approval basis for those exact records. Future records should be classified using that standard without requiring individual human approval before appearing in a clearly labelled automated comparison.

The review date itself was not stated and is not recorded. The approval applies to the record ids listed in `reference.json` and does not extend to later records.

## Fields reviewed

- relevance: is_retrieval_problem
- classifications: photo_type, intent, failure_stage
- summaries: summary
- evidence_quotes: key_quote
- present in each record, not separately named by the owner: title, cues_remembered, cues_forgotten, query_tried, workaround, scraped_at

## Unavailable in the saved export

- original_post_text
- author
- published_at
- quote_offsets
- severity
- impact_signals
- scope_class_core_or_adjacent
- reason_code
- replies
- review_date

## Inputs

- `n8n/discovery_sheet_template - insights.csv`: sha256 22f1463584509c5590985129c4271757954338cfd98f9e2e83f2f2db94f2f848
- `data/insights_seed.csv`: sha256 24797e10de8937b71311aaf6bdb0aff0dcf5ed3e4acffcb59d543a35e05d18fc
- records.jsonl: sha256 7d8ddc7ee0c9757d6af7c5c55523f95961af6b82d89b1dad654670deb1e21e29

## Verification

- records_with_quote: 22
- records_without_quote: 26
- quotes_verified_against_original_text: 0
- quote_verification_unavailable: 48
- quotes_equal_to_saved_title: 18
- quotes_within_saved_title: 20
- records_with_summary: 47
- records_without_summary: 1
- note: Title containment is a weak consistency check on saved sheet text. It is not verification against the original post, which the export does not include.

## Limitations

- The n8n export carries titles, workflow tags, a key quote and a summary. It does not carry the original post text, so no quote is verified against source text here.
- The n8n schema records a binary retrieval-problem flag. It does not distinguish core incomplete recall from adjacent known-item retrieval, and no scope class is inferred.
- Cues, queries and workarounds are free text and are not mapped onto the application vocabularies.
- Severity, impact, offsets, publication dates and authors are unavailable and are not inferred.
- The owner's review is the approval basis for these exact records only. It does not approve later records.
