# Google Competitor Ads Pipeline

End-to-end pipeline to refresh competitor-ad data from Google's Ads
Transparency Center: scrape every advertiser's ads → download videos and
images → upload to Cloudflare R2 → AI-analyse and produce two Word documents
per ad. Recurring weekly/fortnightly process. Sibling pipeline to
`~/Documents/fb-ad-downloader/`.

> **🇮🇳 India-only ads.** The scraper passes `region=IN` to Google's API, so
> only ads shown in India are returned. Advertisers themselves can be
> verified in any country — Duolingo Inc is US-verified, Busuu Limited is
> UK, Loora is Israel — because global brands run India ads through
> non-India legal entities. See `HANDOVER.md §3` for the verified-AR list.

> **Pipeline switched on 2026-06-01.** Step 1 used to be a JavaScript prompt
> pasted into the Claude-in-Chrome extension. It is now a Python script that
> talks to Google's underlying API directly — no browser, no DOM scraping,
> no AI inference during the scrape itself. The old prompts are kept in
> `archive/` for historical reference only. **Do not paste them anywhere.**

> **⛔ Rate-limit guardrail (new).** The scraper now refuses to run if it would
> breach the rate-limit operating policy (default: **1 competitor/run, 24 h
> between runs, 24 h cooldown after a 429**). Check status any time with
> `python3 scripts/scrape_guardrail.py status`. Full policy + how to tune it:
> `HANDOVER.md` → "Rate-limit operating policy". Override (at your own risk)
> with `--force`.

## Start here

👉 **Open `HANDOVER.md`** — single source of truth: setup, how to run each
step, output schemas, common failures, troubleshooting.

👉 **First-time setup?** Run `pip3 install --user -r requirements.txt`, then
copy `.env.template` → `.env` and fill in your R2 + Gemini credentials.
HANDOVER §1 walks through both.

👉 If you've operated the FB pipeline (`fb-ad-downloader/`), most of the
mental model carries over. The big difference is Step 1: Google has a
public-but-undocumented API we hit directly, whereas Facebook needs `yt-dlp`'s
`facebook:ads` extractor.

## Manual run — one competitor at a time (if you need to)

In normal use, you don't run individual steps. The wrapper above does
everything. But if you need to invoke a single step (debugging, testing a
new competitor, fixing one master CSV), here are the bare commands:

```bash
cd ~/Desktop/google-ad-downloader

# Step 1 — scrape one competitor (~1-10 min)
python3 scripts/scrape_google_ads.py --competitor "SpeakX" --region IN --out .

# Step 2 — yt-dlp metadata enrichment (~30s)
python3 scripts/download_google_ads.py "inputs/g-ads-speakx-$(date +%F).csv" \
    --videos-out "./videos/speakx-$(date +%F)/" \
    --images-out "./images/speakx-$(date +%F)/" \
    --batch-size 600

# Step 3 — upload assets to R2 + update master CSV (~30s)
python3 scripts/upload_to_r2.py \
    --input  "inputs/g-ads-speakx-$(date +%F).csv" \
    --videos "videos/speakx-$(date +%F)/" \
    --images "images/speakx-$(date +%F)/"

# HTML5 banner capture (only for rows tagged html5-banner-no-mp4)
python3 scripts/capture_html5_banners.py --competitor speakx
# After capture, re-run Step 3 to upload the new mp4s

# Creative Studio — AI analysis (optional, gated by cost estimate)
python3 scripts/estimate_step4_cost.py --competitor speakx --all
# Review the estimate, then run stages 1-6 if approved — see HANDOVER §7
```

## Quick start — all 9 competitors, one command

**This is the way you should run the pipeline.** Paste once, walk away,
come back to a complete master.

```bash
cd ~/Desktop/google-ad-downloader
bash run_all_competitors.sh
```

That command runs four passes end-to-end:

1. **Pass 1** — Steps 1+2+3 + YouTube metadata backfill, for every
   competitor. ~1 hour.
2. **Pass 2** — wait 30 min for Google's anti-abuse cooldown, then retry
   any competitor that hit a 429. One retry only. ~40 min if needed.
3. **Pass 3** — HTML5 banner capture for every `html5-banner-no-mp4` row
   in the master, via headless Chromium. ~6-8 hours.
4. **Pass 4** — re-upload to R2 so the captured HTML5 mp4s land at
   `r2_public_url`. ~5 min.

Default total: ~8-10 hours for a fresh, complete run. Tail
`logs/run-all-*.log` from a second terminal to watch progress.

For faster, lighter runs use the opt-out flags:

```bash
bash run_all_competitors.sh --quick           # Steps 1+2+3 only, ~1 hour
bash run_all_competitors.sh --skip-html5      # no Pass 3/4, ~1.5 hours
bash run_all_competitors.sh --skip-retry      # no Pass 2, ~7-8 hours
```

The HTML5 capture pass is auto-skipped if Playwright isn't installed.
First-time setup for the HTML5 pass:

```bash
pip3 install --user playwright
python3 -m playwright install chromium    # ~150 MB download, one-time
brew install ffmpeg                       # if not already installed
```

## Folder layout

