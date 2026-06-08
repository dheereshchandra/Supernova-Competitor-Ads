# Strategic view — mysivi (facebook)

*Generated from 1838 ads, latest 2026-06-04.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 1596 | 1596 | 488 | 0.306 |
| 2026-06-04 | 1417 | 242 | 436 | 0.308 |

*Only a couple of scrape dates so far, so daily volume is sparse; it densifies as history accrues.*

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| other | 1749 | 422 | 0.241 |
| ai_plus_human | 65 | 62 | 0.954 |
| ai_plus_ai | 10 | 10 | 1.0 |
| paper_translation | 9 | 9 | 1.0 |
| human_only | 5 | 5 | 1.0 |
| split_screen | 51 | 48 | 0.941 |
| TOTAL | 1838 | 508 | 0.276 |

*split-screen ads (captured both above and in `mysivi_raw_format_counts.csv`): 51.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 51 | 48 | 0.941 |
| skit-narrative | 26 | 26 | 1.0 |
| pen-and-paper | 9 | 9 | 1.0 |
| app-demo | 7 | 7 | 1.0 |
| text-on-screen-only | 2 | 2 | 1.0 |
| other | 2 | 2 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 43 | 41 | 0.953 |
| translation-practice | 16 | 15 | 0.938 |
| fear-shame | 14 | 14 | 1.0 |
| habit-aspiration | 8 | 8 | 1.0 |
| understand-cant-speak | 7 | 7 | 1.0 |
| social-proof | 5 | 5 | 1.0 |
| feature-demo | 4 | 4 | 1.0 |

*Price / offer hook present in 67 of 1838 ads. Split-screen role split in `mysivi_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 75 | 0.96 |
| human_only | 5 | 1.0 |
| paper_translation | 9 | 1.0 |
| other | 1749 | 0.241 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 43 | 7 | 1596 | 488 | 0.306 |
| 2026-06-01 | 0 | 0 | 242 | 20 | 0.083 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| character_variant | 1 | 0 | 0 | 0 | 0 |
| exact_replica | 21 | 0 | 0 | 0 | 0 |
| translation_replica | 25 | 0 | 0 | 0 | 0 |
| visual_variant | 7 | 0 | 0 | 0 | 0 |
| ALL | 54 | 0.0 | 0 | 0 | 0 |

*Fastest replicated group: `mysivi-g0000` — replica `809446541711698` (visual_variant) appeared 0 day(s) after the original `1003719535314984`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| mysivi-g0000 | 10 | 10 | 10 | 1.0 | exact_replica;original;visual_variant |
| mysivi-g0001 | 7 | 7 | 7 | 1.0 | exact_replica;original;translation_replica |
| mysivi-g0002 | 6 | 6 | 6 | 1.0 | exact_replica;original;translation_replica |
| mysivi-g0003 | 6 | 6 | 5 | 0.833 | original;translation_replica |
| mysivi-g0004 | 5 | 5 | 5 | 1.0 | character_variant;exact_replica;original;translation_replica |
| mysivi-g0005 | 5 | 5 | 5 | 1.0 | original;translation_replica |
| mysivi-g0006 | 5 | 5 | 5 | 1.0 | exact_replica;original;translation_replica |
| mysivi-g0007 | 4 | 4 | 4 | 1.0 | exact_replica;original;translation_replica |
| mysivi-g0008 | 3 | 3 | 1 | 0.333 | exact_replica;original;translation_replica |
| mysivi-g0009 | 3 | 3 | 3 | 1.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `mysivi_by_language.csv` and `mysivi_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `mysivi_by_replication.csv` and the new `mysivi_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `mysivi_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

