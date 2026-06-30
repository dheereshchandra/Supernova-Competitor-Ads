# Strategic view — speakeasy (facebook)

*Generated from 409 ads, latest 2026-06-30.*

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
| 2026-06-27 | 210 | 62 | 41 | 0.195 |
| 2026-06-29 | 150 | 17 | 39 | 0.26 |
| 2026-06-30 | 194 | 59 | 33 | 0.17 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 330 | 45 | 0.136 |
| ai_plus_ai | 61 | 4 | 0.066 |
| human_only | 11 | 1 | 0.091 |
| other | 7 | 2 | 0.286 |
| split_screen | 226 | 31 | 0.137 |
| TOTAL | 409 | 52 | 0.127 |

*split-screen ads (captured both above and in `speakeasy_raw_format_counts.csv`): 226.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 226 | 31 | 0.137 |
| skit-narrative | 118 | 12 | 0.102 |
| app-demo | 56 | 7 | 0.125 |
| text-on-screen-only | 7 | 1 | 0.143 |
| other | 1 | 1 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 220 | 28 | 0.127 |
| fear-shame | 71 | 11 | 0.155 |
| habit-aspiration | 54 | 5 | 0.093 |
| understand-cant-speak | 24 | 3 | 0.125 |
| translation-practice | 23 | 2 | 0.087 |
| social-proof | 14 | 3 | 0.214 |
| other | 2 | 0 | 0.0 |

*Price / offer hook present in 256 of 409 ads. Split-screen role split in `speakeasy_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 391 | 0.125 |
| human_only | 11 | 0.091 |
| paper_translation | 0 | 0.0 |
| other | 7 | 0.286 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-22 | 228 | 5 | 333 | 52 | 0.156 |
| 2026-06-29 | 40 | 0 | 76 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 7 | 3 | 3.3 | 0 | 7 |
| exact_replica | 49 | 2 | 2.5 | 0 | 5 |
| reworded_replica | 48 | 0.0 | 1.4 | 0 | 8 |
| translation_replica | 30 | 4.0 | 4.0 | 0 | 8 |
| visual_variant | 6 | 3.5 | 3.7 | 0 | 8 |
| ALL | 140 | 2.0 | 2.5 | 0 | 8 |

*Fastest replicated group: `speakeasy-g0000` — replica `832059772860621` (reworded_replica) appeared 0 day(s) after the original `1003649275414638`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| speakeasy-g0000 | 9 | 9 | 3 | 0.333 | original;reworded_replica;translation_replica;visual_variant |
| speakeasy-g0001 | 9 | 9 | 0 | 0.0 | character_variant;original;reworded_replica;visual_variant |
| speakeasy-g0002 | 9 | 9 | 3 | 0.333 | exact_replica;original;reworded_replica;translation_replica |
| speakeasy-g0003 | 7 | 7 | 1 | 0.143 | exact_replica;original;reworded_replica;translation_replica |
| speakeasy-g0004 | 7 | 7 | 0 | 0.0 | exact_replica;original;reworded_replica;translation_replica |
| speakeasy-g0005 | 6 | 6 | 0 | 0.0 | original;translation_replica |
| speakeasy-g0006 | 5 | 5 | 1 | 0.2 | original;reworded_replica |
| speakeasy-g0007 | 5 | 5 | 1 | 0.2 | character_variant;original;reworded_replica |
| speakeasy-g0008 | 5 | 5 | 1 | 0.2 | original;reworded_replica;translation_replica |
| speakeasy-g0009 | 4 | 4 | 1 | 0.25 | original;reworded_replica |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `speakeasy_by_language.csv` and `speakeasy_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `speakeasy_by_replication.csv` and the new `speakeasy_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `speakeasy_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

