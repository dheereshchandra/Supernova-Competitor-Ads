#!/usr/bin/env python3.13
"""Surgically remove duplicate rows from a Sheet tab, keyed by sync_to_sheets' KEY_COLS
(Competitor, Platform, Ad ID). Keeps the FIRST occurrence of each key, deletes the rest —
preserving every unique row, header, and formatting. Use to clean legacy duplicate cruft
(e.g. the Overview tab) without a destructive --rebuild.

Usage:
  python3.13 tools/csv-sync/dedup_sheet.py [--tab Overview] [--dry-run]
"""
import argparse, pathlib, sys, json

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "csv-sync"))
import _gsheets, sync_to_sheets as sts  # noqa: E402


def load_env():
    env = {}
    for ln in (REPO / ".env").read_text().splitlines():
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1); env[k.strip()] = v.strip()
    return env


def coalesce_desc(indices):
    """[5,4,3,9,8] -> [(8,10),(3,6)] half-open [start,end) ranges, sorted desc by start."""
    idx = sorted(set(indices), reverse=True)
    ranges = []
    for i in idx:
        if ranges and ranges[-1][0] == i + 1:        # contiguous below the current range start
            ranges[-1] = (i, ranges[-1][1])
        else:
            ranges.append((i, i + 1))
    return ranges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default="Overview")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    env = load_env()
    drive, sheets = _gsheets.build_services(env)
    ssid = json.loads((REPO / "tools" / "csv-sync" / "sheet_id.json").read_text())["spreadsheet_id"]
    tabs = _gsheets.get_tabs(sheets, ssid)
    if args.tab not in tabs:
        sys.exit(f"[error] tab '{args.tab}' not found ({list(tabs)})")
    gid = tabs[args.tab]
    rows = _gsheets.read_tab_values(sheets, ssid, args.tab)
    if not rows:
        sys.exit(f"[error] '{args.tab}' is empty")
    header = rows[0]
    try:
        pos = [header.index(k) for k in sts.KEY_COLS]
    except ValueError as e:
        sys.exit(f"[error] key column missing from '{args.tab}' header: {e}")

    seen, dup_row_idx = set(), []           # 0-based sheet row index (row 0 = header)
    for i, r in enumerate(rows[1:], start=1):
        key = tuple(str(r[p]).strip() if len(r) > p else "" for p in pos)
        if key in seen:
            dup_row_idx.append(i)
        else:
            seen.add(key)
    print(f"[dedup] {args.tab}: {len(rows)-1} data rows · {len(seen)} unique keys · {len(dup_row_idx)} duplicate row(s)")
    if not dup_row_idx:
        print("[dedup] nothing to do — no duplicates."); return
    ranges = coalesce_desc(dup_row_idx)
    print(f"[dedup] {'(dry) would delete' if args.dry_run else 'deleting'} {len(dup_row_idx)} rows in {len(ranges)} range(s)")
    if args.dry_run:
        return
    # delete highest ranges first so lower indices stay valid; chunk the requests
    reqs = [{"deleteDimension": {"range": {"sheetId": gid, "dimension": "ROWS",
             "startIndex": s, "endIndex": e}}} for (s, e) in ranges]
    CHUNK = 300
    for i in range(0, len(reqs), CHUNK):
        _gsheets.with_backoff(lambda c=reqs[i:i + CHUNK]: sheets.spreadsheets().batchUpdate(
            spreadsheetId=ssid, body={"requests": c}).execute())
    # verify
    rows2 = _gsheets.read_tab_values(sheets, ssid, args.tab)
    keys2 = [tuple(str(r[p]).strip() if len(r) > p else "" for p in pos) for r in rows2[1:]]
    print(f"[dedup] after: {len(rows2)-1} data rows · {len(set(keys2))} unique · "
          f"duplicates remaining: {len(keys2) - len(set(keys2))}")


if __name__ == "__main__":
    main()
