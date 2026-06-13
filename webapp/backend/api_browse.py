"""Browse/read API: competitors, ad listing with filters/facets, ad detail."""
from __future__ import annotations

import json
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query

from . import db
from .auth import require_user
from .config import FACEBOOK_DIR
from .data import catalog

router = APIRouter(dependencies=[Depends(require_user)])

# Statuses hidden from the main Library listing (still visible on the Pipeline board).
HIDDEN_FROM_LIBRARY = {"approved", "in_production", "shipped"}


def _csv(v: str | None) -> list[str]:
    return [s for s in (v or "").split(",") if s]


def _tracker_map() -> dict[tuple, dict]:
    return {(r["pipeline"], r["competitor"], r["ad_id"]): dict(r)
            for r in db.query("SELECT * FROM tracker")}


def _active_jobs() -> dict[tuple, dict]:
    rows = db.query("SELECT * FROM jobs WHERE status IN ('queued','running','interrupted')")
    return {(r["pipeline"], r["competitor"], r["ad_id"]): dict(r) for r in rows}


def _attach_status(ads: list[dict]) -> list[dict]:
    tracker, jobs = _tracker_map(), _active_jobs()
    out = []
    for a in ads:
        key = (a["pipeline"], a["competitor"], a["ad_id"])
        t, j = tracker.get(key), jobs.get(key)
        out.append({**a,
                    "status": (t or {}).get("status") or "",
                    "claimed_by": (t or {}).get("claimed_by") or "",
                    "job": {"id": j["id"], "status": j["status"],
                            "current_step": j["current_step"]} if j else None})
    return out


_VERDICT_ORDER = {"strong_winner": 0, "winner": 1, "undecided": 2, "new": 3, "loser": 4}


def _fold_groups(pipeline: str, ads: list[dict]) -> tuple[list[dict], int]:
    """Collapse a filtered+sorted flat ad list into script-group tiles, in order.

    The first member seen per group is the representative — it both matches the
    active filters and carries the best value of the active sort, so groups
    inherit the flat ordering for free. Empty script_group_id → singleton.
    Returns (groups, count of ungrouped singleton ads).
    """
    cat = catalog()
    by_key: dict[tuple, dict] = {}
    folded: list[dict] = []
    for a in ads:
        gid = a["script_group_id"]
        key = (a["competitor"], gid or f"~{a['ad_id']}")
        bucket = by_key.get(key)
        if bucket is None:
            bucket = {"gid": gid, "members": []}
            by_key[key] = bucket
            folded.append(bucket)
        bucket["members"].append(a)
    groups, ungrouped = [], 0
    for bucket in folded:
        gid, members = bucket["gid"], bucket["members"]
        rep = members[0]
        if not gid:
            ungrouped += 1
        meta = (cat.group_meta(pipeline, rep["competitor"], gid) if gid
                else {"size": 1, "languages_total": 1 if rep["language"] else 0,
                      "winners_total": int(rep["verdict"] in ("strong_winner", "winner"))})
        lang_counts: dict[str, int] = {}
        statuses: dict[str, int] = {}
        for m in members:
            if m["language"]:
                lang_counts[m["language"]] = lang_counts.get(m["language"], 0) + 1
            if m["status"]:
                statuses[m["status"]] = statuses.get(m["status"], 0) + 1
        max_run = max(members, key=lambda m: m["run_days"] or 0)
        groups.append({
            "script_group_id": gid,
            "representative": rep,
            "members_matching": len(members),
            "group_size_total": meta["size"],
            "languages": sorted(lang_counts, key=lambda l: -lang_counts[l]),
            "languages_total": meta["languages_total"],
            "max_run_days": max_run["run_days"] or 0,
            "max_run_days_is_lower_bound": max_run["run_days_is_lower_bound"],
            "best_verdict": min((m["verdict"] for m in members),
                                key=lambda v: _VERDICT_ORDER.get(v, 9)),
            "winners": sum(1 for m in members
                           if m["verdict"] in ("strong_winner", "winner")),
            "live_count": sum(1 for m in members if not m["is_retired"]),
            "statuses": statuses,
            "member_ids": [m["ad_id"] for m in members],
        })
    return groups, ungrouped


@router.get("/api/competitors")
def competitors():
    return {"competitors": catalog().competitors(), "data_as_of": catalog().loaded_at}


