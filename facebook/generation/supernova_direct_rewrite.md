# Supernova — Direct seed→target rewrite (NO English master)

YOUR JOB — produce a Supernova ad DIRECTLY in the TARGET LANGUAGE (named at the very end of this prompt),
from a competitor's SEED-LANGUAGE ad (seed language also named at the end). Above you have Supernova's brand
context + pitch menu, the few HARD LINES, and the full localization rules for the target language. Below
(INPUT) is a scene-by-scene breakdown of a PROVEN competitor ad in its seed language. In ONE pass, RE-SKIN
it into a Supernova ad AND write it directly in natural, spoken, code-mixed TARGET language. There is NO
English master — do both at once.

## A. RE-SKIN (change as little as possible; the competitor ad is proven)
- Write the WHOLE ad as ONE continuous, natural conversation (not isolated scene fragments).
- Keep the seed's hook, its SPECIFIC lines/examples, who speaks first, and the turn order. **The hook's
  exact CLAIM / FRAMING is frozen** — preserve WHAT the opener asserts (translate it faithfully): "not able
  to speak English" / "don't know English" must STAY that; never recast it as "afraid / scared to speak" or
  "can't speak", and never inject the brand's fear / no-judgement angle into the opener.
- **PRESERVE THE SEED'S INTERACTION PATTERN (the teaching mechanic) — not just the lines.** Check the
  decompose's `interaction_pattern`. If the teacher SAYS a phrase and the learner REPEATS it back (a
  model-and-repeat / repeat-after-me drill), KEEP that exact mechanic — the teacher leads with the phrase,
  the learner echoes it; do NOT turn it into a quiz where the teacher ASKS and the learner ANSWERS, and do
  NOT make a struggling beginner suddenly produce correct English on her own. A live correction stays a
  correction; a testimonial stays a testimonial. Treat the learner exactly as the seed shows her (a beginner
  being drilled stays a beginner). The concept brief may reclassify the format; otherwise preserve the mechanic.
- **The wrong-English CORRECTION beat applies ONLY IF the seed actually contains a learner mistake.** If the
  seed has no wrong-English line (e.g. a repeat-after-me drill, a testimonial, a feature montage), do NOT
  invent one. When a mistake IS present: the human learner makes it and the **AI teacher CORRECTS it — NEVER
  voice the learner's wrong-English mistake yourself.** A short clarifying / warmth clause on a kept example
  is fine; do not substitute examples or invent beats.
- **No spoken voiceover? Re-skin the ON-SCREEN TEXT.** If the seed has NO spoken dialogue and carries its
  message as ON-SCREEN TEXT over a song / music (a captioned / meme ad — see the decompose's `audio_track`
  and per-scene `on_screen_text`), build the script by re-skinning and translating that ON-SCREEN TEXT (it
  IS the ad's copy). Do NOT emit empty scripts and do NOT fabricate a spoken voiceover that pretends to be
  the original. (A reviewer remark will note that the source had no voiceover and what the audio was.)
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
- **Reveal Supernova AI LATE.** Keep the first part the relatable, in-world moment (the correction +
  rapport + the benefits the beats invite); bring the product in only in the **back portion** of the ad,
  ideally *asked into existence* by the learner's own interest ("How do I start?" / "That sounds amazing!"),
  the teacher naming it in response — NOT announced up front. Follow the seed if it genuinely reveals early.
- **Warmth + a little chemistry (where the moment supports it).** After a correction, prefer a short
  **"why?" exchange** — the learner asks why and the teacher explains the logic in one or two sentences
  (this earns the rest). Let the two react to each other — the learner surprised ("Really?!"), a little
  embarrassed, pushing back; the teacher warm and encouraging. Use where it fits; never force it onto a seed
  with no room. **Laughter is SHARED** — never the teacher laughing alone *at* the learner's mistake.
- **The learner's final beat is ACTION / commitment** ("I'm downloading right now!" / "Yes, let's start!"),
  never a polite thank-you.
- **Objections — only if the seed's situation invites them:** the natural order is **time first** ("I don't
  get time"), then **fear / embarrassment** ("people will laugh"), each answered as it comes. A tool for when
  the context calls for it — never imposed on a seed that has none.
- Do NOT add commerce / legal framing the seed lacks — no "cancel anytime" / subscription / trial / pricing.
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
