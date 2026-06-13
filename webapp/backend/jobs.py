"""Generation job runner: wraps the Creative Studio CLI chain per ad.

One global FIFO worker (concurrency = 1) — same-competitor workspace files,
master-CSV whole-file writes, and git commits are all single-writer, and the
serial queue makes spend reasoning trivial. Every underlying script is
idempotent/checkpointed, so resume = re-run the current step.

The step chain mirrors analysis/scripts/run_pipeline.sh:step4_execute() with
two deliberate additions: step4_upload_gdocs.py (Stage 9 — the collaborative
Google Docs, which step4_execute never wired in) and commit+push (the 11:30
repo-sync / 11:35 capture-sync launchd jobs SKIP on a dirty or unpushed main,
so a web-triggered job must leave the tree clean and pushed).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import re
import urllib.request
from urllib.parse import urlparse

from . import db
from .config import FACEBOOK_DIR, REPO, settings
from .data import catalog
from .notify import notify

PY = "python3.13"

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}

STEP_LABELS = {
    "hydrate": "Fetching the ad media",
    "estimate": "Estimating cost",
    "decompose_upload": "Uploading video to Gemini",
    "decompose": "Watching & decomposing the ad",
    "decompose_images": "Reading & decomposing the ad",
    "frames": "Extracting scene frames",
    "char_sheets": "Drawing character sheets",
    "panels": "Drawing storyboard panels",
    "upload_images": "Publishing images",
    "rewrite_submit": "Submitting the Supernova rewrite",
    "rewrite_poll": "Writing the Supernova script",
    "build_docs": "Building the documents",
    "upload_and_update": "Publishing the documents",
    "build_html": "Building the web version",
    "upload_gdocs": "Creating the Google Docs",
    "commit_push": "Saving to the repo",
    "sheet_sync": "Updating the tracker sheet",
    "localize": "Translating into the chosen languages",
    "tts": "Generating the voiceover",
}

# Image generation (char_sheets, panels — Nano Banana Pro) is NO LONGER part of the
# script/document chain; it runs as a separate later step. Frames (free) stay so the
# competitor doc keeps the original video screenshots.
STEPS_VIDEO = ["hydrate", "estimate", "decompose_upload", "decompose", "frames",
               "upload_images", "rewrite_submit",
               "rewrite_poll", "build_docs", "upload_and_update", "build_html",
               "upload_gdocs", "commit_push", "sheet_sync"]
STEPS_IMAGE = ["hydrate", "estimate", "decompose_images",
               "upload_images", "rewrite_submit",
               "rewrite_poll", "build_docs", "upload_and_update", "build_html",
               "upload_gdocs", "commit_push", "sheet_sync"]
# Localization (PR 4): translate an existing English master into N languages. No image/decompose
# stages — step4_localize.py reuses the ad's existing images (image-once guardrail).
STEPS_LOCALIZE = ["localize", "commit_push", "sheet_sync"]
# TTS (Stage 5a, voiceover only): synth a per-language voiceover from the approved script —
# multi-provider (Cartesia + ElevenLabs), voice-mapped per character. No image/decompose stages.
STEPS_TTS = ["tts", "commit_push", "sheet_sync"]

_cancel_requested: set[int] = set()


def _download(url: str, dest: pathlib.Path) -> None:
    """Pull one R2 object. Prefer the authenticated S3 path (works even when the
    public bucket is off); fall back to the public URL with a browser UA, since
    Cloudflare's r2.dev dev domain 403s the default Python-urllib agent."""
    env = settings().env
    keys = ("R2_S3_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    if all(env.get(k) for k in keys):
        try:
            import boto3
            client = boto3.client(
                "s3", endpoint_url=env["R2_S3_ENDPOINT"],
                aws_access_key_id=env["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"], region_name="auto")
            client.download_file(env["R2_BUCKET"], urlparse(url).path.lstrip("/"), str(dest))
            return
        except Exception:  # noqa: BLE001 — fall through to public URL
            pass
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AdStudio)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())


