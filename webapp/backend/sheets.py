"""Production Tracker tab mirror in the "Supernova Competitor Master" Sheet.

SQLite is the source of truth; the Sheet is a synced view the team can read
anywhere. Two columns are TEAM-OWNED — "Notes" and "Final Video Link" — the
syncer reads them back into SQLite before upserting and never overwrites a
remote edit with an older local value.

Reuses tools/csv-sync/_gsheets.py (same service account + Shared Drive +
spreadsheet sidecar as the existing csv-sync job). csv-sync owns the Legend/
Overview/Analysis tabs; this module owns exactly one tab: "Production Tracker".
All writes are debounced + best-effort: a Sheets outage never breaks the app.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import threading
import traceback

from . import db
from .config import REPO, settings
from .data import catalog

sys.path.insert(0, str(REPO / "tools" / "csv-sync"))

TAB = "Production Tracker"
SIDECAR = REPO / "tools" / "csv-sync" / "sheet_id.json"

HEADERS = ["Status", "Competitor", "Platform", "Ad ID", "Page", "Verdict",
           "Run Days", "Video (R2)", "Ad Library", "Supernova Script (GDoc)",
           "Competitor Analysis (GDoc)", "Script (HTML)", "Open in Ad Studio",
           "Requested By", "Claimed By", "Created", "Script Ready",
           "Last Update", "Notes", "Final Video Link"]
KEY_COLS = ("Competitor", "Platform", "Ad ID")
TEAM_COLS = ("Notes", "Final Video Link")

STATUS_LABEL = {
    "shortlisted": "Shortlisted", "generating": "Generating…",
    "script_ready": "Script ready", "in_edit": "In edit", "approved": "Approved",
    "in_production": "In production", "shipped": "Shipped",
    "dismissed": "Dismissed", "dropped": "Dropped",
}

_dirty = threading.Event()
_services = None  # (sheets, ssid) cached


def mark_dirty() -> None:
    _dirty.set()


def _connect():
    global _services
    if _services is not None:
        return _services
    from _gsheets import build_services, ensure_spreadsheet, ensure_tab, get_tabs
    env = settings().env
    drive, sheets_svc = build_services(env)
    ssid, _ = ensure_spreadsheet(drive, sheets_svc, env, SIDECAR)
    tabs = get_tabs(sheets_svc, ssid)
    ensure_tab(sheets_svc, ssid, TAB, tabs)
    _services = (sheets_svc, ssid)
    return _services


def _studio_link(row: dict) -> str:
    base = settings().env.get("STUDIO_PUBLIC_URL", "").rstrip("/")
    path = f"/ad/{row['pipeline']}/{row['competitor']}/{row['ad_id']}"
    return f"{base}{path}" if base else path


def _json_col(t: dict, col: str) -> dict:
    try:
        return json.loads(t[col]) if t.get(col) else {}
    except Exception:
        return {}


def _langs_in_tracker() -> list[str]:
    """Union of localized languages across all tracker rows → the per-language
    column set (auto-expanding: a new language adds its columns on next sync)."""
    langs: set[str] = set()
    for r in db.query("SELECT localization_gdoc_urls, verified_languages FROM tracker "
                      "WHERE localization_gdoc_urls IS NOT NULL "
                      "   OR verified_languages IS NOT NULL"):
        t = dict(r)
        langs.update(_json_col(t, "localization_gdoc_urls").keys())
        langs.update(_json_col(t, "verified_languages").keys())
    return sorted(langs)


def _lang_headers(langs: list[str]) -> list[str]:
    out = []
    for lang in langs:
        out += [f"{lang} Script (GDoc)", f"{lang} Verified"]
    return out


def _row_dict(t: dict, langs: list[str]) -> dict[str, str]:
    ad = catalog().get(t["pipeline"], t["competitor"], t["ad_id"]) or {}
    d = {
        "Status": STATUS_LABEL.get(t["status"], t["status"]),
        "Competitor": t["competitor"], "Platform": t["pipeline"], "Ad ID": t["ad_id"],
        "Page": ad.get("page_name", ""), "Verdict": ad.get("verdict", ""),
        "Run Days": str(ad.get("run_days") or ""),
        "Video (R2)": ad.get("media_url", ""),
        "Ad Library": ad.get("ad_library_url", ""),
        "Supernova Script (GDoc)": t["rewrite_gdoc_url"] or ad.get("rewrite_gdoc_url", ""),
        "Competitor Analysis (GDoc)": t["analysis_gdoc_url"] or ad.get("analysis_gdoc_url", ""),
        "Script (HTML)": t["rewrite_html_url"] or ad.get("rewrite_html_url", ""),
        "Open in Ad Studio": _studio_link(t),
        "Requested By": t["requested_by"] or "", "Claimed By": t["claimed_by"] or "",
        "Created": t["created_at"] or "", "Script Ready": t["script_ready_at"] or "",
        "Last Update": t["updated_at"] or "",
        "Notes": t["notes"] or "", "Final Video Link": t["final_video_url"] or "",
    }
    links = _json_col(t, "localization_gdoc_urls")
    verified = _json_col(t, "verified_languages")
    for lang in langs:
        d[f"{lang} Script (GDoc)"] = links.get(lang, "")
        v = verified.get(lang) or {}
        d[f"{lang} Verified"] = (f"✓ {v.get('verified_by', '')}".strip()
                                 if v.get("verified") else ("pending" if lang in links else ""))
    return d


def _sync_once() -> None:
    """Read tab → merge team-owned cols back → upsert all tracker rows."""
    from _gsheets import (append_rows, batch_update_values, col_to_a1,
                          read_tab_values, sanitize_cell, with_backoff)
    sheets_svc, ssid = _connect()
    langs = _langs_in_tracker()
    wanted = HEADERS + _lang_headers(langs)
    values = with_backoff(lambda: read_tab_values(sheets_svc, ssid, TAB))
    if not values:  # brand-new tab: write the header
        with_backoff(lambda: append_rows(sheets_svc, ssid, TAB, [wanted]))
        values = [wanted]
    header = values[0]
    # auto-expand: append any missing columns (e.g. a newly localized language)
    missing = [h for h in wanted if h not in header]
    if missing:
        header = header + missing
        rng = f"'{TAB}'!A1:{col_to_a1(len(header) - 1)}1"
        with_backoff(lambda: batch_update_values(
            sheets_svc, ssid, [{"range": rng, "values": [header]}]))
    idx = {h: i for i, h in enumerate(header)}
    key_idx = [idx[k] for k in KEY_COLS if k in idx]
    remote: dict[tuple, tuple[int, list]] = {}
    for rn, row in enumerate(values[1:], start=2):
        row = row + [""] * (len(header) - len(row))
        key = tuple(row[i] for i in key_idx)
        remote[key] = (rn, row)

    # 1) read-back of team-owned columns into SQLite
    for r in db.query("SELECT * FROM tracker"):
        key = (r["competitor"], r["pipeline"], r["ad_id"])
        hit = remote.get(key)
        if not hit:
            continue
        _, row = hit
        notes = row[idx["Notes"]] if "Notes" in idx else ""
        final = row[idx["Final Video Link"]] if "Final Video Link" in idx else ""
        if notes != (r["notes"] or "") and notes:
            db.execute("UPDATE tracker SET notes=? WHERE pipeline=? AND competitor=? AND ad_id=?",
                       (notes, r["pipeline"], r["competitor"], r["ad_id"]))
        if final != (r["final_video_url"] or "") and final:
            db.execute("UPDATE tracker SET final_video_url=? "
                       "WHERE pipeline=? AND competitor=? AND ad_id=?",
                       (final, r["pipeline"], r["competitor"], r["ad_id"]))

    # 2) upsert every tracker row (update changed, append new) — cells serialized
    #    in the REMOTE header's order, so team column rearrangements survive
    updates, appends = [], []
    for r in db.query("SELECT * FROM tracker"):
        t = dict(r)
        d = _row_dict(t, langs)
        vals = [sanitize_cell(d.get(h, "")) for h in header]
        key = (t["competitor"], t["pipeline"], t["ad_id"])
        hit = remote.get(key)
        if hit is None:
            appends.append(vals)
        else:
            rn, existing = hit
            if existing[:len(vals)] != vals:
                rng = f"'{TAB}'!A{rn}:{col_to_a1(len(vals) - 1)}{rn}"
                updates.append({"range": rng, "values": [vals]})
    if updates:
        with_backoff(lambda: batch_update_values(sheets_svc, ssid, updates))
    if appends:
        with_backoff(lambda: append_rows(sheets_svc, ssid, TAB, appends))


async def _syncer():
    """Debounced single-flight syncer + 5-minute reconciliation."""
    loop = asyncio.get_running_loop()
    while True:
        triggered = await loop.run_in_executor(None, _dirty.wait, 300)
        _dirty.clear()
        if triggered:
            await asyncio.sleep(5)  # coalesce bursts
            _dirty.clear()
        if not db.query_one("SELECT 1 FROM tracker LIMIT 1"):
            continue
        try:
            await loop.run_in_executor(None, _sync_once)
        except Exception:
            print("[sheets] tracker sync failed:\n" + traceback.format_exc()[-800:])


def seed_from_masters() -> int:
    """First boot: ads that already have docs from past batch runs enter the
    tracker as script_ready (imported) so nobody re-pays for them."""
    if db.query_one("SELECT 1 FROM tracker WHERE imported=1 LIMIT 1"):
        return 0
    n = 0
    cat = catalog()
    cat.reload_if_stale()
    res = cat.list_ads(pipeline="facebook", generated="yes", has_media=False,
                       page_size=10000)
    for ad in res["ads"]:
        if not (ad["has_docs"] or ad["has_gdocs"]):
            continue
        cur = db.execute(
            """INSERT INTO tracker (pipeline, competitor, ad_id, status, requested_by,
                                    verdict_at_shortlist, imported, rewrite_gdoc_url,
                                    analysis_gdoc_url, rewrite_html_url,
                                    script_ready_at)
               VALUES (?,?,?,'script_ready','batch import',?,1,?,?,?,datetime('now'))
               ON CONFLICT (pipeline, competitor, ad_id) DO NOTHING""",
            (ad["pipeline"], ad["competitor"], ad["ad_id"], ad["verdict"],
             ad["rewrite_gdoc_url"], ad["analysis_gdoc_url"], ad["rewrite_html_url"]))
        n += cur.rowcount if cur.rowcount > 0 else 0
    if n:
        mark_dirty()
    return n


def enabled() -> bool:
    """Live-Sheet writes are opt-in (STUDIO_SHEET_SYNC=1) so dev instances
    never touch the team's spreadsheet."""
    return settings().env.get("STUDIO_SHEET_SYNC", "") == "1"


def start_syncer(app) -> None:
    seeded = seed_from_masters()
    if seeded:
        print(f"[sheets] seeded {seeded} previously-generated ads as script_ready (imported)")
    if not enabled():
        print("[sheets] live Sheet sync DISABLED (set STUDIO_SHEET_SYNC=1 to enable)")
        return
    asyncio.get_running_loop().create_task(_syncer())
