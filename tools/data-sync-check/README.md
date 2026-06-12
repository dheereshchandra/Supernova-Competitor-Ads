# data-sync-check — daily "is everything the same everywhere?" watchdog

One read-only check, every day at **12:15**, that the three places the team
sees data all agree:

| Place | What's checked |
|---|---|
| **The Mac** | canonical clone on `main`, clean, neither ahead nor behind `origin/main`; the Ad Studio backend is up and serving a clean, pushed clone |
| **The repo** | (same git comparison, from both sides) |
| **The Google Sheet** | `Overview` + `Analysis` tabs contain exactly the ads the local CSVs produce (it reuses `sync_to_sheets.py`'s own row builder, so the comparison can never drift from the real sync); `Production Tracker` rows match the app's SQLite tracker — keys *and* status |

12:15 is deliberate: it runs right after the 11:30 repo-sync → 11:35
capture-sync → 11:45 csv-sync chain, so it validates the whole morning
pipeline end-to-end.

**Alerting:** silent when everything agrees (the log records the daily OK).
On any mismatch — or if a source can't be reached to verify — it alerts via
`tools/notify/notify.sh` (macOS banner + Slack once `SLACK_WEBHOOK_URL` is set).

## Install (once, from the canonical MAIN clone)

```sh
zsh tools/data-sync-check/install.sh
```

## Run by hand

```sh
python3.13 tools/data-sync-check/check_sync.py            # from the canonical clone
python3.13 tools/data-sync-check/check_sync.py --repo /path/to/canonical   # from anywhere
launchctl kickstart -k gui/$(id -u)/live.gosupernova.sync-check            # force the launchd run
```

Exit codes: `0` consistent · `1` mismatches · `2` could not verify.
Log: `~/Library/Application Support/SupernovaSyncCheck/check.log`.

## What a mismatch means (and the usual fix)

- **dirty / ahead / behind** — a job died mid-commit or a push failed: open
  Conductor and ask Claude to commit/push, or `git pull --ff-only`.
- **Sheet missing ads** — csv-sync hasn't run since new data landed: wait for
  the next run or `launchctl kickstart -k gui/$(id -u)/live.gosupernova.csv-sync`.
- **tracker orphans / status drift** — the app's Sheet mirror missed a write:
  any tracker edit in the app re-syncs the full tab, or restart the backend.

Files: `check_sync.py` (the checks) · `check.sh` (launchd wrapper + alerting) ·
`install.sh` / `uninstall.sh` · `live.gosupernova.sync-check.plist.template`.
