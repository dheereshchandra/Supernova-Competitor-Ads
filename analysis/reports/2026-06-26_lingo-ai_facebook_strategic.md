# Strategic view — lingo-ai (facebook)

*Generated from 271 ads, latest 2026-06-26.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-06-15 | 29 | 29 | 9 | 0.31 |
| 2026-06-16 | 42 | 25 | 7 | 0.167 |
| 2026-06-17 | 93 | 50 | 11 | 0.118 |
| 2026-06-22 | 53 | 35 | 2 | 0.038 |
| 2026-06-23 | 30 | 10 | 5 | 0.167 |
| 2026-06-24 | 105 | 46 | 7 | 0.067 |
| 2026-06-25 | 117 | 35 | 5 | 0.043 |
| 2026-06-26 | 147 | 41 | 6 | 0.041 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_ai | 216 | 8 | 0.037 |
| other | 48 | 2 | 0.042 |
| paper_translation | 4 | 3 | 0.75 |
| human_only | 3 | 0 | 0.0 |
| split_screen | 21 | 0 | 0.0 |
| TOTAL | 271 | 13 | 0.048 |

*split-screen ads (captured both above and in `lingo-ai_raw_format_counts.csv`): 21.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 86 | 3 | 0.035 |
| app-demo | 86 | 4 | 0.047 |
| listicle-montage | 43 | 1 | 0.023 |
| split-screen | 21 | 0 | 0.0 |
| other | 17 | 2 | 0.118 |
| text-on-screen-only | 8 | 0 | 0.0 |
| pen-and-paper | 4 | 3 | 0.75 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 76 | 2 | 0.026 |
| habit-aspiration | 70 | 2 | 0.029 |
| other | 56 | 4 | 0.071 |
| feature-demo | 40 | 5 | 0.125 |
| translation-practice | 23 | 0 | 0.0 |

*Price / offer hook present in 0 of 271 ads. Split-screen role split in `lingo-ai_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 216 | 0.037 |
| human_only | 3 | 0.0 |
| paper_translation | 4 | 0.75 |
| other | 48 | 0.042 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-15 | 83 | 7 | 104 | 13 | 0.125 |
| 2026-06-22 | 104 | 0 | 167 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 64 | 8.0 | 5.2 | 0 | 10 |
| reworded_replica | 6 | 0.5 | 2 | 0 | 9 |
| translation_replica | 2 | 0.0 | 0 | 0 | 0 |
| visual_variant | 5 | 1 | 3.4 | 0 | 8 |
| ALL | 77 | 6 | 4.7 | 0 | 10 |

*Fastest replicated group: `lingo-ai-g0000` — replica `27252840764373165` (exact_replica) appeared 0 day(s) after the original `1543351697304303`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| lingo-ai-g0000 | 9 | 9 | 0 | 0.0 | exact_replica;original;reworded_replica |
| lingo-ai-g0001 | 8 | 8 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0002 | 5 | 5 | 0 | 0.0 | exact_replica;original;visual_variant |
| lingo-ai-g0003 | 4 | 4 | 1 | 0.25 | exact_replica;original |
| lingo-ai-g0004 | 4 | 4 | 0 | 0.0 | exact_replica;original;translation_replica |
| lingo-ai-g0005 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0006 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0007 | 3 | 3 | 1 | 0.333 | exact_replica;original |
| lingo-ai-g0008 | 3 | 3 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0009 | 3 | 3 | 0 | 0.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `lingo-ai_by_language.csv` and `lingo-ai_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `lingo-ai_by_replication.csv` and the new `lingo-ai_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `lingo-ai_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

