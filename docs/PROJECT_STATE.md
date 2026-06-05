# Fever Watch - Project State & Handoff

> Read this plus `CLAUDE.md` at the start of a new session. It captures what is built, what is
> verified, what is mock/pending, every locked decision, how to run everything, and a ready-to-build
> spec for the next big piece (the SSG).
>
> Fever Watch is a sibling to **Mosquito Watch** (`../Monsoon Disease Project`) but architecturally the
> INVERSE: Mosquito Watch keeps its three layers separate and never blends them; Fever Watch blends
> three signals into one *decomposable* score. The repos are independent.

---

## 1. What this is

A consumer-facing, PharmEasy-branded web tool that gives **one daily risk score per city** for India's
top monsoon fevers, with the per-disease breakdown underneath. City-first: one page per city at
`/fever-watch/{city}`. **Top ~120 cities** (expandable).

- **Diseases (v1):** dengue (flagship), malaria, chikungunya, typhoid, viral fever.
- **The score:** a confirmation-weighted ensemble of 3 signals -> a city headline blend + 5 disease scores.
- **Framing (non-negotiable):** a **risk indicator**, NOT a diagnosis or a case/mosquito count. Forecast-only
  cells are capped and can never show HIGH. No medical JSON-LD.

---

## 2. Status snapshot

| Area | Status | Verified |
|---|---|---|
| Data layer (configs, weather, consolidation engine, grid) | **DONE** | engine smoke-tested; grid 595 cells |
| Top-120 city config (`scripts/gen_cities.py` -> 119 cities) | **DONE** | coord ranges validated; needs gazetteer QA |
| Providers: serpapi (weekly) / googlesheet (daily) / cached, config-driven | **DONE** | googlesheet tested on sample; cached state->city verified; all compile |
| Geolocation module (`assets/js/geo.js`, BigDataCloud + freeipapi) | **DONE** | nearest-city snapping verified nationwide |
| Share-image export module (`assets/js/share.js`) | **DONE** | module built (canvas PNG + native/WhatsApp) |
| Front-end design: 2 clickable prototypes (mobile + desktop) | **DONE** | rendered + screenshot-verified across many iterations |
| Co-branded nav lockup (`assets/img/fever-watch-lockup-white.svg`) | **DONE** | rendered both navs |
| **SSG `/fever-watch/{city}` pages (device-adaptive)** | **NOT BUILT** | see section 9 |
| **GitHub Actions (daily/weekly/deploy)** | **NOT BUILT** | see section 7 item 2 |
| Real trends + lab feeds | **MOCK** | flip via `config/signals.json` when feeds are ready |

Everything runs on the **Python standard library** (no third-party deps). `requirements.txt` is essentially empty.

---

## 3. Architecture & stack

Serverless by design: scheduled scripts write static JSON, a static device-adaptive site reads it.

```
GitHub Actions (cron)                          [NOT BUILT YET]
  daily.yml : build_weather (NASA POWER) + build_daily (reads signals.json) -> grid.json + SSG + deploy
  weekly.yml: build_trends (SerpApi x5) -> trends.json
       |
       v
data/*.json  (committed; weather.json, grid.json[, trends.json])
       |
       v
SSG: src/build_site.py  [NOT BUILT]  ->  /fever-watch/{city}/index.html per city (SEO baked + #fw-app)
       |
       v
Static front end (device-adaptive): one URL serves the MOBILE flow or the DESKTOP flow,
chosen by device at load. Reads grid.json for switching + leaderboard.
Hosting: GitHub Pages; production = pharmeasy.in/research/... subpath via reverse-proxy (mirrors Mosquito Watch).
```

### The 3-signal engine (the heart, built + tested)
- **Weather / breeding** (leading): NASA POWER, per-disease-family shaping (see scoring.json). Daily.
- **Google Search Interest** (coincident): SerpApi Google Trends, per-state. Weekly -> `trends.json` (read by `cached`).
- **PharmEasy lab positivity** (lagging, ground truth): Google Sheet, daily.

`src/consolidate.py` (config: `config/consolidation.json`):
- With positivity: weights ~`30/22/48` (weather/trends/positivity); agreement (spread < 22) x1.08, else x0.96.
- Without positivity: `forecast_only` blends `60/40` and **caps at 69** (one below the HIGH floor of 70) -> can never show HIGH.
- Bands: HIGH >=70, MODERATE >=45, LOW-MODERATE >=25, LOW >=0.
- **City headline blend** (in `build_daily.py`): `0.8 x top disease + 0.2 x mean(rest)`, with the **driver disease named**.

---

## 4. Locked decisions

