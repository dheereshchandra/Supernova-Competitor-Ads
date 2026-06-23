# Strategic view — duolingo (facebook)

*Generated from 65 ads, latest 2026-06-23.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 29 | 29 | 29 | 1.0 |
| 2026-06-04 | 63 | 34 | 30 | 0.476 |
| 2026-06-07 | 30 | 0 | 30 | 1.0 |
| 2026-06-11 | 30 | 0 | 30 | 1.0 |
| 2026-06-12 | 30 | 0 | 30 | 1.0 |
| 2026-06-13 | 30 | 0 | 30 | 1.0 |
| 2026-06-14 | 30 | 0 | 30 | 1.0 |
| 2026-06-15 | 30 | 0 | 30 | 1.0 |
| 2026-06-16 | 30 | 0 | 30 | 1.0 |
| 2026-06-17 | 30 | 0 | 30 | 1.0 |
| 2026-06-22 | 30 | 2 | 28 | 0.933 |
| 2026-06-23 | 30 | 0 | 28 | 0.933 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| other | 61 | 26 | 0.426 |
| human_only | 4 | 4 | 1.0 |
| split_screen | 1 | 1 | 1.0 |
| TOTAL | 65 | 30 | 0.462 |

*split-screen ads (captured both above and in `duolingo_raw_format_counts.csv`): 1.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| app-demo | 22 | 15 | 0.682 |
| other | 7 | 4 | 0.571 |
| listicle-montage | 6 | 0 | 0.0 |
| skit-narrative | 4 | 2 | 0.5 |
| text-on-screen-only | 2 | 0 | 0.0 |
| split-screen | 1 | 1 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| habit-aspiration | 1 | 0 | 0.0 |
| other | 1 | 0 | 0.0 |

*Price / offer hook present in 2 of 65 ads. Split-screen role split in `duolingo_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 0 | 0.0 |
| human_only | 4 | 1.0 |
| paper_translation | 0 | 0.0 |
| other | 61 | 0.426 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 19 | 4 | 29 | 29 | 1.0 |
| 2026-06-01 | 0 | 2 | 34 | 1 | 0.029 |
| 2026-06-22 | 2 | 0 | 2 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| reworded_replica | 4 | 4.5 | 4.5 | 0 | 9 |
| visual_variant | 17 | 9 | 9 | 9 | 9 |
| ALL | 21 | 9 | 8.1 | 0 | 9 |

*Fastest replicated group: `duolingo-g0001` — replica `2207673653307134` (reworded_replica) appeared 0 day(s) after the original `1270856521521372`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| duolingo-g0000 | 20 | 20 | 2 | 0.1 | original;reworded_replica;visual_variant |
| duolingo-g0001 | 2 | 2 | 2 | 1.0 | original;reworded_replica |
| duolingo-g0002 | 2 | 2 | 2 | 1.0 | original;reworded_replica |
| duolingo-g0003 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0004 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0005 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0006 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0007 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0008 | 1 | 1 | 1 | 1.0 | unique |
| duolingo-g0009 | 1 | 1 | 1 | 1.0 | unique |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `duolingo_by_language.csv` and `duolingo_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `duolingo_by_replication.csv` and the new `duolingo_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `duolingo_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

