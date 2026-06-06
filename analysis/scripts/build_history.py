#!/usr/bin/env python3
"""
build_history.py — Phase 1, script 1 of the competitor-ad analysis system.

Turns dated scrape SNAPSHOTS into the append-only rank HISTORY LOG — the single
source of truth for rank-over-time. One row per ad per scrape_date.

Why this exists: the per-competitor master CSV is "latest snapshot only" and is
useless as a time series. The dated input snapshots (facebook/inputs/fb-ads-*.csv,
google/inputs/g-ads-*.csv) are the real raw material. This script folds each
snapshot into analysis/history/{pipeline}/{competitor}.csv.

Design (locked — see .context/rank-tracking-brainstorm.md §3-4):
  * Grain: exactly one row per ad per scrape_date (collapse creatives/variants).
  * scrape_date comes from the INPUT FILENAME, not any internal date column
    (internal date columns are inconsistent — verified on ewa).
  * page_rank is computed locally (dense ordinal of row_rank within
    (page_id, scrape_date), tie-broken by ad_id) — never trusted from the file.
  * Idempotent: re-running a scrape REPLACES that (ad_id, scrape_date)'s rows,
    so replays and double-runs are safe. Otherwise purely additive (append at
    the bottom) → clean git diffs, no merge conflicts between competitors.

Usage:
    # one snapshot
    python3 analysis/scripts/build_history.py --pipeline facebook \
        --competitor duolingo \
        --scrape facebook/inputs/fb-ads-duolingo-2026-06-04-1540.csv

    # backfill: replay every real snapshot for a competitor, oldest -> newest
    python3 analysis/scripts/build_history.py --pipeline facebook \
        --competitor duolingo --backfill

    # preview only
    python3 analysis/scripts/build_history.py --pipeline facebook \
        --competitor duolingo --backfill --dry-run
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional

# Canonical history schema (both pipelines mapped onto this one set).
HISTORY_COLS = [
    "pipeline", "competitor", "page_id", "page_name", "ad_id",
    "scrape_date", "row_rank", "page_rank", "ad_start_date",
    "media_type", "low_impression",
]

# Per-pipeline source-column mapping: canonical -> source column name.
FIELD_MAP = {
    "facebook": {
        "page_id": "facebook_page_id",
        "page_name": "facebook_page_name",
        "ad_id": "ad_library_id",
        "row_rank": "row_rank",
        "ad_start_date": "ad_start_date",
        "media_type": "ad_media_type",
        "low_impression": "has_low_impression_warning",
        "creative_index": "creative_index_in_ad",
    },
    "google": {
        "page_id": "advertiser_id",
        "page_name": "advertiser_name",
        "ad_id": "creative_id",
        "row_rank": "row_rank",
        "ad_start_date": None,            # Google has no start date
        "media_type": "creative_format",
        "low_impression": None,
        "creative_index": "variant_index",
    },
}

# Strict filename whitelist (slug-anchored), built per-call. Captures the date.
# FB: fb-ads-{slug}-YYYY-MM-DD[-HHMM].csv   (nothing else after the date/time)
# Google: g-ads-{slug}-YYYY-MM-DD.csv
def _filename_pattern(pipeline: str, slug: str) -> str:
    s = re.escape(slug)
    if pipeline == "facebook":
        return r"^fb-ads-" + s + r"-(\d{4}-\d{2}-\d{2})(?:-\d{4})?\.csv$"
    return r"^g-ads-" + s + r"-(\d{4}-\d{2}-\d{2})\.csv$"


def repo_root(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # analysis/scripts/build_history.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


def inputs_dir(root: Path, pipeline: str) -> Path:
    return root / pipeline / "inputs"


def history_path(root: Path, pipeline: str, competitor: str) -> Path:
    return root / "analysis" / "history" / pipeline / f"{competitor}.csv"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def scrape_date_from_name(name: str, pipeline: str, slug: str) -> Optional[str]:
    m = re.match(_filename_pattern(pipeline, slug), name)
    return m.group(1) if m else None


def header_and_count(path: Path) -> tuple[list[str], int]:
    """Return (header, data_row_count) without loading the whole file as dicts."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rdr = csv.reader(fh)
        try:
            header = next(rdr)
        except StopIteration:
            return [], 0
        return header, sum(1 for _ in rdr)


