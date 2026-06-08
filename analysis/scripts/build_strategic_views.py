#!/usr/bin/env python3
"""
build_strategic_views.py — Phase 1, script 5 of the competitor-ad analysis system.

OFFLINE. Reads the already-derived CSVs + transcript sidecars only — NO API
calls, NO network. Re-rolls the existing data into strategic views that answer
Q1-Q11. Rebuilt from scratch each run. Runs AFTER compute_rank_metrics.py +
build_report.py, so {slug}_enriched.csv and scripts/{slug}.csv already exist.

Outputs (under analysis/derived/{pipeline}/ unless noted):
  {slug}_by_bucket.csv               Q2/Q5/Q11 — 4-bucket (+ split_screen + TOTAL) mix
  {slug}_raw_presenter_counts.csv    raw per-presenter_type counts (nothing lost)
  {slug}_raw_production_counts.csv    raw per-production_type counts
  {slug}_raw_format_counts.csv        raw per-device_format counts
  {slug}_by_format_axis.csv          Axis 1 — merged format (app-demo) mix
  {slug}_by_angle.csv                Axis 3 — message/hook angle mix (NEW)
  {slug}_by_split_role.csv           split-screen role (ai-corrects-human, ...)
  {slug}_new_per_week.csv            Q9 — new scripts / formats / ads per ISO week
  {slug}_replication_speed.csv       Q10 — per (group, replica) days_to_replica
  {slug}_replication_speed_summary.csv  Q10 — median/mean per replication_type
  {slug}_by_script_group.csv         Q11 — per-script-group performance
  {slug}_daily_volume.csv            Q1 — per scrape_date volume (only if history)
  analysis/reports/{latest}_{slug}_{pipeline}_strategic.md   ties Q1-Q11 to numbers

Usage:
    python3 analysis/scripts/build_strategic_views.py --pipeline facebook --competitor duolingo
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict, Counter
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Editable 4-bucket (+overrides) mapping. classify_bucket() evaluates rules in
# list order and returns the first match's name, else 'other'. This lets buckets
# be re-derived from {slug}_by_bucket.csv's raw count sidecars WITHOUT re-running
# enrichment — just edit and re-run this script.
WINNER_VERDICTS = {"winner", "strong_winner"}

# Each rule: (bucket_name, predicate(presenter_type, production_type, device_format) -> bool)
# ORDER MATTERS — first match wins. paper_translation is an override checked
# first; ai_plus_human before ai_plus_ai (an ai+human presenter is human-paired
# even if production is ai-generated); human_only last before the 'other' default.
BUCKET_CONFIG = {
    "order": [
        "paper_translation",
        "ai_plus_human",
        "ai_plus_ai",
        "human_only",
    ],
    "rules": {
        # pen-and-paper handwriting/translation explainer format (override)
        "paper_translation": lambda p, prod, fmt: fmt == "pen-and-paper",
        # any ad pairing a human with an AI presenter
        "ai_plus_human": lambda p, prod, fmt: p == "ai+human",
        # fully AI (incl. split-screen AI comparisons): AI-generated production
        # with no human on screen
        "ai_plus_ai": lambda p, prod, fmt: (
            prod == "ai-generated"
            and p in {"ai-avatar-only", "voiceover-only", "none"}
        ),
        # real human on camera, not AI-generated
        "human_only": lambda p, prod, fmt: (
            p == "human-only" and prod != "ai-generated"
        ),
    },
    "default": "other",
}

# Also emitted regardless of bucket so nothing is lost:
#   SPLIT_SCREEN_FORMAT flags device_format=='split-screen' as its own pseudo-bucket row
#   + raw per-presenter_type / per-production_type / per-device_format count CSVs.
SPLIT_SCREEN_FORMAT = "split-screen"

# Axis-1 format merge: the two tiny straight-to-camera formats read as one
# "app-demo" category (each alone is small; together = "straight demo/spokesperson").
FORMAT_MERGE = {"app-screencast": "app-demo", "talking-head": "app-demo"}

# NOTE on live duolingo enums (verify before trusting buckets):
#   presenter_type observed: voiceover-only, human-only, none   (NO 'ai-avatar-only'/'ai+human' yet)
#   production_type observed: human-recorded, mixed             (NO 'ai-generated' yet)
#   device_format observed: app-screencast, skit-narrative, listicle-montage,
#                           split-screen, text-on-screen-only, other  (NO 'pen-and-paper' yet)
# So today most duolingo ads fall to 'human_only' or 'other'; the ai_* and
# paper_translation buckets are forward-looking for competitors that use them.

CAVEAT = (
    "> **How to read this:** rank is the ad library's *impression ordering*, a "
    "position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). "
    "A \"winner\" means the advertiser **sustained** the ad (longevity, the primary "
    "signal) and the platform **kept surfacing** it (rank, confirmatory) — strong "
    "revealed preference, not proof of conversion. Longevity carries the verdict; "
    "rank only corroborates."
)


# ---------------------------------------------------------------------------
# Helpers copied verbatim / per-spec from compute_rank_metrics.py + build_report.py
def repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _int(x, default=10 ** 9):
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def d(s: str) -> Optional[date]:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def week_label(dt: date) -> str:
    """ISO-week Monday date as the label."""
    iso = dt.isocalendar()
    return date.fromisocalendar(iso[0], iso[1], 1).isoformat()


def win_ratio(winners: int, ads: int) -> float:
    return round(winners / ads, 3) if ads else 0.0


def classify_bucket(presenter_type: str, production_type: str, device_format: str) -> str:
    """Evaluate BUCKET_CONFIG rules IN ORDER; return the first matching bucket,
    else the configured default ('other'). Reads from the editable config so
    buckets can be re-derived without re-running enrichment."""
    p = (presenter_type or "").strip()
    prod = (production_type or "").strip()
    fmt = (device_format or "").strip()
    for name in BUCKET_CONFIG["order"]:
        rule = BUCKET_CONFIG["rules"].get(name)
        if rule and rule(p, prod, fmt):
            return name
    return BUCKET_CONFIG["default"]


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {path}")


# ---------------------------------------------------------------------------
def load_sidecar_fields(tdir: Path, ad_id: str) -> dict:
    """Read presenter_type/production_type/device_format from a transcript
    sidecar. Mirrors load_enrichment() in compute_rank_metrics.py."""
    p = tdir / f"{ad_id}.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    out = {}
    for k in ("presenter_type", "production_type", "device_format"):
        v = obj.get(k)
        if v:
            out[k] = v
    return out


def load_angle_fields(tdir: Path, ad_id: str) -> dict:
    """Read the Axis-3 / extra fields (message_angle, split_screen_role,
    has_price_offer) from a transcript sidecar — these are NOT in enriched.csv,
    so they always come straight from the sidecar (empty for untagged ads)."""
    p = tdir / f"{ad_id}.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k: obj.get(k) for k in ("message_angle", "split_screen_role", "has_price_offer")}


def merged_format(fmt: str) -> str:
    """Axis-1 display format: collapse the tiny straight-to-camera formats."""
    f = (fmt or "").strip()
    return FORMAT_MERGE.get(f, f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=["facebook", "google"])
    ap.add_argument("--competitor", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    root = repo_root(args.base)
    slug = args.competitor.lower().strip()
    pipeline = args.pipeline

    derived = root / "analysis" / "derived" / pipeline
    enriched_rows = read_csv(derived / f"{slug}_enriched.csv")
    if not enriched_rows:
        raise SystemExit(f"[error] no enriched data for {slug} "
                         f"(run compute_rank_metrics.py first).")

    scripts_rows = read_csv(root / "analysis" / "enrichment" / pipeline
                            / "scripts" / f"{slug}.csv")
    history_rows = read_csv(root / "analysis" / "history" / pipeline / f"{slug}.csv")

    tdir = root / "analysis" / "enrichment" / pipeline / "transcripts" / slug

    # scripts_map = authoritative source for script_group_id / replication_type /
    # variant_role / group_size, keyed on ad_id.
    scripts_map: dict[str, dict] = {r["ad_id"]: r for r in scripts_rows}

    # ---- build in-memory 'ad' records (one per enriched row) ----
    ads: list[dict] = []
    for r in enriched_rows:
        ad_id = r["ad_id"]
        presenter_type = (r.get("presenter_type") or "").strip()
        production_type = (r.get("production_type") or "").strip()
        device_format = (r.get("device_format") or "").strip()

        # Only touch the sidecar when an enriched field is blank (untranscribed ads).
        if not presenter_type or not production_type or not device_format:
            side = load_sidecar_fields(tdir, ad_id)
            if not presenter_type:
                presenter_type = (side.get("presenter_type") or "").strip()
            if not production_type:
                production_type = (side.get("production_type") or "").strip()
            if not device_format:
                device_format = (side.get("device_format") or "").strip()

        # Axis 3 + extras always come from the sidecar (not in enriched.csv)
        angle = load_angle_fields(tdir, ad_id)
        message_angle = (angle.get("message_angle") or "").strip()
        split_screen_role = (angle.get("split_screen_role") or "").strip()
        has_price_offer = bool(angle.get("has_price_offer"))

        smap = scripts_map.get(ad_id, {})
        script_group_id = (smap.get("script_group_id") or r.get("script_group_id") or "").strip()
        replication_type = (smap.get("replication_type") or r.get("replication_type") or "").strip()
        variant_role = (smap.get("variant_role") or r.get("variant_role") or "").strip()
        group_size = _int(smap.get("group_size"), default=0)

        verdict = (r.get("verdict") or "").strip()
        is_winner = verdict in WINNER_VERDICTS

        ads.append({
            "ad_id": ad_id,
            "presenter_type": presenter_type,
            "production_type": production_type,
            "device_format": device_format,
            "script_group_id": script_group_id,
            "replication_type": replication_type,
            "variant_role": variant_role,
            "group_size": group_size,
            "verdict": verdict,
            "is_winner": is_winner,
            "first_seen": d(r.get("first_seen", "")),
            "first_seen_raw": (r.get("first_seen") or "").strip(),
            "last_seen": (r.get("last_seen") or "").strip(),
            "run_days": _int(r.get("run_days"), default=0),
            "bucket": classify_bucket(presenter_type, production_type, device_format),
            "split_screen": device_format == SPLIT_SCREEN_FORMAT,
            "format_axis": merged_format(device_format),
            "message_angle": message_angle,
            "split_screen_role": split_screen_role,
            "has_price_offer": has_price_offer,
        })

    # quick lookups keyed by ad_id
    verdict_of = {a["ad_id"]: a["verdict"] for a in ads}
    first_seen_of = {a["ad_id"]: a["first_seen_raw"] for a in ads}
    is_winner_of = {a["ad_id"]: a["is_winner"] for a in ads}

    latest = max(a["last_seen"] for a in ads if a["last_seen"])

    # =====================================================================
    # OUTPUT 1: by_bucket (+ 3 raw count files)
    # =====================================================================
    bucket_agg: dict[str, dict] = defaultdict(lambda: {"ads": 0, "winners": 0})
    for a in ads:
        bucket_agg[a["bucket"]]["ads"] += 1
        if a["is_winner"]:
            bucket_agg[a["bucket"]]["winners"] += 1

    by_bucket_rows = []
    for bucket, v in sorted(bucket_agg.items(), key=lambda kv: -kv[1]["ads"]):
        by_bucket_rows.append({
            "pipeline": pipeline, "competitor": slug, "bucket": bucket,
            "ads": v["ads"], "winners": v["winners"],
            "win_ratio": win_ratio(v["winners"], v["ads"]),
        })
    # split_screen pseudo-row
    ss_ads = sum(1 for a in ads if a["split_screen"])
    ss_winners = sum(1 for a in ads if a["split_screen"] and a["is_winner"])
    by_bucket_rows.append({
        "pipeline": pipeline, "competitor": slug, "bucket": "split_screen",
        "ads": ss_ads, "winners": ss_winners, "win_ratio": win_ratio(ss_winners, ss_ads),
    })
    # TOTAL row
    tot_ads = len(ads)
    tot_winners = sum(1 for a in ads if a["is_winner"])
    by_bucket_rows.append({
        "pipeline": pipeline, "competitor": slug, "bucket": "TOTAL",
        "ads": tot_ads, "winners": tot_winners, "win_ratio": win_ratio(tot_winners, tot_ads),
    })
    write_csv(derived / f"{slug}_by_bucket.csv",
              ["pipeline", "competitor", "bucket", "ads", "winners", "win_ratio"],
              by_bucket_rows)

    # raw count files — one row per distinct non-empty value, same way as rollup()
    def raw_counts(field: str) -> list[dict]:
        agg: dict[str, dict] = defaultdict(lambda: {"ads": 0, "winners": 0})
        for a in ads:
            k = (a.get(field) or "").strip()
            if not k:
                continue
            agg[k]["ads"] += 1
            if a["is_winner"]:
                agg[k]["winners"] += 1
        return [{"pipeline": pipeline, "competitor": slug, field: k,
                 "ads": v["ads"], "winners": v["winners"],
                 "win_ratio": win_ratio(v["winners"], v["ads"])}
                for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["ads"])]

    for field, fname in [
        ("presenter_type", f"{slug}_raw_presenter_counts.csv"),
        ("production_type", f"{slug}_raw_production_counts.csv"),
        ("device_format", f"{slug}_raw_format_counts.csv"),
    ]:
        write_csv(derived / fname,
                  ["pipeline", "competitor", field, "ads", "winners", "win_ratio"],
                  raw_counts(field))

    # ---- the locked 3-axis taxonomy views (blank/untagged values are skipped) ----
    #   Axis 1 = merged format ; Axis 2 = presenter_type (raw above) ; Axis 3 = message angle.
    for field, fname in [
        ("format_axis", f"{slug}_by_format_axis.csv"),       # Axis 1 (app-demo merge)
        ("message_angle", f"{slug}_by_angle.csv"),           # Axis 3 (NEW)
        ("split_screen_role", f"{slug}_by_split_role.csv"),  # split-screen sub-type
    ]:
        write_csv(derived / fname,
                  ["pipeline", "competitor", field, "ads", "winners", "win_ratio"],
                  raw_counts(field))

    # =====================================================================
    # OUTPUT 2: new_per_week (Q9)
    # =====================================================================
    # group debut week: min(first_seen) over a group's ads
    group_first: dict[str, Optional[date]] = {}
    for a in ads:
        gid = a["script_group_id"]
        if not gid:
            continue
        fs = a["first_seen"]
        if fs is None:
            continue
        if gid not in group_first or fs < group_first[gid]:
            group_first[gid] = fs
    group_debut_week = {gid: week_label(fs) for gid, fs in group_first.items() if fs}

    # format debut week: min(first_seen) over ads with that format
    format_first: dict[str, Optional[date]] = {}
    for a in ads:
        fmt = a["device_format"]
        if not fmt:
            continue
        fs = a["first_seen"]
        if fs is None:
            continue
        if fmt not in format_first or fs < format_first[fmt]:
            format_first[fmt] = fs
    format_debut_week = {fmt: week_label(fs) for fmt, fs in format_first.items() if fs}

    # per-week counters
    new_scripts_by_week: Counter = Counter()
    for wk in group_debut_week.values():
        new_scripts_by_week[wk] += 1
    new_formats_by_week: Counter = Counter()
    for wk in format_debut_week.values():
        new_formats_by_week[wk] += 1

    new_ads_by_week: Counter = Counter()
    winners_among_new_by_week: Counter = Counter()
    # B3: ad-level new-script vs reused-script. An ad runs a NEW script if its script
    # group debuts in the same week it first appeared; else it REUSES an existing
    # script. (new_ads counts ads regardless of script novelty; new_scripts counts
    # GROUPS, not ads — this is the missing ad-level split for Q6.)
    new_script_ads_by_week: Counter = Counter()
    reused_script_ads_by_week: Counter = Counter()
    for a in ads:
        if a["first_seen"] is None:
            continue
        wk = week_label(a["first_seen"])
        new_ads_by_week[wk] += 1
        if a["is_winner"]:
            winners_among_new_by_week[wk] += 1
        gid = a["script_group_id"]
        if gid:
            if group_debut_week.get(gid) == wk:
                new_script_ads_by_week[wk] += 1
            else:
                reused_script_ads_by_week[wk] += 1

    all_weeks = (set(new_scripts_by_week) | set(new_formats_by_week)
                 | set(new_ads_by_week))
    new_per_week_rows = []
    for wk in sorted(all_weeks):
        na = new_ads_by_week.get(wk, 0)
        win = winners_among_new_by_week.get(wk, 0)
        new_per_week_rows.append({
            "pipeline": pipeline, "competitor": slug, "week": wk,
            "new_scripts": new_scripts_by_week.get(wk, 0),
            "new_formats": new_formats_by_week.get(wk, 0),
            "new_ads": na,
            "new_script_ads": new_script_ads_by_week.get(wk, 0),
            "reused_script_ads": reused_script_ads_by_week.get(wk, 0),
            "winners_among_new": win,
            "win_ratio": win_ratio(win, na),
        })
    write_csv(derived / f"{slug}_new_per_week.csv",
              ["pipeline", "competitor", "week", "new_scripts", "new_formats",
               "new_ads", "new_script_ads", "reused_script_ads",
               "winners_among_new", "win_ratio"],
              new_per_week_rows)

    # =====================================================================
    # OUTPUT 3: replication_speed (+ summary) (Q10)
    # =====================================================================
    # group members keyed by script_group_id
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in ads:
        if a["script_group_id"]:
            groups[a["script_group_id"]].append(a)

    def _fs_key(a):
        # same tiebreak as script_cluster._fs: earliest first_seen, then smallest ad_id
        return (a["first_seen_raw"] or "9999", a["ad_id"])

    repl_rows = []
    days_by_type: dict[str, list[int]] = defaultdict(list)
    for gid, members in groups.items():
        # only groups with a replica (group_size > 1)
        gsize = max((m["group_size"] for m in members), default=len(members))
        if gsize <= 1 and len(members) <= 1:
            continue
        # identify original: variant_role == 'original', else earliest first_seen / smallest ad_id
        original = next((m for m in members if m["variant_role"] == "original"), None)
        if original is None:
            original = min(members, key=_fs_key)
        original_fs = original["first_seen"]
        for m in members:
            if m is original or m["ad_id"] == original["ad_id"]:
                continue
            replica_fs = m["first_seen"]
            if original_fs is not None and replica_fs is not None:
                days_to_replica = (replica_fs - original_fs).days
            else:
                days_to_replica = ""
            repl_rows.append({
                "pipeline": pipeline, "competitor": slug,
                "script_group_id": gid,
                "original_ad_id": original["ad_id"],
                "original_first_seen": original["first_seen_raw"],
                "replica_ad_id": m["ad_id"],
                "replication_type": m["replication_type"],
                "replica_first_seen": m["first_seen_raw"],
                "days_to_replica": days_to_replica,
                "original_is_winner": original["is_winner"],
                "replica_is_winner": m["is_winner"],
            })
            if days_to_replica != "":
                days_by_type[m["replication_type"] or "untyped"].append(days_to_replica)

    repl_rows.sort(key=lambda x: (x["script_group_id"],
                                  x["days_to_replica"] if x["days_to_replica"] != "" else 10 ** 9))
    write_csv(derived / f"{slug}_replication_speed.csv",
              ["pipeline", "competitor", "script_group_id", "original_ad_id",
               "original_first_seen", "replica_ad_id", "replication_type",
               "replica_first_seen", "days_to_replica", "original_is_winner",
               "replica_is_winner"],
              repl_rows)

    # summary stats per replication_type (+ ALL)
    def _stat_row(rtype: str, vals: list[int]) -> dict:
        if vals:
            return {
                "pipeline": pipeline, "competitor": slug, "replication_type": rtype,
                "n_replicas": len(vals),
                "median_days_to_replica": statistics.median(vals),
                "mean_days_to_replica": round(statistics.mean(vals), 1),
                "min_days_to_replica": min(vals),
                "max_days_to_replica": max(vals),
            }
        return {
            "pipeline": pipeline, "competitor": slug, "replication_type": rtype,
            "n_replicas": 0,
            "median_days_to_replica": "", "mean_days_to_replica": "",
            "min_days_to_replica": "", "max_days_to_replica": "",
        }

    repl_summary_rows = [_stat_row(rt, days_by_type[rt])
                         for rt in sorted(days_by_type)]
    all_vals = [v for vals in days_by_type.values() for v in vals]
    repl_summary_rows.append(_stat_row("ALL", all_vals))
    write_csv(derived / f"{slug}_replication_speed_summary.csv",
              ["pipeline", "competitor", "replication_type", "n_replicas",
               "median_days_to_replica", "mean_days_to_replica",
               "min_days_to_replica", "max_days_to_replica"],
              repl_summary_rows)

    # =====================================================================
    # OUTPUT 4: by_script_group (Q11)
    # =====================================================================
    by_group_rows = []
    for gid, members in groups.items():
        gsize = max((m["group_size"] for m in members), default=len(members))
        if gsize < len(members):
            gsize = len(members)
        n_ads = len(members)
        n_winners = sum(1 for m in members if m["is_winner"])
        rtypes = sorted({m["replication_type"] for m in members if m["replication_type"]})
        by_group_rows.append({
            "pipeline": pipeline, "competitor": slug,
            "script_group_id": gid, "group_size": gsize,
            "ads": n_ads, "winners": n_winners,
            "win_ratio": win_ratio(n_winners, n_ads),
            "replication_types": ";".join(rtypes),
        })
    by_group_rows.sort(key=lambda x: (-x["group_size"], x["script_group_id"]))
    write_csv(derived / f"{slug}_by_script_group.csv",
              ["pipeline", "competitor", "script_group_id", "group_size", "ads",
               "winners", "win_ratio", "replication_types"],
              by_group_rows)

    # =====================================================================
    # OUTPUT 5 (optional): daily_volume (Q1)
    # =====================================================================
    daily_rows = []
    stops_rows = []
    if history_rows:
        by_date: dict[str, set] = defaultdict(set)
        for r in history_rows:
            sd = (r.get("scrape_date") or "").strip()
            if not sd:
                continue
            by_date[sd].add(r["ad_id"])
        group_of = {a["ad_id"]: a["script_group_id"] for a in ads}
        dates = sorted(by_date)
        for i, sd in enumerate(dates):
            live = by_date[sd]
            ads_live = len(live)
            new_ads = sum(1 for a in live if first_seen_of.get(a, "") == sd)
            winners_live = sum(1 for a in live if verdict_of.get(a) in WINNER_VERDICTS)
            # B3 (daily): of the ads that first appeared today, how many run a NEW
            # script (their group debuted today) vs REUSE an existing one?
            new_script_ads = reused_script_ads = 0
            for a in live:
                if first_seen_of.get(a, "") != sd:
                    continue
                gid = group_of.get(a)
                if not gid:
                    continue
                if group_first.get(gid) == d(sd):
                    new_script_ads += 1
                else:
                    reused_script_ads += 1
            # B7: stop-events — ads present on the previous scrape but gone today.
            stopped = 0
            if i > 0:
                gone = by_date[dates[i - 1]] - live
                stopped = len(gone)
                for aid in sorted(gone):
                    stops_rows.append({
                        "pipeline": pipeline, "competitor": slug, "ad_id": aid,
                        "stopped_on": sd, "last_seen": dates[i - 1],
                        "first_seen": first_seen_of.get(aid, ""),
                    })
            daily_rows.append({
                "pipeline": pipeline, "competitor": slug, "scrape_date": sd,
                "ads_live": ads_live, "new_ads": new_ads,
                "new_script_ads": new_script_ads, "reused_script_ads": reused_script_ads,
                "stopped_ads": stopped,
                "winners_live": winners_live,
                "win_ratio": win_ratio(winners_live, ads_live),
            })
        write_csv(derived / f"{slug}_daily_volume.csv",
                  ["pipeline", "competitor", "scrape_date", "ads_live", "new_ads",
                   "new_script_ads", "reused_script_ads", "stopped_ads",
                   "winners_live", "win_ratio"],
                  daily_rows)
        write_csv(derived / f"{slug}_stops.csv",
                  ["pipeline", "competitor", "ad_id", "stopped_on", "last_seen",
                   "first_seen"],
                  stops_rows)

    # =====================================================================
    # OUTPUT 6: strategic_report.md
    # =====================================================================
    L: list[str] = []
    L.append(f"# Strategic view — {slug} ({pipeline})")
    L.append("")
    L.append(f"*Generated from {len(ads)} ads, latest {latest}.*")
    L.append("")
    L.append(CAVEAT)
    L.append("")

    # ---- Q1 Volume over time ----
    L.append("## Q1 Volume over time")
    L.append("")
    if daily_rows:
        L.append("Per scrape-date live volume (history.csv — one row per ad per scrape).")
        L.append("")
        L.append("| scrape_date | ads live | new | winners live | win ratio |")
        L.append("|---|--:|--:|--:|--:|")
        for r in daily_rows:
            L.append(f"| {r['scrape_date']} | {r['ads_live']} | {r['new_ads']} | "
                     f"{r['winners_live']} | {r['win_ratio']} |")
        L.append("")
        if len(daily_rows) < 3:
            L.append("*Only a couple of scrape dates so far, so daily volume is sparse; "
                     "it densifies as history accrues.*")
            L.append("")
    else:
        L.append("*No history log yet — see the weekly fallback in "
                 f"`{slug}_weekly.csv` / `{slug}_new_per_week.csv`. Daily volume "
                 "needs `analysis/history/` rows.*")
        L.append("")

    # ---- Q2 Format/bucket mix ----
    L.append("## Q2 Format / bucket mix")
    L.append("")
    L.append("| bucket | ads | winners | win ratio |")
    L.append("|---|--:|--:|--:|")
    for r in by_bucket_rows:
        L.append(f"| {r['bucket']} | {r['ads']} | {r['winners']} | {r['win_ratio']} |")
    L.append("")
    L.append(f"*split-screen ads (captured both above and in "
             f"`{slug}_raw_format_counts.csv`): {ss_ads}.*")
    L.append("")

    # ---- Format axis (merged) + Message angle (Axis 3) ----
    L.append("## Format mix (Axis 1 — merged)")
    L.append("")
    L.append("| format | ads | winners | win ratio |")
    L.append("|---|--:|--:|--:|")
    for r in raw_counts("format_axis"):
        L.append(f"| {r['format_axis']} | {r['ads']} | {r['winners']} | {r['win_ratio']} |")
    L.append("")

    L.append("## Message angle (Axis 3)")
    L.append("")
    angle_rows = raw_counts("message_angle")
    if angle_rows:
        L.append("| message_angle | ads | winners | win ratio |")
        L.append("|---|--:|--:|--:|")
        for r in angle_rows:
            L.append(f"| {r['message_angle']} | {r['ads']} | {r['winners']} | {r['win_ratio']} |")
        L.append("")
        n_price = sum(1 for a in ads if a["has_price_offer"])
        L.append(f"*Price / offer hook present in {n_price} of {len(ads)} ads. "
                 f"Split-screen role split in `{slug}_by_split_role.csv`.*")
        L.append("")
    else:
        L.append("*No `message_angle` tags yet — captured by transcribe_tag going "
                 "forward (re-tag) or back-filled into the sidecars.*")
        L.append("")

    # ---- Q5 AI vs human production ----
    L.append("## Q5 AI vs human production")
    L.append("")
    ai_heavy = {"ads": 0, "winners": 0}
    for b in ("ai_plus_ai", "ai_plus_human"):
        v = bucket_agg.get(b)
        if v:
            ai_heavy["ads"] += v["ads"]
            ai_heavy["winners"] += v["winners"]
    collapsed = [
        ("AI-heavy (ai_plus_ai + ai_plus_human)", ai_heavy["ads"], ai_heavy["winners"]),
        ("human_only", bucket_agg.get("human_only", {}).get("ads", 0),
         bucket_agg.get("human_only", {}).get("winners", 0)),
        ("paper_translation", bucket_agg.get("paper_translation", {}).get("ads", 0),
         bucket_agg.get("paper_translation", {}).get("winners", 0)),
        ("other", bucket_agg.get("other", {}).get("ads", 0),
         bucket_agg.get("other", {}).get("winners", 0)),
    ]
    L.append("| production class | ads | win ratio |")
    L.append("|---|--:|--:|")
    for name, n, w in collapsed:
        L.append(f"| {name} | {n} | {win_ratio(w, n)} |")
    L.append("")

    # ---- Q9 New scripts/formats per week ----
    L.append("## Q9 New scripts / formats per week")
    L.append("")
    if new_per_week_rows:
        L.append("| week | new scripts | new formats | new ads | winners | win ratio |")
        L.append("|---|--:|--:|--:|--:|--:|")
        for r in new_per_week_rows:
            L.append(f"| {r['week']} | {r['new_scripts']} | {r['new_formats']} | "
                     f"{r['new_ads']} | {r['winners_among_new']} | {r['win_ratio']} |")
        L.append("")
    else:
        L.append("*No dated ads to derive weekly debut counts.*")
        L.append("")

    # ---- Q10 Replication speed ----
    L.append("## Q10 Replication speed")
    L.append("")
    L.append("Days from a script group's original to each replica (median per type).")
    L.append("")
    L.append("| replication_type | n replicas | median days | mean days | min | max |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for r in repl_summary_rows:
        L.append(f"| {r['replication_type']} | {r['n_replicas']} | "
                 f"{r['median_days_to_replica']} | {r['mean_days_to_replica']} | "
                 f"{r['min_days_to_replica']} | {r['max_days_to_replica']} |")
    L.append("")
    fastest = None
    for r in repl_rows:
        if r["days_to_replica"] == "":
            continue
        if fastest is None or r["days_to_replica"] < fastest["days_to_replica"]:
            fastest = r
    if fastest is not None:
        L.append(f"*Fastest replicated group: `{fastest['script_group_id']}` — replica "
                 f"`{fastest['replica_ad_id']}` ({fastest['replication_type'] or 'untyped'}) "
                 f"appeared {fastest['days_to_replica']} day(s) after the original "
                 f"`{fastest['original_ad_id']}`.*")
        L.append("")
    else:
        L.append("*No usable replica timing yet (no group with >1 dated member).*")
        L.append("")

    # ---- Q11 Per-script performance ----
    L.append("## Q11 Per-script performance (top 10 groups by size)")
    L.append("")
    if by_group_rows:
        L.append("| script_group_id | group size | ads | winners | win ratio | replication_types |")
        L.append("|---|--:|--:|--:|--:|---|")
        for r in by_group_rows[:10]:
            L.append(f"| {r['script_group_id']} | {r['group_size']} | {r['ads']} | "
                     f"{r['winners']} | {r['win_ratio']} | {r['replication_types'] or '—'} |")
        L.append("")
    else:
        L.append("*No script groups yet (run script_cluster.py).*")
        L.append("")

    # ---- Q3/Q4/Q6/Q7/Q8 pointers ----
    L.append("## Q3 / Q4 / Q6 / Q7 / Q8 — where to look")
    L.append("")
    L.append(f"- **Q3 / Q4 (language mix & cadence):** see `{slug}_by_language.csv` "
             f"and `{slug}_weekly.csv`.")
    L.append(f"- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) "
             f"counts:** see `{slug}_by_replication.csv` and the new "
             f"`{slug}_by_script_group.csv` (per-group `replication_types` set).")
    L.append("")
    L.append("**Q8 residual limitation:** `visual_variant` is detected purely from a "
             "`device_format` change between a replica and its group original. The "
             "transcript-tagged format enum is coarse (app-screencast, skit-narrative, "
             "listicle-montage, split-screen, text-on-screen-only, other), so a script "
             "re-shot with genuinely different visuals but tagged into the SAME format "
             "bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is "
             "therefore a LOWER BOUND keyed on format-category change, not a pixel-level "
             "visual diff — no frame/image comparison is performed (offline, no API). Use "
             f"`{slug}_by_script_group.csv` to eyeball groups whose members share a "
             "format but differ visually.")
    L.append("")

    reports = root / "analysis" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    md_out = reports / f"{latest}_{slug}_{pipeline}_strategic.md"
    md_out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  -> {md_out}")

    print(f"{slug}: strategic views -> {derived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
