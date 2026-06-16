# Fever Watch

A daily, PharmEasy-branded **risk indicator** for India's top monsoon fevers (dengue, malaria,
chikungunya, typhoid), by city. One decomposable score per city per disease, blended
from three signals: breeding weather (leading), search interest (coincident), and lab positivity
(lagging ground truth).

**It is a risk indicator, not a diagnosis or a case count.** Forecast-only locations are capped and
can never show HIGH.

## Architecture

Serverless by design: scheduled scripts write static JSON, a static site reads it. Rainfall comes from
NOAA CPC (gauge-based, U.S. public domain) and temperature/humidity from NASA POWER (U.S. public domain),
both keyless and commercial-OK; NASA stays switchable (`--provider nasa-power`). See `CLAUDE.md`
for the full brief and `docs/` for handoff notes.

## Run

```
python src/consolidate.py     # smoke-test the consolidation engine
```

## Status

Scaffolding (step 1 of 9). See `CLAUDE.md` > Build order.
