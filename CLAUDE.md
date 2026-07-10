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
- **Hosting:** PRODUCTION deploys to a **Hostinger VPS (CyberPanel / OpenLiteSpeed)** via rsync-over-SSH from
  `.github/workflows/deploy-cyberpanel.yml` (2026-07-02; build stays in Actions with `SITE_ENV=production`, the VPS
  serves the pre-rendered static files, no Python/PHP). It is triggered by **daily.yml's `dispatch-production` job** (an
  explicit `gh workflow run` fired the moment the fresh grid is committed, cron-lag-free), so the VPS updates by **~05:30
  IST** (2026-07-07; this replaced the 00:30-UTC schedule, which GitHub delayed a consistent ~4h to ~10:00 IST, and the
  flaky `workflow_run` chain that never fired). Manual `workflow_dispatch` is the recovery path; the rsync step
  auto-retries up to 2x on a transient SSH timeout. **GitHub Pages (github.io) is now the STAGING origin** (`deploy.yml` on push + `daily.yml`
  daily; `daily.yml`'s Pages `deploy` job is `continue-on-error` so a Pages hiccup cannot block the VPS deploy).
  Public URL + `base_url` are unchanged: `https://pharmeasy.in/fever-watch/` (a subpath on the pharmeasy.in apex
  served to the VPS origin via the edge reverse-proxy, mirroring Mosquito Watch; the edge rule is PENDING, another
  team). `base_url` lives only in `config/site.json` (set 2026-06-25; was `/research/fever-watch-2026/`); the
  CyberPanel workflow overrides it at build time from the `FW_PROD_BASE_URL` secret, which MUST be the public
  pharmeasy.in URL, NOT the VPS origin host. New Actions secrets: `FW_PROD_BASE_URL`, `DEPLOY_HOST`, `DEPLOY_USER`,
  `DEPLOY_SSH_KEY`, `DEPLOY_PATH` (the dedicated `.../public_html/fever-watch/` folder; rsync `--delete` mirrors it),
  `DEPLOY_PORT`.
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

- Risk-indicator framing only; never diagnostic or predictive of individual illness; no medical JSON-LD. (The
  reviewer byline added 2026-06-24 uses schema.org's GENERIC `WebPage.reviewedBy` Person entities for E-E-A-T, NOT
  `MedicalWebPage` / medical-entity types - that is the compliant, non-medical way and stays inside this guardrail.)
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
  (`Weather conditions today`) shows the real weather-score drivers - 3 tiles** Temperature near 29C / 14-day
  Rainfall / Humidity (desktop 3-up, mobile 2 + Humidity full-width); the old "estimated stagnation" tile was removed
  2026-06-24 (producer kept in `build_daily.py`).
- **2026-06-24 medical-review UX overhaul (committed + pushed to master; full detail in PROJECT_STATE):**
  "breeding" -> "Weather conditions" everywhere user-facing (mosquito kept where it is the mechanism; the Rainfall tile
  names typhoid too); stagnation tile removed (producer kept); precautions section -> `What you can do`; the dial
  gained a plain-language **meaning line** (copy simplified 2026-06-26: `Right now {city}'s overall score is {score}/100, {band
  phrase + driver}. A daily look at local risk, not who's actually sick.` - `BAND_MEAN` is now a per-band PHRASE
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
  `dialInfo` onClick branch + `positionTip` + `firePeek` + `maybeScrollPeek` + `onTipScroll` are byte-identical
  across the JS twins (`peekDialInfo` differs by flow). **Tooltip positioning (2026-06-25):** `.dialtip` is
  `position:fixed` (z-index 90, above the sticky header) and JS-placed by `positionTip` (renamed from `positionCaret`),
  mirroring `method.js` `placePop` - it sits above the ⓘ, FLIPS below (`.dialtip.below`, caret flips) when there is
  no room above (clears the header), clamps horizontally to the viewport, and keeps the caret on the ⓘ. This fixed a
  bug where the box overflowed the top, overlapping the header + sidebar. (CSS is not parity-gated; markup is, so the
  fix is JS+CSS only.) Desktop hover-open was dropped (it opened an unplaced fixed box); click + peek place it.
- **2026-06-26 copy simplification + "why" chips + mobile polish (full detail in PROJECT_STATE):** plain-language
  pass on hard-to-read copy - the lab metric is now **"share of positive tests"** (not "positivity"); the dial
  "overall read" -> "overall score" and "conditions" -> "local risk"; the dial 80/20 line, the SIG "what" lines, the
  TIPINFO popovers, and the `consolidate.py` engine notes (agree / disagree / forecast / news-spike, baked into
  `grid.json`) were all reworded; the FAQ "how worried" answer aligned. The **"Why this score?" breakdown now tags
  ONLY the highest + lowest disease with a plain-language driver line** as a 2nd row under the disease name (shared
  `whyChip`/`_why_chip`, byte-identical 3-way, names the signal by CONTRIBUTION order; "" when forecast-absent /
  all-Low / no score spread). Mobile: `.acchead` `min-height:71px` equalizes the four disease rows; the breakdown
  trend `.sigbadge` (up + down) is hidden for now (tokens.css). Also (2026-06-25 method citations): the popover
  source links were swapped to PMC6518529 (rain + temperature `/#sec5`) and pubmed30443418 + springer (search,
  via a new `method.js` `data-href2` second-link slot).
- **2026-07-04 SEO: dated page titles + "today" copy sweep (committed + pushed `4f883db`):** Page `<title>`s are now
  DATED and name all four diseases - city = `{City} Monsoon Fever Risk, {DD Mon YYYY} | Dengue, Malaria, Chikungunya,
  Typhoid | Fever Watch`; landing = `Monsoon Fever Risk in India, {date} | ...` (both build the date from
  `_fmt_date_js(generated_at)`, IST, so it re-stamps every daily build and matches the on-page Updated line; also feeds
  `og:title`/`twitter:title`). Search-Console-led: the flagship query is disease+city (`dengue mumbai`, `kolkata
  dengue`) + year (`...2026`) + monsoon + now-intent (`...now`). Every user-facing **"this week" was swept to "today"**
  (scores, rankings, section headers incl. `Weather conditions today`, leaderboard, share cards + the `Today, {date}`
  card stamp, share text `Today:`) or **"right now"** (band readings, weather-window sentences, question phrasings)
  across build_site.py + faq.js + mobile.js + desktop.js + build_share_cards.py; meta description opens `Today's ...`.
  The inert `PERIOD_LABELS` ("This week"/"This month" on the dead week/month tabs) are untouched. "cases" is
  deliberately NOT chased in the title (no case counts). Twins kept byte-identical (above-fold `parity_check` + a
  `faq_items` vs `faq.js build()` render-diff both pass). STILL DEFERRED: the dynamic driver-led meta description
  (lead with the actual top disease + its live number).
- **2026-07-06 per-city localized outbound links (committed + pushed):** Two PharmEasy links now point at the
  visitor's CITY page for local-SEO authority, each with an honest generic fallback. (1) The **"Book a fever panel
  test" CTA** (in-content `What you can do`, SSR fallback + both JS flows) uses `config/diag_links.json` (**100/209**
  cities, from the diagnostics `local-all-package.xml`, 102 pages); the URL is stored as `city.diag_url` on every grid
  city (build_site enriches the in-memory grid + re-serializes the served `dist/data/grid.json`, seed carries the
  current city's) so the CTA tracks the CLIENT-SIDE-SWITCHED city, not just the landed page; params
  `?src=feverwatch&page=2#:~:text=Fever` (same deeplink everywhere, locked with marketing). (2) The **header
  "Medicines" nav link** (`nav_html`, SSR, per page) uses `config/med_links.json` (**204/209**, from the 1322-page meds
  sitemap); `?src=feverwatch` (old `?src=homecard` dropped from Medicines ONLY - Lab tests / Healthcare / Blog keep
  theirs); the header is static per-page SSR so it reflects the page's city and does NOT re-render on client-side
  switch. Aliases are state-verified; **brahmapur (Odisha) is deliberately NOT mapped to berhampore-2530 (West Bengal,
  cross-state)**. Meds fallbacks (absent from the 2022 sitemap): bhubaneswar, kolhapur, rohtak, karimnagar, brahmapur.
  Full detail + match tables: PROJECT_STATE 2026-07-06 banner.
- **2026-07-08 SEO Phase 0 on-page pass (committed + pushed; plan + forecast in `docs/seo_growth_plan.md`):**
  Every city page gained: **BreadcrumbList** JSON-LD (PharmEasy > Fever Watch > {City}; landing 2-item, wired to
  WebPage.breadcrumb); **Dataset enrichment** (temporalCoverage `{yr}-06-01/..`, isBasedOn x4 sources incl. "Google
  Trends search interest (via SerpApi)", measurementTechnique incl. the forecast cap, variableMeasured x5) ->
  Google Dataset Search eligible; **dynamic driver-led meta description** (`{City} fever risk today, {date}:
  {driver} leads at {n}/100 ({BAND}). Dengue {d}, ... A risk indicator, not a diagnosis.`, 154-169 chars, re-stamped
  daily; landing dated too); **"How this monsoon compares" season block** (archive ly-vs-ty same-week compare,
  +/-8 thresholds, last season's peak week; the anti-thin-content block; omitted honestly when a slice is missing);
  **"Nearby cities right now" chips** (nearest-5 equirectangular, crawlable links + in-app switch, inside the
  leaderboard card); **dated weather sub** (`Conditions as of {date} ...`, byte-identical 3-way); the **"What you
  can do" CTA is personalized** (`Book a fever panel test in {City}`). Shared helpers live in build_site.py
  (_season_bits/_nearest_cities/FW_TESTS) + both flows (seasonBits/nearbyHtml/FW_TESTS) - facts byte-consistent
  3-way (same +/-8 thresholds, same 0.00872664626 distance constant, id tie-break). **The "Fever tests" block is
  BUILT but GATED OFF** pending the medical/counsel review (~2026-07-15): `FW_TESTS_ENABLED=False` (build_site.py)
  + `FW_TESTS_ON=false` (mobile.js/desktop.js); to ship, flip all three AND re-add the `#s-tests` TOC link in both
  byte-identical TOC twins + desktop spyScroll ids (instructions at each flag). Its `.fwtests` CSS stays dormant in
  tokens.css. Independently QA'd (fresh-eyes agent): 0 blockers/majors, facts recomputed on all 209 cities,
  SHIP-READY verdict; post-QA fixes folded in (meta tail trim, CTA localization, SerpApi attribution).

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
- [~] Production hosting: **CyberPanel / OpenLiteSpeed VPS deploy WIRED** (2026-07-02, `deploy-cyberpanel.yml`, rsync-over-SSH, `SITE_ENV=production`; github.io demoted to staging; repo = `pharmeasyMarketing/fever-watch`). STILL OPEN: dry-run-verify the first live `--delete` deploy; confirm `FW_PROD_BASE_URL` = the public pharmeasy.in URL; the **pharmeasy.in edge reverse-proxy route** to the VPS origin (another team); HARDEN (pin `burnett01/rsync-deployments` to a SHA, add known_hosts host-key pinning).
- [x] Self-host Inter -> DONE (latin woff2 + `@font-face`, replacing the Google Fonts CDN). [ ] Final brand sign-off on the co-branded lockup still pending.
- [ ] Backtest the 3-signal lag on a past monsoon before any public early-warning claim.
