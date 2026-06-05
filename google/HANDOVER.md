# Handover: Google Competitor Ads Pipeline

A practical guide to running the end-to-end pipeline that turns competitors'
Google Ads Transparency Center listings into one row per ad in a master CSV,
with assets in R2 and AI-generated analysis docs back-filled per row. Read
this once end-to-end, then keep it around as a reference.

> **🇮🇳 India-only ads.** The scraper passes `region=IN` to Google's
> internal API, so the master CSVs only contain ads shown in India.
> **Advertisers** themselves can be legally registered anywhere — Duolingo
> Inc is US-verified, Busuu Limited is UK, Loora A.I is Israel — because
> global brands run India ads through non-India legal entities. The
> verified-AR map in §3 keeps these. The India filter is applied at scrape
> time, not at discovery. See §12 for the rationale.

> **Pipeline switched to CLI on 2026-06-01.** Step 1 used to be a JavaScript
> prompt pasted into the Claude-in-Chrome extension that scraped the rendered
> SPA via a hidden iframe. It is now a Python CLI script that talks to
> Google's underlying `SearchService` / `LookupService` RPC endpoints
> directly. The same data, an order of magnitude cheaper and faster, with no
> AI inference during the scrape and no browser involvement. The old prompts
> live in `archive/` for reference only — do not paste them anywhere.

This document is **the single source of truth** for the operator. If
something here disagrees with anything else in the folder, this document
wins — flag the conflict to the maintainer.

The pipeline is a sibling to `~/Documents/fb-ad-downloader/`. The
architectural model is identical (cost-gated Step 4, idempotent + resumable
scripts, master CSV per competitor), so if you've operated that folder,
most of this will feel familiar. §11 lists everything that's genuinely
different.

---

## Table of contents

