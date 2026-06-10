# Supernova — Casting & Localisation (feedback item #8)

*How the generated VISUALS get cast. The script side (#3/#4) keeps a competitor ad's proven concept;
this is the rule for the **people and places** in it. Enforced in the Step-4 image generation
(`step4_character_sheets.py`, `step4_panels.py`) via the shared `facebook/scripts/_casting.py`.*

---

## The core problem this fixes

We replicate proven competitor ads. If we copy their visuals faithfully and the competitor was running
a **foreign** ad, our regenerated visuals come out **foreign-looking** — wrong people, wrong settings
for an Indian audience. The decompose step describes whatever the source showed, and the old image
prompts said *"skin tone, hair … MUST match the description precisely"* — which **locked in** the
foreign casting.

## The rule — localise to India

- **Every HUMAN character is re-cast as an authentically Indian person**, for an everyday **Tier-2 /
  Tier-3 India** context. Keep the character's **role, age, gender, build, expression and demeanour**
  from the source; change **ethnicity, skin tone, features, hair and wardrobe** so they read as natural
  Indian — **never** Western / European / East-Asian / foreign, even if the source description says so.
- **Wardrobe** = everyday Indian clothing fit for the role (kurta, salwar/saree, simple shirt-trousers,
  a work uniform), not Western business/casual by default.
- **Settings** = Indian homes, streets, offices, shops, classrooms; Indian signage, props, vehicles.
- **Consistency** = the same person looks the same across panels.

This sits *under* the "keep the core visual" rule from `supernova_creative_context.md`: keep the
**composition / concept / camera**, swap the **casting** to authentic India.

## Miss Nova (the AI teacher) — PLACEHOLDER, pending brand assets

When a character **is the AI teacher** (detected from the decompose role/appearance — "AI", "robot",
"avatar", "assistant", "Sivi", "Nova"…), render her as **Miss Nova**, not a generic person:

> Warm, friendly young woman in clean **3D-animated (Pixar/Disney) style** (not photorealistic).
> Chin-length wavy auburn-brown hair, large expressive eyes, bright encouraging smile. Distinctive
> **burnt-orange / rust 'space-suit' top** with light-grey accents and a small glowing **Supernova
> star badge**; in AI-teacher shots, a slim black headset+mic.

- **Reference art:** `facebook/generation/assets/miss_nova/` — these are **placeholder ASO screenshots**
  (`miss_nova_classroom / _phone / _headset`). The cleanest one is used for image-conditioning.
- **This is intentionally a placeholder.** Real brand assets will replace these; Miss Nova's exact look
  is not critical here because editors refine her in post. Swap the files in `assets/miss_nova/`
  (and tighten `MISS_NOVA_DESC` in `_casting.py`) when brand art arrives — no other code changes needed.

## First-frame localisation (the highest-leverage frame)

The opening frame (scene 1) is the thumbnail/hook — it must be unmistakably Indian and per-language
appropriate. Lean on regional cues where known: e.g. **Marathi** → Maharashtra wardrobe/streetscape,
**Tamil/Telugu** → South-Indian cues, **Bengali** → Kolkata cues. On-screen text is added by editors in
the target script later (the generated panels are intentionally text-free).

## Where it's wired

- `facebook/scripts/_casting.py` — `is_ai_teacher()`, `MISS_NOVA_DESC`, the India casting/setting rules,
  and Miss-Nova image-conditioning. Single source for both image stages.
- `step4_character_sheets.py` (Stage 3) — per-character reference sheets: AI teacher → Miss Nova (with
  reference image); humans → authentic Indian.
- `step4_panels.py` (Stage 4) — scene panels: same casting rules + Indian settings.
