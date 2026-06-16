# Supernova — Direct seed→target rewrite (NO English master)

YOUR JOB — produce a Supernova ad DIRECTLY in the TARGET LANGUAGE (named at the very end of this prompt),
from a competitor's SEED-LANGUAGE ad (seed language also named at the end). Above you have Supernova's brand
context + pitch menu, the few HARD LINES, and the full localization rules for the target language. Below
(INPUT) is a scene-by-scene breakdown of a PROVEN competitor ad in its seed language. In ONE pass, RE-SKIN
it into a Supernova ad AND write it directly in natural, spoken, code-mixed TARGET language. There is NO
English master — do both at once.

## A. RE-SKIN (change as little as possible; the competitor ad is proven)
- Write the WHOLE ad as ONE continuous, natural conversation (not isolated scene fragments).
- Keep the seed's hook, its SPECIFIC lines/examples, who speaks first, and the turn order. The exact
  wrong-English example being corrected STAYS, and the **AI teacher CORRECTS it — NEVER voice the learner's
  wrong-English mistake yourself** (the human learner makes the mistake; Miss Nova corrects). A short
  clarifying / warmth clause on a kept example is fine; do not substitute examples or invent beats.
- Swap the competitor brand → **"Supernova AI"** (ALWAYS the full name, never bare "Supernova").
- The AI teacher's speaker label is **Miss Nova**, but she is **NEVER named aloud in the dialogue** — she is
  "I" / "me"; others say "an AI teacher". Never put the literal words "Miss Nova" inside a spoken line.
- Weave in the benefits the beats invite (lead with **"1 crore+ users"** and **"improve in just 30 days"**;
  **"30 days" is the ONLY time-to-result claim** — never invent another, e.g. not "21 days"/"a month").
- The **"7× cheaper"** cost claim: bring it in ONLY when a character cues cost (asks the price / "won't that
  cost a lot?") — answer it there. If there is no cue but it still fits, place it near the **END beside the
  CTA**; otherwise leave it out. NEVER force it mid-script.
- "You SPEAK" = **speaking PRACTICE**, never "out loud / loudly".
- Explain "in your own language" simply as **using the target language by name** (e.g. "in Hindi" / "Telugu
  lo"), never "your own language" / "mother tongue".
- Re-point the CTA to ONE single urgent first-person close at the end (install + download Supernova AI).
- Indianize names/places. Never cross the four HARD LINES.

## B. LOCALIZE (apply ALL the target-language rules above)
Natural spoken code-mixed TARGET language — native script with English keywords kept inline; anti-newspaperish;
correct relationship register (Miss Nova is always warm / polite); taught-English phrases stay in English;
comparative multipliers go local; numbers stay English numerals; read-aloud-test every line.

## OUTPUT — exactly one JSON object (no markdown fences, no commentary)
{
  "production_type": "<from input>",
  "format": "<the ad's format/container in a few words>",
  "visual_overview": "<2–4 plain sentences: what the ad LOOKS like end to end (setting, who is on screen, any app-UI cutaways, end card) — skim context for the editor, NOT the script>",
  "characters": [
    {"id": "<A/B as in input>", "name": "<assigned name; the AI teacher = Miss Nova (label only)>", "role": "<short>"}
  ],
  "scenes": [
    {
      "n": "<same as input>",
      "scene_label": "<short, describes the visual/action — NEVER a pitch-point label>",
      "script_native": "<this scene's slice of the ONE continuous conversation, in the TARGET language's NATIVE script with inline English keywords. Each spoken turn on its OWN line prefixed with the speaker's name + ' says:'. PURE DIALOGUE — one light inline cue like '(warmly)' allowed; never speak 'Miss Nova'. Empty string \"\" if the scene has no speech (music-only / pure visual).>",
      "script_roman": "<the SAME lines, romanized in Latin letters with inline English keywords.>"
    }
  ],
  "pitch_points_used": ["<the Supernova benefits you landed>"]
}

Same scene count + order as the input. Read top-to-bottom, the scenes MUST form ONE unbroken, natural
conversation (no recap, brand introduced once). A music-only / pure-visual scene gets empty "" scripts.
Output 100% valid JSON.
