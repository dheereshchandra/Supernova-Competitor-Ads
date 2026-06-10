# Skill architecture — four skills, one pipeline (Google)

This document is the single source of truth for *why the skill structure is
shaped this way* for the Google pipeline. Anyone editing the skills should
read this first. The operator-facing how-to lives in `../HANDOVER.md` and in
each skill's own `SKILL.md`.

This is a sibling document to
`~/Documents/fb-ad-downloader/skills/ARCHITECTURE.md`. The high-level
architecture is the same shape — orchestrator skill, cost gate between
non-paid steps and paid analysis, idempotent + resumable scripts — with the
Google-specific differences called out in §1.5.

> **🇮🇳 India-only ADS.** The scraper passes `region=IN` to Google's API.
> The master CSV's `target_country` is always `IN`. Discovery, however,
> keeps advertisers verified in any country (US, UK, Israel, etc.) because
> many global brands advertise heavily in India through non-India-verified
> entities. The skills assume this. Multi-region scraping is a larger
> architectural change, not a flag.

> **Pipeline switched to CLI on 2026-06-01.** Step 1 used to be a JavaScript
> prompt pasted into a Claude-in-Chrome session, scraping the rendered SPA
> via a hidden iframe. It is now a Python CLI script
> (`scripts/scrape_google_ads.py`) that talks to Google's underlying RPC
> endpoints directly. The previous architecture document described the
> 6-pass iframe scraper. That section is now archived along with the
> obsolete prompt in `../archive/`.

## The big picture

```
                       Operator
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
   run_all_competitors.sh    google-ads-pipeline      ← two equivalent
   (terminal entry point)    (Cowork skill entry)       entry points
              │                        │
              └───────────┬────────────┘
                          ▼
        ┌─────────────────┼──────────────────────────────┐
        ▼                 ▼                              ▼
┌──────────────────┐ ┌──────────────────────────┐ ┌─────────────────────────────┐
│ google-ad-       │ │ google-ads-download-     │ │ google-ads-video-analysis   │
│ scraper          │ │ and-upload               │ │ (Creative Studio)           │
│ (Step 1)         │ │ (Steps 2 + 3)            │ │                             │
│                  │ │                          │ │  • cost estimate + gate     │
│ Advertiser IDs   │ │ CSV in → yt-dlp metadata │ │  • per-format branching     │
│ → API → assets   │ │ + assets → R2 → URLs in  │ │    (Video / Image / Text)   │
│ + CSV            │ │ master CSV               │ │  • Supernova rewrite        │
│                  │ │                          │ │  • 2 docx per ad → R2       │
└──────────────────┘ └──────────────────────────┘ └─────────────────────────────┘
```

All four skills' scripts live in `../scripts/`. The skills are documentation
+ Cowork-invocation logic; the actual work is done by the Python scripts.

## 1.5 What's different from FB's architecture

Five things shape the Google variant:

1. **Step 1 is an API client, not a browser scraper.** FB's pipeline relies
   on `yt-dlp`'s `facebook:ads` extractor against the public Ad Library
   pages. Google's Transparency Center has no equivalent in yt-dlp, but its
   SPA fetches data from two internal RPC endpoints
   (`SearchService/SearchCreatives` for the listing,
   `LookupService/GetCreativeById` for per-creative detail). Those endpoints
   are public, undocumented, and stable enough to call directly. Our Step 1
   does exactly that — `requests.post(...)` with the same payload shape the
   SPA uses — and parses the JSON response. No browser, no DOM, no AI calls.

2. **Asset URLs are short-lived but stable in shape.** Video creatives are
   served from `googlevideo.com/videoplayback?...` URLs that are signed and
   expire in ~5 hours; image creatives are at
   `tpc.googlesyndication.com/archive/simgad/…` and don't expire. The Step 1
   scraper downloads videos immediately in the same run, never storing the
   googlevideo URL for later re-use. (FB's pipeline has the same constraint
   for video CDN URLs.) The YouTube watch ID is derived from the
   16-hex `id=` parameter on the googlevideo URL via base64url-encoding —
   verified reversible — so Step 2 can still feed yt-dlp a real
   `youtube.com/watch?v=…` URL.

