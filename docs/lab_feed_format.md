# Fever Watch - PharmEasy lab feed format (signal 3)

The PharmEasy lab signal (positivity) is the only proprietary input and the "ground
truth" layer. Publish it as a Google Sheet, "Published to web" as CSV, and Fever Watch
reads that CSV on every build. Until the sheet is live, a deterministic MOCK provider is
the default, so nothing breaks.

## One row per city x disease x period

| column | type | required | notes |
|---|---|---|---|
| `week_start` | date `YYYY-MM-DD` | yes | start of the rolling window this row covers |
| `city` | string | yes | must match a city `id` in `config/cities.json` (e.g. `bengaluru`, `mumbai`) |
| `disease` | string | yes | one of: `dengue`, `malaria`, `chikungunya`, `typhoid` |
| `tests_booked` | integer | yes | aggregate count of relevant tests in that city / disease / window |
| `positives` | integer | yes* | aggregate count of positive results. `positivity_pct = positives / tests_booked x 100` |
| `positivity_pct` | float 0-100 | optional | send this *instead of* `positives` if you cannot share raw positive counts |

\* Provide either `positives` (preferred) or `positivity_pct`.

### Privacy and data-quality rules (built into the reader)
- **Aggregate, city-level, de-identified only.** No PII, no sub-city geography, no individual records.
- If `tests_booked` is below a confidence threshold (default **30**) or a city/disease row is
  absent, Fever Watch treats positivity as **"no data"** for that cell. It then falls back to the
  capped `forecast-only` mode, so a weak-data cell can never show HIGH.
- Positivity is shown as a **trend**, never as a re-identifiable rate (selection-bias guardrail).

## Cadence
**Daily is fully supported.** Publish a fresh rolling 7-day window each morning, or weekly if
that is easier. The Fever Watch cron picks up whatever the published CSV currently says.

## Wiring it in (one switch, when the sheet is ready)
1. In the Google Sheet: `File > Share > Publish to web > select the tab > CSV`. Copy the published CSV URL.
2. Put that URL in config (a `positivity` / `panel` block read by the build).
3. Flip the positivity provider from `mock` to `googlesheet` (a `src/signals/googlesheet.py` that reads
   the CSV with stdlib `urllib` + `csv`, no new dependency). The `mock` stays default until then.

See `docs/lab_feed_sample.csv` for a ready-to-copy example.
