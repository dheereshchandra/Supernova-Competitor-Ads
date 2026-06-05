---
name: google-ads-pipeline
description: >-
  Master skill for the Supernova Google competitor-ads pipeline. Orchestrates
  the end-to-end flow: invokes the google-ad-scraper sub-skill (Step 1 — CLI
  scraper against Google's Ads Transparency Center API), the
  google-ads-download-and-upload sub-skill (Steps 2 + 3 — yt-dlp metadata,
  R2 upload, master CSV update), then the google-ads-video-analysis sub-skill
  (Step 4 — scene decomposition for video, single-page treatment for image,
  text-only branch for Text ads, two docx per ad, gated by a
  cost-estimate-and-approval step). Use when the operator wants the full
  weekly/fortnightly refresh for a competitor — phrasings like "run the full
  Google pipeline on Zinglish", "refresh Google ads for SpeakX end-to-end",
  "do the whole thing for Duolingo Google". Don't use if the operator only
  wants a single step — invoke the relevant sub-skill directly instead.
---

# Master pipeline — end-to-end Google competitor-ads refresh

This skill is the convenience wrapper for a full weekly/fortnightly refresh cycle. It does no work itself — it sequences three sub-skills with a cost-approval gate before the most expensive one.

See `../ARCHITECTURE.md` for the architectural rationale. See the three sub-skills' SKILL.md files for the actual work each one does.

> **⛔ Step 1 is rate-limit gated.** Before any Google scrape, run
> `python3 scripts/scrape_guardrail.py status`. If it reports BLOCKED, do not
> scrape — report when the next run is allowed and stop. Policy defaults:
> 1 competitor/run, 24 h between runs, 24 h cooldown after a 429. The scraper
> enforces this automatically and logs every run to
> `logs/scrape_history.jsonl`. See `../../HANDOVER.md` → "Rate-limit operating
> policy".

## When to invoke this skill (and when not to)

**Invoke when** the operator wants the full refresh — competitor name(s) in, master CSV updated with R2 URLs *and* analysis docs in, end of story. Phrasings:

- *"Run the full Google pipeline for SpeakX"*
- *"Refresh Duolingo Google ads end-to-end"*
- *"Run steps 1 through 4 on Memrise Google"*
- *"Do the whole Google pipeline for these competitors"*

**Don't invoke when**:

- Operator only wants Step 1 (just the CSV + asset download) → use `google-ad-scraper`
- Operator only wants Steps 2+3 (no analysis) → use `google-ads-download-and-upload`
- Operator only wants Step 4 against existing master rows → use `google-ads-video-analysis`
- This is about Meta/FB ads, not Google ads → switch to `~/Documents/fb-ad-downloader/`

**For the operator running things from Terminal directly** (the most common case), they don't invoke skills at all — they run a single command:

```bash
bash run_all_competitors.sh
```

That wrapper does the same four passes this skill orchestrates (Steps 1+2+3 → 429 retry → HTML5 capture → final R2 re-upload) without a Cowork agent in the loop. See `../../HANDOVER.md §8`. The skills exist for Cowork-mediated invocations where an agent is driving the work end-to-end and may need to ask the operator for input (e.g. cost approval before Step 4).

## The shape of a master-skill run

```
┌─ Operator says: "run the full Google pipeline for {competitors}" ─┐
│                                                                   │
│  Phase A — Setup                                                  │
│  ────────────                                                     │
│  Ask which competitors (or default to all 9)                      │
│  Sanity-check .env has R2 + GEMINI_API_KEY                        │
│                                                                   │
│  Phase B — Step 1 (google-ad-scraper)                             │
│  ───────────────────────────                                      │
│  Invoke sub-skill per competitor                                  │
│  Surface per-competitor tally (CSV rows + downloaded assets)      │
│  Track which competitors hit 429 / scrape-error for Phase B'      │
│                                                                   │
│  Phase B' — 429 retry (if any competitor was blocked)             │
│  ─────────────────────────────                                    │
│  Wait 30 min for Google anti-abuse cooldown                       │
│  Retry Step 1 once for blocked competitors                        │
│  If still blocked: surface, ask whether to defer or continue      │
│                                                                   │
│  Phase C — Steps 2+3 (google-ads-download-and-upload)             │
│  ────────────────────────────────────                             │
│  Invoke sub-skill per fresh Step 1 CSV                            │
│  Surface tally (uploaded / carried-forward / text-no-asset)       │
│                                                                   │
│  Phase C' — HTML5 banner capture (optional)                       │
│  ──────────────────────────────                                   │
│  For every master row tagged 'html5-banner-no-mp4':               │
│    Render in headless Chromium, record as mp4                     │
│    Update error_tag → 'html5-captured-locally'                    │
│  Then re-invoke google-ads-download-and-upload to push captures  │
│  to R2 and fill r2_public_url                                     │
│                                                                   │
│  Phase D — Cost gate                                              │
│  ────────────────                                                 │
│  Read master/{competitor}.csv                                     │
│  Identify candidate Step 4 rows                                   │
│  Ask scope: random N / all / specific IDs                         │
│  Run scripts/estimate_step4_cost.py — pure local math             │
│  Show per-row breakdown + batch total + wall-clock                │
│  Ask: approve / reduce / cancel                                   │
│  WAIT for explicit yes                                            │
│                                                                   │
│  Phase E — Step 4 (google-ads-video-analysis)                     │
│  ──────────────────────────────                                   │
│  Invoke sub-skill with approved scope                             │
│  Stream stage-by-stage progress                                   │
│                                                                   │
│  Phase F — Final report                                           │
│  ──────────────────                                               │
│  Per-competitor: rows in master, R2 URLs, docs, cost, time        │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Phase A — Setup

1. **Ask which competitors to refresh.** Default to all 9 in
   `scripts/scrape_google_ads.py`'s `COMPETITOR_ADVERTISERS` map if the
   operator says "everyone". Otherwise take a list.

2. **Sanity-check `.env`.** R2 credentials are required for Steps 2+3.
   `GEMINI_API_KEY` is required for Step 4. If Gemini is missing, surface:
   > *"Step 4 requires a Gemini API key. Steps 1-3 will still run, but
   > Step 4 will be skipped. Continue, or pause until the key is available?"*

## Phase B — Invoke `google-ad-scraper` per competitor

For each competitor, hand off control with the competitor name. When
complete, capture per-competitor tally:

- CSV row count
- Videos downloaded
- Images downloaded
- Rate-limit / scrape-error count (if any)

If a competitor hits a persistent 429 (Google's anti-abuse block), surface
the issue and ask whether to skip that one and continue with others, retry
from a different network, or pause the whole run. Don't force-retry — the
block lifts on its own time.

## Phase C — Invoke `google-ads-download-and-upload` per CSV

For each successful Step 1 CSV from Phase B, hand off control with the CSV
path. When complete, capture the tally:

- Total rows processed
- Videos uploaded (YouTubeVideo format)
- Images uploaded (Image format)
- Text rows skipped (`text-no-asset`)
- Asset-missing (HTML5 banners with no extractable mp4 — expected)
- Errors

Surface compactly. Don't proceed automatically — pause for the operator.

If a sub-skill failed mid-way, surface the error and ask whether to retry
or stop. Don't push to Step 4 if Step 3 didn't finish cleanly.

## Phase D — Cost gate (the critical UX moment)

After Phase C completes for every competitor (or the operator picks one):

1. Open `master/{competitor}.csv`. Identify rows where one or both docx
   URLs are blank AND `creative_format` is analysable (YouTubeVideo /
   Image / Text). Rows with format=Shopping/Maps are only candidates if
   they have an `r2_public_url`.

2. Tell the operator:
   > *"All Step 2+3 work is done. {competitor} master has {V} videos +
   > {I} images in R2, {T} text-only ads with copy ready, and {N} rows
   > total that haven't been analysed yet. How many should I run analysis on?"*

3. Ask via AskUserQuestion:
   - *"All {N} rows"*
   - *"Variant 0 of each distinct creative only (Recommended)"* — avoids
     paying 3x for near-identical variant analyses
   - *"A random sample of 5"* — for first runs
   - *"Specific IDs I'll provide"*
   - *"Cancel — only run Steps 1-3 this time"*

4. Invoke `google-ads-video-analysis`'s Stage 0 cost estimator with the
   chosen scope. **No API calls — purely local math.**

5. Surface the cost estimate in the format defined in
   `google-ads-video-analysis/SKILL.md` Stage 0.

6. Ask the operator for explicit approval via AskUserQuestion:
   - *"Approve and run"*
   - *"Reduce the scope"* (back to step 3)
   - *"Cancel"*

7. Only on explicit *"Approve and run"* do you proceed to Phase E.

## Phase E — Invoke `google-ads-video-analysis`

Hand off control with the approved scope. Resumable and chunked — likely 20–60 min wall-clock dominated by Gemini Batch queue + image generation.

While the sub-skill runs, surface progress milestones at stage transitions (not per row):

- "Decompose batch submitted — polling"
- "Decompose complete — verifying"
- "Frame extraction complete"
- "Character sheets — N/M done"
- "Panels — N/M done"
- "Supernova rewrite submitted"
- "Building docx files"
- "Reviewing each doc for quality"
- "Uploading to R2"
- "Done"

## Phase F — Final report

```
google-ads-pipeline — run complete
─────────────────────────────────────────────────
Phase B (Step 1 scrape):
  Memrise        ✅  3 rows
  Loora          ✅  4 rows
  Praktika AI    ✅  82 rows
  Busuu          ✅  87 rows
  Speak          ✅  77 rows
  SpeakX         ✅  383 rows
  Duolingo       ✅  743 rows (230 scrape-error from 429)
  English Seekho ❌  blocked by 429
  ...

Phase C (Steps 2+3):
  • Videos uploaded:        18
  • Images uploaded:        201
  • Text-no-asset:          6
  • Asset-missing:          ~556  (HTML5 banners, expected)
  • Errors:                 0

Phase E (Step 4):
  • Rows analysed:          3 (variant 0 of each distinct creative)
  • Both docs uploaded:     3
  • Actual cost:            $1.34
  • Wall-clock:             12 min

Artefacts:
  • master/*.csv (8 competitors updated)
  • step4_workspace/logs/step4-{competitor}-{date}.log
```

## Hard rules (don't violate)

- **Never proceed past Phase D without explicit operator approval.** The cost gate is sacred.
- **Never invoke `google-ads-video-analysis` if Phase C failed.** Step 4 has no value without Step 3's URLs in the master.
- **Never invent a Gemini API key** — if missing, ask explicitly or offer to run only Phases A-C.
- **Never invoke sub-skills with scopes the operator didn't approve.** If they said "variant 0 of each", don't process all variants.
- **Never mix Google and Meta workflows in the same skill invocation.** Each pipeline has its own folder, its own skill set, its own master CSV.
- **If Phase B hits a persistent 429 for a competitor, skip that one and continue.** Don't burn an hour retrying a blocked IP. Report the gap in Phase F.

## Resume behaviour

- If Cowork session is killed during Phase B (scraping), re-invoke — Step 1 is idempotent for already-downloaded assets and the CSV gets rewritten cleanly.
- If killed during Phase C (Steps 2+3), the sub-skill resumes from the master CSV (carry-forward logic).
- If killed during Phase E (Step 4), the sub-skill resumes cleanly (intermediate JSONs + image files are the recovery state).
- If the operator deferred Phase E until later, they can invoke `google-ads-video-analysis` directly later — no need to re-run Phases A-C.

## Cross-references

- `../ARCHITECTURE.md` — architectural rationale
- `../google-ad-scraper/SKILL.md` — Phase B sub-skill (Step 1)
- `../google-ads-download-and-upload/SKILL.md` — Phase C sub-skill (Steps 2+3)
- `../google-ads-video-analysis/SKILL.md` — Phase E sub-skill (Step 4)
- `../../HANDOVER.md` — operator manual for the whole pipeline
- `../../run_all_competitors.sh` — the Bash wrapper an operator runs from Terminal for the same end-to-end refresh
- `~/Documents/fb-ad-downloader/skills/fb-ads-pipeline/SKILL.md` — sibling pipeline for Meta ads