```
google-ad-downloader/
├── README.md                          ← you are here
├── HANDOVER.md                        ← full operator walkthrough, read this next
├── requirements.txt                   ← pip3 install --user -r requirements.txt
├── run_all_competitors.sh             ← "do everything" wrapper for Steps 1+2+3
├── .env                               ← R2 + Gemini credentials (gitignored)
├── .env.template                      ← shows which keys go in .env
├── .gitignore
│
├── scripts/                           ← all four pipeline steps
│   ├── scrape_google_ads.py           ← Step 1 — Google API → CSV + assets
│   ├── download_google_ads.py         ← Step 2 — yt-dlp metadata sidecars
│   ├── upload_to_r2.py                ← Step 3 — R2 upload + master CSV
│   ├── estimate_step4_cost.py         ← Creative Studio stage 0 — cost estimate (free)
│   ├── step4_decompose.py             ← Creative Studio stage 1 — Gemini Batch decompose
│   ├── step4_frames.py                ← Creative Studio stage 2 — ffmpeg scene-frame extract
│   ├── step4_character_sheets.py      ← Creative Studio stage 3 — Nano Banana character sheets
│   ├── step4_panels.py                ← Creative Studio stage 4 — Nano Banana clean panels
│   ├── step4_rewrite.py               ← Creative Studio stage 5 — Gemini Batch Supernova rewrite
│   ├── step4_upload_images.py         ← Creative Studio stage 6a — image upload to R2
│   ├── step4_build_docs.py            ← Creative Studio stage 6b — build .docx with captions
│   ├── step4_audit_docs.py            ← Creative Studio stage 7a — strict programmatic audit
│   └── step4_upload_and_update.py     ← Creative Studio stage 8 — R2 docx upload + master update
│
├── skills/                            ← how-to docs per pipeline step
│   ├── ARCHITECTURE.md                ← design rationale, read first if editing skills
│   ├── google-ads-pipeline/           ← master orchestrator (weekly refresh)
│   ├── google-ad-scraper/             ← Step 1 docs
│   ├── google-ads-download-and-upload/ ← Steps 2 + 3 docs
│   └── google-ads-video-analysis/     ← Creative Studio docs
│
├── archive/                           ← old Chrome-extension prompts (do not use)
│   ├── README.md                      ← explains why these are here
│   ├── scraper_prompt.md
│   └── find_advertiser_ids_prompt.md
│
├── inputs/                            ← per-run input CSVs from Step 1
│   └── g-ads-{competitor}-{date}.csv
├── videos/{competitor}-{date}/        ← .mp4 + .info.json sidecars
├── images/{competitor}-{date}/        ← .jpg / .png banner images
├── master/{competitor}.csv            ← rolling per-competitor truth (Step 3+ owns columns)
├── step3_logs/                        ← per-row upload outcome
├── step4_workspace/                   ← created on first Creative Studio run
└── logs/                              ← run_all_competitors.sh wrapper logs
```

## The 4 pipeline steps

| Step | Script | What it does |
|---|---|---|
| 1. Scrape | `scrape_google_ads.py` | Hits Google's `SearchService` / `LookupService` RPC endpoints, pulls every creative for each advertiser, downloads videos (signed googlevideo.com mp4) and images (simgad/googlesyndication), writes a 28-column CSV |
| 2. Enrich | `download_google_ads.py` | Walks the CSV from Step 1, runs `yt-dlp --write-info-json` on the youtube_video_url for every video row to produce a `.info.json` sidecar with title, description, channel, duration. (Step 1 already downloaded the mp4s, so this stage is mostly metadata-only.) |
| 3. Upload | `upload_to_r2.py` | Uploads every mp4 + image to Cloudflare R2, writes/updates `master/{competitor}.csv` with `r2_public_url` per row + YouTube metadata from the sidecar |
| 4. Analyse | `step4_*.py` | Gemini Pro decomposes each video into scenes + characters, Nano Banana Pro regenerates clean panel imagery + character reference sheets, Gemini rewrites the script in Supernova's voice, builds two .docx per ad (competitor analysis + rewrite), uploads docs to R2, back-fills two URL columns in the master |

## Where each step runs

| Step | Runs in | Why |
|---|---|---|
| 1. Scrape | Your Mac's Terminal | Talks to Google API; needs your IP + network |
| 2. Enrich | Your Mac's Terminal | `yt-dlp` needs reliable YouTube access |
| 3. Upload | Your Mac's Terminal | `boto3` needs Cloudflare R2 — Cowork sandbox proxy returns 403 |
| 4. Analyse | Your Mac's Terminal *or* Cowork | Gemini API works from either |

Cowork is best used for editing scripts/docs, inspecting CSVs and logs, and
running Creative Studio (which is mostly remote API work). The data-movement steps
(1, 2, 3) run on your Mac because they need your network and credentials.
See `HANDOVER.md §1` for the full reasoning.

## Where to read next

- `HANDOVER.md` — full operator walkthrough, troubleshooting, current
  pipeline state, list of known bugs and workarounds
- `skills/ARCHITECTURE.md` — why the pipeline is split this way; the
  reasoning behind the API-direct Step 1 vs the historical Chrome scrape
- `skills/google-ads-pipeline/SKILL.md` — the master skill a Cowork agent
  invokes to refresh all competitors end-to-end
