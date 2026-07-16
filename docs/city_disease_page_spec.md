# City x Disease Pages - Build Spec (SEO Phase 1)

> Created 2026-07-11. The flagship of `docs/seo_growth_plan.md` Phase 1: 209 cities x 4 diseases =
> **836 new pages** at `/fever-watch/{city}/{disease}/`. Forecast: the single biggest traffic line
> (base ~10.5k clicks/mo in-season at maturity). This spec covers content modules, SEO surface,
> engineering plan, data prerequisites, states, guardrails, and rollout. Design brief at the end.
>
> **DESIGN REVIEWED 2026-07-11 (v2, "Fever Watch Disease Page v2.dc.html", 4 frames; local reference
> copy: the session scratchpad `design_v2_fixed.html`).** Reviewed end-to-end by the lead + an
> independent reviewer against this spec, CLAUDE.md guardrails, and production source. Verdict:
> **BUILD-READY WITH ADAPTATIONS** - no re-layout needed; ~80% of the design's components verified
> as REUSE of existing production machinery (ticker, leaderboard incl. bars/pinned-row/pager/search,
> share dock, reads module, method sheet, trend widget, nearest-cities, season sentence). Design
> fidelity to production tokens/copy/math was verified byte-level (band ladder, 30/22/48 + 60/40
> weights, forecast soft-knee taper held below 69 (soft_knee 55, was a hard cap 69 pre-2026-07-15),
> agree nudge 1.08, signal/disease hexes, contribution sums reconcile).
> Gating fixes before/при build (full findings in the review record): footer must be the legal-verbatim
> `footer_html()` (design drew a paraphrase - never hand-type it); no risk-band zones behind SIGNAL
> tab lines in the trend chart (per-signal glow, as production trend.js); the 2d Labs empty-state
> copy must not tie chart history to the 69 cap (split the two ideas; cap sentence only when the
> cell is truly forecast-only); swap all product-copy middots ("Live - Dengue"; Labs tab stays plain
> "Labs"); "this week" regression in one FAQ -> "today"; search cadence is DAILY in the
> when-does-it-change FAQ; dock copy band-tier fix; mobile keeps the Chikungunya leaderboard chip +
> the Further-reading module; leaderboard rows become real same-disease links + "see all cities"
> hub link; nearby chips get band words (a11y); amber early-estimate lead darkened to ~#96520F (AA);
> reduced-motion fallbacks for marquee/pulses; rank strip dated on mobile too; full "LOW-MODERATE"
> band labels + existing RISK_SOFT tokens; sibling rows = real anchors; "Google search interest"
> casing; sources line = "Google Trends (via SerpApi), PharmEasy Labs and its Partner Affiliates".
> DECISIONS RECORDED: (1) "Early estimate" vs "Forecast only" terminology - one term everywhere,
> needs product + counsel sign-off, then a full sweep (method/faq/TIPINFO/engine notes/hub) - do
> not ship both; (2) H1 = "{Disease} risk in {City} today, in one score." (keeps the designed
> em-styling, restores the exact-match + "today"); (3) per-signal "rising" badges stay HIDDEN in v1
> (consistency with the product-wide hide); (4) the "+31% vs last year" chip ships only after the
> archive v1.1 window fix (3-week centered mean, not single-week endpoint); (5) the gated
> fever-tests row needs a one-disease design variant before the FW_TESTS flags flip. The
> counsel bundle (17 copy items incl. About-{disease} texts, band-adaptive HIGH actions, early/lab
> chips, new FAQ answers) is recorded in the review output and goes with the ~2026-07-15 review.

---

## 0. Build status + locked decisions (2026-07-11)

The flagship build (~8-12 sessions). **W1 + W2a + W2b DONE + verified; W2c/W3 pending. Everything is LOCAL and
uncommitted** - carry forward: `src/build_archive.py`, the regenerated `data/archive/trend_series.json`,
`src/build_site.py` (W2a), `assets/js/{mobile,desktop,faq,trend}.js` + `scripts/parity_check.js` +
`prototypes/tokens.css` (W2b), and this spec.