def discover_snapshots(root: Path, pipeline: str,
                       slug: str) -> tuple[list[tuple[str, Path]], list[tuple[str, str]]]:
    """Return ([(scrape_date, path)], [(skipped_file, reason)]). One file per date
    (the most complete CONFORMING file), sorted oldest -> newest. Files that match
    the name pattern but use a non-standard schema (missing the ad-id column — e.g.
    an experimental scraper variant) are skipped, not silently picked."""
    idir = inputs_dir(root, pipeline)
    if not idir.is_dir():
        return [], []
    id_col = FIELD_MAP[pipeline]["ad_id"]
    by_date: dict[str, Path] = {}
    rows_for: dict[str, int] = {}
    skipped: list[tuple[str, str]] = []
    for p in sorted(idir.glob("*.csv")):
        date = scrape_date_from_name(p.name, pipeline, slug)
        if not date:
            continue
        header, n = header_and_count(p)
        if id_col not in header:
            skipped.append((p.name, f"non-standard schema (no '{id_col}' column)"))
            continue
        # Keep the most complete CONFORMING file per date (tiebreak: later filename).
        if date not in by_date or n > rows_for[date] or (
            n == rows_for[date] and p.name > by_date[date].name
        ):
            by_date[date] = p
            rows_for[date] = n
    return sorted(by_date.items()), skipped


def collapse_to_ads(rows: list[dict], pipeline: str) -> list[dict]:
    """One row per ad: keep the creative/variant with index 0 (else lowest index,
    else first seen). Rank fields are identical across an ad's creatives."""
    fm = FIELD_MAP[pipeline]
    idx_col = fm["creative_index"]
    best: dict[str, tuple[int, dict]] = {}
    for r in rows:
        ad_id = (r.get(fm["ad_id"]) or "").strip()
        if not ad_id:
            continue
        try:
            idx = int((r.get(idx_col) or "0").strip() or "0")
        except ValueError:
            idx = 0
        if ad_id not in best or idx < best[ad_id][0]:
            best[ad_id] = (idx, r)
    return [v[1] for v in best.values()]


def _rank_int(value: str) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return 10 ** 9  # unranked / empty rows sort last


def to_history_rows(ad_rows: list[dict], pipeline: str, competitor: str,
                    scrape_date: str) -> list[dict]:
    fm = FIELD_MAP[pipeline]

    def get(r: dict, key: str) -> str:
        src = fm[key]
        return "" if src is None else (r.get(src) or "").strip()

    # Group by page, assign page_rank = strict ordinal of (row_rank, ad_id).
    by_page: dict[str, list[dict]] = {}
    for r in ad_rows:
        by_page.setdefault(get(r, "page_id"), []).append(r)

    out: list[dict] = []
    for page_id, prows in by_page.items():
        prows.sort(key=lambda r: (_rank_int(get(r, "row_rank")), get(r, "ad_id")))
        for i, r in enumerate(prows, start=1):
            out.append({
                "pipeline": pipeline,
                "competitor": competitor,
                "page_id": page_id,
                "page_name": get(r, "page_name"),
                "ad_id": get(r, "ad_id"),
                "scrape_date": scrape_date,
                "row_rank": get(r, "row_rank"),
                "page_rank": str(i),
                "ad_start_date": get(r, "ad_start_date"),
                "media_type": get(r, "media_type"),
                "low_impression": get(r, "low_impression"),
            })
    return out


def upsert(history: list[dict], new_rows: list[dict]) -> list[dict]:
    """Replace any existing rows that share an (ad_id, scrape_date) with a new
    row, then keep everything else. Sorted by (scrape_date, page_id, page_rank)."""
    replaced_keys = {(r["ad_id"], r["scrape_date"]) for r in new_rows}
    kept = [r for r in history
            if (r.get("ad_id"), r.get("scrape_date")) not in replaced_keys]
    merged = kept + new_rows
    merged.sort(key=lambda r: (
        r.get("scrape_date", ""), r.get("page_id", ""), _rank_int(r.get("page_rank", "")),
    ))
    return merged


