// ============================================================================
// THE GENERATION PROMPTS — SINGLE SOURCE OF TRUTH.
// This file is the ONLY place the write / verify / revise prompts live.
// The Supernova brand rules are NOT copied here — they live only in
//   facebook/generation/supernova_{creative_context,direct_rewrite,
//   translation_rules,brand_safety,casting}.md
// and the agents below READ them at runtime. To change generation behaviour,
// edit THIS file (orchestration + prompt scaffolding) or those .md files
// (brand rules) — never restate a prompt anywhere else (e.g. in SKILL.md).
//
// Run via the Workflow tool:
//   Workflow({ scriptPath: ".../scripts/generate_workflow.js",
//              args: { root: "<repo root abs path>", ads: [ {n,name,language,
//                       faithful,brief_raw,duration_s,format,angle}, ... ] } })
// Each ad's full competitor transcript is read by the agents from
//   <root>/<workdir>/source_master.json   (entry whose "n" matches),
// so `args` stays small. Returns: [{n, script, verdict, revised}, ...].
// ============================================================================
export const meta = {
  name: 'replicate-competitor-ads',
  description: 'Generate Supernova AI ad replications (English + romanized target language) with adversarial verification',
  phases: [
    { title: 'Write', detail: 'one writer per ad → English re-skin + romanized target language' },
    { title: 'Verify', detail: 'adversarial QC vs brand HARD LINES, brief adherence, fidelity' },
    { title: 'Revise', detail: 'fix flagged scripts and re-verify' },
  ],
}

const A = (typeof args === 'string') ? JSON.parse(args) : (args || {})
const ADS = A.ads
const ROOT = A.root
const SRC_FILE = A.sourceFile || `${ROOT}/.context/replicate/source_master.json`
if (!Array.isArray(ADS)) throw new Error(`ads not an array: typeof args=${typeof args}; keys=${Object.keys(A || {})}`)
if (!ROOT) throw new Error('root missing from args')

const RULE_FILES = `Read these brand-rule files with the Read tool and follow them exactly (they are the authoritative source — do not rely on memory):
- ${ROOT}/facebook/generation/supernova_creative_context.md   (who Supernova AI is + the claim menu)
- ${ROOT}/facebook/generation/supernova_direct_rewrite.md      (the re-skin rules + output expectations)
- ${ROOT}/facebook/generation/supernova_brand_safety.md        (the few HARD LINES — authoritative)
- ${ROOT}/facebook/generation/supernova_translation_rules.md   (localization — read the section for the target language)`

// Condensed cheat-sheet of the hard lines. AUTHORITATIVE source is
// supernova_brand_safety.md / supernova_direct_rewrite.md — keep this in sync
// only if those hard lines themselves change (rare).
const HARD = `HARD LINES (never break — full text in supernova_brand_safety.md / supernova_direct_rewrite.md):
- Brand is ALWAYS "Supernova AI" (full name). Replace the source brand everywhere — it must NOT appear.
- The AI teacher's label is "Miss Nova" but she is NEVER named aloud in any spoken line — she is "I"/"me"; others call her "an AI teacher". (On-screen bubble labels are not speech.)
- "30 days" is the ONLY time-to-result claim. If the source says "15 days" / "one week" / "a month" / "fast", make it "improve in just 30 days". Never invent another (no "21 days").
- Daily practice time = "10–15 minutes a day" (use "just 10 minutes" when answering a no-time objection).
- Lead with the two flagship claims where they fit: "1 crore+ users" and "improve in just 30 days".
- Cost claim = "7× cheaper than offline classes" — ONLY when a character cues cost. NEVER a rupee figure, NEVER "free". If the source says "free"/"₹1"/"1 rupee", convert to the 7×-cheaper framing (or drop if there is no cost cue). Do not add pricing/subscription/cancel-anytime framing.
- Keep the seed's HOOK CLAIM frozen, its EXACT wrong-English example, and its INTERACTION PATTERN. Do not invent a learner mistake the seed lacks. NEVER voice the learner's wrong-English line as the teacher's own line.
- "You speak" = speaking PRACTICE, never "out loud / loudly". "Explains in your language" → name the language, never "mother tongue" / "your own language".
- Reveal Supernova AI LATE; the learner's final beat is action / commitment, never a polite thank-you.`

