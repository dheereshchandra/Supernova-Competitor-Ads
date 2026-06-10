# Daily 11:30 AM repo auto-sync

Keeps your **canonical clone** of this repo up to date automatically, so a teammate's
pushes appear every morning without you remembering to `git pull`. (We work one
competitor per person on a shared repo, so staying in sync matters.)

It is a macOS **launchd** job that, every day at **11:30 AM local**, runs
`git fetch` + `git pull --ff-only` on `main`.

## Safety — what it will and won't do

- ✅ **Pull-only.** It only ever *fast-forwards* `main` when your clone is clean and
  strictly behind origin.
- 🚫 **Never pushes, never hard-resets, never force-merges.** Your work is never touched.
- ⏭️ If `main` has uncommitted changes, has unpushed commits, has diverged, or isn't the
  checked-out branch, it **skips** and posts a macOS notification telling you to open
  Conductor and ask Claude to resolve. It logs the exact reason.

## Install (one time, ~10 seconds)

Run from your **main clone** of the repo — **not** a Conductor worktree:

```bash
zsh tools/daily-sync/install.sh
```

That generates `~/Library/LaunchAgents/live.gosupernova.repo-sync.plist` (with the correct
absolute paths for your machine) and loads it. Re-running is safe.

## Verify it works

```bash
launchctl kickstart -k gui/$(id -u)/live.gosupernova.repo-sync && sleep 2 \
  && tail -n 5 "$HOME/Library/Application Support/SupernovaRepoSync/sync.log"
```

You should see an `OK ...` line (e.g. `OK already up to date` or `OK fast-forwarded main`).

## Files

| File | What it is |
|------|-----------|
| `sync.sh` | the pull-only sync logic (finds its own repo root; logs + notifies) |
| `live.gosupernova.repo-sync.plist.template` | launchd schedule template (paths filled in by the installer) |
| `install.sh` | generates the plist with real paths and loads the job |
| `uninstall.sh` | unloads and removes the job |

- **Log:** `~/Library/Application Support/SupernovaRepoSync/sync.log`
- **Change the time:** edit `Hour`/`Minute` in `live.gosupernova.repo-sync.plist.template`, then re-run `install.sh`.
- **Remove:** `zsh tools/daily-sync/uninstall.sh`

> Note: install this on the **canonical clone** you keep long-term. Conductor workspaces
> are git worktrees that share that clone's object store, so a fetch there updates
> `origin/*` for all of them.
