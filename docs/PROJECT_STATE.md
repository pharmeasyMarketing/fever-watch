# Fever Watch - Project State & Handoff

> Read this plus `CLAUDE.md` at the start of a new session. It captures what is built, what is
> verified, what is mock/pending, every locked decision, and how to run everything. The SSG is
> **LIVE on GitHub Pages staging: https://pharmeasymarketing.github.io/fever-watch/**; PRODUCTION now deploys to a
> Hostinger CyberPanel / OpenLiteSpeed VPS behind the pharmeasy.in `/fever-watch/` reverse-proxy (see the 2026-07-02 banner).
>
> **NEWEST (2026-07-07, DEPLOY TIMING FIX + RSYNC AUTO-RETRIES - committed + pushed):** The CyberPanel (production)
> deploy now fires the MOMENT `daily.yml` commits the fresh grid, via a new **`dispatch-production` job** in daily.yml
> that runs `gh workflow run deploy-cyberpanel.yml` (a workflow_dispatch sent with GITHUB_TOKEN - exempt from GitHub's
> anti-recursion guard, so it genuinely starts the run). This is the RELIABLE, cron-lag-free replacement for
> deploy-cyberpanel.yml's own `schedule` (00:30 UTC), which GitHub was delaying a consistent **~4h** (firing ~04:30 UTC =
> **~10:00 IST**, not the 06:00 the cron implies) - so the VPS now updates by **~05:30 IST**. The old `schedule` cron AND
> the never-firing `workflow_run` trigger were REMOVED from deploy-cyberpanel.yml; its triggers are now just
> `workflow_dispatch` (used by both the daily.yml chain and manual recovery). Moving the cron alone could NOT beat the
> deadline (the deploy must run AFTER daily.yml's ~23:45-UTC data commit, and +4h lag lands ~09:24 IST), so chaining is
> the only reliable fix. **Retries:** the single rsync/SSH step became **3 attempts** (attempts 1-2 `continue-on-error`
> with a 30s then 90s pause; attempt 3 unguarded, so the job still fails + notifies if all three time out) - this
> directly absorbs the transient `ssh: connect ... Operation timed out` that broke the 2026-07-07 morning deploy (the
> build was fine; a manual re-run then succeeded, confirming it was transient). Trade-off: the deploy's only AUTOMATIC
> trigger is now the daily.yml chain (+ manual dispatch); no cron backstop, but the chain is deterministic and the
> retries + manual recovery cover the gaps. First live test: the next daily run (~05:30 IST) - watch for a
> `dispatch-production` job in daily.yml, then a workflow_dispatch-triggered CyberPanel deploy right after. YAML
> validated (both files parse; step wiring confirmed); the live production dispatch can only be proven by that run.
> burnett01/rsync-deployments stays on v7.0.2 (deprecation warning noted; v8 + host-key pinning remain open harden items).
>
> **(2026-07-06, PER-CITY LOCALIZED OUTBOUND LINKS - diagnostics CTA + Medicines nav - committed + pushed):**
> Two outbound PharmEasy links now resolve to the visitor's CITY page (local-SEO authority + relevance), each with an
> honest generic fallback for unmatched cities:
> 1. **"Book a fever panel test" CTA** (the in-content `What you can do` button; SSR fallback + both JS flows) ->
>    `config/diag_links.json` maps {city_id -> local `diagnostics/health-checkup-packages/{slug}-{id}` page}. **100/209**
>    matched (95 exact + 5 alias) from the 102-page `sitemaps/diagnostic/local-all-package.xml`; rest -> the generic
>    packages page. Params LOCKED with marketing: `?src=feverwatch&page=2#:~:text=Fever`, SAME deeplink everywhere.
>    Because the JS flows swap city client-side (`setCity`/`pickCity`/geo), the URL is stored as `city.diag_url` on
>    EVERY grid city: `build_site.main()` enriches the in-memory grid and RE-SERIALIZES the served `dist/data/grid.json`
>    (no longer a raw copy), and the inlined seed carries the current city's - so the CTA tracks the rendered city, not
>    just the landed page. Log line: `Diagnostics CTA: 100/209 cities mapped to a local page (rest -> default).`
> 2. **Header "Medicines" nav link** (`nav_html`, now takes a per-page `meds_href`; SSR, baked per page) ->
>    `config/med_links.json` maps {city_id -> local `online-medicine-order/location/city/{slug}-{id}` page}. **204/209**
>    matched (185 exact + 19 alias) from the user-provided 1322-page meds sitemap; rest + the national LANDING -> the
>    generic medicines page. `?src=feverwatch` (the old `?src=homecard` removed from the Medicines link ONLY; Lab tests
>    / Healthcare / Blog keep theirs). The header is STATIC per-page SSR (a crawlable per-city link = the SEO win); it
>    does NOT re-render on client-side city switch, so it reflects the page's city.
> Aliases are state-verified: gurugram->gurgaon, mysuru->mysore, prayagraj->allahabad, mangaluru->mangalore,
> belagavi->belgaum (both maps), + meds-only kochi->cochin, kadapa->cuddapah, davanagere->davangere, panaji->goa,
> sri-ganganagar->sriganganagar, tiruppur->tirupur, visakhapatnam->vishakhapatnam, vijayawada->vijaywada,
> tiruchirappalli->tiruchi, hubballi->hubli, puducherry->pondicherry, tumakuru->tumkur, vijayapura->bijapur,
> thoothukudi->tuticorin. **Deliberately NOT mapped: brahmapur (Odisha) -/-> berhampore-2530 (West Bengal) - a
> cross-state trap the grep surfaced.** Meds fallbacks (genuinely absent from the 2022 sitemap): bhubaneswar, kolhapur,
> rohtak, karimnagar, brahmapur. VERIFIED: build clean (210 pages); SSR CTA hrefs + Medicines nav hrefs correct across
> matched/alias/fallback/landing; served grid enriched (`diag_url` x209); seed carries the current city's; live
> first-paint JS CTA = the local page, console clean; above-fold `parity_check` OK (mobile + desktop). Maps are
> regenerated from the sitemaps (one-off match scripts); REFRESH if the sitemaps change. Diagnostics coverage will
> reconcile to 100 as the sitemap grows; meds `src` intentionally `feverwatch` (not `fever-watch`).
>
> **(2026-07-04, SEO: DATE-STAMPED PAGE TITLES + "TODAY" COPY SWEEP - committed + pushed `4f883db`):** Page
> `<title>`s are now DATED and name all four diseases: city = `{City} Monsoon Fever Risk, {DD Mon YYYY} | Dengue,
> Malaria, Chikungunya, Typhoid | Fever Watch`; landing = `Monsoon Fever Risk in India, {date} | ...`. Both build the
> date from `_fmt_date_js(generated_at)` (IST-shifted), so it re-stamps on every daily build, matches the on-page
> "Updated" line, and also feeds `og:title` / `twitter:title`. Rationale (from the first Search Console queries): the
> flagship pattern is disease+city (`dengue mumbai`, `kolkata dengue`, `dengue in hyderabad`), plus year (`dengue cases
> in kolkata 2026`), monsoon (`monsoon in ghaziabad`), and now-intent (`fever in kerala now`) - so the title leads with
> the city + "Monsoon Fever Risk" + the live date and names all four diseases (previously only 3 were listed, and
> "Dengue" sat in the truncated tail after the pipe). "cases" is deliberately NOT chased in the title (we report no
> case counts; the existing "Are dengue cases actually rising?" FAQ covers that intent compliantly). Separately, EVERY
> user-facing **"this week" was swept to "today"** (scores, rankings, section headers incl. `Weather conditions today`,
> the other-cities leaderboard, the share cards + their `Today, {date}` stamp, the WhatsApp/share text `Today:`) or
> **"right now"** (band readings, the weather-window FAQ sentences, question phrasings) across `build_site.py`,
> `faq.js`, `mobile.js`, `desktop.js`, `build_share_cards.py`; the meta description now opens `Today's ...`. The inert
> `PERIOD_LABELS` ("This week"/"This month", the dead week/month tabs) are left as-is. Verified before push: build
> clean (210 pages); **0** user-facing "this week" in the built HTML; above-fold `parity_check` OK (mobile + desktop)
> and a Python `faq_items` vs `faq.js build()` render-diff byte-identical across 3 cities; no em/en/middot dashes; live
> hydrated render + console clean. STILL DEFERRED/available: the dynamic, driver-led meta description (open with the
> actual top disease + its live number) - the piece that most directly stops Google discarding the description and
> stitching its own snippet.
>
> **(2026-07-03, VPS DEPLOY TRIGGER FIX - `workflow_run` NEVER FIRED, ADDED A DIRECT DAILY CRON):** [SUPERSEDED
> 2026-07-07: this schedule cron was REMOVED - GitHub delayed it ~4h to ~10:00 IST; the deploy now chains off
> daily.yml's `dispatch-production` job (~05:30 IST). See the newest banner.] The
> `workflow_run` chain (CyberPanel deploy auto-runs after `daily.yml` completes) turned out to **never fire even
> once**. The morning after go-live, `daily.yml` ran + succeeded (23:35->23:44 UTC, both jobs green) and refreshed the
> data, but no CyberPanel deploy was triggered - every run to date was a manual `workflow_dispatch`. Config was correct
> (exact workflow-name match, file on the default branch, `conclusion == success`), so this is `workflow_run`'s known
> cross-workflow-chaining unreliability. FIX (`769c2ca`): added a direct **`schedule: - cron: "30 0 * * *"` (00:30 UTC
> = 06:00 IST)** to `deploy-cyberpanel.yml` as the PRIMARY trigger - empirically `daily.yml` finishes by ~00:00 UTC
> (its ~22:30 cron starts ~1h late every night), so the fresh `grid.json` is committed before this fires; GitHub cron
> lag ~1h means it lands ~06:30-07:30 IST. Also updated the deploy job `if` to allow `github.event_name == 'schedule'`
> (else the scheduled run is created but SKIPS the deploy job - the same silent no-op class as the `workflow_run` miss).
> `workflow_run` is kept as a harmless fast-path. Verified same day: a manual run pushed the day's fresh data (16.7 MB
> synced, `--delete` clean, no timeout). First automatic `schedule`-event run to watch: tomorrow ~00:30 UTC.
>
> **(2026-07-02, CYBERPANEL / OPENLITESPEED VPS PRODUCTION DEPLOY WIRED):** Production hosting moved off
> GitHub Pages onto a **Hostinger VPS running CyberPanel / OpenLiteSpeed**, served under `/fever-watch/` and
> reverse-proxied by the pharmeasy.in edge (public URL + `base_url` unchanged: `https://pharmeasy.in/fever-watch/`).
> github.io is now explicitly the STAGING origin. Committed + pushed to master (`ebf83fc`; dry-run test + go-live in `e1c0bf0`..`7ea79b9`). **DEPLOY VERIFIED LIVE (2026-07-02)** - see OPEN item (a).
> 1. **New workflow `.github/workflows/deploy-cyberpanel.yml`** (originally the user's file, added via the GitHub UI
>    as `eab2ef4`; then comment-corrected + folded into git). Builds the PRODUCTION export (`SITE_ENV=production` ->
>    indexable robots meta + `Allow:` robots.txt + canonical from `base_url`), overrides `base_url` at build time from
>    the `FW_PROD_BASE_URL` secret, runs the SSG (build_assets + build_share_cards + build_site), sanity-checks that
>    `indore/index.html` carries `index,follow`, then rsyncs `dist/fever-watch/` to the host via
>    `burnett01/rsync-deployments@7.0.2` over SSH. Triggers on `workflow_run` after each successful "Daily refresh +
>    deploy (Fever Watch)" run (fresh grid -> fresh VPS deploy) + manual dispatch. [SUPERSEDED 2026-07-03: this `workflow_run` chain never fired; a 00:30 UTC daily `schedule` is now the primary trigger - see the newest banner.] The VPS runs NO Python/PHP; it just
>    serves the pre-rendered static files, so the SSR<->JS parity contract still holds.
> 2. **`daily.yml` Pages `deploy` job is now `continue-on-error: true`.** The CyberPanel workflow's `workflow_run`
>    trigger is gated on `conclusion == success`; without this, a flaky or cancelled Pages publish would fail the run
>    and silently skip that day's VPS deploy. The `refresh` job is deliberately NOT guarded, so a real data/build
>    failure still (correctly) blocks production. Staging keeps refreshing daily.
> 3. **New Actions secrets** (user added): `FW_PROD_BASE_URL` (**must be the public `https://pharmeasy.in/fever-watch/`,
>    NOT the CyberPanel origin host**, or canonical/OG/sitemap point at the hidden origin), `DEPLOY_HOST`, `DEPLOY_USER`
>    (the CyberPanel site Linux user that owns public_html), `DEPLOY_SSH_KEY`, `DEPLOY_PATH`, `DEPLOY_PORT`.
> 4. **The deploy SSH key is JAILED to `/fever-watch/`**, so `DEPLOY_PATH` is set to `.` (resolves to the jail root =
>    the fever-watch dir) and rsync `--delete` cannot escape it. This is safe ONLY because of the jail; on an
>    unrestricted key `.` would resolve to the whole home dir and `--delete` would wipe public_html +
>    `.ssh/authorized_keys`. VERIFIED 2026-07-02: the live run deleted only a stray `fw_test.txt` in the target dir, proving `.` resolves to the jailed fever-watch folder and `--delete` is confined to it.
> OPEN / next: (a) [DONE 2026-07-02] **first live deploy VERIFIED** - the real deploy (run 28591701910) sent the full
> 59 MB site and `--delete` pruned only a stray `fw_test.txt`; a follow-up `--dry-run` (run 28597913537) connected
> clean over SSH with nothing unexpected to delete; `--dry-run` was then removed (`7ea79b9`) so daily auto-deploys
> write for real. One `Operation timed out` mid-test was a transient fail2ban/firewall ban that cleared (see the
> hardening/watch note);
> (b) confirm the `FW_PROD_BASE_URL` value; (c) the **pharmeasy.in edge reverse-proxy rule** `/fever-watch/` -> VPS
> origin is still PENDING (another team) - until it lands, verify at the origin host directly; (d) on a subpath,
> `pharmeasy.in/robots.txt` (root, owned by the main site) governs crawling, not `/fever-watch/robots.txt` - coordinate
> the sitemap reference there; (e) HARDENING: pin `burnett01/rsync-deployments` to a commit SHA (not the `@7.0.2` tag)
> and add known_hosts host-key pinning.
>
> **(2026-06-26, COPY SIMPLIFICATION + "WHY" DRIVER CHIPS + METHOD CITATIONS + MOBILE POLISH):** All
> verified live (mobile flow + SSR/parity OK both flows); committed + pushed to master. Nothing here is mock.
> 1. **Method-popover research citations** (the ⓘ "Source"/"assumption" links live in `mobile.js`/`desktop.js`, NOT
>    `build_site.py` METHOD_HTML). Rain window: nature `srep35028` -> `pmc.ncbi.nlm.nih.gov/articles/PMC6518529` (both
>    the Source and the "14-day window" assumption links). Temperature: `PMC6744319` -> `PMC6518529/#sec5` (TEMPERATURE
>    ONLY; Humidity left on PMC6744319 per user). Search: nature `nature07634` -> TWO sources `pubmed.../30443418/` +
>    `link.springer.com/article/10.1186/s12879-025-10801-0`. `method.js` gained a **`data-href2`** second-link slot
>    (renders a 2nd `.mthd-pop-link`); `tokens.css` `.mthd-pop-link` -> `display:flex; width:fit-content` so two
>    links stack.
> 2. **Plain-language copy pass** (the 6 user-flagged sentences + neighbours). The LAB METRIC is now consistently
>    **"share of (local) tests coming back positive" / "positive tests"** (no more "positivity"). All parity-gated
>    3-way twins unless noted: dial 80/20 tooltip "Led by X, the highest-risk fever..." -> "{d} ({score}) is the top
>    fever here, making up about 80% of this score. The other three add 20%."; SIG "what" micro-lines reworded ("How
>    many local tests come back positive." / "How often people here search these symptoms."); TIPINFO ⓘ popovers
>    reworded (positivity "...For a full 100, dengue needs 25%, malaria 4%, chikungunya 15%, typhoid 45%..."); dial
>    MEANING line "overall read"->"overall score", "A daily snapshot of conditions, not who's actually sick"->"A daily
>    look at local risk, not who's actually sick". ENGINE notes in `src/consolidate.py` (baked into `data/grid.json`;
>    38 diverge + 2 agree + 796 forecast cells string-replaced in place locally, CI regenerates from consolidate.py):
>    agree "All three signals agree - lab tests, search and weather point the same way."; diverge "Signals disagree:
>    we trust the lab tests most, and weather and search matter less."; forecast "No confirmed test data here yet, so
>    the score uses weather and search only, and can't reach HIGH."; news-spike "Search may be driven by news, so we
>    trust it less." FAQ "how worried" answer (`build_site.py:533` + `faq.js:60`, feeds the JSON-LD too) aligned to
>    "overall score" + "a daily look at local risk... not who's actually sick". The full 92-item review of the
>    remaining Tier-B/C strings is in the gitignored `Fever_Watch_Copy_Simplification_Review.xlsx` (builder
>    `scripts/build_copy_review_xlsx.py`).
> 3. **"Why this score?" highest/lowest driver chip.** The breakdown now tags ONLY the top + bottom disease with a
>    plain-language driver line as a 2nd row under the disease name (e.g. Malaria "High positive tests + strong
>    weather.", Typhoid "Lower search despite strong weather."). New helper `whyChip(cell, kind)` (mobile.js +
>    desktop.js) / `_why_chip` (build_site.py), BYTE-IDENTICAL (the `#s-why` breakdown is above-fold parity-gated);
>    names the signal(s) by CONTRIBUTION order (the +N, so it cites the real lever), simplified vocab ("high positive
>    tests"/"strong weather"/"high search interest"); returns "" (no chip) when forecast-absent, all-Low, or no score
>    spread. Markup wraps the name in `.nmwrap` + `.whysub` (CSS in shared tokens.css). User rejected an always-visible
>    summary-under-title as cluttered and chose the 2nd-line placement (Option 1) over inline, after several mock rounds.
> 4. **Mobile polish.** `.acchead` `min-height:71px` (mobile.css) equalizes the four disease rows (the captioned
>    highest/lowest rows wrap to 2 lines on the narrow mobile width; the others pad up to match). The breakdown trend
>    triangles `.sigbadge` (BOTH "up" rising and "down" easing) are HIDDEN for now (tokens.css
>    `.sigbadge.up, .sigbadge.down { display: none }`).
> STALE-DOC follow-up NOT done: the methodology Word doc / compliance copy still uses the pre-simplification wording;
> re-confirm all copy with counsel before any public launch.
>
> **(2026-06-25 PM, LEGAL FOOTER-DISCLAIMER UPDATE):** Legal supplied an updated footer disclaimer; applied
> VERBATIM to the shared page footer (`footer_html` `.footdisc` in `build_site.py`, ~L364). The footer is now exactly:
> "Fever Watch is a risk indicator and not a diagnosis or representation of actual case counts. It is for
> informational purposes only and should not constitute medical advice; please consult a doctor for any symptoms or
> health concerns. The data used to calculate the risk is derived from: live rainfall via NOAA CPC (public domain) and
> temperature/humidity via NASA POWER (public domain); Google search trends via Serpapi; aggregate lab data from
> PharmEasy Labs and its Partner Affiliates." = `MEDICAL_DISCLAIMER` (the unchanged 2-sentence constant, also reused in
> the crawler `fw-fallback` `.fw-disc`) + the new data-sources sentence. Changes vs before: added the "The data used to
> calculate the risk is derived from:" lead-in and changed the trends attribution "Google Trends" -> **"Serpapi"**
> (legal's wording). **This copy is legal-mandated - do not edit casually; re-confirm with counsel before changing.**
> Verified: footer renders the exact text on city pages + landing; parity OK both flows.
>
> **(2026-06-25, TOOLTIP FIX + ANDROID PUSH IMAGES + LOGGER URL + PROD base_url):** Four-part change, all verified.
> 1. **Tooltip positioning fix.** `.dialtip` (dial chip + per-signal "Why this score?" popovers, both flows) was
>    `position:absolute` opening upward with no clamping, at z-index 40 (above the sticky header z-index 30), so on
>    desktop it overflowed the top, overlapping the header + Quick-Links sidebar. Fix: `.dialtip` -> `position:fixed`
>    z-index 90, JS-placed by `positionTip` (renamed from `positionCaret`, byte-identical in mobile.js/desktop.js,
>    mirrors `method.js` placePop): above the ⓘ by default, FLIPS below (`.dialtip.below`) when no room above (clears
>    the header), clamps horizontally to the viewport, caret stays on the ⓘ. Dropped the desktop CSS `:hover`-open
>    (it opened an unplaced fixed box). Markup unchanged -> parity OK. Verified live both flows (above / flip-below /
>    breakdown / mobile): `position:fixed`, on-screen, caret-on-icon, no header overlap. **Follow-up (same day):** the
>    MOBILE breakdown auto-peek floated over the bottom Share dock on scroll (a fixed box does not move with the page,
>    and the peek is immune to the scroll-close so it persisted). Now `maybeScrollPeek` fires only when the ⓘ is
>    COMFORTABLY in view (`top>=56 && bottom<=vh-100`, clear of header + dock), `onTipScroll` keeps the open peek PINNED
>    to its ⓘ as the page scrolls (re-runs `positionTip`) and closes it once the ⓘ scrolls off-screen, and `positionTip`
>    flips below using the live `.fw-nav` bottom (not a flat 8px) so the box never slips under the sticky header.
> 2. **Android push image set.** Per-city **1024x512 (2:1)** big-picture = the SAME OG landscape card (gauge,
>    regional subtitle, top-concern box, gold CTA, band pill), FIT aspect-preserved into 1024x512 by new
>    `rasterize_push()` and centred on the OG dark-green bg - so the gauge/circles stay perfectly round (~24px dark
>    side margins that blend into the card edge). **An earlier custom push card was replaced 2026-06-25 per team
>    feedback to match the OG template exactly.** OG + push share one `render_landscape` render. Output
>    `assets/img/push/<city>.jpg` (~42KB, gitignored, built in CI by the existing build_share_cards step - no
>    daily.yml change). Verified by rendering + viewing bengaluru/agra.
> 3. **Logger push URL columns.** `sheetlog.py` `push_raw` now logs 2 new `raw_data` columns (AE/AF):
>    `push_image_url_prod` + `push_image_url_staging` (base_url / staging_url from config/site.json + `assets/img/push/
>    <city>.jpg?v=<og_ver>`), repeated on all 5 rows per city. Mirrored in `backfill_sheetlog.py` HEADER (blank for
>    historic) + the Apps Script `HEADERS.raw_data` + data_dictionary in `docs/sheets_logging.md`. **USER ACTION: re-
>    deploy the Apps Script** so the live sheet gets the 2 columns.
> 4. **Production base_url** corrected to `https://pharmeasy.in/fever-watch/` (was `/research/fever-watch-2026/`) in
>    config/site.json; cascades to canonical/OG/JSON-LD/sitemap + the logged prod push URL. SITE_ENV=staging still
>    overrides to github.io, so the live staging site is unchanged.
>
> **(2026-06-24 PM, REVIEWER BYLINE + reviewedBy SCHEMA for E-E-A-T - committed + pushed to master 2026-06-25):** Added a
> `Reviewed by Dr. Nikita Toshi and Dr. Avinav Gupta` trust strip (treatment "V2": a shield icon + always-underlined
> links to their PharmEasy editorial-policy profiles, `target=_blank rel=noopener`) directly under the
> `Updated <date>. Available in select cities.` line, on BOTH flows + the landing. Visible markup = a shared `REVIEWBY`
> constant, byte-identical across `mobile.js` / `desktop.js` / `build_site.py` (parity-gated, mirroring `LOC_PIN`),
> inserted into render() / searchHero() / `_mobile_pre` / `_search_hero_d` / `render_landing`. Per-flow CSS: mobile =
> green links on the light hero; desktop = WHITE links + `#cfe6e4` label on the dark-green `.srch` gradient (both
> confirmed by computed styles). JSON-LD: `reviewedBy` Person[] (name, url, jobTitle "Doctor", worksFor #organization),
> sourced from the `REVIEWERS` list in build_site.py, on the city `WebPage` node AND the landing `WebApplication` node.
> **COMPLIANCE: deliberately uses schema.org's generic `WebPage.reviewedBy` (editorial trust), NOT `MedicalWebPage` /
> medical-entity types, so it respects the "no medical schema in JSON-LD" guardrail - but get a counsel nod in the
> pre-launch compliance pass since the reviewers are doctors.** Verified: node --check, PY parse, parity OK both flows,
> SSG 210 pages, reviewedBy parses on city + landing, byline computed colours correct. Reviewer data lives in
> `REVIEWERS`/`REVIEWBY` in build_site.py (could move to config/site.json if the brand team wants to self-serve edits).
>
> **(2026-06-24 PM, DIAL MEANING-LINE COPY shortened per team feedback - committed 2a18295):** The
> dial-card meaning line was rewritten (team feedback: the old "Risk is noticeably raised. Take precautions and watch
> for fever. <Driver> is the main fever to watch in <city> this week." was too long). New copy (<=20 words, "Set E"):
> **`Right now <city>'s overall read is <score>/100, <band phrase>. A daily snapshot of conditions, not who's actually
> sick.`** where the band phrase is `low, <driver> highest` / `slightly raised, <driver> leading` / `moderate,
> <driver> leading` / `high, driven by <driver>`. `BAND_MEAN` changed from a full sentence to a per-band PHRASE with a
> `{d}` driver placeholder; the `mean` line composes city + overall score + phrase + the fixed snapshot/heads-up
> framing. Edited byte-identically in all 3 twins (`mobile.js`/`desktop.js`/`build_site.py`); parity gate OK; verified
> all 4 bands render correctly across the 210 built pages (e.g. Jaipur 47 moderate, Ranchi 79 high, Arrah 23 low, Agra
> 44 slightly raised). The score/driver are intentionally restated in prose even though the ring + legend already show
> them (team preference, "close to the original example").
>
> **(2026-06-24 PM, ⓘ-TOOLTIP PERSISTENCE + PEEK-ON-SCROLL + CRAWLER DATE CONSISTENCY - committed 226754a):** Three
> user-requested fixes, all verified in the live preview.
> 1. **ⓘ tooltips no longer auto-dismiss on a timer.** The 2.5s auto-close was removed from the `dialInfo` onClick
>    branch in `mobile.js` + `desktop.js`. An explicit tap now keeps the tooltip (dial band-chip + the per-signal
>    breakdown popovers - same handler) open until the user (a) taps the ⓘ again, (b) taps anything else (the
>    outside-close on the first line of `onClick`), or (c) **scrolls** (`onTipScroll` on a passive `window` "scroll").
>    Verified BOTH flows: stays open >3s, closes on scroll / outside-tap / second-tap; only-one-open holds.
> 1b. **Auto-peek now fires WHEN THE SECTION IS SCROLLED INTO VIEW (not blindly at load).** DESKTOP: the dial is in
>    the 2nd fold, so its peek now triggers on scroll-into-view. MOBILE: keeps the dial's after-load peek (first fold)
>    AND adds a peek for the **top disease's first "Why this score?" tooltip** (`.acc.open .dialinfo`) on
>    scroll-into-view (to hint those per-signal info popovers exist). Implemented as a `window`-scroll
>    `getBoundingClientRect` "fully in view" check (`maybeScrollPeek`/`onTipScroll`), re-querying the target by
>    SELECTOR each render - deliberately NOT IntersectionObserver, because IO observes a node the seed->data
>    re-render DETACHES (peek would never fire in prod) and IO/rAF are throttled in hidden/background tabs. A peek is
>    immune to the scroll-close (tracked by `_peekEl`) so a scroll-into-view peek is not flashed away by the same
>    scroll; it self-closes ~1.7s. `firePeek`/`maybeScrollPeek`/`onTipScroll`/`positionCaret` are byte-identical
>    across the twins; only `peekDialInfo` differs by flow. Verified: desktop dial peeks on scroll-in + survives
>    continued scroll + self-closes; mobile breakdown tooltip peeks on scroll-in + survives + self-closes + tap
>    persists + scroll-closes. (Live browser auto-verification of the scroll/peek had to dispatch synthetic `scroll`
>    events because the headless preview tab is `document.hidden`, which pauses the frame loop that delivers real
>    scroll events / IO / rAF; the handler logic is exercised identically.) parity gate OK; `node --check` clean.
> 2. **Crawler-visible dates now all express the same IST calendar date.** A 5-agent audit confirmed the visible
>    "Updated" text, sitemap `<lastmod>`, and FAQ dates were already IST, but the three JSON-LD `dateModified` fields
>    (WebPage/Dataset/WebApplication) emitted the **raw UTC** `generated_at` - a calendar date ONE DAY BEHIND on every
>    22:30-UTC cron build (e.g. page said 24 Jun, JSON-LD said 23 Jun). FIX: new `iso_datetime_ist()` helper in
>    `build_site.py`; `jsonld()` shifts `generated_at` +5:30 once at the top so all three nodes emit e.g.
>    `2026-06-24T05:08:42+05:30`. Now JSON-LD dateModified == sitemap lastmod (`2026-06-24`) == visible "Updated 24 Jun
>    2026" == FAQ "from 24 Jun 2026". (Left as-is by design: the og:image `?v=` token keeps raw-UTC digits - a
>    cache-bust key, not a semantic date, and it feeds the shared data/share-card cache-bust system; the inlined
>    `FW.seed.generated_at`/`trends_as_of` stay raw UTC and are converted to IST client-side by `fmtDate()`.)
>
> **(2026-06-24, MEDICAL-REVIEW UX OVERHAUL - committed + pushed to master; verified via the parity gate +
> DOM/geometry, headless-preview screenshots blocked by a flaky `grid.json` fetch):** A doctors' medical review (7
> points) drove a wide front-end pass. A 7-point feasibility workflow mapped them; these shipped (committed 2026-06-24):
> - **"breeding" removed across all user-facing copy** -> "Weather conditions" (signal name; the weather-card title
>   `Weather conditions this week` + sub; hero; dial footer; share text; FAQ; methodology; meta description;
>   `grid.json` disclaimer; Dataset JSON-LD; the trend "vs last year" weather captions; method popovers). Rationale:
>   breeding is mosquito-only and we also cover waterborne typhoid. "mosquito" KEPT where it is the genuine mechanism
>   (temp/humidity); the Rainfall tile now names typhoid too. Code comments tidied.
> - **Stagnation weather tile removed** from all 3 render twins. The `_stagnation()` PRODUCER in `build_daily.py` is
>   KEPT (grid.json still carries `weather.stagnation`, just not rendered) - per user decision. Weather card = 3 tiles
>   (Temperature / Rainfall / Humidity): **desktop 3-up; mobile 2 squares + Humidity full-width horizontal** below.
> - **Precautions section renamed** `Take the right precautions` -> **`What you can do`** (mobile actionsCard, desktop
>   doSection, build_site SEO `do_sec`, + the desktop Quick Links TOC). (The 4 precaution links were already verified
>   live + carrying `?src=feverwatch`.)
> - **Dial / first-fold comprehension:** (1) a plain-language **meaning line** under the band chip - copy revised
>   2026-06-24 PM (team feedback, see top banner) to `Right now <city>'s overall read is <score>/100, <band phrase +
>   driver>. A daily snapshot of conditions, not who's actually sick.` (`BAND_MEAN` is now a per-band PHRASE with a
>   `{d}` driver token); (2) an **ⓘ tooltip** on the band chip explaining
>   the headline = ~80% the top fever + ~20% the rest, plus a Low->High **bands legend**. It tap-toggles
>   (`data-act="dialInfo"`), **auto-peeks ~1.7s as a hint** (desktop: on scroll-into-view since the dial is 2nd-fold;
>   mobile: shortly after load); an EXPLICIT tap then keeps it open until tapped again / outside-tap / **scroll**
>   (no timed auto-close as of 2026-06-24 PM; see the 2026-06-24 PM banner + `onTipScroll`/`maybeScrollPeek`), closes on
>   outside-tap, and **only one `.dialinfo.open` at a time** (the onClick outside-close closes every open tooltip not
>   containing the click). A `.tipcaret` is JS-positioned to point at the ⓘ (`positionCaret`). (3) dial centre
>   `Overall fever risk` -> **`Overall fever risk score`** (em narrowed + number shrunk so the longer label stays
>   inside the 270deg arc - verified by corner-distance vs the safe radius). (4) **period tabs reduced to "Today"
>   only** - "This week"/"This month" were non-functional placeholders (no per-period score, no click handler), gated
>   on by days-of-history; `periodTabs`/`_period_tabs` now filter to today (the data layer `grid["periods"]` is
>   untouched, so re-enabling is a one-line revert once the real multi-period feature is built). (5) **vs-yesterday
>   delta triangles hidden** in the legend (`deltaArrow` call dropped). (6) per-disease legend scores show **`/100`**.
> - **Desktop dial + "Why this score" EQUAL HEIGHT (replaces an earlier content-height stopgap):** equal-height was
>   re-enabled and the DIAL sized DOWN (ring 188->150, number 52->40, `.rtop` gap removed, legend padding tight,
>   `.rfoot` border-top removed, `.dialmean` margin 15px) so its natural height is <= the breakdown card. So the
>   breakdown is the taller card (sits at content height, no void) and the dial stretches gracefully (`.rtop` flex:1
>   re-centres the ring). Root cause of the original void: equal-height + top-aligned tiles grew the tiles
>   tall-but-empty when the dial grew.
> - **"Why this score?" "raw" clarified (Option C):** derivation line `{weight}% weight x raw {v}` -> `{weight}% weight
>   x {v}/100`; each line carries a per-signal **ⓘ popover** (`TIPINFO[k]` = weather/search/lab text) explaining what
>   that 0-100 number measures. The popover reuses the dial pattern (dark box + caret), anchored to the `.sig`
>   (`position:relative`); `.acc.open` set to `overflow:visible` (head/body corners re-rounded) so the floating popover
>   is not clipped; `.dialtip {white-space:normal}` (it lives inside the `nowrap` derivation line and must reset).
>   NOTE: showing the real lab positivity % is NOT possible - the guardrail keeps only the derived 0-100 signal in
>   grid.json.
> - **Shared dial-tooltip primitives** are byte-identical across `mobile.js`/`desktop.js`/`build_site.py` (parity gate
>   `scripts/parity_check.js` stayed OK throughout): the `.dialinfo`/`.dialinfo-btn[data-act=dialInfo]`/`.dialtip`/
>   `.tipcaret` markup; `BAND_MEAN`, `TIPINFO` maps; the `dialInfo` onClick branch (toggle + `positionCaret`, no
>   timed auto-close), the outside-close (only-one-open), `positionCaret`, `firePeek`, `maybeScrollPeek`, and
>   `onTipScroll` (the `window`-scroll handler: peek-on-scroll-into-view + close user-opened tooltips; `peekDialInfo`
>   differs by flow). ONE handler drives both the dial
>   tooltip and the per-signal breakdown popovers.
> - **STILL OPEN from the review (NOT done):** #6 "this vs last monsoon ~0%" - DIAGNOSED (a single-week endpoint
>   comparison, NOT universal: only ~40/209 cities read ~0%, Bengaluru is -37%; root = it compares ONE week, should
>   compare season-to-date) but the fix is NOT implemented. Plus the flaky-but-non-fatal `grid.json` refetch loop in
>   the headless preview (a seed boot exists so prod hydrates; offered to add a guard). Earlier same session: the two
>   CTA blog links (Vaccination, Fever-framework) shipped + committed (`1b4b14f`); separate analyses (a 2025 push-
>   notification cadence plan, a testing-repo setup doc, the one-page push-plan .docx) are gitignored deliverables.
>
> **(2026-06-20, EXPLORATION SESSION - national-heatmap plan + hi-fi mock (user NOT happy, exploring an alt direction), 2025/2026 data deep-dive, 6-feature roadmap. ALL local-only / gitignored; nothing committed beyond the methodology port `633fa8c`):**
> A wide-ranging exploration on top of the committed methodology redesign. Nothing here is committed except the methodology port (`633fa8c`, next banner); the deliverables are gitignored local files.
> - **NATIONAL INDIA HEATMAP ("the strongest viral object"):** a full implementation plan was produced (a 5-agent research workflow) AND a hi-fi interactive mock built + reviewed live in Chrome. **STATUS: the user is NOT satisfied with the mock look-and-feel and is exploring a different direction - do NOT resume the current mock approach without fresh direction.** The PLAN itself is still good reference (memory `[[national-heatmap-plan]]`): a HYBRID faint-outline + 209 city-DOT map (we hold point data, NOT polygons, so no choropleth); an inline equirectangular projection (no build toolchain), implemented as a JS<->Python twin guarded by a parity gate; a pre-projected `data/india_outline.json` shared by the client SVG AND the resvg-baked share card (one source of truth); dots sized by band (HIGH biggest + a pulsing beacon), confirmed=solid / forecast=faded. **Legal must-get-right = a compliant Survey-of-India boundary (J&K / Aksai Chin / Arunachal drawn as India); recommended source india-geodata SOI-variant (CC0); legal sign-off required, then FREEZE the outline.** Daily-baked "India's fever map this week" OG (1200x630) + WhatsApp (900x1200) via `build_share_cards.py`; lands on the landing hero (Option A clean card vs Option B hero spotlight) + a city-page variant. Mock = `prototypes/national-map-mock.html` (gitignored; builder `_build_map_mock.py` + `_map_template.html`, also gitignored). Palette PREREQUISITE: reconcile `grid.json bands[]` / tokens `--risk-*` / `build_share_cards.py BAND_COLOR` to ONE ramp before building.
> - **2025/2026 DATA DEEP-DIVE (memory `[[data-insights-2025-2026]]`; workbook `Fever_Watch_2025_2026_Analysis.xlsx`, gitignored, 10 tabs + charts):** 2025 lab = 131,662 tests / 13.4% blended positivity; typhoid 25.2% (flat-high), dengue 11.1% (rises to 15.3% by Oct), chik 7.7% (rises late), malaria 1.9% (flat-low) - VALIDATES the per-disease refs 25/15/4/45 + the lead(weather) -> lag(labs) order. **WHY 191 cities are forecast-capped = lab-coverage geography: only 18/209 are HIGH-eligible; 191 are capped at 69 because NO positivity clears the 30-test gate (795/795 forecast cells have positivity=None). Testing is concentrated in ~18-37 metros - it is structural, not a bug.** 2026 is tracking ~8-10 pts BELOW 2025 (milder onset). **Band-transition VOLUME insight (key for alerts/news): per-disease MODERATE crossings = 10-100x the volume of rare HIGH (384 per-disease band-ups in 6 days vs 34 HIGH crossings in all of 2025) - trigger WEEKLY with hysteresis, frame as conditions/risk, NOT cases.**
> - **6-FEATURE ROADMAP explored (memory `[[feature-roadmap-2026]]`):** (1) threshold/risk-movement alerts via CleverTap web push - HIGH only fires for ~18 cities, so reframe to tiered "risk rose to MODERATE" per-disease for volume; (2) JSON-LD - AVOID medical / SpecialAnnouncement / FAQ schema (deprecated + breaches the no-medical-schema guardrail); add Dataset + BreadcrumbList only; (3) city-vs-city compare (client-side from grid.json + a client-rendered share card); (4) the national heatmap (above); (5) news syndication = RSS + a newsroom page + an auto data-story email + a PR wire (NewsVoir ~Rs5k/release); (6) OG-image URL sheet -> `Fever_Watch_OG_Image_URLs.csv` (209 rows; pattern `{base_url}assets/img/og/{id}.jpg`; the 1200x630 OG works for Android/web-push big-image with a `?v=` cache-bust; portrait 900x1200 is for WhatsApp, NOT push).
> - **Other local deliverables (gitignored):** `Fever_Watch_Score_Calculation_Medical_Review.docx` (1-page methodology for the medical team - all assumptions + cited sources + 2 worked examples), `prototypes/method-options.html` (the #3/#7 review mock). `.gitignore` extended to cover all the above scratch + design prototypes.
>
> **NEWEST (2026-06-19, "How we calculate the score" methodology REDESIGN - PRODUCTION PORT + review revisions DONE, committed + pushed):**
> The consumer methodology explainer was redesigned (old `prototypes/method-section-mock.html` was "still confusing"),
> ported to production, then revised across two user review rounds. It is LIVE in the "How we calculate the score"
> methodsheet (mobile) / section (desktop). Interactivity lives in a new shared module `assets/js/method.js`
> (popovers + signal accordions + the dynamic worked examples); markup is the `METHOD` constant in `mobile.js`
> (mobile layout) + `desktop.js` (single-column layout) - the SSR `METHOD_HTML` in `build_site.py` stays a
> CRAWLABLE TEXT fallback (it sits inside `#fw-app`, which the JS replaces on hydration; an interactive accordion
> there would hide the search/lab copy from crawlers). All widget CSS is namespaced `.mthd-*` in `tokens.css`
> (every class, to dodge the bare-global `.card`/`.fill`/`.track` and the disease-breakdown `.acc`/`.acchead`).
> `method.js` is loaded in the PAGE `<script>` block + added to the `asset_version()` cache-bust hash. Source of
> truth = `prototypes/method-section-final.html`.
> - **Direction B layout:** intro (3-signal chips) -> three drill-down signal accordions (Weather two-family
>   45/35/20 mosquito + rain-only typhoid; Search; Lab) -> dynamic worked example(s) -> score bands -> footer.
> - **Markers:** "our assumption" = a dotted-underline glossary term (no pill). Its popover reads "Our assumption"
>   for pure judgement, or "Our assumption, informed by research" + a "Read the research" link where a citation
>   genuinely applies (14-day window srep35028, typhoid windows PMC8832923, per-disease thresholds UNHCR). Separate
>   green "Source" chips carry the published-science links. NO "not a cited fact" phrasing. `method.js` `openPop`
>   switches the title on the presence of `data-href` on a `data-mpop="set"` marker.
> - **Lab thresholds** render as colour chips (Dengue 25% / Chikungunya 15% / Malaria 4% / Typhoid 45%), not bars.
> - **Score builder DROPPED**; the two worked examples are now DYNAMIC from the loaded city's real grid cells via
>   `FeverWatchMethod.examplesHtml(picks, city, isDesktop)`, which mirrors `consolidate.py` EXACTLY (confirmed:
>   base = .30w+.22s+.48lab, spread<22 -> x1.08 cap 100 else x0.96; forecast: .60w+.40s capped 69) and apportions
>   the per-signal pieces by largest-remainder so they SUM EXACTLY (the old hand-authored "25+16+38=80" mismatch
>   is gone). FIXED the forecast weights that the prototype had wrong: 60/40, NOT 58/42. Edge case: driver disease
>   + one of the OPPOSITE mode if the city has one, else just the driver (16 cities are mixed-mode, 191 all-forecast,
>   the rest all-confirmed - so MOST pages show one example). Mobile re-fills on each `openMethod`; desktop re-fills
>   in `render()` (tracks the selected city). Verified live: Mumbai -> Malaria 63 = grid; Delhi -> Chikungunya
>   forecast (72 capped to 69) + Typhoid with-lab (57 x0.96 -> 54), all matching the grid.
> - **Other review fixes:** removed the duplicate eyebrow/title inside the widget (the sheet/section header already
>   says it) + the "Source/Our setting" legend row + "Live (plausible numbers)" labels + the footer "Open any score
>   ... never a mystery number" line. **Lab attribution: NO "ThyroCare" or "PharmEasy diagnostics" in any user-facing
>   copy** - always "PharmEasy Labs and its Partner Affiliates" (both flows + `METHOD_HTML`; only internal docstrings
>   in `citymap.py`/`gsheet_api.py` still name the providers). Added a second **"Know more"** link (opens the
>   methodology, like the dial card's) after the "Why this score?" subtitle - in `mobile.js`, `desktop.js` AND the
>   desktop SSR twin `build_site.py` `_why_section_d` (it is above-fold; parity stays byte-identical).
> - **Dormant (harmless):** the old score-builder/dial CSS (`.mthd-builder`/`.mthd-dial`/`.mthd-thr`/`.mthd-deskgrid`/
>   `.mthd-modetog`/`.mthd-ledger`/`.mthd-capnote`) + the `method.js` `setDial`/mode-toggle code are now unused but
>   left in place (so the builder is trivial to re-enable). Can be pruned later.
> - **Verified:** `node --check` clean on all three JS; full SSG builds 210 pages; `scripts/parity_check.js` PARITY
>   OK both flows (the method section is below-fold except the parity-twinned "Why this score?" Know-more); browser-
>   verified every interaction + the dynamic example math against the grid. Committed + pushed to master (CI deploys).
> Full detail in memory `method-section-redesign.md`.
>
> **NEWEST (2026-06-18 EOD, ALL MOCK season-trend DATA REMOVED - the home was still serving a mock chart; now there is no mock anywhere):**
> A deep-dive (home + 10 cities, cache/cookie matrix, full code audit, adversarial design review) found the
> **home page consistently served a MOCK season-trend** while the 10 city pages were already real. Root cause: the
> landing `window.FW` had NO `archiveUrl` and NO `seed`, so the archive never loaded and `trend.js` fell into the
> deterministic mock. Since all three signals are live, the mock is no longer needed - it is now **deleted from the
> whole project** and replaced with honest states. Verified end to end; committed + pushed.
> - **Deleted the mock** from both byte-identical twins: `trend.js` (`metricSeries`/`lyPeak`/`SHAPE`/`LY_MIN`/`LY_MAX`/
>   `PEAK_IDX`/`hashStr`) and `build_site.py` (`_t_metric_series`/`_t_lypeak`/`_t_hash`/`TREND_SHAPE`/`TREND_PEAK`/
>   `TREND_LY_*`). Every metric is now real-or-`{avail:false}`; NO fabricated series can be produced.
> - **Fallback ladder (all honest):** real archive series -> HEIGHT-MATCHED skeleton while a city's slice is still
>   loading (CLS 0, kept) -> per-metric "coming soon" for a metric with no data (Labs for the 185/209 cities with no
>   2025 history - scoped PER-METRIC so the card is never blanked) -> whole-card "coming soon" only if a city has no
>   real `overall` line. The `_archiveFailed -> carry mock` path is gone; on archive-fetch failure the current city
>   stays real via the seed slice and any other city shows a skeleton (never mock).
> - **LANDING fix:** `page()` now inlines the DEFAULT city's (`bengaluru`, matching `pickDefaultCity`) `seed` +
>   `seed.archive` slice + `archiveUrl`, mirroring city pages, so the home first-paints REAL. `FW.city` is left unset
>   so `maybeGeo()`'s IP redirect still runs on the landing.
> - **Resilience:** the real-vs-available gate is now LENIENT on the this-year length (`1 <= len(ty) <= asOf+1`);
>   `_t_real_series`/`realSeries` clamp to the last real point (`cur = min(asOf, len(ty)-1)`) and the chart dot sits at
>   the series end, so a short `ty` (e.g. a week-boundary day before the daily archive cron extends it) renders a real
>   PARTIAL line instead of blank or mock. A **build-time ASSERT** (`build_site.py` `main()`) aborts the build if any
>   city lacks a real `overall` line (ly==22, 1<=ty<=asOf+1), so a stale/malformed archive can never deploy a blank
>   trend - the previous good build stays live instead.
> - **Verified:** home `/` REAL ("peaked at 88 in Jun", not the mock "89 ... late August"); labs-coming-soon city
>   (kanpur) shows real Overall/Weather/Searches + grayed "coming soon" Labs, card not blank; archive-fetch failure ->
>   skeleton, `mock:false` in every case; **JS<->Python trend parity EXACT** across 4 cities (`forCity()`==`_trend_series()`);
>   `scripts/parity_check.js` OK both flows; build assert passes 209/209; zero "late August"/mock strings in `dist/`;
>   no console errors. (`dist/` is gitignored - CI rebuilds + deploys on push to master. NOTE: GitHub Pages edge-caches
>   the HTML ~10 min and the `FW` seed lives in the HTML, not the `?v=`-busted JS, so the home may serve the old mock
>   HTML until the edge refreshes; a hard refresh confirms sooner.)
>
> **NEWEST (2026-06-18 PM, COLD-LOAD season-trend "mock graphs first" fix + Labs tab/label alignment + Monsoon-precautions CTA + Google Tag Manager - committed + pushed):**
> - **Cold-load mock-trend bug FIXED.** On a cold load the "This monsoon vs last year" chart (and the desktop
>   "Signals at a glance" sparkline shapes) rendered the deterministic MOCK series and only flipped to REAL after
>   the full `trend_series.json` fetch landed (so users saw mock first, real after a reload/browse). Root cause:
>   the instant-first-paint `FW.seed` carried no archive, so `trend.js` `forCity()` fell back to `metricSeries()`
>   (mock) until the async fetch re-booted. Three-part fix, all verified locally:
>   1. **Seed inlines THIS city's real archive slice** (`build_site.py` `page()`: `seed["archive"] = {"cities":
>      {id: archive_city}}`, ~0.4KB raw / ~+240B gzipped per page) so the FIRST paint is REAL - no mock phase.
>   2. **Height-matched loading skeleton** (`trend.js` `seasonAxis`/`buildSkeleton`/`skeletonCard` + `tokens.css`
>      `.fwtrend-skel*`) shown when a city's archive is not yet present (e.g. switching to a non-seed city before
>      the full archive lands) INSTEAD of the mock; CLS-0 verified (skeleton == real card height: mobile 590=590,
>      desktop 628=628, incl. the smalls row). The deterministic mock is now reachable ONLY as a graceful fallback
>      if the archive fetch definitively FAILS (so nothing hangs forever).
>   3. **Parallel fetch + retry** (`mobile.js`/`desktop.js`): grid + archive fetched concurrently (archive no
>      longer chained behind the ~950KB grid); `loadArchive(3)` retries + `console.warn`s on final failure;
>      `_archiveFull`/`_archiveFailed` flags drive the skeleton-vs-real-vs-mock gate in `trend.js`; on archive
>      failure the seed slice is carried forward so the CURRENT city never regresses to mock.
> - **Five UI / analytics changes:**
>   1. **Season-trend Labs tab:** dropped the "soon" word, kept the tab grayed (`.soon`) + non-clickable; tightened
>      the MOBILE tab side-padding (14->10px, mobile flow only) so the four tabs (Overall/Weather/Searches/Labs)
>      stay on ONE row (was wrapping "Labs" to a 2nd line at ~375px). `trend.js` `tabsHtml` + `build_site.py`
>      `_trend_html` + `tokens.css` media query.
>   2. **Desktop small-multiples** ("Signals at a glance"): no-data mini now reads "No confirmed lab data yet"
>      (was "soon"); `.fwtrend-smini` is now a top-aligned flex column so the Labs label lines up with
>      Weather/Searches (was ~19px low because the stretched `<button>` centered its shorter content).
>      `trend.js` `smallsHtml` + `tokens.css`.
>   3. **Desktop "Why this score?"** breakdown: `.sig` tiles -> `justify-content: flex-start` (was `center`) so the
>      short no-data Lab tile's label lines up with Weather/Search (was ~29px low). `desktop.css` only (DOM-measured
>      label tops now [548,548,548]).
>   4. **"Monsoon precautions" CTA** now links to
>      `https://pharmeasy.in/blog/17-simple-health-tips-for-the-monsoons/?src=feverwatch` (was `#`). `ACTIONS` in
>      `mobile.js`/`desktop.js`/`build_site.py`.
>   5. **Google Tag Manager `GTM-W5PR55Z`** added site-wide: loader `<script>` high in `<head>` + the `<noscript>`
>      iframe right after `<body>` in the shared `PAGE` template (`build_site.py`); ships on every city + landing
>      page (verified `dataLayer` init + `gtm.js` request firing, 2 ID occurrences/page, no leftover `{{` braces).
> - Verified: both flows `parity_check` OK; DOM-measured alignment (sig + smalls labels equal); mobile tab row no
>   longer wraps; CLS-0 skeleton; GTM live. `dist/` is gitignored (CI rebuilds). Asset hash bumps so caches bust.
>
> **NEWEST (2026-06-18, "Updated {date}" timezone fix - all displayed dates now IST - committed + pushed):**
> The "Updated {date}" note (and the FAQ date, the share/OG card "This week, {date}", and the sitemap `<lastmod>`)
> was showing the **UTC calendar date** of `grid.generated_at`, so a cron build at 23:59 UTC rendered "17 Jun" to
> IST users even though it is already 18 Jun in India. Fixed with a consistent **+5:30 IST shift** before extracting
> the date parts, in the shared formatters: `fmtDate()` (mobile.js / desktop.js / faq.js), `_fmt_date_js()`
> (build_site.py, kept byte-identical to the JS), `iso_date()` (sitemap), `fmt_date()` (build_share_cards.py), and the
> season-trend `asOf` (trend.js + build_site `_trend_series` + build_archive `_as_of`). `generated_at` is still minted
> in UTC and the raw data fields (`generated_at`, `trends_as_of`) stay UTC - only the DISPLAY converts to IST.
> Verified: built page shows "Updated 18 Jun 2026", FAQ + sitemap `lastmod` 2026-06-18 match, SSR<->JS parity OK, and
> `asOf` is unchanged (still 2 - Jun 17 UTC and Jun 18 IST are the same season-week, so no archive rebuild was needed).
>
> **NEWEST (2026-06-17 PM, PER-DISEASE POSITIVITY REFS + "Why this score?" readout redesign + analytics sign-off workbook - committed + pushed):**
> - **Per-disease `ref_positivity_pct` = dengue 25 / malaria 4 / chikungunya 15 / typhoid 45** (the % positivity that maps to a full
>   100 signal, from the real 2025 gated p90; replaces the single global 35). Wired through `config/signals.json`
>   (`ref_positivity_pct_by_disease`, both providers), `gsheet_api.build_index`/`_signal`, `googlesheet._signal`,
>   `build_archive.LAB_REF_BY_DISEASE`, `scripts/build_lab_feed_2025_historic.REF_BY_DISEASE`, `backfill_sheetlog.REF_PCT_BY_DISEASE`,
>   and the in-sheet col-O Apps Script formula (now an `IFS` on the disease in col E, `docs/sheets_logging.md` - **RE-DEPLOY the Apps
>   Script**). Effect: malaria can finally reach 100 (was capped ~33), typhoid 30% -> 67 (was 86, no longer over-saturating).
>   Regenerated `data/lab_feed_2025_historic.csv`, `data/backfill/sheet/raw_data_2025.xlsx` (now with the REAL positivity build-up
>   cols AB tests_booked / AC positives / AD positivity_pct + gated O formula, sourced from the TC feed), and the season-trend
>   `data/archive/trend_series.json` (labs.ly recomputed per-disease, 24 cities). The LIVE `grid.json` re-derives on the next CI
>   `build_daily` (gsheet_api). MUST also update the Word doc + "How we calculate the score" - DONE (see below).
> - **"Why this score?" readout redesigned** (`mobile.js`/`desktop.js`/`build_site.py` `sig`/`_sig` + SIG bg/fg + `level`/`_level`):
>   a High/Moderate/Low **level pill** on its own row + the full **`{weight}% weight x raw {v}`** derivation on its own row (NO `=`),
>   `+N` contribution split from the dormant trend badge, reconciliation footer kept as-is. Signal labels shortened
>   (Breeding weather -> Weather, Search interest -> Search, Lab signal -> Lab). Desktop tiles grow into the dial's slack via a
>   CSS flex-fill (`#s-why` flex column + open-accordion/accbody fill + `.sig` justify-center) and the `.accnote` top margin -> 0;
>   `#s-why .sig` padding tuned to `5px 12px 6px` so the tallest #s-why (mumbai, 3 confirmed tiles) stays <= the 608px dial =>
>   **ZERO section growth** (verified by unstretched measurement: gulbarga 587 / mumbai 593 / dial 608). SSR<->JS parity OK both
>   flows; no truncation; full "weight" word now shows on desktop AND mobile. Methodology updated (`build_site` METHOD_HTML + the
>   mobile/desktop JS `METHOD` twins) + Word doc `Fever_Watch_Project_Document_v3.docx` (gitignored) - both carry the per-disease
>   refs + the new readout. (Did refinements #1 humanize, #2 drop "35% reference" from consumer, #3 split +N/trend, #6 per-disease
>   ref, + label shortening. NOT done: #4 disease-delta timeframe label, #5 Overall-vs-top-disease note (user: don't touch the dial),
>   #7 formal a11y verify.)
> - **Analytics sign-off workbook** `data/analytics/Fever_Watch_Score_Workbook.xlsx` (gitignored, ~42MB; reproducible builder
>   `scripts/build_score_workbook.py`): 10 tabs - Overview, Data_Dictionary, Scores_2025 (REAL labs, full in-cell formula build-up),
>   Scores_2026 (2026-06-01..14 backfill, **positivity MOCK** - flagged in Overview), Weather_2025/2026, Trends, Labs_2025,
>   Labs_2026 (the **LIVE** feed pulled via `gsheet_api`, city-aggregated), Config_Refs. For the analytics team to audit the
>   weather + search + labs -> score chain end to end. (Offer outstanding: regenerate Scores_2026 to use the real live labs.)
> - **Live data is REAL on all 3 signals already** (`grid.json` positivity_provider=gsheet_api, 39/836 cells confirmed, the rest
>   honestly forecast-only/capped 69); the per-disease refs + new readout take effect on the next deploy.
>
> **NEWEST (2026-06-17, LAB POSITIVITY IS LIVE + season-trend made REAL + scope locked to 209 - committed, pushed, verified in prod):**
> signal-3 (PharmEasy/ThyroCare lab positivity, the proprietary ground-truth layer) is LIVE end to end; the season-trend
> Labs + Overall lines are now REAL (were mocks); project scope is locked to the 209 lab-covered cities. Commits
> `6632419`..`7ef48e4`, all pushed + deployed; verified on https://pharmeasymarketing.github.io/fever-watch/.
> - **LIVE LAB FEED (signal 3):** new `src/signals/gsheet_api.py` reads the PRIVATE Google Sheet tab
>   **"Year 2026 DoD data(TC Data)"** via the **Google Sheets API + a service account** (NOT publish-to-web). Auth =
>   `GOOGLE_SHEETS_SA_JSON` Actions secret (set) / local `secrets/gsheets_sa.json` (gitignored). `daily.yml` grid step runs
>   `POSITIVITY_PROVIDER=gsheet_api` (committed config default stays `mock` so local builds without the key still work).
>   Column adapter handles verbose+standard headers and DD-MM-YYYY / YYYY-MM-DD; trailing `window_days` (=14) sum, 30-test
>   gate, ref 35% -> 0-100 signal (`_signal`). Only the DERIVED 0-100 signal reaches the PUBLIC grid.json; RAW counts never
>   leave the private sheet. Verified live: 209 cities, ~39 confirmed-positivity cells; e.g. Delhi typhoid 85 -> score ~60.
> - **CITY MAP (`data/citymap/`):** the lab feed's free-text city strings (702 in 2025) map to config ids via a reusable
>   resolver `src/citymap.py` (EXACT case-insensitive match ONLY - no suffix-strip, so no cross-state collisions like
>   AURANGABAD(BH)) using committed counts-free `city_alias_map.csv` (raw->config_id) + `manual_aliases.csv` (satellite
>   folds: KALYAN/DOMBIVLI->thane; MIRA/BHAYANDAR/VASAI/VIRAR/NALASOPARA->mumbai). Built by a 2-gazetteer
>   (GeoNames+Wikidata) reconcile + adversarial-verify workflow. Unmapped live strings log to `unmapped_live.csv` for review.
> - **SCOPE LOCKED to 209 cities:** `scripts/gen_cities.py` `DROP_NO_LAB_DATA` drops the 19 config cities with no lab data
>   (228 -> 209); `config/cities.json` regenerated; `build_archive` prunes the archive to config on every write.
> - **HISTORIC 2025 audited + transformed:** `TC Fever Watch Data 2025.xlsx` (gitignored) ->
>   `scripts/build_lab_feed_2025_historic.py` -> `data/lab_feed_2025_historic.csv` (gitignored; now carries the FULL
>   positivity build-up: tests_booked -> positives -> positivity_pct -> positivity_signal[gated 30, ref 35]). This TC 2025
>   data (NOT the sheet's sparse "Last Year DoD data(PE Data)" PE tab) is the source for the last-year labs line.
> - **SEASON-TREND now REAL (replaced the deterministic mock for Labs + Overall):** `src/build_archive.py --history`
>   (local one-off; reads the gitignored backfills + the TC csv) writes COUNTS-FREE `labs.ly` (24 cities have a real
>   last-year line) and a real, **dial-consistent** `overall{ly,ty}` per city (per-disease consolidate -> 0.8*top +
>   0.2*mean-rest headline; `overall.ty[current]` == the live dial, verified 0 mismatches/209). `--daily` upserts labs.ty +
>   overall.ty from grid.json. `trend.js` + `build_site.py` consume the real overall/labs (mock fallback retained for
>   cities without history). The YoY verdict chip now reads **"-N% vs the same week last year"** (was "lower/higher than
>   last year") - the delta is THIS week vs the SAME week of last season, not vs last year's peak.
> - **LOGGER (`docs/sheets_logging.md` Code.gs + `src/sheetlog.py`):** the full lab build-up is in-cell. tests_booked(AB)
>   + positives(AC) are POSTED; positivity_pct(AD) AND positivity(O) are now FORMULAS; O = MIN(100,ROUND(AD/35*100)) gated
>   to "" below 30 tests. Chain: AB,AC -> AD -> O -> score(T). The user has REDEPLOYED the Apps Script (the new O formula
>   shows on rows posted after the next run).
> - **CACHE-BUST:** grid.json + trend_series.json fetch URLs carry `?v=<grid.generated_at>` (build_site) so a daily data
>   refresh busts the browser cache (only og/share images were versioned before). **CRON rescheduled to 04:00 IST
>   (22:30 UTC)** so GitHub's ~5h scheduled-cron delay lands the run by ~09:00 IST. **SEARCH FIX:** `_search_blocks` now
>   carries forward the last good value for a week beyond the latest weekly timeseries pull (was zeroing - the
>   Ranchi/Jharkhand "Searches 0").
> - **OPEN REFINEMENTS (MOSTLY DONE 2026-06-17 PM - see the newest banner at the very top; only #4/#5/#7 remain):**
>   1. ~~Humanize the per-signal readouts~~ DONE: High/Mod/Low level pill + `{weight}% weight x raw {v}` derivation (no "raw").
>   2. ~~Remove "vs a 35% reference" from the CONSUMER view~~ DONE (high/moderate/low; the per-disease anchor lives in methodology).
>   3. ~~Split the signal chip's CONTRIBUTION (+N) from its TREND arrow~~ DONE (+N top-right, trend badge moved off it).
>   4. **STILL OPEN** - Label the disease-list deltas with a timeframe ("vs last week" / "since yesterday").
>   5. **STILL OPEN (deferred)** - Note/tooltip explaining Overall sitting below the top disease (user: don't touch the dial).
>   6. ~~PER-DISEASE positivity reference~~ DONE: dengue 25 / malaria 4 / chikungunya 15 / typhoid 45 (replaced the global 35).
>   7. **STILL OPEN** - Accessibility formal verify (gray sub-text contrast; trend arrows shape-coded; 44px targets).
>
> **NEWEST (2026-06-16, RAIN SOURCE SWITCHED: NASA POWER -> NOAA CPC):** a 228-city benchmark vs IMD
> gauge truth (dry + wet windows) showed NASA POWER over-reads PRE-MONSOON rainfall in the South
> peninsula (inflating the breeding + typhoid score in the high-dengue belt; Bengaluru live 14d 194mm
> NASA vs 61mm IMD). RAIN is now **NOAA CPC** (Global Unified Gauge-Based Analysis; gauge-based, US
> public domain, no licence). TEMPERATURE + HUMIDITY stay on **NASA POWER**. New HYBRID provider
> `src/providers/cpc.py` (composes NasaPowerProvider for temp/humidity, overlays CPC precip with a
> coastal nearest-valid-cell guard); `cpc` is the registry DEFAULT, `--provider nasa-power` (or
> `WEATHER_PROVIDER=nasa-power`) reverts to all-NASA. COVERED: live daily path, the 2025 (Jun1-Oct30)
> + 2026 (Jun1+) weather backfills + the season-trend archive (regenerated with CPC), the Google-Sheet
> logger (new `weather_source` provenance col AA -> RE-DEPLOY the Apps Script + clear the
> data_dictionary tab), ALL page source citations (rainfall=NOAA CPC, temp/humidity=NASA POWER; SSR<->JS
> twins + prototypes), and CI deps (netCDF4/xarray added to daily.yml). IMD is NOT used in production
> (non-commercial licence) - it was the offline validation truth only. Full analysis + decision:
> `Rain_Data_Provider_Analysis_and_Decision.docx`. Verified live: grid.json on `provider: cpc`,
> Bengaluru rain_14d 194->62mm (dengue saturation-robust, typhoid + moderate-rain South correctly drop),
> SSR<->JS parity OK, full SSG builds. Note CPC is ~0.5deg (same as NASA POWER), gauge-based; its edge
> is concentrated in the early/shoulder season (peak monsoon saturates the rain term regardless).
>
> **NEWEST (2026-06-14, UI-honesty pass - breeding-weather drivers (#6) + contribution-based breakdown (#2 + #4) - committed + pushed):**
> Two launch-blocker "does it make sense to the user" fixes from the like-to-like review, both verified on BOTH flows
> (parity_check OK, CLS-0) with the contribution math reconciled across ALL 912 cells (0 mismatches).
> - **#6 Breeding-weather card now shows what actually DRIVES the weather sub-score** (was humidity + 7-day rain + a
>   static "Mosquito peak: Dawn & Dusk" tile). Tiles are now Temperature (near the 29C breeding optimum, the dominant
>   45% term - previously invisible), 14-day LAGGED rainfall (the window the mosquito score actually uses, was 7-day),
>   Humidity, and the estimated Stagnation index. New thermometer WX_TEMP icon (replaced WX_PEAK); heading "Breeding
>   weather conditions this week"; subtitle "What weather means for mosquito breeding."
> - **#2 + #4 "Why this score?" rebuilt to CONTRIBUTION bars.** Each signal's bar length + its "+N" = that signal's
>   largest-remainder (Hamilton) share of the DISPLAYED integer score, so the three contributions SUM EXACTLY to the
>   score in every mode (agree x1.08, disagree x0.96, forecast cap 69 all absorbed because we apportion the final
>   score, not the pre-multiplier base). Bars are coloured per signal (weather #15ACA5 / search #7C6CD6 / lab #3661B0);
>   the raw value + weight stay as small provenance; a per-signal "what this measures" line addresses #4 (each 0-100 is
>   a DIFFERENT kind of measure: breeding favourability vs relative search interest vs lab-vs-35%-reference); a footer
>   reconciles "Lab N + Weather N + Search N = score" followed by the engine note. Forecast cells drop the misleading
>   empty lab bar for a muted "no confirmed data" tile. Rows ordered by contribution desc (driver signal first). Bar
>   width = floor(pt/score*100+0.5) (integer, so byte-parity-safe across JS/Python).
> - **Desktop layout (user-reviewed, several iterations):** the "three separate bars" option was chosen over a single
>   stacked bar, laid out as COMPACT VERTICAL TILES inside the existing 3-col #s-why grid. Fixed a tile overlap (the
>   long value collided with the label in the 152px column -> label + +N share one row), fixed cramped day-over-day
>   badges (centered flex + 6px gap), and compacted the tiles so the dial card (#s-week) and the breakdown card
>   (#s-why) are EQUAL HEIGHT (603px, both content-filled, no stretch gap).
> - **Engine/parity:** a new contribs()/_contribs() largest-remainder helper is byte-identical across assets/js/mobile.js
>   + assets/js/desktop.js + src/build_site.py; the SIG map gained a per-signal colour (.c), shortened labels, and the
>   "what" microcopy (tag dropped); per-signal colours are emitted INLINE (no mobile.css/desktop.css churn); the desktop
>   s-why SSR twin stays byte-identical (parity_check OK on the gulbarga forecast-cap fixture). The mobile breakdown is
>   JS-only and stacks full-width.
> - **Still mock-flagged (NOT yet addressed - points #1/#3):** lab positivity is still mock, so the lab "+N" + the
>   "confirmed positivity leads" note are driven by a SIMULATED number. The all-red "rising vs yesterday" badges are now
>   live (history has a prior day); toning them down + switching the crawlable no-JS table (still RAW values) to
>   contributions are open optional follow-ups.
>
> **2026-06-14 (point #5 EXACT cross-year SEARCH YoY - committed + pushed):** the season-trend "this monsoon
> vs last year" SEARCH comparison is now EXACT, not directional. NEW `src/refresh_trends_timeseries.py` (env/Actions-
> secret keys, window `2025-06-01..today` so both years share ONE Google normalisation) does a weekly per-state
> interest-over-time re-pull -> `data/backfill/trends_history.json`. `src/build_archive.py` gained a `--search-only`
> mode that recomputes the EXACT search ly+ty from it (weather untouched, + a thin-pull guard that preserves a city's
> last-good block when its state returns no series this run rather than degrading to the national-mean fallback); and
> `--daily` NO LONGER injects the live directional search value - it only length-pads search ty so trend.js's
> `search.ty.length===asOf+1` guard keeps holding between weekly refreshes. `pull_history` was extracted from
> `backfill_trends.py` and is shared by both pullers. Wired into `daily.yml` as a MONDAY-gated step (aligned to the
> 1-Jun season week boundary so as_of advances the same day; new `force_search_refresh` workflow_dispatch input to run
> it on demand) - deliberately NOT a separate `weekly.yml`, because the minified single-line archive JSON must have
> exactly one committer or two workflows git-conflict. Cost ~132 SerpApi searches/Mon (~817/mo in-season of 5 x 250 =
> 1,250 free; keys roll over on quota/error). Verified offline (0 quota spent): full rebuild reproduces the committed
> archive on ly + ty[0] across all 228 cities; --daily is pad-only (no directional injection, weather still grid-
> sourced); --search-only recomputes exact (225 updated / 3 null-geo preserved); no-key run aborts cleanly; YAML +
> step order valid; adversarial review verdict SHIP. FIRST LIVE RUN: next Monday cron, or Actions -> Run workflow with
> force_search_refresh=true (watch for `calls made: ~132` + `recomputed EXACT search`). Lab positivity is still mock.
>
> **LATEST (2026-06-14, COMMITTED + PUSHED to master; staging redeploying):** a large multi-stream session shipped
> ALL of the items the older banner below lists as PENDING/NEXT. 14 commits `1d3f36e`..`3438705`:
> - **Mobile first-fold redesign COMMITTED** (`1d3f36e`) - the dial/legend/chip/tabs/breeding-weather/breakdown
>   redesign detailed in the older banner is now live (was uncommitted).
> - **DESKTOP port + reference redesign** (`c5880a7` port; `671e95b` v2; `3fe3db5`/`49046f4`/`25f1e59`/`bdf572b`/`3438705`
>   refinements): the mobile redesign re-laid into the 2-col desktop flow, then restructured to the reference design -
>   a 3-COLUMN first fold (Quick Links sidebar | score card | "Why this score?" breakdown, the breakdown PROMOTED
>   above the fold via new byte-identical SSR twins), a mobile-style city-selector pill, Quick Links as real
>   `<a href="#...">` SEO anchors (the URL hash updates on click) + scroll-spy, in-card 21px section titles, the method
>   section moved after the trend section + renamed "How we calculate the score", a desktop share dock using the
>   mobile band-tiered copy, the share-modal image capped (no scroll), consistent 30px gaps, and a BIG centered dial
>   (188px) with the 4 diseases stacked below + chip/note/Share snug at the bottom, equal-height with the breakdown.
>   `scripts/parity_check.js` was extended with a desktop `.fw-pre-d` twin; BOTH flows stay PARITY OK (CLS-0).
> - **HISTORICAL BACKFILL shipped** (`b9ea4f9` NASA weather, `d75c1ac` SerpApi trends, `7023f55` archive runner,
>   `4ccdd2c` trend wiring): build_weather.py gained `--start/--end/--as-of` (date-ranged NASA POWER); a new SerpApi
>   per-state interest-over-time puller (`config/in_state_geo.json` + `src/backfill_trends.py`); `src/build_archive.py`
>   recomputes per-city REAL weekly WEATHER + SEARCH curves for 2025 (full season) + 2026 (to date) into the COMMITTED
>   `data/archive/trend_series.json` (~47KB). The season-trend module now shows the REAL last-year line on the Weather +
>   Search tabs (Overall + Labs stay on the deterministic mock until real lab positivity lands). `data/backfill/` is
>   gitignored (regenerable intermediates); only `data/archive/` is committed.
> - **SHEET LOGGER BACKFILL** (`42a27a4` CSV, `57f85e4` XLSX): `src/backfill_sheetlog.py` replicates the live `raw_data`
>   26-col schema for historical dates and emits `.xlsx` workbooks (default) whose K/L/S/T/U/V columns are REAL baked
>   Apps Script formulas (or literal-value CSVs) for 2026-06-01..08 (append to `raw_data`) + 2025-06-01..10-30 daily
>   (separate spreadsheet, ~173K rows). Outputs to `data/backfill/sheet/` (gitignored); the user imports them.
> - **DAILY ARCHIVE REFRESH WIRED** (`913b363`): `build_archive.py --daily` extends the committed
>   `data/archive/trend_series.json` this-year (ty) vectors from `data/grid.json` ONLY (CI-safe, needs no backfill
>   inputs); `daily.yml` runs it after build_daily (continue-on-error) and adds the archive to its commit. So the
>   season-trend "this year" line now grows on every cron run. WEATHER is EXACT (grid signals.weather are the same
>   NASA family scores the backfill used); SEARCH this-year uses the live cross-state value (consistent with the
>   dial + breakdown), so the cross-year SEARCH YoY is DIRECTIONAL not exact - making it exact needs a weekly
>   per-state TIMESERIES re-pull (SerpApi quota; NOT yet added - offered to the user).
> - **TEAM DOC:** `Fever_Watch_Project_Document.docx` at the repo root - a 15-section architecture + tech-stack
>   overview with a full worked example of the score math (Pune, all four layers). Generated locally via docx-js
>   (build script in a temp dir), NOT committed; the latest copy is `Fever_Watch_Project_Document_v2.docx`.
> - **EVERYTHING THROUGH `913b363` IS PUSHED + LIVE** (the 2026-06-14 staging deploy ran green; the daily cron
>   commit `080d324` was merged - kept the new-schema grid/history, took the cron's weather/trends).
> - **STILL PENDING (user-gated):** the real PharmEasy lab-positivity Google Sheet (unlocks the Overall + Labs real
>   trend and flips positivity off mock); the mobile past-7-days trail strip (DEFERRED, no design yet); production
>   `base_url` + reverse-proxy; brand sign-off; the `mira-bhayandar` local-name confirmation; coords QA.
>   (DONE 2026-06-14: the weekly per-state TIMESERIES re-pull for EXACT search YoY - see the NEWEST banner at top.)
>
> **SUPERSEDED 2026-06-13 banner (the mobile redesign below is NOW COMMITTED `1d3f36e`, and its PENDING/NEXT is all
> DONE - see the 2026-06-14 banner above):** a full
> mobile FIRST-FOLD + sections REDESIGN matching the updated Figma (file `m2JNYbCaHkS3rGpKoU8J0S`, node 49-1303).
> Specs: `.claude/plans/fever-watch-first-fold-redesign.md` + `fever-watch-figma-benchmark.md`. SSR/JS byte-parity
> held throughout (`scripts/parity_check.js` PARITY OK = CLS-0). Desktop flow UNTOUCHED. 5 independent QA passes,
> all PASS (no blocker/high). Changes (assets/js/mobile.js + src/build_site.py twins, assets/css/mobile.css,
> prototypes/tokens.css, assets/js/trend.js):
> - **PIPELINE (src/build_daily.py):** history.json day schema expanded to per-disease `cells` (was blend-only);
>   grid bakes `blend.delta_1d` + per-cell `delta_1d` (vs yesterday), `weather.stagnation`={level} (estimated index
>   = rain_14d-rain_7d), and `payload.periods` (today always; week at >=7 committed days; month at >=28). history.json
>   now has 2 committed days. NO trail/standing_mm baked (review = dead weight; history accrues the raw scores).
> - **DIAL:** proportional gauge - fill = overall-score % of the 270deg arc, subdivided into one ROUNDED segment per
>   disease sized by score share, in DISEASE IDENTITY colours (dengue #F1839D / malaria #887ADE / chikungunya
>   #46CFE7 / typhoid #4681EF; tokens.css --dis-*). First segment starts at the track start (no nudge). Centre =
>   dark score + "/ 100" inline + "Overall fever risk". Identity colours also on the legend + breakdown dots.
> - **LOCATION:** one full-width card (red SVG map-pin + city + "Change v" caret; date moved OUT); centered note
>   "Updated {date}. Available in select cities." H1 KEEPS the city, drops the comma. Hero gradient is now a pure
>   180deg vertical fade #0A534F -> #307471 -> #89B8B9 (the 170deg angle was leaving the bottom-centre dark).
> - **LEGEND** "Name : score" (no emoji, no Top concern). **BAND CHIP:** MODERATE -> gold (#F5B630 beacon /
>   #FFF8E3 bg / #F0D27A border), other bands keep the locked risk ramp; animated `.beacon`.
> - **PERIOD TABS** (Today / This week / This month, NO year) above the dial, data-gated by grid.periods (only
>   "Today" renders now). **KNOW MORE** -> methodology bottom sheet. Share-nudge bar made PERSISTENT (x/dismiss removed).
> - **BREEDING WEATHER** cards: outline line-icons + "Label . value" (CSS-dot separator, not a middot char) + mock copy
>   (stagnation keeps "(estimated)"). **BREAKDOWN:** dark bold values + neutral grey bars; per-signal trend badges
>   (red-up = rising / green-down = easing vs yesterday) NOW BUILT - build_daily stores per-signal values daily in
>   history.json `sigs` ([weather,trends,positivity] per city/disease) and bakes `cell.sig_delta`; the badge (mobile.js
>   sigBadge/sig) self-activates from 2026-06-14 (first yesterday carrying sigs). End-to-end verified via a simulated
>   yesterday. **PRECAUTIONS:** emoji -> line SVG icons (shield/syringe/thermometer/stethoscope), brighter teal titles.
>   **SEASON-TREND** verdict -> a single pink "+N% higher than last year" pill (trend.js / tokens.css).
> - **Ticker** label "Today's risk" -> "Live". Removed dead CSS/JS (old single-arc gauge, pills, beacon helper, nudge).
> - **DAILY COLLECTION (now comprehensive):** every build stores per-city blend score + per-disease `cells` +
>   per-signal `sigs` in history.json (rolling 35 days). So week/month dial aggregates AND per-signal badges all
>   accrue from real daily data going forward - no further wiring needed for forward collection.
> - **PENDING / NEXT (a new session each):** (1) DESKTOP parity port - the ENTIRE mobile redesign re-laid-out for the
>   2-col desktop shell (one scope): TOC relabel to mobile section names (This week->Overall fever risk, Scoring
>   methodology->Why this score, +Breeding weather, What to do->Take the right precautions, etc.), new
>   dial/legend/chip/tabs + breakdown (horizontal 3-signal) + breeding-weather + precautions, remove the
>   "{city}, this week / Updated... signal mix behind it" header, port hero/location/gradient; desktop H1 KEEPS the
>   city (consistent with mobile, per user). Above-fold _desktop_pre<->desktop.js must stay byte-identical (CLS-0).
>   (2) HISTORICAL BACKFILL (data-eng): season-to-date (Jun 1-12 2026, before history started) + a one-time LAST YEAR
>   (Jun 1-Oct 30 2025) to power week/month dial aggregates + REAL YoY trends (would replace trend.js/_t_lypeak's
>   deterministic mock last-year). FEASIBILITY: NASA POWER weather = REAL & backfillable (historical time series);
>   SerpApi trends = real but weekly granularity (+API quota); positivity = MOCK (no real history - same fidelity as
>   today's live data, since live positivity is mock). NEEDS: build_weather date-range/"as-of" support + a backfill
>   runner that recomputes per-date grids + a COMPACT seasonal/last-year store (a full season x 228 cities x sigs would
>   bloat the committed history.json to many MB - keep history.json as the rolling 35d window, add a separate archive).
>
> LATEST SHIPPED (2026-06-12, commits `9d9ba9b` + `ad9ccf9` + `b71d987`, all deploy runs green, verified
> live): the **#5 share-card redesign in production** - new per-city og:image (landscape) + WhatsApp share
> image (portrait, 11 language variants), one CI renderer feeding the page's share modal, ~67KB cards with
> idle pre-warm. Earlier shipped layers (trend module, 4-disease set, legal disclaimers) remain live.
>
> **2026-06-12 (SHARE-CARD PRODUCTION PORT - the #5 redesign SHIPPED into the pipeline; commits `9d9ba9b`
> port, `ad9ccf9` modal+Actions, `b71d987` weight cut; all live-verified on staging):** the dual-QA'd,
> content-team-approved share-card design is now the PRODUCTION renderer. What changed:
> - **`src/build_share_cards.py` + `src/textshape.py` REPLACE `src/build_og.py` (deleted).** Per city it bakes
>   BOTH `assets/img/og/{id}.jpg` (1200x630 landscape og:image - same path contract, so build_site.py is
>   untouched) AND `assets/img/share/{id}.jpg` (900x1200 portrait, the WhatsApp share image; new gitignored
>   dir). Stack: parametric SVG with ALL text pre-shaped to outlines via HarfBuzz (uharfbuzz; y_offset/advance
>   NEGATED into SVG space - the sign convention that garbled Nastaliq in QA) -> vendored resvg v0.47.0
>   (`tools/resvg/`, win64 + linux-x86_64, see its README; resvg's own <text> shaping drops the Devanagari
>   aa-matra, so it is never used) -> 2x -> LANCZOS -> opaque JPEG q75 + 4:2:0 (avg ~67KB). Fail-loud:
>   collects per-city errors and exits nonzero (never publishes a partial set). The "Up from N last week"
>   pill is PORTRAIT-ONLY by design and self-activates once `data/history.json` has a day 4-10 days back
>   (history started 2026-06-12 -> first pills ~16 Jun; until then the layout re-pads; demo render verified).
> - **Regional sub-line for 223/228 cities:** `config/city_names_local.json` now carries native-script
>   city+state names (11-language state->variant map in build_share_cards.py; approved fallbacks:
>   Goa/J&K/Ladakh/Sikkim/Assam/A&N/Chandigarh -> Hindi, 5 NE cities -> English card). Generated by AI +
>   dual independent AI verification; ONE flag for human review (mira-bhayandar मीरा vs मिरा) ->
>   `docs/local_names_review.md`. The WhatsApp bar's regional phrase localizes per language too.
> - **Fonts vendored:** `tools/fonts/` = static Inter 600/700/800 + 9 Noto variable script fonts (~6.6MB,
>   committed - build-time only; deliberately OUTSIDE assets/ so build_site's copytree never ships them to Pages).
> - **Adversarially code-reviewed (2 agents) before commit; all findings fixed:** prev pill now reads
>   grid.json `blend.prev_score` (build_daily owns the nearest-to-7d lookup; my reimplementation had a
>   wrong tiebreak - the blocker), equal-score pill omitted, fail-loud on missing driver/generated_at,
>   portrait tier_pad re-pads the csize*0.06 advance too, mobile Save-image failure opens the image URL,
>   desktop `.pop` got max-height+scroll (the taller portrait preview clipped on short laptops), dead
>   LOGO vars + the old `.sharecard`/`.sc-*` DOM-mock CSS removed from both flows.
> - **`assets/js/share.js` REWRITTEN (canvas renderer deleted):** the client now FETCHES the baked portrait
>   (`imageUrl`/`loadCard`, cache-busted with the grid generated_at digits, same scheme as og:image) and the
>   share modal preview on BOTH flows shows that image (`.sharecard-img`) instead of the old DOM mock - one
>   renderer, zero drift. WhatsApp/Save/Copy behavior unchanged (Web Share API w/ file on mobile,
>   download+wa.me fallback); degrades to text-only if the image 404s.
> - **CI:** daily.yml + deploy.yml now `pip install "Pillow>=11,<13" uharfbuzz==0.55.0 fonttools==4.63.0`
>   (pinned), `chmod +x` the vendored linux resvg, and run `build_share_cards.py` instead of `build_og.py`;
>   the apt fonts step (dejavu + noto-color-emoji, only needed by the old Pillow card) is REMOVED.
>   grid.json was regenerated locally so the committed grid carries name_local/state_local for all 223 cities.
> - **Share-image weight cut (user feedback, same day):** portrait now 900x1200 (was 1080x1440; WhatsApp
>   recompresses past that anyway) + JPEG q75 with 4:2:0 chroma subsampling on BOTH outputs (q70 visually
>   verified clean, q75 keeps margin) -> avg share card 110KB -> 67KB (-40%), og ~58KB; AND both flows now
>   PRE-WARM the current city's share image via requestIdleCallback (re-warmed on city switch, guarded
>   per-city), so the modal preview is a 0-byte cache hit (~14ms) instead of a cold fetch on first tap.
> - **Follow-up same day (user feedback):** share-modal CTA buttons moved ABOVE the share text on both flows
>   (first-fold visibility) + the mobile preview image capped at 44vh so image+CTAs fit one fold (verified
>   headlessly at 390x844 + 1366x768; NOTE: measure sheet geometry AFTER the 250ms slide-in - same-tick rects
>   read mid-animation). The "Up from N last week" pill is portrait-only BY DESIGN and data-dependent: it
>   self-activates ~16 Jun once history.json has a day 4-10d back (demo render verified). GitHub Actions bumped
>   to Node-24 majors (checkout v6, setup-python v6, configure-pages v6, upload-pages-artifact v5,
>   deploy-pages v5) ahead of the 2026-06-16 forced default.
>
> **2026-06-11/12 (the #5 share-card DESIGN JOURNEY that produced the port above - for the record; working
> files in `dist/_share_options/` are gitignored/local-only, the committed `src/build_share_cards.py` is now
> the design source of truth):**
> - **Why the first attempt failed (diagnosed):** the rejected 2026-06-11 renders came from Pillow 9.5.0 with
>   raqm=False (no Indic shaping -> broken matras/conjuncts) drawing at 1x (no anti-aliasing -> jagged arcs).
> - **Render-stack bake-off:** 3 prototypes built + adversarially verified (A html+headless-Chromium 9.5/10,
>   B svg+resvg 9/10, C pillow+raqm 9/10). USER PICKED B. Key finding: resvg's native <text> drops the
>   Devanagari aa-matra (both resvg_py and CLI v0.47) -> all text is pre-shaped to outlines via HarfBuzz,
>   which also makes output byte-stable cross-platform.
> - **Portrait iterations (user feedback):** 1080x1440 canvas, square opaque corners, floating header bar
>   with symmetric ~55px top/bottom margins, 0/100 labels centered under the arc caps, one icon axis +
>   one text axis for the info/CTA/WhatsApp rows, info-row label/value gap fix.
> - **15 language-variant mocks + DUAL independent AI QA (script shaping + grammar/colloquial):** found +
>   fixed a y_offset sign bug (garbled Nastaliq Urdu, low Assamese nukta) and the English variant's font
>   fallback. Content team then: middots -> thin rules everywhere; Konkani + Urdu + Nepali + Assamese all
>   replaced with Hindi (final = 11 languages / 15 QA cards); approved the strings
>   (`dist/_share_options/b_resvg/variants/STRINGS_FOR_QA.md` was the sign-off sheet).
> - **Landscape 1200x630 built to the user's reference mock** (two columns, no prev pill / no WhatsApp bar,
>   centered gold CTA) + its own dual-QA round (2 fixes: odia bottom-anchor tier_pad, descender clearance).
>
> **2026-06-11 (LATER: page fixes + legal disclaimers; committed + pushed + deployed, commit `6ff6c48`):**
> four review fixes on top of the UI batch, all verified headlessly and live on staging:
> - **Mobile leaderboard "your city" pinned row no longer cuts off:** the highlight band is now FULL-BLEED to the
>   card edges (`margin: 4px -18px 0; padding: 10px 18px` = the card's 18px padding) so it has breathing room
>   around the rank + score instead of cutting flush against them; columns stay aligned (verified the pinned rank
>   sits at the same x as the other rows). `.lbrow.lb-pinned` in `assets/css/mobile.css`. Desktop was already fine.
> - **Legal disclaimers (from counsel) baked in.** MEDICAL disclaimer ("Fever Watch is a risk indicator and not a
>   diagnosis or representation of actual case counts. It is for informational purposes only and should not
>   constitute medical advice; please consult a doctor for any symptoms or health concerns.") now leads the FOOTER
>   (every page) + the content-bottom `fw-disc`. DASHBOARD/DATA note ("This is a daily updated dashboard where we
>   compute a monsoon-risk score (0-100) based on multiple data inputs, including weather data, Google search
>   trends, and aggregate data from PharmEasy Labs and its Partner Affiliates.") sits at the END of the collapsible
>   "How we calculate this" body (`.dashnote`, last child of `#methbody`, hidden until "Show"). Constants
>   `MEDICAL_DISCLAIMER` + `DASHBOARD_NOTE` in `build_site.py`; mirrored as `DASHNOTE` in `mobile.js`/`desktop.js`;
>   `.dashnote` CSS in `tokens.css`. The footer lab attribution updated to "PharmEasy Labs and its Partner
>   Affiliates"; the legal "0-100" en-dash normalized to an ASCII hyphen per house style.
> - **CTA landing pages wired:** "Book a fever panel test" -> `pharmeasy.in/diag-pwa/content/Fever_LP?src=feverwatch`;
>   "Book a consult" / "Not sure? Talk to a doctor" -> `pharmeasy.in/doctor-consultation/landing?src=feverwatch`.
>   The big `.ctabig` buttons are now `<a>` links (CSS set to render as block / inline-block). SSR `CTA_HREF` +
>   new `CONSULT_HREF` in `build_site.py`; both flows' `ACTIONS` carry `href`; `do_sec`/`actionsCard`/`doSection`.
> - **Copy:** dropped ", more coming soon." everywhere -> just "Available in select cities." (SSR + both flows + prototypes).
> - **OPEN (minor, user to decide):** (a) align the OTHER lab-attribution mentions (FAQ, methodology data-sources
>   list, trend sources line, score-card note) to "PharmEasy Labs and its Partner Affiliates"; (b) whether to
>   repoint the footer's pre-existing "Doctor consult" link (`/online-doctor-consultation/`) to the consult LP.
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
> - **(#5) WhatsApp/OG share-image redesign - SHELVED 2026-06-11 (user paused; card design rejected):** Phase 1
>   data foundation is COMMITTED + KEPT (commit `cc06e28`): real prior-week `prev_score` via a rolling
>   `data/history.json` + `name_local`/`state_local` merge from `config/city_names_local.json` in `build_daily.py`
>   (+ `daily.yml` commits `history.json`). Harmless dormant plumbing - the current `build_og.py` does not read it.
>   The Phase 2 card re-port (rebuilt `build_og.py` to a Claude-Design HANDOFF: radial surface, a 3-segment arc
>   gauge with the score below in gold, Lucide icons, `Chikungunya` with NO bracket score, `Kids & elderly`) was
>   built + rendered but the user rejected the look ("banner designs not good at all"). It is preserved in
>   `git stash@{0}`; `build_og.py` in the tree is back to the committed original glass-card design; `share.js`
>   (canvas) was never touched. AUTHORITATIVE design for when this reopens = the Claude-Design handoff bundle
>   (renderer `share-card.js`); URL + extracted location + the full corrected spec are in memory
>   (share-image-redesign-plan). Do NOT resume the card redesign unless the user reopens it.
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
| Share-image client (`assets/js/share.js`) | **DONE (rewritten 2026-06-12)** | no client rendering: fetches the CI-baked portrait (`assets/img/share/{city}.jpg`, cache-busted like og:image); modal previews the same file; idle pre-warm per city -> 0-byte cache-hit open; Web Share API w/ file on mobile, download+wa.me fallback |
| Front-end design: 2 clickable prototypes (mobile + desktop) | **DONE (frozen)** | the locked design source; now extracted into the SSG runtime (`assets/`), so prototypes are reference-only |
| Co-branded nav lockup (`assets/img/fever-watch-lockup-white.svg`) | **DONE** | rendered both navs |
| **SSG `/fever-watch/{city}` pages (device-adaptive)** | **DONE (full pre-render)** | `build_site.py` -> 228 pages; bakes the ENTIRE page (hero, score, why-this-score table, full methodology, what-to-do, 228-city table, FAQ, reads) + clean H1>H2>H3 hierarchy. Section 9 (AS BUILT). |
| Device-adaptive runtime (`assets/css,js` + `fw-loader.js`) | **DONE (both flows seamless, CLS 0)** | first paint = the designed view on BOTH flows (mobile `.fw-pre-m` card; desktop `.fw-pre-d` shell = searchHero + sidebar TOC + gauge/heatmap), server-rendered byte-identical to the JS so hydration is a no-op repaint; verified headlessly CLS 0 on both (desktop was 0.79); renders instantly from `window.FW.seed` then loads the full grid in the background; no boot-hide; per-city H1 + H2/H3 + live FAQ verified both flows |
| Per-city share cards (`src/build_share_cards.py`, replaced build_og.py 2026-06-12) | **DONE - LIVE** | 228 x 2: og 1200x630 + portrait 900x1200, the QA'd new design w/ native-script sub-line (11 languages); SVG + HarfBuzz outlines + vendored resvg; JPEG q75 ~58-67KB; `?v={generated_at}` cache-bust; fail-loud |
| Brand assets (`src/build_assets.py`) | **DONE (placeholder)** | favicon/PWA/OG via Pillow; swap for final art before launch |
| **Pages deploy (`.github/workflows/deploy.yml`)** | **DONE - LIVE** | builds (build_assets + build_share_cards + build_site) + publishes on push to master; staging (real trends + mock positivity), robots Disallow. Pinned pip deps (Pillow/uharfbuzz/fonttools); actions on Node-24 majors (2026-06-12). |
| **Daily data cron (`.github/workflows/daily.yml`)** | **DONE - LIVE** | daily 01:30 UTC + workflow_dispatch: weather + real trends -> grid -> commit data back [skip ci] -> OG + SSG -> deploy. First run verified green (run 27069051641). |
| **Google Trends (SerpApi, 5 keys)** | **LIVE (real)** | 5 keys in Actions secrets (verified `5/5` in CI); `trends.provider=cached`; `build_trends.py` pulls real state-level interest daily. Fixed a `GEO_MAP_0` bug (GEO_MAP 400s on single query). ~10 searches/refresh; ~1,000+/mo headroom. |
| Lab positivity feed | **MOCK** | the last real feed; needs the PharmEasy Sheet published-CSV URL -> flip `positivity.provider=googlesheet` |
| Risk beacon (pulsing band light) | **DONE** | inline next to the band label, both flows; colour=band, speed=urgency; CSS in tokens.css; reduced-motion fallback; verified live |
| Google Sheets logging (`src/sheetlog.py`) | **LIVE (verified)** | webhook secrets set; a run pushed 1,140 raw rows OK. Logs sheet = `1Iz9nAf38...`. `raw_data` = raw inputs (A-I) + `score`/`band`/`mode` as **in-sheet formulas** (mirror consolidation.json); `daily_summary` = date x disease avg + daily avg/peak + **city overall blend** (0.75*peak+0.25*avg), all by formula. See `docs/sheets_logging.md` |
| Card text overflow (long city names) | **DONE** | `build_share_cards.py` size tiers (portrait 108/84/64px, landscape 92/68/52px by name length) + tier_pad keeps the layout bottom-anchored; verified Bhubaneswar / Thiruvananthapuram |
| **"This monsoon vs last year" trend module** | **DONE (mock series)** | `assets/js/trend.js` widget + `build_site.py _trend_*` SSR, above the FAQ on both flows; verdict + chip + tabs + inline-SVG chart + tooltip + collapse + desktop small-multiples; deterministic per-city mock from real scores. **Last-year is a STABLE per-city baseline** (`lyPeak` seed, band 64-95) so "last year peaked at X" never drifts; this-year's real score floats against it, so the chip/verdict stay dynamic. Python<->JS series **byte-identical** (Node parity); recomputes on city switch; **desktop CLS still 0**. Swap in `data/history.json` for the real last-year line. |

Everything runs on the **Python standard library** (no third-party deps). `requirements.txt` is essentially empty.

---

## 3. Architecture & stack

Serverless by design: scheduled scripts write static JSON, a static device-adaptive site reads it.

```
GitHub Actions (cron)                          [BUILT - daily.yml, LIVE]
  daily.yml : build_weather + build_trends(SerpApi x5) + build_daily -> grid.json ; commit data back ;
              build_share_cards + build_site -> dist/ ; deploy   (daily 01:30 UTC + workflow_dispatch)
  (trends folded into daily.yml at a daily cadence; no separate weekly.yml)
       |
       v
data/*.json  (committed; weather.json, grid.json[, trends.json])
       |
       v
SSG: src/build_share_cards.py (per-city og + share cards) + src/build_site.py   [BUILT]
   -> dist/fever-watch/{city}/index.html per city (SEO baked + #fw-app) + landing + robots/sitemap/manifest
       |
       v
Static front end (device-adaptive): one URL serves the MOBILE flow or the DESKTOP flow, chosen at load
(media-gated CSS in <head> + fw-loader.js injects the active flow's JS). Reads grid.json for switching + leaderboard.
Hosting: GitHub Pages; production = pharmeasy.in subpath via reverse-proxy (mirrors Mosquito Watch).
```

### The 3-signal engine (the heart, built + tested)
- **Weather / breeding** (leading): rain from NOAA CPC + temp/humidity from NASA POWER, per-disease-family shaping (see scoring.json). Daily.
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
- **Weather source (hybrid, default `cpc`):** rain from NOAA CPC (gauge-based, US public domain), temp/humidity from
  NASA POWER (US public domain / CC0; ~1-3 day latency, no forecast - both fine for a trailing breeding index). Revert
  with `--provider nasa-power`. Open-Meteo kept behind the interface as a dev/forecast-only option (free tier non-commercial).
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
- `build_weather.py` -> `data/weather.json`: NOAA CPC rain + NASA POWER temp/humidity per city, per-family sub-scores. Fail-loud guard.
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
manifest), `src/build_share_cards.py` (per-city og + share cards), `src/build_assets.py` (brand placeholders), and the extracted
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
4. **Replace placeholder brand art** (favicon/PWA icons; the per-city OG cards are now the real design),
   **coords QA, compliance/counsel pass, 3-signal backtest** before any public "early warning" claim.
   (Self-host Inter: DONE 2026-06-08. Share-card redesign #5: DONE + LIVE 2026-06-12.)

---

## 8. How to run / build / test

```
# Data (from the project root)
python scripts/gen_cities.py            # regenerate config/cities.json (228 cities)
python src/build_weather.py             # NOAA CPC rain + NASA POWER temp/humidity -> data/weather.json   (daily; ~2 min for 228 cities)
python src/build_daily.py               # compose the grid (reads signals.json) -> data/grid.json
python src/build_trends.py              # WEEKLY: SerpApi -> data/trends.json (needs SERPAPI_KEY in env)
python src/consolidate.py               # smoke-test the ensemble engine

# Flip a signal live (no code change): edit config/signals.json
#   positivity.provider: "mock" -> "googlesheet"  (+ set googlesheet.csv_url)
#   trends.provider:     "mock" -> "cached"        (after a weekly build_trends run)

# Build the static site (after grid.json exists). Order matters: OG cards BEFORE pages.
python src/build_assets.py              # one-off: brand favicon/PWA/OG placeholders -> assets/img/
python src/build_share_cards.py         # each data refresh: per-city og/ (1200x630) + share/ (1080x1440) cards
                                        #   (needs Pillow + uharfbuzz + fonttools; uses tools/resvg/)
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
- **Per-city OG + share cards (REPLACED 2026-06-12; see the 2026-06-12 banner entry):** `src/build_share_cards.py`
  renders `assets/img/og/{city}.jpg` (1200x630 og:image, two-column landscape) AND `assets/img/share/{city}.jpg`
  (900x1200 portrait, the WhatsApp share image w/ the regional WhatsApp bar) from grid.json. Design = the QA'd
  2026-06 card: radial dark-teal surface, floating header lockup, 3-segment arc gauge + gold score, band pill,
  top-concern row, native-script sub-line per the 11-language state map. No emoji fonts needed (all icons are
  vector paths); text is pre-shaped to outlines (src/textshape.py). Run BEFORE `build_site.py`. Both output
  dirs gitignored; fonts at `tools/fonts/`, resvg at `tools/resvg/` (committed).
- **OG cache-bust:** `og:image` + `twitter:image` carry `?v={og_version(generated_at)}` (compact YYYYMMDDHHMMSS) so social
  platforms re-fetch the preview when scores are recomputed; JSON-LD `primaryImageOfPage` and the landing OG stay clean.
- **Colors reconciled:** `tokens.css --risk-*` now matches the JS `RISK` map = the locked brand ramp. (grid.json still
  carries the old consolidation.json band colors, unused by the front-end - regenerate or ignore.)

### The page contract (original spec, mostly as-built above)

### The page contract (what `build_site.py` emits, what the front-end expects)
- `<head>`: per-city `<title>` = `{City} Monsoon Fever Risk, {DD Mon YYYY} | Dengue, Malaria, Chikungunya, Typhoid | Fever Watch`
  (landing = `Monsoon Fever Risk in India, {date} | ...`; date re-stamped daily via `_fmt_date_js`, IST; also feeds `og:title`/`twitter:title`),
  meta description, **canonical** = `base_url + fever-watch/{city}/`, Open Graph/Twitter,
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
config/   site cities(228) diseases(4) scoring consolidation signals city_names_local(223 native-script names)
data/     weather.json  grid.json        (trends.json appears after a weekly build_trends run)
scripts/  gen_cities.py                  one-off city-config generator
src/
  build_weather.py  build_daily.py  build_trends.py  consolidate.py  weather_score.py  httputil.py
  build_site.py     SSG -> dist/fever-watch/ (228 pages + robots/sitemap/manifest), stdlib
  build_share_cards.py  per-city share cards -> assets/img/og/{city}.jpg (1200x630) + assets/img/share/{city}.jpg
                    (900x1200); SVG + HarfBuzz pre-shaping (textshape.py) + vendored resvg; JPEG q75 ~58-67KB
  textshape.py      HarfBuzz -> SVG glyph outlines (the Indic-safe text layer for the cards)
  sheetlog.py       best-effort Google Sheet logger (run_log + raw_data via Apps Script webhook; stdlib)
  build_assets.py   placeholder favicon/PWA/OG -> assets/img/ (Pillow, stdlib fallback)
  providers/        weather: nasa_power(DEFAULT), open_meteo(alt), base, __init__(registry)
  signals/          base, mock(default), googlesheet, serpapi, cached, __init__(registry, config-driven)
prototypes/         mobile.html  desktop.html  tokens.css   <- FROZEN design reference (extracted into assets/)
assets/
  css/  mobile.css  desktop.css          <- extracted from prototypes (tokens.css copied from prototypes/ at build time)
  js/   geo.js  share.js  faq.js  trend.js  fw-loader.js  mobile.js  desktop.js   <- the device-adaptive runtime (boot() at the END of each IIFE)
        faq.js = client FAQ recompute (mirrors build_site faq_items); trend.js = "this monsoon vs last year" widget (mirrors build_site _trend_series)
  fonts/ inter-latin-{400,500,600,700,800}-normal.woff2 (self-hosted web fonts; COMMITTED) + Inter-Variable.ttf
        (LEGACY - was the Pillow OG card font; no build uses it since 2026-06-12, kept for reference)
  img/  pe_logo-white.svg (inlined as a data URI by build_share_cards; COMMITTED)  pe_logo-white.png (LEGACY -
        was the canvas/Pillow logo; unused since 2026-06-12)
        fever-watch-lockup-white.svg  favicon.* icon-*.png og-fever-watch.png
        og/{city}.jpg + share/{city}.jpg (generated JPEGs, both gitignored, rebuilt every CI run)
tools/  resvg/ (vendored resvg v0.47.0: resvg-win64.exe + resvg-linux-x86_64 + README; COMMITTED)
        fonts/ (build-only shaping fonts: Inter 600/700/800 statics + 9 Noto variable script fonts, ~6.6MB;
        COMMITTED; outside assets/ so the Pages copytree never ships them)
dist/   fever-watch/...                  GENERATED SSG output (gitignored)
docs/   lab_feed_format.md  lab_feed_sample.csv  sheets_logging.md  local_names_review.md  PROJECT_STATE.md
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
  Production `base_url` = `https://pharmeasy.in/fever-watch/` (set 2026-06-25, was `/research/fever-watch-2026/`; staging still auto-canonicalises to the github.io URL via SITE_ENV=staging).
- [ ] PharmEasy infra: `/fever-watch/` reverse-proxy route + apex robots allowance.
- [ ] Brand sign-off on the co-branded lockup; provide the exact lockup asset if the rebuilt SVG is not pixel-perfect.
- [ ] Content team: confirm the ONE flagged local name (mira-bhayandar: shipped मीरा-भाईंदर vs alt मिरा-भाईंदर;
  `docs/local_names_review.md`). Plus a real-device WhatsApp share test of the new card (caption-drop behaviour).
- [ ] ~16 Jun: eyeball one live share card to confirm the "Up from N last week" pill activated cleanly
  (history.json will then have its first 4-day-old day).
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
