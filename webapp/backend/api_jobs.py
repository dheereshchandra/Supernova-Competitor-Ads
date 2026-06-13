"""Job + tracker API: enqueue generation, watch progress, manage workflow status."""
from __future__ import annotations

import datetime
import json
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db, jobs
from .auth import require_user
from .config import FACEBOOK_DIR, inr, settings
from .data import catalog

router = APIRouter()

TRACKER_STATUSES = ("shortlisted", "generating", "script_ready", "in_edit",
                    "approved", "in_production", "shipped", "dismissed", "dropped")
# awaiting_confirm = a pipeline run paused after the free scrape, waiting for the
# user to approve the (now-exact) enrichment cost. Treated as in-flight.
ACTIVE = ("queued", "running", "interrupted", "awaiting_confirm")
FALLBACK_FORCE_COST = 0.10  # force-regen of an already-doc'd ad (estimator lists only doc-less candidates). Text-only now — decompose+rewrite; image generation moved to a separate step.


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
        steps = jobs.steps_payload(r.get("media_type") or "Video", r.get("kind") or "generate")
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
        # post-scrape enrichment count+cost, shown on the awaiting_confirm prompt
        "enrich": (json.loads(r["estimate_json"])
                   if r.get("kind") == "pipeline" and r.get("estimate_json") else None),
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
        raise HTTPException(422, f"Estimated {inr(cost)} exceeds the per-job cap ({inr(cfg.max_job_cost)})")
    spent = db.query_one(
        "SELECT COALESCE(SUM(cost_estimate_usd),0) AS s FROM jobs "
        "WHERE status NOT IN ('failed','cancelled') AND date(created_at)=date('now')")
    if (spent["s"] or 0) + cost > cfg.max_daily_cost:
        raise HTTPException(429, f"Daily spend cap reached ({inr(cfg.max_daily_cost)}) — try tomorrow "
                                 f"or ask the operator to raise STUDIO_MAX_DAILY_COST")

    cur = db.execute(
        "INSERT INTO jobs (pipeline, competitor, ad_id, media_type, requested_by, "
        "force_regen, cost_estimate_usd) VALUES (?,?,?,?,?,?,?)",
        (body.pipeline, body.competitor, body.ad_id, ad["media_type"], user,
         int(body.force), cost))
    job_id = cur.lastrowid
    _ensure_tracker(body.pipeline, body.competitor, body.ad_id, "generating", user)
    _log(body.pipeline, body.competitor, body.ad_id, user, "generate",
         f"queued job #{job_id} (~{inr(cost)})")
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    return {"job_id": job_id}


# ---------------- localization (replicate an English master into N languages) ----------------

SUPPORTED_LANGUAGES = ("Hindi", "Telugu", "Tamil", "Marathi", "Kannada", "Malayalam",
                       "Bengali", "Gujarati", "Assamese", "Punjabi")
LOCALIZE_COST_PER_LANG = 0.02  # Flash translate + safety audit; images are REUSED (₹0)


def _ad_has_english(ad: dict) -> bool:
    return bool((ad.get("rewrite_gdoc_url") or "").strip() or ad.get("has_gdocs"))


def _validate_langs(langs: list[str]) -> None:
    if not langs:
        raise HTTPException(422, "Pick at least one language")
    bad = [l for l in langs if l not in SUPPORTED_LANGUAGES]
    if bad:
        raise HTTPException(422, f"Unsupported language(s): {', '.join(bad)}")


def _daily_spent() -> float:
    row = db.query_one(
        "SELECT COALESCE(SUM(cost_estimate_usd),0) AS s FROM jobs "
        "WHERE status NOT IN ('failed','cancelled') AND date(created_at)=date('now')")
    return (row["s"] or 0) if row else 0


class LocalizeBody(BaseModel):
    pipeline: str
    competitor: str
    ad_id: str
    languages: list[str]
    force: bool = False


