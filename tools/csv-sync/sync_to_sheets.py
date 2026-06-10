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
sys.path.insert(0, str(REPO / "analysis" / "scripts"))
import _gsheets  # noqa: E402
from r2_utils import load_env  # noqa: E402
# Verdict thresholds come straight from the metric computation, so the Legend can never
# drift from the actual tuning (if someone retunes compute_rank_metrics, the Legend follows).
import compute_rank_metrics as _crm  # noqa: E402

_STRONG_DAYS = _crm.STRONG_WINNER_RUN_DAYS      # 45 — strong_winner longevity bar
_WINNER_DAYS = _crm.WINNER_RUN_DAYS             # 15 — winner longevity bar
_TOP25_GATE = _crm.TOP25_GATE                   # 0.5 — share of sightings needed in the top 25%
_RANK_ABS = _crm.RANK_GATE_ABS                  # 100 — absolute best-rank bar
_RANK_PCT = int(_crm.RANK_GATE_PCT * 100)       # 10 — or top-N% of the page, whichever is wider
_NEW_DAYS = _crm.NEW_AGE_DAYS                   # 7 — "new" age window

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
# Legend definitions are deliberately LONG and fully objective — every threshold is a real
# number imported from compute_rank_metrics.py, with examples. Background for several of them:
# we scrape each competitor's Ad Library repeatedly (every few days); "rank" = the ad's position
# in its page's ad list at that scrape (1 = top). Meta gives no spend/impressions, so rank +
# longevity are our revealed-preference proxy for "the competitor keeps funding this and Meta
# keeps surfacing it".
COLUMN_DEFS = {
    "Competitor": "Which competitor this ad belongs to (one row per ad, all competitors stacked in the "
                  "same tab — filter this column to focus on one).",
    "Ad ID": "The ad's id in Meta's Ad Library — the stable key used to join every dataset in this "
             "project (master, analysis, transcripts, docs).",
    "Ad Library Link": "Opens this exact ad in Meta's public Ad Library (live page — shows the ad only "
                       "while it's still running).",
    "Verdict": f"The outcome tier, judged in this order: "
               f"• strong_winner = ran MORE than {_STRONG_DAYS} days AND was inside its page's top 25% in at "
               f"least {int(_TOP25_GATE*100)}% of all the scrapes it appeared in (see 'Sustained Top 25%?'). "
               f"• winner = ran {_WINNER_DAYS}+ days AND its best-ever rank reached the page's top band (see "
               f"'Hit Top Ranks?'). "
               f"• loser = vanished from the latest scrape without ever meeting a winner bar. "
               f"• new = first seen within the last {_NEW_DAYS} days and seen in at most 2 scrapes so far — too "
               f"early to judge. "
               f"• undecided = still running but hasn't met a winner bar yet. "
               f"IMPORTANT: winners KEEP their verdict after the ad stops (they get Status=retired, never "
               f"demoted) — so 'strong_winner + retired' means a proven ad that finished its run.",
    "Status": "live = this ad appears in the competitor's MOST RECENT scrape (still running as of our last "
              "check). retired = it was present in an earlier scrape but is gone from the latest one — the "
              "competitor stopped it (or Meta did).",
    "Current Rank": "The ad's position in its page's ad list at the LATEST scrape it appeared in (1 = the "
                    "very top). Lower number = Meta is surfacing it harder. For a retired ad this is its "
                    "final rank before it disappeared.",
    "Best Rank": "The best (lowest) position this ad EVER reached across all scrapes — its peak. An ad "
                 "currently at rank 200 with Best Rank 3 was once a top performer and is fading.",
    "Worst Rank": "The worst (highest) position observed across all scrapes — the floor of its range.",
    "Median Rank": "The middle of all its observed ranks — its typical position, robust to one-off spikes.",
    "% Time in Top 25%": "Of ALL the scrapes this ad appeared in, the fraction where it ranked inside the "
                         "TOP 25% of its page's ads. Example: a page running 100 ads → top 25% = ranks 1–25; "
                         "if we saw the ad in 8 scrapes and it was ranked 1–25 in 6 of them, this = 0.75. "
                         "1.0 = every single time we looked, it was in the top quarter. "
                         f"The strong_winner bar needs ≥ {_TOP25_GATE} (at least {int(_TOP25_GATE*100)}% of its "
                         f"observed life near the top).",
    "Days Running": "Calendar days from the ad's Meta-reported START date to the most recent scrape that "
                    "still contained it. Example: started 2026-03-01, last seen 2026-04-15 → 45 days. This "
                    "is the longevity signal: competitors keep paying only for ads that work. "
                    f"(Bars: winner needs {_WINNER_DAYS}+, strong_winner needs more than {_STRONG_DAYS}.) If Meta "
                    "gave no start date, we count from when WE first saw it and flag 'Days = Minimum?'.",
    "Days = Minimum?": "TRUE = Meta didn't report a start date, so Days Running is counted from OUR first "
                       "sighting — the ad certainly ran AT LEAST this long, probably longer. Also drops "
                       "'Verdict Confidence' to low for winners.",
    "Start Date": "The ad's start date as reported by Meta in the Ad Library.",
    "First Seen": "Date of the FIRST of our scrapes that contained this ad (when it entered our tracking).",
    "Last Seen": "Date of the MOST RECENT of our scrapes that contained it. If this equals the latest "
                 "scrape date, the ad is live.",
    "Scrapes Seen": "How many of our scrape snapshots contained this ad. We scrape each competitor "
                    "repeatedly (typically every few days), so an ad with Scrapes Seen = 6 survived 6 "
                    "checkpoints. Counts observations — 'Days Running' measures calendar time instead.",
    "Weeks Seen": "How many DISTINCT calendar weeks it was seen in (deduplicates several scrapes landing "
                  "in the same week). Weeks Seen = 5 means it was alive across 5 different weeks.",
    "Language": "The ad's language, detected by AI from the actual audio + on-screen text during "
                "enrichment (Hindi, Tamil, Marathi, English, …). Code-mixed ads get their dominant language.",
    "Ad Format": "The visual container, classified by AI from the video: split-screen (teacher + learner "
                 "panels), skit-narrative (acted story), talking-head, app-screencast (app demo), "
                 "pen-and-paper, listicle-montage, …",
    "Presenter": "Who fronts the ad: ai-avatar-only (animated/AI character), human-only, ai+human (both, "
                 "e.g. AI teacher + human learner), voiceover-only (no on-screen presenter), none.",
    "Production": "How the creative was made: human-recorded (filmed people), AI-generated (fully "
                  "synthetic), or mixed (filmed + AI elements).",
    "Message Angle": "The persuasion angle of the script, classified by AI from the transcript: "
                     "speak-correctly (fixes your English mistakes), fear-shame (embarrassment → triumph), "
                     "social-proof (others succeeded), habit-aspiration (daily practice → fluency), "
                     "translation-practice, understand-cant-speak, feature-demo, …",
    "Script Reuse": "How this ad's script relates to other ads' scripts (from transcript clustering): "
                    "original = the earliest ad of a script family that later got copied · "
                    "translation_replica = the SAME script translated into another language · "
                    "exact_replica = near-verbatim re-run · reworded/character/visual variants = same "
                    "script lightly reworked · unique = no other ad shares this script. "
                    "Competitor insight: translation_replicas typically outperform exact_replicas.",
    "Script Group": "Id of the script family — every ad sharing (near-)identical script text gets the "
                    "same group id. Filter by one id to see all clones of one script across languages.",
    "Original/Replica": "This ad's role INSIDE its script group: the original (first/earliest version) "
                        "or a replica (a later copy).",
    "Price Offer?": "TRUE = the ad's script/on-screen text mentions a price, discount, trial offer or "
                    "₹-amount (detected by AI from the transcript). Useful for spotting discount-led vs "
                    "value-led creative strategies.",
    "Media": "Video or Image (the ad's creative type).",
    "Ad Copy (first 150)": "The first 150 characters of the ad's primary text (the caption above the "
                           "creative). Full text lives in the master CSV in git.",
    "Video": "The archived copy of the ad's video in our R2 storage (Meta's own CDN links expire within "
             "days — this one is permanent).",
    "Supernova Rewrite Doc": "Our Supernova-voice rewrite of this ad — a collaborative Google Doc "
                             "(script re-pitched with Supernova's payload + Miss Nova, scene by scene, "
                             "with regenerated India-cast imagery). Open it to review/edit/assign.",
    "Competitor Analysis Doc": "The scene-by-scene breakdown of the competitor's original ad (visuals, "
                               "transcript, on-screen text per scene) — a collaborative Google Doc.",
    "Platform": "Which ads pipeline the row comes from: facebook (Meta Ad Library) or google "
                "(Google Ads Transparency Center).",
    "Page ID": "Numeric id of the Facebook page the ad runs under (one competitor can run several pages).",
    "Page Name": "Name of the Facebook page the ad runs under.",
    "In Latest Scrape?": "TRUE = the ad appears in the competitor's most recent scrape (= Status live). "
                         "The raw flag behind 'Status'.",
    "Retired?": "TRUE = no longer present in the latest scrape (= Status retired). Note: a retired "
                "winner KEEPS its winner verdict.",
    "Page Ad Count": "How many ads this ad's page runs in total (the largest count we ever observed). "
                     "Context for rank: rank 30 on a 600-ad page = top 5% (excellent); rank 30 on a "
                     "40-ad page = bottom half.",
    "Hit Top Ranks?": f"TRUE = the ad's best-ever rank reached its page's top band, defined as: rank ≤ "
                      f"{_RANK_ABS}, OR within the top {_RANK_PCT}% of the page's ads — whichever is more "
                      f"generous (the {_RANK_PCT}% rule matters only for pages running more than "
                      f"{int(_RANK_ABS/(_RANK_PCT/100))} ads). This is the quality bar for 'winner' "
                      f"(combined with {_WINNER_DAYS}+ days running).",
    "Sustained Top 25%?": f"TRUE = '% Time in Top 25%' is at least {_TOP25_GATE} — i.e. in at least "
                          f"{int(_TOP25_GATE*100)}% of all the scrapes where this ad appeared, it ranked inside "
                          f"its page's top 25%. Being there once isn't enough; this requires holding the top "
                          f"quarter for at least half its observed life. The consistency bar for "
                          f"'strong_winner' (combined with {_STRONG_DAYS}+ days running).",
    "Low-Impression Flag": "TRUE = Meta showed its 'low impressions' warning on this ad in at least one "
                           "scrape (Meta's signal that the ad got little delivery).",
    "Verdict Confidence": "high = the verdict rests on solid data (real start date, so Days Running is "
                          "exact). low = something was inferred: the start date was missing (Days = "
                          "Minimum? TRUE), or a 'loser' verdict inferred purely from the ad's absence in "
                          "the latest scrape.",
    "Duration (s)": "The video's length in seconds (measured by AI during transcription).",
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
