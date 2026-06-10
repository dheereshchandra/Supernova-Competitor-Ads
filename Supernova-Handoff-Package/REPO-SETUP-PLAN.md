# Combined Repo Plan — Google + Facebook Ad Pipelines

*Plain-English master plan. Hand this to Claude on the other system/account and it can
build the whole thing. This supersedes the earlier `COLLABORATION-SETUP.md` in the Google
folder — same idea, now covering both pipelines, the run log, and the analysis space.*

---

## What you asked for

1. **One** big shared online project (Git repo) with **two folders** inside: one for
   Google, one for Facebook.
2. After **every run**, the results get saved into the shared project automatically.
3. A clear **log of every run** — what was done, **at what time**, and **by whom**.
4. All the **cloud links (R2 URLs)** stored in the shared project.
5. A dedicated **place for analysis and learnings** that keeps growing over time.

All five are handled below. (Facebook is the primary, reliable pipeline; the Google one is
currently outdated and its scraper isn't working — we keep it in the repo but treat Facebook
as the source of truth.)

---

## The big picture (in everyday terms)

Think of one shared online binder (the Git repo). Inside it:

- A **Google** divider and a **Facebook** divider — each holds that pipeline's scripts,
  instructions, the master spreadsheets, and the run write-ups.
- A **Run Log** at the front — a running diary: every time someone does a run, one line gets
  added saying *who* did *what* and *when*.
- An **Analysis** section at the back — where you keep insights and learnings as you go.

The heavy ad **videos and images do NOT go in the binder** — they stay in the cloud
warehouse (R2), and you pull down only what you need, when you need it. The binder stays
small and fast; the cloud holds the bulk.

> Why this matters for Facebook specifically: Facebook's video links **expire**, so you
> can't re-download an old ad from an old spreadsheet. The cloud (R2) is the *only* place
> the media survives long-term. So "keep media in the cloud, pull on demand" isn't just
> convenient here — it's the safe way to not lose anything.

---

## The folder structure to build

```
supernova-competitor-ads/              ← ONE Git repo (the shared binder)
├── README.md                          ← what this repo is + the daily workflow
├── RUN_LOG.md                         ← the diary: one entry per run (who/when/what)
├── .gitignore                         ← the rulebook that keeps heavy media + secrets out
│
├── facebook/                          ← PRIMARY pipeline (move the current FB folder here)
│   ├── scripts/  skills/  scraper_prompt.md  HANDOVER.md  README.md
│   ├── master/{competitor}.csv        ← KEPT in git (this is where all the R2 links live)
│   ├── inputs/{run csvs}              ← KEPT in git (text, the run inputs)
│   ├── step3_logs/                    ← KEPT in git (text logs)
│   ├── runs/{competitor}_{date}.md    ← per-run summaries (standardized home)
│   └── videos/  images/  step4_workspace/   ← NOT in git (cloud-only; rehydrate from R2)
│
├── google/                            ← SECONDARY pipeline (outdated scraper; kept for ref)
│   └── (same layout as facebook/)
│
├── analysis/                          ← shared learnings + analysis across both pipelines
│   ├── LEARNINGS.md                   ← a running knowledge base of insights
│   └── {topic}/                       ← spreadsheets / notes per analysis (e.g. cta-analysis)
│
└── tools/
    ├── rehydrate.py                   ← pull one competitor's media down from R2
    └── log_and_commit.sh              ← after a run: stamp the Run Log + save to git
```

---

## Requirement 1 — One repo, two folders

Create one private GitHub repo named `supernova-competitor-ads`. Inside it, the current
Facebook folder becomes `facebook/` and the Google folder becomes `google/`. They keep their
own scripts and master spreadsheets; they just live under one roof now.

---

## Requirement 2 — Save results to git after every run

A small helper, `tools/log_and_commit.sh`, run at the end of every pipeline run. It:

1. Adds a dated entry to `RUN_LOG.md` (see Requirement 3).
2. Saves to git only the small, important files: the updated `master/{competitor}.csv`, the
   run's input CSV, the run summary, and the step-3 log.
3. Commits them **under the operator's name** (so git records who did it), and reminds you
   to upload (`git push`).

The heavy videos/images are skipped automatically by the rulebook, so a "save after every
run" is fast and never bloats the repo.

> Spec for the other Claude:
> `tools/log_and_commit.sh <pipeline> <competitor> "<operator name>" "<one-line note>"`
> → append a RUN_LOG entry, then
> `git add <pipeline>/master/<competitor>.csv <pipeline>/inputs/*<competitor>* <pipeline>/runs/* <pipeline>/step3_logs/*<competitor>* RUN_LOG.md`
> → `git commit --author="<operator> <email>" -m "run: <pipeline>/<competitor> by <operator> — <note>"`
> → print a "now run: git push" reminder.

---

## Requirement 3 — A clear log of every run (what / when / who)

Two layers, working together:

**A) `RUN_LOG.md`** — one short entry per run, newest at top. Format:

```
## 2026-06-05 14:30 IST — facebook / loora — operator: <name>
- Steps run: 2+3 (download + master merge). Creative Studio not run.
- Result: 9 new ads · 25 carry-forward · 26 retired · master 51 → 60.
- R2: all 9 new rows have r2_public_url; 0 existing doc URLs changed.
- Cost: $0 (no Creative Studio this run).
- Full write-up: facebook/runs/loora_2026-06-04.md   ·   commit: <git hash>
```

**B) The per-run summary** in `{pipeline}/runs/{competitor}_{date}.md` — the detailed
write-up you *already* produce today (scope, scrape-vs-master comparison, download counts,
merge integrity check, Creative Studio cost estimate, errors/warnings). We just give it a fixed home.

**How "who and when" is guaranteed:** every person sets up git with their own name once, so
**git automatically stamps every save with the author and exact timestamp** — an unforgeable
record. The Run Log's "operator:" line makes the same information easy to read at a glance.

---

## Requirement 4 — EVERY generated link stored in git (including all Creative Studio links)

Every cloud link the pipeline ever creates must end up in git as text. There are several
kinds, and **all** of them are covered:

| Link | Master CSV column | Created by |
|---|---|---|
| Source video / image | `r2_public_url` | Step 3 |
| Competitor-analysis Word doc | `competitor_analysis_docx_r2_url` | Creative Studio |
| Supernova-rewrite Word doc | `supernova_rewrite_docx_r2_url` | Creative Studio |
| Original scene frames (images) | `orig_frame_urls` *(JSON list)* | Creative Studio |
| Clean regenerated panels (images) | `gen_panel_urls` *(JSON list)* | Creative Studio |
| Character reference sheets (images) | `char_sheet_urls` *(JSON list)* | Creative Studio |

*(The Google pipeline uses the equivalent `competitor_analysis_image_r2_urls` /
`supernova_rewrite_image_r2_urls` arrays — same idea.)*

These all live in the **master spreadsheet**, and the master spreadsheet is committed to git,
so the full link history is preserved and shared. Three safeguards make sure nothing is
missed:

1. **Master schema is kept complete.** Some older master files don't yet have the three
   Creative Studio image-array columns (e.g. `zinglish.csv` stops at the two docx columns). Bring
   every master up to the full link schema so each kind of link has a home. Creative Studio's final
   stage (back-fill) is what writes these columns — make sure it runs to completion, because
   that's the moment the image and docx links enter the master.

2. **Keep the per-image link sidecars in git.** Creative Studio (implemented by the legacy step4_* scripts) writes a small
   `step4_workspace/images/<id>/r2_urls.json` for each ad — the raw map of every generated
   image to its R2 link. Even though the rest of `step4_workspace/` is heavy and excluded,
   **these `r2_urls.json` files are kept in git** (see the rulebook) as a redundant,
   per-image record of every link.

3. **A per-run links manifest.** At the end of each run, `tools/log_and_commit.sh` writes
   `{pipeline}/runs/{competitor}_{date}_links.json` — a single consolidated list of every
   R2 link produced that run (source asset + both docx + all image URLs), gathered from the
   master row and the `r2_urls.json` sidecars. It's committed alongside the run summary, so
   each run has one tidy, permanent record of all its links.

> **Links vs. files.** The *links* (text) always go to git. The actual heavy *files* the
> links point to — the .mp4 videos, the .jpg images, the .docx documents — stay in R2 (the
> cloud), because that's what keeps the repo small. Since every link is in git and every file
> is in R2, nothing is ever lost and everything stays reachable. *(If you also want the
> actual Word docs committed into git as files, that's a deliberate size trade-off — see the
> note at the end.)*

---

## Requirement 5 — A place for analysis and learnings

A top-level `analysis/` folder, shared across both pipelines:

- **`analysis/LEARNINGS.md`** — a running knowledge base. Every time you discover something
  ("Wispr Flow leans hard on a fear-of-mispronunciation hook", "Praktika rotates creative
  every ~2 weeks"), add a dated bullet. It becomes your competitive-intelligence memory.
- **`analysis/{topic}/`** — subfolders for deeper work: spreadsheets, notes, charts (e.g.
  move the existing `wispr-flow-cta-analysis.xlsx` here). These are committed to git so both
  of you build on the same body of knowledge.

Because this lives in git, every insight is shared, versioned, and never lost.

---

## The rulebook (`.gitignore`) — what stays out

```
# Secrets — never commit
**/.env

# Heavy media — lives in R2, pulled on demand. Never commit.
**/videos/
**/images/

# Step 4 working files: exclude the HEAVY stuff, but KEEP every link record (the
# *.json sidecars, especially r2_urls.json) so all generated links stay in git.
**/step4_workspace/.gemini_uploads/
**/step4_workspace/batches/
**/step4_workspace/frames/
**/step4_workspace/logs/
**/step4_workspace/docs/
**/step4_workspace/images/**/*.jpg
**/step4_workspace/images/**/*.png
# (everything else under step4_workspace — i.e. the .json link + analysis sidecars — is KEPT)

# Built Word docs and spreadsheet lock files — the docs live in R2 (links in master).
# (Only the binary files are excluded; their R2 links are preserved in the master CSV.)
**/*.docx
**/~$*
**/.~lock.*

# Old manual backups — git history replaces these
**/*.bak
**/*.bak.*
**/*.pre-*
**/*.savedcopy
**/*.pre-revert-*
**/*.pre-restore*
**/*.pre-merge-*

# OS / Python cruft
**/.DS_Store
**/__pycache__/
**/*.pyc
```

> Note on `inputs/` (~64MB of CSVs): these are kept in git — they're text, they compress
> well, and they're the record of what each run started from. Only the genuinely heavy,
> rebuildable media (`videos/`, `images/`, `step4_workspace/`) is excluded.

> **Important — `.gitignore` does NOT delete or block local files.** Whoever runs a task
> keeps **every** video, image, and Word doc on their own computer, exactly as today. The
> rulebook only controls what gets *shared through git* — the heavy files still save to your
> local disk normally (Step 2 → `videos/`+`images/`, Creative Studio → `step4_workspace/docs/`, etc.).
> The only person who *won't* have a given competitor's media locally is the one who didn't
> run it — and they can pull it from R2 on demand. Nobody ever loses local access.

---

## The everyday workflow (what each person does)

1. **Start:** `git pull` — get the latest (seconds; it's small).
2. **Pick a competitor nobody else is doing.** Each competitor has its own master file, so
   two people on different competitors never clash.
3. **Run the pipeline:**
   - Step 1 (scrape) → in the Chrome-connected app.
   - Steps 2–4 (download / upload / AI analysis) → on **your Mac's Terminal** (the Cowork
     sandbox can't reach Facebook's CDN, R2, or the AI service).
4. **If you need media someone else processed:** `python3 tools/rehydrate.py --competitor X`
   to pull it from R2 — not a 60GB transfer.
5. **Finish:** run `tools/log_and_commit.sh ...` to record the run and save to git, then
   `git push` to share it.

---

## A few rules that keep it clean

- **One competitor per person at a time** — the simplest way to avoid clashes.
- **Never hand-edit a master spreadsheet** — the pipeline owns it (this was already a rule).
- **Never put the `.env` secrets file in git** — each person keeps their own.
- **Don't worry about empty videos/images folders** — rehydrate from R2 when needed.
- **Write down learnings as you go** — a one-line note in `analysis/LEARNINGS.md` beats a
  forgotten insight.

---

## Build order for the other Claude (checklist)

1. Create the private GitHub repo `supernova-competitor-ads`. *(Account owner does this.)*
2. Put the Facebook folder under `facebook/` and the Google folder under `google/`.
3. Add the root `README.md`, `RUN_LOG.md` (empty to start), and the `.gitignore` above.
4. Create `analysis/LEARNINGS.md` and move `wispr-flow-cta-analysis.xlsx` into `analysis/`.
5. Build `tools/rehydrate.py` (spec: read `{pipeline}/master/{competitor}.csv`, HTTP-GET each
   `r2_public_url` into `videos/`/`images/` with the existing variant naming; skip files
   already present; no credentials needed — the URLs are public).
6. Build `tools/log_and_commit.sh` (spec under Requirement 2) — and have it also write the
   per-run links manifest `{pipeline}/runs/{competitor}_{date}_links.json` described in
   Requirement 4 (gather every R2 link from the master row + the `r2_urls.json` sidecars).
7. Bring every master CSV up to the full link schema so all Creative Studio image/docx links have a
   column to live in (Requirement 4, safeguard 1).
8. First commit + push. Then your colleague clones it and adds their own `.env`.
9. From then on: pull → work → log_and_commit → push.

---

## Optional: committing the actual Word docs (not just their links)

By default the plan stores every **link** in git and keeps the actual `.docx` / image / video
**files** in R2. That keeps the repo small while losing nothing (every file is one click away
via its committed link). If you'd prefer the finished Word documents themselves to also live
in git — for offline access or extra redundancy — that's a simple change: keep a committed
`{pipeline}/deliverables/{competitor}/` folder of the `.docx` files and remove `**/*.docx`
from the rulebook. Trade-off: each doc is ~1MB, so a few hundred ads adds a few hundred MB to
the repo. Recommended only if offline access to the docs matters; otherwise the R2 links are
enough.

---

*Result: one tidy shared repo, every run recorded with who/when/what, every generated link —
source assets, both Word docs, and all Creative Studio images — preserved in git, a growing analysis
library, and the 60GB of media kept in the cloud where it belongs.*
