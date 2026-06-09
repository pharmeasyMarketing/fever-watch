# Fever Watch - PharmEasy lab feed: HISTORIC (last-season) format

A one-time, fixed extract of LAST season's lab positivity. It powers the "last year"
reference line in the "This monsoon vs last year in {city}" trend module. Schema is the
same as the live daily feed (see `docs/lab_feed_format.md`) plus one optional extra column
(`season_week`). Ready-to-copy sample: `docs/lab_feed_2025_historic_template.csv`.

## One row per city x disease x WEEK, for the full season (1 June - 30 October)

| column | type | required | notes |
|---|---|---|---|
| `week_start` | date `YYYY-MM-DD` | yes | start of the 7-day bucket, last season (e.g. `2025-06-01`) |
| `season_week` | integer 1-22 | optional | week index within the season; derived from `week_start` if omitted |
| `city` | string | yes | the city **id** from `config/cities.json` (lowercase, e.g. `bengaluru`) - not the display name |
| `disease` | string | yes | one of: `dengue`, `malaria`, `chikungunya`, `typhoid`, `viral_fever` |
| `tests_booked` | integer | yes | aggregate count of relevant tests in that city / disease / week |
| `positives` | integer | yes | aggregate positives. `positivity_pct = positives / tests_booked x 100` |

(Counts confirmed with the team: raw `positives` + `tests_booked`, so the 30-test confidence
gate works and sparse weeks fall back to "no data" rather than a shaky number.)

## The 22 weekly buckets (7-day, anchored to 1 June)

```
wk1  2025-06-01   wk7  2025-07-13   wk13 2025-08-24   wk19 2025-10-05
wk2  2025-06-08   wk8  2025-07-20   wk14 2025-08-31   wk20 2025-10-12
wk3  2025-06-15   wk9  2025-07-27   wk15 2025-09-07   wk21 2025-10-19
wk4  2025-06-22   wk10 2025-08-03   wk16 2025-09-14   wk22 2025-10-26
wk5  2025-06-29   wk11 2025-08-10   wk17 2025-09-21
wk6  2025-07-06   wk12 2025-08-17   wk18 2025-09-28
```

## Rules
- **Weekly** granularity (one row per city x disease x week) - matches the trend chart.
- Provide **all 22 weeks** for every city x disease that has data. Omit any city/disease with
  no 2025 data (the chart shows a "Labs: coming soon" state for it rather than faking a line).
- Aggregate, city-level, **de-identified only**. No PII, no sub-city geography, no records.
- Include `tests_booked` even when small - that low count is what flags a week as "not enough
  data" (below 30 -> treated as no data, same as the live feed).
- Bucket **both** last season (this file) and this season (the live feed) the **same way**, so
  week i of last year overlays week i of this year in the chart.

## How it is used
The historic series is the soft gray "last year" band in the "This monsoon vs last year" trend
module; the live feed (`docs/lab_feed_format.md`) accumulates this year's bold line. Until the
real extract arrives, the module runs on **mock** last-year data.
