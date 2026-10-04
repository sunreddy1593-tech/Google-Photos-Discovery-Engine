# Development evaluation with approved reference revision 02

This reevaluation uses the new owner-approved reference with cat impact
unstated and severity 3 retained. It scores the original saved model run
`3dc346ec030a`, without changing its cases or making new provider requests.

Ten documents, six reference cases. Current results:

- Schema validation and exact-source span validation: **1.00** each.
- Prefilter recall: **1.00**.
- Relevance precision: **6/7 = 0.8571**; recall **6/6 = 1.00**.
- Five numeric development thresholds are met; `quality_gate_status` is
  `development_only`.
- Accepted extraction case coverage: **2/6 = 33.3%**, with four missing cases
  (two empty-response omissions and two evidence-rejected attempts).
- Matched-case severity accuracy: **1.00**; the cat reference still has severity 3.
- Reference-disagreement/structural inference diagnostic remains **7/17 = 41.2%**.
  This is not an independently adjudicated semantic fabrication rate.

The model's cat `time_loss` remains unsupported. Both matched reference cases
now have no stated impact labels, so impact recall/F1 are undefined (**null**),
and precision is 0.00 for the model's unsupported prediction. This is a
denominator change from the corrected reference, not improved extraction.

The other review findings and correction proposals are now owner-approved in
`data/interim/phase6/development-review-approval-2026-10-04-01/`. Original model
records, approval decisions, outputs, caches, labels and the prior reference
version are preserved. The new reference follows the written impact definition;
it was not altered to match the model's time-loss claim.

No holdout source text was loaded. Official gold remains empty, original
official reports remain pending and the final quality gate stays pending.
Development is not frozen. M1's technical completion remains separate.
No production evaluation code changed; the last full suite remains
**1100 passed, 5 skipped**. This revision was checked by the existing annotation
validator, source-quote checks, exact change assertions and saved-output evaluator.

Executed offline command:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py `
  --gold data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02/development-reference-02 `
  --split dev `
  --saved-run data/interim/phase5/development-corpus/3dc346ec030a `
  --relevance data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl `
  --pack data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02 `
  --prefilter-events data/interim/phase4/stage_events.jsonl `
  --out data/exports/quality/development-reference-revision-02-2026-10-04-01
```

Do not reuse this occupied destination. Any later offline recheck requires a
fresh output; any later model experiment needs its own bounded authorization.
