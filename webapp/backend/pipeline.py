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
from .config import REPO, inr, settings
from .data import catalog
from .notify import notify

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


def count_unenriched(pipeline: str, slug: str) -> int:
    """Video ads in the master CSV that don't have a transcript yet. Before a
    scrape this is the current backlog; AFTER a scrape it's the true number
    enrichment will process (existing backlog + any new ads the scrape added)."""
    master = REPO / pipeline / "master" / f"{slug}.csv"
    if not master.is_file():
        return 0
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
    return todo


def pending_by_competitor(pipeline: str) -> dict:
    """{slug: pending_videos} for every competitor that has a master CSV, plus a
    total. 'Pending' = scraped video ads that don't have a transcript yet — the
    work an enrichment run would do (and where the full data is still missing)."""
    base = REPO / pipeline / "master"
    out: dict[str, int] = {}
    if base.is_dir():
        for m in sorted(base.glob("*.csv")):
            slug = m.stem
            # skip the variant/snapshot files (e.g. praktika-ai_newly_added_2026-06-04)
            if any(x in slug for x in ("_newly_added", "_step4_", "_top20")):
                continue
            n = count_unenriched(pipeline, slug)
            if n:
                out[slug] = n
    total = sum(out.values())
    return {"per_competitor": out, "total": total,
            "total_cost_usd": round(total * PER_VIDEO_USD, 2),
            "per_video_usd": PER_VIDEO_USD}