**W2b (DONE, verified end-to-end in a browser) - the JS `FW.disease` mode.** `mobile.js`/`desktop.js` branch to
`renderDisease()`; the above-fold hero is byte-identical to the W2a SSR (`diseaseCard`/`diseaseRing`/
`diseaseBreakdown`/`diseaseWeatherCard`, + `searchHeroDisease`/`diseaseToc` desktop). `faq.js buildDisease`/
`forCityDisease` mirror `faq_items_disease` (render-diff 30/30 byte-identical vs the SSR FAQPage JSON-LD).
`trend.js` disease mode remaps `byDisease`/`byFamily`/`states` into `build()`'s shape (dial-consistent).
`scripts/parity_check.js` now runs **4 fixtures** (hub + disease x mobile + desktop) - ALL GREEN. City switch stays
in-vertical (`CITY_ROOT`/`cityHref` disease-aware -> `/{new-city}/{disease}/` pushState + re-render; verified
live). Fixed a `CITY_ROOT` bug (strip trailing `index.html` first). New dormant CSS in `tokens.css`. **The gate is
now env-overridable** (`FW_DISEASE_PAGES=1` builds the 1,046-page set for local review; default OFF ships nothing).

**W2a (DONE, verified) - `build_site.py` disease-page SSR template.** All 836 `/{city}/{disease}/` pages render
server-side. Hub (`disease=None`) code path is byte-identical (parity green). Disease-page emission + hub
switcher row + sitemap children are GATED behind `FW_DISEASE_PAGES_ENABLED` (default `False`, `FW_TESTS`-style):
OFF = 210 pages / byte-identical hub; ON = 1,046 pages / sitemap 1,046 (both verified). The per-disease season
trend reuses the hub trend math via `_disease_archive_view()` (remaps the v1.1 `byDisease`/`byFamily`/`states`
slices into `{overall,weather,search,labs}`), verified dial-consistent (`byDisease.score.ty[-1]` == the live
cell). SEO surface verified: exact-match dated title, number-rich dated meta with vs-yesterday, locked H1,
WebPage + 4-item BreadcrumbList + disease Dataset + FAQPage(6) (no medical schema), self-canonical, CITY og card
reused, Lab-confirmed/Early-estimate chip correct per mode, mosquito/waterborne mechanism line, guardrails clean.
The seed inlines `FW.disease` + city cell + rank + this city's archive slice (incl. its state search line) for
W2b. About-{disease} copy is net-new/non-diagnostic and still needs the ~2026-07-15 counsel pass. **The gate MUST
stay `False` until W2b ships the JS `FW.disease` first paint** (else JS users repaint the hub over the child SSR).

**W1 (DONE, verified) - archive v1.1** (`src/build_archive.py`): the per-disease season data the disease
pages render, all COUNTS-FREE and dial-consistent. New archive keys are ADDITIVE - the legacy
`weather/search/labs/overall` city blocks the hub reads are PRESERVED byte-for-byte, so the existing site
is untouched:
- `cities.{id}.byDisease.{disease}.score.{ly,ty}` - that disease's own dial line, `consolidate()`'d per
  week exactly like the overall; **`ty[-1]` == the live dial** (verified 4/4 on Kolkata: 42/74/60/45).
- `cities.{id}.byDisease.{disease}.labs.{ly,ty}` - REAL 2025 lab line ONLY where 2025 history exists
  (24 cities); ABSENT otherwise, so that disease's Labs tab keeps the honest "coming soon".
- `cities.{id}.byFamily.{mosquito,waterborne}.{ly,ty}` - per-family weather (the 3 mosquito diseases
  share one line; typhoid the other).
- `states.{state}.{disease}.{ly,ty}` - EXACT per-disease search, keyed by state (27 states; both years on
  one Google normalisation). Search is state-resolution, so ~30 blocks serve all 209 cities.
