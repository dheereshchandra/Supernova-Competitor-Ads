---
name: replicate-competitor-ads
description: >-
  Replicate competitor video ads as Supernova AI ad scripts (English + romanized target
  language) and deliver them as one Google Doc per ad plus a filled-in CSV. Use when given a
  shortlist (a sheet/CSV or a list) of competitor ad reference links, each with a target
  language and a concept brief ("Same"/"Ditto" = faithful replication; anything else = apply
  the brief). By default it generates via the repo's own Creative-Studio pipeline (Gemini), staying in sync with Ad Studio (a Claude engine is optional). Runs standalone/on-demand (no Ad Studio webapp queue involved).
---

# Replicate competitor ads → Supernova scripts (Google Docs + CSV)

Given a shortlist of competitor ads, produce, per ad, **one Google Doc** containing the full
Supernova re-skin in English followed by the full version in the target language (romanized),
and return the shortlist as a **CSV with each Doc link filled in**.

## When to use
The operator gives you a sheet/list of competitor ads to replicate as Supernova creatives —
each row has a **target language**, a **concept brief**, and a **reference link** to the
original ad. Trigger phrases: "replicate these ads", "make Supernova scripts for this sheet",
"turn these competitor links into scripts + Docs".

## Inputs
A sheet (`.xlsx`/`.csv`) or JSON list. Columns are auto-detected by header keyword:
- **Language** (the target language, e.g. Malayalam / Kannada / Telugu / Hindi …)
- **Concept Brief** — `Same`/`Ditto`/blank ⇒ faithful replication; otherwise the brief is applied (it **overrides** the original where they differ).
- **Reference / Inspiration Link** — the original competitor ad (an R2 `.mp4`, a Facebook Ad Library `?id=…`, or a social link like an Instagram reel).
- **Idea / Ad Name** (optional, for titles).