@router.post("/api/jobs/localize", status_code=201)
def create_localize_job(body: LocalizeBody, user: str = Depends(require_user)):
    if body.pipeline != "facebook":
        raise HTTPException(422, "Localization is Facebook-only for now")
    _validate_langs(body.languages)
    ad = catalog().get(body.pipeline, body.competitor, body.ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    if not _ad_has_english(ad):
        raise HTTPException(422, "Generate the English Supernova script first")
    active = db.query_one(
        f"SELECT id FROM jobs WHERE pipeline=? AND competitor=? AND ad_id=? "
        f"AND status IN {ACTIVE}", (body.pipeline, body.competitor, body.ad_id))
    if active:
        raise HTTPException(409, f"A run for this ad is already in flight (job #{active['id']})")
    cost = len(body.languages) * LOCALIZE_COST_PER_LANG
    cfg = settings()
    if _daily_spent() + cost > cfg.max_daily_cost:
        raise HTTPException(429, f"Daily spend cap reached ({inr(cfg.max_daily_cost)})")
    cur = db.execute(
        "INSERT INTO jobs (pipeline, competitor, ad_id, media_type, requested_by, "
        "force_regen, cost_estimate_usd, kind, languages) VALUES (?,?,?,?,?,?,?,?,?)",
        (body.pipeline, body.competitor, body.ad_id, ad.get("media_type"), user,
         int(body.force), cost, "localize", json.dumps(body.languages)))
    job_id = cur.lastrowid
    _log(body.pipeline, body.competitor, body.ad_id, user, "localize",
         f"queued localize job #{job_id} → {', '.join(body.languages)} (~{inr(cost)})")
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    return {"job_id": job_id}


class BulkLocalizeBody(BaseModel):
    items: list[AdRef]
    languages: list[str]


def _classify_localize(items: list[AdRef]) -> list[dict]:
    out = []
    seen = set()
    for it in items:
        key = (it.pipeline, it.competitor, it.ad_id)
        if key in seen:
            continue
        seen.add(key)
        base = {"pipeline": it.pipeline, "competitor": it.competitor, "ad_id": it.ad_id}
        ad = catalog().get(it.pipeline, it.competitor, it.ad_id)
        if it.pipeline != "facebook":
            out.append({**base, "eligible": False, "reason": "facebook_only"}); continue
        if not ad:
            out.append({**base, "eligible": False, "reason": "not_found"}); continue
        if not _ad_has_english(ad):
            out.append({**base, "eligible": False, "reason": "no_english_script"}); continue
        active = db.query_one(
            f"SELECT id FROM jobs WHERE pipeline=? AND competitor=? AND ad_id=? "
            f"AND status IN {ACTIVE}", key)
        if active:
            out.append({**base, "eligible": False, "reason": "in_flight"}); continue
        out.append({**base, "eligible": True})
    return out


@router.post("/api/jobs/localize/bulk-estimate")
def bulk_localize_estimate(body: BulkLocalizeBody, _user: str = Depends(require_user)):
    _validate_langs(body.languages)
    items = _classify_localize(body.items)
    per = len(body.languages) * LOCALIZE_COST_PER_LANG
    for it in items:
        if it.get("eligible"):
            it["cost_usd"] = per
    total = sum(it.get("cost_usd", 0) for it in items if it.get("eligible"))
    cfg = settings()
    return {"items": items, "languages": body.languages, "total_cost_usd": total,
            "daily_cap_usd": cfg.max_daily_cost, "daily_spent_usd": _daily_spent(),
            "daily_remaining_usd": max(0, cfg.max_daily_cost - _daily_spent())}


@router.post("/api/jobs/localize/bulk", status_code=201)
def bulk_localize(body: BulkLocalizeBody, user: str = Depends(require_user)):
    _validate_langs(body.languages)
    items = _classify_localize(body.items)
    per = len(body.languages) * LOCALIZE_COST_PER_LANG
    cfg = settings()
    spent = _daily_spent()
    queued, skipped = [], []
    for it in items:
        if not it.get("eligible"):
            skipped.append(it); continue
        if spent + per > cfg.max_daily_cost:
            skipped.append({**it, "eligible": False, "reason": "daily_cap"}); continue
        ad = catalog().get(it["pipeline"], it["competitor"], it["ad_id"]) or {}
        cur = db.execute(
            "INSERT INTO jobs (pipeline, competitor, ad_id, media_type, requested_by, "
            "force_regen, cost_estimate_usd, kind, languages) VALUES (?,?,?,?,?,?,?,?,?)",
            (it["pipeline"], it["competitor"], it["ad_id"], ad.get("media_type"), user,
             0, per, "localize", json.dumps(body.languages)))
        spent += per
        queued.append({**it, "job_id": cur.lastrowid, "cost_usd": per})
        _log(it["pipeline"], it["competitor"], it["ad_id"], user, "localize",
             f"bulk localize → {', '.join(body.languages)}")
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    return {"queued": queued, "skipped": skipped,
            "total_queued_usd": sum(q["cost_usd"] for q in queued)}


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


class EnrichConfirm(BaseModel):
    proceed: bool


@router.post("/api/jobs/{job_id}/enrich-confirm")
def enrich_confirm(job_id: int, body: EnrichConfirm, user: str = Depends(require_user)):
    r = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not r:
        raise HTTPException(404, "Job not found")
    if r["kind"] != "pipeline" or r["status"] != "awaiting_confirm":
        raise HTTPException(409, "This run is not waiting for enrichment confirmation")
    if body.proceed:
        # hand back to the worker for stage 5 (enrichment)
        db.execute("UPDATE jobs SET status='queued', current_step='enrich' WHERE id=?", (job_id,))
        _log(r["pipeline"], r["competitor"], r["ad_id"], user, "enrich_confirm",
             f"approved enrichment (~{inr(r['cost_estimate_usd'] or 0)})")
    else:
        # skip enrichment — the free ranking refresh is already committed
        db.execute("UPDATE jobs SET status='done', finished_at=datetime('now') WHERE id=?", (job_id,))
        _log(r["pipeline"], r["competitor"], r["ad_id"], user, "enrich_skip",
             "skipped enrichment; kept the free ranking update")
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


# ---------------- bulk actions (multi-select in the Library) ----------------

class AdRef(BaseModel):
    pipeline: str
    competitor: str
    ad_id: str


class BulkTrackerBody(BaseModel):
    items: list[AdRef]
    status: str


class BulkItemsBody(BaseModel):
    items: list[AdRef]


# Bulk never downgrades work in flight: shortlist applies to untouched /
# dismissed / dropped ads, dismiss to untouched / shortlisted ones.
_BULK_ALLOWED_FROM = {
    "shortlisted": ("", "dismissed", "dropped"),
    "dismissed": ("", "shortlisted"),
}


def _dedupe(items: list[AdRef]) -> list[AdRef]:
    seen: set[tuple] = set()
    out = []
    for it in items:
        k = (it.pipeline, it.competitor, it.ad_id)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _mark_sheet_dirty():
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass


@router.patch("/api/tracker/bulk")
def bulk_tracker(body: BulkTrackerBody, user: str = Depends(require_user)):
    if body.status not in _BULK_ALLOWED_FROM:
        raise HTTPException(422, f"Bulk supports {tuple(_BULK_ALLOWED_FROM)}, not {body.status!r}")
    items = _dedupe(body.items)
    if not items:
        raise HTTPException(422, "No ads given")
    if len(items) > 200:
        raise HTTPException(422, "Too many ads in one batch (max 200)")
    # Each ad lives at exactly one pipeline stage (tracker PK). Bulk never adds an
    # ad that's already in the pipeline a second time, nor downgrades one in flight —
    # such ads are skipped and reported with their CURRENT stage so the UI can say
    # exactly where they already are.
    changed, skipped = 0, []
    for it in items:
        if not catalog().get(it.pipeline, it.competitor, it.ad_id):
            skipped.append({**it.model_dump(), "reason": "not_found", "status": ""})
            continue
        row = db.query_one(
            "SELECT status FROM tracker WHERE pipeline=? AND competitor=? AND ad_id=?",
            (it.pipeline, it.competitor, it.ad_id))
        current = (row["status"] if row else "") or ""
        if current == body.status:
            skipped.append({**it.model_dump(), "reason": "unchanged", "status": current})
            continue
        if current not in _BULK_ALLOWED_FROM[body.status]:
            skipped.append({**it.model_dump(), "reason": "already_in_flow", "status": current})
            continue
        _ensure_tracker(it.pipeline, it.competitor, it.ad_id, body.status, user)
        _log(it.pipeline, it.competitor, it.ad_id, user, body.status, "bulk")
        changed += 1
    if changed:
        _mark_sheet_dirty()
    return {"changed": changed, "skipped": skipped}


def _batch_estimates(slug: str, ad_ids: list[str]) -> dict[str, dict]:
    """One estimator subprocess per competitor (it accepts --ids a,b,c);
    returns ad_id -> estimate row. The estimator only lists doc-less candidates."""
    try:
        proc = subprocess.run(
            ["python3.13", "scripts/estimate_step4_cost.py", "--competitor", slug,
             "--ids", ",".join(ad_ids), "--json"],
            cwd=FACEBOOK_DIR, capture_output=True, text=True, timeout=180)
        est = json.loads(proc.stdout[proc.stdout.index("{"):])
        return {str(r.get("ad_library_id")): r for r in est.get("estimates", [])}
    except Exception:
        return {}


def _daily_spent() -> float:
    spent = db.query_one(
        "SELECT COALESCE(SUM(cost_estimate_usd),0) AS s FROM jobs "
        "WHERE status NOT IN ('failed','cancelled') AND date(created_at)=date('now')")
    return float(spent["s"] or 0)


def _classify_bulk(items: list[AdRef]) -> list[dict]:
    """Per-ad eligibility + real cost, shared by bulk-estimate and bulk-create
    (the enqueue path re-runs this — client-supplied costs are never trusted)."""
    by_slug: dict[str, list[str]] = {}
    for it in items:
        if it.pipeline == "facebook":
            by_slug.setdefault(it.competitor, []).append(it.ad_id)
    est = {slug: _batch_estimates(slug, ids) for slug, ids in by_slug.items()}
    cfg = settings()
    out = []
    for it in items:
        ref = it.model_dump()
        if it.pipeline != "facebook":
            out.append({**ref, "eligible": False, "reason": "facebook_only"})
            continue
        ad = catalog().get(it.pipeline, it.competitor, it.ad_id)
        if not ad:
            out.append({**ref, "eligible": False, "reason": "not_found"})
            continue
        if not ad["media_url"]:
            out.append({**ref, "eligible": False, "reason": "no_media"})
            continue
        active = db.query_one(
            f"SELECT id FROM jobs WHERE pipeline=? AND competitor=? AND ad_id=? "
            f"AND status IN {ACTIVE}", (it.pipeline, it.competitor, it.ad_id))
        if active:
            out.append({**ref, "eligible": False, "reason": "in_flight"})
            continue
        row = est.get(it.competitor, {}).get(it.ad_id)
        if row is None:
            reason = ("already_generated" if (ad["has_docs"] or ad["has_gdocs"])
                      else "not_a_candidate")
            out.append({**ref, "eligible": False, "reason": reason})
            continue
        cost = round(float(row.get("cost_total", 0)), 3)
        if cost > cfg.max_job_cost:
            out.append({**ref, "eligible": False, "reason": "job_cap", "cost_usd": cost})
            continue
        out.append({**ref, "eligible": True, "reason": None, "cost_usd": cost,
                    "media_type": row.get("media_type") or ad["media_type"],
                    "duration_s": row.get("duration_s"), "scenes": row.get("scenes")})
    return out


@router.post("/api/jobs/bulk-estimate")
def bulk_estimate(body: BulkItemsBody, _user: str = Depends(require_user)):
    items = _dedupe(body.items)
    if not items:
        raise HTTPException(422, "No ads given")
    if len(items) > 50:
        raise HTTPException(422, "Too many ads in one batch (max 50)")
    rows = _classify_bulk(items)
    cfg = settings()
    spent = _daily_spent()
    return {"items": rows,
            "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in rows if r["eligible"]), 3),
            "daily_cap_usd": cfg.max_daily_cost,
            "daily_spent_usd": round(spent, 2),
            "daily_remaining_usd": round(max(0.0, cfg.max_daily_cost - spent), 2),
            "max_job_cost_usd": cfg.max_job_cost}


@router.post("/api/jobs/bulk", status_code=201)
def bulk_create(body: BulkItemsBody, user: str = Depends(require_user)):
    items = _dedupe(body.items)
    if not items:
        raise HTTPException(422, "No ads given")
    if len(items) > 50:
        raise HTTPException(422, "Too many ads in one batch (max 50)")
    rows = _classify_bulk(items)
    cfg = settings()
    spent = _daily_spent()
    queued, skipped = [], []
    for r in rows:  # request order; enqueue-what-fits under the daily cap
        ref = {k: r[k] for k in ("pipeline", "competitor", "ad_id")}
        if not r["eligible"]:
            skipped.append({**ref, "reason": r["reason"]})
            continue
        cost = r["cost_usd"]
        if spent + cost > cfg.max_daily_cost:
            skipped.append({**ref, "reason": "daily_cap"})
            continue
        cur = db.execute(
            "INSERT INTO jobs (pipeline, competitor, ad_id, media_type, requested_by, "
            "force_regen, cost_estimate_usd) VALUES (?,?,?,?,?,0,?)",
            (r["pipeline"], r["competitor"], r["ad_id"], r["media_type"], user, cost))
        job_id = cur.lastrowid
        spent += cost
        _ensure_tracker(r["pipeline"], r["competitor"], r["ad_id"], "generating", user)
        _log(r["pipeline"], r["competitor"], r["ad_id"], user, "generate",
             f"queued job #{job_id} (~{inr(cost)}) [bulk]")
        queued.append({**ref, "job_id": job_id, "cost_usd": cost})
    if queued:
        _mark_sheet_dirty()
    return {"queued": queued, "skipped": skipped,
            "total_queued_usd": round(sum(q["cost_usd"] for q in queued), 3)}


# ---------------- pipeline (full data-update run) ----------------

class PipelineBody(BaseModel):
    pipeline: str
    competitors: list[str] = []
    competitor: str | None = None  # back-compat single


@router.get("/api/pipeline/pending")
def pipeline_pending(pipeline: str = "facebook", _user: str = Depends(require_user)):
    """Ads pending enrichment, per competitor + total — the actionable backlog."""
    from .pipeline import pending_by_competitor
    if pipeline not in ("facebook", "google"):
        raise HTTPException(422, "pipeline must be facebook or google")
    return pending_by_competitor(pipeline)


@router.get("/api/pipeline/estimate")
def pipeline_estimate(pipeline: str, competitor: str, _user: str = Depends(require_user)):
    from .pipeline import estimate_cost
    if pipeline not in ("facebook", "google"):
        raise HTTPException(422, "pipeline must be facebook or google")
    return estimate_cost(pipeline, competitor)


@router.post("/api/pipeline/run", status_code=201)
def pipeline_run(body: PipelineBody, user: str = Depends(require_user)):
    from .pipeline import count_unenriched, PER_VIDEO_USD
    if body.pipeline not in ("facebook", "google"):
        raise HTTPException(422, "pipeline must be facebook or google")
    slugs = list(dict.fromkeys(body.competitors or ([body.competitor] if body.competitor else [])))
    if not slugs:
        raise HTTPException(422, "pick at least one competitor")

    # reject ones already running; estimate total cost up front (pending enrichment)
    running = {r["competitor"] for r in db.query(
        f"SELECT competitor FROM jobs WHERE kind='pipeline' AND pipeline=? AND status IN {ACTIVE}",
        (body.pipeline,))}
    from .config import REPO
    queued, skipped = [], []
    total_cost = 0.0
    for slug in slugs:
        if slug in running or not (REPO / body.pipeline / "master" / f"{slug}.csv").is_file():
            skipped.append(slug)
            continue
        total_cost += count_unenriched(body.pipeline, slug) * PER_VIDEO_USD
        queued.append(slug)
    if not queued:
        raise HTTPException(409, "Those competitors are already running, or have no data yet.")

    cfg = settings()
    if total_cost > cfg.max_daily_cost:
        raise HTTPException(422, f"Estimated {inr(total_cost)} of enrichment exceeds the "
                                 f"{inr(cfg.max_daily_cost)} cap — pick fewer competitors or raise "
                                 f"STUDIO_MAX_DAILY_COST.")
    job_ids = []
    for slug in queued:
        cost = round(count_unenriched(body.pipeline, slug) * PER_VIDEO_USD, 2)
        cur = db.execute(
            "INSERT INTO jobs (kind, mode, pipeline, competitor, ad_id, requested_by, "
            "cost_estimate_usd) VALUES ('pipeline','full',?,?,'(full-run)',?,?)",
            (body.pipeline, slug, user, cost))
        job_ids.append(cur.lastrowid)
        _log(body.pipeline, slug, "(full-run)", user, "pipeline_run",
             f"queued data update (~{inr(cost)})")
    return {"job_ids": job_ids, "queued": queued, "skipped": skipped}


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


class LocalizeVerify(BaseModel):
    language: str
    verified: bool


@router.patch("/api/tracker/{pipeline}/{slug}/{ad_id}/localize-verify")
def localize_verify(pipeline: str, slug: str, ad_id: str, body: LocalizeVerify,
                    user: str = Depends(require_user)):
    """Record (display-only, not enforced) who verified a localized language."""
    row = db.query_one("SELECT verified_languages FROM tracker "
                       "WHERE pipeline=? AND competitor=? AND ad_id=?", (pipeline, slug, ad_id))
    if row is None:
        raise HTTPException(404, "No tracker row for this ad")
    try:
        verified = json.loads(row["verified_languages"]) if row["verified_languages"] else {}
    except Exception:
        verified = {}
    verified[body.language] = {
        "verified": body.verified,
        "verified_by": user if body.verified else "",
        "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M") if body.verified else "",
    }
    db.execute("UPDATE tracker SET verified_languages=?, updated_at=datetime('now') "
               "WHERE pipeline=? AND competitor=? AND ad_id=?",
               (json.dumps(verified), pipeline, slug, ad_id))
    _log(pipeline, slug, ad_id, user,
         "localize_verify" if body.verified else "localize_unverify", body.language)
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass
    return {"verified_languages": verified}
