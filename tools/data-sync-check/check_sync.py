#!/usr/bin/env python3.13
"""Daily data-consistency check — the three places the team sees data must agree:

  1. the Mac        (canonical clone working tree + the Ad Studio backend)
  2. the repo       (origin/main on GitHub)
  3. the Google Sheet ("Supernova Competitor Master": Overview / Analysis /
                       Production Tracker tabs)

Checks (ALL read-only — never pulls, pushes, or writes a cell):
  [1/4] git: canonical clone on main, clean, neither ahead nor behind origin
  [2/4] app: Ad Studio backend up and serving a clean, pushed clone
  [3/4] sheet views: Overview + Analysis row keys == what sync_to_sheets.py
        would build from the local CSVs right now (same builder code, so the
        comparison can't drift from the real sync)
  [4/4] tracker: Production Tracker tab rows == the app's SQLite tracker

Exit codes: 0 = consistent · 1 = mismatches found · 2 = could not verify
(a source unreachable / check crashed). The check.sh wrapper notifies on 1 & 2.

Manual run (any clone, against the canonical repo):
  python3.13 tools/data-sync-check/check_sync.py [--repo /path/to/canonical]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import subprocess
import sys
import traceback
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parents[1]

mismatches: list[str] = []
errors: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK        {msg}")


def bad(msg: str) -> None:
    mismatches.append(msg)
    print(f"  MISMATCH  {msg}")


def warn(msg: str) -> None:
    print(f"  warn      {msg}")


def err(msg: str) -> None:
    errors.append(msg)
    print(f"  ERROR     {msg}")


def sample(keys, n: int = 5) -> str:
    s = sorted("/".join(k) for k in keys)
    extra = f" (+{len(s) - n} more)" if len(s) > n else ""
    return ", ".join(s[:n]) + extra


# ---- [1/4] Mac ↔ repo --------------------------------------------------------

def check_git(repo: pathlib.Path) -> None:
    print("[1/4] Mac ↔ repo (git)")

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                              text=True, timeout=120)

    branch = git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if branch != "main":
        bad(f"canonical clone is on '{branch or 'DETACHED'}', not main")
        return
    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        bad(f"working tree has {len(dirty.splitlines())} uncommitted change(s) — "
            "the Mac/app shows data the repo doesn't have")
    if git("fetch", "-q", "origin").returncode != 0:
        warn("git fetch failed (offline?) — comparing against last-known origin/main")
    ahead = git("rev-list", "--count", "origin/main..HEAD").stdout.strip() or "?"
    behind = git("rev-list", "--count", "HEAD..origin/main").stdout.strip() or "?"
    if ahead != "0":
        bad(f"local main is {ahead} commit(s) AHEAD of origin — unpushed data "
            "teammates can't see")
    if behind != "0":
        bad(f"local main is {behind} commit(s) BEHIND origin — the Mac/app is "
            "stale vs the repo")
    if not dirty and ahead == "0" and behind == "0":
        ok("clean + exactly in sync with origin/main")


# ---- [2/4] app ↔ Mac ---------------------------------------------------------

def check_app() -> None:
    print("[2/4] Ad Studio app ↔ Mac")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/health",
                                    timeout=15) as r:
            h = json.load(r)
    except Exception as e:
        bad(f"Ad Studio backend unreachable on :8787 ({e}) — the app is down")
        return
    if not h.get("ok"):
        bad("backend /api/health reports not-ok")
        return
    git = h.get("git") or {}
    clean = True
    if git.get("dirty"):
        bad("the clone the app serves from has uncommitted changes")
        clean = False
    if git.get("unpushed"):
        bad(f"the clone the app serves from has {git['unpushed']} unpushed commit(s)")
        clean = False
    if clean:
        ok(f"backend up — {h.get('competitors')} competitors, "
           f"data as of {h.get('data_as_of')}, serving a clean pushed clone")


# ---- [3/4] repo CSVs ↔ Sheet (Overview / Analysis) ---------------------------

def _sheet_keys(rows: list, key_cols, tab: str):
    if not rows:
        return None, f"{tab} tab is empty"
    header = [str(c).strip() for c in rows[0]]
    try:
        pos = [header.index(k) for k in key_cols]
    except ValueError as e:
        return None, f"{tab} header is missing a key column ({e})"
    keys = set()
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue
        keys.add(tuple(str(row[p]).strip() if len(row) > p else "" for p in pos))
    return keys, None


def check_sheet_views(repo: pathlib.Path) -> None:
    print("[3/4] repo CSVs ↔ Google Sheet (Overview & Analysis)")
    sys.path.insert(0, str(repo / "tools" / "csv-sync"))
    import _gsheets
    import sync_to_sheets as sts

    sidecar = repo / "tools" / "csv-sync" / "sheet_id.json"
    if not sidecar.exists():
        err("tools/csv-sync/sheet_id.json missing — can't locate the Sheet")
        return
    ssid = json.loads(sidecar.read_text())["spreadsheet_id"]
    env = sts.load_env(repo / ".env")
    _drive, sheets = _gsheets.build_services(env)

    # expected = the EXACT rows csv-sync would write right now
    expected = {"Overview": set(), "Analysis": set()}
    for pipeline in sts.PIPELINES:
        for comp in sts.discover_competitors(pipeline):
            ov, an = sts.build_views(pipeline, comp)
            for tab, rows in (("Overview", ov), ("Analysis", an)):
                for row in rows:
                    expected[tab].add(tuple(
                        str(row.get(k, "")).strip() for k in sts.KEY_COLS))

    for tab in ("Overview", "Analysis"):
        got = _gsheets.read_tab_values(sheets, ssid, tab)
        keys, problem = _sheet_keys(got, sts.KEY_COLS, tab)
        if keys is None:
            err(problem)
            continue
        missing = expected[tab] - keys   # in local CSVs, not in the Sheet
        extra = keys - expected[tab]     # in the Sheet, no longer in the CSVs
        if missing:
            bad(f"{tab}: {len(missing)} ad(s) in the repo CSVs but NOT in the "
                f"Sheet — e.g. {sample(missing)}")
        if extra:
            bad(f"{tab}: {len(extra)} row(s) in the Sheet with no matching ad "
                f"in the repo CSVs — e.g. {sample(extra)}")
        if not missing and not extra:
            ok(f"{tab}: all {len(keys):,} ads match the repo CSVs exactly")


# ---- [4/4] app tracker ↔ Sheet (Production Tracker) --------------------------

def _norm_status(s: str) -> str:
    return (s or "").strip().lower().replace("…", "").replace(" ", "_")


def check_tracker(repo: pathlib.Path) -> None:
    print("[4/4] app tracker (SQLite) ↔ Sheet 'Production Tracker'")
    db_path = repo / "webapp" / "state" / "studio.db"
    if not db_path.exists():
        warn("no webapp/state/studio.db — Ad Studio not installed here; skipping")
        return
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        local = {(c, p, a): _norm_status(s) for c, p, a, s in con.execute(
            "SELECT competitor, pipeline, ad_id, status FROM tracker")}
    finally:
        con.close()

    sys.path.insert(0, str(repo / "tools" / "csv-sync"))
    import _gsheets
    import sync_to_sheets as sts
    ssid = json.loads(
        (repo / "tools" / "csv-sync" / "sheet_id.json").read_text())["spreadsheet_id"]
    env = sts.load_env(repo / ".env")
    _drive, sheets = _gsheets.build_services(env)
    rows = _gsheets.read_tab_values(sheets, ssid, "Production Tracker")
    if not rows:
        if local:
            bad(f"Production Tracker tab is empty but the app has {len(local)} "
                "tracked ad(s)")
        else:
            ok("no tracked ads anywhere (both empty)")
        return
    header = [str(c).strip() for c in rows[0]]
    try:
        pc, pp, pa, ps = (header.index(k) for k in
                          ("Competitor", "Platform", "Ad ID", "Status"))
    except ValueError as e:
        err(f"Production Tracker header missing a key column ({e})")
        return
    remote: dict[tuple, str] = {}
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue
        key = tuple(str(row[i]).strip() if len(row) > i else "" for i in (pc, pp, pa))
        remote[key] = _norm_status(row[ps] if len(row) > ps else "")

    missing = set(local) - set(remote)
    extra = set(remote) - set(local)
    if missing:
        bad(f"tracker: {len(missing)} ad(s) tracked in the app but missing from "
            f"the Sheet — e.g. {sample(missing)}")
    if extra:
        bad(f"tracker: {len(extra)} row(s) in the Sheet with no app tracker row "
            f"(orphans) — e.g. {sample(extra)}")
    drift = [k for k in set(local) & set(remote) if local[k] != remote[k]]
    if drift:
        # statuses re-sync on the next tracker write; drift = sync isn't running
        bad(f"tracker: {len(drift)} ad(s) show a DIFFERENT status in the Sheet "
            f"vs the app — e.g. {sample(drift)}")
    if not missing and not extra and not drift:
        ok(f"all {len(local)} tracked ads match the Sheet (keys + status)")


# ---- main --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=pathlib.Path, default=DEFAULT_REPO,
                    help="canonical clone to check (default: this script's repo)")
    args = ap.parse_args()
    repo = args.repo.resolve()
    print(f"data-sync check · repo={repo}")

    for name, fn in (("git", lambda: check_git(repo)),
                     ("app", check_app),
                     ("sheet views", lambda: check_sheet_views(repo)),
                     ("tracker", lambda: check_tracker(repo))):
        try:
            fn()
        except Exception:
            err(f"the '{name}' check crashed — see traceback above/below")
            traceback.print_exc()

    if errors and not mismatches:
        print(f"RESULT: COULD NOT VERIFY ({len(errors)} check error(s))")
        return 2
    if mismatches:
        print(f"RESULT: {len(mismatches)} MISMATCH(ES) — "
              + " | ".join(mismatches[:3]))
        return 1
    print("RESULT: CONSISTENT — Mac, repo and Sheet all agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
