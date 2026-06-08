#!/usr/bin/env python3
"""
compute_rank_metrics.py — Phase 1, script 2 of the competitor-ad analysis system.

Reads the append-only history log (built by build_history.py) and derives, per
ad, the longevity/rank metrics and the 4-tier performance verdict. Rebuilt from
scratch each run (the history log is the only thing that accumulates).

Outputs (under analysis/derived/{pipeline}/):
  {competitor}_enriched.csv   one row per ad: metrics + verdict + confidence
  {competitor}_weekly.csv     per (page, ISO-week): ads_live / new / winners / win_ratio

Verdict tiers (locked — see .context/rank-tracking-*.md). Longevity is the
PRIMARY signal; rank is a position proxy that only confirms. First match wins:
  strong_winner : run_days > 45  AND  >=half its life in the page's top 25%
  winner        : run_days >= 15  AND  best rank in top-100 / top-10% of page (whichever is more permissive)
  sore_loser    : CONFIRMED inactive, ran >= 7 days, never won   (needs inactive scraping; inert in v1)
  loser         : not a winner, gone from the latest scrape, and short-lived / never-ranked
  new           : first seen <= 7 days ago and <= 2 scrapes — too early to judge
  undecided     : present, in-flight

Caveat baked into every verdict: rank is the ad library's impression ordering,
NOT a measured performance metric. "Winner" = the advertiser sustained it and the
platform surfaced it (strong revealed preference), not proof of conversion.

Usage:
    python3 analysis/scripts/compute_rank_metrics.py --pipeline facebook --competitor duolingo
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

# Locked thresholds (config constants, not magic numbers).
STRONG_WINNER_RUN_DAYS = 45
WINNER_RUN_DAYS = 15
WINNER_WEEKS = 3
MEANINGFUL_RUN_DAYS = 7          # sore_loser / loser longevity floor
TOP25_FRACTION = 0.25
TOP25_GATE = 0.5                 # >= half its life in the page's top 25%
RANK_GATE_ABS = 100            # top-100 absolute ...  (winner gate; widened from 10 so 'winner' = stayed >15d AND within top-100)
RANK_GATE_PCT = 0.10           # ... OR top-10% of the page, whichever is more permissive
NEW_AGE_DAYS = 7

ENRICHED_COLS = [
    "pipeline", "competitor", "page_id", "page_name", "ad_id", "media_type",
    "language", "presenter_type", "device_format", "production_type",
    "script_group_id", "replication_type", "variant_role",
    "first_seen", "last_seen", "times_seen", "weeks_seen",
    "ad_start_date", "run_days", "run_days_is_lower_bound",
    "best_page_rank", "worst_page_rank", "median_page_rank", "current_page_rank",
    "present_latest", "is_retired", "page_count", "frac_top_25",
    "rank_gate", "top25_gate", "low_impression_ever", "verdict", "verdict_confidence",
]
WEEKLY_COLS = [
    "pipeline", "competitor", "page_id", "page_name", "week",
    "ads_live", "new_ads", "winners_live", "win_ratio",
]


def repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_enrichment(root: Path, pipeline: str, slug: str) -> dict:
    """Optional Flash-derived signals — {ad_id: {language, presenter_type,
    device_format, production_type}}. Empty until detect_language / transcribe_tag
    have been run; the transcript language (if any) overrides the text-only one."""
    import json as _json
    base = root / "analysis" / "enrichment" / pipeline
    enr: dict[str, dict] = {}
    lang_csv = base / "language" / f"{slug}.csv"
    if lang_csv.exists():
        for r in read_csv(lang_csv):
            enr.setdefault(r["ad_id"], {})["language"] = r.get("language", "")
    tdir = base / "transcripts" / slug
    if tdir.is_dir():
        for p in tdir.glob("*.json"):
            try:
                d = _json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            rec = enr.setdefault(d.get("ad_id") or p.stem, {})
            if d.get("language"):
                rec["language"] = d["language"]
            for k in ("presenter_type", "device_format", "production_type"):
                if d.get(k):
                    rec[k] = d[k]
    scsv = base / "scripts" / f"{slug}.csv"
    if scsv.exists():
        for r in read_csv(scsv):
            rec = enr.setdefault(r["ad_id"], {})
            for k in ("script_group_id", "replication_type", "variant_role"):
                if r.get(k):
                    rec[k] = r[k]
    return enr


def d(s: str) -> Optional[date]:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def week_label(dt: date) -> str:
    """ISO-week Monday date as the label."""
    iso = dt.isocalendar()
    return date.fromisocalendar(iso[0], iso[1], 1).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--winner-days", type=int, default=WINNER_RUN_DAYS)
    ap.add_argument("--strong-days", type=int, default=STRONG_WINNER_RUN_DAYS)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    hpath = root / "analysis" / "history" / args.pipeline / f"{slug}.csv"
    if not hpath.exists():
        raise SystemExit(f"[error] no history yet: {hpath}\n"
                         f"        run build_history.py first.")

    rows = read_csv(hpath)
    if not rows:
        raise SystemExit(f"[error] history is empty: {hpath}")

    # ---- page-size per (page_id, scrape_date); competitor-level latest date ----
    page_size: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        page_size[(r["page_id"], r["scrape_date"])] += 1
    latest_overall = max(r["scrape_date"] for r in rows)
    enr_map = load_enrichment(root, args.pipeline, slug)

    # ---- group rows per ad ----
    by_ad: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ad[r["ad_id"]].append(r)

    enriched: list[dict] = []
    for ad_id, ar in by_ad.items():
        ar.sort(key=lambda r: r["scrape_date"])
        page_id = ar[-1]["page_id"]
        page_name = ar[-1]["page_name"]
        dates = sorted({r["scrape_date"] for r in ar})
        first_seen, last_seen = dates[0], dates[-1]
        times_seen = len(dates)
        weeks_seen = len({week_label(d(x)) for x in dates if d(x)})

        ranks = [int(r["page_rank"]) for r in ar if r["page_rank"].isdigit()]
        best = min(ranks) if ranks else None
        worst = max(ranks) if ranks else None
        median = int(round(statistics.median(ranks))) if ranks else None
        current = next((int(r["page_rank"]) for r in reversed(ar)
                        if r["scrape_date"] == last_seen and r["page_rank"].isdigit()), None)

        # carry-forward the non-empty start date (an ad's start is fixed)
        starts = [r["ad_start_date"] for r in ar if d(r["ad_start_date"])]
        start = max(starts) if starts else ""   # max == most-recently-stated; all should agree
        sd, fsd, lsd = d(start), d(first_seen), d(last_seen)
        if sd and lsd:
            run_days, lower_bound = (lsd - sd).days, False
        else:
            run_days = (lsd - fsd).days if (lsd and fsd) else 0
            lower_bound = True

        # frac of observed life spent in the page's top 25%
        in_top25 = 0
        for r in ar:
            psize = page_size[(r["page_id"], r["scrape_date"])]
            thresh = max(1, math.ceil(TOP25_FRACTION * psize))
            if r["page_rank"].isdigit() and int(r["page_rank"]) <= thresh:
                in_top25 += 1
        frac_top_25 = round(in_top25 / times_seen, 3) if times_seen else 0.0

        # Presence is competitor-level: an ad is "present" if it appears in the
        # competitor's most recent scrape. Keying on page_id is unsafe — some
        # scrapers emit a different facebook_page_id for the same advertiser
        # across runs (e.g. ewa), which would hide every retirement.
        present_latest = last_seen == latest_overall
        # page_count = the most complete observed size of this ad's page
        page_count = max((page_size[(page_id, x)] for x in dates
                          if (page_id, x) in page_size), default=0)
        rank_gate = best is not None and best <= max(RANK_GATE_ABS,
                                                     math.ceil(RANK_GATE_PCT * page_count))
        top25_gate = frac_top_25 >= TOP25_GATE
        low_imp = any((r.get("low_impression") or "").strip().lower()
                      in ("true", "1", "yes") for r in ar)
        age_days = (d(latest_overall) - fsd).days if (d(latest_overall) and fsd) else 0
        confirmed_inactive = False   # set true once inactive scraping exists

        # ---- verdict (first match wins) ----
        # Winner tiers are status-independent: a long-lived, well-ranked ad that
        # later goes inactive STAYS a winner (we mark it retired separately, never
        # demote it). new/undecided describe only ads still PRESENT in the latest
        # scrape; any non-winner that has dropped out is a loser (gone, didn't win).
        if run_days > args.strong_days and top25_gate:
            verdict = "strong_winner"
        elif run_days >= args.winner_days and rank_gate:
            verdict = "winner"
        elif confirmed_inactive and run_days >= MEANINGFUL_RUN_DAYS:
            verdict = "sore_loser"
        elif not present_latest:
            verdict = "loser"
        elif age_days <= NEW_AGE_DAYS and times_seen <= 2:
            verdict = "new"
        else:
            verdict = "undecided"
        is_retired = (not present_latest)

        if verdict in ("winner", "strong_winner"):
            confidence = "low" if lower_bound else "high"
        elif verdict == "loser":
            confidence = "low"            # absence-inferred in v1
        else:
            confidence = "high"

        enriched.append({
            "pipeline": args.pipeline, "competitor": slug,
            "page_id": page_id, "page_name": page_name, "ad_id": ad_id,
            "media_type": ar[-1]["media_type"],
            "language": enr_map.get(ad_id, {}).get("language", ""),
            "presenter_type": enr_map.get(ad_id, {}).get("presenter_type", ""),
            "device_format": enr_map.get(ad_id, {}).get("device_format", ""),
            "production_type": enr_map.get(ad_id, {}).get("production_type", ""),
            "script_group_id": enr_map.get(ad_id, {}).get("script_group_id", ""),
            "replication_type": enr_map.get(ad_id, {}).get("replication_type", ""),
            "variant_role": enr_map.get(ad_id, {}).get("variant_role", ""),
            "first_seen": first_seen, "last_seen": last_seen,
            "times_seen": times_seen, "weeks_seen": weeks_seen,
            "ad_start_date": start, "run_days": run_days,
            "run_days_is_lower_bound": lower_bound,
            "best_page_rank": best, "worst_page_rank": worst,
            "median_page_rank": median, "current_page_rank": current,
            "present_latest": present_latest, "is_retired": is_retired,
            "page_count": page_count,
            "frac_top_25": frac_top_25, "rank_gate": rank_gate, "top25_gate": top25_gate,
            "low_impression_ever": low_imp,
            "verdict": verdict, "verdict_confidence": confidence,
        })

    enriched.sort(key=lambda e: (e["page_id"], e["best_page_rank"] or 10**9))

    # ---- weekly volume per (page, ISO week) ----
    # ad -> verdict lookup
    verdict_of = {e["ad_id"]: e["verdict"] for e in enriched}
    first_seen_of = {e["ad_id"]: e["first_seen"] for e in enriched}
    name_of = {e["page_id"]: e["page_name"] for e in enriched}
    week_ads: dict[tuple[str, str], set] = defaultdict(set)
    for r in rows:
        wk = week_label(d(r["scrape_date"])) if d(r["scrape_date"]) else r["scrape_date"]
        week_ads[(r["page_id"], wk)].add(r["ad_id"])

    weekly: list[dict] = []
    for (page_id, wk), ads in sorted(week_ads.items()):
        new_ads = sum(1 for a in ads
                      if d(first_seen_of.get(a, "")) and week_label(d(first_seen_of[a])) == wk)
        winners = sum(1 for a in ads if verdict_of.get(a) in ("winner", "strong_winner"))
        weekly.append({
            "pipeline": args.pipeline, "competitor": slug,
            "page_id": page_id, "page_name": name_of.get(page_id, ""),
            "week": wk, "ads_live": len(ads), "new_ads": new_ads,
            "winners_live": winners,
            "win_ratio": round(winners / len(ads), 3) if ads else 0.0,
        })

    outdir = root / "analysis" / "derived" / args.pipeline
    outdir.mkdir(parents=True, exist_ok=True)
    epath = outdir / f"{slug}_enriched.csv"
    wpath = outdir / f"{slug}_weekly.csv"
    with epath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ENRICHED_COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(enriched)
    with wpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WEEKLY_COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(weekly)

    # ---- per-language / per-format rollups (only if enrichment is present) ----
    def rollup(key: str) -> list[dict]:
        agg: dict[str, dict] = defaultdict(lambda: {"ads": 0, "winners": 0})
        for e in enriched:
            k = (e.get(key) or "").strip()
            if not k:
                continue
            agg[k]["ads"] += 1
            if e["verdict"] in ("winner", "strong_winner"):
                agg[k]["winners"] += 1
        return [{"pipeline": args.pipeline, "competitor": slug, key: k,
                 "ads": v["ads"], "winners": v["winners"],
                 "win_ratio": round(v["winners"] / v["ads"], 3) if v["ads"] else 0.0}
                for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["ads"])]

    for key, fname in [("language", f"{slug}_by_language.csv"),
                       ("device_format", f"{slug}_by_format.csv"),
                       ("replication_type", f"{slug}_by_replication.csv")]:
        data = rollup(key)
        if data:
            with (outdir / fname).open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["pipeline", "competitor", key,
                                                   "ads", "winners", "win_ratio"])
                w.writeheader(); w.writerows(data)
            print(f"  -> {outdir / fname}")

    counts = defaultdict(int)
    for e in enriched:
        counts[e["verdict"]] += 1
    print(f"{slug}: {len(enriched)} ads | verdicts: {dict(sorted(counts.items()))}")
    print(f"  -> {epath}")
    print(f"  -> {wpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
