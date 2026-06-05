#!/usr/bin/env python3
"""
Rate-limit guardrail + run ledger for the Google Ads scraper.

WHY THIS EXISTS
---------------
Google's Ads Transparency Center anti-abuse blocks an IP that scrapes too
often. Empirically (see HANDOVER "Rate-limit operating policy"):
  * ONE full sweep from a rested IP is fine (~600 creatives, ~37 min, 0 errors).
  * A SECOND heavy sweep within ~4-5 h poisons the IP.
  * A poisoned IP then stays blocked for MORE THAN A DAY.
So the binding limit is *how often you run*, not requests-per-minute.

This module enforces a cadence policy BEFORE any scrape touches the network,
and records every run to a ledger so the policy survives across sessions — no
human or AI assistant has to "remember" when the last run was; it is on disk.

POLICY (defaults — tune the constants below to loosen/tighten)
--------------------------------------------------------------
  * At most MAX_COMPETITORS_PER_RUN competitor(s) per run.
  * At least MIN_GAP_HOURS between runs.
  * After a 429 block, POST_BLOCK_COOLDOWN_HOURS before anything runs.
  * A violation can only be overridden by OVERRIDE_CONFIRMATIONS explicit
    "yes" answers (interactive terminal) or the --force flag (non-interactive).

LEDGER
------
  logs/scrape_history.jsonl   (one JSON object per run, appended)

CLI
---
  python3 scripts/scrape_guardrail.py status                 # last run + whether a run is allowed now
  python3 scripts/scrape_guardrail.py check --competitors 1  # exit 0 if allowed, 3 if not
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# POLICY CONSTANTS  —  tune these to loosen/tighten the cadence
# ---------------------------------------------------------------------------
MAX_COMPETITORS_PER_RUN = 1       # ads from at most N competitors per run
MIN_GAP_HOURS = 24.0             # required rest gap between successful runs
POST_BLOCK_COOLDOWN_HOURS = 24.0  # forced cooldown after a 429 block
OVERRIDE_CONFIRMATIONS = 2        # explicit "yes" answers needed to override

# Request pacing (read by scrape_google_ads.py). Per-run rate was never the
# thing that got the IP blocked (frequency was), but jitter + a slightly
# slower cadence is cheap insurance as ad counts grow.
SEARCH_PAGE_DELAY_SECONDS = 1.0   # base delay between listing pages
SEARCH_PAGE_JITTER = 0.75         # + random 0..this
DETAIL_DELAY_SECONDS = 0.15       # base delay between per-creative detail calls
DETAIL_JITTER = 0.25              # + random 0..this

LEDGER_RELPATH = os.path.join("logs", "scrape_history.jsonl")


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def _now() -> datetime.datetime:
    return datetime.datetime.now()


def ledger_path(base_dir) -> pathlib.Path:
    return pathlib.Path(base_dir) / LEDGER_RELPATH


def _parse_ts(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def read_runs(base_dir) -> list:
    """All run records, oldest→newest (best effort; skips corrupt lines)."""
    p = ledger_path(base_dir)
    if not p.exists():
        return []
    runs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    runs.sort(key=lambda r: r.get("ts_start") or "")
    return runs


def most_recent_run(base_dir) -> Optional[dict]:
    runs = read_runs(base_dir)
    return runs[-1] if runs else None


def record_run(base_dir, *, competitor, advertisers=None, region=None,
               outcome, creatives=0, rows=0, note="",
               ts_start=None, ts_end=None) -> dict:
    """Append a run record. outcome in {success, partial, blocked}."""
    p = ledger_path(base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts_start": ts_start or _now().isoformat(timespec="seconds"),
        "ts_end": ts_end or _now().isoformat(timespec="seconds"),
        "competitor": competitor,
        "advertisers": list(advertisers or []),
        "region": region or "",
        "outcome": outcome,
        "creatives": creatives,
        "rows": rows,
        "note": note,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


# ---------------------------------------------------------------------------
# Policy check + enforcement
# ---------------------------------------------------------------------------
def check_policy(base_dir, competitor_count: int, now=None):
    """Return (allowed: bool, reasons: list[str], next_allowed: datetime|None).

    competitor_count is approximated by the number of advertisers in the run
    (the built-in map has one advertiser per competitor).
    """
    now = now or _now()
    reasons: list = []
    next_allowed = None

    if competitor_count > MAX_COMPETITORS_PER_RUN:
        reasons.append(
            f"This run targets {competitor_count} competitors, but policy allows "
            f"at most {MAX_COMPETITORS_PER_RUN} per run — scrape one at a time.")

    last = most_recent_run(base_dir)
    if last:
        last_ts = _parse_ts(last.get("ts_end") or last.get("ts_start"))
        if last_ts:
            blocked = (last.get("outcome") == "blocked")
            required_h = POST_BLOCK_COOLDOWN_HOURS if blocked else MIN_GAP_HOURS
            elapsed_h = (now - last_ts).total_seconds() / 3600.0
            if elapsed_h < required_h:
                next_allowed = last_ts + datetime.timedelta(hours=required_h)
                what = "a 429 BLOCK" if blocked else "the last run"
                gap_desc = ("a block and the next run" if blocked else "runs")
                reasons.append(
                    f"{what} was {elapsed_h:.1f}h ago "
                    f"(competitor={last.get('competitor', '?')}, "
                    f"outcome={last.get('outcome')}). Policy requires "
                    f"{required_h:.0f}h between {gap_desc}. "
                    f"Next allowed: {next_allowed.strftime('%a %d %b %Y %H:%M')}.")

    return (not reasons), reasons, next_allowed


def enforce(base_dir, competitor_count: int, *, force=False,
            no_guardrail=False, input_fn=input, now=None) -> bool:
    """Gate a scrape. Returns True if it may proceed, False if it must not."""
    if no_guardrail:
        print("[guardrail] DISABLED via --no-guardrail (escape hatch).")
        return True

    allowed, reasons, _ = check_policy(base_dir, competitor_count, now=now)
    if allowed:
        print("[guardrail] OK — within the rate-limit operating policy.")
        return True

    print("\n" + "=" * 66)
    print("RATE-LIMIT GUARDRAIL — this run VIOLATES the operating policy:")
    for r in reasons:
        print(f"   - {r}")
    print("=" * 66)
    print("Running anyway risks getting the IP block-listed for 24h+.")

    if force:
        print("[guardrail] --force supplied -> overriding without prompts.")
        return True

    if not getattr(sys.stdin, "isatty", lambda: False)():
        print("[guardrail] Non-interactive shell and no --force -> REFUSING.")
        print("            Re-run with --force only if you accept the risk.")
        return False

    for i in range(1, OVERRIDE_CONFIRMATIONS + 1):
        ans = input_fn(
            f"   Override {i}/{OVERRIDE_CONFIRMATIONS} — type 'yes' to proceed "
            "(anything else aborts): ").strip().lower()
        if ans not in ("yes", "y"):
            print("[guardrail] Aborted — no scrape was run.")
            return False
    print("[guardrail] Override confirmed -> proceeding against policy.")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli() -> int:
    ap = argparse.ArgumentParser(
        description="Google scraper rate-limit guardrail / run ledger")
    sub = ap.add_subparsers(dest="cmd")

    ps = sub.add_parser("status",
                        help="Show the last run and whether a scrape is allowed now")
    ps.add_argument("--base", default=".", help="Project root (default: cwd)")

    pc = sub.add_parser("check",
                        help="Exit 0 if a run is allowed now, 3 if not")
    pc.add_argument("--base", default=".")
    pc.add_argument("--competitors", type=int, default=1)

    args = ap.parse_args()

    if args.cmd == "status":
        print(f"Ledger: {ledger_path(args.base)}")
        print(f"Policy: <= {MAX_COMPETITORS_PER_RUN} competitor/run, "
              f">= {MIN_GAP_HOURS:.0f}h between runs, "
              f"{POST_BLOCK_COOLDOWN_HOURS:.0f}h cooldown after a block.")
        last = most_recent_run(args.base)
        if not last:
            print("No runs recorded yet — a scrape is allowed.")
            return 0
        print("Most recent run:")
        for k in ("ts_start", "ts_end", "competitor", "region",
                  "outcome", "creatives", "rows", "note"):
            if k in last:
                print(f"  {k:11}: {last[k]}")
        allowed, reasons, _ = check_policy(args.base, competitor_count=1)
        print()
        if allowed:
            print("ALLOWED — a scrape (1 competitor) is within policy right now.")
        else:
            print("BLOCKED — a scrape is NOT allowed right now:")
            for r in reasons:
                print(f"   - {r}")
        return 0

    if args.cmd == "check":
        allowed, reasons, _ = check_policy(
            args.base, competitor_count=args.competitors)
        if allowed:
            print("ALLOWED")
            return 0
        print("BLOCKED")
        for r in reasons:
            print(f"  - {r}")
        return 3

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