const SCHEMA = {
  type: 'object',
  properties: {
    n: { type: 'integer' },
    name: { type: 'string' },
    language: { type: 'string' },
    format: { type: 'string', description: 'the ad format/container in a few words' },
    visual_overview: { type: 'string', description: '2-4 sentences: what the ad looks like end to end, including any setting changes the brief requires' },
    reviewer_note: { type: 'string', description: 'optional — only if a real source issue / rule-conversion worth flagging to a human' },
    cast: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, name: { type: 'string' }, role: { type: 'string' } }, required: ['id', 'name', 'role'] } },
    scenes_at_a_glance: { type: 'array', items: { type: 'string' } },
    scenes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          n: { type: 'integer' },
          scene_label: { type: 'string' },
          english: { type: 'string', description: 'this scene\'s English lines; each spoken turn on its own line as "Name says: ..."; "" if no speech' },
          romanized: { type: 'string', description: 'the SAME turns in the target language, ROMANIZED (Latin, code-mix, NO native script); same order/speakers as english' },
        },
        required: ['n', 'scene_label', 'english', 'romanized'],
      },
    },
  },
  required: ['n', 'name', 'language', 'format', 'visual_overview', 'cast', 'scenes_at_a_glance', 'scenes'],
}

const VERDICT = {
  type: 'object',
  properties: {
    pass: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, area: { type: 'string' }, detail: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'detail'] } },
    notes: { type: 'string' },
  },
  required: ['pass', 'issues'],
}

const sceneGuess = (s) => Math.max(3, Math.round((s || 30) / 8))
const srcRef = (ad) => `COMPETITOR SOURCE AD — Read ${SRC_FILE} (a JSON array) and use the entry whose "n" == ${ad.n}. Its ".src" field is the decompose of the competitor ad to replicate: { language, format, presenter, angle, split_role, duration_s, transcript, on_screen_text, summary }. Replicate from .src.transcript (and .src.on_screen_text if there is no spoken dialogue). Source format≈${ad.format}, angle≈${ad.angle}, duration≈${ad.duration_s}s.`

function writePrompt(ad) {
  const mode = ad.faithful
    ? `FAITHFUL replication (sheet says "${ad.brief_raw}"). Replicate the competitor ad as-is, only re-skinned to Supernova AI. Keep its hook, its specific lines/examples, who speaks first, the turn order, and the interaction pattern. Change as little as possible.`
    : `CONCEPT BRIEF (MANDATORY — it OVERRIDES the competitor original where they differ; replicate faithfully for everything the brief does not change):\n"${ad.brief_raw}"`
  return `You are a senior Supernova AI ad scriptwriter. Re-skin a PROVEN competitor ad into a Supernova AI ad.

${RULE_FILES}

THE AD TO PRODUCE
- Internal name: ${ad.name}   (ad #${ad.n})
- Target language: ${ad.language}
- Replication mode: ${mode}

${srcRef(ad)}

${HARD}

OUTPUT — two languages in ONE script:
1) the ENGLISH replication (the master), and
2) the ${ad.language} version, ROMANIZED (Latin letters, natural spoken code-mix, NO native script).
Both are the SAME script, line-for-line parallel (same turns, same order, same speakers).

WRITING RULES
- Write the WHOLE ad as ONE continuous, natural conversation across scenes (not isolated fragments).
- Keep the source's scene structure/order; about ${sceneGuess(ad.duration_s)} scenes is typical for ${ad.duration_s}s. A music-only/visual-only scene gets english:"" and romanized:"".
- Each spoken turn on its own line: "Name says: ...". Indianize the human's name to fit ${ad.language}; the AI teacher = Miss Nova (label only, never spoken).
- visual_overview must describe the look end-to-end INCLUDING any setting/character the brief requires.
- The romanized ${ad.language} must be natural spoken code-mix: English keywords kept inline, numbers as English numerals, taught-English phrases (the corrected sentence) stay in English, warm/polite register for Miss Nova, readable aloud. Do NOT put native script in the romanized field.

Return ONLY the JSON object for the schema.`
}