- Maintained by the EXTENDED CI modes: `--daily` upserts byFamily/byDisease.score/byDisease.labs ty from
  the live grid + length-pads the state search ty; `--search-only` recomputes the EXACT state search
  weekly. Built one-off via `--history` (reads the gitignored backfills weather_{2025,2026}.json +
  trends_history.json + lab_feed_2025_historic.csv). **The enriched `data/archive/trend_series.json` is a
  COMMIT artifact** - it carries the 2025 `ly` history that `--daily` cannot regenerate, exactly like the
  Phase-0 archive. Verified: 14/14 invariants; the existing 210-page build stays clean with full parity +
  51/51 Phase-0 checks (ZERO regression). Window fix (F21, 3-week centered mean) is NOT yet applied - do
  it before the "+31%" chip ships.

**DECISIONS LOCKED (user, 2026-07-11):**
1. **"early estimate" replaces "Forecast only" EVERYWHERE** (full sweep = method.js, faq builders, TIPINFO,
   `consolidate.py` engine notes + the in-place grid.json patch, hub + new pages). One term, byte-identical
   twins. (= W2c.)
2. **H1 template = `{Disease} risk in {City} today, in one score.`** (keeps the designed gold "one score"
   em; restores the exact-match query + "today").
3. **"What you can do" = REPLICATE the existing live hub section AS IS** (the current `ACTIONS` list + the
   personalized "Book a fever panel test in {City}" CTA), NOT the design's band-adaptive variant. This
   DROPS the band-adaptive HIGH actions (and their counsel-bundle items) for v1.
4. **"About {disease}" = short reviewed blurb + a "Read the full guide" link** to these exact blog URLs:
   - dengue -> `https://pharmeasy.in/blog/5-ways-to-avoid-dengue-fever/`
   - malaria -> `https://pharmeasy.in/blog/types-of-malaria-symptoms-causes-and-treatment/`
   - typhoid -> `https://pharmeasy.in/blog/typhoid-causes-symptoms-and-treatment/`
   - chikungunya -> `https://pharmeasy.in/blog/vaccine-viral-fever-causes-symptoms-and-treatment-options/`
5. (from the review) per-signal "rising" badges stay HIDDEN in v1; the "+31% vs last year" chip ships only
   after the archive window fix; the gated fever-tests row still waits on a one-disease design variant + the
   FW_TESTS flag flip (unchanged from Phase 0).

**REMAINING:** ~~W2a~~ (DONE), ~~W2b~~ (DONE, see above), W2c (the early-estimate sweep, needs product+counsel
sign-off), W3 (trend render-diff + independent QA + broader JSON-LD/meta + guardrail sweep across the 836 +
Lighthouse seed-weight spot-check). Then, once counsel clears the About-{disease} copy + the early-estimate
terminology, flip `FW_DISEASE_PAGES_ENABLED` (or set the deploy env). The remaining design-review polish items
(per-signal glow not band zones on trend SIGNAL tabs, band words on nearby chips, reduced-motion fallbacks, etc.)
are still open and can land alongside W3.

---

## 1. Why these pages win (one paragraph of grounding)

The dominant query pattern in both GSC and the 62-domain SEMrush crunch is disease+city
("dengue mumbai", "kolkata dengue", "dengue fever in bangalore" 5.4k vol KD 18, "dengue cases in
kolkata 2026"). Today those SERPs are won by static hospital brochures (Practo/Manipal/Max local
pages) with zero live data. We have a daily per-city per-disease score, its decomposition, season
history, lab ground truth, and a booking funnel. One page per city x disease, each with genuinely
unique daily data, out-relevances a brochure. Chikungunya is nearly unowned among tracked domains.

## 2. URL, information architecture, internal linking

- **URL:** `/fever-watch/{city}/{disease}/` - children of the city hub. Slugs: `dengue`, `malaria`,
  `chikungunya`, `typhoid` (= disease ids already in config).
