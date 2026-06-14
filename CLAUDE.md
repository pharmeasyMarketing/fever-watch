# Fever Watch — Project Brief

> Standing context for Claude Code. Read this AND `docs/PROJECT_STATE.md` at the start of every session.
> `docs/PROJECT_STATE.md` carries the live status (built / verified / pending) and a ready-to-build SSG spec.
> Sibling product to Mosquito Watch (`../Monsoon Disease Project`), but architecturally the
> INVERSE: Fever Watch blends signals into one decomposable score instead of keeping them separate.

## What we are building

A consumer-facing, PharmEasy-branded tool that gives one **daily risk score per city per disease**
for India's **top monsoon fevers**: dengue (flagship), malaria, chikungunya, and typhoid. It is
share-driven and a funnel into PharmEasy test bookings. It answers one personal
question: *should I worry, and what do I do about it?*

**Critical framing (non-negotiable):** a **risk indicator**, NOT a diagnosis, NOT a count of actual
mosquitoes or cases, NOT medical advice. It is loud only when signals agree; forecast-only locations
are capped and can never show HIGH. No medical schema in JSON-LD.

## The engine: 3 signals, confirmation-weighted (NOT a flat average)

This is the deliberate inverse of Mosquito Watch (which never blends). Each signal sits at a
different point in the illness pipeline:

| Signal | Source | Role | Status |
|---|---|---|---|
| Weather / breeding | **NASA POWER** (public domain, no key) | Leading (conditions ahead) | live |
| Search interest | Google Trends (SerpApi / pytrends) | Coincident (public concern) | mock first |
| Lab positivity | PharmEasy internal labs | Lagging, the ground truth | mock first |

Clubbing logic lives in `src/consolidate.py` + `config/consolidation.json`:
- positivity present, it dominates (~30/22/48 weather/trends/positivity); agreement across all three
  applies a confidence multiplier.
- no positivity, "Forecast only" mode blends weather and trends and **caps the score at 69, one
  point below the HIGH band floor (70)**, with lower confidence. So a forecast-only read can never
  reach HIGH by construction. This honesty mechanism protects credibility.
- per-city z-score normalization vs a baseline (kills big-city bias): hook now, real baselines later.
- the score is ALWAYS decomposable in the UI; never a mystery number.

## Locked architecture decisions

- **Storage:** static JSON committed to Git (no server, no DB). Daily commits double as the durable
  history and the future Random-Forest training set.
- **Front-end:** Python SSG (one static page per city x disease, for programmatic SEO) plus vanilla
  JS for interactivity. No Node build toolchain.
- **Weather source:** NASA POWER (CC0 / U.S. public domain). ~3-day latency and no forecast, both
  fine for a trailing breeding index that already designs around a 1-2 week rain-to-emergence lag.
  Open-Meteo is kept behind the same interface as a dev/forecast option only (its free tier is
  non-commercial).
- **Hosting:** GitHub Pages (public repo) + Actions cron. Production = a subpath on the pharmeasy.in
  apex via reverse-proxy, mirroring Mosquito Watch. `base_url` lives only in `config/site.json`.

## Disease model (`config/diseases.json` + `config/scoring.json`)

Two weather-shaping families select how trailing daily weather maps to the environmental sub-score (a
third, **febrile** / viral fever, was retired 2026-06-09 - PharmEasy runs no lab-positivity test for
viral fever, so it can never get the ground-truth signal; the febrile shaping stays in weather_score.py
but is now unused):
- **mosquito** (dengue / malaria / chikungunya): unimodal temperature near 29C, times lagged rainfall
  (standing water), times humidity.
- **waterborne** (typhoid): recent plus lagged rainfall as a contamination proxy; temperature minor.

## Build order

1. Scaffold + configs + NASA POWER default + consolidation engine  (DONE, this session)
2. Weather builder (per-family shaping) to `data/weather.json`
3. Daily grid builder (weather live + trends/positivity mock) to `data/grid.json` + fail-loud guard
4. Front-end (vanilla-JS port of the prototype UX)
5. SSG: per city x disease SEO pages + JSON-LD / robots / sitemap / manifest / OG
6. Geolocation: IP / GPS / saved-address to nearest-city snap + dropdown override
7. Virality: share-card image export + WhatsApp / Instagram deep links
8. GitHub Actions daily cron + deploy
9. Methodology / disclaimer copy + compliance pass + 3-signal backtest

## Reused from Mosquito Watch (`../Monsoon Disease Project`)

- Provider-interface + registry pattern (weather now; trends + positivity next).
- `httputil.py`, the config-driven design, and the fail-loud data-quality guard.
- SSG / JSON-LD / robots / sitemap / manifest machinery, extended to many pages.
- GitHub Actions cron + commit-data-back + Pages model.
- `trends_providers/` and `panel_providers/` (positivity) port almost as-is.

## Guardrails (carry into every session)

- Risk-indicator framing only; never diagnostic or predictive of individual illness; no medical JSON-LD.
- The single score is always decomposable; forecast-only is capped and cannot show HIGH.
- Positivity is shown as an aggregate city-level TREND only; nothing re-identifiable (selection bias).
- Weather temperature is not body-temperature fever; keep them distinct in all copy.
- **No em dashes, en dashes, or middot separators** in any copy (meta, FAQ, JSON-LD strings, UI text,
  engine notes). Use an ASCII hyphen.
