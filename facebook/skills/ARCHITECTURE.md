# Skill architecture — three skills, one pipeline

This document is the single source of truth for *why the skill structure is shaped this way*. Anyone editing the skills should read this first. The operator-facing how-to lives in `HANDOVER.md` §17 and in each skill's own `SKILL.md`.

## The big picture

```
                       Operator
                          │
                          ▼
              ┌───────────────────────┐
              │   fb-ads-pipeline     │   ← master skill (Cowork enters here)
              │   (orchestrator)      │
              └─────────┬─────────────┘
                        │
        ┌───────────────┴───────────────────┐
        ▼                                   ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│ fb-ads-download-and-     │    │  fb-ads-video-analysis      │
│ upload                   │    │  (Step 4)                   │
│ (Steps 2 + 3)            │    │                             │
│                          │    │  • cost estimate + gate     │
│  CSV in → videos out     │    │  • decompose + frames +     │
│  → R2 URLs in master     │    │    sheets + panels          │
│                          │    │  • Supernova rewrite        │
│                          │    │  • 2 docx per video         │
│                          │    │  • R2 upload of docs        │
│                          │    │  • verification + review    │
└──────────────────────────┘    └─────────────────────────────┘
```

Step 1 (scraping) is **not** a skill in Cowork — it runs in the operator's Claude-in-Chrome standalone session (the Chrome extension drives Meta Ad Library directly). The CSV it produces is the input to the pipeline. During Step 1, facebook.com is a restricted site so Claude requests approval for every JS execution (~30-40 per 30-ad page); the operator can auto-approve only the facebook.com popup with `facebook/scripts/fb_allow_clicker.py` (run from a standalone Terminal, needs Screen Recording + Accessibility) — full setup in `HANDOVER.md §6.8`. This is optional and does not affect the CSV the pipeline consumes.

## Why three skills, not one

Two arguments shape the split:

1. **Different cost profiles**. Steps 2+3 are essentially free (just disk + R2 storage). Step 4 burns Gemini Pro + Nano Banana Pro per video — meaningful money. Keeping them in separate skills lets the master interpose a *cost estimate + approval gate* between the cheap deterministic stages and the expensive AI stages. The operator gets to see exactly how much Step 4 will cost before authorizing it.

2. **Different invocation patterns**. The download-and-upload sub-skill is the right unit to invoke on its own when you only want raw videos in R2 — e.g. you're feeding videos to a separate skill, or just stocking the bucket without doing analysis. The video-analysis sub-skill is the right unit when the videos are already in R2 (from a previous run) and you only want to refresh the analysis. The master skill is the right unit when you're doing the full weekly/fortnightly refresh from scratch.

## Skill responsibilities — strict boundaries

### `fb-ads-pipeline` (master)

**One job:** orchestrate. It owns no business logic.

- Asks the operator for the Step 1 CSV (file upload in chat, or a path)
- Invokes `fb-ads-download-and-upload` with that CSV
- Surfaces that sub-skill's tally
- Asks the operator: "ready to estimate Step 4 cost?" — and *waits for explicit yes*
- Invokes `fb-ads-video-analysis` with the chosen scope (random N rows, all rows, filtered subset)
- Surfaces the final tally including R2 URLs for all generated docs

If the operator only needs Steps 2+3, they invoke `fb-ads-download-and-upload` directly. If they only need Step 4 against the existing master, they invoke `fb-ads-video-analysis` directly. The master is the convenience wrapper.

### `fb-ads-download-and-upload` (Steps 2 + 3)

**One job:** turn a Step 1 CSV into a master CSV with `r2_public_url` filled in for every video row.

It wraps the existing two scripts:

- `scripts/download_fb_ads.py` (downloads videos via yt-dlp into `videos/{competitor}-{date}/`)
- `scripts/upload_to_r2.py` (uploads to R2, maintains `master/{competitor}.csv`, idempotent)

The skill's SKILL.md describes the invocation, the chunked-resume behaviour (Cowork bash cap), and the post-rename column schema. It does **not** touch Gemini, image generation, or document building.

### `fb-ads-video-analysis` (Step 4)

**One job:** for every row in `master/{competitor}.csv` whose `competitor_analysis_docx_r2_url` and `supernova_rewrite_docx_r2_url` are empty, produce two analysis docs and back-fill those columns.

Pipeline stages it owns:

