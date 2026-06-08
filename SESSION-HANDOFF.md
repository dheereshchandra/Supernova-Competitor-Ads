# Session Handoff — Competitor-Ad Analysis System

> Running status so this work can resume in any workspace. Last updated 2026-06-08.
> Read this first, then the linked docs.

## What this project is
A competitor-ad intelligence system (Facebook + Google) for Supernova. It scrapes
each competitor's live ads, tracks how they perform **over time**, and answers 12
strategic questions (volume, format mix, winners/losers, run-days, win-ratios,
script similarity & replication, FB↔Google transfer). Git holds the small precious
text (scripts, master CSVs with R2 links, the analysis); Cloudflare R2 holds the
heavy media. See `README.md` (collaboration model) and `analysis/README.md` (the
analysis system + run recipes).

## ✅ BUILT & MERGED (PRs #1–#6) — fully working
The whole analysis system is on `main` and validated end-to-end on a real Mac.

**Free rank pipeline** (`analysis/scripts/`, no API):
`build_history.py` (dated snapshots → append-only per-competitor rank history;
`--backfill` for FB, `--from-master` for Google) → `compute_rank_metrics.py`
(winners/losers via 4 tiers: strong_winner >45d & ≥½ life top-25%; winner ≥15d &
top-10/10%; loser gone-&-never-won; sore_loser=inactive[inert]; +new/undecided;
retired winners keep `is_retired`) → `build_rank_chart.py` (wide rank pivot = the
chart) → `build_report.py` (markdown review). `run_all_free.sh <pipeline>` = all
competitors.

**Paid enrichment** — Gemini **Flash ONLY, never Pro** (hard cost rule):
`detect_language.py`, `transcribe_tag.py` (1 Flash call/video → transcript +
format + language, cached/idempotent), `embed_scripts.py`, `script_cluster.py`
(script_group_id + replication_type), `fb_google_overlap.py` (FB↔Google transfer).
`run_enrichment.sh <pipeline> <competitor> [--full]` chains it all (defaults to a
cheap `--limit 5` calibration); `preflight_enrichment.py` gates it. Outputs land in
`analysis/{enrichment,derived,reports}/` and are committed (teammates reuse
transcripts → never re-pay).

**Design docs:** `.context/rank-tracking-brainstorm.md` + `-addendum-inactive.md`
(workspace-local). Gap analysis of the 12 questions is in the plan file / memory.

## ✅ Operationally validated (on the operator's Mac)
- **Facebook Duolingo**: full enrichment run + pushed (40 transcripts, by_language/
  by_format/by_replication). Insights: app-screencast-heavy; heavy script reuse
  (17 visual_variants, 5 exact_replicas vs 12 unique); originals win more than copies.
- **Google Duolingo**: full enrichment run + pushed (19 video transcripts). Mostly
  `new` verdicts (Google has only ~2 days of history; longevity needs more scrapes).

## 🆕 NEW (2026-06-08) — Facebook permission auto-clicker
`fb_allow_clicker.py` (`facebook/scripts/fb_allow_clicker.py`) is a macOS Vision-OCR
background watcher that auto-approves the Claude-in-Chrome **"Allow this action"**
popup during the FB scrape. facebook.com is a **RESTRICTED** site so the extension
prompts for **EVERY** JS execution (30–40 clicks per 30-ad page; upstream bug
`anthropics/claude-code#55124`). Makes the **current** Claude-in-Chrome method less
manual — it does **not** replace it.