3. **Format heterogeneity.** A Meta advertiser is mostly Video, occasionally
   Image. A Google advertiser is a mix of YouTubeVideo / Image / Text /
   Shopping / Maps. Creative Studio branches on `creative_format`. The text-only path
   (single Gemini sync call analysing the headline + description → two
   single-page docs) doesn't exist in the FB pipeline.

4. **Variants exist.** A single Google `creative_id` can have multiple
   "variations" — different copy or visuals served alternately. The master
   is keyed on `(creative_id, variant_index)`. The CLI scraper extracts all
   variants from the `GetCreativeById` response in one call (no chevron
   clicks needed — the API returns them as a list).

5. **Rate limiting is real.** Google's anti-abuse system can 429 the
   scraper mid-run, especially on large advertisers (Duolingo with 400+
   ads, English Seekho with 4K+). The scraper has progressive backoff
   (15s → 30s → 60s → 2min → 4min) per call, and tags individual creatives
   as `scrape-error` rather than crashing the whole run. Recovery is to
   wait 15-30 min, or switch network. The operator's wrapper
   `run_all_competitors.sh` automates this: after the first pass it waits
   30 min and retries any blocked competitor once.

   **Update — rate-limit operating policy.** Empirically (see the run logs and
   HANDOVER "Rate-limit operating policy") the binding limit is run
   *frequency*, not request rate: one sweep from a rested IP is fine, a second
   the same day poisons the IP for 24 h+, and the 30-min retry above is
   optimistic for a repeat-offense block. A guardrail
   (`scripts/scrape_guardrail.py`) now enforces a cadence policy — default
   1 competitor/run, 24 h between runs, 24 h post-block cooldown — **before any
   network call**, backed by a `logs/scrape_history.jsonl` ledger so the policy
   survives across sessions (no human or agent has to remember the last run).
   The scraper also honors `Retry-After` and uses jittered pacing. Constants
   live at the top of `scrape_guardrail.py`.

6. **HTML5 banner ads exist as a fundamentally different asset class.** A
   large share of Google display ads (especially for India ed-tech brands)
   are HTML5-rendered banners, not static mp4 files. Google's
   `format_int=3` marks them video-like but the content.js preview contains
   no `googlevideo.com` URL. There's no file to download. The pipeline
   handles this with a separate **HTML5 capture pass**
   (`scripts/capture_html5_banners.py`) — headless Chromium loads each
   `creative_url`, records the rendered ad for 10s, ffmpeg encodes to mp4.
   Output files use the same `{creative_id}.mp4` naming as direct
   downloads, so the downstream R2-upload logic doesn't need to know the
   provenance. The master's `error_tag` flips
   `html5-banner-no-mp4` → `html5-captured-locally` to record it.

Everything else — the four-skill split, the cost-approval gate, the
idempotency rules, the per-row checkpointing, the verification gates between
Creative Studio stages, the Claude-reviews-the-docx pattern — is the same as the FB
pipeline.

## Step 1 architecture (Google-specific)

Step 1 is the Python script `scripts/scrape_google_ads.py`. It's a single
file, no async magic, no browser. Key design choices:

- **Two RPC endpoints.** `SearchService/SearchCreatives` lists creatives
  for an advertiser (paged in batches of 40); `LookupService/GetCreativeById`
  returns per-creative detail including variants, content URLs, and region
  metadata. Both take a `f.req` form-encoded JSON body in the same
  positional-array shape the SPA uses internally.
- **Format detection is content-driven, not format-int-driven.** Google's
  detail response has a `format` integer field, but format_int=1 and =2
  both appear for image banner ads in practice. The reliable signal is
  what the variant payload actually contains: an `<img src=…>` snippet
  means `Image`, a content.js URL whose body has a `googlevideo.com` link
  means `YouTubeVideo`, neither means `Text`.
- **Video extraction is two-hop.** Variant payload gives a content.js URL;
  the script fetches that, regex-parses out the signed
  `googlevideo.com/videoplayback?...` URL embedded inside a VAST `MediaFile`
  element, downloads the mp4 directly. The YouTube watch ID falls out of
  the `id=` hex parameter.
- **Image extraction is one-hop.** Variant payload includes the
  `tpc.googlesyndication.com/archive/simgad/…` URL inside an `<img>`
  snippet. Downloaded as `{creative_id}.jpg`.