- **Storage:** static JSON in Git (no server/DB). Daily commits = history + future RF training set.
- **Front-end:** Python SSG + vanilla JS, **device-adaptive** (separate purpose-built mobile and desktop flows
  served from one URL; NOT responsive).
- **Weather source:** NASA POWER (US public domain / CC0; ~3-day latency, no forecast - both fine for a trailing
  breeding index). Open-Meteo kept behind the interface as a dev/forecast-only option (its free tier is non-commercial).
- **Cadence:** weather **daily**, trends **weekly** (SerpApi, 5 keys), lab **daily** (Google Sheet, backend-updated).
- **Blend:** max-dominant `0.8/0.2` + named driver.
- **Geolocation source:** BigDataCloud `reverse-geocode-client` (keyless, client-side, commercial-OK; client-side-only
  constraint) + freeipapi.com fallback. (ip-api.com ruled out: non-commercial + HTTP.)
- **Brand:** PharmEasy - Inter; Porcelain Green `#10847E`; gold accent `#EFD06C`; diagnostics blue `#3661B0` for the
  lab signal. Risk ramp: LOW `#2FA66F`, LOW-MODERATE `#C7A93C`, MODERATE `#E8923A`, HIGH `#E4572E`. Co-branded
  horizontal lockup (mark + divider + "Fever Watch") in nav.

---

## 5. What is built + verified (detail)

**Config (`config/`):** `site.json` (SEO identity, single source for base_url), `cities.json` (119 cities, generated),
`diseases.json` (5, with family + seasonal_push), `scoring.json` (per-family weather shaping), `consolidation.json`
(ensemble + bands + city_blend), `signals.json` (trends/positivity provider selection + config).

**Builders (`src/`):**
- `build_weather.py` -> `data/weather.json`: NASA POWER per city, per-family sub-scores. Fail-loud guard.
- `consolidate.py`: the ensemble engine (smoke-tested; caught + fixed a real forecast-cap-vs-HIGH bug the prototype had).
- `weather_score.py`: the per-family shaping (mosquito unimodal temp ~29C x lagged rain x humidity; waterborne rain-led;
  febrile humidity + temp swing + rain).
- `build_daily.py` -> `data/grid.json`: runs the engine for every city x disease, computes the city blend + driver,
  bakes each city's raw weather + the band thresholds. Provider selection reads `config/signals.json` (env override +
  graceful fallback to mock if `trends.json` is missing).
- `build_trends.py` -> `data/trends.json`: WEEKLY SerpApi builder (interest-by-region per disease + national news_spike).
- `providers/`: weather - nasa_power (DEFAULT), open_meteo (alt), base, registry.
- `signals/`: base, mock (default), googlesheet (positivity, tested), serpapi (weekly upstream), cached (daily reader).

**Front-end (design, prototypes):** `prototypes/mobile.html`, `prototypes/desktop.html`, `prototypes/tokens.css`
(PharmEasy tokens). Both are clickable, PharmEasy-styled, read `data/grid.json`, default Bengaluru, and were
iterated against detailed feedback (symmetric 270deg dial, branded share card, full methodology + 6 citations,
collapsible sections, leaderboard, co-branded lockup). These are the **design source of truth** for the SSG.

**Front-end modules (ready to wire into the SSG):** `assets/js/geo.js`, `assets/js/share.js`.

**Brand assets:** `assets/img/pe_logo-white.svg` (self-hosted), `assets/img/fever-watch-lockup-white.svg`.

---

## 6. What is MOCK / pending the user

- **Trends + lab signals are MOCK** (`signals/mock.py`) until the feeds are wired:
  - Lab: provide the Google Sheet **published-to-web CSV URL** -> set `config/signals.json` `positivity.googlesheet.csv_url`
    and `positivity.provider = "googlesheet"`. Format + sample: `docs/lab_feed_format.md`, `docs/lab_feed_sample.csv`.
  - Trends: add the **5 SerpApi keys** as Actions secrets (`SERPAPI_KEY`, `SERPAPI_KEY_2..5`); run `build_trends.py`
    weekly; set `trends.provider = "cached"`.
- **City coordinates** are ~0.05deg approximations - QA against an authoritative gazetteer before launch.
- **Fonts:** prototypes load Inter from Google Fonts CDN; self-host for production.
- Brand sign-off on the co-branded lockup; convert its "Fever Watch" text to outlines for pixel-perfect rendering.

---

## 7. Next up (prioritized)

1. **SSG `/fever-watch/{city}` (device-adaptive).** The big one. Full build spec in **section 9**.
2. **GitHub Actions:** `daily.yml` (weather + lab read + grid + SSG + commit + deploy), `weekly.yml` (SerpApi trends),
   `deploy.yml` (push + manual). Mirror Mosquito Watch's workflows. 5 SerpApi keys as secrets. Fail loudly if a source fails.
