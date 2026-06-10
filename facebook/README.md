# FB Competitor Ads Pipeline

The end-to-end pipeline used at Supernova to refresh competitor-ad data: scrape Meta Ad Library → download videos → upload to R2 → AI-analyse and produce two Word documents per ad. Recurring weekly/fortnightly process.

## Start here

👉 **Open `HANDOVER.md`** — it's the single source of truth. Setup, how to run each step, what the outputs look like, common failures, troubleshooting, and §17 for the three-skill architecture.

👉 If you're editing the skills themselves, **read `skills/ARCHITECTURE.md` first** — it explains why the pipeline is split into three skills and what each one is responsible for.

## What's in this folder

```
fb-competitor-ads-pipeline/
├── README.md                            ← you are here
├── HANDOVER.md                          ← single source of truth — read this next
├── scraper_prompt.md                    ← Step 1: paste this into Claude-in-Chrome
├── SKILL.md                             ← legacy upstream Step 2 skill (reference only)
├── .env                                 ← R2 + Gemini credentials (gitignored)
├── .gitignore
│
├── skills/                              ← The three Cowork skills
│   ├── ARCHITECTURE.md                  ← design rationale, read first if editing skills
│   ├── fb-ads-pipeline/                 ← master orchestrator skill
│   │   └── SKILL.md
│   ├── fb-ads-download-and-upload/      ← Steps 2 + 3 sub-skill
│   │   └── SKILL.md
│   └── fb-ads-video-analysis/           ← Creative Studio sub-skill (scene analysis)
│       ├── SKILL.md
│       └── scripts/                     ← Creative Studio helper scripts (to be filled in
│                                          when GEMINI_API_KEY arrives)
│
├── scripts/                             ← All pipeline scripts
│   ├── r2_utils.py                      ← shared R2 client / upload helpers / image key conventions
│   ├── download_fb_ads.py               ← Step 2 — videos from Meta CDN
│   ├── upload_to_r2.py                  ← Step 3 — videos → R2 + master CSV (declares MASTER_EXTRA_COLS)
│   ├── estimate_step4_cost.py           ← Creative Studio cost estimator (no API call, free)
│   ├── run_step4.py                     ← Creative Studio high-level orchestrator scaffold
│   ├── step4_decompose.py               ← Creative Studio Stage 1 — Gemini Batch video decompose
│   ├── step4_frames.py                  ← Creative Studio Stage 2 — ffmpeg scene-frame extract (source-native res)
│   ├── step4_character_sheets.py        ← Creative Studio Stage 3 — Nano Banana Pro char sheets @ 2K
│   ├── step4_panels.py                  ← Creative Studio Stage 4 — Nano Banana Pro clean panels @ 2K
│   ├── step4_upload_images.py           ← Creative Studio Stage 4.5 — upload every image to R2 + r2_urls.json sidecar
│   ├── step4_rewrite.py                 ← Creative Studio Stage 5 — Gemini Batch Supernova rewrite
│   ├── step4_build_docs.py              ← Creative Studio Stage 6 — assemble the two docx files (Asset: URL captions)
│   ├── step4_upload_and_update.py       ← Creative Studio Stages 7+8 — R2 upload + master update (5 URL columns)
│   ├── step4_audit.py                   ← Creative Studio audit — HEAD-checks every URL in docs + master
│   └── backfill_step4_images.py         ← One-shot: re-process existing docs to add image URLs
│
├── inputs/                              ← per-run input CSVs (from Step 1)
│   └── fb-ads-{competitor}-{date}.csv
├── videos/{competitor}-{date}/          ← .mp4 files from Step 2
├── master/{competitor}.csv              ← rolling per-competitor truth (all steps own columns)
├── step3_logs/                          ← per-run upload logs from Step 3
└── step4_workspace/                     ← created on first Creative Studio run
    ├── .gemini_uploads/<competitor>.json   Gemini Files API state for resume
    ├── batches/decompose_<short>.json      Active/completed Gemini batch jobs
    ├── batches/rewrite_<short>.json
    ├── scenes/<id>.json                    Decompose sidecar (the structured analysis)
    ├── scenes/<id>.supernova.json          Supernova-voice rewrite sidecar
    ├── frames/<id>/orig_NN.jpg             Original scene screenshots (source-native resolution)
    ├── images/<id>/char_X_sheet.jpg        Character reference sheets (2K)
    ├── images/<id>/gen_NN_pos.jpg          Clean regenerated panel imagery (2K)
    ├── images/<id>/r2_urls.json            Stage 4.5 sidecar: image → R2 URL map
    ├── docs/<id>_competitor_analysis.docx  Final deliverable Doc 1 (Asset: URL beneath each image)
    ├── docs/<id>_supernova_rewrite.docx    Final deliverable Doc 2 (Asset: URL beneath each image)
    └── logs/                               Per-run Creative Studio audit trail
```

### Final master CSV — Creative Studio columns

| Column | Type | Owner |
|---|---|---|
| `competitor_analysis_docx_r2_url` | string | Stage 7+8 |
| `supernova_rewrite_docx_r2_url`   | string | Stage 7+8 |
| `orig_frame_urls`                 | JSON array of strings | Stage 4.5 → Stage 8 |
| `gen_panel_urls`                  | JSON array of strings | Stage 4.5 → Stage 8 |
| `char_sheet_urls`                 | JSON array of strings | Stage 4.5 → Stage 8 |

See `HANDOVER.md §9.7` for the full URL contract.

## The 4 steps

1. **Scrape** — operator runs `scraper_prompt.md` in Claude-in-Chrome standalone, gets a CSV
   - While scraping, Meta asks Claude to approve every JS step (~30-40 per 30-ad page). Automate with `facebook/scripts/fb_allow_clicker.py` (run from a standalone Terminal.app, not Conductor; needs Screen Recording + Accessibility) — see `HANDOVER.md §6.8`.
2. **Download** — `scripts/download_fb_ads.py` saves every video locally
3. **R2 upload** — `scripts/upload_to_r2.py` uploads to R2, maintains per-competitor master CSV
4. **AI analysis** — the `scripts/step4_*.py` family (one script per stage of the 9-stage pipeline, plus `step4_audit.py` and `backfill_step4_images.py`) and the `fb-ads-video-analysis` skill produce **two Word documents per ad** (competitor analysis + Supernova-voice rewrite), upload every per-scene image to R2 (originals, regenerated panels, character sheets, all @ 2K), embed an `Asset: <R2 URL>` hyperlink caption beneath every picture in the docs, then upload both docs to R2 and back-fill **five** URL columns in the master (two doc URLs + three JSON arrays of image URLs). Final HEAD-check audit confirms every recorded URL resolves. Validated end-to-end on 5 Zinglish ads, $1.00 actual cost.

## Running the pipeline — three entry points

**End-to-end (most common)**: tell Cowork *"run the full pipeline on this CSV"* — invokes the `fb-ads-pipeline` master skill which runs Steps 2+3, asks for cost approval, then runs Creative Studio.

**Just download + upload (videos in R2, no analysis)**: tell Cowork *"run the downloader and upload on `inputs/fb-ads-{competitor}-{date}.csv`"* — invokes the `fb-ads-download-and-upload` sub-skill directly.

**Just analysis (videos already in R2)**: tell Cowork *"analyse 5 random ads from the Zinglish master"* — invokes the `fb-ads-video-analysis` sub-skill directly. Still subject to its internal cost-approval gate.

Read `HANDOVER.md §17` for full details on the three-skill model and `skills/ARCHITECTURE.md` for the design rationale.