- **content.js caching per-run.** Many variants of one creative share the
  same preview URL (only `assets=` and `htmlParentId=` differ); the script
  normalises those query params and caches by URL to avoid redundant 100KB
  fetches.
- **Per-run cookie warm-up.** Without an initial `GET /` to
  `adstransparency.google.com`, the POST sometimes returns `{}`. The
  `TransparencyClient.__init__` does this.
- **No persistent state between runs.** Re-running is safe — the CSV gets
  rewritten (API is the source of truth), local file downloads are skipped
  if a >10KB file is already on disk.
- **Region filter is server-side.** Passing `region_code=2356` (India) in
  the SearchCreatives body restricts results to India ads. The script's
  `REGION_CODES` map covers the 20 markets we care about; more can be
  added from the upstream open-source library if needed.

When Google's API shape changes (rare — it's been stable for years), the
fix is in `parse_creative_detail()` and `extract_googlevideo_url()`.
Nothing else in the folder needs touching.

## Why four skills, not one

Same three arguments as FB:

1. **Different cost profiles.** Steps 1+2+3 are essentially free
   (HTTP + R2 PUT charges). Creative Studio burns Gemini Pro + Nano Banana Pro —
   meaningful money. Splitting them lets the master skill interpose a
   cost-estimate + approval gate.
2. **Different invocation patterns.** Sometimes you only want to add a new
   competitor (Step 1 only). Sometimes you only want assets in R2 (Steps
   1-3 only, no analysis). Sometimes you only want analysis on existing R2
   assets (Creative Studio only, no fresh download). The sub-skills are usable on
   their own; the master is the convenience wrapper.
3. **Different failure modes.** Step 1 fails on Google rate-limits.
   Step 2/3 fail on yt-dlp / R2 credentials. Creative Studio fails on Gemini billing
   or content-policy blocks. Keeping them separate makes each failure
   localised and retryable.

## Skill responsibilities — strict boundaries

### `google-ads-pipeline` (master)

**One job:** orchestrate. Owns no business logic.

- Asks which competitors to refresh (or all)
- Invokes `google-ad-scraper` per competitor
- Surfaces Step 1's tally
- Invokes `google-ads-download-and-upload` with the resulting CSVs
- Surfaces that sub-skill's tally
- Asks: "ready to estimate Creative Studio cost?" — waits for explicit yes
- Invokes `google-ads-video-analysis` with the chosen scope
- Surfaces the final tally including R2 URLs for all generated docs

### `google-ad-scraper` (Step 1)

**One job:** turn one or more advertiser IDs into a CSV + downloaded assets.

Wraps one script: `scripts/scrape_google_ads.py`.

Input forms accepted:

- Inline AR IDs (positional args)
- `--competitor "NAME"` shortcut (uses built-in map)
- `--all-competitors` (runs all 9 in the map)
- A `.txt` file (one AR per line)
- A `.csv` / `.xlsx` with an `advertiser_id` column
- A public Google Sheets URL

Outputs:

- `inputs/g-ads-{slug}-{date}.csv` (28-column schema)
- `videos/{slug}-{date}/*.mp4`
- `images/{slug}-{date}/*.{jpg,png}`

It does **not** touch R2, Gemini, or the master CSV. Step 3 owns those.

### `google-ads-download-and-upload` (Steps 2 + 3)

**One job:** turn a Step 1 CSV into a master CSV with `r2_public_url`
filled in for every analysable row.

Wraps two scripts:

- `scripts/download_google_ads.py` — runs `yt-dlp` to produce `.info.json`
  sidecars next to each video for YouTube metadata enrichment.
- `scripts/upload_to_r2.py` — uploads assets to R2, maintains
  `master/{competitor}.csv`, idempotent.

Per-row decision logic, branching on `creative_format`:

| Format | Step 2 (metadata) | Step 3 (upload) | Master `r2_public_url` |
|---|---|---|---|
| `YouTubeVideo` | yt-dlp `--write-info-json` on watch URL | Upload .mp4 | Populated |
| `Image` | No-op | Upload image | Populated |
| `Text` | No-op (logged `text-no-asset`) | No-op | Stays empty |
| `Shopping`, `Maps` | Best-effort if URL columns populated | If asset present: upload | Conditional |

It does **not** touch Gemini, image generation, or document building.

