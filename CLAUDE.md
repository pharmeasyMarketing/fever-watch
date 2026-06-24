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
| Weather / breeding | **NOAA CPC** rain + **NASA POWER** temp/humidity (public domain, no key) | Leading (conditions ahead) | live |
| Search interest | Google Trends (SerpApi / pytrends) | Coincident (public concern) | live (SerpApi -> cached) |
| Lab positivity | PharmEasy / ThyroCare labs | Lagging, the ground truth | **LIVE** (gsheet_api + service account, 2026-06-17) |

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
- **Weather source (hybrid, default `cpc`):** RAINFALL from **NOAA CPC** (Global Unified Gauge-Based
  Analysis; gauge-based, US public domain) - it tracks Indian gauge truth far better than NASA's
  reanalysis rain, which over-reads the pre-monsoon South (228-city benchmark vs IMD; see
  `Rain_Data_Provider_Analysis_and_Decision.docx`). TEMPERATURE and HUMIDITY stay on **NASA POWER**
  (CC0 / U.S. public domain). Both keyless, ~1-3 day latency, no forecast - fine for a trailing breeding
  index designed around a 1-2 week rain-to-emergence lag. Revert to all-NASA with `--provider nasa-power`
  (or `WEATHER_PROVIDER=nasa-power`). Open-Meteo stays behind the same interface as a dev/forecast option
  (its free tier is non-commercial). IMD gauge data is NOT used in production (non-commercial licence);
  it was the offline validation truth only.
- **Hosting:** GitHub Pages (public repo) + Actions cron. Production = a subpath on the pharmeasy.in
  apex via reverse-proxy, mirroring Mosquito Watch. `base_url` lives only in `config/site.json`.
- **Analytics:** Google Tag Manager container `GTM-W5PR55Z` is injected site-wide from the shared `PAGE`
  template in `src/build_site.py` (loader `<script>` high in `<head>` + the `<noscript>` iframe right after
  `<body>`), so every city + landing page carries it. Add tags/pixels in GTM, not in the page source.

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
- **All user-facing dates are IST.** `grid.generated_at` is minted in UTC; the display formatters shift **+5:30**
  before extracting the date (`fmtDate()` in mobile.js/desktop.js/faq.js, `_fmt_date_js()`/`iso_date()` in build_site.py,
  `fmt_date()` in build_share_cards.py, the trend `asOf`). So a 23:59-UTC build shows the India date. Keep the JS
  `fmtDate()` and the SSR `_fmt_date_js()` byte-identical, and never display a raw UTC timestamp to users.
- Internal docs / spreadsheets (`*.xlsx`) are gitignored; never commit them to a public repo.
- Re-check copy with compliance / counsel before any public launch.

## How to run

```
python scripts/gen_cities.py     # regenerate config/cities.json (228 cities)
python src/build_weather.py      # NOAA CPC rain + NASA temp/humidity -> data/weather.json (daily)
python src/build_daily.py        # compose the grid (reads config/signals.json) -> data/grid.json
python src/build_trends.py       # WEEKLY: SerpApi -> data/trends.json (needs SERPAPI_KEY)
python src/consolidate.py        # smoke-test the ensemble engine
python -m http.server 8137       # preview prototypes/mobile.html , prototypes/desktop.html
```
Lab positivity is now LIVE: the `gsheet_api` provider reads the private "Year 2026 DoD data(TC Data)" sheet tab via the Google Sheets API + a service account (`daily.yml` sets `POSITIVITY_PROVIDER=gsheet_api`; secret `GOOGLE_SHEETS_SA_JSON`; local key `secrets/gsheets_sa.json`). The committed `config/signals.json` default stays `mock` so local builds without the key still work. Full status + SSG spec + open refinements: `docs/PROJECT_STATE.md` (2026-06-17 banner).

## Data cadence (LOCKED)

