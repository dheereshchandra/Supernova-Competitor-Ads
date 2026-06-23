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
    "direct_submit": "Submitting the script",
    "direct_poll": "Writing the script in each language",
    "qc": "Quality-checking the script",
    "direct_docs": "Building the Google Docs",
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
# When the operator picks languages up front, generate produces ONE combined Doc per language
# (English + that language) through the localize engine — so the English-only doc tail
# (build_docs/upload_and_update/build_html/upload_gdocs) is replaced by the single `localize` step.
STEPS_VIDEO_LOCALIZED = ["hydrate", "estimate", "decompose_upload", "decompose", "frames",
                         "upload_images", "rewrite_submit", "rewrite_poll",
                         "localize", "commit_push", "sheet_sync"]
STEPS_IMAGE_LOCALIZED = ["hydrate", "estimate", "decompose_images",
                         "upload_images", "rewrite_submit", "rewrite_poll",
                         "localize", "commit_push", "sheet_sync"]
# DIRECT seed→target (default for generate-with-languages): each selected language is generated
# DIRECTLY from the seed language in one Pro pass (re-skin + localize together) — NO English master,
# unless "English" is one of the selected languages. A QC gate runs before the docs are built.
STEPS_VIDEO_DIRECT = ["hydrate", "estimate", "decompose_upload", "decompose", "frames",
                      "upload_images", "direct_submit", "direct_poll", "qc",
                      "direct_docs", "commit_push", "sheet_sync"]
STEPS_IMAGE_DIRECT = ["hydrate", "estimate", "decompose_images",
                      "upload_images", "direct_submit", "direct_poll", "qc",
                      "direct_docs", "commit_push", "sheet_sync"]
# "Add a language later" (kind=localize) is ALSO direct-from-seed now (no English master needed) —
# it only needs the existing decompose sidecar.
STEPS_DIRECT_LOCALIZE = ["direct_submit", "direct_poll", "qc", "direct_docs", "commit_push", "sheet_sync"]
# Legacy English-pivot localize (translate an approved English master into N languages) — retired as the
# default by steps_for() but kept for reference / any explicit English-master→translate use.
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


def _parse_langs(raw) -> list[str]:
    """Job.languages is stored as a JSON array (web) or a comma string (legacy). Either → list."""
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def steps_for(media_type: str, kind: str = "generate", languages=None) -> list[str]:
    if kind == "localize":          # add-language-later → direct from seed (no English master needed)
        return STEPS_DIRECT_LOCALIZE
    if kind == "tts":
        return STEPS_TTS
    if languages:                   # generate into N languages → DIRECT seed→target (English only if picked)
        return STEPS_IMAGE_DIRECT if media_type == "Image" else STEPS_VIDEO_DIRECT
    return STEPS_IMAGE if media_type == "Image" else STEPS_VIDEO   # no languages → English-only master


