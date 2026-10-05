# Approved development reference revision 02

Sunayana approved this revision on 2026-10-04:

> . I recommend a **new reference version with impact unstated, retaining severity 3**.  - go ahead with this, I approve the rest

This new pack preserves the same ten gold-dev documents, six cases, source
packets, seating manifest, scope decisions and one-human/AI-assisted method.
The nine other review files are copied unchanged from `sunayana-reviewed-01`.

For `reddit-c2c00b25a88b#g01` only:

- `impact_signals`: `{"observation": "not_stated", "value": []}`.
- Remove its one obsolete impact evidence attachment. The same source passage
  remains attached to the other supported fields, including severity.
- Severity remains **3/stated**, with its original evidence unchanged.

Reference export: `development-reference-02/` (10 documents, 6 cases,
38 retained field quote attachments). The original version has 39 attachments
and is preserved; removing an attachment does not change the source text.
Revision notes and the owner's authorization are recorded in the new cat review
and review policy. No second coder or adjudication is invented.

The rest of the six-document review is approved in the separate ledger
`data/interim/phase6/development-review-approval-2026-10-04-01/approved_findings.jsonl`.
That approval records findings and proposed corrections, not repaired saved
model output. Failed candidates remain rejected and existing browser guards
remain in force. Prompts and schemas are unchanged.

The pack passes the existing annotation validator. Saved-model reevaluation is
at `data/exports/quality/development-reference-revision-02-2026-10-04-01/`.
Five numeric development thresholds are met; model case coverage remains **2/6**.
Official gold, prior versions, runs, caches and splits remain unchanged. Holdout
remains locked; development is not frozen and final certification is pending.

`provenance.json` binds 166 protected inputs, all unchanged. The preparation
script also checks that only the authorized case-value/evidence change occurred.