- **Weather (NOAA CPC rain + NASA POWER temp/humidity):** pulled **daily** to `data/weather.json`. ~228 NASA calls/day for temp/humidity + one NOAA CPC NetCDF/year (cached in `data/cpc_cache/`, gitignored) for rain; no key (both US public domain, no hard daily limit).
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
- **City-first**: one page per city at `/fever-watch/{city}` (SSG, data baked in, share-link target). **209 lab-covered cities (228 -> 209 scope locked 2026-06-17; the 19 with no lab data dropped via `gen_cities.py` DROP_NO_LAB_DATA).**
- Headline = **max-dominant blend** (`0.8 x top disease + 0.2 x mean of rest`) with the driver disease named.
- **Season-trend ("This monsoon vs last year") is ALWAYS REAL - there is NO mock anywhere in the project**
  (removed 2026-06-18; all three signals are live). Every page (incl. the **landing**, which inlines the default
  city's `seed`+`archive` slice + `archiveUrl`, same as a city page) renders the real last-year+this-year lines
  from `data/archive/trend_series.json`. Fallbacks, in order, are honest - never fabricated: real -> a
  HEIGHT-MATCHED skeleton while a not-yet-loaded city's archive is fetching (CLS 0) -> per-metric "coming soon"
  for a metric with no data (e.g. Labs for the 185/209 cities with no 2025 history) -> a whole-card "coming
  soon" only if a city has no real `overall` line (unreachable: `build_site.py` ASSERTS every city has one and
  aborts the build otherwise, so a stale archive can never ship a blank/mock trend). The real-vs-available gate
  is lenient on the this-year length (a short `ty` charts as a real partial). Keep `trend.js` `build()`/`forCity()`/
  `realSeries()` byte-identical to `build_site.py` `_trend_series()`/`_t_real_series()` (verified by a JS<->Python
  parity check; the SSR<->JS above-fold twin by `scripts/parity_check.js`).
- **"Why this score?" breakdown is CONTRIBUTION-based** (not raw sub-score bars): each signal's bar + `+N` = its
  largest-remainder share of the displayed integer score, so the three contributions SUM EXACTLY to the score (the
  agree/disagree multiplier + forecast cap are absorbed); coloured per signal, with a per-signal "what this measures"
  line and a reconciliation footer. (2026-06-17 readout redesign: each signal now leads with a **High/Moderate/Low
  level pill** + a `{weight}% weight x {v}/100` derivation (2026-06-24: "raw" dropped for "/100", and each derivation
  line gained a per-signal **ⓘ popover** `TIPINFO[k]` explaining the 0-100 number); labels Weather / Search / Lab;
  positivity scaled by a **per-disease reference 25/4/15/45**, not the global 35.) Helper `contribs()`/`_contribs()`
  byte-identical across mobile.js/desktop.js/build_site.py. Desktop renders compact vertical tiles in the 3-col
  `#s-why` grid, **equal-height with the dial** (`#s-week`) - the dial is sized DOWN so it is the shorter card (no
  empty void); `.acc.open` is `overflow:visible` so the per-signal popover is not clipped. The **weather card
  (`Weather conditions this week`) shows the real weather-score drivers - 3 tiles** Temperature near 29C / 14-day
  Rainfall / Humidity (desktop 3-up, mobile 2 + Humidity full-width); the old "estimated stagnation" tile was removed
  2026-06-24 (producer kept in `build_daily.py`).
