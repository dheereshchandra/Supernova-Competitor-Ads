# Supernova — Brand-Safety Guardrails
*The hard NEVERs for every generated Supernova ad (feedback item #5). This is the single source of
truth used in two places: (1) it's loaded into the generation prompt so the writer avoids violations
up front, and (2) it's the rubric for the independent automated safety audit (`step4_safety_check.py`,
Gemini Flash) that checks every script before it reaches the team.*

> **How severity maps to a verdict.** Each guardrail is tagged **[SEVERE]** or **[MODERATE]**.
> The audit returns: **BLOCK** if any SEVERE violation is present · **FLAG** if only MODERATE
> violations · **PASS** if none. BLOCK = do not ship without a human fix; FLAG = a human should
> glance before it ships. The goal is a safety net that lets good scripts through untouched and
> stops harmful ones automatically.
>
> These are **safety/compliance limits, not creative limits.** They sit *under* the creative latitude
> in `supernova_creative_context.md` — stay wild and differentiated, just never cross these lines.

---

## G1 — Claims & legal

- **G1.1 [SEVERE] No brand-voiced outcome guarantees.** The brand/VO/on-screen text must never *promise*
  a result. ❌ "Guaranteed fluent in 7 days," "100% job after this course." ✅ A *character* may give a
  personal testimonial ("I improved in two weeks") — the brand never guarantees.
  - ✅ **Carve-out — soft progress expectation.** The brand MAY set a realistic, *non-guaranteed* progress
    expectation tied to consistent practice — "with daily practice you'll **start** seeing visible progress
    in about 30 days," "speak more confidently within a month." It must use hedge language
    (start / begin / most learners / can) and name **progress / confidence**, never a guaranteed end-state.
    ❌ Still BANNED: "guaranteed fluent in 30 days," "100% fluent in a month," or any job / income / visa /
    exam outcome on a timeline (see G1.2).
- **G1.2 [SEVERE] No false job / income / visa / exam outcomes.** ❌ "Get a US visa," "Double your
  salary," "Pass IELTS guaranteed." English is a confidence/skill tool, not a guaranteed outcome.
- **G1.3 [SEVERE] No fake authority or credentials.** ❌ presenting an actor as "a certified Cambridge
  examiner," fabricated awards, "Government approved," invented user/rating counts. (A true, approved
  proof point like "1 crore+ users" is fine — see G6.3.)
- **G1.4 [MODERATE] No absolute superlatives.** ❌ "world's #1 / the best English app / only app that
  works." ✅ comparative, defensible framing ("learn by *speaking*, not reading").

## G2 — Competitors & disparagement

- **G2.1 [MODERATE] Contrast, don't trash.** The ChatGPT contrast ("ChatGPT gives answers; Supernova
  extracts them from you") is on-brand and allowed. ❌ Naming and *insulting* a named competitor app
  ("unlike that useless XYZ app") — legal + policy risk. ❌ Naming a *third-party / competitor* learning
  channel or app (e.g. YouTube, or a NAMED coaching brand — the specific brand, NOT the generic category;
  "7× cheaper than coaching classes" as a cost comparator stays allowed per G6.2) only to call it a waste
  of time also counts as trashing — reference the *activity* ("passively watching videos"), not the brand.
  (The violation trigger is a NAMED platform/brand token — "YouTube", a coaching brand — not the generic
  verb; "scrolling tip-videos you never act on" with no platform named is fine.) ✅ Meta's OWN scroll
  surfaces (Reels / feeds) used as a generic "stop doomscrolling, spend the time learning" anchor are
  fine, as is the ChatGPT *behaviour* contrast ("ChatGPT gives answers, Supernova makes you speak").
  (The test is a NAMED third party + waste/negative framing — not "is it Meta-owned": Reels/feeds are OK
  ONLY as a neutral time-reallocation anchor ("spend that time learning"), never themselves trashed.)
- **G2.2 [SEVERE] No false claims about a named competitor.** Never state a falsehood about another
  named product/company.

## G3 — Dignity & representation

- **G3.1 [SEVERE] Shame must resolve in dignity.** The shame→authority hook is approved ONLY when the
  underdog or an authority *flips it into triumph/respect*. ❌ An ad that ends on the person still being
  mocked, humiliated, or "less than." Never punch down.
- **G3.2 [SEVERE] No demeaning of a protected/identity group.** Never mock or stereotype on the basis of
  caste, religion, region/language, gender, age, disability, body, skin tone, or economic class. Our
  audience is Tier 2–3, blue-collar India — portray them with warmth and respect, never as "backward,"
  "illiterate," or a punchline.
