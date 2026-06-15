# Ad Studio watchdog + uptime safeguards

Keeps the team's Ad Studio public URL (`https://dheeresh.tail92accf.ts.net`) reachable,
and pages you the moment it isn't. Built after the 2026-06-15 outage where a transient
LAN-IP change on the host Mac left the Tailscale Funnel's public ingress **stale** —
remote users got `ERR_CONNECTION_CLOSED` while the operator (on localhost/tailnet) saw a
perfectly healthy app. The app/backend were never the problem; the **public doorway** was.

Three layers, defence-in-depth:

| Layer | What it catches | Where it runs |
|-------|-----------------|---------------|
| **Local watchdog** | backend down, tailscaled offline, Funnel config dropped, **stale Funnel after an IP flap** — auto-heals + alerts | this Mac (launchd, every 60s + on network change) |
| **External monitor** | a TOTAL public outage (Funnel edge stale / host unreachable) — the only off-tailnet vantage | GitHub Actions (every ~5 min) |
| **Cold-boot hardening** | the Mac slept / lost power / rebooted | one-time host settings |

---

## Tier 1a — Local watchdog (`watchdog.sh`)

Every 60 seconds (and immediately on any DNS/network change) it checks three local truths
and auto-heals:

1. **Backend** `127.0.0.1:8787/api/health` responds → else `launchctl kickstart` the
   `live.gosupernova.ad-studio` job.
2. **Tailscale** `BackendState=Running` and `Self.Online=true` (`tailscale status --json`).
3. **Funnel** still proxies `:8787` (`tailscale funnel status`) → else re-assert.
4. **LAN IP changed since last run?** This is the exact trigger that wedges the public
   ingress, so it proactively runs the documented repair
   `tailscale serve reset && tailscale funnel --bg 8787`.

Heals are capped at **4/hour** (a wedged edge can't loop forever); on a clean self-heal it
posts an `Ad Studio auto-recovered` note, and if it can't fix things it posts
`Ad Studio DEGRADED`. All alerts go through the shared `tools/notify/notify.sh`
(macOS banner + Slack when `SLACK_WEBHOOK_URL` is in `.env`). Healthy runs are silent
(logged only).

```sh
# install (run on the canonical clone — the same Mac that serves Ad Studio)
zsh tools/ad-studio-watchdog/install.sh

# verify (forces one run)
launchctl kickstart -k gui/$(id -u)/live.gosupernova.ad-studio-watchdog \
  && sleep 4 && tail -n 8 "$HOME/Library/Application Support/SupernovaAdStudioWatchdog/watchdog.log"
# expect:  ... OK backend+tailscale+funnel healthy (ip=192.168.x.x)

# remove
zsh tools/ad-studio-watchdog/uninstall.sh
```

Log: `~/Library/Application Support/SupernovaAdStudioWatchdog/watchdog.log`.
Safe alongside the daily sync jobs — it only touches Tailscale and the backend, never git
or repo data, so it doesn't interfere with the 11:30 sync chain or its blackout window.

> **Why a local check can't be the whole story:** from this Mac, MagicDNS resolves
> `*.ts.net` to the **tailnet** IP, so a local `curl` of the public URL bypasses the public
> edge and always passes — even when remote users are dead. That blind spot is exactly the
> 2026-06-15 failure, and it's why Tier 1b exists.

## Tier 1b — External monitor (`.github/workflows/ad-studio-uptime.yml`)

A GitHub Actions cron (every ~5 min) curls the **public** `/api/health` from off-tailnet
and Slack-alerts on a 2-strike failure. One-time setup:

```sh
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/services/..."   # same webhook as .env
```

Then trigger a test run from the **Actions** tab (`Run workflow`).

Limits to know: GitHub cron is best-effort (can lag), and runners are **IPv4-only**. So this
catches a *total* public outage but **not** a carrier-IPv6-only failure (see below). For
1-minute checks + confirmation counts + an IPv6 probe, add a free **UptimeRobot** or
**BetterStack** HTTP monitor on the same URL (keyword `"ok":true`) → Slack. Recommended in
addition to, not instead of, the Action.

## Tier 2 — Cold-boot / power hardening (`harden-host.sh`)

The watchdog only helps once the Mac is up. This covers sleep / power-loss / reboot.

```sh
zsh tools/ad-studio-watchdog/harden-host.sh            # report current posture
zsh tools/ad-studio-watchdog/harden-host.sh --apply    # set safe power tweaks (sudo)
```

**FileVault is the gate.** This Mac has FileVault **on**, so after a full power-off nothing
runs until someone enters the unlock password at the pre-boot screen. Decide:
- **Keep FileVault** (most secure): UPS + avoid shutdowns + accept one manual login per cold
  boot. After login, backend (KeepAlive), Funnel (`--bg` auto-resume) and the watchdog all
  return on their own.
- **Unattended recovery**: disable FileVault on this dedicated box + enable autologin +
  `--apply` (sets `autorestart 1`). A power cut then auto-reboots back to serving.
  Tradeoff: disk (incl. `.env` secrets) no longer encrypted at rest.

Belt-and-suspenders: `sudo tailscaled install-system-daemon` (so the Funnel survives without
the GUI app session) and confirm "Launch Tailscale at login" is on.

---

## Known limitation → Tier 3 (the real cure)

The Funnel publishes both an IPv4 (A) and IPv6 (AAAA) record and there is **no knob to
suppress the AAAA**. Indian mobile carriers (esp. Jio 5G — IPv6-first) are documented to
drop IPv6 connections to dual-stack hosts with this same `ERR_CONNECTION_CLOSED` symptom,
while IPv4 works. None of the layers above can fix a broken client-side IPv6 path.

The durable fix that removes both the single-Mac SPOF **and** the IPv6 problem is to front
the app with a **Cloudflare Tunnel** (you control DNS → can serve IPv4-friendly, plus custom
domain/WAF) or lift it to a small **cloud Linux VM** (stable IP, native IPv6, no login
gating). See `webapp/install/README.md` §3 (legacy cloudflared note) and §7 (cloud lift).
