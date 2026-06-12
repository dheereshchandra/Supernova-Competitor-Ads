# Session Handoff — Competitor-Ad Analysis System

> Running status so this work can resume in any workspace. Last updated 2026-06-12.
> Read this first, then the linked docs.

## What this project is
A competitor-ad intelligence system (Facebook + Google) for Supernova. It scrapes
each competitor's live ads, tracks how they perform **over time**, and answers 12
strategic questions (volume, format mix, winners/losers, run-days, win-ratios,
script similarity & replication, FB↔Google transfer). Git holds the small precious
text (scripts, master CSVs with R2 links, the analysis); Cloudflare R2 holds the
heavy media. See `README.md` (collaboration model) and `analysis/README.md` (the
analysis system + run recipes).

## 🆕 2026-06-12 — Ad Studio is PUBLIC (Tailscale Funnel) + failure alerts

**Hosting — LIVE.** The Ad Studio web app (`webapp/`, see PRs #53–#65) is publicly
reachable at **https://dheeresh.tail92accf.ts.net** — a **Tailscale Funnel** on the
operator's Mac (operator's personal tailnet; the company tailnet blocked Funnel —
no admin). Cloudflare was abandoned: the `gosupernova.live` DNS zone sits in an
inaccessible Cloudflare account. Teammates need NO install — URL + shared
`STUDIO_PASSWORD` (the only gate; the URL is open internet, share privately).
Durability: hostname is permanent; `tailscale funnel --bg 8787` persists across
reboot/daemon restarts; backend launchd (`live.gosupernova.ad-studio`) is
KeepAlive+RunAtLoad. Only manual step: after a FileVault cold reboot, log into the
Mac once. Lid-closed serving needs `sudo pmset -c sleep 0` + `sudo pmset -a
disablesleep 1`. When the Mac is unreachable the frontend shows the "😴 offline —
ping Dheeresh" overlay (PR #65) and auto-reconnects. Full runbook:
`webapp/install/README.md` §3–4. `STUDIO_PUBLIC_URL` in `.env` = the ts.net URL
(feeds the Sheet's "Open in Ad Studio" links).

**Failure alerts — ONE shared notifier.** `tools/notify/notify.sh` posts a macOS
banner + a Slack message (when `SLACK_WEBHOOK_URL` is set in `.env` — create an
Incoming Webhook at api.slack.com/apps). Wired into: daily-scrape (per-competitor
FAIL, push-fail, end-of-run summary when blocked/failed>0), daily-sync +
csv-sync + capture-sync (their existing notify() now goes through it), and the
Ad Studio backend (`webapp/backend/notify.py` — generation-job failures, pipeline
scrape-blocked/failed, enrichment failures). App-DOWN alerting can't come from the
Mac itself — use an external uptime monitor (e.g. UptimeRobot free) on
`https://dheeresh.tail92accf.ts.net/api/health`.

## 🆕 2026-06-09/10 — the big build-out (PRs #21–#42). READ THIS FIRST TO RESUME.

**1. Enrichment hardened + run at scale (PRs #21–#34).** `transcribe_tag.py` is now concurrent
(`--workers`, default 6) with a per-video hard timeout and **valid-JSON via `response_schema`**
(controlled generation — fixed ~90% parse failures); rehydrate dedups across dated folders; lenient
JSON parsing in `_flash.py`. **MySivi fully enriched: 2,005 ads / 1,937 transcripts**, all committed.
Strategy outputs: `analysis/reports/mysivi_strategy_memo.md` (senior-analyst teardown — Marathi lever,
translate>copy, fear-shame underused, AI-presenter wins, whitespace) + the auto
`2026-06-09_mysivi_facebook_strategic.md`. Orchestrator `analysis/scripts/run_pipeline.sh` (#22) runs
Steps 1→6 staged with a typed cost gate; `tools/capture-sync/` (#23) is a daily launchd job that
auto-captures fresh snapshots before CDN expiry.

**2. Creative Studio prompt overhaul (the "subjective feedback" bucket) — PRs #35–#37.**
- **#35 creative context (feedback #3+#4):** `facebook/generation/supernova_creative_context.md` is the
  single source of truth (who Supernova/Miss Nova are, the 7-beat payload — lead with personalization +
  privacy, hook families, format library, DON'Ts, wide-latitude mandate; built from a teardown of 35
  winning Supernova ads). `step4_rewrite.py` loads it at runtime; governing rule = **keep the
  competitor ad's proven visual shell, re-pitch only the message**. Eval harness:
  `facebook/generation/gen_test.py` (5-seed divergence battery).
- **#36 brand safety (feedback #5):** `facebook/generation/supernova_brand_safety.md` (7 guardrail
  categories, SEVERE/MODERATE) + `step4_safety_check.py` — an independent Flash audit per script
  (verdict computed deterministically: any SEVERE→block). Also baked into the generation prompt.
- **#37 India casting + Miss Nova (feedback #8):** `facebook/scripts/_casting.py` + both image stages —
  every human re-cast authentically Indian (foreign source descriptions override), settings localised;
  the AI teacher renders as **Miss Nova** (3D orange-suit mascot; PLACEHOLDER art in
  `facebook/generation/assets/miss_nova/` — swap when brand assets arrive, no code change).

**3. Collaborative Google Docs — Stage 9 (PR #38) + one-time Google setup DONE.**
`step4_upload_gdocs.py` converts both deliverable .docx into native Google Docs in a **Shared Drive**
("Supernova Competitor Docs", id `0AKmBubqd4DqGUk9PVA`), anyone-with-link edit, links into master
(`supernova_rewrite_gdoc_url`, `competitor_analysis_gdoc_url`). Idempotency = collaboration protection
(git-tracked sidecar `scenes/<id>.gdocs.json`; re-runs reuse, `--force` creates v2). The Google side is
LIVE: GCP project `supernova-gdocs`, service account `supernova-gdocs@supernova-gdocs.iam.gserviceaccount.com`
(key at `~/.config/supernova/gdrive-sa.json`, NEVER in the repo), Drive API + **Sheets API enabled**,
SA = Content Manager of the Shared Drive. Setup walkthrough: `facebook/HANDOVER.md §9.10`.

**4. Top-5 MySivi Creative Studio run — LIVE END-TO-END (PR #39).** The 5 longest-running winners went
through decompose → new-prompt rewrite → India-cast visuals → docs → **10 collaborative Google Docs**
(13/13 audit green; payload_audit shows personalization+privacy beats, Miss Nova named, ₹3 price
stripped). Data committed (master gdoc links + sidecars).

**5. NAMING RULE (also #39):** "Step N" = ONLY the canonical 6-step pipeline (Step 4 = Free Analysis,
free/no-AI). The generation workflow is **Creative Studio** — never "a Step"; its scripts keep the
legacy `step4_` prefix. Published in `CLAUDE.md`; docs aligned repo-wide. Plus `video_path_for`/
`image_path_for` now search ALL dated media folders (decompose/build_docs/frames).

**6. Team Google Sheet auto-sync (PRs #40–#42) — LIVE.** `tools/csv-sync/` upserts the analysis into
ONE spreadsheet **"Supernova Competitor Master"**
(https://docs.google.com/spreadsheets/d/1Iy6gKifge9Y2B1kwXZL2nd3r2xCudB0HB9UNYzyxxRI/edit — id also in
`tools/csv-sync/sheet_id.json`): tabs **Overview** (21 self-explanatory cols, one row per ad, all
competitors — verdict/status/ranks/% Time in Top 25%/language/format/angle/price + video & doc links),
**Analysis** (36-col pivot dataset), **Legend** (auto-generated column definitions). Upsert never
reorders rows or touches team-added columns. launchd `live.gosupernova.csv-sync` runs **11:45 + 19:00**
from the canonical clone (installed + verified green). Column renames: edit `OVERVIEW_COLS`/
`ANALYSIS_COLS`/`COLUMN_DEFS` in `sync_to_sheets.py`, run once with `--rebuild`.
- Gotchas burned in: launchd has a **minimal PATH** (sync.sh exports `/opt/homebrew/bin`); preflight
  must run from `facebook/`; **the runner clone's `.env` needs the 4 GDRIVE keys**; `install.sh`'s
  `chmod +x` used to dirty the clone and silently block `git pull` (modes now committed 755).

**Still open (the short list):** feedback **#6** structured brief/input system (brainstormed, not built);
**Miss Nova real brand assets** (placeholder in use); English-vs-Hinglish base script decision;
wire `step4_safety_check.py` as a blocking gate in the pipeline; A2 per-version transcription (deferred —
FB versions proved byte-identical); R2 public URLs return 403 (pre-existing; Google Docs sidestep it);
`estimate_step4_cost.py`/`run_step4.py` still use newest-folder-only video lookup (non-critical).

## ✅ BUILT & MERGED (PRs #1–#6) — fully working
The whole analysis system is on `main` and validated end-to-end on a real Mac.

**Free rank pipeline** — canonical Step 4, Free Analysis (free, no AI) — (`analysis/scripts/`, no API):
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
4. Daily auto-sync (one-time): `zsh tools/daily-sync/install.sh` — keeps your canonical clone up to date at 11:30 AM daily.
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

## 🧪 BENCH — terminal Facebook scraper V2 (payload interception, 2026-06-10)
Goal: move the FB scrape off Claude-in-Chrome to a pure terminal command (Google is
already terminal). **Status: V2 BUILT and smoke-tested — now in a PARALLEL-RUN
window.** Production scrape **remains Claude-in-Chrome** (`scraper_prompt.md` v2.3)
until V2 passes same-day diffs. Bar (operator's, unchanged): every field matches a
Claude-in-Chrome scrape, zero misses — not just ad-id recall.

**What V2 is** — `facebook/scripts/fb_scrape_v2.py`: drives the same listing URL with
Playwright but reads the STRUCTURED JSON the page itself receives (server-embedded
first batch + every `AdLibrarySearchPaginationQuery` XHR via `page.on("response")`)
instead of parsing the rendered DOM (which is what the old, still-PAUSED
`fb_scrape.py` did and why it mis-read dates/text). Key discovery (probe 2026-06-10):
each search edge is a *collation* whose `collated_results[]` are the ad's VERSIONS —
full nodes with own id/unix dates/text/cta/link/platforms/media. So the v2.3
"Pass 3" (the detail-view click-walk that makes Claude runs take 10–24 h) arrives
free with the listing. Emits the full 36-column v2.3 schema; `-v2`-suffixed
filenames are structurally invisible to `build_history.py`'s snapshot regex, so
bench CSVs can NEVER pollute the time series. Official Ad Library API was confirmed
unusable (non-EU commercial ads excluded, per Meta's own docs).

**Smoke test (Duolingo, 2026-06-10, headless, ~50 s):** audit PASS · 30/30 recall ·
31 rows (1 multi-version ad expanded with per-version ids+dates) · 23 V / 8 I ·
100% media-URL fill (no hover) · cross-date diff vs the 06-04 Claude CSV:
**zero MISS on every field**; old killer bugs gone (`ad_primary_text` 100%,
`ad_media_type` 100%, `creative_count_in_ad` 100%); V2 filled start_date /
destination_url / platforms / 5 CTAs where the old CSV was blank.

**Parallel-run day 1 (SpeakX, 2026-06-10 — V2 side only):**
`fb-ads-speakx-2026-06-10-1636-v2.csv` (committed) — audit PASS · 170 rows /
168 ads / 2 multi-version expanded · 0 blank thumbnails. No same-day Claude run
was made, so the only possible diff was cross-date vs the 06-04 (pre-v2.3) CSV:
**zero MISS again**; 89% recall + 16 extra ads = 6 days of ad churn, not a
recall bug; the mismatches cluster exactly on the open items below —
`has_low_impression_warning` ×24 (badges may legitimately decay as impressions
accrue; only a same-day diff settles item 2), `ad_version_count` ×2,
`ad_primary_text` ×32 (ref text looks like title-block capture / DCO rotation).
NEW check item: SpeakX page `104428871316786` ("SpeakX English") is absent from
BOTH the 06-04 Claude CSV and the 06-10 V2 run → likely just 0 active ads;
confirm via the per-page log on the next same-day run. **Day-2 blocker: a
same-day Claude-in-Chrome run (SpeakX or MySivi) → `fb_scrape_diff.py` → fix
every MISS/mismatch.**

**Parallel-run day 2 (MySivi, 2026-06-10 — same-day V2 vs a partial Claude ref):**
operator ran a partial Claude-in-Chrome scrape (page-1 top ~20 ads = 5 multi-version
ads, 21 rows) and a same-day V2 page-1 run. The diff exposed — and we FIXED — two
real V2 bugs, both validated to clean against the reference:
- **Version grouping (the big one).** On MySivi, Meta ships an ad's versions as
  SEPARATE top-level search results that share a `collation_id` (with empty
  `collated_results[]`), NOT nested. V2 read only `collated_results[]`, so it
  emitted each version as its own single-version "ad" — 907 phantom ads, every
  multi-version ad flagged `ad_version_count=1`. FIX: `find_ad_nodes` +
  group-by-`collation_id` in `collations_from_sources` (lead/version-0 = first in
  impression order = the grid card Claude scrapes). Result: 907→**650 real ads,
  140 multi-version**, version sets + per-version dates/CTA/URL match the reference
  exactly. Handles BOTH payload shapes (Duolingo's nested collations still 30/30,
  unchanged — no regression).
- **Date off-by-one.** Payload timestamps are midnight US-Pacific; Meta's
  "Started running on" (what Claude reads) is the day BEFORE, in both PST and PDT.
  FIX: `DATE_SHIFT_DAYS=-1`. All 5 ref ads' dates now agree (were 0/5).
- **Diff tool:** versions now matched by stable `version_id`, not positional
  `version_index` (the two scrapers enumerate versions in different orders).
- **Residual diff flags are all REFERENCE artifacts, not V2 misses:** (a) ad
  `914613221634852` — Claude emitted 2 identical duplicate rows with body text
  "Open Dropdown" (a UI label) and blank version_ids; Meta says `collation_count=1`
  and V2 correctly emits 1 real version. (b) `ad_primary_text`/`description`
  "mismatches" — V2 maps Meta's `body`→primary (full text) and `title`→description
  faithfully; Claude TRUNCATED the body and misattributed its tail as the
  description, missing the real title. **V2 is strictly more correct on both.**
  Net: zero V2 data loss/error on the overlap; remaining flags are Claude
  DOM-scraping artifacts. Takeaway: Claude-in-Chrome is NOT a perfect golden
  reference — V2 (payload) corrects some of its truncation/duplication.

**Parallel-run protocol (next few days):** for each competitor scraped, run BOTH
(Claude-in-Chrome as production + `python3.13 facebook/scripts/fb_scrape_v2.py
"<Competitor>"`), then
`python3.13 facebook/scripts/fb_scrape_diff.py <v2_csv> <claude_csv>` (now 4-class:
agree / richer / MISS / mismatch, version-grain aware). Fix every MISS/mismatch;
cut over per-competitor only on CLEAN verdicts.

**Open bench items (validate on same-day diffs):**
1. ✅ RESOLVED (day 2): `DATE_TZ`/`DATE_SHIFT_DAYS` — dates are midnight US-Pacific;
   Claude shows the day before → `DATE_SHIFT_DAYS=-1`. 5/5 same-day MySivi ads agree.
   Re-validate as more same-day diffs land (calibrated on one page, one moment).
2. `has_low_impression_warning`: read from the card badge via a zero-click DOM pass;
   payload-field mapping still unknown (`--debug` records candidates per ad —
   needs a page that actually has badges, Duolingo had none).
3. ✅ RESOLVED (day 2): large/scattered collations — versions arrive as separate
   top-level results sharing a `collation_id`; group-by-`collation_id` recovers
   all of them from the listing (MySivi page 1: 140 multi-version ads, 0 residual
   truncations). No deeplink fallback needed.
4. `creative_aspect_ratio`: V2 computes from preview-image pixels; one cross-date
   variant seen (`1200x628` vs ref `1.91:1` — bucket naming, single ad).
5. DCO ads: payload exposes ALL card variants; default `--dco-mode card` mimics
   Claude (lead variant only); decide later whether to switch to `full` (richer).
6. Coverage gap inherited from the PROMPT's map: Duolingo English Test page
   `1829461027108598` (33 ads on 06-04) is in neither the prompt's
   COMPETITOR_PAGES nor V2's — re-add to BOTH if it should be tracked.

(Historical: the DOM-based `fb_scrape.py` + `fb_scrape_probe.py` stay committed,
PAUSED, unwired — superseded by V2 but kept for the probe + driver lineage. Old
DOM-era misses for the record: start_date off-by-one, wrong primary_text block,
missing page_rank — all root-caused by rendered-DOM parsing and all structurally
fixed in V2 by reading the payload.)

## 🔀 PR history (all merged)
#1 Phase 1 (free rank) · #2 Phase 0+2 (Google snapshots + Flash enrichment) ·
#3 Phase 3 (script replication + FB↔Google) · #4 ops (Google seed + runners) ·
#5 authenticated R2 + smart-quote tolerance · #6 .env found anywhere ·
#7 FB scrape probe · #8 first-cut terminal FB scraper · #9 handoff doc + scraper v2 ·
#10 IST timezone + full-field diff · #11 drop locale (fixed 0-ads) ·
#12 pause terminal scraper + save learnings.
New tool (2026-06-08): `facebook/scripts/fb_allow_clicker.py` — FB permission auto-clicker (see section above).
**2026-06-09/10:** #21 B2/B3/B7 capture metrics · #22 staged orchestrator `run_pipeline.sh` ·
#23 capture-sync launchd · #24 B5/B6/B9 replica/pHash/language · #26 hang-guard · #27 A1
version-aware dedup · #28 lenient JSON · #29 thread-timeout · #30 version view · #31 HTML output +
English/structured prompt · #32 transcribe concurrency · #33 rehydrate cross-date dedup ·
#34 response_schema valid-JSON · #35 Supernova creative context (feedback #3+#4) · #36 brand-safety
guardrails + Flash audit (#5) · #37 India casting + Miss Nova (#8) · #38 Stage 9 Google Docs ·
#39 top-5 run + Creative Studio naming + video_path_for fix · #40 csv-sync Google Sheet ·
#41 launchd PATH/cwd hotfix · #42 readable sheet columns + Legend tab.

## 📌 Open decisions / later
- Format taxonomy: re-author a clean schema (the seed CSV is Supernova's own ads).
- ">95% script match" threshold + similarity thresholds: calibrate on real data.
- Inactive-ad scraping (sore_loser tier) — designed, not built (see addendum).
- Real Google scrapes to build Google longevity (currently ~2 days only).