0. [Onboarding](#0-onboarding) — read this first if you're new
1. [First-time setup](#1-first-time-setup) — Python deps, `.env`, smoke test
2. [Where each step runs](#2-where-each-step-runs) — Mac vs Cowork
3. [Verified advertiser IDs](#3-verified-advertiser-ids) — the competitor map
4. [Step 1 — Scrape](#4-step-1--scrape) — the CLI scraper
5. [Step 2 — yt-dlp metadata enrichment](#5-step-2--yt-dlp-metadata-enrichment)
6. [Step 3 — R2 upload + master CSV](#6-step-3--r2-upload--master-csv)
7. [Step 4 — AI analysis](#7-step-4--ai-analysis) — gated by cost estimate
8. [Running all competitors at once](#8-running-all-competitors-at-once)
9. [Output schemas](#9-output-schemas) — CSV columns explained
10. [Troubleshooting](#10-troubleshooting)
11. [Known issues + differences from FB pipeline](#11-known-issues)
12. [Why India-only at scrape time](#12-why-india-only-at-scrape-time)
13. [Skills architecture](#13-skills-architecture)

---

## 0. Onboarding

If you're the original maintainer, skip to §1. This section exists for the
colleague taking over the pipeline.

### 0.1 The whole pipeline in one command

For a weekly refresh of all 9 competitors:

```bash
cd ~/Desktop/google-ad-downloader
bash run_all_competitors.sh
```

That single command does everything — paste once, walk away, come back to
a complete master. Four passes run end-to-end:

1. **Pass 1** — Steps 1+2+3 + YouTube metadata backfill for every
   competitor. ~1 hour.
2. **Pass 2** — 30-min cooldown, then retry any competitor that hit
   Google's 429. One retry only. ~40 min if needed.
3. **Pass 3** — HTML5 banner capture (headless Chromium) for every
   `html5-banner-no-mp4` row in master. ~6-8 hours.
4. **Pass 4** — re-upload to R2 so the captured HTML5 mp4s fill in
   `r2_public_url`. ~5 min.

Default total runtime: ~8-10 hours for a fresh, complete refresh.

Opt-out flags for lighter runs:

```bash
bash run_all_competitors.sh --quick           # Steps 1+2+3 only, ~1 hour
bash run_all_competitors.sh --skip-html5      # no Pass 3/4, ~1.5 hours
bash run_all_competitors.sh --skip-retry      # no Pass 2, ~7-8 hours
```

Step 4 (AI analysis) is **deliberately not** part of the wrapper — it's
gated by an explicit cost estimate and approval. Run it separately when
you want analysis docs (see §7).

### 0.1.1 If you need to invoke one step at a time

You normally don't, but for debugging:

```bash
# Step 1 — scrape one competitor
python3 scripts/scrape_google_ads.py --competitor "SpeakX" --region IN --out .

# Step 2 — yt-dlp metadata enrichment
python3 scripts/download_google_ads.py "inputs/g-ads-speakx-$(date +%F).csv" \
    --videos-out "./videos/speakx-$(date +%F)/" \
    --images-out "./images/speakx-$(date +%F)/" --batch-size 600

# Step 3 — upload to R2
python3 scripts/upload_to_r2.py \
    --input "inputs/g-ads-speakx-$(date +%F).csv" \
    --videos "videos/speakx-$(date +%F)/" \
    --images "images/speakx-$(date +%F)/"

# HTML5 banner capture (Pass 3 equivalent for one competitor)
python3 scripts/capture_html5_banners.py --competitor speakx

# Step 4 — AI analysis (gated by cost estimate)
python3 scripts/estimate_step4_cost.py --competitor speakx --all
```

### 0.2 First-time setup (5 minutes)

```bash
cd ~/Desktop/google-ad-downloader

# 1. Install Python deps (one-time; safe to re-run)
pip3 install --user -r requirements.txt

# 2. Copy the env template and fill in real credentials
cp .env.template .env
# Edit .env with your real R2 + Gemini keys — see §1.2 for what each is

# 3. Smoke-test Step 1 against a small advertiser (~30s)
python3 scripts/scrape_google_ads.py --competitor "Memrise" --region IN --limit 3 --out /tmp/gads-smoke
ls /tmp/gads-smoke/inputs/g-ads-memrise-*.csv && echo "smoke test OK"
```

If the smoke test produces a CSV, you're good. If you see `429 Too Many
Requests`, Google's anti-abuse rate-limited your IP — see §10.

### 0.3 What's already done — current state of the data

As of the last full run (June 2026):

- **8 of 9 competitors** are fully through Steps 1+2+3, sitting in
  `master/*.csv`, assets uploaded to R2.
- **SpeakX** additionally has Step 4 complete — 3 distinct videos analysed,
  6 .docx files in R2, master back-filled.
- **English Seekho** is the only outstanding competitor — the IP got
  rate-limited mid-run during a previous attempt. It needs a retry from
  either a different network (mobile hotspot) or after a multi-hour
  cooldown. The scrape itself takes ~30-40 min because Keyaro Edutech has
  ~4K ads.

See the row-count summary by running:

```bash
ls -la master/*.csv
```

---

## 1. First-time setup

### 1.1 Python dependencies

A single `requirements.txt` covers everything:

```
requests        # Step 1, 3 — HTTP client
boto3           # Step 3 — Cloudflare R2 (S3-compatible) uploads
yt-dlp          # Step 2 — YouTube metadata via --write-info-json
openpyxl        # Step 1 — only if feeding an .xlsx of advertiser IDs
google-genai    # Step 4 — Gemini Pro + Nano Banana Pro
python-docx     # Step 4 — building .docx files
```

Install with: `pip3 install --user -r requirements.txt`

The pipeline runs on Python 3.9 (Apple Command Line Tools default) or 3.11+.
Scripts auto-install `requests` if missing — so on a clean machine you may
not even need step 1 above, but doing it is cleaner.

### 1.2 The `.env` file

Copy `.env.template` to `.env` and fill these in:

| Key | Where it comes from | Used by |
|---|---|---|
| `R2_ACCOUNT_ID` | Cloudflare dash → R2 → account ID | Step 3 |
| `R2_S3_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` | Step 3 |
| `R2_ACCESS_KEY_ID` | Cloudflare dash → R2 → Manage API tokens → Create | Step 3 |
| `R2_SECRET_ACCESS_KEY` | Same place; shown once at creation | Step 3 |
| `R2_BUCKET` | Bucket name (we use `video-ads`, shared with FB pipeline) | Step 3 |
| `R2_PUBLIC_URL_BASE` | Bucket public URL or custom domain | Step 3, master CSV |
| `GEMINI_API_KEY` | aistudio.google.com → Get API key | Step 4 |

**Shortcut: if you already have FB pipeline R2 credentials**
(`~/Documents/fb-ad-downloader/.env`), the values are likely identical — same
Cloudflare account, same bucket. The Google upload script auto-prepends `g_`
to keys so Google assets don't collide with Facebook ones in the shared
bucket.

### 1.3 Smoke test

```bash
python3 scripts/scrape_google_ads.py --competitor "Memrise" --region IN --limit 3 --out /tmp/gads-smoke
```

Expected output ends with:

```
[csv] wrote N rows → /tmp/gads-smoke/inputs/g-ads-memrise-YYYY-MM-DD.csv
[done] CSV: /tmp/gads-smoke/inputs/g-ads-memrise-YYYY-MM-DD.csv
[done] rows: N
```

If Step 3's R2 upload smoke test is also wanted: run the full Memrise
sequence (Steps 1+2+3 from §0.1) against `--out .` instead of `/tmp/`.

---

## 2. Where each step runs

| Step | Runs on | Why |
|---|---|---|
| 1. Scrape | Your Mac's Terminal | Talks to Google's API; needs your IP + network |
| 2. Enrich | Your Mac's Terminal | yt-dlp needs YouTube access (Cowork sandbox proxy returns 403) |
| 3. Upload | Your Mac's Terminal | boto3 needs Cloudflare R2 (Cowork sandbox proxy returns 403) |
| 4. Analyse | Your Mac's Terminal *or* Cowork | Gemini API works from either; Step 4 is mostly remote API work |

**What Cowork IS useful for:**

- Editing scripts, docs, this HANDOVER
- Inspecting CSVs and logs
- Running Step 4 (the cost is in API calls, not your local machine)
- Verifying / auditing master CSV state
- Sanity-checking scraper logic via small probes

**What Cowork is NOT useful for:**

- Running Steps 1-3 against real competitors — the sandbox can scrape, but
  bash commands cap at 45 seconds so big advertisers (Duolingo, English
  Seekho) won't finish in one call. Your Mac has no such cap.
- Running yt-dlp, boto3 — the sandbox's network proxy blocks YouTube and R2

---

## 3. Verified advertiser IDs

These are the 9 verified `AR…` advertiser IDs Google's Transparency Center
returned when the brand list was looked up. They're hard-coded inside
`scripts/scrape_google_ads.py` under `COMPETITOR_ADVERTISERS`, so the
`--competitor "NAME"` shortcut works without you needing to remember IDs.

| Competitor | Verified advertiser | Location | AR ID |
|---|---|---|---|
| MySivi ⚠ | NinjaSalary Financial Services Private Limited | India | AR00309923070552834049 |
| SpeakX ⚠ | Ivypods Technology Pvt. Ltd | India | AR02221466555617640449 |
| English Seekho ⚠ | Keyaro Edutech Private Limited | India | AR02289573295139323905 |
| Speak | Speakeasy Labs, Inc | US | AR00705977088842137601 |
| Loora | Loora AI LTD | Israel | AR13725632235724341249 |
| Duolingo | Duolingo Inc | US | AR01320432650854334465 |
| Busuu | Busuu Limited | UK | AR10122694483049971713 |
| Memrise | Memrise Ltd | UK | AR06420837225457516545 |
| Praktika AI | PRAKTIKA.AI COMPANY | US | AR10065453821808607233 |

⚠ = brand verifies under a different operating company; confirm with the
brand team before relying.

Four brands from the original list have no verified advertiser on the
Transparency Center: Zinglish, EnglishBolo, EnglishBhashi, Multibhashi.
They may not run Google ads at all, or may advertise under a parent
company name we haven't yet identified. They're in the map with empty
lists — the scraper skips them.

**To add a new competitor:** look up their AR ID using a regular browser at
`adstransparency.google.com`, search the brand name, click the verified
entry, and grab the `AR…` from the URL. Then add an entry to
`COMPETITOR_ADVERTISERS` in `scripts/scrape_google_ads.py`. See
`archive/find_advertiser_ids_prompt.md` for the discovery process we used
originally (kept only because the methodology is documented there in detail).

---

## 3.5 Rate-limit operating policy + guardrail (READ BEFORE SCRAPING)

Google's Transparency Center anti-abuse blocks an IP that scrapes too often —
this is the single most common way the pipeline fails. The policy below is
enforced in code by `scripts/scrape_guardrail.py`; this section explains why
and how.

### What the logs actually show

Measured from this folder's own `logs/run-all-*.log`:

| Run | When | Result |
|---|---|---|
| 1 | cold/rested IP | ~600 creatives across 7 competitors (incl. Duolingo's 417) in ~37 min, **0 throttle events** |
| 2 | ~4–5 h after run 1 | 50 backoffs, 10 hard blocks, **0 rows** |
| 3+ | next day(s) | still blocked on the first call |

**Conclusion: the binding limit is how *often* you sweep, not requests/min.**
One sweep from a rested IP is fine; a second heavy sweep the same day poisons
the IP, and a poisoned IP stays blocked for **more than a day**. There is no
published rate limit for this endpoint (it's undocumented); Google's sanctioned
Ads API runs ~1 QPS only as a loose reference point.

### The policy (enforced automatically before any network call)

| Rule | Default | Constant in `scrape_guardrail.py` |
|---|---|---|
| Max competitors per run | 1 | `MAX_COMPETITORS_PER_RUN` |
| Min gap between runs | 24 h | `MIN_GAP_HOURS` |
| Cooldown after a 429 block | 24 h | `POST_BLOCK_COOLDOWN_HOURS` |
| Confirmations to override a violation | 2 | `OVERRIDE_CONFIRMATIONS` |
| Per-request pacing + jitter | ~1 s ±0.75 (listing), ~0.15 s ±0.25 (detail) | `SEARCH_PAGE_*`, `DETAIL_*` |

Tune any of these by editing the constants at the top of the file — no logic
changes needed. Recommended cadence: **one competitor per day**, rotating
through the few you track. To keep *all* competitors on a weekly cycle instead,
raise `MAX_COMPETITORS_PER_RUN` and lower `MIN_GAP_HOURS` — but then a single
run spends the whole daily budget at once (riskier).

### How the guardrail behaves

Every `scrape_google_ads.py` run calls the guardrail **before** the first
network call, and appends a record to the ledger when it finishes:

- **Within policy** → prints `[guardrail] OK` and proceeds.
- **Violation** → prints the reason + when the next run is allowed, then:
  - interactive terminal → you must type `yes` **twice** to override;
  - non-interactive (cron / `run_all_competitors.sh`) → it refuses unless
    `--force` is passed.
- **A 429 block** → recorded as `outcome=blocked`; the next run is then refused
  for 24 h (the post-block cooldown).

Flags: `--force` (override without prompts — only if you accept the IP-block
risk), `--no-guardrail` (skip entirely — testing only).

### The run ledger

`logs/scrape_history.jsonl` — one JSON line per run (start/end time, competitor,
region, outcome, creatives, rows, note). **This is the persistent memory the
policy relies on — don't delete it.** Inspect any time:

```bash
python3 scripts/scrape_guardrail.py status              # last run + can I run now?
python3 scripts/scrape_guardrail.py check --competitors 1   # exit 0 if allowed, 3 if not
```

### If you are an AI assistant about to scrape

Run `python3 scripts/scrape_guardrail.py status` **first**. If it reports
BLOCKED, do NOT scrape — tell the operator when the next run is allowed and
stop. Only proceed past a violation with the operator's explicit, repeated
confirmation.

### Recovery when blocked

A poisoned IP needs real rest (a day or more) or a different network. Switch to
a mobile hotspot and re-run, or wait out the cooldown. Hammering through backoff
deepens the block — the guardrail's stop-on-block behaviour exists to prevent
exactly that.

---

## 4. Step 1 — Scrape

**Script:** `scripts/scrape_google_ads.py`
**Skill:** `skills/google-ad-scraper/SKILL.md`

### What it does

Takes a competitor name (or raw `AR…` IDs, or a file/sheet of them), hits
Google's `SearchService/SearchCreatives` RPC to list every ad, then
`LookupService/GetCreativeById` per ad for details, then downloads:

- **Video creatives** (YouTube/HTML5 video): fetches the content.js preview
  URL, extracts the signed `googlevideo.com/videoplayback` mp4 URL from the
  VAST body, downloads the mp4 directly. Also derives the YouTube watch ID
  by base64url-encoding the 16-hex `id=` parameter — that gives a real
  `youtube.com/watch?v=…` URL that Step 2 can hand to `yt-dlp`.
- **Image creatives** (display/banner): extracts the
  `tpc.googlesyndication.com/archive/simgad/…` URL from the variant's `<img>`
  HTML snippet and downloads it as `.jpg`.
- **Text / Other**: no asset to download; metadata only.

Writes a CSV with the 28-column schema downstream Steps 2+3+4 expect (see §9).

### Usage

```bash
# One competitor (uses built-in map)
python3 scripts/scrape_google_ads.py --competitor "SpeakX" --region IN --out .

# All 9 competitors
python3 scripts/scrape_google_ads.py --all-competitors --region IN --out .

# Raw AR IDs
python3 scripts/scrape_google_ads.py AR02221466555617640449 --slug speakx --region IN --out .

# Cap creatives per advertiser for a quick test
python3 scripts/scrape_google_ads.py --competitor "Memrise" --region IN --limit 5 --out /tmp/test

# CSV only, no asset downloads
python3 scripts/scrape_google_ads.py --competitor "Duolingo" --region IN --no-download --out .
```

### What it produces

```
inputs/g-ads-{slug}-{YYYY-MM-DD}.csv      28 columns, see §9
videos/{slug}-{YYYY-MM-DD}/
    {creative_id}.mp4                      variant 0
    {creative_id}_v2.mp4                   variant 1 (if multi-variant)
    {creative_id}_v3.mp4                   variant 2
    ...
images/{slug}-{YYYY-MM-DD}/
    {creative_id}.jpg
    {creative_id}_v2.png
    ...
```

### Resumability

The script streams each download to a `.part` file first, renames on
success. If a video/image already exists and is >10 KB, it's skipped on
re-run. The CSV gets rewritten on each run since the API is the source of
truth, but assets aren't re-downloaded.

### Rate-limit behaviour

Google's anti-abuse occasionally hits the script with HTTP 429 or a 302
redirect to `/sorry/index`. The script handles this with progressive
backoff (15s → 30s → 60s → 2min → 4min, ~7 min total per call) before
giving up on a specific creative and writing it as a `scrape-error` row.
The per-creative loop continues even if one ad is fully blocked.

If an entire run gets persistently 429'd at the very first call (i.e. your
IP is on Google's longer block list), you'll see:

```
requests.exceptions.HTTPError: 429 persisted after 465s of backoff —
IP likely block-listed; wait 30+ min before retrying.
```

See §10 for what to do in that case.

---

## 5. Step 2 — yt-dlp metadata enrichment

**Script:** `scripts/download_google_ads.py`
**Skill:** `skills/google-ads-download-and-upload/SKILL.md` (Steps 2 + 3)

### What it does

Walks the Step 1 CSV row by row and runs `yt-dlp --write-info-json` on every
`youtube_video_url` to produce a `.info.json` sidecar next to the video
file. The sidecar has YouTube title, description, channel/uploader,
duration — which Step 3 reads into the master CSV's
`youtube_video_title`, `youtube_video_description`, `youtube_channel_name`,
`youtube_video_duration_s` columns.

For rows that already have an mp4 on disk (because Step 1 downloaded it)
and no `.info.json` sidecar yet, the script runs a metadata-only
`yt-dlp --skip-download --dump-single-json` call. So Step 2 is mostly a
quick metadata pass, not a full re-download.

Rows with no `youtube_video_url` are logged as `youtube-id-missing` and
skipped — that's expected for HTML5 banner-style ads that don't sit on a
public YouTube video.

### Usage

```bash
python3 scripts/download_google_ads.py "inputs/g-ads-speakx-2026-06-03.csv" \
    --videos-out "./videos/speakx-2026-06-03/" \
    --images-out "./images/speakx-2026-06-03/" \
    --batch-size 600
```

Use a large `--batch-size` (e.g. 600). The original FB-pipeline default of 5
exists to throttle yt-dlp downloads, but Step 1 has usually downloaded the
videos already and this stage is metadata-only, so 600 lets a 500-row CSV
finish in a single pass.

### What it produces

- `.info.json` sidecars next to each existing `.mp4`
- `videos/{slug-date}/download_summary.csv` — per-row outcome
- `videos/{slug-date}/failed_ads.txt` — IDs that failed (usually rows with
  no YouTube URL — these are HTML5 banners, not "failures" in the
  problematic sense)

---

## 6. Step 3 — R2 upload + master CSV

**Script:** `scripts/upload_to_r2.py`
**Skill:** `skills/google-ads-download-and-upload/SKILL.md`

### What it does

For every row in the Step 1 CSV:

- If the row's local asset is on disk (mp4 or image), upload to R2 under
  key `g_{creative_id}.{ext}` (the `g_` prefix keeps Google assets distinct
  from Facebook ones in the shared `video-ads` bucket).
- Read the `.info.json` sidecar (if present) and merge YouTube metadata
  into the row.
- Upsert the row into `master/{competitor}.csv`, keyed on
  `(creative_id, variant_index)`.

### Usage

```bash
python3 scripts/upload_to_r2.py \
    --input  "inputs/g-ads-speakx-2026-06-03.csv" \
    --videos "videos/speakx-2026-06-03/" \
    --images "images/speakx-2026-06-03/"
```

Add `--dry-run` to see what would happen without spending R2 PUT operations.

### What it produces

- `master/{competitor}.csv` (upsert) — the rolling per-competitor truth
- `inputs/g-ads-{slug}-{date}_enriched.csv` — the input CSV with
  `r2_public_url` column appended per row
- `step3_logs/{competitor}-{date}-{HHMM}.log` — per-row outcome log

### Status tags per row (Step 3 internal — visible only in `step3_logs/`)

| Tag | Meaning |
|---|---|
| `uploaded-video` | New mp4 pushed to R2 |
| `uploaded-image` | New image pushed to R2 |
| `carried-forward` | Row already in master with R2 URL; carried over |
| `text-no-asset` | Text-format row, no asset to upload |
| `asset-missing` | Format expects a file but it's not on disk (Step 1 couldn't extract a video URL or an image URL) |
| `scrape-error` | Step 1 hit a 429 / error on this creative; row preserved with empty media |
| `unsupported` | Shopping/Maps with no usable asset |

### error_tag values written to the master CSV

The `error_tag` column in `master/{competitor}.csv` explains why a row has
an empty `r2_public_url`. Empty `error_tag` means the asset was successfully
uploaded to R2 (so `r2_public_url` is filled). Non-empty values:

| `error_tag` value | What it means | What to do |
|---|---|---|
| `html5-banner-no-mp4` | YouTubeVideo-format row, but Google serves this ad as an HTML5/animated banner — no static mp4 exists to download | Open `creative_url` in a browser to view; capture via headless screen recording if the analysis layer needs it. Most ads of this type are intentionally browser-rendered. |
| `image-url-not-extracted` | Image-format row, but the scraper couldn't extract a `tpc.googlesyndication.com/archive/simgad/...` URL from the variant payload | Scraper edge case — open the `creative_url` in a browser to inspect; report to maintainer if frequent. |
| `image-url-not-uploaded` | Image URL was extracted but upload to R2 hadn't run yet, or it failed silently | Re-run Step 3 — usually self-heals. |
| `video-url-not-uploaded` | googlevideo.com URL was extracted but no mp4 landed on disk for upload | Re-run Step 1 to refresh the (short-lived) signed URL, then re-run Step 3. |
| `text-no-asset` | Text-format row, by design no media | None — Step 4 still analyzes the headline + description. |
| `unknown-no-format` | Detail-fetch failed; the scraper has the `creative_id` from the listing but never got the detail to know what format it is | Re-run Step 1 for that competitor — usually a transient 429. |
| `detail-fetch: HTTPError` | Step 1 hit a 429 / network error specifically on this creative | Re-run Step 1 — backoff in the script handles this on retry. |
| `asset-missing-from-disk` | The row had an asset URL but the local file wasn't found at Step 3 time (Step 1's `videos/` or `images/` folder was deleted, or a download silently failed) | Re-run Step 1 to re-download, then Step 3. |
| `html5-captured-locally` | HTML5 banner that was captured via `capture_html5_banners.py` and the mp4 is on disk but not yet uploaded to R2 | Re-run Step 3 — it will see the mp4 and upload it. |

### Known bug — `carried-forward` doesn't backfill YouTube metadata

If a row was uploaded to R2 in a previous run, then Step 1 was re-run, the
new master row will have empty `youtube_video_title` etc. The "carried
forward" branch in `upload_to_r2.py` doesn't re-read `.info.json` sidecars.

**Workaround:** after Step 3, run this one-time backfill. Replace `SLUG`
and `VIDEOS_DIR` with the right values:

```bash
python3 - SLUG videos/SLUG-DATE/ <<'PY'
import csv, json, pathlib, sys
slug, videos_dir = sys.argv[1], sys.argv[2]
videos = pathlib.Path(videos_dir)
master = pathlib.Path(f"master/{slug}.csv")
meta = {}
for info_path in videos.glob("*.info.json"):
    cr_id = info_path.name.split(".")[0]
    with info_path.open() as f:
        data = json.load(f)
    meta[cr_id] = {
        "youtube_video_title": (data.get("title") or "")[:500],
        "youtube_video_description": (data.get("description") or "")[:2000],
        "youtube_channel_name": data.get("uploader") or data.get("channel") or "",
        "youtube_video_duration_s": str(data.get("duration", "") or ""),
    }
with master.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
filled = 0
for r in rows:
    cr = r.get("creative_id", "")
    if cr in meta:
        for col, val in meta[cr].items():
            if val and not r.get(col):
                r[col] = val; filled += 1
with master.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
print(f"filled {filled} cells")
PY
```

The wrapper `run_all_competitors.sh` runs this backfill automatically after
every Step 3 — so this manual snippet is only needed if you ran Steps 1-3
by hand.

---

## 7. Step 4 — AI analysis

**Scripts:** `scripts/estimate_step4_cost.py`, `scripts/step4_*.py`
**Skill:** `skills/google-ads-video-analysis/SKILL.md`

This is the most expensive stage in the pipeline (Gemini Pro + Nano Banana
Pro per video). It is **gated by an explicit cost-estimate-and-approval
step** before any API call fires.

### Stage 0 — cost estimate (free, no API calls)

```bash
python3 scripts/estimate_step4_cost.py --competitor speakx --all
# or scope it:
python3 scripts/estimate_step4_cost.py --competitor speakx --random 5
python3 scripts/estimate_step4_cost.py --competitor speakx --ids CR123,CR456
```

Prints a per-row breakdown and a batch total. **Review and approve before
proceeding.** Example output for the SpeakX run (June 2026):

```
candidate rows:      9  (missing one or both docx URLs)
selected for est:    9
format breakdown:    9 YouTubeVideo
BATCH TOTAL:         $4.02
Wall-clock estimate: 33-57 min
```

In practice, actual spend was ~$1.34 because only variant 0 of each
distinct creative was analysed (variants are near-identical re-cuts;
analysing all 3 variants would have produced near-identical .docx files).

### Stages 1-6 — the actual analysis

Run these in order, one stage at a time. The decompose and rewrite stages
use Gemini's **Batch API**, which queues the request and returns a
`short_id` to poll.

```bash
# Stage 1 — decompose
python3 scripts/step4_decompose.py upload --competitor speakx CR... CR... CR...
python3 scripts/step4_decompose.py submit --competitor speakx CR... CR... CR...
# Captures a short_id. Poll until done:
python3 scripts/step4_decompose.py poll <short_id>
# Re-run poll every ~60s until "Job succeeded. DONE — N sidecars written"

# Stage 2 — extract one frame per scene (fast, local ffmpeg)
python3 scripts/step4_frames.py --competitor speakx CR... CR... CR...

# Stage 3 — character reference sheets (Nano Banana Pro, parallel-sync)
python3 scripts/step4_character_sheets.py --competitor speakx CR... CR... CR...

# Stage 4 — clean panel imagery (Nano Banana Pro)
python3 scripts/step4_panels.py --competitor speakx CR... CR... CR...
# This stage has an internal deadline; you may need to re-run it once to
# finish all panels. Output ends with "DEADLINE — N done, M remaining" if so.

# Stage 5 — Supernova-voice rewrite (Gemini Batch)
python3 scripts/step4_rewrite.py submit --competitor speakx CR... CR... CR...
python3 scripts/step4_rewrite.py poll <short_id>

# Stage 6a — upload per-creative images to R2 (must run before 6b)
python3 scripts/step4_upload_images.py --competitor speakx CR... CR... CR...

# Stage 6b — build the two .docx per ad with R2-URL captions
python3 scripts/step4_build_docs.py --competitor speakx CR... CR... CR...

# Stage 7+8 — upload docx to R2 + update master CSV (final stage)
python3 scripts/step4_upload_and_update.py --competitor speakx CR... CR... CR...
```

After Stage 8, the master CSV has two new URL columns filled per analysed
row: `competitor_analysis_docx_r2_url` and `supernova_rewrite_docx_r2_url`.

### Format-aware behaviour

| Format | What Step 4 does |
|---|---|
| YouTubeVideo | Full pipeline: decompose, frames, character sheets, panels, rewrite, docs |
| Image | Simplified: single-image analysis + 1 panel + rewrite + docs |
| Text | Text-only analysis: 2 sync Gemini calls, no image generation |
| Shopping/Maps | Treated as Image if `image_url_at_scrape` is set, else skipped |

### Choosing scope

For competitors with many variants per creative (SpeakX, MySivi), prefer
running only **variant 0 of each distinct creative_id**, not every variant.
Variants are typically the same source video re-cut slightly — analysing
all of them produces near-identical analyses and triples the spend.

To list the unique creative_ids that have an R2 asset:

```bash
python3 -c "
import csv
with open('master/speakx.csv', encoding='utf-8-sig') as f:
    ids = sorted({r['creative_id'] for r in csv.DictReader(f)
                  if r['r2_public_url'].startswith('https') and r['variant_index']=='0'})
print(' '.join(ids))
"
```

---

## 8. Running all competitors at once — the wrapper

`run_all_competitors.sh` is the operator's primary command. It runs every
recovery pass in sequence so you don't have to know about Step 2 vs Step 3
vs HTML5 capture vs 429 retry — you just type one command.

```bash
cd ~/Desktop/google-ad-downloader
bash run_all_competitors.sh

# Watch progress from a second terminal tab:
tail -f logs/run-all-*.log
```

### What the four passes do

| Pass | What runs | Wall-clock |
|---|---|---|
| 1 | Per competitor: Step 1 (scrape + asset download) → Step 2 (yt-dlp metadata) → Step 3 (R2 upload + master) → YouTube metadata backfill. Tracks which competitors hit 429s. | ~1 hour |
| 2 | If any competitor was 429-blocked: wait 30 min, retry it. One retry only, then continue. | ~40 min if needed |
| 3 | For every master row tagged `html5-banner-no-mp4`: render the ad in headless Chromium, record as mp4. Skipped if Playwright isn't installed. | ~6-8 hours |
| 4 | Re-upload to R2 so the freshly captured HTML5 mp4s fill in `r2_public_url`. | ~5 min |

Order matters: small competitors run first (Memrise → Loora → Praktika AI),
so quick wins land before the long English Seekho run (which has ~4K ads).

### Opt-out flags

```bash
bash run_all_competitors.sh --quick           # Steps 1+2+3 only (Pass 1)
bash run_all_competitors.sh --skip-html5      # no Pass 3/4
bash run_all_competitors.sh --skip-retry      # no Pass 2
bash run_all_competitors.sh --help            # show usage
```

Use `--quick` for routine weekly refreshes when you don't need HTML5
captures and don't expect rate-limit issues. Use the default (no flag)
when you want a complete master end-to-end.

### Final summary the wrapper prints

```
Summary of master CSVs:
  Memrise               3 rows     3 with r2_public_url
  Loora                 4 rows     0 with r2_public_url
  Praktika AI          82 rows    15 with r2_public_url
  ...

Unrecovered competitors (still 429-blocked):
  - English Seekho
Re-run from a different network or after a longer cooldown.
```

### Editing which competitors run

Edit the `COMPETITORS=(...)` array near the top of
`run_all_competitors.sh`. Comment out the ones you don't want, or add a
new entry — the slug derivation handles spaces and mixed case.

### Why Step 4 isn't part of the wrapper

Step 4 (AI analysis via Gemini + Nano Banana) is **deliberately separate**.
It's gated by an explicit cost-estimate-and-approval step because real
money is spent on the API calls. Run it independently with
`scripts/estimate_step4_cost.py` and the `step4_*.py` stages — see §7.

---

## 9. Output schemas

### Per-run input CSV (`inputs/g-ads-{slug}-{date}.csv`)

28 columns, in this exact order (Step 2 + Step 3 + Step 4 all depend on
this layout):

```
row_rank, competitor_name, advertiser_id, advertiser_name,
advertiser_verified_location, target_country, creative_id, creative_url,
creative_format, creative_last_shown_date, regions_shown, variant_index,
variant_count, ad_headline, ad_description, ad_cta_text, ad_overlay_text,
ad_destination_url, youtube_video_id, youtube_video_url,
youtube_video_title, youtube_video_description, youtube_channel_name,
youtube_video_duration_s, image_url_at_scrape, aspect_ratio,
scrape_run_date, error_tag
```

Step 1 fills the first 18 columns plus `youtube_video_id` and
`youtube_video_url` (when extractable). Step 2 leaves the four
`youtube_video_*` metadata columns for Step 3 to fill from the
`.info.json` sidecars.

### Master CSV (`master/{competitor}.csv`)

All 28 input columns + 6 added by Step 3 / Step 4:

```
r2_public_url                              Step 3 — public URL of mp4/jpg in R2
first_scrape_run_date                      Step 3 — when the row was first seen
latest_scrape_run_date                     Step 3 — when last refreshed
competitor_analysis_docx_r2_url            Step 4 stage 8
supernova_rewrite_docx_r2_url              Step 4 stage 8
competitor_analysis_image_r2_urls          Step 4 stage 6a (semicolon-separated)
supernova_rewrite_image_r2_urls            Step 4 stage 6a (semicolon-separated)
```

### Format column values

`creative_format` is one of: `YouTubeVideo`, `Image`, `Text`, `Other`.
This is **inferred** from the variant payload, not from Google's `format_int`
field — because format_int=1 and =2 both appear for image banner ads in
practice. The reliable signal is what the variant actually contains:

- `<img src=…>` snippet → `Image`
- content.js URL whose body contains a `googlevideo.com` link → `YouTubeVideo`
- content.js URL with no obvious image or video → treated as `Image`
  (HTML5/display)
- No variant content → `Text` (catch-all)

---

## 10. Troubleshooting

### Google rate-limits the scraper (429)

**Symptom:** `429 Client Error: Too Many Requests` or
`requests.exceptions.HTTPError: 429 persisted after 465s of backoff`.

**Why:** Google's anti-abuse system flags your IP after enough request
volume. The script's automatic backoff (15s → 30s → 60s → 2min → 4min)
handles transient rate-limits, but a sustained block needs more.

**Fix, in order:**

1. **Stop running scrapes** and wait 15-30 min for the block to clear.
2. If still blocked: switch network. Tether off your phone, use a VPN, or
   move to a different WiFi. The block is per-IP; a fresh IP works
   immediately.
3. When you retry, **run one competitor at a time** instead of the
   wrapper. Smaller bursts are less likely to re-trigger the block.
4. English Seekho is the highest-risk one (4K ads, longest run) — do it
   alone, on a fresh IP, and don't chain anything after.

### `boto3 not installed`

Run `pip3 install --user boto3`. Then re-run the failed command.

### `ImportError: cannot import name 'genai' from 'google'`

Run `pip3 install --user google-genai`. Stage 1 of Step 4 needs it.

### BSD-sed slug bug in `run_all_competitors.sh` (already fixed)

macOS's BSD `sed` doesn't recognise `\+` as "one or more"; you need
`sed -E` (extended regex). If you see Praktika AI (or any multi-word
competitor) get marked `[skip] -- no CSV produced` despite a CSV existing,
the slug was mis-computed. The current `run_all_competitors.sh` uses
`sed -E` and handles spaces correctly.

### Step 3 reports `asset-missing` for an mp4 you can see on disk

`upload_to_r2.py` looks for `{creative_id}_v{N+1}.mp4` for variants ≥1.
Step 1 currently downloads only variant 0's mp4 (because variants share
the same content URL with different querystrings), so variants 1-3 show as
`asset-missing` even though variant 0 was uploaded. This is mostly
cosmetic — the analytical row in master has the R2 URL via the
carried-forward of variant 0. Known issue, not blocking.

### Empty `ad_headline` / `ad_description` for Image and Video rows

Expected behaviour, not a bug. Google ads don't carry separate headline
text fields the way Facebook ads do — the visual *is* the message. Step 1
extracts headline + description **only** when the content.js body has
rendered HTML with prominent text nodes; HTML5 banners with text baked
into the image won't yield anything.

### `Empty `youtube_video_title` etc. in master after re-run

See §6 "Known bug — carried-forward doesn't backfill YouTube metadata."
The wrapper handles this automatically; manual runs need the backfill
snippet.

### Step 2 reports `no youtube URL` for hundreds of rows

Expected. The HTML5 banner-style ads that Step 1 classifies as
`YouTubeVideo` (because Google's `format_int=3`) don't always sit on a
downloadable mp4 with an extractable YouTube ID. They're real video ads,
just served via Google's display-video pipeline, not as a public YouTube
video. yt-dlp has nothing to fetch for them — the row is correctly tagged
and skipped.

---

## 11. Known issues

| Item | Status | Notes |
|---|---|---|
| English Seekho not yet through Step 1 | Scheduled retry queued | Auto-retry task scheduled; will retry from a fresh attempt once IP block clears |
| Duolingo has 230 `scrape-error` rows | Scheduled retry queued | Same as above; re-scrape recovers them |
| 1,381 rows tagged `html5-banner-no-mp4` | Capture script available | Run `scripts/capture_html5_banners.py` — see §11.1 |
| 4 rows tagged `image-url-not-extracted` | Open, needs investigation | Scraper edge case in variant payload parsing. Live-probe blocked while IP is 429'd. |
| 1 row tagged `video-url-not-uploaded` | Open, needs investigation | Same — investigate once Google API access returns. |
| Step 3 `carried-forward` doesn't backfill yt metadata | Worked around | Run the snippet in §6. Wrapper handles it. |
| Step 3 marks `_v2.mp4` etc. as `asset-missing` | Cosmetic | Variant 0 is in R2; variants 1-3 inherit via carry-forward. |
| `ad_destination_url` mostly empty for HTML5 banners | Real gap | Clickthrough URL is in JS, not `<a href>`. Could be improved. |
| Loora / Duolingo have 1 verified AR ID; doc mentioned multiple | Need confirmation | Other IDs unverified — only the one in autocomplete surfaces is in the map. |

### 11.1 Capturing HTML5 banner ads (Option 1 workaround)

Most rows in the master with empty `r2_public_url` are tagged
`html5-banner-no-mp4` — these are real ads but Google composes them in the
browser as HTML5/animated banners, not static mp4 files. To capture them
anyway, use `scripts/capture_html5_banners.py`. It uses Playwright +
headless Chromium to load each ad in a real browser, record the rendered
output for 10 seconds, and convert to mp4 via ffmpeg.

**Setup (one-time):**

```bash
pip3 install --user playwright
python3 -m playwright install chromium    # downloads ~150 MB
brew install ffmpeg                       # if not already installed
```

**Usage:**

```bash
# Test on 10 banners first (recommended)
python3 scripts/capture_html5_banners.py --competitor speakx --limit 10

# Run for one full competitor
python3 scripts/capture_html5_banners.py --competitor speakx

# Run for everyone
python3 scripts/capture_html5_banners.py --all-competitors

# Longer animations need longer recordings
python3 scripts/capture_html5_banners.py --competitor mysivi --seconds 20
```

**Output:** mp4 files at `videos/{slug}-{date}/{creative_id}.mp4` — same
filename convention as direct API downloads, so `upload_to_r2.py` picks
them up automatically on its next invocation with no extra wiring. The
master CSV row's `error_tag` flips from `html5-banner-no-mp4` to
`html5-captured-locally` to record provenance. Re-run Step 3 to upload
the new mp4s and fill `r2_public_url`.

(The wrapper `run_all_competitors.sh` does this automatically — Pass 3
runs the capture, Pass 4 re-runs Step 3 to upload the captures.)

**Caveats:**

- Headless visits to the Transparency Center can trip Google's 429
  anti-abuse same way the API does. The script detects this (302 to
  `/sorry/index`) and reports per-ad failures instead of corrupting the
  master. Stop and wait for cooldown if every ad in a row fails this way.
- Recording length is fixed per run. Bump `--seconds` for ads with longer
  animation loops; lower it to save time on short ads.
- Pacing defaults to 2s between captures. Don't drop it below 1s — that's
  where 429s start appearing.
- Roughly 15-20 seconds wall-clock per ad. For all 1,381 banners that's
  ~6-8 hours of unattended runtime. Plan accordingly.

### Differences vs FB pipeline

| Aspect | FB | Google |
|---|---|---|
| Step 1 source | `yt-dlp facebook:ads` extractor | Internal `SearchService` / `LookupService` RPC |
| What "ad" means | One `library_id` | One `creative_id` with one or more variants |
| Failure mode | "Unable to extract ad data" | 429 rate-limit or `scrape-error` |
| Region filtering | None — FB Ad Library is global | Server-side via numeric region code (`2356` for India) |
| Ad copy availability | Headline + description always present | Only Text + some Image; usually empty for HTML5/Video |
| Multiple advertisers per brand | One Page ID per brand | Many AR IDs possible per brand (Duolingo has 2, Loora has 3 in some sources) |

---

## 12. Why India-only at scrape time

The Transparency Center is a global tool. We want India ads only because
that's our market. There are two places this filter could live:

- **At discovery:** drop advertisers whose verified country isn't India.
- **At scrape time:** keep every advertiser, ask Google for India ads only
  via `region=IN`.

We do the latter, because:

1. Many global brands (Duolingo Inc → US, Busuu → UK, Loora → Israel,
   Memrise → UK) run India ads through non-India legal entities. Dropping
   them at discovery would lose meaningful competitive data.
2. The Transparency Center's region filter is applied server-side — the API
   returns only ads served in the selected region. So `region=IN` is the
   right level of granularity.
3. India-resident brands (MySivi, SpeakX, English Seekho) verify under
   different parent companies (NinjaSalary, Ivypods, Keyaro) anyway, so
   "filter by country" was already going to miss them.

The discovery list is therefore "all 9 verified advertisers, regardless of
location." The scrape applies `region=IN`. The master CSV's
`advertiser_verified_location` column documents where each advertiser is
verified (informational only), and `target_country` is always `IN`.

---

## 13. Skills architecture

Four Cowork skills exist in `skills/`:

| Skill | What it does | When to invoke |
|---|---|---|
| `google-ads-pipeline` | Master orchestrator — runs the full weekly refresh end-to-end | Operator says "refresh all Google competitors" |
| `google-ad-scraper` | Step 1 only — CLI scrape for one or more advertisers | Operator pastes AR IDs or a competitor name |
| `google-ads-download-and-upload` | Steps 2 + 3 — given a Step 1 CSV, enrich + upload | Operator drops a `g-ads-…csv` and asks to push to R2 |
| `google-ads-video-analysis` | Step 4 — gated by cost estimate | Operator asks for analysis on specific creative IDs |

See `skills/ARCHITECTURE.md` for the design rationale behind the split.

The skills are mostly relevant when invoking work through Cowork. For
hands-on Terminal operation, you can ignore them and just use the scripts
directly per §0.1.
