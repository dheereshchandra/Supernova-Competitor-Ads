# Strategic view — loora (facebook)

*Generated from 138 ads, latest 2026-06-26.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-27 | 51 | 51 | 39 | 0.765 |
| 2026-06-04 | 34 | 9 | 31 | 0.912 |
| 2026-06-11 | 39 | 11 | 35 | 0.897 |
| 2026-06-12 | 38 | 0 | 34 | 0.895 |
| 2026-06-13 | 38 | 0 | 34 | 0.895 |
| 2026-06-14 | 36 | 1 | 33 | 0.917 |
| 2026-06-15 | 45 | 12 | 30 | 0.667 |
| 2026-06-16 | 53 | 10 | 29 | 0.547 |
| 2026-06-17 | 52 | 15 | 29 | 0.558 |
| 2026-06-22 | 53 | 15 | 27 | 0.509 |
| 2026-06-23 | 53 | 0 | 27 | 0.509 |
| 2026-06-24 | 46 | 6 | 19 | 0.413 |
| 2026-06-25 | 47 | 8 | 18 | 0.383 |
| 2026-06-26 | 47 | 0 | 18 | 0.383 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| ai_plus_human | 73 | 35 | 0.479 |
| ai_plus_ai | 62 | 24 | 0.387 |
| other | 3 | 0 | 0.0 |
| split_screen | 75 | 35 | 0.467 |
| TOTAL | 138 | 59 | 0.428 |

*split-screen ads (captured both above and in `loora_raw_format_counts.csv`): 75.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| split-screen | 75 | 35 | 0.467 |
| app-demo | 60 | 24 | 0.4 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| speak-correctly | 100 | 46 | 0.46 |
| understand-cant-speak | 27 | 8 | 0.296 |
| habit-aspiration | 7 | 4 | 0.571 |
| fear-shame | 1 | 1 | 1.0 |

*Price / offer hook present in 1 of 138 ads. Split-screen role split in `loora_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 135 | 0.437 |
| human_only | 0 | 0.0 |
| paper_translation | 0 | 0.0 |
| other | 3 | 0.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 25 | 2 | 51 | 39 | 0.765 |
| 2026-06-01 | 3 | 0 | 9 | 6 | 0.667 |
| 2026-06-08 | 1 | 0 | 12 | 9 | 0.75 |
| 2026-06-15 | 5 | 0 | 37 | 0 | 0.0 |
| 2026-06-22 | 3 | 1 | 29 | 5 | 0.172 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 65 | 15 | 12.6 | 0 | 29 |
| reworded_replica | 14 | 21.0 | 18.5 | 0 | 28 |
| translation_replica | 18 | 20.0 | 15.3 | 0 | 29 |
| visual_variant | 1 | 29 | 29 | 29 | 29 |
| ALL | 98 | 19.0 | 14.1 | 0 | 29 |

*Fastest replicated group: `loora-g0000` — replica `1399715815299179` (exact_replica) appeared 0 day(s) after the original `1286341193458429`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| loora-g0000 | 20 | 20 | 6 | 0.3 | exact_replica;original;reworded_replica |
| loora-g0001 | 19 | 19 | 7 | 0.368 | exact_replica;original;translation_replica |
| loora-g0002 | 14 | 14 | 3 | 0.214 | exact_replica;original;reworded_replica |
| loora-g0003 | 13 | 13 | 6 | 0.462 | exact_replica;original;visual_variant |
| loora-g0004 | 6 | 6 | 4 | 0.667 | exact_replica;original;reworded_replica |
| loora-g0005 | 6 | 6 | 2 | 0.333 | exact_replica;original |
| loora-g0006 | 5 | 5 | 4 | 0.8 | exact_replica;original;reworded_replica |
| loora-g0007 | 5 | 5 | 4 | 0.8 | exact_replica;original |
| loora-g0008 | 4 | 4 | 3 | 0.75 | exact_replica;original;reworded_replica |
| loora-g0009 | 3 | 3 | 3 | 1.0 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `loora_by_language.csv` and `loora_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `loora_by_replication.csv` and the new `loora_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `loora_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