def steps_payload(media_type: str, kind: str = "generate", languages=None) -> list[dict]:
    return [{"key": k, "label": STEP_LABELS[k]} for k in steps_for(media_type, kind, languages)]


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

    # ---------- direct seed→target ----------
    async def step_direct_submit(self):
        langs = _parse_langs(self.job.get("languages"))
        if not langs:
            raise StepFailed("direct_submit: no target languages")
        out = await self.must("direct_submit", [
            PY, "scripts/step4_rewrite.py", "submit", "--competitor", self.slug,
            "--target-languages", ",".join(langs), self.ad_id], timeout_s=300)
        m = re.findall(r"poll ([A-Za-z0-9_-]+)", out)
        if not m:
            raise StepFailed("direct_submit: could not capture poll id")
        _set(self.id, rewrite_short_id=m[-1])
        self.job["rewrite_short_id"] = m[-1]

    async def step_direct_poll(self):
        short = self.job.get("rewrite_short_id") or (
            (db.query_one("SELECT rewrite_short_id FROM jobs WHERE id=?", (self.id,)) or {})
            .get("rewrite_short_id"))
        if not short:  # resumed without a submit — redo it (direct)
            await self.step_direct_submit()
            short = self.job["rewrite_short_id"]
        rc = await self._poll_until_terminal(short)
        if rc == 2:
            raise StepFailed("direct_poll: batch terminally failed")
        # rc == 4: ≥1 requested language DROPPED (model error / malformed JSON). Regenerate ONCE
        # (persist the guard FIRST so a crash can't loop), then surface any still-dropped language and
        # proceed with the survivors — never silently lose a language, never silently ship a partial.
        if rc == 4 and not self.job.get("direct_retried"):
            _set(self.id, direct_retried=1); self.job["direct_retried"] = 1
            _event(self.id, "direct_poll", "some languages dropped — regenerating once")
            await self.step_direct_submit()
            short = self.job["rewrite_short_id"]
            rc = await self._poll_until_terminal(short)
            if rc == 2:
                raise StepFailed("direct_poll: batch terminally failed on retry")
        if rc == 4:
            dropped = self._dropped_langs(short)            # {Language: reason}
            _set(self.id, dropped_languages=json.dumps(dropped))
            _event(self.id, "direct_poll", "DROPPED — " + "; ".join(f"{l}: {r}" for l, r in dropped.items()))
            survivors = [l for l in _parse_langs(self.job.get("languages"))
                         if l.lower() not in {d.lower() for d in dropped}]
            self.job["languages"] = json.dumps(survivors)   # downstream steps run on the survivors only
            if not survivors:
                raise StepFailed("direct_poll: every requested language was dropped — "
                                 + "; ".join(f"{l}: {r}" for l, r in dropped.items()))

    async def _poll_until_terminal(self, short: str) -> int:
        for _ in range(80):
            rc, _out = await self.run_cmd("direct_poll", [
                PY, "scripts/step4_rewrite.py", "poll", short], timeout_s=180)
            if rc in (0, 2, 4):
                return rc
            await asyncio.sleep(30)
        raise StepFailed("direct_poll: not done after 80 polls (~40 min)")

    def _dropped_langs(self, short: str) -> dict:
        """Map the rewrite poll's failures.json (missing metadata keys → reasons) to {Language: reason}."""
        fp = FACEBOOK_DIR / "step4_workspace" / "batches" / f"rewrite_{short}.failures.json"
        if not fp.is_file():
            return {}
        try:
            d = json.loads(fp.read_text())
        except Exception:
            return {}
        out = {}
        for k in d.get("missing", []):
            lang = "English" if "." not in k else k.rsplit(".", 1)[1].title()
            out[lang] = d.get("reasons", {}).get(k, "no response in the batch")
        return out

    async def step_qc(self):
        """QC gate. Lint the generated sidecars; on a BLOCK, auto-regenerate ONCE (persisting the
        1-retry guard FIRST so a crash can't loop), then hard-gate. Flags are non-blocking."""
        scenes = FACEBOOK_DIR / "step4_workspace" / "scenes"
        qc_path = scenes / f"{self.ad_id}.qc.json"
        corr_path = scenes / f"{self.ad_id}.qc_correction.txt"
        qc_argv = [PY, "scripts/step4_qc.py", self.ad_id, "--competitor", self.slug]
        _qc_langs = _parse_langs(self.job.get("languages"))   # scope QC to this job's (surviving) languages
        if _qc_langs:                                          # → no stale English-master / other-lang contamination
            qc_argv += ["--langs", ",".join(_qc_langs)]

        def _block_reason() -> str:
            try:
                d = json.loads(qc_path.read_text())
                bl = [i for i in d.get("issues", []) if i.get("severity") == "block"]
                return "; ".join(f"{i['code']}: {i['detail']}" for i in bl)[:500] or "QC blocked"
            except Exception:
                return "QC blocked"

        rc, out = await self.run_cmd("qc", qc_argv, timeout_s=600)
        if rc == 0:
            if "flag" in out:
                _event(self.id, "qc", "QC flags noted for human review (non-blocking)")
            return
        # rc == 2 → block
        if self.job.get("qc_retried"):
            reason = _block_reason()
            _set(self.id, qc_block=reason)
            raise StepFailed(f"qc: blocked after 1 regenerate — {reason}")
        _set(self.id, qc_retried=1)          # persist the guard BEFORE the re-submit (crash-safe)
        self.job["qc_retried"] = 1
        try:                                  # write the corrective the rewrite prompt will read back
            d = json.loads(qc_path.read_text())
            bl = [i for i in d.get("issues", []) if i.get("severity") == "block"]
            corr_path.write_text("\n".join(f"- {i['code']}: {i['detail']}" for i in bl), encoding="utf-8")
        except Exception:
            pass
        _event(self.id, "qc", "QC blocked — regenerating once with corrections")
        await self.step_direct_submit()
        await self.step_direct_poll()
        corr_path.unlink(missing_ok=True)
        rc2, _ = await self.run_cmd("qc", qc_argv, timeout_s=600)
        if rc2 == 2:
            reason = _block_reason()
            _set(self.id, qc_block=reason)
            raise StepFailed(f"qc: blocked after 1 regenerate — {reason}")

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
        elif step == "direct_submit":
            await self.step_direct_submit()
        elif step == "direct_poll":
            await self.step_direct_poll()
        elif step == "qc":
            await self.step_qc()
        elif step == "direct_docs":
            langs = _parse_langs(self.job.get("languages"))
            if not langs:
                raise StepFailed("direct_docs: no target languages")
            argv = [PY, "scripts/step4_localize.py", self.ad_id, "--competitor", self.slug,
                    "--languages", ",".join(langs), "--direct", "--source", "sidecar"]
            await self.must("direct_docs", argv, timeout_s=1200)
        elif step == "upload_gdocs":
            argv = [PY, "scripts/step4_upload_gdocs.py", "--competitor", self.slug, self.ad_id]
            if self.job.get("force_regen"):
                argv.append("--force")
            await self.must(step, argv, timeout_s=300)
        elif step == "localize":
            langs = _parse_langs(self.job.get("languages"))
            if not langs:
                raise StepFailed("localize: no target languages")
            argv = [PY, "scripts/step4_localize.py", self.ad_id, "--competitor", self.slug,
                    "--languages", ",".join(langs), "--source", "auto"]
            if self.job.get("force_regen"):
                argv.append("--regenerate")
            await self.must(step, argv, timeout_s=1200)
        elif step == "tts":
            langs = _parse_langs(self.job.get("languages"))
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
        langs = _parse_langs(self.job.get("languages"))
        steps = steps_for(self.media_type, kind, langs)
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
        if langs:
            # Merged generate+localize: the per-language combined Docs ARE the deliverable
            # (no standalone English Doc). Mark script_ready AND record the per-language links.
            _set(self.id, status="done", finished_at=_now(), current_step=None)
            _tracker_on_done_localized(self.job, self.collect_locales())
            return
        rewrite, analysis = self.collect_results()
        _set(self.id, status="done", finished_at=_now(), current_step=None,
             rewrite_html_url=_html_url(self.slug, self.ad_id))
        _tracker_on_done(self.job, rewrite, analysis,
                         _html_url(self.slug, self.ad_id))