- **2026-06-24 medical-review UX overhaul (committed + pushed to master; full detail in PROJECT_STATE):**
  "breeding" -> "Weather conditions" everywhere user-facing (mosquito kept where it is the mechanism; the Rainfall tile
  names typhoid too); stagnation tile removed (producer kept); precautions section -> `What you can do`; the dial
  gained a plain-language **meaning line** (2026-06-24 PM copy: `Right now {city}'s overall read is {score}/100, {band
  phrase + driver}. A daily snapshot of conditions, not who's actually sick.` - `BAND_MEAN` is now a per-band PHRASE
  with a `{d}` driver token, e.g. `moderate, {d} leading` / `low, {d} highest`) + an **ⓘ tooltip** on the band
  chip (tap-toggle, JS-positioned caret, bands legend + the 80/20 headline derivation; **auto-peek ~1.7s as a hint**;
  an EXPLICIT tap then keeps it open until the user taps it again, taps outside, or **scrolls** - no timed auto-close
  as of 2026-06-24; **only one tooltip open at a time**); `Overall fever risk` -> `Overall fever risk score`; period tabs
  reduced to **Today only** (week/month were dead placeholders); legend vs-yesterday delta triangles hidden;
  per-disease legend scores show `/100`. **Auto-peek triggers (2026-06-24 PM):** mobile peeks the dial shortly after
  load (first fold) PLUS the top disease's first "Why this score?" tooltip (`.acc.open .dialinfo`) on scroll-into-view;
  desktop peeks the dial on scroll-into-view (it is in the 2nd fold). The scroll-into-view check is a `window`-scroll
  `getBoundingClientRect` test (`maybeScrollPeek`/`onTipScroll`), NOT IntersectionObserver - IO would observe a node
  the seed->data re-render detaches (and is throttled in hidden tabs); the selector is re-queried live each render.
  A peek is immune to the scroll-close (tracked by `_peekEl`) and self-closes ~1.7s. Shared primitives
  `.dialinfo`/`.dialinfo-btn[data-act=dialInfo]`/`.dialtip`/`.tipcaret` + `BAND_MEAN`/`TIPINFO` maps + the
  `dialInfo` onClick branch + `positionCaret` + `firePeek` + `maybeScrollPeek` + `onTipScroll` are byte-identical
  across the JS twins (`peekDialInfo` differs by flow); `.dialtip` anchors to its positioned parent (`.bandchip` for the dial, `.sig` for the
  breakdown), opens above, `white-space:normal`.

## Open decisions / TODO

- [x] v1 diseases: dengue, malaria, chikungunya, typhoid. (Viral fever removed 2026-06-09: no lab-positivity test exists for it, so it could never get the ground-truth signal; see PROJECT_STATE.)
- [x] UX: dual mobile/desktop flows, city-first, 209 lab-covered cities (locked 2026-06-17), `/fever-watch/{city}` URLs (prototypes approved-in-progress).
- [x] Data cadence: weather daily, trends weekly (SerpApi x5), lab Google Sheet daily (see above).
- [x] Top ~230 city config built (`scripts/gen_cities.py` -> `config/cities.json`, 228 cities); coords need a QA pass before launch.
- [x] Signal providers built + wired via `config/signals.json`: SerpApi weekly (`build_trends.py` -> `trends.json`, read by `cached`); Google Sheet daily (`googlesheet`, tested). Flip `mock` -> real in `signals.json`.
- [x] IP-geolocation source: BigDataCloud `reverse-geocode-client` (keyless, client-side, commercial-OK; client-side-only constraint) + freeipapi.com fallback. Front-end impl pending.
- [x] **Lab positivity LIVE (2026-06-17):** reads the private "Year 2026 DoD data(TC Data)" tab via the Google Sheets API + a service account (`src/signals/gsheet_api.py`, provider `gsheet_api`, secret `GOOGLE_SHEETS_SA_JSON`; `daily.yml` sets `POSITIVITY_PROVIDER=gsheet_api`). City map in `data/citymap/` (resolver `src/citymap.py`); 2025 historic = `data/lab_feed_2025_historic.csv` (from `TC Fever Watch Data 2025.xlsx`); season-trend Labs + Overall now REAL. Full detail: PROJECT_STATE 2026-06-17 banner.
- [~] **"Why this score?" UX + calibration refinements (mostly DONE 2026-06-17 PM):** DONE = humanized per-signal readouts (High/Mod/Low level pill + full `{weight}% weight x raw {v}` derivation, no "raw"/"35% reference" in the consumer view); split contribution (+N) from the trend badge; **per-disease `ref_positivity_pct` = 25/4/15/45** (dengue/malaria/chik/typhoid, replacing the global 35); shortened signal labels; methodology + Word doc updated. STILL OPEN: label disease-list deltas with a timeframe (#4); a note explaining Overall vs the top disease (#5, deferred - user said don't touch the dial); formal a11y verify (#7). See PROJECT_STATE newest banner.
- [x] Add the 5 SerpApi keys as Actions secrets -> DONE (5/5 verified in CI; `trends.provider=cached`; pulled by `daily.yml`).
- [ ] Repo name + Pages + production reverse-proxy route (mirror Mosquito Watch).
- [x] Self-host Inter -> DONE (latin woff2 + `@font-face`, replacing the Google Fonts CDN). [ ] Final brand sign-off on the co-branded lockup still pending.
- [ ] Backtest the 3-signal lag on a past monsoon before any public early-warning claim.
