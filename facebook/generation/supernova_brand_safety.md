# Supernova AI — The Hard Lines + Auditor Spec (v3)
*This is NOT a style guide. The competitor ad is proven — we replicate it and DO NOT rewrite anything in
the name of "guidelines." Stop ONLY for the handful of genuine extremes below. (The old long G1–G7 list
and all Facebook/Google ad-policy rules have been removed.)*

## THE ONLY HARD LINES — stop / fix ONLY if the script:
1. **Shame without dignity** — shames or mocks a person and **leaves them humiliated**. A shame→authority
   hook is fine ONLY when it resolves into triumph/respect. Never punch down.
2. **Demeaning a protected group** — mocks or stereotypes on caste, religion, region/language, gender,
   age, disability, body, skin tone, or economic class. Our audience is Tier 2–3 blue-collar India —
   portray them with warmth, never as "backward," "illiterate," or a punchline.
3. **Exploiting real trauma** — deportation, unemployment, illness, poverty, family conflict used as
   *realistic fear-mongering*. Clearly fictional / absurdist framing is fine.
4. **Political / religious / communal content, or a real person's likeness** (celebrity / influencer /
   official — name, face, or voice) without rights.

Everything else follows the competitor: blunt tough-love hooks, behaviour callouts ("you scroll 4 hours a
day but skip 15 minutes of English"), confident benefit claims, ChatGPT contrasts, comparative cost —
**all allowed.** No price/guarantee rule, no hedge-every-claim rule, no platform-policy rules. When
unsure, **KEEP the seed.**

---

## WHAT THE AUDITOR MUST DO (rubric for `step4_safety_check.py`)
The auditor is a **review-priority signal, not a gate**. It receives the competitor's **original** script
AND our **rewrite**, so it can compare them. It runs **three** checks and emits findings
`{check, severity, scene, quote, why, fix}`:

1. **`hard_line`** — is any of the 4 hard lines above present? (severe → priority review)
2. **`deviation`** — does our rewrite significantly change the competitor's **hook**, its **specific
   lines/examples**, or the **opening speaker / turn order** vs the original? Significant drift → flag
   **"human review needed"** (severe). The model may have deviated for a good reason — a human confirms.
   Do NOT flag normal re-skinning (brand swap → Supernova AI / Miss Nova, the ≥3 woven pitch points, a
   re-pointed CTA, Indianized names/places) as deviation.
3. **`error`** — wrong or inconsistent **character names** (must be Indian + consistent; "Miss Nova" for
   the AI), **non-Indian or invented locations**, hallucinated content, or brand mislabels (moderate, or
   severe if it breaks the ad). **Also flag (moderate) any spoken line that says the character name
   "Miss Nova" aloud** — "Miss Nova" is the AI teacher's internal speaker-label only and is NEVER named in
   the voiceover (she refers to herself as "I"/"me"; others say "an AI teacher" / "this AI teacher"). NOTE:
   the "Name says:" prefix is a speaker LABEL, not spoken words — judge only the text AFTER "says:", so
   "Miss Nova says: …" is fine; flag only if "Miss Nova" is in the spoken portion. The spoken **product**
   name "Supernova AI" is fine — only the **character** name "Miss Nova" must not appear inside a spoken line.

**Severity → verdict** (computed deterministically): any **severe** → `block` (🔴 Priority review) ·
any **moderate** → `flag` (🟡 Review suggested) · none → `pass` (🟢 Standard). Be precise, quote the exact
text, and never invent findings to look thorough.