### `google-ads-video-analysis` (Creative Studio)

**One job:** for every analysable master row whose docx URLs are missing,
produce two analysis docs and back-fill those columns.

Pipeline stages — same as FB plus the Text branch:

| Stage | Engine | Per-row cost band | Failure mode |
|---|---|---|---|
| 0. Cost estimate + operator approval gate | Local Python (no API call) | $0 | Operator declines → skill exits |
| 1a. Decompose video → structured JSON (YouTubeVideo) | Gemini 3.1 Pro Batch API | ~$0.035 | Truncated JSON → retry with bumped tokens |
| 1b. Decompose image ad → structured JSON (Image) | Gemini 3.1 Pro sync | ~$0.01 | Same |
| 1c. Decompose text ad → structured JSON (Text) | Gemini 3.1 Pro sync (headline + description as input) | ~$0.005 | Same |
| 2. Extract frame screenshots (video) / copy image / no-op (text) | ffmpeg / local copy / N/A | $0 | Codec issue → skip with log |
| 3. Character reference sheets (video only) | Nano Banana Pro, parallel-sync | ~$0.04/char | Content-policy block → fall back |
| 4. Clean panel imagery (video + image) | Nano Banana Pro, parallel-sync | ~$0.04/panel | Content-policy block → fall back to original |
| 5. Supernova rewrite (all formats) | Gemini 3.1 Pro Batch API | ~$0.02 | Truncated JSON → retry |
| 6a. Upload per-creative images to R2 + write `image_urls/{ckey}.json` sidecar | boto3, local | $0 (storage) | Network → retry; idempotent via sidecar |
| 6b. Build two `.docx` files with R2 URL captions under every embedded image | python-docx, local | $0 | Image embed failure → log + retry |
| 7a. Strict programmatic audit (R2-URL-below-every-image, scene count, no placeholders) | python-docx, local | $0 | ERROR-severity → row excluded from upload |
| 7b. Claude review of each docx (grammar, image quality, layout) | the model | ~$0 (LLM tokens) | Quality fail → mark needs-rerun, don't upload |
| 8. Upload docs to R2 + update master CSV (docx URLs + image URL JSON arrays) | boto3, local | $0 | Network → retry |

**Strict rule:** the analysis sub-skill never modifies `videos/`, `images/`,
`inputs/`, or any non-master CSV. It only reads from `master/`, writes
intermediate state to `step4_workspace/`, and updates four columns in the
master at the end.

## How the cost-estimate-and-approval gate works (Creative Studio)

1. Read the master CSV.
2. Identify candidate rows (missing one or both docx URLs).
3. Apply the operator's scope flag (`--random N`, `--all`, `--ids X,Y,Z`).
4. For each candidate row, compute estimated cost based on `creative_format`:
   - **YouTubeVideo**: ffprobe duration → scene count → decompose + sheets
     + panels + rewrite
   - **Image**: fixed $0.05 (single Gemini call + one panel + rewrite)
   - **Text**: fixed $0.02 (two Gemini sync calls, no images)
   - **Shopping/Maps**: treated as Image if asset exists, else excluded
5. Present per-row breakdown + total + wall-clock estimate.
6. Ask via AskUserQuestion: Approve / Reduce / Cancel.
7. Only on explicit "Approve" do Stages 1+ run.

This gate is the operator's single most important safety net. Never bypass.

## How verification works at every Creative Studio stage

- **After decompose**: every row has a sidecar JSON, JSON parses. For video:
  `scenes ≥ 1`, each scene has non-empty `audio_transcript`. For image: 1
  synthetic scene with `on_screen_text` filled. For text: 1 synthetic
  scene with `ad_headline` + `ad_description` populated.
- **After frames**: for video, one `orig_NN.jpg` per scene; for image,
  exactly 1 `orig_01.jpg`; for text, no frames.
- **After sheets**: video only; one sheet per declared character.
- **After panels**: video + image; one panel per scene.
- **After rewrite**: same scene count as decompose, every scene has
  `supernova_script`.
- **After docx build**: opens cleanly, paragraph count > minimum, image
  count = expected, no empty headings.
- **After Claude review of docx**: open both docs, review text + images for
  quality. Verdict goes into the per-row log.

