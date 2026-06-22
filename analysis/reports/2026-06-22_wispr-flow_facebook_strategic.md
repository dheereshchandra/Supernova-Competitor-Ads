# Strategic view — wispr-flow (facebook)

*Generated from 483 ads, latest 2026-06-22.*

> **How to read this:** rank is the ad library's *impression ordering*, a position proxy — not a measured performance metric (there is no CTR/CVR/ROAS). A "winner" means the advertiser **sustained** the ad (longevity, the primary signal) and the platform **kept surfacing** it (rank, confirmatory) — strong revealed preference, not proof of conversion. Longevity carries the verdict; rank only corroborates.

## Q1 Volume over time

Per scrape-date live volume (history.csv — one row per ad per scrape).

| scrape_date | ads live | new | winners live | win ratio |
|---|--:|--:|--:|--:|
| 2026-05-28 | 476 | 476 | 24 | 0.05 |
| 2026-06-16 | 7 | 7 | 0 | 0.0 |
| 2026-06-17 | 7 | 0 | 0 | 0.0 |
| 2026-06-22 | 7 | 0 | 0 | 0.0 |

## Q2 Format / bucket mix

| bucket | ads | winners | win ratio |
|---|--:|--:|--:|
| human_only | 363 | 4 | 0.011 |
| other | 120 | 20 | 0.167 |
| split_screen | 59 | 1 | 0.017 |
| TOTAL | 483 | 24 | 0.05 |

*split-screen ads (captured both above and in `wispr-flow_raw_format_counts.csv`): 59.*

## Format mix (Axis 1 — merged)

| format | ads | winners | win ratio |
|---|--:|--:|--:|
| app-demo | 276 | 4 | 0.014 |
| split-screen | 59 | 1 | 0.017 |
| skit-narrative | 35 | 0 | 0.0 |
| listicle-montage | 4 | 1 | 0.25 |

## Message angle (Axis 3)

| message_angle | ads | winners | win ratio |
|---|--:|--:|--:|
| feature-demo | 344 | 5 | 0.015 |
| other | 21 | 1 | 0.048 |
| habit-aspiration | 7 | 0 | 0.0 |
| social-proof | 2 | 0 | 0.0 |

*Price / offer hook present in 278 of 483 ads. Split-screen role split in `wispr-flow_by_split_role.csv`.*

## Q5 AI vs human production

| production class | ads | win ratio |
|---|--:|--:|
| AI-heavy (ai_plus_ai + ai_plus_human) | 0 | 0.0 |
| human_only | 363 | 0.011 |
| paper_translation | 0 | 0.0 |
| other | 120 | 0.167 |

## Q9 New scripts / formats per week

| week | new scripts | new formats | new ads | winners | win ratio |
|---|--:|--:|--:|--:|--:|
| 2026-05-25 | 191 | 5 | 476 | 24 | 0.05 |
| 2026-06-15 | 3 | 0 | 7 | 0 | 0.0 |

## Q10 Replication speed

Days from a script group's original to each replica (median per type).

| replication_type | n replicas | median days | mean days | min | max |
|---|--:|--:|--:|--:|--:|
| exact_replica | 156 | 0.0 | 0.5 | 0 | 19 |
| reworded_replica | 18 | 0.0 | 0 | 0 | 0 |
| visual_variant | 6 | 0.0 | 0 | 0 | 0 |
| ALL | 180 | 0.0 | 0.4 | 0 | 19 |

*Fastest replicated group: `wispr-flow-g0000` — replica `2467773930362439` (reworded_replica) appeared 0 day(s) after the original `1083502908185516`.*

## Q11 Per-script performance (top 10 groups by size)

| script_group_id | group size | ads | winners | win ratio | replication_types |
|---|--:|--:|--:|--:|---|
| wispr-flow-g0000 | 7 | 7 | 0 | 0.0 | exact_replica;original;reworded_replica |
| wispr-flow-g0001 | 7 | 7 | 0 | 0.0 | original;reworded_replica;visual_variant |
| wispr-flow-g0002 | 5 | 5 | 0 | 0.0 | exact_replica;original |
| wispr-flow-g0003 | 4 | 3 | 0 | 0.0 | exact_replica;original |
| wispr-flow-g0004 | 4 | 4 | 0 | 0.0 | exact_replica;original;reworded_replica |
| wispr-flow-g0005 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| wispr-flow-g0006 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| wispr-flow-g0007 | 4 | 4 | 0 | 0.0 | exact_replica;original;visual_variant |
| wispr-flow-g0008 | 4 | 4 | 0 | 0.0 | exact_replica;original |
| wispr-flow-g0009 | 4 | 4 | 1 | 0.25 | exact_replica;original |

## Q3 / Q4 / Q6 / Q7 / Q8 — where to look

- **Q3 / Q4 (language mix & cadence):** see `wispr-flow_by_language.csv` and `wispr-flow_weekly.csv`.
- **Q6 (exact_replica), Q7 (translation_replica), Q8 (visual_variant) counts:** see `wispr-flow_by_replication.csv` and the new `wispr-flow_by_script_group.csv` (per-group `replication_types` set).

**Q8 residual limitation:** `visual_variant` is detected purely from a `device_format` change between a replica and its group original. The transcript-tagged format enum is coarse (app-screencast, skit-narrative, listicle-montage, split-screen, text-on-screen-only, other), so a script re-shot with genuinely different visuals but tagged into the SAME format bucket is UNDERCOUNTED (labeled exact_replica or character_variant). Q8 is therefore a LOWER BOUND keyed on format-category change, not a pixel-level visual diff — no frame/image comparison is performed (offline, no API). Use `wispr-flow_by_script_group.csv` to eyeball groups whose members share a format but differ visually.

