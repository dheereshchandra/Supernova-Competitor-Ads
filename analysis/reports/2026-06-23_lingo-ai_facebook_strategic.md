# Strategic view — lingo-ai (facebook)

*Generated from 149 ads, latest 2026-06-23.*

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

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_ai | 111 | 8 | 0.072 |
| other | 32 | 2 | 0.062 |
| paper_translation | 3 | 3 | 1.0 |
| human_only | 3 | 0 | 0.0 |
| split_screen | 15 | 0 | 0.0 |
| TOTAL | 149 | 13 | 0.087 |

*split-screen ads (captured both above and in `lingo-ai_raw_format_counts.csv`): 15.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| skit-narrative | 49 | 3 | 0.061 |
| app-demo | 45 | 4 | 0.089 |
| listicle-montage | 19 | 0 | 0.0 |
| split-screen | 15 | 0 | 0.0 |
| other | 12 | 2 | 0.167 |
| text-on-screen-only | 5 | 0 | 0.0 |
| pen-and-paper | 3 | 3 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 40 | 2 | 0.05 |
| habit-aspiration | 38 | 2 | 0.053 |
| other | 30 | 3 | 0.1 |
| feature-demo | 25 | 5 | 0.2 |
| translation-practice | 15 | 0 | 0.0 |

*Price / offer hook present in 0 of 149 ads. Split-screen role split in `lingo-ai_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 111 | 0.072 |
| human_only | 3 | 0.0 |
| paper_translation | 3 | 1.0 |
| other | 32 | 0.062 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-06-15 | 82 | 7 | 104 | 13 | 0.125 |
| 2026-06-22 | 32 | 0 | 45 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 25 | 1 | 1.2 | 0 | 6 |
| reworded_replica | 4 | 0.5 | 0.8 | 0 | 2 |
| translation_replica | 2 | 0.0 | 0 | 0 | 0 |
| visual_variant | 3 | 1 | 0.7 | 0 | 1 |
| ALL | 34 | 1.0 | 1.1 | 0 | 6 |

*Fastest replicated group: `lingo-ai-g0000` — replica `27252840764373165` (exact_replica) appeared 0 day(s) after the original `1543351697304303`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| lingo-ai-g0000 | 9 | 9 | 0 | 0.0 | exact_replica;original;reworded_replica |
| lingo-ai-g0001 | 8 | 8 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0002 | 5 | 5 | 0 | 0.0 | exact_replica;original;visual_variant |
| lingo-ai-g0003 | 4 | 4 | 0 | 0.0 | exact_replica;original;translation_replica |
| lingo-ai-g0004 | 2 | 2 | 1 | 0.5 | exact_replica;original |
| lingo-ai-g0005 | 2 | 2 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0006 | 2 | 2 | 1 | 0.5 | exact_replica;original |
| lingo-ai-g0007 | 2 | 2 | 0 | 0.0 | exact_replica;original |
| lingo-ai-g0008 | 2 | 2 | 1 | 0.5 | original;reworded_replica |
| lingo-ai-g0009 | 2 | 2 | 0 | 0.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `lingo-ai_by_language.csv` and `lingo-ai_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `lingo-ai_by_replication.csv` and the new `lingo-ai_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `lingo-ai_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