3. **Wire the real feeds** (Sheet URL + SerpApi keys) and flip `signals.json` mock -> real.
4. **Repo + hosting:** create the public repo, enable Pages (Actions source), set `config/site.json base_url`, and ask
   PharmEasy infra for the `/research/fever-watch-.../` reverse-proxy route + apex robots allowance.
5. **Coords QA, self-host Inter, brand sign-off, compliance/counsel pass, 3-signal backtest** before any public
   "early warning" claim.

---

## 8. How to run / build / test

```
# Data (from the project root)
python scripts/gen_cities.py            # regenerate config/cities.json (119 cities)
python src/build_weather.py             # NASA POWER -> data/weather.json   (daily; ~2 min for 119 cities)
python src/build_daily.py               # compose the grid (reads signals.json) -> data/grid.json
python src/build_trends.py              # WEEKLY: SerpApi -> data/trends.json (needs SERPAPI_KEY in env)
python src/consolidate.py               # smoke-test the ensemble engine

# Flip a signal live (no code change): edit config/signals.json
#   positivity.provider: "mock" -> "googlesheet"  (+ set googlesheet.csv_url)
#   trends.provider:     "mock" -> "cached"        (after a weekly build_trends run)

# Preview the prototypes (the .claude/launch.json "fever-watch" server runs this on :8137)
python -m http.server 8137
#   http://localhost:8137/prototypes/mobile.html
#   http://localhost:8137/prototypes/desktop.html
```

Note: the harness preview tool's screenshot capture occasionally wedges after edits; a `preview_stop` +
`preview_start` (fresh renderer) clears it. `preview_eval` keeps working even when screenshot hangs.

---

## 9. SSG build spec (ready for the next session)

Goal: one indexable static page per city at `/fever-watch/{city}/index.html` that serves the **mobile OR desktop
flow** by device, with SEO content baked for crawlers. Architecture decision is **locked: device-adaptive, one page.**

### The page contract (what `build_site.py` emits, what the front-end expects)
- `<head>`: per-city `<title>`, meta description, **canonical** = `base_url + fever-watch/{city}/`, Open Graph/Twitter,
  theme-color `#10847E`, manifest, favicons; a JSON-LD `@graph` with **WebPage + Dataset + FAQPage** (NO medical schema).
- `<body>`:
  - A **baked, crawler-readable content block** (also the no-JS fallback): `<h1>`, the city blend (score + band + named
    driver), the 5 disease scores as real HTML, the "updated" date, a short methodology summary, and the FAQ. Real text,
    not JS-rendered.
  - The app mount: `<div id="fw-app"></div>`.
  - `<script>window.FW = { city: "{city_id}", gridUrl: "/data/grid.json" };</script>`
  - `<link rel="stylesheet" href="/assets/css/tokens.css">`
  - `<script src="/assets/js/geo.js" defer></script>` `<script src="/assets/js/share.js" defer></script>`
  - `<script src="/assets/js/fw-loader.js" defer></script>`

### Front-end to build (extract from the two prototypes - keep the flows SEPARATE)
- `assets/js/fw-loader.js`: detect device with `matchMedia('(max-width: 819px), (pointer: coarse)')` -> set
  `document.body.className = 'fw-mobile'|'fw-desktop'`, then inject the matching `assets/css/{mode}.css` +
  `assets/js/{mode}.js`. Only the active flow loads.
- `assets/css/mobile.css`, `assets/css/desktop.css`: extracted from each prototype's `<style>`.
- `assets/js/mobile.js`, `assets/js/desktop.js`: extracted from each prototype's `<script>`, adapted to:
  - mount into `#fw-app` (not `document`/`#app`);
  - default city = `window.FW.city`; grid url = `window.FW.gridUrl`;
  - **create their own sheets/scrim/popover DOM dynamically** (the prototypes have those as static HTML);
  - integrate `FeverWatchGeo.resolve(DATA.cities)` -> if the detected nearest city differs and the user has not picked,
    offer it as the default with a "Showing {city}, not you? change" affordance (never a hard lock);
  - wire the Share button(s) to `FeverWatchShare` (render the card -> `nativeShare` on mobile, download + WhatsApp on
    desktop), passing `{emoji, score, band, bandColor, title, sub}` for the driver disease.

### Also generate
- A **landing page** at `/fever-watch/index.html`: the city search + geo (default to detected city, link to its page).
- `sitemap.xml` (all 119 city URLs + landing), `robots.txt` (Disallow-all on staging via `SITE_ENV`, like Mosquito
  Watch; canonical always points at production), `site.webmanifest`, favicons.
- Output dir: pick `dist/` (or in-place); mirror Mosquito Watch's `build_site.py` conventions (stdlib, idempotent,
  `SITE_ENV=staging|production`).