def steps_for(media_type: str, kind: str = "generate") -> list[str]:
    if kind == "localize":
        return STEPS_LOCALIZE
    if kind == "tts":
        return STEPS_TTS
    return STEPS_IMAGE if media_type == "Image" else STEPS_VIDEO


def steps_payload(media_type: str, kind: str = "generate") -> list[dict]:
    return [{"key": k, "label": STEP_LABELS[k]} for k in steps_for(media_type, kind)]


def _event(job_id: int, step: str, line: str) -> None:
    line = line.rstrip()[:2000]
    if line:
        db.execute("INSERT INTO job_events (job_id, step, line) VALUES (?,?,?)",
                   (job_id, step, line))
        # keep at most ~2000 lines per job so a long poll loop can't grow unbounded
        db.execute("DELETE FROM job_events WHERE job_id=? AND id < "
                   "(SELECT MAX(id)-2000 FROM job_events WHERE job_id=?)",
                   (job_id, job_id))


def _set(job_id: int, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


class StepFailed(Exception):
    pass


class JobRunner:
    def __init__(self, job: dict):
        self.job = job
        self.id = job["id"]
        self.slug = job["competitor"]
        self.ad_id = job["ad_id"]
        self.media_type = job["media_type"] or "Video"
        self.tail: list[str] = []

    # ---------- subprocess plumbing ----------

    async def run_cmd(self, step: str, argv: list[str], cwd: pathlib.Path = FACEBOOK_DIR,
                      timeout_s: int = 900) -> tuple[int, str]:
        """Run one CLI, streaming output lines into job_events. Returns (rc, all_output)."""
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        lines: list[str] = []

        async def pump():
            assert proc.stdout
            async for raw in proc.stdout:
                line = raw.decode(errors="replace")
                lines.append(line)
                self.tail.append(line.rstrip())
                del self.tail[:-50]
                _event(self.id, step, line)

        try:
            await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            raise StepFailed(f"{step}: timed out after {timeout_s}s")
        return proc.returncode or 0, "".join(lines)

    async def must(self, step: str, argv: list[str], **kw) -> str:
        rc, out = await self.run_cmd(step, argv, **kw)
        if rc != 0:
            raise StepFailed(f"{step}: exit {rc}")
        return out

    # ---------- individual steps ----------

    async def step_hydrate(self):
        ad = catalog().get("facebook", self.slug, self.ad_id)
        if not ad or not ad["media_url"]:
            raise StepFailed("hydrate: ad has no media URL")
        url = ad["media_url"]
        name = pathlib.Path(urlparse(url).path).name
        kind = "videos" if pathlib.Path(name).suffix.lower() in VIDEO_EXTS else "images"
        kind_dir = FACEBOOK_DIR / kind
        if any(p.stat().st_size > 0 for p in kind_dir.glob(f"{self.slug}-*/{name}")):
            _event(self.id, "hydrate", f"already cached: {name}")
            return
        date = ad.get("last_seen") or datetime.date.today().isoformat()
        dest = kind_dir / f"{self.slug}-{date}" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        _event(self.id, "hydrate", f"downloading {url}")
        loop = asyncio.get_running_loop()
        for attempt in range(3):
            try:
                await loop.run_in_executor(None, _download, url, tmp)
                tmp.replace(dest)
                _event(self.id, "hydrate", f"saved {dest.relative_to(REPO)}")
                return
            except Exception as e:  # noqa: BLE001
                _event(self.id, "hydrate", f"attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(5)
        raise StepFailed("hydrate: download failed after 3 attempts")

    async def step_estimate(self):
        rc, out = await self.run_cmd("estimate", [
            PY, "scripts/estimate_step4_cost.py", "--competitor", self.slug,
            "--ids", self.ad_id, "--json"], timeout_s=180)
        if rc == 0:
            try:
                est = json.loads(out[out.index("{"):])
                if est.get("estimates"):
                    row = est["estimates"][0]
                    _set(self.id, cost_estimate_usd=row.get("cost_total"),
                         estimate_json=json.dumps(row))
            except (ValueError, json.JSONDecodeError):
                pass  # estimate is informational once the job is approved

    async def step_loop_imagegen(self, step: str, script: str):
        """char_sheets / panels: rc 1 = deadline hit with work left (re-run);
        rc 0 = pass complete (policy-blocked items never finish — proceed).
        Stop early after 2 consecutive passes with zero new completions."""
        no_progress = 0
        for _ in range(30):
            rc, out = await self.run_cmd(step, [
                PY, f"scripts/{script}", "--competitor", self.slug, self.ad_id],
                timeout_s=300)
            if rc == 0:
                return
            if rc != 1:
                raise StepFailed(f"{step}: exit {rc}")
            made_progress = bool(re.search(r"\bOK\b", out))
            no_progress = 0 if made_progress else no_progress + 1
            if no_progress >= 2:
                _event(self.id, step, "no progress across 2 passes — continuing with gaps")
                return
        raise StepFailed(f"{step}: still pending after 30 passes")

    async def step_rewrite_submit(self):
        out = await self.must("rewrite_submit", [
            PY, "scripts/step4_rewrite.py", "submit", "--competitor", self.slug,
            self.ad_id], timeout_s=300)
        m = re.findall(r"poll ([A-Za-z0-9_-]+)", out)
        if not m:
            raise StepFailed("rewrite_submit: could not capture poll id")
        _set(self.id, rewrite_short_id=m[-1])
        self.job["rewrite_short_id"] = m[-1]

    async def step_rewrite_poll(self):
        short = self.job.get("rewrite_short_id") or (
            db.query_one("SELECT rewrite_short_id FROM jobs WHERE id=?", (self.id,)) or {}
        )["rewrite_short_id"]
        if not short:  # resumed without a submit — redo it
            await self.step_rewrite_submit()
            short = self.job["rewrite_short_id"]
        for _ in range(80):
            rc, _out = await self.run_cmd("rewrite_poll", [
                PY, "scripts/step4_rewrite.py", "poll", short], timeout_s=180)
            if rc == 0:
                return
            if rc == 2:
                raise StepFailed("rewrite_poll: batch terminally failed")
            await asyncio.sleep(30)
        raise StepFailed("rewrite_poll: not done after 80 polls (~40 min)")

    async def step_commit_push(self):
        await self.must("commit_push", [
            "bash", "tools/log_and_commit.sh", "facebook", self.slug,
            f"{self.job.get('requested_by') or 'ad-studio'} (Ad Studio)",
            f"Creative Studio via Ad Studio: {self.ad_id}"], cwd=REPO, timeout_s=120)
        rc, _ = await self.run_cmd("commit_push", ["git", "push"], cwd=REPO, timeout_s=180)
        if rc != 0:
            rc2, _ = await self.run_cmd("commit_push", ["git", "pull", "--no-rebase"],
                                        cwd=REPO, timeout_s=180)
            if rc2 == 0:
                rc, _ = await self.run_cmd("commit_push", ["git", "push"], cwd=REPO,
                                           timeout_s=180)
        if rc != 0:
            _set(self.id, needs_push=1)
            _event(self.id, "commit_push", "push failed — flagged needs_push (job still OK)")

    async def step_sheet_sync(self):
        try:
            from . import sheets
            sheets.mark_dirty()
        except Exception as e:  # never fail the job on the mirror
            _event(self.id, "sheet_sync", f"tracker sheet sync skipped: {e}")

    def collect_results(self):
        sidecar = FACEBOOK_DIR / "step4_workspace" / "scenes" / f"{self.ad_id}.gdocs.json"
        rewrite = analysis = ""
        if sidecar.is_file():
            try:
                d = json.loads(sidecar.read_text(encoding="utf-8"))
                rewrite = (d.get("supernova_doc") or {}).get("link", "")
                analysis = (d.get("competitor_doc") or {}).get("link", "")
            except (json.JSONDecodeError, OSError):
                pass
        _set(self.id, rewrite_gdoc_url=rewrite, analysis_gdoc_url=analysis)
        return rewrite, analysis

    # ---------- the chain ----------

    async def run_step(self, step: str):
        ids = [self.ad_id]
        simple = {
            "decompose_upload": [PY, "scripts/step4_decompose.py", "upload",
                                 "--competitor", self.slug, *ids],
            "decompose": [PY, "scripts/step4_decompose_sync.py", self.slug, *ids],
            "decompose_images": [PY, "scripts/step4_decompose.py", "images",
                                 "--competitor", self.slug, *ids],
            "frames": [PY, "scripts/step4_frames.py", "--competitor", self.slug, *ids],
            "upload_images": [PY, "scripts/step4_upload_images.py",
                              "--competitor", self.slug, *ids],
            "build_docs": [PY, "scripts/step4_build_docs.py",
                           "--competitor", self.slug, *ids],
            "upload_and_update": [PY, "scripts/step4_upload_and_update.py",
                                  "--competitor", self.slug, *ids],
            "build_html": [PY, "scripts/step4_build_html.py", "--competitor", self.slug,
                           "--ids", self.ad_id, "--upload", "--update-master"],
        }
        if step == "hydrate":
            await self.step_hydrate()
        elif step == "estimate":
            await self.step_estimate()
        # char_sheets / panels (Nano Banana Pro image generation) were removed from the
        # script/document chain — image generation runs as a separate later step.
        # step_loop_imagegen() is retained for that future workflow.
        elif step == "rewrite_submit":
            await self.step_rewrite_submit()
        elif step == "rewrite_poll":
            await self.step_rewrite_poll()
        elif step == "upload_gdocs":
            argv = [PY, "scripts/step4_upload_gdocs.py", "--competitor", self.slug, self.ad_id]
            if self.job.get("force_regen"):
                argv.append("--force")
            await self.must(step, argv, timeout_s=300)
        elif step == "localize":
            raw = self.job.get("languages") or "[]"
            try:
                langs = json.loads(raw) if raw.strip().startswith("[") else \
                    [x.strip() for x in raw.split(",") if x.strip()]
            except Exception:
                langs = [x.strip() for x in raw.split(",") if x.strip()]
            if not langs:
                raise StepFailed("localize: no target languages")
            argv = [PY, "scripts/step4_localize.py", self.ad_id, "--competitor", self.slug,
                    "--languages", ",".join(langs), "--source", "auto"]
            if self.job.get("force_regen"):
                argv.append("--regenerate")
            await self.must(step, argv, timeout_s=1200)
        elif step == "tts":
            raw = self.job.get("languages") or "[]"
            try:
                langs = json.loads(raw) if raw.strip().startswith("[") else \
                    [x.strip() for x in raw.split(",") if x.strip()]
            except Exception:
                langs = [x.strip() for x in raw.split(",") if x.strip()]
            if not langs:
                raise StepFailed("tts: no target languages")
            argv = [PY, "scripts/step4_tts.py", self.ad_id, "--competitor", self.slug,
                    "--languages", ",".join(langs), "--source", "auto"]
            if self.job.get("force_regen"):
                argv.append("--regenerate")
            await self.must(step, argv, timeout_s=1800)
        elif step == "commit_push":
            await self.step_commit_push()
        elif step == "sheet_sync":
            await self.step_sheet_sync()
        elif step in simple:
            timeout = 1200 if step in ("decompose", "decompose_images") else 600
            await self.must(step, simple[step], timeout_s=timeout)
        else:
            raise StepFailed(f"unknown step {step}")

    def collect_locales(self) -> dict:
        """Read the per-language Google Doc links the localize engine wrote to the sidecar."""
        sidecar = FACEBOOK_DIR / "step4_workspace" / "scenes" / f"{self.ad_id}.gdocs.json"
        try:
            return json.loads(sidecar.read_text()).get("locales", {}) or {}
        except Exception:
            return {}

    def collect_tts(self) -> dict:
        """Read the per-language voiceover URLs the TTS engine wrote to the sidecar."""
        sidecar = FACEBOOK_DIR / "step4_workspace" / "scenes" / f"{self.ad_id}.gdocs.json"
        try:
            return json.loads(sidecar.read_text()).get("tts", {}) or {}
        except Exception:
            return {}

    async def run(self):
        kind = self.job.get("kind", "generate")
        steps = steps_for(self.media_type, kind)
        start_at = 0
        cur = self.job.get("current_step")
        if cur in steps:  # resume from the interrupted step
            start_at = steps.index(cur)
        elif cur in ("char_sheets", "panels") and "upload_images" in steps:
            # image-gen stages were removed from the chain (now a separate later step);
            # a job paused at one of them resumes at the next surviving step.
            start_at = steps.index("upload_images")
        _set(self.id, status="running",
             started_at=self.job.get("started_at") or _now())
        for step in steps[start_at:]:
            if self.id in _cancel_requested:
                _cancel_requested.discard(self.id)
                _set(self.id, status="cancelled", finished_at=_now())
                _tracker_on_fail(self.job)
                return
            _set(self.id, current_step=step)
            _event(self.id, step, f"▶ {STEP_LABELS[step]}")
            try:
                await self.run_step(step)
            except StepFailed as e:
                _set(self.id, status="failed", error=str(e), finished_at=_now(),
                     stderr_tail="\n".join(self.tail))
                notify("Ad Studio: script generation failed",
                       f"{self.slug}/{self.ad_id} — {e}")
                return
        if kind == "localize":
            _set(self.id, status="done", finished_at=_now(), current_step=None)
            _tracker_on_localize(self.job, self.collect_locales())
            return
        if kind == "tts":
            _set(self.id, status="done", finished_at=_now(), current_step=None)
            _tracker_on_tts(self.job, self.collect_tts())
            return
        rewrite, analysis = self.collect_results()
        _set(self.id, status="done", finished_at=_now(), current_step=None,
             rewrite_html_url=_html_url(self.slug, self.ad_id))
        _tracker_on_done(self.job, rewrite, analysis,
                         _html_url(self.slug, self.ad_id))


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")


def _html_url(slug: str, ad_id: str) -> str:
    ad = catalog().get("facebook", slug, ad_id)
    return (ad or {}).get("rewrite_html_url") or ""


# ---------- tracker side-effects ----------

def _tracker_on_localize(job: dict, locales: dict) -> None:
    """Write per-language links + seed verify state onto the tracker (status unchanged —
    the ad stays where it is; localization is an append-only enrichment)."""
    links = {lang: (loc or {}).get("link", "") for lang, loc in locales.items()}
    # preserve any existing verify state; seed unseen languages as unverified
    row = db.execute(
        "SELECT verified_languages FROM tracker WHERE pipeline=? AND competitor=? AND ad_id=?",
        (job["pipeline"], job["competitor"], job["ad_id"])).fetchone()
    verified = {}
    if row and row["verified_languages"]:
        try:
            verified = json.loads(row["verified_languages"])
        except Exception:
            verified = {}
    for lang in locales:
        verified.setdefault(lang, {"verified": False, "verified_by": "", "at": ""})
    db.execute(
        """UPDATE tracker SET localization_gdoc_urls=?, verified_languages=?,
           updated_at=datetime('now')
           WHERE pipeline=? AND competitor=? AND ad_id=?""",
        (json.dumps(links), json.dumps(verified),
         job["pipeline"], job["competitor"], job["ad_id"]))
    db.execute(
        "INSERT INTO activity (pipeline, competitor, ad_id, who, action, detail) "
        "VALUES (?,?,?,?,?,?)",
        (job["pipeline"], job["competitor"], job["ad_id"], job.get("requested_by") or "system",
         "localized", f"Localized into: {', '.join(locales.keys())}"))
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass


def _tracker_on_tts(job: dict, tts_map: dict) -> None:
    """Write per-language voiceover URLs + seed verify state onto the tracker (status
    unchanged — TTS is an append-only enrichment, like localization)."""
    urls = {lang: (v or {}).get("track_url", "") for lang, v in tts_map.items()}
    row = db.execute(
        "SELECT tts_verified_languages FROM tracker WHERE pipeline=? AND competitor=? AND ad_id=?",
        (job["pipeline"], job["competitor"], job["ad_id"])).fetchone()
    verified = {}
    if row and row["tts_verified_languages"]:
        try:
            verified = json.loads(row["tts_verified_languages"])
        except Exception:
            verified = {}
    for lang in tts_map:
        verified.setdefault(lang, {"verified": False, "verified_by": "", "at": ""})
    db.execute(
        """UPDATE tracker SET tts_audio_urls=?, tts_verified_languages=?,
           updated_at=datetime('now')
           WHERE pipeline=? AND competitor=? AND ad_id=?""",
        (json.dumps(urls), json.dumps(verified),
         job["pipeline"], job["competitor"], job["ad_id"]))
    db.execute(
        "INSERT INTO activity (pipeline, competitor, ad_id, who, action, detail) "
        "VALUES (?,?,?,?,?,?)",
        (job["pipeline"], job["competitor"], job["ad_id"], job.get("requested_by") or "system",
         "tts", f"Voiceover for: {', '.join(tts_map.keys())}"))
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass


def _tracker_on_done(job: dict, rewrite: str, analysis: str, html: str) -> None:
    db.execute(
        """UPDATE tracker SET status='script_ready', rewrite_gdoc_url=?,
           analysis_gdoc_url=?, rewrite_html_url=?, script_ready_at=datetime('now'),
           updated_at=datetime('now')
           WHERE pipeline=? AND competitor=? AND ad_id=?""",
        (rewrite, analysis, html, job["pipeline"], job["competitor"], job["ad_id"]))
    db.execute(
        "INSERT INTO activity (pipeline, competitor, ad_id, who, action, detail) "
        "VALUES (?,?,?,?,?,?)",
        (job["pipeline"], job["competitor"], job["ad_id"], "system",
         "script_ready", "Supernova script generated"))
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass


def _tracker_on_fail(job: dict) -> None:
    try:
        from . import sheets
        sheets.mark_dirty()
    except Exception:
        pass


# ---------- the worker ----------

def _in_blackout() -> bool:
    window = settings().blackout
    try:
        start, end = window.split("-")
        now = datetime.datetime.now().strftime("%H:%M")
        return start <= now <= end
    except ValueError:
        return False


async def _worker():
    while True:
        job = None
        try:
            if _in_blackout():
                await asyncio.sleep(30)
                continue
            row = db.query_one(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1")
            if row is None:
                await asyncio.sleep(2)
                continue
            job = dict(row)
            if job.get("kind") == "pipeline":
                from .pipeline import PipelineRunner
                await PipelineRunner(job).run()
            else:
                await JobRunner(job).run()
        except Exception as e:  # worker must never die
            try:
                if job is not None:
                    _set(job["id"], status="failed", error=f"runner crashed: {e}",
                         finished_at=_now())
                    # timeouts & unexpected crashes land here, not in the per-step
                    # failure branches — without this, a hung run fails silently
                    notify("Ad Studio: job crashed",
                           f"{job.get('competitor') or job.get('slug') or '?'}"
                           f" (job {job['id']}) — {e}")
            except Exception:
                pass
            await asyncio.sleep(5)


def request_cancel(job_id: int) -> None:
    _cancel_requested.add(job_id)


def start_worker(app) -> None:
    # crashed-while-running jobs resume from their current step
    db.execute("UPDATE jobs SET status='queued' WHERE status IN ('running','interrupted')")
    asyncio.get_running_loop().create_task(_worker())
