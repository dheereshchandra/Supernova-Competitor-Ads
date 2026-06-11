# Strategic view — zinglish (facebook)

*Generated from 31 ads, latest 2026-06-11.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-26 | 31 | 31 | 31 | 1.0 |
| 2026-06-04 | 31 | 0 | 31 | 1.0 |
| 2026-06-11 | 31 | 0 | 31 | 1.0 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| other | 15 | 15 | 1.0 |
| human_only | 10 | 10 | 1.0 |
| paper_translation | 6 | 6 | 1.0 |
| split_screen | 0 | 0 | 0.0 |
| TOTAL | 31 | 31 | 1.0 |

*split-screen ads (captured both above and in `zinglish_raw_format_counts.csv`): 0.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| app-demo | 23 | 23 | 1.0 |
| pen-and-paper | 6 | 6 | 1.0 |
| other | 1 | 1 | 1.0 |
| listicle-montage | 1 | 1 | 1.0 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| translation-practice | 13 | 13 | 1.0 |
| feature-demo | 10 | 10 | 1.0 |
| other | 8 | 8 | 1.0 |

*Price / offer hook present in 0 of 31 ads. Split-screen role split in `zinglish_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 0 | 0.0 |
| human_only | 10 | 1.0 |
| paper_translation | 6 | 1.0 |
| other | 15 | 1.0 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 30 | 5 | 31 | 31 | 1.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| visual_variant | 1 | 0 | 0 | 0 | 0 |
| ALL | 1 | 0 | 0 | 0 | 0 |

*Fastest replicated group: `zinglish-g0000` — replica `908822938160022` (visual_variant) appeared 0 day(s) after the original `900964249487648`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| zinglish-g0000 | 2 | 2 | 2 | 1.0 | original;visual_variant |
| zinglish-g0001 | 1 | 1 | 1 | 1.0 | unique |
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

