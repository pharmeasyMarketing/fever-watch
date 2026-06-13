# Fever Watch - historical weather archive format

The weather backfill produces a compact, committed, date-indexed store of recomputed
weather sub-scores for PAST dates. It exists so the downstream archive runner can build
historical Fever Watch grids (durable history + a future Random-Forest training set)
without re-fetching NASA POWER on every run. The live daily pipeline
(`python src/build_weather.py` with no flags) is unchanged and still writes
`data/weather.json`.

## Where it lives

`data/backfill/weather_{year}.json`, one file per calendar year (e.g.
`data/backfill/weather_2025.json`, `data/backfill/weather_2026.json`). These files are
committable to Git: `.gitignore` only excludes `data/cache/`, not `data/backfill/`. Files
are written MINIFIED (no whitespace, compact `,`/`:` separators) to keep the committed
size down.

## How it is produced

```
# A date range (inclusive):
python src/build_weather.py --start 2025-06-01 --end 2025-10-30

# A single date:
python src/build_weather.py --as-of 2025-09-15
```

`--start`/`--end` (a range) and `--as-of` (one date) are mutually exclusive. Each also has
an environment-variable fallback so the archive runner can drive the script without flags:
`WEATHER_START`, `WEATHER_END`, `WEATHER_AS_OF`. The output directory defaults to
`data/backfill/` and can be overridden with `--out-archive`. Backfill requires the
`nasa-power` provider (the only source with real history); pointing it at any other
provider aborts loudly.

Re-running an overlapping range MERGES new dates and cities into the existing per-year
file; it never clobbers prior dates. A re-fetched (date, city) cell is overwritten in
place, so the store is idempotent under re-runs.

## NASA POWER request

- Endpoint: `https://power.larc.nasa.gov/api/temporal/daily/point`
- Parameters: `T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR`
- `community=AG`, `format=JSON`
- One request per city covers the whole inclusive `start..end` daily series.
- Fill value `-999` (and any missing value) is converted to `None`.

For each backfill run, the per-city fetch spans `earliest_target - 20 days` to
`latest_target`. The 20-day lead-in is a 14-day trailing window plus NASA POWER's ~6-day
latency, so the earliest target date's 14-day window is fully covered even with interior
gaps in the source series. The lead-in is free: it is the same single per-city call.

NASA POWER has a ~2-7 day latency, so the most recent target dates in a run may have no
usable observation yet. Those (date, city) cells are skipped (omitted from the file) and
are NON-fatal: they do not count toward the fail-loud abort fraction. Only a city whose
whole-range fetch fails counts toward that fraction.

## Trailing-window recompute rule

Each (date, city) record is recomputed from EXPLICIT calendar-date-bounded trailing
windows anchored on the target date D, not "the last N available days":

- `rain_7d_mm`  = sum of daily precipitation over the dates in `[D-6 .. D]` (skipping missing days).
- `rain_14d_mm` = sum of daily precipitation over the dates in `[D-13 .. D]` (skipping missing days).
- `temp_mean_c` = mean daily mean temperature over `[D-13 .. D]`.
- `humidity_pct` = mean daily relative humidity over `[D-13 .. D]`.

Anchoring on the calendar date (not the last N rows present) is what makes per-date
recompute correct across interior gaps: a missing day shrinks the window rather than
silently reaching further back in time. These windowed inputs are then fed to the SAME
`score_family` math the live daily pipeline uses, so family sub-scores stay consistent
with production. Only the two live families are emitted: `mosquito` (dengue / malaria /
chikungunya) and `waterborne` (typhoid). The retired `febrile` family is not produced.

## Output schema

```jsonc
{
  "year": 2025,
  "provider": "nasa-power",
  "attribution": "Weather data by NASA POWER (MERRA-2 / GMAO), public domain",
  "generated_at": "2026-06-13T12:00:00+00:00",   // ISO 8601, UTC
  "by_date": {
    "2025-08-16": {                               // target date D, YYYY-MM-DD
      "mumbai": {                                 // city id from config/cities.json
        "agg": {
          "temp_mean_c": 26.2,                    // float, 14-day mean
          "humidity_pct": 89.5,                   // float, 14-day mean
          "rain_7d_mm": 199.6,                    // float, 7-day trailing sum
          "rain_14d_mm": 230.8                    // float, 14-day trailing sum
        },
        "families": {
          "mosquito": 98,                          // int 0-100 weather sub-score
          "waterborne": 100                        // int 0-100 weather sub-score
        }
      }
      // ... one entry per city present for this date
    }
    // ... one entry per target date in this year
  }
}
```

Only what the downstream runner needs per (date, city) is stored: the four `agg` fields
and the two family weather sub-scores. The live `data/weather.json` bookkeeping
(`temp_swing`, `has_temp`, `n_days`, per-disease components) is intentionally dropped here
to keep the committed store small.

## Caveat: historical grids built from this are forecast-only-capped

Any historical Fever Watch grid the downstream runner builds from this archive is
WEATHER plus TRENDS driven only. There is no lab-positivity ground truth for past dates
(the PharmEasy lab feed is mock / not back-dated). That means every historical cell runs
in the consolidation engine's "forecast only" mode and is CAPPED at 69 - one point below
the HIGH band floor (70). A backtested historical grid can therefore never show HIGH by
construction, and any positivity-derived value in it is mock, not lab-confirmed. Keep this
distinction in any backtest or early-warning claim.
