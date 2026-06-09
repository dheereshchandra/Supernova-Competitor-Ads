#!/usr/bin/env python3.13
"""
build_version_view.py — per-version "relaunch / placement-change" view (OFFLINE, no API).

A v2.3 scrape enumerates every VERSION of an ad (one master row per version/creative,
with version_start_date, version_platforms_distribution, version_destination_url,
version_cta_label, creative_aspect_ratio …). The media is often byte-identical across
versions (A1 dedups the video), but the METADATA is kept — and that metadata answers a
real question: when a competitor shows "N versions" of an ad, is it…
  • a RELAUNCH      — the same ad re-started on a LATER date (different version_start_date),
                      i.e. they recycle the creative. The most common real signal.
  • a PLACEMENT/FORMAT change — versions differ in platforms (Threads/Instagram/…),
                      aspect ratio (9:16 vs 16:9), destination URL, or CTA. Rare but
                      strategically interesting when it happens.
  • a SIMULTANEOUS duplicate — same start date, no metadata difference (FB just
                      enumerated the same ad twice). Noise.

Reads {pipeline}/master/{slug}.csv; writes
  analysis/derived/{pipeline}/{slug}_versions.csv          (one row per multi-version ad)
      ad_id, page_name, version_count, distinct_start_dates, first_start, last_start,
      relaunch_span_days, kind, platforms_changed, aspect_changed,
      destination_changed, cta_changed
  analysis/derived/{pipeline}/{slug}_versions_summary.csv  (rollup: kinds, change counts,
      version-count distribution, relaunch cadence)

Usage:
    python3.13 analysis/scripts/build_version_view.py --pipeline facebook --competitor mysivi
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

VERSION_COLS = {"version_index", "version_start_date"}   # gate: skip masters without versions


def repo_root(explicit):
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _int0(x) -> int:
    try:
        return int(str(x or "0").strip() or "0")
    except (ValueError, TypeError):
        return 0


def _d(s):
    """Parse a date in either ISO ('2026-05-18') or FB's human format ('18 May 2026' /
    'May 18, 2026'). The master stores version_start_date in the human form."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    master = root / args.pipeline / "master" / f"{slug}.csv"
    rows = read_csv(master)
    if not rows:
        raise SystemExit(f"[error] master not found / empty: {master}")
    if not VERSION_COLS.issubset(rows[0].keys()):
        print(f"{slug}: master has no version columns (pre-v2.3) — nothing to do.")
        return 0

    # group ad -> all its rows. version_index is POSITIONAL (changes per scrape), so we
    # work off all rows directly and key "versions" off the stable version_id when present.
    ads: dict[str, list[dict]] = defaultdict(list)
    page_name: dict[str, str] = {}
    for r in rows:
        aid = (r.get("ad_library_id") or "").strip()
        if not aid:
            continue
        ads[aid].append(r)
        page_name.setdefault(aid, (r.get("facebook_page_name") or "").strip())

    out_rows = []
    kinds = defaultdict(int)
    changes = defaultdict(int)
    vcount_dist = defaultdict(int)
    relaunch_gaps = []        # days between consecutive relaunch dates
    relaunch_spans = []
    for aid, arows in ads.items():
        def distinct(col):    # distinct non-blank values of a column across the ad's rows
            return {(r.get(col) or "").strip() for r in arows if (r.get(col) or "").strip()}

        vids = distinct("version_id")
        vidx = {_int0(r.get("version_index")) for r in arows}
        max_count = max((_int0(r.get("ad_version_count")) for r in arows), default=0)
        vcount = max(len(vids), len(vidx), max_count)
        if vcount <= 1:
            continue
        vcount_dist[vcount] += 1
        starts = sorted({d for d in (_d(r.get("version_start_date")) for r in arows) if d})
        n_dates = len(starts)
        platforms_changed = len(distinct("version_platforms_distribution")) > 1
        destination_changed = len(distinct("version_destination_url")) > 1
        cta_changed = len(distinct("version_cta_label")) > 1
        asp_changed = len(distinct("creative_aspect_ratio")) > 1
        any_meta = platforms_changed or destination_changed or cta_changed or asp_changed

        if n_dates > 1:
            kind = "relaunch"
            relaunch_spans.append((starts[-1] - starts[0]).days)
            relaunch_gaps.extend((starts[i] - starts[i - 1]).days for i in range(1, len(starts)))
        elif any_meta:
            kind = "placement_format_change"
        else:
            kind = "simultaneous_duplicate"
        kinds[kind] += 1
        for k, v in (("platforms", platforms_changed), ("aspect", asp_changed),
                     ("destination", destination_changed), ("cta", cta_changed)):
            if v:
                changes[k] += 1

        out_rows.append({
            "ad_id": aid, "page_name": page_name.get(aid, ""), "version_count": vcount,
            "distinct_start_dates": n_dates,
            "first_start": starts[0].isoformat() if starts else "",
            "last_start": starts[-1].isoformat() if starts else "",
            "relaunch_span_days": (starts[-1] - starts[0]).days if n_dates > 1 else "",
            "kind": kind,
            "platforms_changed": "true" if platforms_changed else "false",
            "aspect_changed": "true" if asp_changed else "false",
            "destination_changed": "true" if destination_changed else "false",
            "cta_changed": "true" if cta_changed else "false",
        })

    derived = root / "analysis" / "derived" / args.pipeline
    derived.mkdir(parents=True, exist_ok=True)
    out_rows.sort(key=lambda r: (-r["version_count"], r["ad_id"]))
    cols = ["ad_id", "page_name", "version_count", "distinct_start_dates", "first_start",
            "last_start", "relaunch_span_days", "kind", "platforms_changed",
            "aspect_changed", "destination_changed", "cta_changed"]
    out = derived / f"{slug}_versions.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(out_rows)

    # summary
    srows = []
    for k in ("relaunch", "placement_format_change", "simultaneous_duplicate"):
        srows.append({"metric": f"kind:{k}", "value": kinds.get(k, 0)})
    for k in ("platforms", "aspect", "destination", "cta"):
        srows.append({"metric": f"changed:{k}", "value": changes.get(k, 0)})
    for vc in sorted(vcount_dist):
        srows.append({"metric": f"ads_with_{vc}_versions", "value": vcount_dist[vc]})
    if relaunch_spans:
        srows.append({"metric": "relaunch_span_days_median", "value": int(statistics.median(relaunch_spans))})
    if relaunch_gaps:
        srows.append({"metric": "relaunch_gap_days_median", "value": int(statistics.median(relaunch_gaps))})
    sout = derived / f"{slug}_versions_summary.csv"
    with sout.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value"])
        w.writeheader(); w.writerows(srows)

    total_mv = len(out_rows)
    print(f"{slug}: {total_mv} multi-version ads | "
          f"relaunch {kinds['relaunch']}, placement/format-change {kinds['placement_format_change']}, "
          f"simultaneous-dup {kinds['simultaneous_duplicate']}")
    if relaunch_gaps:
        print(f"  relaunch cadence: median {int(statistics.median(relaunch_gaps))} days between relaunches")
    print(f"  -> {out}\n  -> {sout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
