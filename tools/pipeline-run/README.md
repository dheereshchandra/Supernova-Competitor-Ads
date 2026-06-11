# pipeline-run — durable, self-healing daily Facebook pipeline

Runs the full Facebook pipeline (scrape → download → R2 → free analysis → enrichment;
**Creative Studio excluded**) for a list of competitors, under **macOS launchd** so it
**survives the controlling session/account being killed**, **auto-resumes** from where
it stopped, and is **observable** at any time.

This exists because running the pipeline as a Claude-session background task means it
dies on a session/account switch — and you don't find out. launchd is detached from any
session, and every pipeline stage is already idempotent, so a relaunch just resumes.

## Files
- `run_batch.sh` — the runner (caffeinate-wrapped, PID-locked, heartbeat every 20s).
  Loops `competitors.txt`, runs `analysis/scripts/run_pipeline.sh --competitor <slug>
  --through-stage 5` for each. Exits 0 only when everything is settled.
- `state.py` — JSON run-state + heartbeat + progress fingerprint at
  `analysis/state/pipeline-run.json` (gitignored). Used by the runner and `status.sh`.
- `status.sh` — read-only dashboard: per-competitor stage, heartbeat/stall, launchd
  state, live counts. Last line `OVERALL: done|running|stalled|dead|empty`.
- `competitors.txt` — the daily list (one slug per line).
- `install.sh` / `uninstall.sh` / `*.plist.template` — the LaunchAgent.

## Install (daily production)
Run ONCE from your **main clone** (not a Conductor worktree — single writer):
```
zsh tools/pipeline-run/install.sh
```
Installs `live.gosupernova.pipeline-run`: runs **daily at 12:15 PM** and **auto-resumes
on crash** (`KeepAlive{SuccessfulExit:false}`). Change the time in the plist template +
re-run install. Remove with `uninstall.sh`.

## Run now / resume (any time, detached — survives the session dying)
```
launchctl kickstart -k gui/$(id -u)/live.gosupernova.pipeline-run
```

## Check progress (any time)
```
bash tools/pipeline-run/status.sh                 # dashboard
tail -f analysis/logs/pipeline-run-$(date +%F).log   # live log
bash analysis/scripts/watch_pipeline.sh <slug>    # live file-count watch
```

## How durability works
| Failure | What happens |
|---|---|
| Session / account switch kills it | It's a launchd child, not a session child → **keeps running** |
| Process crashes / is killed | Exits non-zero → launchd **relaunches** (throttled) → **resumes** (idempotent) |
| A stage hangs | Heartbeat fingerprint stops changing → `status.sh`/notify flags **STALLED** |
| A competitor hard-fails | Retried up to `MAX_ATTEMPTS` (state.py), then marked failed + notified; batch continues |
| Mac tries to idle-sleep | `caffeinate -i` holds it awake for the run |
| Done | Exits 0 → launchd leaves it stopped until the next scheduled run |

macOS notifications fire on each competitor finishing, batch completion, and failures.

## Ad-hoc (no launchd)
You can also run it directly (still caffeinate-wrapped + locked, but tied to your shell):
```
zsh tools/pipeline-run/run_batch.sh                 # competitors.txt
zsh tools/pipeline-run/run_batch.sh speakx zinglish # specific slugs
```
For true session-independence use the `launchctl kickstart` path above.

## Relationship to capture-sync
`tools/capture-sync` also runs `run_pipeline.sh --through-stage 5`, but only for
already-present *fresh manual snapshots* and does not scrape. This job is the active
**Facebook driver** (it auto-scrapes via the V2 terminal scraper); capture-sync is left
to cover Google / any manually-dropped snapshots. Don't point both at the same FB
competitors on the same schedule.
