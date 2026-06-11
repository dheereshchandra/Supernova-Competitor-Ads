"""One-click "Run data update" — runs the competitor pipeline stages 1–5
(scrape → download → R2 upload → free analysis → enrichment), EXCLUDING the
Creative Studio script generation (stage 6).

Wraps analysis/scripts/run_pipeline.sh as a single long subprocess, parsing its
`-- stage N (name) --` markers for live progress. On success it commits the data
(master CSV + analysis/derived + enrichment sidecars — log_and_commit alone
misses the derived CSVs that drive verdicts/ranks) and pushes, so origin/main +
the Sheet pick up the new ranks and the tree stays clean for the daily sync.
Then the in-memory catalog reloads, so the whole app reflects the new data.
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import pathlib
import re

from . import db
from .config import REPO, settings
from .data import catalog

PER_VIDEO_USD = 0.012  # Gemini Flash transcribe+tag, ~$0.012/new video (run_batch.sh)

# run_pipeline.sh stage index → (key, friendly label). Stages 1–5 only.
STAGE_BY_INDEX = {
    1: ("scrape", "Scraping the ad library"),
    2: ("download", "Downloading new videos"),
    3: ("r2upload", "Uploading media to storage"),
    4: ("free", "Building rankings & analysis"),
    5: ("enrich", "Enriching (transcripts & tags)"),
}
PIPELINE_STEPS = [
    {"key": "scrape", "label": "Scraping the ad library"},
    {"key": "download", "label": "Downloading new videos"},
    {"key": "r2upload", "label": "Uploading media to storage"},
    {"key": "free", "label": "Building rankings & analysis"},
    {"key": "enrich", "label": "Enriching (transcripts & tags)"},
    {"key": "commit", "label": "Saving the new data"},
    {"key": "refresh", "label": "Refreshing the app"},
]
_STAGE_RE = re.compile(r"--\s*stage\s+(\d+)\s*\(([a-z0-9]+)\)", re.I)


def estimate_cost(pipeline: str, slug: str) -> dict:
    """Approx cost = video ads in master with NO transcript yet × per-video.
    Stages 1–4 are free; only enrichment (stage 5) spends, and only on videos
    that haven't been enriched. New ads the scrape finds add ~$0.012 each."""
    master = REPO / pipeline / "master" / f"{slug}.csv"
    if not master.is_file():
        return {"eligible": False, "reason": f"No data yet for {slug} on {pipeline}."}
    tdir = REPO / "analysis" / "enrichment" / pipeline / "transcripts" / slug
    done = {p.stem for p in tdir.glob("*.json")} if tdir.is_dir() else set()
    id_col = "ad_library_id" if pipeline == "facebook" else "creative_id"
    seen, todo = set(), 0
    with master.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            aid = (r.get(id_col) or "").strip()
            mt = (r.get("ad_media_type") or r.get("creative_format") or "").strip().lower()
            if aid and aid not in seen:
                seen.add(aid)
                if aid not in done and ("video" in mt or mt == ""):
                    todo += 1
    return {"eligible": True, "backlog_videos": todo,
            "cost_usd": round(todo * PER_VIDEO_USD, 2),
            "note": "Covers transcript/tagging for videos not yet enriched. "
                    "New ads the scrape finds add ~$0.012 each. "
                    "Scraping, download, upload and analysis are free.",
            "excludes": "Supernova script generation is NOT part of this run.",
            "wall_clock": "20–90 min depending on how many new videos"}


def _snapshot(pipeline: str, slug: str) -> dict:
    """Counts before/after a run so we can show what changed."""
    enriched = REPO / "analysis" / "derived" / pipeline / f"{slug}_enriched.csv"
    total = winners = 0
    if enriched.is_file():
        try:
            with enriched.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    total += 1
                    if r.get("verdict") in ("strong_winner", "winner"):
                        winners += 1
        except OSError:
            pass
    return {"ads": total, "winners": winners}


