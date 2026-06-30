# Strategic view — zinglish (facebook)

*Generated from 41 ads, latest 2026-06-30.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 31 | 31 | 31 | 1.0 |
| 2026-06-04 | 31 | 0 | 31 | 1.0 |
| 2026-06-11 | 31 | 0 | 31 | 1.0 |
| 2026-06-12 | 31 | 0 | 31 | 1.0 |
| 2026-06-13 | 30 | 0 | 30 | 1.0 |
| 2026-06-14 | 30 | 0 | 30 | 1.0 |
| 2026-06-15 | 30 | 0 | 30 | 1.0 |
| 2026-06-16 | 30 | 0 | 30 | 1.0 |
| 2026-06-17 | 30 | 0 | 30 | 1.0 |
| 2026-06-22 | 30 | 0 | 30 | 1.0 |
| 2026-06-23 | 30 | 0 | 30 | 1.0 |
| 2026-06-24 | 30 | 0 | 30 | 1.0 |
| 2026-06-25 | 30 | 0 | 30 | 1.0 |
| 2026-06-26 | 30 | 0 | 30 | 1.0 |
| 2026-06-28 | 37 | 7 | 30 | 0.811 |
| 2026-06-29 | 37 | 0 | 30 | 0.811 |
| 2026-06-30 | 40 | 3 | 31 | 0.775 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 20 | 10 | 0.5 |
| other | 15 | 15 | 1.0 |
| paper_translation | 6 | 6 | 1.0 |
| split_screen | 0 | 0 | 0.0 |
| TOTAL | 41 | 31 | 0.756 |

*split-screen ads (captured both above and in `zinglish_raw_format_counts.csv`): 0.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| app-demo | 32 | 23 | 0.719 |
| pen-and-paper | 6 | 6 | 1.0 |
| other | 1 | 1 | 1.0 |
| listicle-montage | 1 | 1 | 1.0 |
| skit-narrative | 1 | 0 | 0.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| translation-practice | 17 | 13 | 0.765 |
| feature-demo | 16 | 10 | 0.625 |
| other | 8 | 8 | 1.0 |

*Price / offer hook present in 0 of 41 ads. Split-screen role split in `zinglish_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 0 | 0.0 |
| human_only | 20 | 0.5 |
| paper_translation | 6 | 1.0 |
| other | 15 | 1.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 30 | 5 | 31 | 31 | 1.0 |
| 2026-06-22 | 7 | 1 | 7 | 0 | 0.0 |
| 2026-06-29 | 2 | 0 | 3 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 1 | 2 | 2 | 2 | 2 |
| visual_variant | 1 | 0 | 0 | 0 | 0 |
| ALL | 2 | 1.0 | 1 | 0 | 2 |

*Fastest replicated group: `zinglish-g0000` — replica `908822938160022` (visual_variant) appeared 0 day(s) after the original `900964249487648`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| zinglish-g0000 | 2 | 2 | 2 | 1.0 | original;visual_variant |
| zinglish-g0001 | 2 | 2 | 0 | 0.0 | exact_replica;original |
| zinglish-g0002 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0003 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0004 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0005 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0006 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0007 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0008 | 1 | 1 | 1 | 1.0 | unique |
| zinglish-g0009 | 1 | 1 | 1 | 1.0 | unique |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `zinglish_by_language.csv` and `zinglish_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `zinglish_by_replication.csv` and the new `zinglish_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `zinglish_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

