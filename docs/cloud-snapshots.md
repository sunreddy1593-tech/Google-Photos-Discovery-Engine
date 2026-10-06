# Public snapshots in Streamlit Cloud

The scheduler publishes local snapshots into gitignored directories. Streamlit
Cloud receives tracked repository files, so it previously showed both snapshots
as missing even when the local scheduler had published them.

`scripts/prepare_cloud_snapshots.py` reads only the two current public snapshots,
checks both with the existing privacy scan, and packages them under the tracked
`data/exports/public/cloud-snapshots/` directory. It uses the existing versioned
snapshot writer and atomic pointer replacement. Previous versions remain usable
on failure. It never reads private runs, secrets or frozen evaluation text, and
never calls a collector, provider, n8n or Sheets. Repeating it with unchanged
inputs is idempotent. It refuses a changed body under the same current version.

The app prefers a usable local snapshot, falling back to the deployment copy.
Both versions retain their recorded reference/model/prompt/schema provenance.
Cache identities and Refresh buttons are unchanged. Cloud copies have a visible
saved-deployment notice; recorded next-run times are historical schedule data,
not proof that the scheduler is running on Cloud.

To publish later results, run `.\.venv\Scripts\python.exe
scripts\prepare_cloud_snapshots.py` locally, review the public files, then commit
and push the updated deployment copies. Local runs do not upload themselves.
No scheduler task registrations, budgets or integration behavior were changed.

The curated Cloud package builder includes both current snapshots and the reader
module. Private data and the local scheduler directories remain excluded.

Initial copies: scheduled run `ce6e008cebf6`, completed October 6, 2026 at
15:19 IST (0 new documents, shortfall 50); comparison `f266fffd119f24fc`
(48 human-reviewed reference records, 5 eligible automated cases, 2 flagged,
9 failed/incomplete). The two snapshots describe different saved inputs; their
counts are not combined.