function verifyPrompt(ad, script) {
  const briefCheck = ad.faithful
    ? `FAITHFUL: is the hook claim preserved? the exact wrong-English example kept? the interaction pattern intact (a correction stays a correction, a drill stays a drill, a testimonial stays a testimonial)? no invented learner mistake?`
    : `BRIEF (mandatory override): "${ad.brief_raw}". Confirm EVERY concrete thing the brief asks for is actually present — character/gender swaps, setting/location changes, format reclassification, and any specific lines/exchanges the brief dictates (verbatim if it gives them). Also confirm everything the brief does NOT mention is replicated faithfully from the source. If the source contained anything that breaks the HARD LINES (e.g. "free", "₹1", "one week"), confirm it was converted (7×-cheaper / "30 days").`
  return `You are an ADVERSARIAL QC reviewer for Supernova AI ad scripts. Be strict — default to flagging. Read the brand-rule files first:
${RULE_FILES}

REPLICATION MODE: ${ad.faithful ? 'FAITHFUL ("' + ad.brief_raw + '")' : 'CONCEPT BRIEF (mandatory override): "' + ad.brief_raw + '"'}
TARGET LANGUAGE: ${ad.language}

${srcRef(ad)} Use .src.transcript as the fidelity reference.

GENERATED SCRIPT (JSON):
${JSON.stringify(script)}

AUDIT for issues (severity blocker / major / minor):
1. HARD LINES — any SPOKEN "Miss Nova"? bare "Supernova" without "AI"? any leftover source brand? any time-to-result other than "30 days" (e.g. "15 days","one week","a month","21 days","fast")? "free" or any rupee figure for cost? "out loud/loudly"? "mother tongue"/"your own language"? teacher voicing the learner's wrong-English line?
2. ${briefCheck}
3. PARALLELISM — english vs romanized: same number of turns, same order, same speakers per scene?
4. LANGUAGE — is romanized actually ${ad.language} (not another language)? natural code-mix? readable? warm register? any NON-LATIN / native script leaking into the romanized field? any bracketed [placeholder] in romanized?
5. FLOW — one continuous conversation; Supernova AI revealed late; learner ends on action/commitment.

Return {pass, issues[], notes}. pass=true ONLY if there are NO blocker and NO major issues.`
}

function revisePrompt(ad, script, verdict) {
  return `Fix this Supernova AI ad script to resolve ALL the issues listed. Keep everything that is already correct. Output the corrected JSON (same schema). Consult the brand-rule files if needed:
${RULE_FILES}

REPLICATION MODE: ${ad.faithful ? 'FAITHFUL ("' + ad.brief_raw + '")' : 'BRIEF (override): "' + ad.brief_raw + '"'}
TARGET LANGUAGE: ${ad.language}

ISSUES TO FIX:
${JSON.stringify(verdict.issues, null, 2)}

CURRENT SCRIPT:
${JSON.stringify(script)}

${srcRef(ad)} Use .src.transcript as the reference.

Return ONLY the corrected JSON object.`
}

const out = await pipeline(
  ADS,
  (ad) => agent(writePrompt(ad), { label: `write:${ad.n}-${(ad.language || '').slice(0, 3)}`, phase: 'Write', schema: SCHEMA }),
  (script, ad) => agent(verifyPrompt(ad, script), { label: `verify:${ad.n}`, phase: 'Verify', schema: VERDICT }).then((v) => ({ script, verdict: v, ad })),
  async (sv, ad) => {
    if (!sv || !sv.script) return null
    if (sv.verdict && sv.verdict.pass) return { n: ad.n, script: sv.script, verdict: sv.verdict, revised: false }
    const fixed = await agent(revisePrompt(ad, sv.script, sv.verdict), { label: `revise:${ad.n}`, phase: 'Revise', schema: SCHEMA })
    const v2 = await agent(verifyPrompt(ad, fixed), { label: `reverify:${ad.n}`, phase: 'Revise', schema: VERDICT })
    return { n: ad.n, script: fixed, verdict: v2, revised: true }
  },
)

const final = out.filter(Boolean)
log(`generated ${final.length}/${ADS.length} scripts; clean=${final.filter((r) => r.verdict && r.verdict.pass).length}, revised=${final.filter((r) => r.revised).length}`)
return final
