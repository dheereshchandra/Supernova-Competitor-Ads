"""Job + tracker API: enqueue generation, watch progress, manage workflow status."""
from __future__ import annotations

import json
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, jobs
from .auth import require_user
from .config import FACEBOOK_DIR, settings
from .data import catalog

router = APIRouter()

TRACKER_STATUSES = ("shortlisted", "generating", "script_ready", "in_edit",
                    "approved", "in_production", "shipped", "dismissed", "dropped")
ACTIVE = ("queued", "running", "interrupted")
FALLBACK_FORCE_COST = 0.35  # estimator lists only doc-less candidates


def _log(pipeline, slug, ad_id, who, action, detail=""):
    db.execute(
        "INSERT INTO activity (pipeline, competitor, ad_id, who, action, detail) "
        "VALUES (?,?,?,?,?,?)", (pipeline, slug, ad_id, who, action, detail))


def _ensure_tracker(pipeline, slug, ad_id, status, who):
    ad = catalog().get(pipeline, slug, ad_id) or {}
    db.execute(
        """INSERT INTO tracker (pipeline, competitor, ad_id, status, requested_by,
                                verdict_at_shortlist)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (pipeline, competitor, ad_id)
           DO UPDATE SET status=excluded.status, updated_at=datetime('now')""",
        (pipeline, slug, ad_id, status, who, ad.get("verdict", "")))


# ---------------- jobs ----------------

class JobBody(BaseModel):
    pipeline: str
    competitor: str
    ad_id: str
    force: bool = False


def _job_payload(r: dict, queue_ids: list[int]) -> dict:
    if r.get("kind") == "pipeline":
        from .pipeline import PIPELINE_STEPS
        steps = PIPELINE_STEPS
    else:
        steps = jobs.steps_payload(r.get("media_type") or "Video")
    keys = [s["key"] for s in steps]
    cur = r.get("current_step")
    return {**{k: r.get(k) for k in (
        "id", "kind", "pipeline", "competitor", "ad_id", "status", "current_step",
        "requested_by", "created_at", "started_at", "finished_at",
        "cost_estimate_usd", "error", "stderr_tail", "rewrite_gdoc_url",
        "analysis_gdoc_url", "rewrite_html_url", "needs_push")},
        "steps": steps,
        "step_index": keys.index(cur) if cur in keys else None,
        "queue_position": queue_ids.index(r["id"]) + 1 if r["id"] in queue_ids else None,
    }


