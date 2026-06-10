"""
_casting.py — shared casting/localisation rules for the Step-4 image generation (feedback #8).

Two jobs:
  1. LOCALISE TO INDIA — competitor ads we replicate are often foreign; copying their visuals
     yields foreign-looking people/settings. These rules force every HUMAN character + setting to
     read as authentically Indian (Tier 2/3), while keeping role/age/build/demeanour.
  2. MISS NOVA — Supernova's signature AI-teacher mascot. When a character IS the AI teacher, render
     her as Miss Nova (a consistent 3D mascot), not a generic person. Reference art lives in
     facebook/generation/assets/miss_nova/ (PLACEHOLDER ASO screenshots until brand assets arrive).

Imported by step4_character_sheets.py and step4_panels.py. Full human-readable policy:
facebook/generation/supernova_casting.md.
"""
from __future__ import annotations

import pathlib
import re

ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "generation" / "assets" / "miss_nova"
# Primary reference for image-conditioning (cleanest bust shot). Placeholder until brand assets land.
MISS_NOVA_PRIMARY_REF = ASSETS_DIR / "miss_nova_classroom.png"

# Text descriptor of Miss Nova, derived from the placeholder ASO art. Used in the image prompt so she
# renders consistently even without image-conditioning.
MISS_NOVA_DESC = (
    "Miss Nova — Supernova's signature AI English-teacher mascot: a warm, friendly young woman drawn "
    "in clean, vibrant 3D-animated (Pixar/Disney) style (NOT photorealistic). Chin-length wavy "
    "auburn-brown hair, large expressive brown eyes, a bright encouraging smile. She wears a "
    "distinctive burnt-orange / rust high-collar 'space-suit'-style top with light-grey panel accents "
    "and a small glowing Supernova star badge on the chest; in AI-teacher shots she may wear a slim "
    "black headset with a mic. Upbeat, approachable, supportive."
)

# Tokens that mark a character as the AI teacher (-> render as Miss Nova). Word-boundary matched so
# 'ai' doesn't match 'maid' etc. 'sivi'/'nova' catch competitor/our AI-teacher names.
_AI_TEACHER_RE = re.compile(
    r"\b(a\.?i\.?|robot|avatar|assistant|hologram|holographic|virtual|chat-?bot|bot|android|"
    r"sivi|nova)\b|miss\s*nova",
    re.IGNORECASE,
)


def is_ai_teacher(character: dict) -> bool:
    """True if this decompose character is the AI teacher/assistant (-> Miss Nova)."""
    blob = " ".join(str(character.get(k, "")) for k in
                    ("id", "role", "appearance", "wardrobe", "demeanor"))
    return bool(_AI_TEACHER_RE.search(blob))


# --- localisation instruction blocks (kept tight — image models prefer short, direct prompts) ---

INDIA_CASTING_RULE = (
    "CASTING — LOCALISE TO INDIA (critical):\n"
    "- Render every HUMAN character as an authentically INDIAN person in an everyday Tier-2/Tier-3 "
    "India context. Keep the ROLE, age, gender, build, expression and demeanour from the description, "
    "but ethnicity, skin tone, facial features and hair MUST read as natural Indian — NEVER "
    "Western/European/East-Asian/foreign, even if the source description says otherwise.\n"
    "- Wardrobe: everyday Indian clothing appropriate to the role (kurta, salwar/saree, simple "
    "shirt-trousers, a work uniform) unless the role genuinely demands otherwise — not Western "
    "business/casual by default.\n"
    "- Keep the SAME person looking consistent across panels."
)

INDIA_SETTING_RULE = (
    "SETTING — LOCALISE TO INDIA: Indian homes, streets, offices, shops, classrooms; Indian signage, "
    "props, vehicles and styling. Never a foreign-looking location."
)

MISS_NOVA_RULE = (
    "This character is the AI teacher — render her as MISS NOVA, exactly and consistently:\n"
    f"{MISS_NOVA_DESC}\n"
    "Do NOT make her a generic human or a foreign-looking person; she is the 3D-animated orange-suited "
    "mascot above. (Reference art is a placeholder; keep her look consistent with it.)"
)


def miss_nova_ref_image_part(gt):
    """Return a Gemini image Part for Miss Nova reference-conditioning, or None if no asset on disk."""
    if MISS_NOVA_PRIMARY_REF.exists():
        return gt.Part.from_bytes(data=MISS_NOVA_PRIMARY_REF.read_bytes(), mime_type="image/png")
    return None