- `base_url` lives only in `config/site.json`; keep all in-page asset paths relative.
- Internal docs / spreadsheets (`*.xlsx`) are gitignored; never commit them to a public repo.
- Re-check copy with compliance / counsel before any public launch.

## How to run

```
python scripts/gen_cities.py     # regenerate config/cities.json (228 cities)
python src/build_weather.py      # NASA POWER -> data/weather.json (daily)
python src/build_daily.py        # compose the grid (reads config/signals.json) -> data/grid.json
python src/build_trends.py       # WEEKLY: SerpApi -> data/trends.json (needs SERPAPI_KEY)
python src/consolidate.py        # smoke-test the ensemble engine
python -m http.server 8137       # preview prototypes/mobile.html , prototypes/desktop.html
```
Going live = flip providers in `config/signals.json` (mock -> googlesheet / cached). Full status + SSG spec: `docs/PROJECT_STATE.md`.

## Data cadence (LOCKED)

- **Weather (NASA POWER):** pulled **daily** to `data/weather.json`. ~228 calls/day for 228 cities, no key (keyless / US public domain, no hard daily limit).
- **Google Trends (SerpApi, 5 API keys with failover):** TWO pulls, both inside `daily.yml`:
  (1) the LIVE cross-state snapshot (`build_trends.py` -> `data/trends.json`, GEO_MAP_0 + news-spike, ~8 searches)
  runs **daily** and feeds the dial/breakdown/leaderboard; (2) the per-state interest-over-time TIMESERIES
  re-pull (`refresh_trends_timeseries.py` -> `data/backfill/trends_history.json`, ~132 searches) runs **weekly**
  (Mondays, aligned to the 1-Jun season week boundary) so the season-trend "this year vs last year" SEARCH lines
  share one Google normalisation - i.e. the cross-year search YoY is now EXACT, not directional. ~817 searches/mo
  in-season (of 5 x 250 = 1,250 free); keys roll over on quota/error. The weekly step then runs
  `build_archive.py --search-only` to recompute the EXACT search ly+ty into the committed archive.
- **PharmEasy lab positivity (Google Sheet):** read **daily** (backend analytics updates the sheet daily).
  Implement `src/signals/googlesheet.py` (stdlib `urllib` + `csv`). Sheet ID/URL pending from user. Feed format:
  `docs/lab_feed_format.md` + `docs/lab_feed_sample.csv`.
- **Grid recompute:** **daily** (latest weather + latest lab + most-recent trends) -> `data/grid.json` ->
  SSG -> commit -> deploy. ONE workflow `daily.yml` does it all (weather + live trends + grid + the Monday-gated
  per-state TIMESERIES re-pull + archive + deploy); the SerpApi weekly work was folded into `daily.yml` (there is
  no separate `weekly.yml`) so the minified single-line `data/archive/trend_series.json` has exactly one committer.

## UX (LOCKED)

- Separate **mobile** and **desktop** flows (not responsive), PharmEasy-styled (Inter, Porcelain Green, gold accent,
  diagnostics blue for the lab signal). Working clickable prototypes in `prototypes/` (`mobile.html`, `desktop.html`,
  `tokens.css`). Co-branded nav lockup at `assets/img/fever-watch-lockup-white.svg`.
- **City-first**: one page per city at `/fever-watch/{city}` (SSG, data baked in, share-link target). **Top ~230 cities (228 live).**
- Headline = **max-dominant blend** (`0.8 x top disease + 0.2 x mean of rest`) with the driver disease named.

## Open decisions / TODO

- [x] v1 diseases: dengue, malaria, chikungunya, typhoid. (Viral fever removed 2026-06-09: no lab-positivity test exists for it, so it could never get the ground-truth signal; see PROJECT_STATE.)
- [x] UX: dual mobile/desktop flows, city-first, top ~230 (228 live), `/fever-watch/{city}` URLs (prototypes approved-in-progress).
- [x] Data cadence: weather daily, trends weekly (SerpApi x5), lab Google Sheet daily (see above).
- [x] Top ~230 city config built (`scripts/gen_cities.py` -> `config/cities.json`, 228 cities); coords need a QA pass before launch.
- [x] Signal providers built + wired via `config/signals.json`: SerpApi weekly (`build_trends.py` -> `trends.json`, read by `cached`); Google Sheet daily (`googlesheet`, tested). Flip `mock` -> real in `signals.json`.
- [x] IP-geolocation source: BigDataCloud `reverse-geocode-client` (keyless, client-side, commercial-OK; client-side-only constraint) + freeipapi.com fallback. Front-end impl pending.
- [ ] Provide the PharmEasy lab Google Sheet published-CSV URL -> set positivity.googlesheet.csv_url + provider `googlesheet`.
- [x] Add the 5 SerpApi keys as Actions secrets -> DONE (5/5 verified in CI; `trends.provider=cached`; pulled by `daily.yml`).
- [ ] Repo name + Pages + production reverse-proxy route (mirror Mosquito Watch).
- [x] Self-host Inter -> DONE (latin woff2 + `@font-face`, replacing the Google Fonts CDN). [ ] Final brand sign-off on the co-branded lockup still pending.
- [ ] Backtest the 3-signal lag on a past monsoon before any public early-warning claim.