| Stage | Engine | Per-video cost band | Failure mode |
|---|---|---|---|
| 0. Cost estimate + operator approval gate | Local Python (no API call) | $0 | Operator declines → skill exits cleanly |
| 1. Decompose video → structured JSON | Gemini 3.1 Pro Batch API | ~$0.035 | Truncated JSON → retry with bumped `max_output_tokens` |
| 1'. Decompose image-only ad → structured JSON | Gemini 3.1 Pro (sync, no batch needed for one frame) | ~$0.01 | Same |
| 2. Extract frame screenshots (source-native resolution, `-q:v 2`) | ffmpeg, local | $0 | Codec issue → skip with log |
| 3. Generate character reference sheets (Nano Banana Pro @ **2K**, 1:1) | Nano Banana Pro, parallel-sync | ~$0.04/char | Content-policy block → keep going |
| 4. Generate clean panel imagery (Nano Banana Pro @ **2K**, aspect-matched to source) | Nano Banana Pro, parallel-sync | ~$0.04/panel | Content-policy block → fall back to original screenshot |
| **4.5. Upload images to R2 + write `r2_urls.json` sidecar** | boto3, local | $0 | Network → retry; idempotent re-upload |
| 5. Supernova rewrite | Gemini 3.1 Pro Batch API | ~$0.02 | Truncated JSON → retry |
| 6. Build two `.docx` files (each image followed by an `Asset: <R2 URL>` hyperlink caption) + programmatic + Claude verification | python-docx, local + model | $0 (verify negligible) | Quality fail → mark row needs-rerun, don't upload |
| 7. Upload docs to R2 | boto3, local | $0 | Network → retry |
| 8. Update master CSV (doc URLs + 3 JSON-array image URL columns) | Local | $0 | — |
| Audit. HEAD-check every URL in docs + master | `scripts/step4_audit.py` | $0 | Any non-200 → flag for re-run |

### Strict rule: the analysis sub-skill never modifies `videos/`, `inputs/`, or any non-master CSV. It only reads from `master/`, writes intermediate state to its own `step4_workspace/`, and updates five columns in the master at the end (`competitor_analysis_docx_r2_url`, `supernova_rewrite_docx_r2_url`, `orig_frame_urls`, `gen_panel_urls`, `char_sheet_urls`) plus the `latest_scrape_run_date` cell.

## How the cost-estimate-and-approval gate works (Step 4)

This is the single most important UX requirement from the operator side.

When `fb-ads-video-analysis` is invoked, BEFORE any Gemini API call fires:

1. Read the master CSV
2. Identify candidate rows (missing one or both docx URLs)
3. Apply the operator's scope flag (`--random N`, `--all`, `--ids X,Y,Z`)
4. For each candidate row, compute an estimated cost:
   - Video duration (from local file via `ffprobe`, or fallback assumption ~30s)
   - Estimated scene count (~1 scene per 6s, capped at 12)
   - Estimated character count (~2)
   - Decompose: tokens × Gemini Pro pricing
   - Sheets: char_count × Nano Banana Pro pricing
   - Panels: scene_count × Nano Banana Pro pricing
   - Rewrite: tokens × Gemini Pro pricing
5. Present the operator with:
   - Per-row cost (or a histogram if many rows)
   - Total batch cost
   - Wall-clock estimate
   - "Approve? (yes / N to reduce / cancel)" prompt via AskUserQuestion
6. Only on explicit "yes" does the actual processing begin

This gate is *the* operator safety net. It makes "accidentally burn $200 on a misclick" impossible.

## How verification works at every stage (Step 4)

Goal: never end up with a 90%-empty docx after 1–2 hours of compute. Detect failures early; flag quality issues; never silently publish bad output.

After each stage, the orchestrator runs `verify_stage_<N>.py` which checks:

- **After decompose**: every row has a sidecar JSON, JSON parses, scenes ≥ 1, every scene has non-empty `audio_transcript` (for video ads) or `on_screen_text` (for image ads), character roster ≥ 1
- **After frames**: exactly `len(scenes)` `orig_NN.jpg` files per row, each > 20 KB, valid JPEG header (raised from 5 KB — high-resolution frames should never be that small)
- **After sheets**: one sheet per declared character, each > 50 KB, recognizable image (no error PNG)
- **After panels**: one panel per scene-panel, log any content-policy blocks (acceptable), retry transient errors once
- **After Stage 4.5 (image upload)**: every `frames/<id>/orig_NN.jpg`, `images/<id>/gen_*.jpg`, and `images/<id>/char_*_sheet.jpg` has a key under `images/<ad_library_id>/...` in R2; `step4_workspace/images/<id>/r2_urls.json` exists; every URL it lists begins with `R2_PUBLIC_URL_BASE`
- **After rewrite**: same scene count as decompose, every scene has non-empty `supernova_script`, no `TODO` / `<INSERT>` / `<UNKNOWN>` placeholders
- **After docx build**: open the docx with python-docx, paragraph count > minimum, **image count == `Asset:` caption count** (HANDOVER §9.7), no `[missing — Stage 4.5 not run...]` captions, no empty headings, no placeholder strings
- **After Claude review of docx**: the orchestrator opens both docs and asks the model to review for grammatical errors, broken English, obviously bad image generations, missing sections. Quality verdict goes into the per-row log.
- **Audit step (after Stage 8)**: `scripts/step4_audit.py` HEAD-checks every URL embedded as an `Asset:` hyperlink and every URL recorded in `orig_frame_urls` / `gen_panel_urls` / `char_sheet_urls` / `competitor_analysis_docx_r2_url` / `supernova_rewrite_docx_r2_url`. Drift between docx hyperlinks and master columns is reported.

A row only gets uploaded to R2 + written into the master when **every** verification gate passes. Otherwise the row is logged as `quality-fail-needs-rerun` and the orchestrator continues with other rows.