### Reuse from Mosquito Watch
`../Monsoon Disease Project/src/build_site.py` is the reference SSG (meta + JSON-LD + robots + sitemap + manifest
pre-render). Adapt its patterns; drop the medical bits; make it multi-page (per city) instead of one index.

---

## 10. Data formats

- **Lab feed (Google Sheet CSV):** `docs/lab_feed_format.md` + `docs/lab_feed_sample.csv`. One row per
  city x disease x period: `week_start, city, disease, tests_booked, positives` (or `positivity_pct`). Aggregate,
  de-identified. `tests_booked < 30` or missing -> that cell is "no data" -> forecast-only.
- **`data/trends.json`** (from `build_trends.py`): `{ diseases: { <id>: { query, news_spike, by_state: { <State>: 0-100 } } } }`.
  `cached.py` maps a city -> its state's value + the disease news_spike.
- **`data/grid.json`** (from `build_daily.py`): `{ cities:[{id,name,state,lat,lon,climate,aliases?,weather,blend}],
  diseases:[...], bands:[...], grid:[{city,disease,family,score,band,color,soft,emoji,confidence,mode,note,weights,
  signals:{weather,trends,positivity,news_spike}}] }`. The front-end reads only this file.

---

## 11. Guardrails & conventions (carry into every session)

- **Risk-indicator framing only.** Never diagnostic/predictive of individual illness. No medical JSON-LD. Forecast-only
  cells are capped (cannot show HIGH).
- Positivity is an aggregate city-level **trend**, never a re-identifiable rate (selection bias). Weather temperature is
  not body-temperature fever.
- **No em dashes, en dashes, or middot separators** in any shipped copy (meta, UI, JSON-LD, engine notes). ASCII hyphen only.
- `base_url` lives only in `config/site.json`; keep in-page asset paths relative-or-root-absolute and consistent.
- Internal docs/spreadsheets (`*.xlsx`) gitignored; never commit to a public repo.
- Going live = a `config/signals.json` flip, not a code change. Builders fail loud, never publish garbage.
- Re-check copy with compliance/counsel before any public launch.

---

## 12. File map

```
CLAUDE.md  README.md  requirements.txt  .gitignore
.claude/launch.json            preview server config (fever-watch on :8137)
config/   site cities(119) diseases(5) scoring consolidation signals
data/     weather.json  grid.json        (trends.json appears after a weekly build_trends run)
scripts/  gen_cities.py                  one-off city-config generator
src/
  build_weather.py  build_daily.py  build_trends.py  consolidate.py  weather_score.py  httputil.py
  providers/        weather: nasa_power(DEFAULT), open_meteo(alt), base, __init__(registry)
  signals/          base, mock(default), googlesheet, serpapi, cached, __init__(registry, config-driven)
prototypes/         mobile.html  desktop.html  tokens.css   <- design source of truth for the SSG
assets/
  img/  pe_logo-white.svg  fever-watch-lockup-white.svg
  js/   geo.js  share.js                <- ready to wire into the SSG front-end
docs/   lab_feed_format.md  lab_feed_sample.csv  PROJECT_STATE.md
index.html                              LEGACY: the early 8-city vanilla-JS port (pre-PharmEasy redesign);
                                        superseded by prototypes/ and to be replaced by the SSG. Safe to delete.
```

---

## 13. Pending user/account actions

- [ ] Provide the PharmEasy lab **Google Sheet published-CSV URL** -> `config/signals.json` + provider `googlesheet`.
- [ ] Add the **5 SerpApi keys** as Actions secrets -> trends provider `cached` (weekly `build_trends.py`).
- [ ] Create the **public repo** + enable **GitHub Pages** (Source = Actions); set `config/site.json base_url`.
- [ ] PharmEasy infra: `/research/fever-watch-.../` reverse-proxy route + apex robots allowance.
- [ ] Brand sign-off on the co-branded lockup; provide the exact lockup asset if the rebuilt SVG is not pixel-perfect.
- [ ] QA the 119 city coordinates.

---

## 14. Session housekeeping (done at handoff)

- Git: the repo is `git init`-ed but **not yet committed**. Suggested first action in the new session:
  `git add -A && git commit -m "Fever Watch: data layer, providers, prototypes, geo/share modules"`.
- The temporary `fever-watch` entry that had been added to the OLD repo's `.claude/launch.json`
  (`../Monsoon Disease Project`) has been **reverted**; that repo is clean again.
- Fever Watch now has its own `.claude/launch.json` (preview server `fever-watch` on :8137).
- `data/grid.json` is in its **mock** state (trends + positivity = mock); no stray `trends.json` committed.
```
