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
`scripts/run_scheduled_discovery.cmd` runs `scripts/run_queued_discovery.py`,
which runs publication after the research command returns successfully,
including partial batches. Collection/model budgets are unchanged.

The three existing Windows tasks retain their 08:00, 14:00 and 20:00 IST
triggers and interactive user. Catch-up (`StartWhenAvailable`) is enabled,
network availability is required, and multiple instances use `Queue`.
Windows can start missed work when the computer is awake, the owner has signed
in and a network is available; catch-up normally has a Windows scheduling delay
(the documented default is ten minutes). This is Windows catch-up, not a promise
to replay every historical occurrence after several days offline.

A shared Windows named mutex serializes all three tasks through both research
and publication, including simultaneous catch-up starts. Waiting does not
collect data or call models. Windows releases ownership if a worker exits or
is terminated. Current-day request reservations, limits and duplicate skipping
still apply. No workflow or integration is invoked by the queue itself. A
publication failure is attempted again at a later successful scheduled run,
without repeating the completed research command inside the same invocation.
Original task XML and settings verification are saved locally under the ignored
`data/interim/task-settings-backup/` directory when these settings are applied.

Microsoft describes the catch-up setting and delay at
https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable.

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
