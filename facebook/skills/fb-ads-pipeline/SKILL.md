---
name: fb-ads-pipeline
description: >-
  Master skill for the Supernova FB competitor-ads pipeline. Orchestrates the
  end-to-end flow: takes the operator's Step 1 scraper CSV, runs the
  fb-ads-download-and-upload sub-skill (Steps 2 + 3 — videos to R2, master CSV
  back-filled), then runs the fb-ads-video-analysis sub-skill (Step 4 — scene
  decomposition + Supernova rewrite, two docx per video, every per-scene image
  also uploaded to R2 and linked under its embedded picture, gated by a cost-
  estimate-and-approval step). Final master CSV has five Step-4 URL columns —
  two for the docs, three JSON arrays for the images — so downstream
  ad-creation automation can pull every asset by URL. Use this skill when the
  operator wants the full weekly/fortnightly refresh for a competitor —
  phrasings like "run the full pipeline on Zinglish", "process this CSV
  end-to-end", "do the whole thing for the SpeakX scrape", "run steps 2
  through 4 on the attached file". Don't use this skill if the operator only
  wants Steps 2+3 or only Step 4 — invoke the relevant sub-skill directly
  instead.
---

# Master pipeline — end-to-end FB competitor-ads refresh

This skill is the convenience wrapper for a full weekly/fortnightly refresh cycle. It does no work itself — it sequences two sub-skills with a cost-approval gate in between.

See `../ARCHITECTURE.md` for the architectural rationale. See the two sub-skills' SKILL.md files for the actual work each one does.

## When to invoke this skill (and when not to)

**Invoke when** the operator wants the full refresh — Step 1 CSV in, master CSV updated with R2 URLs *and* analysis docs in, end of story. Phrasings:

- *"Run the full pipeline on this CSV"*
- *"Process this Zinglish scrape end-to-end"*
- *"Run steps 2 through 4"*
- *"Refresh SpeakX from this scrape"*

**Don't invoke when**:

- Operator only wants Steps 2+3 (no analysis) → use `fb-ads-download-and-upload`
- Operator only wants Step 4 against existing master rows → use `fb-ads-video-analysis`
- Operator hasn't done Step 1 yet → tell them to scrape first (Claude-in-Chrome with `scraper_prompt.md`), then come back

## The shape of a master-skill run