- **City hub keeps its role** (overall blend, all 4 diseases) and gains a **disease switcher row**
  linking its 4 children. Disease pages link: up to the hub, across to 3 siblings, out to
  same-disease nearby cities, and to the disease's blog explainer (lane discipline: blog owns
  national evergreen "what is dengue"; we own local + temporal + decision).
- **Breadcrumb:** PharmEasy > Fever Watch > {City} > {Disease} (4-item BreadcrumbList JSON-LD).
- **Sitemap:** 210 -> 1,046 URLs, all daily-lastmod. Canonicals self-referencing. City hub is NOT
  canonicalized over children (different intent, different content).
- **Keyword lanes (anti-cannibalization):** hub = "{city} fever / monsoon {city}"; child =
  "{disease} {city}", "{disease} in {city} today/now/2026", "{disease} test {city}" (when the tests
  block unlocks); blog = evergreen national. FAQ phrasing differs hub vs child accordingly.

## 3. Content modules (the page, top to bottom)

Ordered for mobile; desktop = same modules in the 3-col shell with the Quick Links rail.

| # | Module | Content (all live data) | New or reuse |
|---|--------|--------------------------|--------------|
| 1 | **Disease hero dial** | THAT disease's score/100 + band + vs-yesterday delta; meaning line: "Right now {city}'s {disease} score is {n}/100, {band phrase}. A daily look at local risk, not who's actually sick."; confidence chip: **Lab-confirmed** vs **Forecast only (capped below HIGH)**; Updated {date} + reviewer byline | Reuse dial primitives, disease-scoped |
| 2 | **Rank strip** | "{City} ranks #{r} of 209 for {disease} today" + "{disease} is {city}'s #{k} concern of 4" - two one-line facts, AI-quotable | New (tiny) |
| 3 | **Why this score** | The 3-signal contribution breakdown for THIS disease cell (weights, level pills, whyChip driver line, popovers) - pre-expanded, no accordion of other diseases | Reuse `contribs()` machinery |
| 4 | **Weather drivers** | The 3 weather tiles + a disease-mechanism line: mosquito family = "Aedes/Anopheles breed near 29C in standing water"; typhoid = "rain washes contamination into water supplies". Dated sub | Reuse card + per-family line |
| 5 | **Season trend (per-disease)** | "This monsoon vs last" chart for THIS disease: search line (real per-disease), labs line (real per-disease where covered), weather line (family-level, labeled honestly); + the season-compare sentence scoped to the disease | **Needs archive v1.1** (sec 5) |
| 6 | **What you can do** | Disease-specific action cards (dengue/chik: standing water + repellent + peak-bite hours; malaria: nets + dusk; typhoid: safe water + food hygiene + vaccine mention) + consult CTA + **"Book a fever panel test in {City}"** diag CTA | New curated 4-list, same card pattern |
| 7 | **Fever test row (GATED)** | THIS disease's confirming test + when-to-test tied to THIS disease's band. Ships when `FW_TESTS_*` flags flip after the medical review; disease pages are its best home | Built, gated |
| 8 | **Nearby cities for {disease}** | Nearest-5 chips showing THAT disease's scores + band dots; links to the same disease page of the neighbour (crawl mesh within the disease vertical) | Reuse `_nearest_cities`, disease-scored |
| 9 | **{Disease} leaderboard** | Top-10 cities for this disease today + this city's row pinned; link "see all cities" -> hub leaderboard pre-tabbed | Reuse leaderboard, pre-filtered |
| 10 | **About {disease} (short)** | 2-3 doctor-reviewed sentences (what it is, how it spreads, typical season) + "Read the full guide" -> blog post. Deep enough for topical relevance, shallow enough to not fight the blog | New static per-disease copy (compliance pass with the tests copy) |
| 11 | **FAQ (6-8 per disease x city)** | Templated from live data: "Is {disease} rising in {city}?" (search + trend framing, no case counts), "What is {city}'s {disease} risk today?", "Is it {disease} season?", "How does {city} compare for {disease}?", "How is this calculated?", "(gated) Which test confirms {disease}?" | Extend faq machinery, disease variants |
| 12 | **Methodology accordion** | Existing method sheet with the worked example locked to THIS disease's cell | Reuse method.js |
| 13 | **Footer/disclaimer/nav** | Unchanged (legal verbatim) | Reuse |

