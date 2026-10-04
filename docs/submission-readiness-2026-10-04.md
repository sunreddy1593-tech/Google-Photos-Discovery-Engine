# Submission demonstration and remaining external steps

The software demonstration now has approved reference evidence, source links,
reviewed field comparisons, memory/journey views, saved-excerpt search and
split-labeled quality aggregates. Reference labels are distinct from model
predictions. The six approved development reference cases are not six successful
model extractions and are not population prevalence. No new taxonomy or
composite opportunity score is invented from this small sample.

The one newly authorized v4 run is complete: six requests, five accepted model
cases, four of six matched references, relevance precision still 0.8333.
The quality view labels this separate development experiment alongside the
unchanged v3 baseline and consumed holdout. Specific semantic errors remain
unapproved; see `docs/development-v4-results-2026-10-04.md`. Do not rerun under
the consumed authorization.

The single-reviewer method is authorized by ADR-33. Independent agreement is
not performed, not a missing person to invent. ADR-37 makes the approved 35
documents and 21 cases the final gold set; the former 75–100 volume is closed.
Wholly unseen validation and reliable automated extraction remain research
limitations, not requirements that can be fixed by changing historic labels.

## Run and test locally

The existing process on port 8501 is retained; refresh it to see code changes.
Do not start a second process on that port. When it is stopped, launch with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

The local view retains saved pilot and YouTube datasets and shows a separate
approved development reference. Public Cloud packages intentionally contain
only the ten-document/six-case reference and quality aggregates, omitting
unapproved model outputs. The datasets are not silently combined.

Evaluator checks:

1. Open Reviewed reference evidence and select the family-album case. Inspect
   its source link, field value and exact quote offsets. Its owner-directed
   core-scope exception stays disclosed.
2. Select the sleeping-video case and inspect evidence for the successful
   outcome. Success does not make an episode irrelevant.
3. Open Problem comparison and Memory map and journeys. Every count has case
   IDs; unstated/uncertain fields remain distinguishable. These are reviewed
   reference assignments, not model quality scores or discovered taxonomy.
4. Search Ask the evidence for `photo`. Inspect saved evidence and its approval
   basis. Search an absent term and confirm an insufficient-evidence response.
5. Open Quality report. Compare configuration-labeled development results and
   the consumed reserved-holdout result. Case omissions and technical failures
   remain visible despite accepted-record validation rates of 1.00.
6. Open Community insights. Confirm that visitors cannot trigger collection,
   old n8n tagging or model spending.

## Streamlit Community Cloud

Use the final curated `data/exports/public/streamlit-cloud-2026-10-04-*` package
identified in STATUS.md, not the complete workspace or earlier draft package.
The final package is `streamlit-cloud-2026-10-04-03` and its matching ZIP.
The package has its own README, two runtime dependencies, minimum excerpts,
source links, aggregate quality pointer and file-hash audit. Private sources,
holdout packets, annotation files, workflow credentials and provider payloads
are excluded. Its app was tested independently with network requests blocked.
Full suite: 1157 passed, 5 skipped. Focused mocked checks: 40 passed. All nine
packaged app surfaces and found/absent searches passed with HTTP and external
sockets blocked; local sockets needed by Windows asyncio were permitted.

Publish only that folder's contents to a dedicated GitHub deployment repository
using the owner's account. In Streamlit Community Cloud select that repository,
its branch, `app.py`, and Python 3.12; the packaged requirements file supplies
Streamlit 1.65.0 and Pydantic. Leave Secrets empty. After deployment, repeat the
six evaluator checks and record the actual URL and smoke-test results.

Repository upload, account sign-in and publication have not been performed in
this session. No public URL is claimed. Official references:
[Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[Secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management),
[pinned Streamlit release](https://pypi.org/project/streamlit/1.65.0/).

## n8n integration

The owner's original workflow and historical sheet rows are preserved. It
normalizes/truncates body text, tags with Groq and stores no original text.
`/webhook/photo-discovery` is therefore refused by the new collection bridge.
It must not be triggered as if it were bounded collection-only behavior.

Import `n8n/discovery-original-posts-v1.json` into n8n Cloud as a separate
workflow. Configure the webhook's Header Auth credential with header
`X-Api-Key`. Publish it only after checking source access and inspecting the
workflow's bounds. Its dedicated production route is
`/webhook/discovery-original-posts-v1`. Set `N8N_COLLECTION_WEBHOOK_URL` and
`N8N_WEBHOOK_KEY` in local `.env`; never paste the key into chat or public Cloud.

This variant makes no model calls or spreadsheet writes. It accepts at most
20 direct thread URLs and at most 20 source-page fetches, disables HTTP retries
and redirects, and extracts only a plain original-post string from structured
`QAPage.mainEntity.text`. Missing/HTML-only/unsupported structured text fails
closed rather than importing body boilerplate or a summary. Replies are not
fetched and completeness stays false. Current page compatibility and n8n Cloud
execution are not verified; offline JavaScript fixtures do not prove them.

Begin with one actual thread and one fetch after the new endpoint is connected.
See `docs/n8n_import_mapping.md` for tested CLI modes and batch commands.
Preserve sampling failures, access blocks and partial responses; do not bypass
CAPTCHAs, alter request bounds or silently fall back to the tagging workflow.