def estimate_cost(pipeline: str, slug: str) -> dict:
    """Pre-run estimate. The headline is deliberately the FREE work — because the
    real enrichment cost can't be known until the scrape reveals how many new
    videos there are. We surface the current backlog only as a hint; the exact
    enrichment cost is confirmed after the (free) scrape."""
    master = REPO / pipeline / "master" / f"{slug}.csv"
    if not master.is_file():
        return {"eligible": False, "reason": f"No data yet for {slug} on {pipeline}."}
    backlog = count_unenriched(pipeline, slug)
    return {"eligible": True, "backlog_videos": backlog,
            "backlog_cost_usd": round(backlog * PER_VIDEO_USD, 2),
            "per_video_usd": PER_VIDEO_USD,
            "two_phase": True,
            "note": "The scrape, download, upload and ranking refresh are free. "
                    "We can't know the real enrichment cost until the scrape reveals "
                    f"how many new videos exist — so you'll confirm the exact cost "
                    f"(≈{inr(PER_VIDEO_USD)}/video) after the free scrape, before anything is spent.",
            "excludes": "Supernova script generation is NOT part of this run.",
            "wall_clock": "free scrape ~10–25 min, then enrichment if you confirm"}


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
        # expand the globs HERE: `git add -- <pathspecs>` aborts the WHOLE add
        # (rc=128, nothing staged) when any one pathspec matches no files — which
        # silently dropped every derived/enrichment file from pipeline commits
        import glob
        matched = [m for pat in patterns for m in glob.glob(str(REPO / pat))]
        if matched:
            await self._run("commit", ["git", "add", "--", *matched], timeout=120)
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

    def _dryrun(self) -> bool:
        import os
        return (os.environ.get("STUDIO_PIPELINE_DRYRUN") == "1"
                or settings().env.get("STUDIO_PIPELINE_DRYRUN") == "1")

    async def _refresh_sheet(self):
        catalog().reload_if_stale()
        try:
            import os
            await self._run("refresh", [
                "launchctl", "kickstart", "-k",
                f"gui/{os.getuid()}/live.gosupernova.csv-sync"], timeout=30)
        except Exception:
            pass

    async def run(self):
        # Phase B (enrichment) — set when the user confirms the cost
        if self.job.get("current_step") == "enrich":
            return await self._enrich_phase()
        return await self._free_phase()

    async def _free_phase(self):
        """Stages 1–4: scrape → download → upload → analysis. All FREE. Commits
        the ranking refresh, then counts the REAL number of videos to enrich and
        pauses for confirmation (the cost is only knowable now, post-scrape)."""
        import json
        from .jobs import _now
        before = _snapshot(self.pipeline, self.slug)
        self._set(status="running", current_step="scrape",
                  started_at=self.job.get("started_at") or _now())
        self._ev("scrape", f"▶ Free refresh for {self.slug} ({self.pipeline}) — "
                           f"scraping & recomputing rankings")
        argv = ["bash", "analysis/scripts/run_pipeline.sh",
                "--competitor", self.slug, "--pipeline", self.pipeline,
                "--through-stage", "4"]
        if self._dryrun():
            argv.append("--dry-run")
        rc = await self._run("scrape", argv, timeout=7200)
        if rc == 10:
            self._set(status="failed", finished_at=_now(),
                      error="Scrape was blocked (0 ads / login wall / throttle). "
                            "Don't retry immediately — try again later.",
                      stderr_tail="\n".join(self.tail[-50:]))
            notify("Ad Studio: data update blocked",
                   f"{self.slug} ({self.pipeline}) — scrape blocked (0 ads/throttle).")
            return
        if rc != 0:
            self._set(status="failed", finished_at=_now(),
                      error=f"Scrape/analysis failed (exit {rc}) — see the log.",
                      stderr_tail="\n".join(self.tail[-50:]))
            notify("Ad Studio: data update failed",
                   f"{self.slug} ({self.pipeline}) — scrape/analysis exit {rc}.")
            return

        # commit the free ranking update now (goes live + keeps the tree clean)
        self._set(current_step="commit")
        self._ev("commit", "▶ Saving the rankings update")
        await self._commit()
        await self._refresh_sheet()

        after = _snapshot(self.pipeline, self.slug)
        summary = (f"{self.slug}: ads {before['ads']}→{after['ads']}, "
                   f"winners {before['winners']}→{after['winners']}")
        backlog = count_unenriched(self.pipeline, self.slug)
        if backlog == 0:
            self._ev("refresh", f"✓ {summary} · nothing new to enrich")
            self._set(status="done", finished_at=_now(), current_step=None, error=None)
            return

        cost = round(backlog * PER_VIDEO_USD, 2)
        self._set(cost_estimate_usd=cost,
                  estimate_json=json.dumps({"videos": backlog, "cost": cost,
                                            "summary": summary}))
        if self.job.get("mode", "full") == "full":
            # cost was confirmed upfront in the modal → enrich straight away
            self._ev("refresh", f"✓ Rankings updated ({summary}). "
                                f"Enriching {backlog} videos (~{inr(cost)})…")
            return await self._enrich_phase()
        # two-phase: pause and let the user approve the now-exact cost
        self._set(status="awaiting_confirm", current_step=None)
        self._ev("refresh", f"✓ Rankings updated ({summary}). "
                            f"{backlog} videos to enrich (~{inr(cost)}) — awaiting confirmation.")

    async def _enrich_phase(self):
        """Stage 5: enrichment (the only paid stage). Runs only after the user
        confirmed the exact cost shown post-scrape."""
        from .jobs import _now
        self._set(status="running", current_step="enrich")
        self._ev("enrich", "▶ Enriching videos (transcripts & tags)")
        argv = ["bash", "analysis/scripts/run_pipeline.sh",
                "--competitor", self.slug, "--pipeline", self.pipeline,
                "--from-stage", "5", "--through-stage", "5"]
        if self._dryrun():
            argv.append("--dry-run")
        rc = await self._run("enrich", argv, timeout=7200)
        if rc != 0:
            self._set(status="failed", finished_at=_now(),
                      error=f"Enrichment failed (exit {rc}) — see the log.",
                      stderr_tail="\n".join(self.tail[-50:]))
            notify("Ad Studio: enrichment failed",
                   f"{self.slug} ({self.pipeline}) — exit {rc}.")
            return
        self._set(current_step="commit")
        self._ev("commit", "▶ Saving the enriched data")
        await self._commit()
        self._set(current_step="refresh")
        await self._refresh_sheet()
        self._ev("refresh", "✓ Enrichment complete — data is live.")
        self._set(status="done", finished_at=_now(), current_step=None, error=None)