**AI-citability rule (carries over from Phase 0):** every module leads with one dated, quotable
sentence containing the number and the city+disease names.

## 4. SEO surface per page

- **Title:** `{Disease} in {City}: Risk Score Today, {DD Mon YYYY} | Fever Watch by PharmEasy`
  - Front-loads the exact query ("dengue in kolkata"); date re-stamps daily. Deliberately NO raw
    score in the title (band/score churn = title churn; the meta carries numbers).
- **Meta description:** `{Disease} risk in {City} today, {date}: {n}/100 ({BAND}), {up|down|steady}
  vs yesterday. Signals: weather {w}, search {s}, labs {l or "no data yet"}. A risk indicator, not
  a diagnosis.` (~150-165 chars, number-rich, driver-free since the page IS the driver.)
- **H1:** `{Disease} risk in {City} today`.
- **JSON-LD @graph:** WebPage (reviewedBy Persons, breadcrumb ref) + 4-item BreadcrumbList +
  Dataset (disease-scoped: `variableMeasured` = that disease + its 3 signals; same isBasedOn /
  measurementTechnique / temporalCoverage) + FAQPage. **No medical schema types** (guardrail; the
  disease name appears as plain WebPage.about strings, same as today).
- **OG/share:** v1 reuses the CITY og card (alt text disease-scoped). Per-disease cards deferred -
  836 extra renders would ~4x the share-card build; revisit if disease pages earn social traction.
- **Uniqueness defense (thin-content):** the differentiators per sibling page are the score set,
  contribution mix, season lines, rank strip, nearby-with-disease-scores, disease FAQ answers with
  live numbers, per-family weather mechanism, per-disease actions + about copy. Template phrasing
  varies by disease family so sibling pages do not share running text beyond structure.

## 5. Data prerequisites (the two real gaps)