def synth_from_master(rows: list[dict], pipeline: str, competitor: str) -> list[dict]:
    """Low-fidelity 2-point history from the master: each ad emits a row at its
    first_scrape_run_date AND its latest_scrape_run_date, ranked (per page+date)
    by the master's row_rank. Gives times_seen/run_days/best_page_rank now; gets
    overwritten by real dated snapshots once they accrue. Used for Google, whose
    input snapshots aren't committed yet."""
    ad_rows = collapse_to_ads(rows, pipeline)
    by_date: dict[str, list[dict]] = {}
    for r in ad_rows:
        first = (r.get("first_scrape_run_date") or "").strip()
        latest = (r.get("latest_scrape_run_date") or "").strip()
        scrape = (r.get("scrape_run_date") or "").strip()
        use = [d for d in (first, latest) if d]
        if not use and scrape:
            use = [scrape]
        for d in dict.fromkeys(use):           # dedupe, keep order
            by_date.setdefault(d, []).append(r)
    out: list[dict] = []
    for d, drows in sorted(by_date.items()):
        out.extend(to_history_rows(drows, pipeline, competitor, d))
    return out


def write_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True, help="Competitor slug.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--scrape", help="A single input snapshot CSV to ingest.")
    group.add_argument("--backfill", action="store_true",
                       help="Replay every real snapshot for this competitor.")
    group.add_argument("--from-master", action="store_true",
                       help="Seed a low-fidelity 2-point history from the master's "
                            "first/latest scrape dates. For Google, which has no "
                            "committed input snapshots yet — gives longevity now, "
                            "replaced by real snapshots as they accrue.")
    ap.add_argument("--base", default=None, help="Repo root (default: auto).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen; write nothing.")
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    hpath = history_path(root, args.pipeline, slug)

    # --- low-fidelity seed from the master (Google has no committed snapshots) ---
    if args.from_master:
        master = root / args.pipeline / "master" / f"{slug}.csv"
        if not master.exists():
            sys.exit(f"[error] master not found: {master}")
        new_rows = synth_from_master(read_csv(master), args.pipeline, slug)
        if not new_rows:
            print(f"[info] {slug} master has no usable dated rows — nothing to do.")
            return 0
        dates = sorted({r["scrape_date"] for r in new_rows})
        if args.dry_run:
            print(f"[dry-run] would seed {len(new_rows)} rows across {len(dates)} "
                  f"date(s) {dates} into {hpath}")
            return 0
        history = read_csv(hpath) if hpath.exists() else []
        history = upsert(history, new_rows)
        write_history(hpath, history)
        print(f"from-master: seeded {len(new_rows)} rows across {len(dates)} "
              f"date(s) {dates} -> {hpath}")
        return 0

    # Build the work list of (scrape_date, path).
    if args.scrape:
        spath = Path(args.scrape)
        if not spath.is_absolute():
            spath = (root / spath).resolve()
        if not spath.exists():
            sys.exit(f"[error] snapshot not found: {spath}")
        date = scrape_date_from_name(spath.name, args.pipeline, slug)
        if not date:
            sys.exit(f"[error] '{spath.name}' is not a recognized {args.pipeline} "
                     f"snapshot for '{slug}' (expected the strict naming pattern).")
        id_col = FIELD_MAP[args.pipeline]["ad_id"]
        header, _ = header_and_count(spath)
        if id_col not in header:
            sys.exit(f"[error] '{spath.name}' has a non-standard schema "
                     f"(no '{id_col}' column) — cannot ingest.")
        work = [(date, spath)]
    else:
        work, skipped = discover_snapshots(root, args.pipeline, slug)
        for name, reason in skipped:
            print(f"[skip] {name}: {reason}")
        if not work:
            print(f"[info] no usable snapshots found for {args.pipeline}/{slug} in "
                  f"{inputs_dir(root, args.pipeline)} — nothing to do.")
            return 0

    history = read_csv(hpath) if hpath.exists() else []
    print(f"history: {hpath}  (existing rows: {len(history)})")

    total_new = 0
    for date, path in work:
        rows = read_csv(path)
        ad_rows = collapse_to_ads(rows, args.pipeline)
        new_rows = to_history_rows(ad_rows, args.pipeline, slug, date)
        pages = len({r["page_id"] for r in new_rows})
        replaced = sum(
            1 for r in history
            if (r.get("ad_id"), r.get("scrape_date")) in
            {(n["ad_id"], n["scrape_date"]) for n in new_rows})
        history = upsert(history, new_rows)
        total_new += len(new_rows)
        print(f"  {date}  {path.name:<48} ads={len(new_rows):<5} "
              f"pages={pages}  ({'replaced '+str(replaced) if replaced else 'new'})")

    if args.dry_run:
        print(f"[dry-run] would write {len(history)} total rows "
              f"({total_new} from this run) to {hpath}")
        return 0

    write_history(hpath, history)
    print(f"wrote {len(history)} total rows to {hpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
