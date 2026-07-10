# Fever Watch - SEO Growth Plan & Traffic Forecast

> Created 2026-07-08. Built from the 62-domain SEMrush organic-positions crunch in
> `Downloads/Claude/SEO/` (Jul 2026 snapshot) + the first Google Search Console signal for
> `/fever-watch/`. Numbers are a planning MODEL, not a promise - see the assumptions in section 3.
> Companion to `CLAUDE.md` and `PROJECT_STATE.md`; all work here inherits the same guardrails.

---

## 1. The opportunity (what the data actually says)

- The **fever / monsoon-disease space in our tracked set = 1,201 keywords / ~5.7M monthly searches.**
  Mayo Clinic owns it (551 kws, 328 top-3), then Medscape, Apollo Hospitals, MedlinePlus, Metropolis,
  Max. **PharmEasy is #10 (77 kws, only 13 top-3) - and every ranking is a blog or diagnostics URL.
  Fever Watch has zero SEMrush-visible rankings today** (too new; expected).
- **94% of these SERPs carry an AI Overview**, 98% People-Also-Ask. The generic informational head
  ("dengue symptoms" 135k, KD 75) is CTR-compressed AND Mayo-owned - a losing fight head-on.
- **Fever Watch's defensible lane is local + temporal + test-intent** - exactly what it was built for:
  - **City-modified disease queries sit at KD 14-28**, owned by thin hospital local pages:
    `dengue fever in bangalore` 5.4k (Practo #6), `dengue fever in delhi` 1.6k, `viral fever in delhi`
    1k, `fever hospital hyderabad` 1.3k. Our GSC already shows this arriving: `dengue mumbai`,
    `kolkata dengue`, `dengue cases in kolkata 2026`, `fever in kerala now`.
  - **Test-intent is a large, soft, buying-intent hole**: `widal test` 90.5k KD 23, `dengue test`
    33.1k (PE absent), `typhoid test` 27.1k (PE #7 via blog), `dengue/typhoid test price` 6.6k each
    (PE absent; Lal PathLabs #1). The whole "test price by city" theme has **median KD 18** - the
    softest theme in the dataset.
  - **Chikungunya is nearly unowned** among tracked domains (`chikungunya symptoms` 27.1k).
- **The blog is unused authority.** PharmEasy's blog ranks **positions 4-10 on 61 fever terms = 386k
  combined volume** (`typhoid fever treatment` 135k at #10, `typhoid treatment` 90.5k at #8, a platelet
  cluster ~80k at #5-10). Fever Watch links to the blog; no blog post links back. Free, unused equity.

---

## 2. Traffic forecast (bottom-up, grounded in the parquet)

Incremental organic clicks Fever Watch can win. Honest scoping: **not** credited with Mayo's symptom
head or the diagnostics team's generic CBC terms.

**At maturity (~12-18 months), in-season monthly / annualized:**

| Scenario | In-season clicks/mo | Annualized |
|---|---:|---:|
| Conservative | ~12,600 | ~94,000 /yr |
| **Base** | **~24,300** | **~181,000 /yr** |
| Optimistic | ~43,700 | ~326,000 /yr |

**By initiative (in-season monthly, at maturity):**

| Initiative | Conserv. | Base | Optim. |
|---|---:|---:|---:|
| City x disease pages (core; + seasonal + nearby) | 5,200 | 10,500 | 17,500 |
| Test-info blocks - local long-tail (`dengue test {city}`) | 1,150 | 2,100 | 3,450 |
| Test-info blocks - head assist (`widal test`; shared w/ diagnostics) | 4,600 | 8,550 | 17,100 |
| State pages | 540 | 970 | 1,620 |
| National rankings + news feed | 930 | 1,860 | 3,350 |
| 2025-vs-2026 recap page | 200 | 400 | 720 |
| **Fever-Watch total** | **~12,600** | **~24,300** | **~43,700** |

- **City x disease is the biggest, surest line** (KD-14-28 lane owned by thin hospital brochures; our
  daily-data pages out-relevance them). The **~8.5k "head assist" row is shared credit** with the
  diagnostics PDPs - the Fever-Watch-purist base is **~16k/mo**.
- **Schema, breadcrumb, seasonal-uniqueness, nearby-cities do not get their own line** - they are
  *enablers* that raise the capture rate on everything above AND are **thin-content insurance** that
  keeps 200+ templated pages indexable.

**Ramp (base case):**

| | Month 3 | Month 6 | Month 12 | Maturity |
|---|---:|---:|---:|---:|
| in-season clicks/mo | ~4,900 | ~11,000 | ~19,500 | ~24,300 |

**Blog halo (separate credit):** the blog->Fever-Watch internal-link item can nudge the 61 blog fever
terms (386k vol) at pos 4-10 into the top-3 = **~19,000-31,000 clicks/mo** - the blog team's traffic,
but the same push delivers it, and it dwarfs the Fever-Watch-direct number.

### 3. Key assumptions & caveats (so it is defensible)
- Baked into the capture rates: **AI Overviews on 94% of SERPs** (discounted; our local/test/booking
  intent is far more AIO-resilient than the informational head), mobile CTR, competitor authority.
- **Seasonality is large.** Fever traffic is monsoon-weighted (Jun-Nov); Sep-Oct is the absolute peak.
  Annualized = ~5 in-season months at full + ~7 off-season at ~35%. A bad dengue year spikes the peak
  month 1.5-2x the in-season average.
- **New-section ramp:** even on aged pharmeasy.in, a new section takes 3-6 months to mature.
- **Indexation dependency:** the whole forecast assumes the pages get indexed - which is why the
  seasonal / test / FAQ blocks matter (they are what make templated pages index-worthy).
- **The monetizable slice is the test-intent clicks** feeding the per-city diagnostics deeplinks
  (already shipped). ~5-11k/mo (base, in-season) at booking intent - that is the ROI line; the
  city-page traffic is reach/brand. (Give me the diag landing->booking conversion rate and I will turn
  clicks into a booking/revenue forecast.)

---

## 4. Roadmap

### Phase 0 - Maximize the EXISTING pages (209 city pages + landing)
Everything that ships on the current URLs, no new page types. These pages are already live, so they
index and rank fastest, they front-load a meaningful share of the base case, AND they build the
content + schema patterns the Phase 1 templates will reuse. (Detailed, sequenced list below.)

> **STATUS 2026-07-08:** 0.1, 0.2, 0.3, 0.5, 0.6, 0.8 SHIPPED (independently QA'd, 0 blockers - see
> PROJECT_STATE 2026-07-08 banner). 0.4 BUILT but GATED off pending the medical/counsel review
> (~2026-07-15; flags FW_TESTS_ENABLED / FW_TESTS_ON). 0.7, 0.9, 0.10, 0.11 not started.

**0A. Crawler-facing (quick, contained, mostly `build_site.py`):**
- **0.1 BreadcrumbList JSON-LD** - Home > Fever Watch > {City}. Missing today; stabilizes the SERP
  breadcrumb display.
- **0.2 Dataset schema enrichment** - add `temporalCoverage` (2026-06-01/..), `isBasedOn` (NOAA CPC,
  NASA POWER, Google Trends via SerpApi, PharmEasy labs), `measurementTechnique`, per-disease
  `variableMeasured`. We already ship Dataset + spatialCoverage + license; this completes eligibility
  for **Google Dataset Search** - a discovery surface no competitor uses.
- **0.3 Dynamic driver-led meta description** - open with the live top disease + score + date per city
  (the deferred item). Stops Google discarding our description; front-loads the numbers.

**0B. On-page content blocks (new sections on the existing city template; template + JS twins + parity):**
- **0.4 Per-city test-info block** - which test confirms each fever (NS1/IgM dengue, Widal typhoid,
  smear/antigen malaria, CBC/platelet context), "when to consider testing" tied to the live band,
  wired to the per-city diagnostics deeplink. Targets the KD-18 test lane with booking intent. **The
  monetizable block.** (Needs counsel review - medical-adjacent copy.)
- **0.5 Per-city seasonal-uniqueness block** - from the 2025 archive: "{City}'s dengue search peaked
  week of {date} last year; this year is {higher/lower}." Kills near-duplicate/thin-content risk
  across 209 templated pages with zero manual writing; feeds "is it dengue season" intent.
- **0.6 Nearby-cities module** - nearest 5 by coords. Crawl mesh + local relevance + real utility.
- **0.7 PAA-aligned FAQ expansion** - 3-4 more per-city FAQs from GSC + the SERP PAA data
  (`is dengue spreading in {city} now`, `which test confirms dengue`, `dengue fever platelet count`
  18.1k KD 29 PE-absent). Compliant framing.
- **0.8 AI-citability copy pass** - every section opens with one clean, dated, sourced, quotable
  sentence ("As of {date}, {City}'s dengue risk is 41/100, Low-Moderate."). 94% of SERPs have AIO;
  AIO cites whoever states the dated fact cleanly - and we are the only ones with a daily number.

**0C. Infra / measurement (no page change):**
- **0.9 IndexNow ping on daily deploy** - Bing/Yandex same-day (Google already handled by our daily
  `lastmod`).
- **0.10 GSC indexation audit** - confirm all 209 city pages are indexed; request-index the top ~50
  by population. Verify indexation is not the bottleneck before judging content.

**0D. Cross-team (flagged, not in this repo):**
- **0.11 Blog -> Fever Watch internal-link module** - a "Check today's {disease} risk in your city"
  module in the ~8 ranking fever posts. Unlocks the blog halo (section 2). Needs the blog team.

### Phase 1 - City x disease pages (the flagship new template)
`/fever-watch/{city}/{disease}/` = 209 x 4. Each reuses the Phase-0 blocks but disease-scoped (that
disease's dial, breakdown, season trend, FAQ, test block). Validated by the data as the biggest, most
winnable lane. Ramp safely with top-50 cities x 4 first if preferred; the SSG makes full scale nearly
free. Canonical discipline: city page = hub, disease pages link up; blog keeps the national evergreen
lane (no cannibalization).

### Phase 2 - Widen the surface
- **2.1 State pages** (~30): `fever in kerala now` already in GSC with no state surface. Aggregate
  member cities (mean/max/leader), link down.
- **2.2 National daily rankings page** (`/fever-watch/rankings/`): "today's top-risk cities per
  disease" - targets `dengue india`-class + press-linkable.
- **2.3 2025-vs-2026 season recap page**: link-magnet for PR outreach.

### Phase 3 - Bigger bets (evaluate after Phase 0-2 data)
- **3.1 Hindi variant** (hreflang, top ~30 Hindi-belt cities): vernacular fever is strong and soft
  (`typhoid ke lakshan` 22.2k KD 23, `fever meaning in hindi` 40.5k); myupchar dominates, no
  e-pharmacy competes. Template translates once; the data is numbers. Needs a Hindi compliance pass.
- **3.2 Video** (1,174/1,201 SERPs carry Video): "how the score works" + per-season recap shorts.
- **3.3 Compliant news-lite strip** (see section 5) - NOT the full personalized news feed.
- **3.4 llms.txt + documented per-city JSON endpoints** - `grid.json` is already public; make it
  AI-crawler-legible.

---

## 5. News feed decision - DEFER the full feed
The personalized local news feed is the lowest-return, highest-risk of the ten explored items:
- **Small, spiky traffic** (~1-3k/mo, folded into the national line); "dengue news" SERPs are owned by
  news publishers we will not out-rank.
- **Real compliance risk:** an auto-pulled headline like "500 dengue cases in Mumbai" next to our risk
  score undercuts the **no-case-counts guardrail** - it could read as us reporting cases. Counsel
  problem, not just a build problem.
- **Ongoing editorial-quality dependency** (junk/misinformation filtering per city).

**Compliant-lite alternative (recommended if any):** an "official guidance" strip linking to the
city's health-department / municipal-corporation advisory pages only, no case numbers surfaced by us.
An E-E-A-T/trust signal rather than a news play, and safe. Pilot on 2-3 cities only after the core
pages perform.

## 6. Guardrails (enforced on every item)
Risk-indicator framing only; **no case counts** (the `dengue cases 2026` query is answered
compliantly, as the FAQ does today); no medical JSON-LD (BreadcrumbList / Dataset / FAQPage / WebPage
only); forecast-cap honesty; ASCII hyphens; SSR<->JS parity on anything in the twins; counsel
re-review for the test-info block copy and any Hindi launch.

## 7. Measurement
- Weekly GSC export scoped to `/fever-watch/` (impressions, position, query mix) into
  `data/analytics/`.
- Tracked set (~50): GSC arrivals + `{disease} {city}` for top-20 cities + test-price terms for
  top-10 cities.
- 6-8 week target: top-10 on 25+ city-disease terms; first AI Overview citation; test-CTA
  clickthrough (GTM events already in place).
- Report booking conversion from the test blocks separately - that is the ROI line.