def _now(plus_seconds: int = 0) -> str:
    t = datetime.datetime.now(datetime.UTC)
    if plus_seconds:
        t += datetime.timedelta(seconds=plus_seconds)
    return t.strftime("%Y-%m-%d %H:%M:%S")


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


def _tracker_on_done_localized(job: dict, locales: dict) -> None:
    """End of a merged generate+localize run: the per-language combined Docs ARE the deliverable
    (no standalone English Doc). Mark script_ready AND record the per-language links + verify seed —
    a union of _tracker_on_done's status flip and _tracker_on_localize's link write."""
    links = {lang: (loc or {}).get("link", "") for lang, loc in locales.items()}
    verified = {lang: {"verified": False, "verified_by": "", "at": ""} for lang in locales}
    db.execute(
        """UPDATE tracker SET status='script_ready', localization_gdoc_urls=?,
           verified_languages=?, script_ready_at=datetime('now'), updated_at=datetime('now')
           WHERE pipeline=? AND competitor=? AND ad_id=?""",
        (json.dumps(links), json.dumps(verified),
         job["pipeline"], job["competitor"], job["ad_id"]))
    db.execute(
        "INSERT INTO activity (pipeline, competitor, ad_id, who, action, detail) "
        "VALUES (?,?,?,?,?,?)",
        (job["pipeline"], job["competitor"], job["ad_id"], "system",
         "script_ready", f"Supernova scripts generated: {', '.join(locales.keys()) or '(none)'}"))
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