## Prerequisites
- Run everything from the **repo root** with `python3.13` (not system `python3`).
- Packages: `openpyxl google-genai yt-dlp` + `ffmpeg` on PATH. `GEMINI_API_KEY` + R2 keys in `.env` (root for the Claude/transcribe path; `facebook/.env` for the repo engine's step4 scripts). The repo engine uses Gemini **Pro** for decompose/rewrite (the sanctioned Creative-Studio exception); transcription is Flash.
- The **claude.ai Google Drive integration** must be connected (for creating the Docs). It can create + read + search, but has **no update/delete** — re-running makes *new* Docs; it can't edit old ones.

## Two generation engines
- **`repo` (DEFAULT) — the real repo / Ad-Studio Creative-Studio pipeline (Gemini).** `scripts/generate_repo_pipeline.py` *only orchestrates*; it shells out to the SAME scripts Ad Studio's `webapp/backend/jobs.py` calls — `facebook/scripts/step4_decompose*.py` (Gemini decompose of the video), `step4_rewrite.py` (Gemini 3.1 Pro rewrite), `step4_qc.py` (Gemini Flash audit). **There is NO copy of the generation logic in the skill** — change `facebook/scripts/step4_*` or `facebook/generation/supernova_*.md` and this skill picks it up automatically. Output is native-script + romanized in the target language (no English master). Cost ≈ $0.05/ad.
- **`claude` (ALTERNATE) — a Claude Workflow** (write → adversarial-verify → revise) defined ONLY in `scripts/generate_workflow.js`, grounded in the same `facebook/generation/supernova_*.md` brand rules (its agents read them at runtime). Output is an English master + romanized target language. Use for fast/cheap drafts or model comparison.

## ⚠️ Single source of truth
- **Generation** = the repo `facebook/scripts/step4_*` pipeline (engine `repo`) OR `scripts/generate_workflow.js` (engine `claude`) — never both copies of a prompt; each lives in exactly one file.
- **Brand rules** (voice, claims, HARD LINES, localization) live **only** in `facebook/generation/supernova_{creative_context,direct_rewrite,brand_safety,translation_rules,casting}.md` — read at runtime by BOTH engines.
- **Doc layout** only in `scripts/build_docs.py` (renders English and/or native + romanized); **CSV mapping** only in `scripts/build_csv.py`.
- This SKILL.md only *orchestrates* — it never restates a prompt or a brand rule. **To change behaviour, edit the one canonical file**; everything downstream picks it up.

## Pipeline — run these in order
Let `ROOT` = repo root, `WORK` = `$ROOT/.context/replicate/<batch-name>` (gitignored scratch),
`S` = `$ROOT/.claude/skills/replicate-competitor-ads/scripts`.

**0. Working dir** — `mkdir -p "$WORK"`.

**1. Parse the input** → `shortlist.json`:
```
python3.13 "$S/parse_input.py" --input "<the sheet>" --out "$WORK/shortlist.json"
```

**2. Resolve sources** (reuse repo transcripts; download+transcribe the rest) → `source_master.json` + `ads.json`:
```
python3.13 "$S/resolve_sources.py" --shortlist "$WORK/shortlist.json" --root "$ROOT" --workdir "$WORK"
```
If it lists any **UNRESOLVED** ads, ask the operator for an `.mp4` or transcript for those, drop the file in `$WORK/videos/`, and re-run (cached transcripts are reused).

**3. Generate the scripts** → `$WORK/generated.json`. Pick the engine:

**3a. `repo` engine (DEFAULT — the real Gemini pipeline).** Needs the ads to be rows in
`facebook/master/<competitor>.csv` with an `r2_public_url`; pass that competitor slug:
```
python3.13 "$S/generate_repo_pipeline.py" --shortlist "$WORK/shortlist.json" --root "$ROOT" \
    --competitor <slug> --workdir "$WORK"
```
It downloads the videos, decomposes them (Gemini), submits the Gemini 3.1-Pro rewrite per target
language and polls the Batch API (blocks up to `--max-poll-min`, default 45), runs the Flash QC, and
writes `$WORK/generated.json`. (The Gemini Batch API occasionally drops a malformed-JSON key — the
script auto-resubmits dropped keys once. If any remain `MISSING`, re-run the same command; finished
work is skipped.) Long-running, so prefer running it as a background Bash command.

**3b. `claude` engine (ALTERNATE — fast Claude drafts / model comparison).** Read `$WORK/ads.json`, then:
```
Workflow({ scriptPath: "$S/generate_workflow.js",
           args: { root: "$ROOT", sourceFile: "$WORK/source_master.json", ads: <contents of ads.json> } })
```
When it finishes, the task-output file's `result` key is `[{n, script, verdict, revised}, …]` — save that
array to `$WORK/generated.json` (`python3.13 -c "import json;d=json.load(open('<output-file>'));json.dump(d['result'],open('$WORK/generated.json','w'),ensure_ascii=False,indent=2)"`).

**4. Final safety sweep** (safe auto-fixes + flags):
```
python3.13 "$S/sweep_fix.py" --gen "$WORK/generated.json"
```
Resolve any printed FLAGS (re-run a targeted revise, or fix the specific field) before continuing.

**5. Build the doc bodies** (the deliverable layout) → `$WORK/docs/*.txt` + `upload_manifest.json`:
```
python3.13 "$S/build_docs.py" --gen "$WORK/generated.json" --src "$WORK/source_master.json" --out "$WORK/docs"
```

**6. Create the Drive folder + upload one Google Doc per ad** (you, via the Google Drive integration):
- Create a folder (mimeType `application/vnd.google-apps.folder`), e.g. *"Supernova — <batch> Replications"*; keep its `id`.
- For each entry in `$WORK/docs/upload_manifest.json`: **Read** `$WORK/docs/<txt>`, then `create_file` with `title` = entry title, `parentId` = folder id, `textContent` = the file's exact content, `contentMimeType` = `text/plain` (auto-converts to a native Google Doc). Capture the new file id → URL `https://docs.google.com/document/d/<id>/edit`.
- For >~6 ads, delegate this loop to a sub-agent (Agent tool) so the file contents stay out of the main context; have it write `$WORK/links.json` = `{"<n>": "<url>", …}` and return the map.

**7. Fill the CSV**:
```
python3.13 "$S/build_csv.py" --input "<the original sheet>" --shortlist "$WORK/shortlist.json" \
    --links "$WORK/links.json" --out "$WORK/<sheet-name> - FILLED.csv" --status Drafted
```

**8. Report** the Drive folder link, the per-ad Doc links, and the CSV path. Surface any
source issues / rule-conversions (each Doc already carries a ⚠️ Reviewer note) as findings.

## Output layout (what each Doc contains)
1. 🎬 Competitor reference link · 2. ⚠️ Reviewer note (if any) · 3. Visual & Cast (Format, Look,
Cast, Scenes at a glance) · 4. **Full script — English** (one continuous block) · 5. **Full script
— <language> (romanized)** (one continuous block). No per-scene split, no TTS section.
*(To change this layout, edit `scripts/build_docs.py` only.)*

## How replication is decided (defined fully in `generate_workflow.js` + the brand .md files)
- **Faithful** (`Same`/`Ditto`/blank): re-skin the proven ad to Supernova AI, changing as little as possible — keep its hook, exact wrong-English example, speaker order, and interaction pattern.
- **Brief**: the concept brief is a **mandatory override** (character/gender swaps, setting/format changes, specific lines it dictates); everything it doesn't touch is replicated faithfully.
- **HARD LINES** (always): full name "Supernova AI"; "Miss Nova" never spoken aloud; "30 days" is the only time-to-result claim; "7× cheaper" only on a cost cue (never "free"/a rupee figure); reveal late; action close. *(Authoritative text: `facebook/generation/supernova_brand_safety.md` + `supernova_direct_rewrite.md`.)*

## Troubleshooting
- **UNRESOLVED source** (step 2): the link wasn't in the repo and couldn't be downloaded — provide an `.mp4` (drop in `$WORK/videos/<NN>_<id>.mp4`) or a transcript JSON in `$WORK/transcripts/`, then re-run step 2.
- **yt-dlp blocked** (Instagram/FB login wall): download the reel manually, place it in `$WORK/videos/`, re-run.
- **Drive integration missing**: connect *claude.ai Google Drive*; without it, steps 6–7 can't create Docs.
- **Wrong-language / non-Latin leak / bracket placeholder** in romanized: step 4 flags it; re-run the verify/revise for that ad or fix the field, then rebuild (steps 5–7).
- **Re-running**: the integration can't edit/delete old Docs — a re-run creates a *new* folder + new links; update the CSV to the new links and delete the superseded folder manually.
