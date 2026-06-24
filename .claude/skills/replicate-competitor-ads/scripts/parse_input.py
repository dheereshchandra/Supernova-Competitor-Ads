#!/usr/bin/env python3.13
"""Parse a replication shortlist (xlsx / csv / json) into a normalized shortlist.json.

Auto-detects columns by header keywords (case-insensitive):
  language  -> col containing "language"
  brief     -> col containing "concept brief" (or just "brief")
  ref_link  -> col containing "reference" or "inspiration" or "link"
  name      -> col containing "idea" or "ad name" or "name" or "title"

Each output row: {n, row, name, language, brief_raw, faithful, ref_link}
  faithful = brief_raw.lower() in {"", "same", "ditto"}  (else the brief is applied)

Usage:
  python3.13 parse_input.py --input <sheet.xlsx|.csv|.json> --out shortlist.json [--sheet 0]
JSON input may be either this same schema, or a list of {name,language,brief,ref_link/link}.
"""
import argparse, csv, json, pathlib, sys

KEYS = {
    "language": ["language", "lang"],
    "brief": ["concept brief", "brief"],
    "ref_link": ["reference", "inspiration", "ref link", "link", "url"],
    "name": ["idea / ad name", "idea", "ad name", "name", "title"],
}

def pick_col(headers, keys):
    low = [(i, (h or "").strip().lower()) for i, h in enumerate(headers)]
    for k in keys:                       # exact-ish, longest keys first by caller order
        for i, h in low:
            if h == k:
                return i
    for k in keys:
        for i, h in low:
            if k in h:
                return i
    return None

# A brief that is just one of these (any trailing punctuation) means "replicate
# faithfully, no override" — no concept changes to apply.
FAITHFUL_BRIEFS = ("", "same", "ditto", "exact replication", "exact", "replication")

def is_faithful(brief):
    return brief.strip().rstrip(".!").strip().lower() in FAITHFUL_BRIEFS

def normalize(rows_as_dicts):
    out = []
    for n, d in enumerate(rows_as_dicts, start=1):
        brief = (d.get("brief") or "").strip()
        out.append({
            "n": n, "row": d.get("row", n + 1),
            "name": (d.get("name") or f"ad-{n}").strip(),
            "language": (d.get("language") or "").strip(),
            "brief_raw": brief,
            "faithful": is_faithful(brief),
            "ref_link": (d.get("ref_link") or "").strip(),
        })
    return out

def from_table(headers, rows):
    cols = {k: pick_col(headers, v) for k, v in KEYS.items()}
    missing = [k for k in ("language", "ref_link") if cols[k] is None]
    if missing:
        sys.exit(f"[parse_input] could not find column(s) for {missing} in headers: {headers}")
    dicts = []
    for r_i, r in enumerate(rows):
        if not any((c or "").strip() for c in r):
            continue
        get = lambda key: (r[cols[key]] if cols[key] is not None and cols[key] < len(r) else "")
        if not (get("ref_link") or "").strip():
            continue
        dicts.append({"row": r_i + 2, "name": get("name"), "language": get("language"),
                      "brief": get("brief"), "ref_link": get("ref_link")})
    return dicts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", default=0)
    args = ap.parse_args()
    p = pathlib.Path(args.input)
    ext = p.suffix.lower()

    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, data_only=True)
        ws = wb.worksheets[int(args.sheet)] if str(args.sheet).isdigit() else wb[args.sheet]
        grid = [[("" if c.value is None else str(c.value)) for c in row] for row in ws.iter_rows()]
        dicts = from_table(grid[0], grid[1:])
    elif ext == ".csv":
        rows = list(csv.reader(open(p, encoding="utf-8-sig")))
        dicts = from_table(rows[0], rows[1:])
    elif ext == ".json":
        data = json.load(open(p))
        dicts = [{"row": d.get("row", i + 2), "name": d.get("name", ""),
                  "language": d.get("language", ""), "brief": d.get("brief", d.get("brief_raw", "")),
                  "ref_link": d.get("ref_link", d.get("link", ""))} for i, d in enumerate(data)]
    else:
        sys.exit(f"[parse_input] unsupported input type: {ext}")

    shortlist = normalize(dicts)
    pathlib.Path(args.out).write_text(json.dumps(shortlist, ensure_ascii=False, indent=2))
    print(f"[parse_input] {len(shortlist)} ads -> {args.out}")
    for a in shortlist:
        tag = "FAITHFUL" if a["faithful"] else "BRIEF"
        print(f"  #{a['n']:>2} [{a['language'][:9]:<9}] {tag:<8} {a['name'][:40]:<40} {a['ref_link'][:60]}")

if __name__ == "__main__":
    main()
