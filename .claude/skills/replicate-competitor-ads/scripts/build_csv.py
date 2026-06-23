#!/usr/bin/env python3.13
"""Write the input shortlist sheet back out as CSV with each ad's Google Doc link.

- Reads the ORIGINAL sheet (xlsx/csv) so every original column is preserved.
- Maps ad number -> sheet row from shortlist.json (its "row" field; default row = n+1).
- Fills a "Script Link" column with links.json[n] and a "Script Status" column with --status.
- Those columns are auto-detected by header ("script link"/"link"; "script status"/"status");
  if absent, they are appended at the end.

Usage:
  python3.13 build_csv.py --input <orig sheet> --shortlist shortlist.json --links links.json \
      --out <out.csv> [--status Drafted]
"""
import argparse, csv, json, pathlib

def load_grid(path):
    p = pathlib.Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        ws = openpyxl.load_workbook(p, data_only=True).active
        return [[("" if c.value is None else c.value) for c in row] for row in ws.iter_rows()]
    return [list(r) for r in csv.reader(open(p, encoding="utf-8-sig"))]

def find_col(header, keys):
    low = [(i, str(h or "").strip().lower()) for i, h in enumerate(header)]
    for k in keys:
        for i, h in low:
            if h == k:
                return i
    for k in keys:
        for i, h in low:
            if k in h:
                return i
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--links", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default="Drafted")
    args = ap.parse_args()

    grid = load_grid(args.input)
    if not grid:
        raise SystemExit("[build_csv] empty input")
    header = grid[0]
    shortlist = {a["n"]: a.get("row", a["n"] + 1) for a in json.load(open(args.shortlist))}
    links = json.load(open(args.links))

    link_col = find_col(header, ["script link", "link", "doc link", "script url"])
    status_col = find_col(header, ["script status", "status"])
    width = max(len(r) for r in grid)
    if link_col is None:
        link_col = width; width += 1
    if status_col is None:
        status_col = width; width += 1
    # normalize widths + ensure header labels
    grid = [list(r) + [""] * (width - len(r)) for r in grid]
    if not str(grid[0][link_col]).strip():
        grid[0][link_col] = "Script Link"
    if not str(grid[0][status_col]).strip():
        grid[0][status_col] = "Script Status"

    filled = 0
    for n_str, url in links.items():
        n = int(n_str); row = shortlist.get(n, n + 1)
        idx = row - 1
        if 0 <= idx < len(grid):
            grid[idx][link_col] = url
            grid[idx][status_col] = args.status
            filled += 1

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(grid)
    print(f"[build_csv] wrote {args.out}; filled {filled} links "
          f"(link col {link_col+1}, status col {status_col+1})")

if __name__ == "__main__":
    main()