1. **Per-disease season archive (v1.1 of `build_archive.py`).** Today `trend_series.json` carries
   per-city `overall/weather/search/labs` only. Verified available inputs: per-disease per-state
   SEARCH series (`data/backfill/trends_history.json` has a `diseases` dimension), per-disease
   city-level LABS history (`lab_feed_2025_historic.csv`: city,disease,week rows + the live sheet),
   WEATHER at disease-family level (mosquito vs waterborne - label honestly, one line shared by the
   3 mosquito diseases). Extend the archive to `cities.{id}.byDisease.{disease}.{search|labs}.{ly,ty}`
   (+ family weather), keeping the minified single-writer convention. **Ship order decision:** v1
   pages can launch with the disease season module in its honest fallback (overall line + "disease
   split coming soon" caption) OR wait for v1.1. Recommendation: build archive v1.1 FIRST - the
   per-disease trend is a top-3 differentiator of the whole page.
2. **Vs-yesterday delta per disease cell.** `data/history.json` already tracks per-cell deltas for
   the legend triangles (currently hidden). Reuse it for the hero delta + meta "up/down vs
   yesterday" - verify coverage, no new pipeline.

## 6. Engineering plan (repo-shaped)

- **build_site.py:** `page()` + `render_content()` get a `disease` param (None = hub, unchanged
  output). New disease-scoped SSR: hero pre (parity twin), rank strip, breakdown, weather line,
  season section, actions, nearby, leaderboard, FAQ, JSON-LD, title/meta. City hub gains the
  switcher row. Sitemap emits 1,046 URLs. Build loop: `for city -> write hub + 4 children`.
- **JS flows (mobile.js / desktop.js):** a `FW.disease` page hint. Disease mode = hero dial bound
  to that cell; breakdown pre-expanded to it (no 4-disease accordion); leaderboard pre-tabbed;
  trend module opens on that disease's lines; nearby uses disease scores; actions/FAQ swap to the
  disease variants. City switcher keeps you inside the same disease vertical
  (`/{new-city}/{disease}/` pushState). Estimated as mode branches on existing renderers, not a
  third flow. **Parity:** extend `scripts/parity_check.js` with a disease-page fixture (hub fixture
  unchanged); the disease hero SSR pre must be byte-identical to the JS disease-mode first paint.
- **Seeds:** child pages inline their own cell + rank + archive slice (same pattern as hubs; ~same
  page weight).
- **faq.js / trend.js:** disease-variant builders, render-diff parity tests extended.
- **CI cost:** SSG string-templating; expect build minutes +3-4x for site step (fine); share-card
  step unchanged (v1 reuses city cards); Pages artifact grows ~5x page count (small files, fine).
- **Verification set (definition of done):** parity (hub + disease fixtures) - FAQ + trend
  render-diffs incl. disease variants - Py=JS facts script extended to disease pages - JSON-LD +
  meta sweep across a 20-page sample incl. edge cities - guardrail greps (dashes, "this week",
  case-count language) - full-build page-count + sitemap asserts - independent QA agent pass with
  screenshots - Lighthouse spot-check (page weight budget: seed < 25KB, no new blocking assets).

## 7. States the design + build must handle

1. **Lab-confirmed** cell (mode=confirmed): full dial, labs line present, "PharmEasy lab signals
   feed this score" chip.
2. **Forecast-only** cell (soft-knee taper, held below 69): honesty chip "Forecast only - held below
   HIGH until lab data confirms it" + eased-back dial treatment. This is 191/209 cities - the DEFAULT
   state, design for it first.
3. **News-spike** (dengue only, national flag): small "news interest is spiking nationally" note.
4. **No labs history** (185/209 cities): season module shows search (+family weather) lines, labs
   tab = "coming soon" (existing honest-ladder pattern).
5. **Missing archive slice:** season module omitted entirely (never fabricate).
6. **All-LOW city:** copy must not manufacture urgency (band phrases already handle).
7. **Tests block gated:** page must read complete without module 7 (and slot it in cleanly when
   the flags flip).

## 8. Guardrails (unchanged, enforced on every module)

Risk indicator, never diagnosis/case counts; forecast cap always labeled; score always
decomposable; positivity as aggregate trend only; no medical JSON-LD; ASCII hyphens; IST dates;
byte-identical twins wherever markup is shared; "About {disease}" + tests copy through
medical/counsel review (bundle with the ~2026-07-15 tests review); weather-temp is not body-temp.

## 9. Rollout

1. Archive v1.1 (per-disease lines) + delta verification.
2. Build behind `SITE_ENV`-agnostic completeness: ship all 836 in one build (SSG makes partial
   rollout pointless), but **internal links + sitemap emphasis on the top-50 cities**; staging
   review; then prod via the daily chain.
3. GSC: submit updated sitemap; monitor Coverage weekly; request-index top 50 x dengue.
4. Measure: GSC page-path regex per disease vertical; tracked set = {disease} x top-20 cities +
   GSC arrivals; target top-10 on 25+ terms in 6-8 weeks (per the growth plan).
5. Tests block flip (post-review) lands on hubs + children in one go.

## 10. Open decisions (need product/user call)

- Title formula final call (with/without score; current spec says without - churn control).
- Season v1.1 first vs launch with fallback (spec recommends v1.1 first).
- "About {disease}" copy source: net-new reviewed copy vs excerpt-of-blog (spec: net-new short,
  blog-linked; needs the same counsel pass).
- Per-disease OG cards: deferred (v1 reuses city card) - confirm.
- Hub "Why this score?" keeps all 4 accordions (yes per spec; children are the deep-dives).
