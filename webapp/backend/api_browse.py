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
    retired: str = "any",
    generated: str = "any",
    status: str = "",
    has_media: bool = True,
    has_transcript: str = "any",
    min_run_days: int | None = None,
    first_seen_days: int | None = None,
    q: str = "",
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
        device_format=_csv(device_format), retired=retired, generated=generated,
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
    total = len(ads)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "facets": full["facets"], "ads": ads[start:start + page_size],
            "data_as_of": catalog().loaded_at}


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
    key = (pipeline, slug, ad_id)
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