@router.post("/api/jobs", status_code=201)
def create_job(body: JobBody, user: str = Depends(require_user)):
    if body.pipeline != "facebook":
        raise HTTPException(422, "Script generation is Facebook-only for now")
    ad = catalog().get(body.pipeline, body.competitor, body.ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    if not ad["media_url"]:
        raise HTTPException(422, "This ad has no media in R2 to work from")
    active = db.query_one(
        f"SELECT id FROM jobs WHERE pipeline=? AND competitor=? AND ad_id=? "
        f"AND status IN {ACTIVE}", (body.pipeline, body.competitor, body.ad_id))
    if active:
        raise HTTPException(409, f"A run for this ad is already in flight (job #{active['id']})")
    if (ad["has_docs"] or ad["has_gdocs"]) and not body.force:
        raise HTTPException(409, "Docs already exist for this ad — open them, or force-regenerate")

    # cost gate: real estimate, then per-job + per-day caps
    cost = FALLBACK_FORCE_COST
    try:
        proc = subprocess.run(
            ["python3.13", "scripts/estimate_step4_cost.py", "--competitor",
             body.competitor, "--ids", body.ad_id, "--json"],
            cwd=FACEBOOK_DIR, capture_output=True, text=True, timeout=120)
        est = json.loads(proc.stdout[proc.stdout.index("{"):])
        if est.get("estimates"):
            cost = est["estimates"][0].get("cost_total", cost)
    except Exception:
        pass
    cfg = settings()
    if cost > cfg.max_job_cost:
        raise HTTPException(422, f"Estimated ${cost:.2f} exceeds the per-job cap (${cfg.max_job_cost:.0f})")
    spent = db.query_one(
        "SELECT COALESCE(SUM(cost_estimate_usd),0) AS s FROM jobs "
        "WHERE status NOT IN ('failed','cancelled') AND date(created_at)=date('now')")
    if (spent["s"] or 0) + cost > cfg.max_daily_cost:
        raise HTTPException(429, f"Daily spend cap reached (${cfg.max_daily_cost:.0f}) — try tomorrow "
                                 f"or ask the operator to raise STUDIO_MAX_DAILY_COST")

    cur = db.execute(
        "INSERT INTO jobs (pipeline, competitor, ad_id, media_type, requested_by, "
        "force_regen, cost_estimate_usd) VALUES (?,?,?,?,?,?,?)",
        (body.pipeline, body.competitor, body.ad_id, ad["media_type"], user,
         int(body.force), cost))
    job_id = cur.lastrowid
    _ensure_tracker(body.pipeline, body.competitor, body.ad_id, "generating", user)
    _log(body.pipeline, body.competitor, body.ad_id, user, "generate",
         f"queued job #{job_id} (~${cost:.2f})")
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    return {"job_id": job_id}


@router.get("/api/jobs")
def list_jobs(scope: str = "recent", _user: str = Depends(require_user)):
    if scope == "active":
        rows = db.query(f"SELECT * FROM jobs WHERE status IN {ACTIVE} ORDER BY id")
    elif scope == "all":
        rows = db.query("SELECT * FROM jobs ORDER BY id DESC")
    else:
        rows = db.query("SELECT * FROM jobs ORDER BY id DESC LIMIT 50")
    queue_ids = [r["id"] for r in db.query(
        "SELECT id FROM jobs WHERE status='queued' ORDER BY id")]
    return {"jobs": [_job_payload(dict(r), queue_ids) for r in rows]}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, _user: str = Depends(require_user)):
    r = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not r:
        raise HTTPException(404, "Job not found")
    queue_ids = [x["id"] for x in db.query(
        "SELECT id FROM jobs WHERE status='queued' ORDER BY id")]
    payload = _job_payload(dict(r), queue_ids)
    payload["events"] = [dict(e) for e in db.query(
        "SELECT ts, step, line FROM job_events WHERE job_id=? "
        "ORDER BY id DESC LIMIT 100", (job_id,))][::-1]
    return payload


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, user: str = Depends(require_user)):
    r = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not r:
        raise HTTPException(404, "Job not found")
    if r["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, f"Job is {r['status']} — nothing to retry")
    db.execute("UPDATE jobs SET status='queued', error=NULL, finished_at=NULL WHERE id=?",
               (job_id,))
    _log(r["pipeline"], r["competitor"], r["ad_id"], user, "retry", f"job #{job_id}")
    return {"ok": True}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, user: str = Depends(require_user)):
    r = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not r:
        raise HTTPException(404, "Job not found")
    if r["status"] == "queued":
        db.execute("UPDATE jobs SET status='cancelled', finished_at=datetime('now') "
                   "WHERE id=? AND status='queued'", (job_id,))
    elif r["status"] == "running":
        jobs.request_cancel(job_id)  # honored between steps
    else:
        raise HTTPException(409, f"Job is {r['status']}")
    _log(r["pipeline"], r["competitor"], r["ad_id"], user, "cancel", f"job #{job_id}")
    return {"ok": True}


# ---------------- pipeline (full data-update run) ----------------

class PipelineBody(BaseModel):
    pipeline: str
    competitor: str


@router.get("/api/pipeline/estimate")
def pipeline_estimate(pipeline: str, competitor: str, _user: str = Depends(require_user)):
    from .pipeline import estimate_cost
    if pipeline not in ("facebook", "google"):
        raise HTTPException(422, "pipeline must be facebook or google")
    return estimate_cost(pipeline, competitor)