## The five master columns added by Step 4

Added by Step 4 on top of the 39-column post-Step-3 master (= 36 scraper + 3
Step-3 columns), bringing the final schema to **44 columns**. Declared in
`MASTER_EXTRA_COLS` in `scripts/upload_to_r2.py` so they survive Step-3 re-runs:

| Column | Type | What it contains |
|---|---|---|
| `competitor_analysis_docx_r2_url` | string | Public R2 URL of Doc 1 (the scene-by-scene competitor analysis) |
| `supernova_rewrite_docx_r2_url` | string | Public R2 URL of Doc 2 (the Supernova-voice rewrite of the script) |
| `orig_frame_urls` | JSON string (array) | R2 URLs of every original scene frame in scene order |
| `gen_panel_urls` | JSON string (array) | R2 URLs of every regenerated clean panel in scene+position order |
| `char_sheet_urls` | JSON string (array) | R2 URLs of every character reference sheet, sorted by character id |

R2 key naming:

- Docs (flat namespace, historical convention):
  - `{ad_library_id}_competitor_analysis.docx`
  - `{ad_library_id}_supernova_rewrite.docx`
  - For variants: `{ad_library_id}_v{N+1}_competitor_analysis.docx` and `_supernova_rewrite.docx` (not honoured by the script yet — known limitation).
- Per-ad images (HANDOVER §9.7), foldered under one prefix per ad so a single
  consumer can list every asset for an ad with one `list_objects_v2(Prefix=...)`:
  - `images/{ad_library_id}/orig_{NN}.jpg` — original scene frames
  - `images/{ad_library_id}/gen_{NN}_{pos}.jpg` — regenerated clean panels
  - `images/{ad_library_id}/char_{X}_sheet.jpg` — character reference sheets

The image-URL columns and folder layout exist so downstream ad-creation
automation can pull every asset for an ad without having to crack open the
`.docx`. The docs still embed the images themselves; the URL captions are
purely a machine-readable handle.

## Image-only ads — the single-page treatment

For master rows with `ad_media_type=Image`:

- Doc 1 (competitor analysis): single page with the ad's image embedded, the `ad_primary_text` / `ad_description` / `ad_cta_label` verbatim, plus a brief AI-generated description of what the image conveys
- Doc 2 (Supernova rewrite): single page with a regenerated brand-safe image (or the original if regeneration is blocked) + Supernova-voice rewrite of the ad copy

Image fetch: Step 4 will re-resolve the image fresh from `ad_library_url` at processing time (the scraper's `facebook_thumbnail_cdn_url_at_scrape` is stale by then). Caches to `images/{competitor}-{date}/{ad_library_id}.jpg` so re-runs skip the fetch.

## Where intermediate state lives

```
fb-ad-downloader/
└── step4_workspace/                                NEW — owned by fb-ads-video-analysis
    ├── .gemini_uploads/<id>.json                   Gemini Files API references (48h TTL)
    ├── batches/
    │   ├── decompose_<short>.json                  Active/completed Gemini batch job state
    │   └── rewrite_<short>.json                    Same for Supernova rewrite
    ├── scenes/
    │   ├── <id>.json                               Decompose sidecar
    │   └── <id>.supernova.json                     Rewrite sidecar
    ├── frames/<id>/orig_NN.jpg                     Scene screenshots (source-native res)
    ├── images/<id>/                                Character sheets + clean panels (2K)
    │   ├── char_<X>_sheet.jpg
    │   ├── gen_NN_<pos>.jpg
    │   └── r2_urls.json                            Stage 4.5 sidecar — image → R2 URL map
    ├── docs/                                       Built before R2 upload
    │   ├── <id>_competitor_analysis.docx           (each image has an "Asset:" caption)
    │   └── <id>_supernova_rewrite.docx
    └── logs/                                       Per-run audit trail
        └── step4-{competitor}-{YYYY-MM-DD-HHMM}.log
```

Once a doc is uploaded to R2 and its URL is in the master, the local `.docx` in `step4_workspace/docs/` can be deleted (the R2 copy is the canonical version). Intermediate JSONs + images are kept indefinitely so re-runs can skip work.

## API key handling

Same `.env` file we already use for R2. Step 4 reads:

- `GEMINI_API_KEY` — from `.env` or environment

When the key is missing, the analysis skill refuses to run with a clear error message pointing the operator to where to put the key. The cost estimator (Stage 0) works without the key — that's intentional, so the operator can preview cost before bothering with credentials.

## When to break this architecture

The skill structure should hold up unless one of these changes:

- We start running Step 1 in Cowork (today it's in Claude-in-Chrome standalone). If that ever happens, add a `fb-ads-scrape` sub-skill and the master picks up another stage.
- We add a Step 5 (push the master to a DB). That becomes a third sub-skill; the master gains another stage.
- The cost-estimate-then-approval pattern becomes operator-burdensome. If Step 4 ends up running on small fixed-cost batches (e.g. always 5 videos), the gate could move from `fb-ads-video-analysis` itself into the master only.

Until one of those triggers, this is the shape.