Run from a **STANDALONE Terminal.app** (not Conductor's built-in terminal), started
**before** the scrape, **Ctrl-C** when done:
```bash
python3.13 facebook/scripts/fb_allow_clicker.py        # for real
# validate first: python3.13 facebook/scripts/fb_allow_clicker.py --dry-run
# extra flags: --any-app  --verbose
```
- **One-time deps:** `python3.13 -m pip install --user --break-system-packages pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa`
- **One-time macOS permissions** (granted to the Terminal that launches it): **Screen
  Recording** + **Accessibility** (Cmd-Q + reopen Terminal after granting).
- **Safeguards:** clicks **only** the facebook.com "Allow this action" button under 6
  simultaneous conditions; never Decline / Always-allow.
- Full operator reference: `facebook/HANDOVER.md §6.8`; onboarding driver: root
  `CLAUDE.md` + `Supernova-Handoff-Package/START-HERE.md`.

(Unrelated to the PAUSED `fb_scrape.py` terminal-scraper experiment below — that work
stays separate.)

## 🆕 NEW (2026-06-08) — FB scraper v2.3: VERSION-EXPANSION
The FB scraper is now **v2.3** with **version-expansion**: a **36-column** schema and
**one row per `(ad_library_id, version_index, creative_index_in_ad)`**.
- **Row grain:** `version_index` is **0-based** (like `creative_index_in_ad`).
  Single-version ads have `version_index=0` on every row, with the `version_*` fields
  copying the `ad_*` baseline. `ad_version_count` = number of **distinct**
  `version_index` values for the ad (the real enumerated count).
- **Columns are additive:** the existing `ad_*` columns (`ad_primary_text`,
  `ad_cta_label`, `ad_media_type`, the CDN urls, etc.) are **RETAINED** as the
  card / version-0 baseline; new `version_*` columns hold per-version detail. Old
  masters without `version_index` read **blank** and coerce to **0**.
- **Downstream wiring:** `build_history.py` collapse now **folds `version_index`**
  (rank stays **one row per ad**); `upload_to_r2.py`'s key is now a **3-tuple**.
- **Scope of first release:** keeps **one transcript per ad** (no Flash cost increase).
  **Per-version transcription** and **per-version media download** are flagged
  **follow-ups** (not in this release).

## How to run (the everyday rhythm)
```bash
cd <repo>
git pull
bash analysis/scripts/run_enrichment.sh facebook <competitor> --full
git add -A && git commit -m "enrichment: <competitor> facebook" && git push
```
Full from-scratch workflow (scrape→download→R2→analyze→push), incl. the FB
Claude-in-Chrome scrape and the Google CLI scrape: see chat / `facebook/HANDOVER.md`
+ `google/README.md`. Quick map:
- **FB scrape** = Claude-in-Chrome (paste `facebook/scraper_prompt.md`) → `inputs/`.
- **Google scrape** = `python3 scripts/scrape_google_ads.py --competitor X --region IN`
  (Terminal; ⛔ guardrail: 1 competitor/run, 24h gaps).
- Download/upload: `download_*_ads.py` → `upload_to_r2.py`.
- Then the analysis rhythm above.

## ⚙️ Setup on a fresh Mac
1. `pip3.13 install --user --break-system-packages google-genai numpy boto3 yt-dlp`
2. `.env` with R2 + Gemini keys — put it at **repo root** (works for everything) and/or
   `facebook/.env`. **Do NOT wrap values in quotes** (Mac smart-quotes break the API;
   the loaders now strip them, but bare values are safest).
3. `python3.13 facebook/scripts/preflight.py` and
   `python3.13 analysis/scripts/preflight_enrichment.py` → both READY.
4. Daily auto-sync (one-time): `zsh tools/daily-sync/install.sh` — keeps your canonical clone up to date at 9 AM daily.
   The committed templates live in `tools/daily-sync/` (`sync.sh`, `install.sh`, `uninstall.sh`, `live.gosupernova.repo-sync.plist.template`, `README.md`); pull-only (never pushes/resets — skips + notifies if main is dirty/ahead/diverged). Supersedes the old machine-only sync job (see memory `daily-repo-sync-launchd.md`).

## 🩹 Operational gotchas hit & fixed (so the friend won't)
- **Smart quotes in `.env`** → `'ascii' codec can't encode '”'`. Fixed: loaders
  strip curly quotes (PR #5). Use bare values.
- **R2 403 on rehydrate** → bucket public access is off. Fixed: `rehydrate.py`
  downloads **authenticated** via R2 keys (PR #5); finds `.env` in any folder (PR #6).
- **Flash model name**: `gemini-flash-latest` works; embeddings `gemini-embedding-001`.
- **git push rejected (non-fast-forward)** → `git pull --no-rebase` then `git push`
  (if a merge editor opens and you close it blank, run `git commit --no-edit`).
- **`page_id` unstable across FB scrapes** (ewa) → presence judged at competitor level
  by `ad_id`. **Master CSVs are latest-only** → time series comes from dated `inputs/`.

## 📁 Data locations
- **Git (committed):** scripts, `*/master/*.csv` (R2 links), `*/inputs/*.csv` (FB
  snapshots; Google now too), `analysis/{history,derived,reports,enrichment}/`.
- **R2 (durable media):** videos/images/docs, referenced by `r2_public_url` in masters.
- **Local cache (gitignored):** `{facebook,google}/{videos,images}/{slug}-{date}/`.
  Pull on demand: `python3 tools/rehydrate.py --pipeline facebook --competitor X`.

## ⏸️ PAUSED — terminal Facebook scraper experiment (parked 2026-06-07)
Goal was to move the FB scrape off Claude-in-Chrome to a pure terminal command
(Google is already terminal). **DECISION: PAUSED — keep Claude-in-Chrome as the FB
scrape method for now.** A same-day benchmark found real field-level misses, so it's
not production-ready. Work is committed + documented so it resumes from here —
**do NOT restart from scratch.** Bar (operator's): every field matches a
Claude-in-Chrome scrape, zero misses — not just ad-id recall.

Files (committed, EXPERIMENTAL, NOT wired into the pipeline):
- `facebook/scripts/fb_scrape_probe.py` (PR #7) — proved Meta lets a Playwright
  browser load the ads (no anti-bot block). ✅
- `facebook/scripts/fb_scrape.py` (PRs #8–#11) — Playwright scraper: reuses the
  competitor→page map + navigate URL + scroll; climbs to the full ad card; hovers to
  load media + CDN; `--debug` dumps first card to `fb_card_debug.html`; prints fill-rates.
- `facebook/scripts/fb_scrape_diff.py` — per-page, per-field fidelity diff vs a
  Claude-in-Chrome CSV (case/space-insensitive; prints a sample mismatch per field).

**What WORKS** (validated vs a same-day Claude-in-Chrome scrape of Duolingo, 30 ads):
✅ anti-bot beatable · ✅ 100% ad recall (30/30 ad_library_ids) · ✅ `ad_media_type`
correct (8 Image + 22 Video) · ✅ `ad_version_count`, `has_low_impression_warning`
match · ✅ CDN video URLs captured (22/30) via hover.

**What's BROKEN** (remaining work to hit zero-miss):
1. **`ad_start_date` off by ONE day** (terminal `2026-02-06` vs Claude `2026-02-05`).
   NOT timezone (`timezone_id=Asia/Kolkata` didn't change it; `locale=en-IN` broke
   rendering → 0 ads, removed). Likely the regex grabs the wrong date text. Need the
   card innerText to fix.
2. **`ad_primary_text` grabs the wrong block** (terminal pulled body "Duolingo is the
   world's #1…"; Claude has headline "Free language learning"). "Longest text block"
   heuristic is wrong — need the card structure to pick the right node.
3. **`page_rank` column missing** — Claude schema = 27 cols incl. `page_rank` (col 2);
   fb_scrape.py emits 26. Easy fix: per-page 1-based counter. (build_history computes
   page_rank locally anyway, so analysis isn't blocked.)
4. Untested/likely: carousel `creative_index` splitting; agreement on `ad_description`/
   `ad_cta_label`/`ad_destination_url`/`ad_distribution_platforms`/`facebook_page_followers`;
   per-page mapping gaps (Duolingo English Test page `1829461027108598` not in
   COMPETITOR_PAGES — but today's Claude scrape also got only the 1 mapped page, so
   that's a shared mapping limit, not a scraper diff).

**To RESUME (don't restart):**
1. `python3.13 facebook/scripts/fb_scrape.py "Duolingo" --debug` → share `fb_card_debug.html`.
2. From the card HTML: fix the start_date regex + primary_text selector; add page_rank col.
3. Re-run + `fb_scrape_diff.py <terminal_csv> <same-day-claude_csv>` until every field ~100%.
4. If the DOM stays fragile, capture Meta's GraphQL/AJAX responses (structured data)
   instead of scraping the rendered DOM — more robust.
5. Once faithful: add mapping pages + carousel splitting, then wire it in as FB Step 1.

## 🔀 PR history (all merged)
#1 Phase 1 (free rank) · #2 Phase 0+2 (Google snapshots + Flash enrichment) ·
#3 Phase 3 (script replication + FB↔Google) · #4 ops (Google seed + runners) ·
#5 authenticated R2 + smart-quote tolerance · #6 .env found anywhere ·
#7 FB scrape probe · #8 first-cut terminal FB scraper · #9 handoff doc + scraper v2 ·
#10 IST timezone + full-field diff · #11 drop locale (fixed 0-ads) ·
#12 pause terminal scraper + save learnings (this doc).
New tool (2026-06-08): `facebook/scripts/fb_allow_clicker.py` — FB permission auto-clicker (see section above).

## 📌 Open decisions / later
- Format taxonomy: re-author a clean schema (the seed CSV is Supernova's own ads).
- ">95% script match" threshold + similarity thresholds: calibrate on real data.
- Inactive-ad scraping (sore_loser tier) — designed, not built (see addendum).
- Real Google scrapes to build Google longevity (currently ~2 days only).