# ---- failure classification & auto-retry policy (data-update runs) --------
# kind -> (max_total_attempts, cooldown_seconds). A failed attempt is auto-
# retried only while attempt_count < max_total_attempts AND the kind is
# retryable. 'blocked' (scrape 0-ads / login wall / throttle) waits HOURS on
# purpose: the FB scraper shares one static IP, so retrying soon just deepens
# the throttle — the long cooldown lets the IP recover (the real fix is a
# rotating proxy). 'timeout' is cheap to retry because enrichment resumes
# incrementally (already-transcribed videos are skipped), so a giant competitor
# that caps out finishes on the next attempt. 'permanent' never auto-retries.
RETRY_POLICY = {
    "blocked":   (2, 6 * 3600),   # 1 auto-retry, +6h
    "timeout":   (3, 10 * 60),    # 2 auto-retries, +10m
    "transient": (2, 10 * 60),    # 1 auto-retry, +10m
    "permanent": (1, 0),          # no auto-retry
}


def _fmt_eta(seconds: int) -> str:
    if seconds >= 3600:
        h = seconds / 3600
        return f"{h:.0f}h" if h == int(h) else f"{h:.1f}h"
    return f"{max(1, round(seconds / 60))} min"


def record_failure(job: dict, *, kind: str, error: str,
                   tail: list[str] | None = None) -> None:
    """Central failure handler for pipeline (data-update) runs — applies the
    auto-retry policy. If attempts remain and the kind is retryable, the job is
    re-queued with a cooldown (next_retry_at); the FIFO worker skips it until
    then and keeps current_step so enrichment resumes where it stopped. Cooled-
    down jobs do NOT block the queue — the worker's next_retry_at gate lets other
    runs go ahead. Otherwise the job lands in 'failed' and an escalation alert
    fires. The manual Retry button always works and resets the budget. A heads-up
    Slack alert fires on the first failure and again on final escalation (not on
    the quiet middle retries). Never raises — a broken handler must not wedge the
    worker."""
    try:
        job_id = job["id"]
        slug = job.get("competitor") or job.get("slug") or "?"
        pipe = job.get("pipeline") or "?"
        max_attempts, cooldown = RETRY_POLICY.get(kind, RETRY_POLICY["transient"])
        row = db.query_one("SELECT attempt_count FROM jobs WHERE id=?", (job_id,))
        attempt = ((row["attempt_count"] if row else 0) or 0) + 1
        tail_s = "\n".join((tail or [])[-50:]) or None
        if kind != "permanent" and attempt < max_attempts:
            eta = _fmt_eta(cooldown)
            _set(job_id, status="queued", attempt_count=attempt, failure_kind=kind,
                 next_retry_at=_now(cooldown), finished_at=None, stderr_tail=tail_s,
                 error=f"{error} — auto-retry {attempt + 1}/{max_attempts} in ~{eta}")
            _event(job_id, job.get("current_step") or "scrape",
                   f"⚠ {error} — auto-retry {attempt + 1}/{max_attempts} scheduled in ~{eta}")
            if attempt == 1:  # first failure only; stay quiet on the middle retries
                notify("Ad Studio: run failed — auto-retrying",
                       f"{slug} ({pipe}) — {error} Retry {attempt + 1}/{max_attempts} in ~{eta}.")
        else:
            _set(job_id, status="failed", attempt_count=attempt, failure_kind=kind,
                 next_retry_at=None, finished_at=_now(), error=error, stderr_tail=tail_s)
            notify("Ad Studio: run needs attention",
                   f"{slug} ({pipe}) — failed after {attempt} attempt(s): {error} "
                   f"Manual retry needed.")
    except Exception:
        try:  # last-ditch: never leave the job stuck in 'running'
            _set(job["id"], status="failed", finished_at=_now(), error=error)
        except Exception:
            pass


async def _worker():
    while True:
        job = None
        try:
            if _in_blackout():
                await asyncio.sleep(30)
                continue
            # skip jobs in an auto-retry cooldown (next_retry_at in the future) so
            # they don't block ready work; same-format UTC strings compare lexically
            row = db.query_one(
                "SELECT * FROM jobs WHERE status='queued' "
                "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
                "ORDER BY id LIMIT 1", (_now(),))
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
                    if job.get("kind") == "pipeline":
                        # timeouts & unexpected crashes land here, not the per-step
                        # failure branches — route through the auto-retry policy so a
                        # hung run self-heals instead of failing silently.
                        kind = "timeout" if "timed out" in str(e) else "transient"
                        record_failure(job, kind=kind, error=f"runner crashed: {e}")
                    else:
                        _set(job["id"], status="failed", error=f"runner crashed: {e}",
                             finished_at=_now())
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