class PipelineRunner:
    """Runs one stages-1–5 pipeline pass for a competitor as a tracked job."""

    def __init__(self, job: dict):
        self.job = job
        self.id = job["id"]
        self.pipeline = job["pipeline"]
        self.slug = job["competitor"]
        self.who = job.get("requested_by") or "ad-studio"
        self.tail: list[str] = []

    # local imports avoid a cycle with jobs.py (which imports pipeline)
    def _ev(self, step, line):
        from .jobs import _event
        _event(self.id, step, line)

    def _set(self, **f):
        from .jobs import _set
        _set(self.id, **f)

    async def _run(self, step, argv, cwd=REPO, timeout=7200):
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        cur_step = step

        async def pump():
            nonlocal cur_step
            assert proc.stdout
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").rstrip()
                self.tail.append(line)
                del self.tail[:-80]
                m = _STAGE_RE.search(line)
                if m:
                    idx = int(m.group(1))
                    if idx in STAGE_BY_INDEX:
                        cur_step = STAGE_BY_INDEX[idx][0]
                        self._set(current_step=cur_step)
                self._ev(cur_step, line)

        try:
            await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"{step}: timed out after {timeout}s")
        return proc.returncode or 0

    async def _commit(self):
        """Stage master + analysis data for this competitor (NOT git add -A — that
        would sweep up unrelated untracked files), then commit + push."""
        p, slug = self.pipeline, self.slug
        patterns = [
            f"{p}/master/{slug}.csv",
            f"analysis/history/{p}/{slug}.csv",
        ]
        # derived + enrichment files are prefixed by the slug with a separator,
        # so "speak_*" won't grab "speakx_*"
        for d in (f"analysis/derived/{p}",):
            for sep in ("_", "-", "."):
                patterns.append(f"{d}/{slug}{sep}*")
        for sub in ("transcripts", "language", "scripts", "embeddings", "media", "visual"):
            patterns.append(f"analysis/enrichment/{p}/{sub}/{slug}")
            patterns.append(f"analysis/enrichment/{p}/{sub}/{slug}.*")
            patterns.append(f"analysis/enrichment/{p}/{sub}/{slug}_*")
        await self._run("commit", ["git", "add", "--", *patterns], timeout=120)
        # log_and_commit adds master+inputs+RUN_LOG and commits the whole staged index
        rc = await self._run("commit", [
            "bash", "tools/log_and_commit.sh", p, slug,
            f"{self.who} (Ad Studio pipeline)",
            f"data refresh via Ad Studio (stages 1-5)"], timeout=180)
        if rc != 0:
            self._ev("commit", "nothing to commit or commit skipped")
        rc = await self._run("commit", ["git", "push"], timeout=180)
        if rc != 0:
            await self._run("commit", ["git", "pull", "--no-rebase"], timeout=180)
            rc = await self._run("commit", ["git", "push"], timeout=180)
        if rc != 0:
            self._set(needs_push=1)
            self._ev("commit", "push failed — flagged needs_push")

    async def run(self):
        from .jobs import _now
        before = _snapshot(self.pipeline, self.slug)
        self._set(status="running", current_step="scrape",
                  started_at=self.job.get("started_at") or _now())
        self._ev("scrape", f"▶ Running data update for {self.slug} ({self.pipeline})")

        argv = ["bash", "analysis/scripts/run_pipeline.sh",
                "--competitor", self.slug, "--pipeline", self.pipeline,
                "--through-stage", "5"]
        import os
        if (os.environ.get("STUDIO_PIPELINE_DRYRUN") == "1"
                or settings().env.get("STUDIO_PIPELINE_DRYRUN") == "1"):
            argv.append("--dry-run")  # plumbing test: prints stages, no scrape/spend
        rc = await self._run("scrape", argv, timeout=7200)

        if rc == 10:
            self._set(status="failed", finished_at=_now(),
                      error="Scrape was blocked (0 ads / login wall / throttle). "
                            "Don't retry immediately — try again later.",
                      stderr_tail="\n".join(self.tail[-50:]))
            return
        if rc != 0:
            self._set(status="failed", finished_at=_now(),
                      error=f"Pipeline failed (exit {rc}) — see the log.",
                      stderr_tail="\n".join(self.tail[-50:]))
            return

        self._set(current_step="commit")
        self._ev("commit", "▶ Saving the new data")
        await self._commit()

        self._set(current_step="refresh")
        catalog().reload_if_stale()
        # nudge the twice-daily Sheet sync so the master Sheet reflects new ranks now
        try:
            await self._run("refresh", [
                "launchctl", "kickstart", "-k",
                f"gui/{__import__('os').getuid()}/live.gosupernova.csv-sync"], timeout=30)
        except Exception:
            pass

        after = _snapshot(self.pipeline, self.slug)
        summary = (f"{self.slug}: ads {before['ads']}→{after['ads']}, "
                   f"winners {before['winners']}→{after['winners']}")
        self._ev("refresh", f"✓ {summary}")
        self._set(status="done", finished_at=_now(), current_step=None,
                  error=None)