- **G3.3 [MODERATE] No language/accent mockery as the joke.** A *relatable* Indian-English error the
  viewer self-diagnoses is the hook; an accent or a person being the object of ridicule is not.
- **G3.4 [MODERATE] No attack on self-WORTH (behavior critique IS allowed).** Don't tell someone they're
  worthless or "less than" *as a person* without English. But motivating urgency about a HABIT or a missed
  opportunity is fine and often the winning hook — "you waste 4 hours a day scrolling but skip 15 minutes
  of English", "your appraisal is 30 days away" — because it targets a *choice*, not the person's worth.
  Tough-love, blunt, direct second person is allowed; only an attack on identity/worth is not.

## G4 — Meta / Facebook ad policy (these run as FB ads — violations get auto-rejected)

- **G4.1 [SEVERE] No assertion of a SENSITIVE / PROTECTED personal attribute.** Meta prohibits implying
  you *know* a sensitive trait of the viewer — health, finances, religion, caste, sexual orientation, a
  disability, or a worth-judgement like "illiterate". ❌ "Struggling illiterate?", "You who *failed* at
  English are worthless." ✅ Critiquing a BEHAVIOR or choice is fine and is often the winning hook:
  "you scroll 4 hours a day but skip 15 minutes of English — that's your mistake", "still hiding behind
  ChatGPT?", a relatable self-diagnosed error ("I used to say 'I passed out in 2022'"), or a neutral
  second-person prompt ("Describe this clip in English"). Blunt, tough-love second person is allowed —
  only a claimed sensitive trait or an attack on the viewer's identity/worth is not. (Real winners run on
  Meta for months with behavior-callout hooks; do not over-block them.)
- **G4.2 [SEVERE] No misleading mechanics / fake UI.** No fake "play" buttons, fake system warnings,
  fake chat notifications, sham countdown timers, or claims the app does something it doesn't.
- **G4.3 [MODERATE] No sensational / shocking before-after.** No exaggerated transformation claims or
  shock imagery used purely to bait clicks.
- **G4.4 [MODERATE] No prohibited/limited-content framing.** Avoid health-cure framing, gambling/quick-
  money framing, or anything reading as a get-rich-quick scheme.

## G5 — Sensitive themes

- **G5.1 [SEVERE] No exploitation of real trauma.** Deportation, unemployment, illness, poverty, or
  family conflict may appear ONLY as **clearly fictional/absurdist or aspirational** framing in service
  of confidence — never as realistic fear-mongering that exploits a genuine vulnerable situation.
  (The skeleton-deportation *thriller* is fine because it's overtly absurdist fiction.)
- **G5.2 [SEVERE] No political, religious, communal, or national-security content.** No real officials,
  parties, religious figures/symbols, or border/military framing presented as real.
- **G5.3 [MODERATE] No real-person likeness.** No real celebrities, influencers, or public figures
  (likeness, name, or voice) without rights — even as a look-alike.

## G6 — Price & financial

- **G6.1 [SEVERE] No hard rupee price or unapproved offer.** ❌ "Just ₹9," "₹299/month," "50% off
  today." Pricing/discounts must come from the team, not the generator.
- **G6.2 [MODERATE] Comparative cost only if apt.** A *comparative* ("7× cheaper than coaching classes,"
  "affordable") is allowed when it fits the scene — never a bare rupee figure.
- **G6.3 [MODERATE] Social proof only if true & approved.** "1 crore+ users" is an approved, true proof
  point — fine to use where it fits; don't fabricate a different number.

## G7 — Privacy & data framing

- **G7.1 [SEVERE] No creepy-surveillance framing.** The always-on, "talk at 3 a.m., make 1000 mistakes"
  benefit must read as **private and safe** (no one is watching/judging *you*). ❌ Anything implying the
  app records, shares, exposes, or judges the user, or that "everyone can hear you."
- **G7.2 [MODERATE] No data/secret-sharing implications.** Don't imply the user's voice, mistakes, or
  data are shared, posted, or used against them.

---

## What the auditor must do (rubric for `step4_safety_check.py`)

For each ad (script + on-screen text + visual descriptions), find EVERY real violation and emit:
`{guardrail_id, category, severity, scene, quote, why, fix}`. Be strict but precise — only genuine
violations, and **quote the exact offending text**. Then a one-line summary. The pipeline computes the
final verdict deterministically from the severities (any SEVERE → BLOCK; else any MODERATE → FLAG; else
PASS), so the auditor's job is accurate *violation detection*, not the verdict label.