A row only gets uploaded + master-updated when all gates pass. Otherwise
tagged `quality-fail-needs-rerun` and the orchestrator continues with other
rows.

## The four new master columns added by Creative Studio

| Column | What it contains |
|---|---|
| `competitor_analysis_docx_r2_url` | Public R2 URL of Doc 1 (competitor analysis) |
| `supernova_rewrite_docx_r2_url` | Public R2 URL of Doc 2 (Supernova-voice rewrite) |
| `competitor_analysis_image_r2_urls` | JSON array of every image embedded in Doc 1 (originals + clean panels + character sheets) |
| `supernova_rewrite_image_r2_urls` | JSON array of every image embedded in Doc 2 (clean panels only) |

R2 key naming (doc files):

- `{ckey}_competitor_analysis.docx` where ckey is `creative_id` (variant 0)
  or `{creative_id}_v{N+1}` (variant N≥1)
- `{ckey}_supernova_rewrite.docx`

R2 key naming (image files, uploaded in Stage 6a):

- `{ckey}_img_orig_NN.jpg` — original frame screenshots
- `{ckey}_img_panel_NN_pos.jpg` — clean regenerated panels
- `{ckey}_img_char_X.jpg` — character reference sheets

If `R2_BUCKET` matches the FB pipeline's bucket name (`video-ads`), the
`g_` prefix is added automatically to avoid namespace collisions.

## Image-only ads — the single-page treatment

For master rows with `creative_format = Image`:

- Doc 1 (competitor analysis): single page with the original image
  embedded, the Transparency Center metadata, plus a Gemini-generated
  description of what the image conveys.
- Doc 2 (Supernova rewrite): single page with a regenerated brand-safe
  image (or original if regeneration is blocked) + Supernova-voice rewrite.

## Text-only ads — the new branch (no FB analog)

For master rows with `creative_format = Text`:

- Doc 1: single page with `ad_headline` + `ad_description` verbatim, plus a
  Gemini-generated breakdown of the messaging, target audience, and
  value-prop.
- Doc 2: single page with a Supernova-voice rewrite of the headline and
  description.
- No images involved (no character sheets, no panels). Stages 2/3/4 are
  no-ops for these rows.

## Where intermediate state lives

```
google-ad-downloader/
├── inputs/                                          Step 1 output (CSV per run)
├── videos/{slug}-{date}/                            Step 1 + Step 2 outputs
├── images/{slug}-{date}/                            Step 1 outputs
├── master/{competitor}.csv                          Step 3+ owns; rolling truth
├── step3_logs/                                      Step 3 per-row outcome
└── step4_workspace/                                 Owned by google-ads-video-analysis
    ├── .gemini_uploads/<id>.json                    Gemini Files API references
    ├── batches/
    │   ├── decompose_<short>.json                   Batch job state
    │   └── rewrite_<short>.json
    ├── scenes/
    │   ├── <id>.json                                Decompose sidecar
    │   └── <id>.supernova.json                      Rewrite sidecar
    ├── frames/<id>/orig_NN.jpg                      Scene screenshots
    ├── images/<id>/                                 Character sheets + clean panels
    │   ├── char_<X>_sheet.jpg
    │   └── gen_NN_<pos>.jpg
    ├── image_urls/<ckey>.json                       Per-creative image→R2 map (Stage 6a)
    ├── docs/                                        Built by Stage 6b before R2 upload
    ├── audit_reports/<ckey>.json                    Stage 7a audit
    └── logs/                                        Per-run audit trail
```

## API key handling

Same `.env` file used by Step 3. Creative Studio reads `GEMINI_API_KEY`. When
missing, the analysis skill refuses to run with a clear error. The cost
estimator (Stage 0) works without the key.

## When to break this architecture

The skill structure should hold up unless one of these changes:

- We start running Step 1 in Cowork as part of the orchestrator (right now
  it runs on the operator's Mac). Then the master skill needs to learn how
  to coordinate Mac + Cowork.
- We add a Step 5 (push the master to a DB). That becomes a fifth skill.
- The cost-estimate-then-approval pattern becomes operator-burdensome. If
  small fixed batches become the norm, the gate could move from the
  analysis skill to the master only.
- Google adds a major new ad format we hadn't anticipated. Then the Creative Studio
  skill grows a new branch.

Until one of those triggers, this is the shape.
