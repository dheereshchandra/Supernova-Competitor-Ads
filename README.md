# supernova-competitor-ads

One shared repo for Supernova's competitor-ad pipelines (Facebook + Google).
Two teammates work from separate Macs without shipping 50–60 GB of media around:
**git holds the small precious text, Cloudflare R2 holds the heavy media.**

## The model

- **Git holds:** scripts, skills, prompts, the per-competitor **master CSVs**
  (which carry every R2 link), per-run input CSVs, logs, run summaries, and the
  `analysis/` folder. All text → clones in seconds, stays small.
- **R2 holds:** all heavy media (videos, images, the built Word docs). They are
  *referenced by link* from the master CSVs; the files themselves never enter git.
- **Local `videos/` / `images/` / `step4_workspace/`** are a rebuildable cache —
  never committed. Pull what you need with `tools/rehydrate.py`.

> Why this matters for Facebook: FB video CDN links **expire**, so old media
> can't be re-fetched from old spreadsheets. R2 is the only durable home —
> which is exactly why "media in R2, pull on demand" is the safe call.

## Layout

```
supernova-competitor-ads/
├── README.md                     ← you are here
├── RUN_LOG.md                    ← append-only diary: every run (who / when / what)
├── .gitignore                    ← keeps secrets + heavy media + .bak sprawl out of git
├── facebook/                     ← PRIMARY pipeline (mature, reliable)
│   ├── scripts/ skills/ scraper_prompt.md HANDOVER.md
│   ├── master/{competitor}.csv   ← committed (every R2 link lives here)
│   ├── inputs/ step3_logs/ runs/ ← committed (text)
│   └── videos/ images/ step4_workspace/   ← NOT committed (R2 + rehydrate)
├── google/                       ← SECONDARY pipeline (API CLI scraper; rate-limit guarded)
│   └── (same layout as facebook/)
├── analysis/                     ← shared learnings + competitive analysis
│   ├── LEARNINGS.md
│   └── wispr-flow-cta-analysis.xlsx
└── tools/
    ├── rehydrate.py              ← pull one competitor's media down from R2
    └── log_and_commit.sh         ← after a run: stamp RUN_LOG + links manifest + commit
```

## Daily workflow

1. `git pull` — get the latest (seconds; it's small).
2. **Claim a competitor nobody else is doing.** Each competitor has its own
   master file, so two people on different competitors never clash.
3. Run the pipeline:
   - **Step 1 (scrape):** Facebook → Claude-in-Chrome; Google → `python3 scripts/scrape_google_ads.py` (on your Mac).
   - **Steps 2–4** (download / R2 upload / AI analysis) → on **your Mac's Terminal**.
     The Cowork sandbox can't reach Facebook's CDN, R2, YouTube, or the AI API.
4. Need media a teammate processed? `python3 tools/rehydrate.py --pipeline facebook --competitor <slug>` — pulls it from R2, not a 60 GB transfer.
5. Finish: `tools/log_and_commit.sh <pipeline> <competitor> "<your name>" "<note>"` then `git push`.

## Rules that keep it clean

- **One competitor per person at a time.**
- **Never hand-edit a master CSV** — the pipeline owns it.
- **Never commit `.env`** — each person keeps their own (it's gitignored).
- **Don't worry about empty `videos/`/`images/` folders** — rehydrate from R2 on demand.
- **Write down learnings** in `analysis/LEARNINGS.md` as you go.

## Google rate-limit guardrail

The Google scraper enforces a cadence policy (default: 1 competitor/run, 24 h
between runs, 24 h cooldown after a 429) and logs every run to
`google/logs/scrape_history.jsonl`. Check status with
`python3 scripts/scrape_guardrail.py status`. See `google/HANDOVER.md` →
"Rate-limit operating policy".

## Every generated link is preserved

Every R2 link the pipeline creates — source asset, both Word docs, and all
Step-4 image arrays — lives in the committed master CSV (and, per run, in
`{pipeline}/runs/{competitor}_{date}_links.json`). The heavy files stay in R2.
Nothing is lost; everything stays one click away.
