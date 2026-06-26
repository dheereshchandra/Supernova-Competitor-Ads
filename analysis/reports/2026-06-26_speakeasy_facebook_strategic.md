# Strategic view — speakeasy (facebook)

*Generated from 271 ads, latest 2026-06-26.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-06-22 | 111 | 111 | 52 | 0.468 |
| 2026-06-23 | 30 | 0 | 28 | 0.933 |
| 2026-06-24 | 112 | 43 | 46 | 0.411 |
| 2026-06-25 | 136 | 50 | 43 | 0.316 |
| 2026-06-26 | 172 | 67 | 41 | 0.238 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 221 | 45 | 0.204 |
| ai_plus_ai | 40 | 4 | 0.1 |
| human_only | 5 | 1 | 0.2 |
| other | 5 | 2 | 0.4 |
| split_screen | 148 | 31 | 0.209 |
| TOTAL | 271 | 52 | 0.192 |

*split-screen ads (captured both above and in `speakeasy_raw_format_counts.csv`): 148.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 148 | 31 | 0.209 |
| skit-narrative | 76 | 12 | 0.158 |
| app-demo | 43 | 7 | 0.163 |
| text-on-screen-only | 2 | 1 | 0.5 |
| other | 1 | 1 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 153 | 28 | 0.183 |
| fear-shame | 42 | 11 | 0.262 |
| habit-aspiration | 34 | 5 | 0.147 |
| translation-practice | 16 | 2 | 0.125 |
| understand-cant-speak | 14 | 3 | 0.214 |
| social-proof | 9 | 3 | 0.333 |
| other | 2 | 0 | 0.0 |

*Price / offer hook present in 177 of 271 ads. Split-screen role split in `speakeasy_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 261 | 0.188 |
| human_only | 5 | 0.2 |
| paper_translation | 0 | 0.0 |
| other | 5 | 0.4 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-22 | 189 | 5 | 271 | 52 | 0.192 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 5 | 3 | 2.4 | 0 | 4 |
| exact_replica | 15 | 2 | 1.8 | 0 | 3 |
| reworded_replica | 42 | 0.0 | 0.9 | 0 | 4 |
| translation_replica | 13 | 4 | 3.3 | 0 | 4 |
| visual_variant | 4 | 2.5 | 2.2 | 0 | 4 |
| ALL | 79 | 2 | 1.6 | 0 | 4 |

*Fastest replicated group: `speakeasy-g0000` — replica `2513169462430169` (reworded_replica) appeared 0 day(s) after the original `1354159723277515`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakeasy-g0000 | 8 | 8 | 0 | 0.0 | character_variant;original;reworded_replica;visual_variant |
| speakeasy-g0001 | 7 | 7 | 3 | 0.429 | original;reworded_replica;translation_replica |
| speakeasy-g0002 | 6 | 6 | 1 | 0.167 | exact_replica;original;reworded_replica;translation_replica |
| speakeasy-g0003 | 6 | 6 | 3 | 0.5 | exact_replica;original;reworded_replica;translation_replica |
| speakeasy-g0004 | 5 | 5 | 1 | 0.2 | original;reworded_replica |
| speakeasy-g0005 | 5 | 5 | 1 | 0.2 | character_variant;original;reworded_replica |
| speakeasy-g0006 | 4 | 4 | 2 | 0.5 | original;reworded_replica |
| speakeasy-g0007 | 4 | 4 | 1 | 0.25 | original;reworded_replica;translation_replica |
| speakeasy-g0008 | 4 | 4 | 1 | 0.25 | original;reworded_replica |
| speakeasy-g0009 | 4 | 4 | 0 | 0.0 | original;reworded_replica;translation_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakeasy_by_language.csv` and `speakeasy_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakeasy_by_replication.csv` and the new `speakeasy_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakeasy_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

