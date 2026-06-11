# Fever Watch - Project State & Handoff

> Read this plus `CLAUDE.md` at the start of a new session. It captures what is built, what is
> verified, what is mock/pending, every locked decision, and how to run everything. The SSG is
> **LIVE on GitHub Pages staging: https://pharmeasymarketing.github.io/fever-watch/**
> The trend module + the 4-disease set + all the 2026-06-09 trend refinements below are **COMMITTED + PUSHED +
> DEPLOYED** (commit `df15dcc`, push to `master` -> deploy run green) and **verified live** (the staging Bengaluru
> page returns the trend module, the "four fevers" copy, the 4 diseases, and zero "viral").
>
> **2026-06-11 (UI batch: desktop share-dock recolor, live-ready footer, trend y-axis, leaderboard "your city"
> pin; share-image redesign #5 kicked off):** five user-requested enhancements. #1-#4 are BUILT + verified on both
> flows + adversarially reviewed (committed + pushed to master this session); #5 is planned with locked decisions
> and now in progress.
> - **(#1) Desktop share dock recolored to match the mobile floater:** `.fw-dock` is now Porcelain Green with white
>   text, a white Share button with green text, and a ghost-on-green copy button (was the inverse: white dock, green
>   button). CSS-only in `assets/css/desktop.css`; the mobile `.fw-foot` bar is the reference scheme.
> - **(#2) Footer copy made live-ready:** dropped "simulated in this preview"; the disclaimer now reads "Live
>   weather via NASA POWER (public domain); Google search interest via Google Trends; lab signal from PharmEasy
>   diagnostics (aggregate, de-identified)." in `build_site.py:321` (shipped SSR) + the two frozen prototype mirrors.
>   NOTE: this names the lab signal as live PharmEasy diagnostics, so it should go PUBLIC only alongside flipping
>   `positivity.provider` to `googlesheet` (lab feed is still mock). Legacy `index.html` still carries the old
>   "preview/simulated" copy + retired viral_fever (flagged for delete; superseded by the SSG).
> - **(#3) Season-trend chart got a y-axis scale + caption + data labels (JS<->Python mirrored):** a left gutter
>   (PADL 12->26; mini sparklines keep 12), 0/mid/top y-ticks in the gutter + 2 faint gridlines, spaced data labels
>   (you-are-here value in the metric colour + last-year reference points at weeks 6/13/19), and a one-line axis
>   caption "Vertical scale starts at 0; higher means greater risk." (NOT "0 to 100" - the y-axis ZOOMS to the data,
>   so a fixed top would contradict the rendered top tick; caught in review). Mirrored in `trend.js`
>   chartGeom/chartSVG + `build_site.py` `_trend_chart_static`/`_trend_html`; CSS in `prototypes/tokens.css`
>   (`.fwtrend-axiscap`, `.fwtrend-svg text`, asymmetric `.fwtrend-months` padding 7.65%/3.5% for the gutter).
> - **(#4) Leaderboard pins the user's own city as a last row when it is off the current page:** new `rowFor()`
>   helper in BOTH `mobile.js` + `desktop.js` `leaderboardInner`; `pinned = me && !onPage && !q` (suppressed while
>   searching, auto-suppressed once paging reaches the city's real rank). Verified: Thane (#139) pins on pages 1-2
>   and shows in place on page 14. `.lb-pinned` CSS (green top border + faint green bg) in both flow CSS files.
> - **(#5) WhatsApp/OG share-image redesign - STARTED, decisions LOCKED:** rebuild `share.js` (canvas, the real
>   shared image) + `build_og.py` (Pillow) to the new mock: a 180deg NEEDLE gauge (green/yellow/red + needle, NOT
>   the app's 270deg ring), regional-script city/state name, an "up from N last week" chip, and a "most at risk"
>   row. Locked: per-state native scripts (Wikidata auto-pull -> PharmEasy QA), REAL prior-week score (rolling
>   `data/history.json` in `build_daily`), single static "Children and the elderly" most-at-risk line, BOTH portrait
>   + 1200x630 landscape redesigned, band pill in the brand ramp colour. Phase 1 = data foundation (prev_score +
>   name_local plumbing), Phase 2 = needle-gauge card redesign (both renderers, mirrored), Phase 3 = names + Noto
>   Indic fonts. Full plan + decisions saved to memory (share-image-redesign-plan).
> - Verified headlessly on both flows; an adversarial parity/copy review passed (one defect fixed: the axis-caption
>   "0 to 100" claim vs the zoomed axis). The local :8137 grid.json fetch still flakes under instrumented load
>   (a local-only issue, fine on Pages).
>
> **2026-06-09 (EVEN LATER: data-pipeline robustness - carry-forward over mock, atomic writes, the CI
> cancellation fix - plus a Google-Sheet logger overhaul. Backend/CI only; the deployed site is unchanged
> and the committed grid.json gets the new fields on the next daily run):**
> - **CI cancellation diagnosed + fixed:** the 2026-06-09 cron run was CANCELLED (run_log: weather
>   "cancelled", rest "skipped"). Cause: GitHub delayed the 01:30 UTC cron to ~05:47 UTC, which collided
>   with a morning push, and `daily.yml` + `deploy.yml` shared `concurrency: group: pages` (deploy has
>   cancel-in-progress:true), so the push-deploy cancelled the in-flight refresh. Fix: `daily.yml` now
>   uses its OWN group `fever-daily-refresh`; the Pages publish stays serialized by the environment.
> - **run_log `reason` column:** `sheetlog.log()` + the workflow pass a reason for any non-success step,
>   so cancelled/skipped rows explain themselves instead of being blank.
> - **Phase 1 (never clobber good data):** new `src/iohelpers.py write_json_atomic` (temp + os.replace)
>   in build_weather/build_trends/build_daily, so a crash/kill can't corrupt the last-good file.
>   build_trends MERGES a partial SerpApi run over the previous trends.json (failed diseases keep their
>   last-good by_state, NOT a drop to floor-4), each disease stamped with `as_of`.
> - **Phase 2 (carry-forward + freshness):** build_daily tags each cell's per-signal freshness
>   (fresh / carried Nd / stale Nd) from the file `as_of` timestamps, flags `stale` past a `stale_days`
>   budget (config/consolidation.json, default 3) + downgrades that cell's confidence one step, and will
>   drop stale positivity to forecast-only once the lab feed is real. So a failed API falls back on the
>   last-good REAL value, not mock (mock = cold-start only). New grid fields: per-cell `freshness`,
>   `stale`, `signals.trends_raw`/`trends_as_of`; payload `stale_days`/`stale_count`.
> - **Logger build-up formulas (your ask - "how is weather_score / trends_score computed?"):** in the
>   Sheet `raw_data` tab, `weather_score` (K) + `trends_score` (L) are now in-sheet FORMULAS (not posted
>   values) - K inlines the full family-weighted build-up from temp/humidity/rain (VERIFIED to reproduce
>   the grid value exactly: 71=71, 91=91, ...), L = MAX(4, MIN(100, trends_state_interest)). New columns
>   `trends_state_interest`, `weather_fresh`, `trends_fresh`, `stale`; confidence downgrades when stale;
>   data_dictionary updated. Apps Script source is in `docs/sheets_logging.md`.
> ACTION FOR YOU (the Apps Script lives in the Sheet, not the repo): paste the updated `Code.gs` from
> `docs/sheets_logging.md`, re-deploy a NEW version, DELETE the `raw_data` + `daily_summary` tabs (they
> recreate with the new columns next run) and add a `reason` header in `run_log!G1`.
>
> **2026-06-09 (LATEST: trend-module polish + dropped Viral fever, so v1 is now 4 diseases):** three
> review changes on top of the shipped trend module, all verified on both flows:
> - **Desktop trend heading moved OUTSIDE the card** to match the other page sections: the section now leads with an
>   h2 "This monsoon vs last in {City}" + a "Season trend" subtitle (`.fwtrend-sectop`, reusing `.sechead`/`.secsub`),
>   the Hide/Show toggle top-right, and the card itself now leads with the verdict. Mobile keeps its in-card eyebrow +
>   title. `trend.js renderCard` is mode-aware; `build_site.py _trend_html` mirrors the heading-outside SSR; the chevron
>   now keys off `aria-expanded` so it rotates correctly with the toggle outside the card.
> - **Month axis labels fixed (both flows):** moved from SVG `<text>` (which scaled with the chart - huge on desktop,
>   unevenly spaced) to a fixed-size HTML row (`.fwtrend-months`, flex space-between) -> equidistant at any width
>   (verified desktop gaps ~204px, mobile ~70px), 13px on desktop / 11px on mobile, pulled tight under the chart (gap 0).
> - **Chart layout reworked to "fill the height" (user picked Option 2 from a 4-way mock):** the desktop chart was too
>   tall (~390px) with a big empty top on low-value tabs (e.g. Labs peaks at 70 on a 0-100 axis). Fix = (a) a
>   mode-dependent viewBox aspect so the chart is COMPACT on the wide desktop (viewBox 340x92 -> ~244px) while mobile
>   stays taller (340x150 -> ~142px); and (b) the y-axis ZOOMS to the data (top = peak + 15%, capped 100) so the curve
>   fills the space - Overall + high signals (peak ~90) stay at full 0-100 so the risk zones keep meaning, low tabs like
>   Labs zoom in. `trend.js` got a `chartGeom`/`geomXY` refactor (the tooltip reads the live geometry via `st.geo`);
>   `build_site.py _trend_chart_static` mirrors it (compact + zoom). Verified both flows: tooltip still positions
>   correctly, Overall zones intact, desktop CLS still 0.
> - **Signal tabs made visually consistent with Overall:** Overall has the faint risk-zone colour bands as a backdrop;
>   the signal tabs were plain white ("vanilla"). Each signal tab now gets a soft backdrop GLOW in its own colour
>   (Weather teal / Searches purple / Labs blue, a low-opacity vertical gradient in `chartSVG`), so every tab reads as
>   equally designed while Overall keeps its meaningful zones. (The compact+zoom geometry was already identical across
>   tabs - verified - so the only gap was this backdrop.)
> - **Mobile floating share bar recoloured to stand out (was invisible white-on-white):** `.fw-foot` is now Porcelain
>   Green with white text; its Share button is a NEW standalone class `.fw-foot-share` (white-on-green, keeping the
>   current 12px radius + design) deliberately SEPARATE from the global `.sharebtn` so the two never affect each other
>   (the risk-card / sheet Share buttons stay green, verified). Mobile only; the desktop dock is unchanged.
> - **Viral fever REMOVED (v1 is now dengue, malaria, chikungunya, typhoid):** PharmEasy runs no lab-positivity /
>   parameter test for "viral fever" (a catch-all, not a specific testable condition), so it could NEVER get the third
>   "ground-truth" signal (permanently forecast-only) and is not a bookable fever-panel test (so it never served the
>   funnel). Removed from `config/diseases.json` (+ the `viral_fever` trends keywords in `config/signals.json`);
>   `data/grid.json` regenerated -> **912 cells (228 x 4)**. Copy swept everywhere "...and viral fever" / "the five
>   fevers" / the Febrile methodology bullet appeared: `build_site.py` (meta, JSON-LD, hero subtitles, FAQ + methodology,
>   the "four fevers" heatmap subtitle, `_CAT`), `faq.js`, `mobile.js`, `desktop.js` (SSR<->JS byte-identical pairs kept
>   in sync), `config/site.json` (description + keywords), CLAUDE.md + the lab-feed format docs. Verified: **0
>   "viral"/"five fevers" left in `dist/`**; both flows render 4 pills / 4 ranked bars / 4 leaderboard tabs; trend
>   JS<->Python parity still byte-identical; **desktop CLS still 0** (the 5->4 bar change is consistent SSR<->JS). The
>   `febrile` family shaping stays in `weather_score.py` but is now unused.
> All of the above (trend module, last-year stabilization, heading/labels/Option-2 chart, signal-tab backdrops, the
> viral-fever removal, and the green share bar) is COMMITTED + PUSHED + DEPLOYED in commit `df15dcc` and verified live.
>
> **2026-06-09 (LATER: the "This monsoon vs last year" trend module SHIPPED + verified on both flows - it was the
> LAST remaining handoff component, so the build is now FEATURE-COMPLETE on staging):**
> Built the season-over-season trend module per `docs/season-trend-module-brief.md`. (The design bundle URL had
> expired - 404 - so it was brand-recreated from the written brief, which carries the full anatomy / colours / copy /
> data shape.) Placed ABOVE the FAQ on both flows; recomputes per city on every switch, mirroring the faq.js pattern.
> - **New shared widget `assets/js/trend.js`** (`window.FeverWatchTrend`): words-first verdict (above / below / in line
>   x rising / falling) + delta chip, a context line ("Last year peaked at X (BAND) in late August"), segmented tabs
>   (Overall / Weather / Searches / Labs - ONE chart at a time), a hand-rolled inline-SVG chart (faint LOW/MOD/HIGH
>   risk zones on Overall only + soft gray last-year band + bold this-year line + "you are here" dot + Jun-Oct month
>   ticks, no numeric axis), tap/hover tooltip ("Week of D Mon - This year a - Last year b", future weeks honestly
>   blank), collapse/expand, a per-metric caption, provenance microcopy, a "Labs coming soon" empty state, and a
>   DESKTOP small-multiples row (3 signal sparklines, click to promote to the hero). It owns its subtree (tabs /
>   tooltip / collapse handled internally), so the flows just `mount()` it after each render.
> - **Deterministic MOCK from the city's REAL scores** (not fake static data): a 22-week (1 Jun - 30 Oct) seasonal
>   SHAPE. THIS-YEAR is scaled so it ends at the city's current blend / signal sub-scores; LAST-YEAR is a **STABLE
>   per-city peak seeded ONLY from the city id** (band 64-95) so "last year peaked at X" NEVER drifts as the daily
>   score or the week changes (verified: Bengaluru reads peak 89 whether its score is 56/60/64 or the week advances).
>   The chip / verdict / captions still move with the live score. `asOfWeekIndex` from `grid.generated_at` (currently
>   week 2 -> the brief's early-season state: a short 2-point this-year line over the full gray last-year band).
>   2026-06-09 UPDATE (user-requested "stabilize the mock"): replaced the original score-derived last-year (`lyFactor`,
>   which made the peak wander day-to-day and across the season - incoherent for immutable history) with the fixed
>   `lyPeak` seed. Trade-off: a stable peak makes last year's EARLY-season value low, so early-season deltas are widest
>   (a few cities ~+/-40-48%) and narrow toward the Aug peak; band 64-95 was tuned to keep most reads calmly
>   "below/around last year" with a modest "above" tail (228-city split ~138 below / 62 above / 28 in line; one
>   constant pair, easy to retune). The math (SHAPE / city-hash / `lyPeak` / round-half-up) is mirrored EXACTLY in
>   Python (`build_site.py _trend_series`) and JS (`trend.js`); a Node parity harness confirms BYTE-IDENTICAL series +
>   peaks. Swap for a real `data/history.json` later (format `docs/lab_feed_historic_format.md`) by replacing
>   `_t_metric_series` / `metricSeries`.
> - **Crawlable SSR**: `build_site.py _trend_html` bakes a static Overall chart + verdict + context + caption + sources
>   into every page's `.fw-below` block, between "other cities" and the FAQ (baked order verified). The flow JS
>   replaces it on hydration.
> - **Wiring**: inserted above the FAQ in `mobile.js` + `desktop.js` render(); the desktop TOC gained a "This year vs
>   last year" -> `s-trend` link, added BYTE-IDENTICALLY to BOTH `desktop.js` render() and `build_site.py _desktop_pre`
>   so desktop hydration stays a no-op repaint (CLS 0), and `s-trend` joined `spyScroll`'s id list. Shared `.fwtrend*`
>   CSS in `prototypes/tokens.css`. `trend.js` added to the page `<script>`s and the `asset_version()` cache-bust hash
>   (faq.js too - it had been missing from the hash).
> - **Verified headlessly (preview, BOTH flows):** renders above the FAQ; verdict/chip/context correct; tabs switch the
>   chart + caption + line colour and drop the risk zones for signal tabs; tooltip shows values and blanks future weeks;
>   **city switch recomputes the module** (Pune ~0%/peak 83, Delhi -7%/peak 69, Guwahati -12%/peak 100, all matching
>   Python); desktop small-multiples render (mobile has none); collapse works; **desktop CLS still 0** (0 shifts); no
>   trend-related console errors (only the known local grid-fetch flake, which the inline seed covers). Tone spread over
>   the 228 cities: 91 below / 75 above / 62 in line.
> NOTE: the trend series + copy now live in TWO places - keep `build_site.py _trend_series`/`_trend_caption` and
> `assets/js/trend.js` in sync (same two-place rule as the FAQ).
>
> **2026-06-09 (FAQ + Ranked Composite Bars + footer ALL SHIPPED + deployed; trend module shipped later same day, see the entry above):**
> A big UI session. Done + on staging today:
> - **FAQ redesign + per-city content (commit `1cdb6f7`):** replaced the 6 generic FAQs with **10 humanized,
>   per-city FAQs** (interpolated from blend / driver / weather / mode / national rank / signals) in a new
>   **accordion** (rounded cards, chevron tile, first two open). SSG source = `build_site.py faq_items(city,...)`
>   feeding the baked `_faq_html` + the per-city FAQPage JSON-LD; shared `.faq-list` CSS in `prototypes/tokens.css`.
> - **FAQ-on-switch fix = Option A (commit `cf18117`):** the FAQ used to go stale when you switched city without a
>   reload (it read the initial city's inlined `seed.faq`). Now a shared **`assets/js/faq.js`**
>   (`window.FeverWatchFaq.forCity`) mirrors `faq_items()` and **recomputes the FAQ from the loaded grid on every
>   render/switch**; both flows call it. Dropped the redundant `seed.faq` (kept a tiny `seed.rank`) -> each city HTML
>   84.9 -> 80.7 KB. **Crawlability unchanged** (the per-city `<details>` accordion + FAQPage JSON-LD are still
>   Python-baked into every static page). NOTE: FAQ copy now lives in TWO places - edit BOTH `build_site.py
>   faq_items()` (SSG) and `assets/js/faq.js` (client) and keep them in sync.
> - **Desktop Ranked Composite Bars (commits `730b6dd` + `b72e449`):** replaced the heatmap in `weekSection`'s `.grid2`
>   with ranked composite bars (segment = `signal/sum*score` %, signal strip, rank, emoji, score in band colour, "Top
>   concern" flag) + the card title "This week's outbreak signal score" / subtitle. `desktop.js heatmapCard` and
>   `build_site.py _heatmap_card` are **byte-identical** so the SSR above-fold matches hydration (`#s-week` SSR==live,
>   **desktop CLS 0**). Desktop only (mobile keeps its breakdown).
> - **Footer rebuilt to the PharmEasy 4-column reference (commit `c0bf249`):** Company + Our Services / Featured
>   Categories / Need Help + Policy Info / **Follow Us** (inline-SVG social icons); **payment-partners row removed**;
>   light blue-gray bg; Fever Watch disclaimer + copyright kept. `footer_html` + `FOOT_*` in `build_site.py`;
>   `.footcol/.footsec/.footfollow` CSS in `desktop.css`/`mobile.css`.
> - Earlier today: saved the lab-feed templates (`docs/lab_feed_2026_live_template.csv`,
>   `docs/lab_feed_2025_historic_template.csv`), `docs/lab_feed_historic_format.md`, and the trend design brief
>   (`docs/season-trend-module-brief.md`).
>
> ### >>> DONE: the "This monsoon vs last year" trend module SHIPPED (details in the 2026-06-09 LATER entry above). <<<
> It was the only remaining handoff component, so Fever Watch is now feature-complete on staging. The module runs on a
> deterministic per-city MOCK derived from the city's real scores; to make the "last year" line REAL, drop in a
> `data/history.json` (format `docs/lab_feed_historic_format.md`) and replace the series generators
> (`build_site.py _trend_series` + `assets/js/trend.js metricSeries`). Full design intent: `docs/season-trend-module-brief.md`.
> The remaining work is now only the pre-launch items (wire the real lab feed, coords QA, production base_url,
> compliance/counsel pass, 3-signal backtest) - see section 7.
>
> **2026-06-08 (performance + share-chrome + seamless-first-paint pass; ALL LIVE + PSI-audited):** big perf/UX
> pass, deployed. Live PSI headline: **mobile 67-89 -> 97-99, CLS 0.95 -> 0, FCP 2.7s -> ~1.1s, best-practices 100**;
> **OG cards 700KB PNG -> ~55KB JPEG**. Commits: `a77bc73` (share chrome + Inter + logging), `dd7c691` (cache-bust),
> `564f2fc` (logging dictionary/confidence), `e224d98` (OG JPEG + fonts), `5e6748f` (inline seed - had the bug below),
> `135afe6` (seed-boot fix + mobile SSR card + JS preload), `83f8cd5` (desktop revert). What changed:
> - **CRITICAL bug fixed (`135afe6`):** the inline-seed boot was **silently throwing** - it ran near the top of each
>   flow's IIFE, BEFORE the `FAQ`/`METHOD` globals are assigned at the bottom, so `render()` did `FAQ.map` on undefined;
>   the `catch` swallowed it and the async grid-boot masked it. Net: **the seed never rendered on either flow** ->
>   both waited for the 850KB grid -> the plain fallback lingered (this was the real cause). Fix: invoke `boot()` at the
>   END of each IIFE (after FAQ/METHOD); boot failures now `console.error` instead of being swallowed.
> - **Mobile first paint IS the design (seamless, no flash):** `build_site.py` server-renders the real designed card
>   (hero + gauge SVG + pills) **byte-identical** to the JS `riskCard` via shared classes, media-gated `.fw-pre-m`
>   (helpers `_gauge_svg`/`_risk_card`/`_mobile_pre`). Hydration is a no-op repaint over identical DOM (verified
>   `1692==1692`). The old boot-time fallback-hide + 6s failsafe were removed; the header ticker is baked server-side
>   (`ticker_html`).
> - **Inline per-city seed** (`window.FW.seed` = the city's blend + its 5 cells + diseases + bands, ~3.5KB) so the flow
>   renders without waiting for the 850KB grid; the full grid loads in the background only for the leaderboard.
> - **Self-hosted Inter** (5 latin woff2 in `assets/fonts/` + `@font-face` in `prototypes/tokens.css`, replacing the
>   render-blocking Google Fonts `@import`; SSG preloads 600/700) -> FCP 2.7s -> ~1.1s. Plus `Inter-Variable.ttf` drives
>   the Pillow OG card weights. **The "self-host Inter" pending item is now DONE.**
> - **OG + share/download cards -> JPEG q82** (`build_og.py` + `share.js` canvas), `og:image:type` set. ~92% smaller.
> - **Cache-busting:** every CSS/JS URL carries a content-hash `?v=` (`asset_version()` + `window.FW.ver`; `fw-loader`
>   appends it) so returning users get new releases. Grid is `cache:no-store`. The HTML itself is still bound by GitHub
>   Pages' ~10-min `max-age` (no header control on Pages) - the production reverse-proxy should set HTML `no-cache`.
> - **Granular Sheets logging is now LIVE + verified:** Apps Script redeployed, tabs cleared, `daily.yml` re-run ->
>   **1,368 rows** pushed (228 x [5 diseases + 1 OVERALL]). `raw_data` = 22 cols (A-R raw inputs incl. temp/humidity/
>   rain, signal sub-scores, trends keywords, weights; S-V confidence/score/band/mode by in-sheet FORMULA) + a per-city
>   `OVERALL` blend row + a new `data_dictionary` tab. See `docs/sheets_logging.md`.
>
> ### >>> RESOLVED (this session): desktop seamless first paint <<<
> **Done + verified.** `build_site.py` now server-renders the desktop shell: `_desktop_pre` emits `searchHero` (`.srch`)
> + `.shell{.toc + .main{ _week_section(.grid2{ gauge card + _heatmap_card }) }}` byte-identical to what `desktop.js`
> `render()` paints from the inlined seed (new helpers `_search_hero_d` / `_week_section` / `_heatmap_card` / `_beacon`,
> reusing `_gauge_svg` at size 112; new `SIGCOL` / `SIGNAME` constants). It is media-gated `.fw-pre-d` (shown on desktop;
> `mobile.css` now hides `.fw-pre-d`; the old centered `.fw-pre-d-plain` fallback is gone). Hydration is now a no-op
> repaint, so the **desktop CLS 0.79 -> 0** (0 shifts), verified headlessly at 1300px; the SSR `.srch` / `.toc` /
> `#s-week` are byte-identical to the live post-hydration DOM (799==799, 282==282, 4275==4275). Mobile re-verified:
> still CLS 0, `.fw-pre-d` correctly hidden, mobile card intact. Both flows now paint the real design as first paint.
>
> ### >>> Also fixed (this session): two UI bugs (commit `2b4efa1`) <<<
> - **Desktop combo-input outline:** the `.combopanel` (`overflow:hidden`) clipped the focused `#cityinput`'s default
>   focus outline into a partial dark border. Now `.combopanel input:focus` is `outline:none` + an on-brand green
>   underline (`assets/css/desktop.css`).
> - **Mobile sheet scroll-flash:** the city/share `.sheet` was hidden only by `transform:translateY(100%)` while still
>   paintable, so the first scroll (mobile address-bar collapse resizes the viewport, recomputing the transform) flashed
>   it briefly at the bottom. Now `visibility:hidden` when closed (instant toggle; transition kept on `transform` only)
>   so the closed sheet cannot paint (`assets/css/mobile.css`). Trade-off: the sheet now closes instantly (no slide-out),
>   which matches the already-instant scrim; restore the slide-out with a `transitionend` -> `visibility:hidden` hook if wanted.
>
> **2026-06-06 (signals live):** Google Trends is now REAL and AUTOMATED. The 5 SerpApi keys are in
> GitHub Actions secrets (verified `5/5` in CI), and `.github/workflows/daily.yml` runs the full pipeline
> DAILY (01:30 UTC) - weather (NASA POWER) + real trends (SerpApi) -> grid -> commit data back -> SSG ->
> deploy. Live `grid.json` shows `trends_provider: cached`. Only **lab positivity** remains mock (needs the
> PharmEasy Sheet CSV URL). `gh` CLI is installed + authenticated (account `pharmeasyMarketing`) so workflows
> can be dispatched/watched from the CLI (push-trigger was flaky; dispatch via `gh workflow run` is reliable).
>
> **2026-06-07:** coverage extended to **228 cities** (live); a per-band **risk beacon** (pulsing alert light)
> added inline next to the band label on both score cards; card text overflow fixed (long city+state). Google
> Sheets logging is **LIVE** (`src/sheetlog.py` + `daily.yml` -> Apps Script webhook, secrets set, verified
> 1,140 raw rows pushed): `run_log` + a `raw_data` tab whose `score`/`band`/`mode` are **in-sheet formulas**
> over the raw signals, + a `daily_summary` with date- and city-level scores by formula. See `docs/sheets_logging.md`.
>
> **2026-06-07 (share + cards + granular logging pass):** share-surface chrome added per the handoff - a live
> **city ticker under the header** (clickable cities, marquee, pauses on hover / touch-hold) on BOTH flows, a
> **desktop bottom-right share dock** (Share + copy link; no embed) and a **mobile floating share CTA bar**; all
> Share buttons unified to one design. **Cards + logo now use Inter** (bundled `assets/fonts/Inter-Variable.ttf`,
> driven via the variable weight axis in `build_og.py`; the share canvas waits for `fonts.ready`); the header
> "Fever Watch" lockup is now **live Inter text** (was an SVG `<img>`). The share/OG card **drops the state**
> (city only) to stop WhatsApp overflow; share text reads "Know more here". Desktop `.srch` tinted `#10847e0f`.
> JS leaderboards + tickers now emit real `<a href>` city links (SEO interlinking survives JS hydration).
> **Sheets `raw_data` is now fully granular** (cols A-S: raw weather temp/humidity/rain, signal sub-scores,
> trends keywords, weights, confidence) with `score`/`band`/`mode` (T-V) + a per-city **OVERALL** blend row,
> all by in-sheet formula. ACTION: re-deploy the Apps Script (`docs/sheets_logging.md`) and delete the old
> `raw_data` + `daily_summary` tabs once, to pick up the expanded columns.
>
> **2026-06-06 pass (staging-feedback fixes, all verified):** the SSG now pre-renders the FULL page
> content (not a stub) with a clean H1>H2>H3 heading hierarchy across the baked HTML and both JS flows;
> the OG + WhatsApp share cards were redesigned to the approved "glass card" look (textured teal,
> co-branded lockup, OVERALL score as the hero with the top disease named) and reconciled so the live
> canvas matches the Pillow OG card; the share logo is now a rasterized PNG (`assets/img/pe_logo-white.png`)
> so it never drops on Android; "Use my location" is wired on both flows; per-city H1; meta says "this
> week"; and `og:image` carries a `?v={generated_at}` cache-bust so previews refresh when scores do.
>
> Fever Watch is a sibling to **Mosquito Watch** (`../Monsoon Disease Project`) but architecturally the
> INVERSE: Mosquito Watch keeps its three layers separate and never blends them; Fever Watch blends
> three signals into one *decomposable* score. The repos are independent.

---

## 1. What this is

A consumer-facing, PharmEasy-branded web tool that gives **one daily risk score per city** for India's
top monsoon fevers, with the per-disease breakdown underneath. City-first: one page per city at
`/fever-watch/{city}`. **Top ~230 cities** (expandable).

- **Diseases (v1):** dengue (flagship), malaria, chikungunya, typhoid. (Viral fever dropped 2026-06-09 - no lab-positivity test exists for it.)
- **The score:** a confirmation-weighted ensemble of 3 signals -> a city headline blend + 5 disease scores.
- **Framing (non-negotiable):** a **risk indicator**, NOT a diagnosis or a case/mosquito count. Forecast-only
  cells are capped and can never show HIGH. No medical JSON-LD.

---

## 2. Status snapshot

| Area | Status | Verified |
|---|---|---|
| Data layer (configs, weather, consolidation engine, grid) | **DONE** | engine smoke-tested; grid now **912 cells** (228 x 4; viral fever dropped 2026-06-09) |
| City config (`scripts/gen_cities.py` -> **228 cities**) | **DONE** | grown 119 -> 228 (next ~109 incl. all missing state/UT capitals); coords ~0.05deg, **gazetteer QA pending** |
| Providers: serpapi (weekly) / googlesheet (daily) / cached, config-driven | **DONE** | googlesheet tested on sample; cached state->city verified; all compile |
| Geolocation module (`assets/js/geo.js`, BigDataCloud + freeipapi) | **DONE** | nearest-city snapping verified; "Use my location" now wired on BOTH flows (GPS->IP), verified switches city |
| Share-image export (`assets/js/share.js`) | **DONE (redesigned)** | canvas matches the OG card (textured teal + glass card + OVERALL score); PNG logo (reliable on Android); WhatsApp text starts "This Week:"; live render verified HIGH+MODERATE |
| Front-end design: 2 clickable prototypes (mobile + desktop) | **DONE (frozen)** | the locked design source; now extracted into the SSG runtime (`assets/`), so prototypes are reference-only |
| Co-branded nav lockup (`assets/img/fever-watch-lockup-white.svg`) | **DONE** | rendered both navs |
| **SSG `/fever-watch/{city}` pages (device-adaptive)** | **DONE (full pre-render)** | `build_site.py` -> 228 pages; bakes the ENTIRE page (hero, score, why-this-score table, full methodology, what-to-do, 228-city table, FAQ, reads) + clean H1>H2>H3 hierarchy. Section 9 (AS BUILT). |
| Device-adaptive runtime (`assets/css,js` + `fw-loader.js`) | **DONE (both flows seamless, CLS 0)** | first paint = the designed view on BOTH flows (mobile `.fw-pre-m` card; desktop `.fw-pre-d` shell = searchHero + sidebar TOC + gauge/heatmap), server-rendered byte-identical to the JS so hydration is a no-op repaint; verified headlessly CLS 0 on both (desktop was 0.79); renders instantly from `window.FW.seed` then loads the full grid in the background; no boot-hide; per-city H1 + H2/H3 + live FAQ verified both flows |
| Per-city OG score cards (`src/build_og.py`) | **DONE (redesigned)** | 228 cards 1200x630; glass-card design, OVERALL score, top disease named; `og:image` has a `?v={generated_at}` cache-bust so previews refresh when scores do |
| Brand assets (`src/build_assets.py`) | **DONE (placeholder)** | favicon/PWA/OG via Pillow; swap for final art before launch |
| **Pages deploy (`.github/workflows/deploy.yml`)** | **DONE - LIVE** | builds (build_assets + build_og + build_site) + publishes on push to master; staging (real trends + mock positivity), robots Disallow. CI installs `fonts-noto-color-emoji`; OG mosquito badge confirmed rendering on the deployed cards. |
| **Daily data cron (`.github/workflows/daily.yml`)** | **DONE - LIVE** | daily 01:30 UTC + workflow_dispatch: weather + real trends -> grid -> commit data back [skip ci] -> OG + SSG -> deploy. First run verified green (run 27069051641). |
| **Google Trends (SerpApi, 5 keys)** | **LIVE (real)** | 5 keys in Actions secrets (verified `5/5` in CI); `trends.provider=cached`; `build_trends.py` pulls real state-level interest daily. Fixed a `GEO_MAP_0` bug (GEO_MAP 400s on single query). ~10 searches/refresh; ~1,000+/mo headroom. |
| Lab positivity feed | **MOCK** | the last real feed; needs the PharmEasy Sheet published-CSV URL -> flip `positivity.provider=googlesheet` |
| Risk beacon (pulsing band light) | **DONE** | inline next to the band label, both flows; colour=band, speed=urgency; CSS in tokens.css; reduced-motion fallback; verified live |
| Google Sheets logging (`src/sheetlog.py`) | **LIVE (verified)** | webhook secrets set; a run pushed 1,140 raw rows OK. Logs sheet = `1Iz9nAf38...`. `raw_data` = raw inputs (A-I) + `score`/`band`/`mode` as **in-sheet formulas** (mirror consolidation.json); `daily_summary` = date x disease avg + daily avg/peak + **city overall blend** (0.75*peak+0.25*avg), all by formula. See `docs/sheets_logging.md` |
| Card text overflow (long city+state) | **DONE** | `build_og.py` shrink-to-fit + 2-line + ellipsis; verified Visakhapatnam / Thiruvananthapuram |
| **"This monsoon vs last year" trend module** | **DONE (mock series)** | `assets/js/trend.js` widget + `build_site.py _trend_*` SSR, above the FAQ on both flows; verdict + chip + tabs + inline-SVG chart + tooltip + collapse + desktop small-multiples; deterministic per-city mock from real scores. **Last-year is a STABLE per-city baseline** (`lyPeak` seed, band 64-95) so "last year peaked at X" never drifts; this-year's real score floats against it, so the chip/verdict stay dynamic. Python<->JS series **byte-identical** (Node parity); recomputes on city switch; **desktop CLS still 0**. Swap in `data/history.json` for the real last-year line. |

Everything runs on the **Python standard library** (no third-party deps). `requirements.txt` is essentially empty.

---

## 3. Architecture & stack

Serverless by design: scheduled scripts write static JSON, a static device-adaptive site reads it.

```
GitHub Actions (cron)                          [BUILT - daily.yml, LIVE]
  daily.yml : build_weather + build_trends(SerpApi x5) + build_daily -> grid.json ; commit data back ;
              build_og + build_site -> dist/ ; deploy   (daily 01:30 UTC + workflow_dispatch)
  (trends folded into daily.yml at a daily cadence; no separate weekly.yml)
       |
       v
data/*.json  (committed; weather.json, grid.json[, trends.json])
       |
       v
SSG: src/build_og.py (per-city OG cards) + src/build_site.py   [BUILT]
   -> dist/fever-watch/{city}/index.html per city (SEO baked + #fw-app) + landing + robots/sitemap/manifest
       |
       v
Static front end (device-adaptive): one URL serves the MOBILE flow or the DESKTOP flow, chosen at load
(media-gated CSS in <head> + fw-loader.js injects the active flow's JS). Reads grid.json for switching + leaderboard.
Hosting: GitHub Pages; production = pharmeasy.in subpath via reverse-proxy (mirrors Mosquito Watch).
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

**Config (`config/`):** `site.json` (SEO identity, single source for base_url), `cities.json` (228 cities, generated),
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

Extended in the 2026-06-05 UI pass (both flows unless noted), all verified headlessly:
- **PharmEasy global nav ported from Mosquito Watch:** Healthcare / Health Hub / Editorial Policy / Research and
  Insights with 11 real pharmeasy.in links; desktop = click dropdowns, mobile = hamburger accordion (`wireNav`). Logo
  links to pharmeasy.in; the Fever Watch lockup stays the brand mark.
- **Leaderboard ("other cities"):** an **Overall** tab (default, ranks by the city blend) before the per-disease tabs,
  a city search box, and pagination at 10/page (`leaderRow` / `leaderboardInner` / `pager` / partial `renderLeaderboard`).
- **"Why this score" ordering:** the mobile breakdown, the desktop heatmap and the headline pills now sort diseases by
  score, high to low (`orderedDiseases`).
- **Methodology placement:** desktop sidebar label is **"Scoring methodology"** and the section sits above "What to do";
  mobile shows "How we calculate this" above "Why this score".
- **Desktop footer** rebuilt to mirror pharmeasy.in/diagnostics (5 link columns + 33 links, social, payment chips,
  NABL/ISO trust strip, copyright + mission); the Fever Watch risk-indicator disclaimer is retained.
- **"Further reading from PharmEasy"** section (sidebar label **"Monsoon reads"**) ported from Mosquito Watch: 3 columns
  (Dengue / Malaria / Mosquito bites and monsoon health), 11 blog links, placed after the leaderboard.
- **Desktop TOC** is now a scroll-spy (active link tracks the section in view across `s-week|s-method|s-do|s-other|s-reads`,
  `wireScrollSpy`); "Other cities" renamed to **"City-level insights"**.
- **Robustness:** the `grid.json` fetch retries (`loadGrid`) so a transient load race cannot strand the page on
  "Failed to fetch".

**Front-end modules (wired into the SSG):** `assets/js/geo.js`, `assets/js/share.js`.

**Brand assets:** `assets/img/pe_logo-white.svg` (self-hosted), `assets/img/fever-watch-lockup-white.svg`, plus
`src/build_assets.py`-generated placeholders (favicon, PWA icons, og-fever-watch.png).

**SSG + device-adaptive runtime (BUILT, verified headlessly):** `src/build_site.py` (228 pages + robots/sitemap/
manifest), `src/build_og.py` (per-city OG cards), `src/build_assets.py` (brand placeholders), and the extracted
`assets/css/{mobile,desktop}.css` + `assets/js/{mobile,desktop}.js` + `assets/js/fw-loader.js`. Details in section 9.

---

## 6. What is MOCK / pending the user

- **Trends + lab signals are MOCK** (`signals/mock.py`) until the feeds are wired:
  - Lab: provide the Google Sheet **published-to-web CSV URL** -> set `config/signals.json` `positivity.googlesheet.csv_url`
    and `positivity.provider = "googlesheet"`. Format + sample: `docs/lab_feed_format.md`, `docs/lab_feed_sample.csv`.
  - Trends: add the **5 SerpApi keys** as Actions secrets (`SERPAPI_KEY`, `SERPAPI_KEY_2..5`); run `build_trends.py`
    weekly; set `trends.provider = "cached"`.
- **City coordinates** are ~0.05deg approximations - QA against an authoritative gazetteer before launch.
- **Fonts: DONE** - Inter is self-hosted (5 latin woff2 in `assets/fonts/` + `@font-face` in `prototypes/tokens.css`,
  SSG preloads 600/700). Frozen prototypes point at the now-self-hosted path; the Google Fonts `@import` is gone.
- Brand sign-off on the co-branded lockup; convert its "Fever Watch" text to outlines for pixel-perfect rendering.

---

## 7. Next up (prioritized)

The SSG + daily cron + real trends + Sheets logging are all **LIVE**. `.github/workflows/deploy.yml` rebuilds +
republishes on every push to `master`; `daily.yml` (01:30 UTC + `gh workflow run daily.yml`) refreshes data + deploys.
Remaining:

1. ~~**Desktop seamless first paint**~~ **DONE this session** (see the RESOLVED banner up top): `build_site.py` now
   server-renders the `.fw-pre-d` desktop shell (searchHero + sidebar TOC + `.grid2{gauge card + heatmap}`) byte-identical
   to `desktop.js`, so desktop hydration is a no-op repaint. Desktop **CLS 0.79 -> 0**, verified headlessly; mobile
   re-verified still CLS 0. This also lifts the CLS-dominated desktop perf score.
2. **Wire the real feeds** (lab Sheet CSV URL + 5 SerpApi keys as Actions secrets) and flip `config/signals.json`
   mock -> real (googlesheet / cached). Then the cron publishes real scores; drop the robots Disallow when ready to index.
3. **Production hosting:** set `config/site.json base_url` to the final pharmeasy.in route; ask PharmEasy infra for the
   reverse-proxy + apex robots allowance. (Staging stays on github.io; production is a one-line base_url change + rebuild.)
4. **Replace placeholder brand art** (favicon/OG/PWA icons), **coords QA, self-host Inter, compliance/counsel pass,
   3-signal backtest** before any public "early warning" claim.

---

## 8. How to run / build / test

```
# Data (from the project root)
python scripts/gen_cities.py            # regenerate config/cities.json (228 cities)
python src/build_weather.py             # NASA POWER -> data/weather.json   (daily; ~2 min for 228 cities)
python src/build_daily.py               # compose the grid (reads signals.json) -> data/grid.json
python src/build_trends.py              # WEEKLY: SerpApi -> data/trends.json (needs SERPAPI_KEY in env)
python src/consolidate.py               # smoke-test the ensemble engine

# Flip a signal live (no code change): edit config/signals.json
#   positivity.provider: "mock" -> "googlesheet"  (+ set googlesheet.csv_url)
#   trends.provider:     "mock" -> "cached"        (after a weekly build_trends run)

# Build the static site (after grid.json exists). Order matters: OG cards BEFORE pages.
python src/build_assets.py              # one-off: brand favicon/PWA/OG placeholders -> assets/img/
python src/build_og.py                  # each data refresh: per-city OG score cards -> assets/img/og/ (needs Pillow)
python src/build_site.py                # each data refresh: dist/fever-watch/ (pages + robots/sitemap/manifest)
SITE_ENV=production python src/build_site.py   # production canonical (default staging -> github.io/fever-watch/)

# Preview (.claude/launch.json "fever-watch" server runs http.server on :8137 from the repo root)
python -m http.server 8137
#   prototypes (FROZEN reference): http://localhost:8137/prototypes/mobile.html , /prototypes/desktop.html
#   the SSG:                       http://localhost:8137/dist/fever-watch/  and  /dist/fever-watch/bengaluru/
```

Note: the harness preview tool's screenshot capture occasionally wedges after edits; a `preview_stop` +
`preview_start` (fresh renderer) clears it. `preview_eval` keeps working even when screenshot hangs.

---

## 9. SSG - AS BUILT

`src/build_site.py` (stdlib) generates a self-contained `dist/fever-watch/`: 1 landing + 228 city pages, each
device-adaptive (one URL serves the mobile OR desktop flow, chosen at load), SEO baked for crawlers.
`SITE_ENV=staging|production`. Modeled on Mosquito Watch's `build_site.py`. As-built details (note the deviations
from the original spec, which is kept below for reference):

- **Output / paths:** `dist/fever-watch/` (gitignored); pages at the literal `/fever-watch/{city}/`. In-page paths are
  RELATIVE via a per-page depth prefix; `base_url` (config/site.json) is absolute ONLY in canonical/OG/JSON-LD/sitemap/
  robots. Staging canonicalizes to `staging_url` (github.io/fever-watch/), production to `base_url`. Swapping the
  production URL = one-line config edit + rebuild.
- **Device-adaptive, no FOUC:** both flow stylesheets are `media`-gated `<link>`s in `<head>` (matching one is
  render-blocking, the other idles), so first paint is styled. `assets/js/fw-loader.js` then injects ONLY the active
  flow's JS (`assets/js/{mobile,desktop}.js`) and sets `body.fw-{mode}`.
- **Baked then hydrate (FULL pre-render, 2026-06-06):** baked server-side = one unified `<header class="fw-nav">`, the
  PharmEasy `<footer>`, and the COMPLETE page inside `#fw-app` (`render_content` / `render_landing` in build_site.py):
  per-city `<h1>` "Live monsoon-fever risk for {City}, in one score.", lede + search, the score block, a "Why this score"
  signal table, the full "How we calculate this" methodology, "So, what should I do?", the **228-city table** (every city
  linked, great for crawl + internal links), "Common questions" (FAQ), and "Further reading". A tiny render-blocking boot
  script sets `<html class="js">` so the baked block (`.fw-fallback`) is hidden for JS users pre-paint (no flash); a 6s
  failsafe re-reveals it if hydration never sets `body.fw-hydrated` (no-JS / broken-JS safety). The flow JS REPLACES
  `#fw-app` on hydration (so no duplicate H1); nav/footer persist; sheets/scrim/popover created dynamically.
- **Heading hierarchy (2026-06-06):** one `<h1>` (hero), `<h2>` per section, `<h3>` per subsection (methodology parts,
  reads categories), footer columns `<h2>`. Applied to the baked HTML AND both JS flows (Google renders JS) AND
  `footer_html`. Verified: 1xH1, no skipped levels, 0xH4/H5; methodology heading moved out of its `<button>` (was invalid).
- **JSON-LD `@graph`:** Organization + WebSite + WebPage + Dataset (license CC0, NASA) + FAQPage per city; landing adds a
  non-medical WebApplication. NO medical types (verified).
- **`window.FW`** per page: `{city?, gridUrl, base, logo, canonicalBase}`. Picking a city / geo-detect updates the URL
  (history.pushState/replaceState, CITY_ROOT-relative, popstate-aware); share text appends `Know More here: {url}` using
  `canonicalBase + city` so links are the deployed URL even on localhost. CTA pinned to "Book a fever panel test".
- **Per-city OG + share card (redesigned 2026-06-06):** `src/build_og.py` (Pillow) renders `assets/img/og/{city}.png`
  (1200x630) from grid.json. Design = dark textured teal (gradient + rain + glow) + co-branded PharmEasy+Fever Watch
  lockup (rasterized `assets/img/pe_logo-white.png`) + OVERALL score hero + "X RISK" pill + a frosted glass card
  (Location pin row + Top-concern disease-emoji row). `render_card(ctx, story=True)` renders the 1080x1350 share variant;
  `assets/js/share.js` mirrors the SAME design on a `<canvas>` so the OG and the WhatsApp/Stories image are identical.
  Color emoji: Segoe UI Emoji locally, `fonts-noto-color-emoji` in CI (emoji_font tries strike sizes). Run BEFORE
  `build_site.py`. `assets/img/og/` is gitignored; `pe_logo-white.png` IS committed (CI needs it).
- **OG cache-bust:** `og:image` + `twitter:image` carry `?v={og_version(generated_at)}` (compact YYYYMMDDHHMMSS) so social
  platforms re-fetch the preview when scores are recomputed; JSON-LD `primaryImageOfPage` and the landing OG stay clean.
- **Colors reconciled:** `tokens.css --risk-*` now matches the JS `RISK` map = the locked brand ramp. (grid.json still
  carries the old consolidation.json band colors, unused by the front-end - regenerate or ignore.)

### The page contract (original spec, mostly as-built above)

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
  - carry over the 2026-06-05 additions: the PharmEasy nav + hamburger (`wireNav`), the rebuilt footer, the
    "Monsoon reads" section, the desktop TOC scroll-spy (`wireScrollSpy`), and the leaderboard Overall/search/pagination.
- The header nav + footer are identical on every page: emit them server-side from `build_site.py` as baked HTML so they
  are crawlable, and let the JS only wire behavior (dropdowns, hamburger, scroll-spy) rather than build the markup.
- **Reconcile the risk colours into one source of truth.** Three ramps currently disagree: `consolidation.json` bands
  (baked into `grid.json`), `tokens.css` `--risk-*`, and the per-prototype JS `RISK` map (which is what actually renders
  today). Pick one and have the baked HTML fallback, the JS app and the tokens all read it.

### Also generate
- A **landing page** at `/fever-watch/index.html`: the city search + geo (default to detected city, link to its page).
- `sitemap.xml` (all 228 city URLs + landing), `robots.txt` (Disallow-all on staging via `SITE_ENV`, like Mosquito
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
config/   site cities(228) diseases(5) scoring consolidation signals
data/     weather.json  grid.json        (trends.json appears after a weekly build_trends run)
scripts/  gen_cities.py                  one-off city-config generator
src/
  build_weather.py  build_daily.py  build_trends.py  consolidate.py  weather_score.py  httputil.py
  build_site.py     SSG -> dist/fever-watch/ (228 pages + robots/sitemap/manifest), stdlib
  build_og.py       per-city OG cards -> assets/img/og/{city}.jpg (Pillow, JPEG q82 ~55KB, Inter via bundled TTF)
  sheetlog.py       best-effort Google Sheet logger (run_log + raw_data via Apps Script webhook; stdlib)
  build_assets.py   placeholder favicon/PWA/OG -> assets/img/ (Pillow, stdlib fallback)
  providers/        weather: nasa_power(DEFAULT), open_meteo(alt), base, __init__(registry)
  signals/          base, mock(default), googlesheet, serpapi, cached, __init__(registry, config-driven)
prototypes/         mobile.html  desktop.html  tokens.css   <- FROZEN design reference (extracted into assets/)
assets/
  css/  mobile.css  desktop.css          <- extracted from prototypes (tokens.css copied from prototypes/ at build time)
  js/   geo.js  share.js  faq.js  trend.js  fw-loader.js  mobile.js  desktop.js   <- the device-adaptive runtime (boot() at the END of each IIFE)
        faq.js = client FAQ recompute (mirrors build_site faq_items); trend.js = "this monsoon vs last year" widget (mirrors build_site _trend_series)
  fonts/ Inter-Variable.ttf (Pillow OG card, weight axis) + inter-latin-{400,500,600,700,800}-normal.woff2 (self-hosted web; COMMITTED)
  img/  pe_logo-white.svg  pe_logo-white.png (rasterized, used by share.js canvas + build_og.py; COMMITTED)
        fever-watch-lockup-white.svg  favicon.* icon-*.png og-fever-watch.png  og/{city}.jpg (generated JPEG, gitignored)
dist/   fever-watch/...                  GENERATED SSG output (gitignored)
docs/   lab_feed_format.md  lab_feed_sample.csv  sheets_logging.md  PROJECT_STATE.md
index.html                              LEGACY: the early 8-city vanilla-JS port; superseded by the SSG. Safe to delete.
```

---

## 13. Pending user/account actions

- [ ] Provide the PharmEasy lab **Google Sheet published-CSV URL** -> `config/signals.json` + provider `googlesheet`.
- [x] ~~**Sheets logging:** deploy the Apps Script + add secrets~~ **DONE + LIVE, now GRANULAR** (logs sheet `1Iz9nAf38...`).
  2026-06-08: Apps Script redeployed + tabs cleared + `daily.yml` re-run -> `raw_data` is the 22-col format (A-R raw
  inputs incl. temp/humidity/rain + signal sub-scores + trends keywords + weights; S-V confidence/score/band/mode by
  formula) + per-city `OVERALL` rows + a `data_dictionary` tab; **1,368 rows** verified. If you change `Code.gs`,
  re-deploy a **new version** and delete `raw_data` + `daily_summary` first to recreate them (see `docs/sheets_logging.md`).
- [x] ~~Add the **5 SerpApi keys** as Actions secrets~~ **DONE + LIVE**: keys set, verified `5/5` in CI; `trends.provider=cached`;
  `daily.yml` pulls real trends daily. (Keys are shared with Mosquito Watch; combined free pool ~1,250 searches/mo.)
- [x] ~~Create the public repo + enable GitHub Pages~~ **DONE + LIVE**: `pharmeasyMarketing/fever-watch`, Pages Source =
  GitHub Actions, `github-pages` env opened to allow `master`. Staging: https://pharmeasymarketing.github.io/fever-watch/
  Production `base_url` still TBD (staging auto-canonicalises to the github.io URL).
- [ ] PharmEasy infra: `/research/fever-watch-.../` reverse-proxy route + apex robots allowance.
- [ ] Brand sign-off on the co-branded lockup; provide the exact lockup asset if the rebuilt SVG is not pixel-perfect.
- [ ] QA the **228** city coordinates against a gazetteer (the ~109 added 2026-06-07 are approximations).

---

## 14. Session housekeeping (done at handoff)

- **2026-06-06 session (staging-feedback fixes, committed + pushed to master):** full-content SSG + H1>H2>H3 heading
  hierarchy; redesigned OG + WhatsApp share cards (glass-card look, OVERALL score, top disease named) with the live
  canvas reconciled to the Pillow OG; rasterized PNG logo (`assets/img/pe_logo-white.png`, committed); "Use my location"
  wired on both flows; per-city H1; "Common questions" FAQ in the live view; meta "today"->"this week"; `og:image`
  `?v` cache-bust; WhatsApp text starts "This Week:"; `deploy.yml` now installs `fonts-noto-color-emoji`. All verified
  (see the per-area notes); the push triggers a fresh Pages deploy.
- Git: **committed + pushed + LIVE.** Remote `origin` = `https://github.com/pharmeasyMarketing/fever-watch.git`, branch
  `master`. The original SSG + UI + batch work landed in commit `13e381d`. `.github/workflows/deploy.yml` auto-builds
  (build_assets + build_og + build_site, from the COMMITTED mock `grid.json`) and deploys `dist/fever-watch/` to Pages on
  every push to `master`. `dist/` and `assets/img/og/` stay gitignored (regenerated in CI). **To redeploy: just push to master.**
- **Deploy gotchas (resolved; noted so they are not re-hit):** Pages Source must be "GitHub Actions"; and the
  auto-created `github-pages` environment blocked `master` until its deployment-branch policy was opened (Settings >
  Environments > github-pages > "No restriction"). Live pages were fetched + verified 200 (landing, city, OG, grid.json).
- `.claude/launch.json` runs `http.server` on :8137 from the repo root (serves both `prototypes/` and `dist/`).
- `data/grid.json` is in its **mock** state (trends + positivity = mock); no `trends.json` committed.
- Verification (2026-06-06): real-browser via a **robust local server on :8139** (the default :8137 preview server
  reset the 436KB `grid.json` fetch under concurrent instrumented loads - a local-only flake, fine on Pages; the harness
  screenshot tool was also wedged). Confirmed: both flows hydrate with no flash, clean heading outlines, "Use my
  location" switches city, the live canvas share image matches the design (HIGH + MODERATE), in-app preview + WhatsApp
  text use the OVERALL score, zero console errors. OG/share cards were eyeballed as rendered PNGs.
- **Still worth doing:** a real-device WhatsApp/Instagram share test (caption-drop behaviour, image fidelity), and a
  glance at the first deployed OG card to confirm the Linux/CI mosquito emoji rendered (Noto Color Emoji).
```