```
┌─ Operator says: "run the full pipeline" ─────────────────┐
│                                                          │
│  Phase A — Setup                                         │
│  ────────────                                            │
│  Ask for the Step 1 CSV (attachment in chat OR path)     │
│  Confirm competitor name + slug                          │
│                                                          │
│  Phase B — Steps 2 + 3 (fb-ads-download-and-upload)      │
│  ──────────────────────────────────                      │
│  Invoke sub-skill                                        │
│  Wait for completion + tally                             │
│  Surface tally to operator (uploaded / carried-forward)  │
│                                                          │
│  Phase C — Cost gate                                     │
│  ────────────────                                        │
│  Read master/{competitor}.csv                            │
│  Identify candidate Step 4 rows (missing both docx URLs) │
│  Ask: "how many to analyse? (random N / all / specific)" │
│  Compute estimated cost via fb-ads-video-analysis's      │
│    Stage 0 cost estimator                                │
│  Surface: per-row cost, total, wall-clock estimate       │
│  Ask: "approve? (yes / reduce scope / cancel)"           │
│  WAIT for explicit "yes"                                 │
│                                                          │
│  Phase D — Step 4 (fb-ads-video-analysis)                │
│  ──────────────────────────────                          │
│  Invoke sub-skill with approved scope                    │
│  Stream stage-by-stage progress to operator              │
│  Wait for completion + final tally                       │
│                                                          │
│  Phase E — Final report                                  │
│  ──────────────────                                      │
│  Show: rows uploaded to R2 (videos), docs uploaded,      │
│        cost, time, any quality-fails, path to master CSV │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Phase A — Setup

0. **Run preflight FIRST.** Execute `python3 scripts/preflight.py` before doing anything else. If it exits non-zero (missing ffmpeg, wrong Python version, missing google-genai, missing .env keys), surface the printed remediation to the operator verbatim and STOP. Do NOT pip-install based on guesswork — the preflight output names the exact correct package (`google-genai`, NOT `google-generativeai`). Failure to do this caused ~45 min of unnecessary Terminal detours on the Learna AI run.

1. **Get the Step 1 CSV.** Ask via AskUserQuestion if not provided:
   - Option: *"Attach the CSV to this chat"*
   - Option: *"Use the latest CSV in inputs/ for a competitor I'll name"*
   - Option: *"Use a specific file path I'll provide"*

2. **Identify the competitor.** Parse the slug from the CSV filename (e.g. `fb-ads-zinglish-2026-05-26.csv` → `zinglish`). If the filename is ambiguous, ask the operator.

3. **Sanity-check `.env`.** Preflight (step 0) already validates this, but double-check that both R2 credentials AND `GEMINI_API_KEY` are present. If `GEMINI_API_KEY` is missing, surface clearly:
   > *"Step 4 requires a Gemini API key. Steps 2+3 will still run, but Step 4 will be skipped. Continue with just Steps 2+3, or pause until the key is available?"*

## Phase B — Invoke `fb-ads-download-and-upload`

Hand off control to that sub-skill with the CSV path. When it completes, capture the tally:

- Total rows processed
- Videos uploaded vs. carried-forward vs. image-pending vs. errors
- Path to the updated master CSV

Surface that tally to the operator in a compact block. Don't proceed automatically to Phase C — pause and let the operator see the result.

If the sub-skill failed mid-way (any errors), surface the error and ask the operator whether to retry or stop. Don't push forward to Step 4 if Step 3 didn't finish cleanly.

## Phase C — Cost gate (the critical UX moment)

After Phase B completes:

1. Open `master/{competitor}.csv`. Identify rows where (`competitor_analysis_docx_r2_url` is blank OR `supernova_rewrite_docx_r2_url` is blank) AND `r2_public_url` is non-blank.

2. Tell the operator how many candidate rows exist and the default scope:
   > *"All Step 2+3 work is done. {competitor} master has {N} videos in R2, and {M} of them haven't been analysed yet. The default Step 4 scope is the top 20 by row_rank (= most prominent active ads). I'll show you the cost estimate next — you can approve or adjust scope before anything fires."*

3. Compute the cost estimate using `--top-by-rank 20` (the canonical default per the Learna AI retro) — no AskUserQuestion at this step. Skip straight to Stage 0.

4. Invoke `fb-ads-video-analysis`'s Stage 0 (cost estimator) with `--top-by-rank 20`. **No API calls — purely local math.**

```bash
python3 scripts/estimate_step4_cost.py --competitor <slug> --top-by-rank 20
```

5. Surface the cost estimate in the format defined in `fb-ads-video-analysis/SKILL.md` Stage 0 (per-row breakdown, total, wall-clock estimate).

6. Ask the operator for explicit approval via AskUserQuestion:
   - *"Approve and run top 20"* (Recommended — matches the standard scope)
   - *"Reduce to top 10 / top 5"* (cheaper)
   - *"Expand to top 50 / all candidates"* (more expensive — re-show estimate)
   - *"Switch to specific IDs"* (operator provides IDs)
   - *"Cancel"*

7. Only on explicit approval do you proceed to Phase D. If the operator says "Reduce" or "Expand", re-run Stage 0 with the new scope and re-show before proceeding.

## Phase D — Invoke `fb-ads-video-analysis`

Hand off control to that sub-skill with the approved scope. The sub-skill is fully resumable and chunked — it will likely take 25–60 minutes of wall-clock time, dominated by Gemini Batch API queue + image generation.

While the sub-skill runs, surface progress milestones to the operator:

- "Decompose batch submitted — polling for completion"
- "Decompose complete — verifying"
- "Frame extraction complete (source-native resolution)"
- "Character sheets — N/M done (2K)"
- "Panels — N/M done (2K)"
- "Uploading images to R2 — N/M done"
- "Supernova rewrite submitted"
- "Building docx files (with Asset: hyperlinks beneath each image)"
- "Reviewing each doc for quality"
- "Uploading docs to R2"
- "Running URL audit"
- "Done"

Don't spam — surface only at stage transitions.

## Phase E — Final report

When the sub-skill completes:

```
fb-ads-pipeline — run complete for {competitor}
─────────────────────────────────────────────
Phase B (Steps 2+3):
  • Videos uploaded:        14
  • Carried-forward:        17
  • Image-pending:          0
  • Errors:                 0