@router.get("/api/ads")
def list_ads(
    pipeline: str = "facebook",
    competitor: str = "",
    verdict: str = "",
    media_type: str = "",
    language: str = "",
    device_format: str = "",
    page_name: str = "",
    platform_os: str = "",
    retired: str = "any",
    generated: str = "any",
    status: str = "",
    has_media: bool = True,
    has_transcript: str = "any",
    min_run_days: int | None = None,
    first_seen_days: int | None = None,
    q: str = "",
    group: str = "",
    sort: str = "run_days",
    order: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
):
    # Materialize the FULL catalog-filtered+sorted set (no pagination yet), because
    # our workflow status/claim live in SQLite and must be joined + filtered BEFORE
    # paginating — otherwise total is wrong and matches outside page 1 are missed.
    full = catalog().list_ads(
        pipeline=pipeline, competitor=competitor, verdict=_csv(verdict),
        media_type=_csv(media_type), language=_csv(language),
        device_format=_csv(device_format), page_name=_csv(page_name),
        platform_os=platform_os, retired=retired, generated=generated,
        has_media=has_media, has_transcript=has_transcript,
        min_run_days=min_run_days, first_seen_days=first_seen_days,
        q=q, sort=sort, order=order, page=1, page_size=10 ** 9)
    ads = _attach_status(full["ads"])
    if status:
        wanted = set(_csv(status))
        none_wanted = "none" in wanted
        ads = [a for a in ads
               if a["status"] in wanted or (none_wanted and not a["status"])]
    else:
        # Main listing hides ads already moved to production (Approved onward) —
        # they're done being "picked"; the Pipeline board still shows them.
        ads = [a for a in ads if a["status"] not in HIDDEN_FROM_LIBRARY]

    if group == "script":
        # One tile per script: pagination counts groups; facets stay ad-level.
        groups, ungrouped = _fold_groups(pipeline, ads)
        start = (page - 1) * page_size
        return {"total": len(groups), "total_ads": len(ads),
                "ungrouped_ads": ungrouped,
                "page": page, "page_size": page_size,
                "facets": full["facets"], "os_coverage": full["os_coverage"],
                "ads": [],
                "groups": groups[start:start + page_size],
                "data_as_of": catalog().loaded_at}

    total = len(ads)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "facets": full["facets"], "os_coverage": full["os_coverage"],
            "ads": ads[start:start + page_size],
            "data_as_of": catalog().loaded_at}


@router.get("/api/groups/{pipeline}/{slug}/{gid}")
def group_detail(pipeline: str, slug: str, gid: str):
    """All members of a script group, unfiltered — the drawer's full-truth view
    (includes Approved+ members the main grid hides)."""
    cat = catalog()
    members = cat.group_members(pipeline, slug, gid)
    if not members:
        raise HTTPException(404, "Script group not found")
    meta = cat.group_meta(pipeline, slug, gid)
    return {"script_group_id": gid, "group_size_total": meta["size"],
            "languages_total": meta["languages_total"],
            "winners_total": meta["winners_total"],
            "members": _attach_status(members)}


@router.get("/api/ads/{pipeline}/{slug}/{ad_id}")
def ad_detail(pipeline: str, slug: str, ad_id: str):
    ad = catalog().get(pipeline, slug, ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    cat = catalog()
    full = _attach_status([ad])[0]
    full["transcript"] = cat.transcript(pipeline, slug, ad_id)
    full["rank_timeline"] = cat.rank_timeline(pipeline, slug, ad_id)
    full["related"] = _attach_status(cat.related(ad))
    full["group_total"] = (cat.group_meta(pipeline, slug, ad["script_group_id"])["size"]
                           if ad["script_group_id"] else 0)
    key = (pipeline, slug, ad_id)
    trow = db.query_one("SELECT verified_languages, tts_verified_languages FROM tracker "
                        "WHERE pipeline=? AND competitor=? AND ad_id=?", key)
    try:
        full["verified_languages"] = (json.loads(trow["verified_languages"])
                                      if trow and trow["verified_languages"] else {})
    except Exception:
        full["verified_languages"] = {}
    try:
        full["tts_verified_languages"] = (json.loads(trow["tts_verified_languages"])
                                          if trow and trow["tts_verified_languages"] else {})
    except Exception:
        full["tts_verified_languages"] = {}
    full["activity"] = [dict(r) for r in db.query(
        "SELECT ts, who, action, detail FROM activity "
        "WHERE pipeline=? AND competitor=? AND ad_id=? ORDER BY id DESC LIMIT 50", key)]
    last_job = db.query_one(
        "SELECT * FROM jobs WHERE pipeline=? AND competitor=? AND ad_id=? "
        "ORDER BY id DESC LIMIT 1", key)
    full["latest_job"] = dict(last_job) if last_job else None
    return full


@router.get("/api/ads/{pipeline}/{slug}/{ad_id}/estimate")
def estimate(pipeline: str, slug: str, ad_id: str):
    if pipeline != "facebook":
        return {"eligible": False, "reason": "Script generation is Facebook-only for now."}
    ad = catalog().get(pipeline, slug, ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    if not ad["media_url"]:
        return {"eligible": False, "reason": "This ad has no media in R2 to work from."}
    try:
        proc = subprocess.run(
            ["python3.13", "scripts/estimate_step4_cost.py",
             "--competitor", slug, "--ids", ad_id, "--json"],
            cwd=FACEBOOK_DIR, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Cost estimate timed out")
    if proc.returncode != 0:
        raise HTTPException(502, f"Estimator failed: {proc.stderr[-400:]}")
    est = json.loads(proc.stdout)
    if not est.get("estimates"):
        # estimator only lists "candidates" (rows still missing docs)
        if ad["has_docs"] or ad["has_gdocs"]:
            return {"eligible": False, "reason": "Docs already exist for this ad.",
                    "already_generated": True}
        return {"eligible": False, "reason": "Ad not eligible (no candidate row)."}
    row = est["estimates"][0]
    spent = db.query_one(
        "SELECT COALESCE(SUM(cost_estimate_usd),0) AS s FROM jobs "
        "WHERE status NOT IN ('failed','cancelled') AND created_at >= date('now','start of month')")
    return {"eligible": True, "cost_usd": round(row.get("cost_total", 0), 3),
            "media_type": row.get("media_type"), "duration_s": row.get("duration_s"),
            "scenes": row.get("scenes"), "notes": row.get("assumption_notes"),
            "wall_clock": "5–20 min",
            "month_to_date_usd": round(spent["s"] if spent else 0, 2)}