@router.post("/api/pipeline/run", status_code=201)
def pipeline_run(body: PipelineBody, user: str = Depends(require_user)):
    from .pipeline import estimate_cost
    if body.pipeline not in ("facebook", "google"):
        raise HTTPException(422, "pipeline must be facebook or google")
    est = estimate_cost(body.pipeline, body.competitor)
    if not est.get("eligible"):
        raise HTTPException(422, est.get("reason", "Not eligible"))
    # one pipeline run per competitor at a time; the serial worker handles the rest
    active = db.query_one(
        f"SELECT id FROM jobs WHERE kind='pipeline' AND pipeline=? AND competitor=? "
        f"AND status IN {ACTIVE}", (body.pipeline, body.competitor))
    if active:
        raise HTTPException(409, f"A data update for {body.competitor} is already running (job #{active['id']})")
    cfg = settings()
    cost = est.get("cost_usd", 0)
    if cost > cfg.max_daily_cost:
        raise HTTPException(422, f"Estimated ${cost:.2f} exceeds the cap (${cfg.max_daily_cost:.0f}) — "
                                 f"raise STUDIO_MAX_DAILY_COST or enrich in smaller batches")
    cur = db.execute(
        "INSERT INTO jobs (kind, pipeline, competitor, ad_id, requested_by, cost_estimate_usd) "
        "VALUES ('pipeline', ?, ?, '(full-run)', ?, ?)",
        (body.pipeline, body.competitor, user, cost))
    job_id = cur.lastrowid
    _log(body.pipeline, body.competitor, "(full-run)", user, "pipeline_run",
         f"queued data update (~${cost:.2f}, {est.get('backlog_videos', 0)} videos)")
    return {"job_id": job_id}


# ---------------- tracker ----------------

class TrackerPatch(BaseModel):
    status: str | None = None
    claim: bool | None = None
    notes: str | None = None
    final_video_url: str | None = None


@router.get("/api/tracker")
def tracker(_user: str = Depends(require_user)):
    rows = []
    for r in db.query("SELECT * FROM tracker ORDER BY updated_at DESC"):
        d = dict(r)
        ad = catalog().get(d["pipeline"], d["competitor"], d["ad_id"]) or {}
        d["ad"] = {k: ad.get(k) for k in ("page_name", "verdict", "run_days",
                                          "media_url", "thumb_url", "ad_text")}
        d["verdict_drift"] = bool(d["verdict_at_shortlist"] and ad
                                  and ad.get("verdict") != d["verdict_at_shortlist"])
        rows.append(d)
    return {"rows": rows}


@router.patch("/api/tracker/{pipeline}/{slug}/{ad_id}")
def patch_tracker(pipeline: str, slug: str, ad_id: str, body: TrackerPatch,
                  user: str = Depends(require_user)):
    if body.status and body.status not in TRACKER_STATUSES:
        raise HTTPException(422, f"Unknown status {body.status}")
    row = db.query_one("SELECT * FROM tracker WHERE pipeline=? AND competitor=? AND ad_id=?",
                       (pipeline, slug, ad_id))
    if row is None:
        if not body.status:
            raise HTTPException(404, "No tracker row yet — set a status first")
        _ensure_tracker(pipeline, slug, ad_id, body.status, user)
        _log(pipeline, slug, ad_id, user, body.status, "")
    else:
        sets, params = ["updated_at=datetime('now')"], []
        if body.status and body.status != row["status"]:
            sets.append("status=?"); params.append(body.status)
            _log(pipeline, slug, ad_id, user, body.status,
                 f"{row['status']} → {body.status}")
        if body.claim is not None:
            sets.append("claimed_by=?"); params.append(user if body.claim else None)
            _log(pipeline, slug, ad_id, user, "claim" if body.claim else "unclaim", "")
        if body.notes is not None:
            sets.append("notes=?"); params.append(body.notes[:2000])
        if body.final_video_url is not None:
            sets.append("final_video_url=?"); params.append(body.final_video_url[:500])
            if body.final_video_url:
                _log(pipeline, slug, ad_id, user, "final_video", body.final_video_url[:200])
        db.execute(f"UPDATE tracker SET {', '.join(sets)} "
                   "WHERE pipeline=? AND competitor=? AND ad_id=?",
                   (*params, pipeline, slug, ad_id))
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    out = dict(db.query_one("SELECT * FROM tracker WHERE pipeline=? AND competitor=? AND ad_id=?",
                            (pipeline, slug, ad_id)))
    return out
