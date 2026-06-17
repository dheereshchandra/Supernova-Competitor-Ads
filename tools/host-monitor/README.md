# Host-presence monitor (laptop UP / DOWN alerts)

Sends the team **one Slack alert when the host Mac comes up** and **one when it goes
down** — so a shutdown/restart isn't a silent mystery. This is the machine-level twin of
the [Ad Studio watchdog](../ad-studio-watchdog/README.md): the watchdog guards the public
*door* (the Tailscale Funnel); this guards the *machine* everything runs on.

| Event | Alert | Reliable? |
|-------|-------|-----------|
| Boot / login | `🟢 Host Mac is UP` | **yes** — every genuine boot |
| **Logout** | `🔴 Host Mac going DOWN` | yes (network still up when the SIGTERM trap runs) |
| **Restart / shutdown** | `🔴 Host Mac going DOWN` | **best-effort** — macOS severs the network as it stops agents, so the Slack POST often loses the race. A missing DOWN here is expected. |
| **Hard** power-loss / panic / battery death | — (can't warn) | **no** — no SIGTERM is sent |

For the restart/shutdown best-effort case **and** the hard cases, the real backstop is the
**off-host** monitors — the [GitHub uptime workflow](../../.github/workflows/ad-studio-uptime.yml)
and the [Ad Studio watchdog](../ad-studio-watchdog/README.md) — not this script. This monitor's
job is the clean, common signal (and a reliable UP on the way back), not to be the only net.

## How it works

`presence.sh` runs as a long-lived launchd LaunchAgent (`KeepAlive`). Both alerts are
**edge-triggered** off a persisted state file (`presence_state`) so administrative churn
can't fake them:

- **UP** — `RunAtLoad` starts it at every boot/login. It waits briefly for the network,
  then posts `🟢 Host Mac is UP` — but **only on a genuine come-back**: either the last
  recorded state was `down` (a graceful shutdown that's now over) or the system uptime is
  small (a hard power-loss leaves no `down` marker). A mid-session `KeepAlive` crash-restart
  (host never went down) is logged but sends **no** UP.
- **DOWN** — at a graceful logout/restart/shutdown, launchd sends `SIGTERM`. A trap catches
  it, records `down`, posts `🔴 Host Mac going DOWN`, and exits. `KeepAlive/SuccessfulExit=false`
  means that clean exit is **not** restarted (no UP/DOWN loop); the next boot re-arms it.
- **Reinstall / uninstall is silent** — `install.sh`/`uninstall.sh` drop an `admin_stop`
  sentinel around the `launchctl bootout`, so stopping the old instance does **not** fire a
  false DOWN, and the new instance does **not** fire a false UP.

All alerts go through the shared `tools/notify/notify.sh` (macOS banner + Slack when
`SLACK_WEBHOOK_URL` is in `.env`).

## Install / verify / remove

```sh
# install (run on the host Mac — the canonical clone that serves Ad Studio)
zsh tools/host-monitor/install.sh
# it fires a '🟢 Host Mac is UP' immediately; check the log:
sleep 3 && tail -n 6 "$HOME/Library/Application Support/SupernovaHostMonitor/host-monitor.log"

# test the DOWN alert (sends '🔴 ... going DOWN', then stops the agent)…
launchctl kill TERM gui/$(id -u)/live.gosupernova.host-monitor
# …then bring it back (re-arms UP/DOWN):
launchctl kickstart -k gui/$(id -u)/live.gosupernova.host-monitor

# remove
zsh tools/host-monitor/uninstall.sh
```

Log: `~/Library/Application Support/SupernovaHostMonitor/host-monitor.log`.

It only reads/sends notifications — it never touches git, the repo, Tailscale, or the
backend — so it's safe alongside the watchdog and the daily sync jobs.
