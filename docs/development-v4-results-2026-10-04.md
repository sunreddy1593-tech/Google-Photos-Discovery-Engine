# One authorized development experiment: actual results

Sunayana approved one development run with at most 20 external requests.
The approval is consumed. No second run or relevance/v6 experiment is authorized
by that approval. No holdout text or predictions were used for this review.

Executed exactly once:

```powershell
.\.venv\Scripts\python.exe scripts/quality_run.py --split dev --candidate-prompt extract/v4 --out data/interim/phase6/quality-dev-v4-2026-10-04-01 --cache data/interim/cache --call-budget 20
```

Ten development documents; relevance/v5 reused ten compatible cache entries
and made zero requests. Extraction/v4 made six requests, one attempt each,
using Groq `openai/gpt-oss-120b`, maximum output 8192, requested temperature 0
(adapter 1e-8), SDK retries 0. All six finish reasons are `stop`.
Recorded usage is complete for these calls: 76,079 input and 25,338 output
tokens. Recorded list-price estimate: $0.026115; this is not a billing receipt.
No usage is inferred for older failed calls.

All six called documents succeeded technically: five accepted cases and one
accepted-empty YouTube result. Four documents were skipped: three valid
out-of-scope decisions and one evidence-rejected cat relevance decision.
The persisted extraction summary's `failed_candidates=4` and
`evidence_validation_failed=4` include these skips; they do not mean four
failed provider requests. The stored `skip_cause` distinguishes them.

Offline scoring uses the unchanged approved reference and evidence-overlap/v1:
four matched of six, two unmatched reference cases and one unmatched model
case. The v3 baseline remains two of six. Relevance precision stays 5/6
(0.8333), below 0.85. Conditional relevance recall is 1.00 after excluding one
technical failure; delivered relevant decisions over all six relevant documents
are 5/6. Schema and span validation rates of 1.00 concern accepted records.
The result is development_only, not a new holdout gate or semantic approval.

## Source-based semantic inspection

These findings are an AI-assisted review, awaiting specific human decisions.
They do not modify model records, approved reference labels or prior reviews.
All stored quotes match development text at their offsets. A matching quote
does not establish the assigned meaning.

- **Family album / google_support-2a080da4b930:** a genuine retrieval request is
  now emitted. Person, relationship and photo are supported. The first sentence
  states a search goal, not why the photo was needed; retrieval_trigger remains
  unsupported. Summary evidence includes both album scope and manual scrolling,
  but the summary converts the source's hedged "It seems" limitation into a
  categorical inability. Its scope is adjacent; the approved reference's core
  exception remains disclosed and unchanged. Final outcome, impact and severity
  are appropriately unstated. Reference face-search and uncertain scope-response
  assignments are absent from the model.
- **Memories / google_support-5b2ec98df32b:** photo and prior availability are
  supported. "to view them" states the goal, not a retrieval trigger. A question
  about how to return does not establish that navigation is impossible; the
  categorical summary overstates the source. Core also disagrees with approved
  adjacent. Unknown outcome, impact and severity remain unstated.
- **Older photo / reddit-0d477b54fb9b:** the source describes an existing older
  photo of the same item and an inability to find it. The summary's complete
  attached sentence supports its clauses. However, known-item/asset evidence is
  attached to the recent comparator photo instead of the sought older photo.
  Visual distinctness is plausible contextual support but the approved cue is
  object_or_subject. "when I took the photo" supports forgotten date, not a
  specifically forgotten clock time. Proposed Google Photos searching is not
  an observed external-app strategy. "find an older photo" is a goal, not a
  trigger. The stated not-found outcome is omitted. No impact/severity is added.
- **Poodle / reddit-87311c2633df:** a case is emitted but every attached span
  precedes the later actual CtrlF search report. None overlaps approved gold
  evidence, so the existing matcher correctly leaves it unmatched. The early
  "Say I have" setup cannot establish observed counts, chronological memory cues
  or the factual episode. Approximate-time cue is unsupported. The grouping
  intention occurs in that illustrative setup and is not sufficient observed
  trigger evidence. The summary's quote does not support the manual-scrolling
  clause, and the later performed search and zero-results response are omitted.
  Use the later first-person account in a future reviewed correction; do not
  change this saved case or the matcher to raise coverage.
- **Sleeping video / reddit-bde62ddef9b5:** video, remembered episode, quoted
  natural-language query and successful retrieval are supported. Suzie's name
  alone does not establish person rather than pet; the subject must remain
  uncertain. Forgotten "when" supports date uncertainty, not clock time.
  Activity cue and successful system response are omitted. The summary attaches
  the complete source sentence, but "typed" strengthens "I can type" into a
  definite executed action. Trigger, impact and severity are not invented.
- **Cat / reddit-c2c00b25a88b:** no extraction request or case. The cached
  relevance quote is rejected as spliced; it remains a technical blockage.
  Human reference severity 3 and impact unstated remain unchanged.
- **YouTube / youtube-17fd27447275:** accepted-empty extraction does not repair
  the cached relevance false positive. Its relevance decision still counts in
  the 5/6 precision denominator.

## Smallest next work, without another paid experiment

Review these specific semantic findings with the owner before recording any
model-case approval. Preserve existing labels and outputs. The separately
prepared relevance/v6 candidate is inactive and unmeasured; mocked quote and
short-title tests are evidence about application behavior, not model quality.
Do not activate it globally or spend again under this consumed authorization.
Resolve collection and deployment account setup in parallel using the prepared
workflow and public package. Reliable automation, unseen validation and the
larger internal gold target remain open research limitations.

Artifacts: `data/exports/quality/dev-v4-2026-10-04-01/report.json`; source spans
and cases under `data/interim/phase6/quality-dev-v4-2026-10-04-01/extraction/d7581cf180be`.
The offline inspector is `scripts/inspect_dev_v4_once.py`. No frozen measurement
file, label, original workflow or saved model response was repaired in place.