Phase D (Step 4):
  • Rows analysed:          5 (random sample of 31)
  • Both docs uploaded:     4
  • Images uploaded to R2:  87  (orig 24 + gen 51 + char 12)
  • Quality-fail:           1 (ad 12345678 — panel regeneration content-blocked, see log)
  • Errors:                 0
  • Actual cost:            $1.42  (estimate was ~$1.55)
  • Wall-clock:             38 min
  • Audit:                  5/5 PASS — every URL HEAD-resolved

Artefacts:
  • master/{competitor}.csv — 5 new rows have docx URLs + orig_frame_urls / gen_panel_urls / char_sheet_urls
  • step4_logs/{competitor}-{date-time}.log
  • All R2 URLs are reachable (HTTP 200)

Next time you scrape {competitor}, this skill will pick up only the new ads
(carry-forwards skip analysis automatically).
```

## Hard rules (don't violate)

- **Always run preflight at Phase A step 0.** If it fails, surface and stop. Don't pip-install based on guesswork. (Learned the hard way on Learna AI — wrong Gemini SDK + missing ffmpeg cost ~45 min.)
- **Default Step 4 scope is `--top-by-rank 20`.** Don't ask the operator how many to run — just compute the estimate at that scope and show them the gate. They adjust there.
- **Never proceed past Phase C without explicit operator approval.** This is the entire reason the master skill exists. The cost gate is sacred.
- **Never invoke `fb-ads-video-analysis` if Phase B failed.** Step 4 has no value without Step 3's R2 URLs in the master.
- **Never invent a Gemini API key** — if it's missing, ask explicitly or offer to run only Phases A-B.
- **Never invoke sub-skills with scopes the operator didn't approve.** If they approved top-20, don't process 21.
- **Stage 4.5 (image upload) MUST run before Stage 6 (build docx)** inside `fb-ads-video-analysis`. The sub-skill's command list is in the correct order — don't reorder.

## Recovery / re-audit

If the operator notices missing URLs in the master CSV or comes back later asking "did everything actually upload?", invoke `scripts/step4_audit.py --competitor <slug> --all` (no API cost — purely HEAD checks). It reports any unreachable URL, any drift between docx hyperlinks and master columns, and any master row that's missing one of the five Step-4 URL columns.

If the audit flags an ad as broken, run `scripts/backfill_step4_images.py --competitor <slug> <ad_id>` — idempotent re-upload of every image, rebuild of both docs with `Asset:` captions, master patch, and re-audit in one command. See HANDOVER §9.7 for the URL contract this enforces.

## Resume behaviour

This master skill is *itself* resumable, but in a different sense than the sub-skills:

- If Cowork's session is killed during Phase B, just re-invoke the master — Phase B's sub-skill resumes from the master CSV (the carry-forward logic handles it). Phase C re-asks for scope.
- If killed during Phase D, the sub-skill resumes cleanly (intermediate JSONs + image files are the recovery state).
- If the operator deferred Phase D until later, they can just invoke `fb-ads-video-analysis` directly later — no need to re-run Phases A-B.

## Cross-references

- `../ARCHITECTURE.md` — architectural rationale
- `../fb-ads-download-and-upload/SKILL.md` — Phase B sub-skill
- `../fb-ads-video-analysis/SKILL.md` — Phase D sub-skill
- `../../HANDOVER.md` — operator manual for the whole pipeline
