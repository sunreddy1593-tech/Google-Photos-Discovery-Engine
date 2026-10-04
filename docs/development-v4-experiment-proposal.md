# Optional bounded development experiment

The extraction-only v4 experiment was authorized and completed once with six
requests. Its approval is consumed. Actual results and semantic findings are in
`docs/development-v4-results-2026-10-04.md`: five accepted cases, four matched of
six, precision 0.8333. The paired relevance/v6 proposal below has not been run
and needs separate authorization; it is not covered by the completed approval.
Both routes are development-only, outside the consumed holdout measurement.

The previously prepared `extract/v4` prompt clarifies that a help request can
describe a genuine retrieval episode without constituting a performed query.
It aims to reduce accepted-empty album, Memories and poodle outputs.

`relevance/v6` is the paired inactive candidate for the other two development
misses. It tells the model to quote one continuous sentence instead of joining
sentences, and to treat a short lost-or-oldest title with no retrieval attempt
as `insufficient_evidence_for_a_case`. It does not relax the evidence gate, does
not change the 0.85 precision threshold, and does not guarantee that a live
model will recover the cat case or correct the YouTube false positive. The
active pin remains `relevance/v5`. Passing only `extract/v4` still reuses
compatible relevance/v5 cache entries.

A new paid run is optional; the saved-data demonstration already works. Neither
candidate can rewrite the consumed holdout measurement or record semantic
approval.

The explicit gold-dev route can request either candidate or both. The default
remains measured v3 for the quality runner and v2 for legacy modes.
Original freeze-bound bytes and all existing measurements remain preserved;
the candidate cannot enter the old freeze or the consumed holdout experiment.

```powershell
.\.venv\Scripts\python.exe scripts\quality_run.py --split dev --candidate-prompt extract/v4 --candidate-relevance relevance/v6 --out data/interim/phase6/quality-dev-v6-2026-10-04-01 --cache data/interim/cache --call-budget 20
```

Ceiling: 10 relevance and 10 extraction external requests, total 20. Groq
`openai/gpt-oss-120b`; relevance/v6 output 4096 tokens; extract/v4 output 8192;
temperature 0 (adapter 1e-8); SDK retries 0; gateway attempts 1. A
relevance/v6 request does not reuse a relevance/v5 cache entry. V3 extraction
cache cannot satisfy v4. An extract/v4-only run can still reuse relevance/v5.
Every stage reserves first attempts. Fresh-output and missing-key guards apply.

Do not run this command without owner approval of this particular new budget.
After one run, score only gold-dev into a fresh development report, retaining
technical failures, accepted-empty results, all six reference cases and semantic
disagreements. Do not open or iterate against holdout, silently retry, or use
human references as model predictions. Paid results may still miss the targets.

The implemented dry-run of the extraction route selected ten documents, reported
zero provider calls and created no output parent. Mocked tests verify v3/v4
cache isolation, v5/v6 relevance cache isolation, unchanged pins, manifest
versions, refusal of either candidate on holdout, and zero-call dry-run.
