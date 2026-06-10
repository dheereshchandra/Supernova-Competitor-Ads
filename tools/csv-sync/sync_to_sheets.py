#!/usr/bin/env python3
"""
Sync local competitor-ad data into ONE Google Sheet ("Supernova Competitor Master"), twice daily.

Builds two curated, cross-competitor, one-row-per-(competitor, ad_id) views and UPSERTS them into a
persistent spreadsheet in the Shared Drive (never rewrites; preserves team-added columns + row order):

  • "Overview" — the decision-scan (~21 cols): verdict, is_live, rank, run_days, language, format,
    angle, replication, has_price_offer, ad_copy, + links (video / Supernova-rewrite doc / analysis doc).
  • "Analysis" — the full per-ad pivot dataset (the enriched CSV + message_angle/duration_s/has_price_offer).

Each view is a JOIN: enriched CSV (the per-ad spine) ⋈ master CSV (links/copy, canonical creative)
⋈ transcript sidecar (angle/duration/price). Reuses the Google-Docs service account + Shared Drive.

Usage:
    python3.13 tools/csv-sync/sync_to_sheets.py --all
    python3.13 tools/csv-sync/sync_to_sheets.py --competitor mysivi --dry-run   # offline, no Sheets calls
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "facebook" / "scripts"))
import _gsheets  # noqa: E402
from r2_utils import load_env  # noqa: E402

MASTER_DIR = REPO / "facebook" / "master"
ENRICHED_DIR = REPO / "analysis" / "derived" / "facebook"
TRANSCRIPT_DIR = REPO / "analysis" / "enrichment" / "facebook" / "transcripts"
SIDECAR_PATH = HERE / "sheet_id.json"

# slugs that are partial/scratch masters, not real competitors
EXCLUDE = ("_newly_added", "_step4", "_top20", "_new_only", "review", "_run_summary", "_gdoctest")

# ---------------------------------------------------------------------------
# Sheet-facing column labels (short but self-explanatory) + their definitions.
# Internal CSV column names stay untouched — this mapping exists ONLY at the
# sheet layer. The Legend tab in the spreadsheet is generated from COLUMN_DEFS.
# ---------------------------------------------------------------------------

# Overview tab — internal key -> display label, in scannable order.
OVERVIEW_COLS = [
    ("competitor", "Competitor"),
    ("ad_id", "Ad ID"),
    ("meta_ad_link", "Ad Library Link"),
    ("verdict", "Verdict"),
    ("is_live", "Status"),
    ("rank", "Current Rank"),
    ("best_rank", "Best Rank"),
    ("pct_top25", "% Time in Top 25%"),
    ("run_days", "Days Running"),
    ("started", "Start Date"),
    ("language", "Language"),
    ("format", "Ad Format"),
    ("presenter", "Presenter"),
    ("angle", "Message Angle"),
    ("replication", "Script Reuse"),
    ("has_price_offer", "Price Offer?"),
    ("media", "Media"),
    ("ad_copy", "Ad Copy (first 150)"),
    ("video", "Video"),
    ("supernova_rewrite", "Supernova Rewrite Doc"),
    ("competitor_analysis", "Competitor Analysis Doc"),
]

# Analysis tab — internal enriched-CSV key -> display label, in order.
ANALYSIS_COLS = [
    ("competitor", "Competitor"),
    ("ad_id", "Ad ID"),
    ("pipeline", "Platform"),
    ("page_id", "Page ID"),
    ("page_name", "Page Name"),
    ("media_type", "Media"),
    ("language", "Language"),
    ("presenter_type", "Presenter"),
    ("device_format", "Ad Format"),
    ("production_type", "Production"),
    ("script_group_id", "Script Group"),
    ("replication_type", "Script Reuse"),
    ("variant_role", "Original/Replica"),
    ("first_seen", "First Seen"),
    ("last_seen", "Last Seen"),
    ("times_seen", "Scrapes Seen"),
    ("weeks_seen", "Weeks Seen"),
    ("ad_start_date", "Start Date"),
    ("run_days", "Days Running"),
    ("run_days_is_lower_bound", "Days = Minimum?"),
    ("best_page_rank", "Best Rank"),
    ("worst_page_rank", "Worst Rank"),
    ("median_page_rank", "Median Rank"),
    ("current_page_rank", "Current Rank"),
    ("present_latest", "In Latest Scrape?"),
    ("is_retired", "Retired?"),
    ("page_count", "Page Ad Count"),
    ("frac_top_25", "% Time in Top 25%"),
    ("rank_gate", "Hit Top Ranks?"),
    ("top25_gate", "Sustained Top 25%?"),
    ("low_impression_ever", "Low-Impression Flag"),
    ("verdict", "Verdict"),
    ("verdict_confidence", "Verdict Confidence"),
    ("message_angle", "Message Angle"),
    ("duration_s", "Duration (s)"),
    ("has_price_offer", "Price Offer?"),
]

# Label -> plain-English definition (drives the Legend tab; shared across tabs).
COLUMN_DEFS = {
    "Competitor": "Which competitor this ad belongs to.",
    "Ad ID": "Meta Ad Library id of the ad (the join key everywhere).",
    "Ad Library Link": "Opens the live ad in Meta's Ad Library.",
    "Verdict": "Outcome tier: strong_winner (ran long AND sustained the page's top 25%), winner (ran long AND hit top ranks), loser (dropped out without winning), new (just appeared), undecided. Winners keep their verdict even after retiring.",
    "Status": "live = ad appears in the most recent scrape; retired = it has dropped out.",
    "Current Rank": "Position in its page's ad list at the latest scrape it was seen in (1 = top).",
    "Best Rank": "Best (lowest) rank it ever reached across all scrapes.",
    "Worst Rank": "Worst (highest) rank observed across all scrapes.",
    "Median Rank": "Median rank across all scrapes.",
    "% Time in Top 25%": "Of all the scrapes this ad was seen in, the share where it ranked in the TOP 25% of its page's ads (1.0 = always near the top).",
    "Days Running": "Calendar days from the ad's start date to the last time we saw it.",
    "Days = Minimum?": "TRUE = the start date was missing, so Days Running is counted from when WE first saw it — the real figure is at least this.",
    "Start Date": "The ad's start date as reported by Meta.",
    "First Seen": "Date of the first scrape that included this ad.",
    "Last Seen": "Date of the most recent scrape that included this ad.",
    "Scrapes Seen": "How many scrape snapshots this ad appeared in.",
    "Weeks Seen": "How many distinct calendar weeks it was seen in.",
    "Language": "Detected language of the ad.",
    "Ad Format": "The visual container: split-screen, skit-narrative, talking-head, app-screencast, pen-and-paper, …",
    "Presenter": "Who fronts the ad: ai-avatar, human, ai+human, voiceover-only, none.",
    "Production": "How it was made: human-recorded, AI-generated, or mixed.",
    "Message Angle": "The persuasion angle: speak-correctly, fear-shame, social-proof, habit-aspiration, translation-practice, …",
    "Script Reuse": "How this ad's script relates to others: original, translation_replica (same script translated), exact_replica, reworded, or unique.",
    "Script Group": "Id of the cluster of ads sharing (near-)identical scripts — same number = same script family.",
    "Original/Replica": "This ad's role inside its script group (the original vs a replica).",
    "Price Offer?": "TRUE = the ad mentions a price / discount / offer.",
    "Media": "Video or Image.",
    "Ad Copy (first 150)": "First 150 characters of the ad's primary text.",
    "Video": "The archived video file (R2 link).",
    "Supernova Rewrite Doc": "Our Supernova-voice rewrite of this ad — collaborative Google Doc.",
    "Competitor Analysis Doc": "Scene-by-scene breakdown of the competitor ad — collaborative Google Doc.",
    "Platform": "Which ads pipeline: facebook or google.",
    "Page ID": "Facebook page id the ad runs under.",
    "Page Name": "Facebook page name the ad runs under.",
    "In Latest Scrape?": "TRUE = the ad appears in the competitor's most recent scrape.",
    "Retired?": "TRUE = no longer present in the latest scrape.",
    "Page Ad Count": "How many ads its page runs in total (largest observed) — context for rank.",
    "Hit Top Ranks?": "TRUE = its best rank reached the page's top band — the eligibility bar for 'winner'.",
    "Sustained Top 25%?": "TRUE = '% Time in Top 25%' cleared the threshold — the eligibility bar for 'strong_winner'.",
    "Low-Impression Flag": "TRUE = Meta flagged this ad as low-impression in at least one scrape.",
    "Verdict Confidence": "high = run dates are solid; low = inferred (missing start date, or a loser inferred from absence).",
    "Duration (s)": "Video length in seconds.",
}

TRANSCRIPT_FIELDS = ["message_angle", "duration_s", "has_price_offer"]
KEY_COLS = ("Competitor", "Ad ID")


def read_csv(path: pathlib.Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames or [])


def safe_int(v, default=0):
    try:
        return int(str(v).strip() or default)
    except (ValueError, TypeError):
        return default


def truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def load_transcript(comp: str, ad_id: str) -> dict:
    p = TRANSCRIPT_DIR / comp / f"{ad_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def master_by_ad(comp: str) -> dict:
    """ad_library_id -> the canonical-creative master row (min version_index, creative_index)."""
    path = MASTER_DIR / f"{comp}.csv"
    if not path.exists():
        return {}
    rows, _ = read_csv(path)
    best = {}
    for m in rows:
        aid = (m.get("ad_library_id") or "").strip()
        if not aid:
            continue
        vk = (safe_int(m.get("version_index")), safe_int(m.get("creative_index_in_ad")))
        if aid not in best or vk < best[aid][0]:
            best[aid] = (vk, m)
    return {k: v[1] for k, v in best.items()}


def build_overview_row(comp: str, e: dict, m: dict, t: dict) -> dict:
    is_live = "live" if truthy(e.get("present_latest")) else ("retired" if truthy(e.get("is_retired")) else "")
    return {
        "competitor": e.get("competitor") or comp,
        "ad_id": (e.get("ad_id") or "").strip(),
        "meta_ad_link": m.get("ad_library_url", ""),
        "verdict": e.get("verdict", ""),
        "is_live": is_live,
        "rank": e.get("current_page_rank", ""),
        "best_rank": e.get("best_page_rank", ""),
        "pct_top25": e.get("frac_top_25", ""),
        "run_days": e.get("run_days", ""),
        "started": m.get("ad_start_date", "") or e.get("ad_start_date", ""),
        "language": e.get("language", ""),
        "format": e.get("device_format", ""),
        "presenter": e.get("presenter_type", ""),
        "angle": t.get("message_angle", ""),
        "replication": e.get("replication_type", ""),
        "has_price_offer": t.get("has_price_offer", ""),
        "media": m.get("ad_media_type", "") or e.get("media_type", ""),
        "ad_copy": (m.get("ad_primary_text", "") or "")[:150],
        "video": m.get("r2_public_url", ""),
        "supernova_rewrite": m.get("supernova_rewrite_gdoc_url", ""),
        "competitor_analysis": m.get("competitor_analysis_gdoc_url", ""),
    }


def build_analysis_row(e: dict, t: dict) -> dict:
    row = dict(e)
    row["message_angle"] = t.get("message_angle", "")
    row["duration_s"] = t.get("duration_s", "")
    row["has_price_offer"] = t.get("has_price_offer", "")
    return row


def relabel(row: dict, cols: list) -> dict:
    """Re-key an internal-name row dict to its sheet display labels."""
    return {label: row.get(key, "") for key, label in cols}


def build_views(comp: str):
    """Return (overview_rows, analysis_rows) for one competitor, or ([],[]) if no enriched CSV."""
    enriched_path = ENRICHED_DIR / f"{comp}_enriched.csv"
    if not enriched_path.exists():
        return [], []
    enriched, _ = read_csv(enriched_path)
    masters = master_by_ad(comp)
    overview, analysis = [], []
    for e in enriched:
        aid = (e.get("ad_id") or "").strip()
        if not aid:
            continue
        m = masters.get(aid, {})
        t = load_transcript(comp, aid)
        overview.append(relabel(build_overview_row(comp, e, m, t), OVERVIEW_COLS))
        analysis.append(relabel(build_analysis_row(e, t), ANALYSIS_COLS))
    return overview, analysis


OVERVIEW_HEADER = [label for _, label in OVERVIEW_COLS]
ANALYSIS_HEADER = [label for _, label in ANALYSIS_COLS]


def legend_rows() -> list:
    """The Legend tab content: which tabs each column appears on + its meaning."""
    on_tab = {}
    for _, label in OVERVIEW_COLS:
        on_tab.setdefault(label, []).append("Overview")
    for _, label in ANALYSIS_COLS:
        on_tab.setdefault(label, []).append("Analysis")
    rows = [["Column", "On Tab(s)", "What it means"]]
    seen = set()
    for label in OVERVIEW_HEADER + ANALYSIS_HEADER:
        if label in seen:
            continue
        seen.add(label)
        rows.append([label, " + ".join(on_tab[label]), COLUMN_DEFS.get(label, "")])
    return rows


def _cells_equal(a, b) -> bool:
    sa, sb = str(a).strip(), str(b).strip()
    if sa == sb:
        return True
    try:
        return abs(float(sa) - float(sb)) < 1e-9
    except (ValueError, TypeError):
        return False


def upsert_tab(sheets, ssid: str, title: str, header: list, rows: list, key_cols, dry_run: bool) -> dict:
    values = _gsheets.read_tab_values(sheets, ssid, title) if not dry_run else []
    sheet_header = list(values[0]) if values else list(header)
    header_changed = not values
    for col in header:
        if col not in sheet_header:
            sheet_header.append(col)
            header_changed = True

    col_idx = {c: sheet_header.index(c) for c in header}
    width = max(col_idx.values()) + 1
    key_pos = [sheet_header.index(k) for k in key_cols if k in sheet_header]

    key_to_row = {}
    for i, r in enumerate(values[1:]):
        key = tuple((str(r[p]).strip() if p < len(r) else "") for p in key_pos)
        key_to_row.setdefault(key, i + 2)

    appended = updated = unchanged = 0
    data_updates, appends = [], []
    for row in rows:
        desired = [""] * len(sheet_header)
        for c in header:
            desired[col_idx[c]] = _gsheets.sanitize_cell(row.get(c, ""))
        key = tuple(str(row.get(k, "")).strip() for k in key_cols)
        rn = key_to_row.get(key)
        if rn is None:
            appends.append(desired[:width])
            appended += 1
        else:
            existing = values[rn - 1]  # values[0] is the header; sheet row N = values[N-1]
            same = all(_cells_equal(existing[col_idx[c]] if col_idx[c] < len(existing) else "",
                                    desired[col_idx[c]]) for c in header)
            if same:
                unchanged += 1
            else:
                rng = f"{_gsheets.a1_quote_title(title)}!A{rn}:{_gsheets.col_to_a1(width - 1)}{rn}"
                data_updates.append({"range": rng, "values": [desired[:width]]})
                updated += 1

    if not dry_run:
        if header_changed:
            _gsheets.write_row(sheets, ssid, title, 1, sheet_header)
        if data_updates:
            _gsheets.batch_update_values(sheets, ssid, data_updates)
        if appends:
            _gsheets.append_rows(sheets, ssid, title, appends)
    return {"appended": appended, "updated": updated, "unchanged": unchanged}


def write_sidecar(ssid: str) -> None:
    url = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
    tmp = SIDECAR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"spreadsheet_id": ssid, "url": url,
                               "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                              indent=2))
    os.replace(tmp, SIDECAR_PATH)


def discover_competitors() -> list:
    out = []
    for p in sorted(ENRICHED_DIR.glob("*_enriched.csv")):
        slug = p.name[:-len("_enriched.csv")]
        if any(x in slug for x in EXCLUDE):
            continue
        out.append(slug)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitor")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="One-time: delete + recreate the Overview/Analysis tabs (e.g. after a "
                         "header rename). Same spreadsheet/URL; team notes on those tabs are lost.")
    args = ap.parse_args()

    os.chdir(REPO)  # launchd cwd-agnostic
    comps = [args.competitor] if args.competitor else discover_competitors()
    if not comps:
        sys.exit("[error] no competitors with enriched CSVs in analysis/derived/facebook/")

    overview_all, analysis_all = [], []
    for comp in comps:
        ov, an = build_views(comp)
        if not an:
            print(f"  [{comp}] SKIP — no enriched CSV")
            continue
        print(f"  [{comp}] built {len(an)} ads")
        overview_all += ov
        analysis_all += an
    if not analysis_all:
        sys.exit("[error] nothing to sync")

    if args.dry_run:
        print(f"\n[dry-run] would sync — Overview: {len(overview_all)} rows · Analysis: {len(analysis_all)} rows")
        print(f"[dry-run] Overview header ({len(OVERVIEW_HEADER)} cols): {OVERVIEW_HEADER}")
        print(f"[dry-run] Analysis header ({len(ANALYSIS_HEADER)} cols): {ANALYSIS_HEADER}")
        print(f"[dry-run] sample Overview row: {json.dumps(overview_all[0], ensure_ascii=False)[:400]}")
        return 0

    env = load_env(REPO / ".env")
    drive, sheets = _gsheets.build_services(env)
    ssid, is_new = _gsheets.ensure_spreadsheet(drive, sheets, env, SIDECAR_PATH)
    if is_new or not SIDECAR_PATH.exists():
        write_sidecar(ssid)
    tabs = _gsheets.get_tabs(sheets, ssid)

    # Legend first (also guarantees the spreadsheet always has ≥1 tab during --rebuild).
    _gsheets.ensure_tab(sheets, ssid, "Legend", tabs)
    leg = legend_rows()
    _gsheets.with_backoff(lambda: sheets.spreadsheets().values().update(
        spreadsheetId=ssid,
        range=f"{_gsheets.a1_quote_title('Legend')}!A1",
        valueInputOption="RAW", body={"values": leg}).execute())

    if args.rebuild:
        for t in ("Overview", "Analysis"):
            _gsheets.delete_tab(sheets, ssid, t, tabs)
        print("  [rebuild] Overview/Analysis tabs dropped — reseeding with fresh headers")

    _gsheets.ensure_tab(sheets, ssid, "Overview", tabs)
    _gsheets.ensure_tab(sheets, ssid, "Analysis", tabs)
    if "Sheet1" in tabs:
        _gsheets.delete_tab(sheets, ssid, "Sheet1", tabs)

    ov = upsert_tab(sheets, ssid, "Overview", OVERVIEW_HEADER, overview_all, KEY_COLS, False)
    an = upsert_tab(sheets, ssid, "Analysis", ANALYSIS_HEADER, analysis_all, KEY_COLS, False)
    print(f"\nDONE — https://docs.google.com/spreadsheets/d/{ssid}/edit")
    print(f"  Overview: {ov}")
    print(f"  Analysis: {an}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
