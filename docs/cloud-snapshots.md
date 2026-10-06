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

Automatic publication is enabled in `config/cloud_publication.json` for this
repository's existing GitHub `origin` and `main` branch. The already registered
`scripts/run_scheduled_discovery.cmd` runs the publication script after the
research command returns successfully, including partial batches. No Windows
task registrations or collection/model budgets were changed.

The publisher fetches the latest remote branch into a temporary sparse Git
checkout that contains only the public snapshot directory. It validates and
commits the two current snapshots there, then performs one ordinary push. It
never stages or commits in the user's working checkout. Unrelated uncommitted
or staged work, credentials, private runs and frozen evaluation data are excluded.
Unchanged snapshots produce no commit. Newer remote results and changed remote
reference versions are preserved. Push rejection, including a concurrent remote
edit, is recorded without a force push, repair call or retry.

Publication status is saved atomically to the gitignored
`data/interim/cloud-publication/CURRENT.json` and printed in command output.
A publication failure does not alter the completed research command's exit code,
rerun collection, or replace the deployed usable snapshot. A later scheduled
invocation tries again with the then-current public results. Existing cached Git
credentials are used with interactive prompts disabled; Streamlit needs no GitHub
or Groq credential for this. The computer must be awake and the scheduled user
logged in, with working network/GitHub access.

To disable automatic publication, set `enabled` to `false` in the local
publication configuration. For publication without a research run, use
`.\.venv\Scripts\python.exe scripts\publish_cloud_snapshots.py`. The offline
packaging script remains available for manual deployment copies. A direct
`main.py schedule` invocation bypasses the Windows command's follow-up step.

Streamlit Cloud updates after GitHub receives the snapshot commit; an app rebuild
may take time. Refresh reloads the deployed version rather than reaching into the
owner's computer. Automatic commits advance remote `main` without changing local
HEAD; fetch and integrate remote changes before a later development push.

The curated Cloud package builder includes both current snapshots and the reader
module. Private data and the local scheduler directories remain excluded.

Initial copies: scheduled run `ce6e008cebf6`, completed October 6, 2026 at
15:19 IST (0 new documents, shortfall 50); comparison `f266fffd119f24fc`
(48 human-reviewed reference records, 5 eligible automated cases, 2 flagged,
9 failed/incomplete). The two snapshots describe different saved inputs; their
counts are not combined.
