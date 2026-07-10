(function () {
  "use strict";
  var FW = window.FW || {};
  var RISK = { "HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F" };
  var RISK_SOFT = { "HIGH": "#FCEBE4", "MODERATE": "#FBF0E2", "LOW-MODERATE": "#F7F3E1", "LOW": "#E4F4EC" };
  var BAND_TITLE = { "HIGH": "High", "MODERATE": "Moderate", "LOW-MODERATE": "Low-Moderate", "LOW": "Low" };
  // Per-disease IDENTITY colours (NOT the severity ramp): dial segments + legend dots + breakdown dots.
  var DISEASE = { dengue: "#F1839D", malaria: "#887ADE", chikungunya: "#46CFE7", typhoid: "#4681EF" };
  // Red map-pin ("location drop") icon - byte-identical to LOC_PIN in build_site.py (above the fold).
  var LOC_PIN = '<svg class="locpin" viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="#F0493F" d="M12 2.2c-3.9 0-7 3.1-7 7 0 5 7 12.6 7 12.6s7-7.6 7-12.6c0-3.9-3.1-7-7-7z"/><circle cx="12" cy="9.2" r="2.6" fill="#fff"/></svg>';
  // Reviewer byline (E-E-A-T trust strip), byte-identical to the REVIEWBY constant in mobile.js + build_site.py.
  var REVIEWBY = '<p class="reviewline"><svg class="revico" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 4v5c0 4-3 7-7 8-4-1-7-4-7-8V7l7-4z"/><path d="M9 12l2 2 4-4"/></svg> Reviewed by <a href="https://pharmeasy.in/legal/editorial-policy/dr-nikita-toshi-2" target="_blank" rel="noopener">Dr. Nikita Toshi</a> and <a href="https://pharmeasy.in/legal/editorial-policy/dr-avinav-gupta-165" target="_blank" rel="noopener">Dr. Avinav Gupta</a></p>';
  // Weather-card outline icons - byte-identical to WX_* in build_site.py (above the fold).
  var _WX_A = '<svg class="wxic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">';
  var WX_HUM = _WX_A + '<path d="M12 3.6c2.9 3.8 5.3 6.5 5.3 9.5a5.3 5.3 0 0 1-10.6 0c0-3 2.4-5.7 5.3-9.5Z"/></svg>';
  var WX_RAIN = _WX_A + '<path d="M7.6 14.4a3.5 3.5 0 0 1 .3-7 4.6 4.6 0 0 1 8.8 1.3 3.2 3.2 0 0 1 .2 5.4"/><path d="M8.4 17.4 7.5 20M12 17.4 11.1 20M15.6 17.4 14.7 20"/></svg>';
  var WX_TEMP = _WX_A + '<path d="M14 14.3V5.5a2 2 0 0 0-4 0v8.8a3.4 3.4 0 1 0 4 0Z"/><path d="M12 9.5v4.8"/></svg>';
  var BEACON_DUR = { "HIGH": "0.85s", "MODERATE": "1.3s", "LOW-MODERATE": "1.9s", "LOW": "2.8s" };
  function beacon(band) { return '<span class="beacon" style="--c:' + (RISK[band] || "#888") + ';--bdur:' + (BEACON_DUR[band] || "1.6s") + '"><i></i></span>'; }
  var PERIOD_LABELS = [["today", "Today"], ["week", "This week"], ["month", "This month"]];
  function periodTabs(periods) {
    var avail = {}; (periods || ["today"]).forEach(function (p) { avail[p] = 1; });
    var out = PERIOD_LABELS.filter(function (t) { return t[0] === "today" && avail[t[0]]; }).map(function (t) {
      return '<button class="ftab' + (t[0] === "today" ? " on" : "") + '" type="button">' + t[1] + '</button>';
    }).join("");
    return '<div class="ftabs">' + out + '</div>';
  }
  var SIGCOL = { weather: [21, 172, 165], trends: [124, 108, 214], positivity: [54, 97, 176] };
  var SIGNAME = { weather: "Weather conditions", trends: "Google Search Interest", positivity: "PharmEasy labs" };
  var SIG = {
    weather: { c: "#15ACA5", bg: "#DBF3EF", fg: "#0c5a55", label: "🌧 Weather", what: "How much recent weather raises fever risk." },
    trends: { c: "#7C6CD6", bg: "#ECE8FB", fg: "#4b3fa3", label: "🔍 Search", what: "How often people here search these symptoms." },
    positivity: { c: "#3661B0", bg: "#E7EEFA", fg: "#22468f", label: "🧪 Lab", what: "How many local tests come back positive." }
  };
  var SHORT = { positivity: "Lab", weather: "Weather", trends: "Search" };
  // Per-signal "what is this 0-100 number" popover text (byte-identical to build_site.py TIPINFO).
  var TIPINFO = {
    weather: "How much recent weather helps these fevers spread, on a 0-100 scale.",
    trends: "How much people near you search these symptoms, vs what's normal for your city. 0-100.",
    positivity: "It's the share of local tests coming back positive. For a full 100, dengue needs 25%, malaria 4%, chikungunya 15%, typhoid 45% - each fever has its own level."
  };
  // 0-100 sub-score -> plain level word (the consumer reads High/Moderate/Low, not the raw number).
  function level(v) { return v >= 67 ? "High" : v >= 34 ? "Moderate" : "Low"; }
  var _IC = '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">';
  var IC_SHIELD = _IC.replace("<svg ", '<svg stroke="#E4572E" ') + '<path d="M12 3.2 5.5 6v5.2c0 4 2.7 7.2 6.5 8.6 3.8-1.4 6.5-4.6 6.5-8.6V6L12 3.2Z"/><path d="m9.3 11.7 1.9 1.9 3.5-3.8"/></svg>';
  var IC_VACC = _IC.replace("<svg ", '<svg stroke="#10847E" ') + '<path d="m17 4 3 3M18.5 5.5 8 16l-3.2 1.2L6 14 16.5 3.5M12.5 7l2 2M9.5 10l2 2"/></svg>';
  var IC_THERMO = _IC.replace("<svg ", '<svg stroke="#E4572E" ') + '<path d="M14 14.5V5.5a2 2 0 0 0-4 0v9a3.5 3.5 0 1 0 4 0Z"/><path d="M12 9.5v5"/></svg>';
  var IC_DOC = _IC.replace("<svg ", '<svg stroke="#10847E" ') + '<path d="M6 4v4.5a4 4 0 0 0 8 0V4M10 18.2a4.4 4.4 0 0 0 8.8 0v-2"/><circle cx="18.8" cy="13.5" r="2.2"/></svg>';
  var ACTIONS = [
    { ic: IC_SHIELD, t: "Monsoon precautions", s: "Cut mosquito sites and bites", href: "https://pharmeasy.in/blog/17-simple-health-tips-for-the-monsoons/?src=feverwatch" },
    { ic: IC_VACC, t: "Vaccination: does it work?", s: "What helps, what does not", href: "https://pharmeasy.in/blog/vaccine-vaccination-what-it-is-how-it-works-and-why-it-matters/?src=feverwatch" },
    { ic: IC_THERMO, t: "Fever? Follow our framework", s: "When to test, when to wait", href: "https://pharmeasy.in/blog/fever-high-temperature-causes-stages-treatments-and-red-flags/?src=feverwatch" },
    { ic: IC_DOC, t: "Not sure? Talk to a doctor", s: "Online consult on PharmEasy", href: "https://pharmeasy.in/online-doctor-consultation/?src=feverwatch" }
  ];
  var DASHNOTE = "This is a daily updated dashboard where we compute a monsoon-risk score (0-100) based on multiple data inputs, including weather data, Google search trends, and aggregate data from PharmEasy Labs and its Partner Affiliates.";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DATA = null, state = { cityId: null, expanded: null, leader: "overall", comboOpen: false, methodOpen: false, lbQuery: "", lbPage: 0 }, app = document.getElementById("fw-app");

  function loadGrid(tries) {
    return fetch(FW.gridUrl || "data/grid.json", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).catch(function (e) {
      if (tries > 1) return new Promise(function (res) { setTimeout(res, 500); }).then(function () { return loadGrid(tries - 1); });
      throw e;
    });
  }

  injectChrome();
  wireNav();  // PharmEasy header dropdowns + hamburger, independent of the data layer
  window.addEventListener("popstate", onPop);

  // Instant first paint from the inlined per-city seed; the full grid loads in the background for the
  // other-cities leaderboard.
  var booted = false;
  function boot(j) {
    DATA = j;
    if (!state.cityId || !DATA.cities.some(function (c) { return c.id === state.cityId; })) state.cityId = pickDefaultCity();
    state.expanded = cityObj(state.cityId).blend.driver;
    if (!booted) { booted = true; document.addEventListener("click", onClick); window.addEventListener("scroll", onTipScroll, { passive: true }); }
    render(); buildTicker(); buildDock();
  }
  // boot() is invoked at the very END of the IIFE - render() uses FAQ/METHOD, which are defined below.

  function pickDefaultCity() {
    if (FW.city && DATA.cities.some(function (c) { return c.id === FW.city; })) return FW.city;
    return DATA.cities.some(function (c) { return c.id === "bengaluru"; }) ? "bengaluru" : DATA.cities[0].id;
  }
  function useMyLocation() {
    if (!window.FeverWatchGeo) return;
    var row = document.querySelector(".comboloc");
    if (row) row.textContent = "◎ Finding your location...";
    window.FeverWatchGeo.resolve(DATA.cities, { allowGPS: true }).then(function (res) {
      if (res && res.cityId && DATA.cities.some(function (c) { return c.id === res.cityId; })) {
        state.comboOpen = false; setCity(res.cityId, true); window.scrollTo({ top: 0, behavior: "smooth" });
      } else if (row) { row.textContent = "◎ Could not detect your location - search below"; }
    }).catch(function () {
      if (row) row.textContent = "◎ Location unavailable - search below";
    });
  }
  function maybeGeo() {
    if (FW.city || !window.FeverWatchGeo) return;  // city pages respect the URL; geo only steers the landing default
    window.FeverWatchGeo.resolve(DATA.cities).then(function (res) {
      if (res && res.cityId && res.cityId !== state.cityId && DATA.cities.some(function (c) { return c.id === res.cityId; })) {
        state.cityId = res.cityId;
        state.expanded = cityObj(state.cityId).blend.driver;
        try { history.replaceState(null, "", cityHref(res.cityId)); } catch (e) {}
        render();
      }
    }).catch(function () {});
  }
  function injectChrome() {
    if (document.getElementById("scrim")) return;
    var d = document.createElement("div");
    d.className = "scrim"; d.id = "scrim";
    d.innerHTML = '<div class="pop" id="pop"></div>';
    document.body.appendChild(d);
  }

  function cityObj(id) { return DATA.cities.filter(function (c) { return c.id === id; })[0]; }
  function diseaseObj(id) { return DATA.diseases.filter(function (d) { return d.id === id; })[0]; }
  function cellFor(city, dis) { return DATA.grid.filter(function (r) { return r.city === city && r.disease === dis; })[0]; }
  // Methodology worked-example picks (edge case b): the driver disease + one of the OPPOSITE mode
  // (confirmed vs forecast) if the city has one, else just the driver.
  function methodPicks(c) {
    var cells = DATA.diseases.map(function (d) { return { cell: cellFor(c.id, d.id), disease: d.label }; }).filter(function (x) { return x.cell; });
    if (!cells.length) return [];
    cells.sort(function (a, b) { return b.cell.score - a.cell.score; });
    var driver = cells[0], dConf = driver.cell.mode === "confirmed", opp = null;
    for (var i = 1; i < cells.length; i++) { if ((cells[i].cell.mode === "confirmed") !== dConf) { opp = cells[i]; break; } }
    return opp ? [driver, opp] : [driver];
  }
  // Fill the methodology "see the parts add up" placeholder with DYNAMIC examples (real numbers) for the
  // current city. Called from render() so it tracks the selected city.
  function fillMethodExamples() {
    if (!window.FeverWatchMethod) return;
    var holder = document.querySelector("#methbody [data-mthd-examples]"); if (!holder) return;
    var c = cityObj(state.cityId); if (!c) return;
    holder.innerHTML = window.FeverWatchMethod.examplesHtml(methodPicks(c), c.name, true);
  }
  function fmtDate(iso) { if (!iso) return ""; var d = new Date(new Date(iso).getTime() + 19800000); return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear(); }  // +19800000ms = IST (UTC+5:30): generated_at is UTC, show the India calendar date
  function orderedDiseases(c) { return DATA.diseases.slice().sort(function (a, b) { return cellFor(c.id, b.id).score - cellFor(c.id, a.id).score; }); }
  function leaderRow(ci) { if (state.leader === "overall") return { score: ci.blend.score, band: ci.blend.band }; var cell = cellFor(ci.id, state.leader); return { score: cell.score, band: cell.band }; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]; }); }

  // City <-> URL sync. CITY_ROOT is the absolute path of /fever-watch/ on this origin.
  var CITY_ROOT = FW.city
    ? location.pathname.replace(/[^/]+\/?$/, "")
    : location.pathname.replace(/index\.html$/, "").replace(/\/?$/, "/");
  function cityHref(id) { return CITY_ROOT + id + "/"; }
  function cityFromPath() { return location.pathname.replace(/\/(index\.html)?$/, "").split("/").pop(); }
  function setCity(id, push) {
    state.cityId = id;
    state.expanded = cityObj(id).blend.driver;
    if (push) { try { history.pushState(null, "", cityHref(id)); } catch (e) {} }
    render();
    idleWarm();
  }
  // pre-fetch the current city's baked share image while the browser is idle, so the
  // share modal preview opens instantly instead of fetching on first tap
  var _warmedShare = "";
  function warmShare() {
    if (!window.FeverWatchShare || !DATA || _warmedShare === state.cityId) return;
    _warmedShare = state.cityId;
    var i = new Image();
    i.src = window.FeverWatchShare.imageUrl(state.cityId, DATA.generated_at);
  }
  function idleWarm() {
    if (window.requestIdleCallback) requestIdleCallback(warmShare, { timeout: 4000 });
    else setTimeout(warmShare, 2500);
  }
  function onPop() {
    if (!DATA) return;
    var id = cityFromPath();
    if (id && id !== state.cityId && DATA.cities.some(function (c) { return c.id === id; })) {
      state.cityId = id; state.expanded = cityObj(id).blend.driver; render(); window.scrollTo(0, 0);
    }
  }

  function wireNav() {
    var burger = document.querySelector(".pe-burger");
    var topnav = document.getElementById("pe-topnav");
    function closeDrops() {
      Array.prototype.forEach.call(document.querySelectorAll(".pe-nav-item.open"), function (o) {
        o.classList.remove("open");
        var b = o.querySelector(".pe-nav-btn"); if (b) b.setAttribute("aria-expanded", "false");
      });
    }
    function closePanel() { if (topnav) topnav.classList.remove("open"); if (burger) { burger.setAttribute("aria-expanded", "false"); burger.innerHTML = "&#9776;"; } }
    if (burger && topnav) {
      burger.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = topnav.classList.toggle("open");
        burger.setAttribute("aria-expanded", open ? "true" : "false");
        burger.innerHTML = open ? "&#10005;" : "&#9776;";
        if (!open) closeDrops();
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll(".pe-nav-btn"), function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var item = btn.parentNode, willOpen = !item.classList.contains("open");
        closeDrops();
        if (willOpen) { item.classList.add("open"); btn.setAttribute("aria-expanded", "true"); }
      });
    });
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!(t.closest && (t.closest(".pe-topnav") || t.closest(".pe-burger")))) { closeDrops(); closePanel(); }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" || e.keyCode === 27) { closeDrops(); closePanel(); } });
  }

  // Scroll-spy: highlight the TOC link for the section currently in view as the page scrolls.
  function spyScroll() {
    if (spyScroll.lock && Date.now() < spyScroll.lock) return;
    // == the TOC href targets, in document order (s-method is NOT a TOC target: it is reached via the
    // riskcard "Know more"). Keep this set identical to the .toc links in render() and _desktop_pre.
    var ids = ["s-week", "s-why", "s-weather", "s-do", "s-trend", "s-other", "s-faq"], cur = ids[0];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el && el.getBoundingClientRect().top <= 110) cur = ids[i];
    }
    var doc = document.documentElement;
    if ((window.innerHeight + (window.scrollY || window.pageYOffset || 0)) >= (doc.scrollHeight - 4)) cur = ids[ids.length - 1];
    var links = document.querySelectorAll(".toc a");
    for (var j = 0; j < links.length; j++) links[j].classList.toggle("cur", links[j].getAttribute("href") === "#" + cur);
  }
  function wireScrollSpy() {
    if (!wireScrollSpy.wired) {
      window.addEventListener("scroll", spyScroll, { passive: true });
      window.addEventListener("resize", spyScroll, { passive: true });
      wireScrollSpy.wired = true;
    }
    spyScroll();
  }

  function render() {
    var c = cityObj(state.cityId), b = c.blend;
    // The above-fold prefix (searchHero + shell-open + toc + s-week + s-why) MUST stay byte-identical to
    // build_site.py _desktop_pre so hydration is a no-op repaint (CLS 0). Edit BOTH together. The toc
    // href targets MUST equal spyScroll()'s ids array, in document order (s-method is reached via the
    // riskcard "Know more", so it is intentionally NOT a TOC target). The first JS-only bytes are
    // '<div class="main">'.
    app.innerHTML = searchHero(c) +
      '<div class="shell"><aside class="toc"><h2>Quick Links</h2>' +
        '<a class="cur" href="#s-week">Overall fever risk</a><a href="#s-why">Why this score?</a><a href="#s-weather">Weather conditions today</a><a href="#s-do">What you can do</a><a href="#s-trend">This year vs last year</a><a href="#s-other">What is happening in other cities?</a><a href="#s-faq">Common questions</a>' +
      '</aside>' + weekSectionD(c, b) + whySection(c) + '<div class="main">' + weatherSection(c) +
        doSection(c) + testsSection(c) +
        '<section id="s-trend" class="fwtrend-host"></section>' + seasonSection(c) + methodSection() + otherSection(c) +
        faqSection() + readsSection() + '</div></div>';
    wireLeaderboard();
    mountTrend(c);
    fillMethodExamples();   // dynamic "see the parts add up" examples for the loaded city
    if (state.methodOpen && window.FeverWatchMethod) window.FeverWatchMethod.wire(document.getElementById("methbody"));
    wireScrollSpy();
    updateDock();
    document.body.classList.add("fw-hydrated");
    peekDialInfo();
  }
  // Peek info tooltips briefly as a hint that they hold tappable info. _peekEl marks the transient peek
  // so the scroll-close leaves it alone; _scrollPeekDone / _loadPeekArmed make each peek fire once.
  var _dialTimer = null, _peekEl = null, _loadPeekArmed = false, _scrollPeekDone = false, _scrollPeekSel = "";
  // Viewport-aware placement (mirrors method.js placePop): the .dialtip is position:fixed, so place it
  // above the i by default, FLIP below when there is no room above (clears the sticky header), clamp
  // horizontally to the viewport, and keep the caret pointing at the i. Replaces the old caret-only helper.
  function positionTip(di) {
    var b = di.querySelector(".dialinfo-btn"), t = di.querySelector(".dialtip"), c = di.querySelector(".tipcaret");
    if (!b || !t || !c) return;
    t.classList.remove("below");
    var nav = document.querySelector(".fw-nav"),
        topSafe = (nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0) + 8,
        br = b.getBoundingClientRect(), tw = t.offsetWidth, th = t.offsetHeight,
        vw = window.innerWidth || document.documentElement.clientWidth,
        vh = window.innerHeight || document.documentElement.clientHeight,
        cx = br.left + br.width / 2, left = cx - tw / 2, top = br.top - th - 9, below = false;
    if (top < topSafe) { top = br.bottom + 9; below = true; }   // flip below so the box never slips under the sticky header
    if (below && top + th > vh - 8) top = Math.max(topSafe, vh - th - 8);
    if (left < 8) left = 8;
    if (left + tw > vw - 8) left = vw - tw - 8;
    t.style.left = left + "px"; t.style.top = top + "px";
    t.classList.toggle("below", below);
    c.style.left = Math.max(12, Math.min(tw - 12, cx - left)) + "px";
  }
  // DESKTOP: the dial sits in the second fold, so peek it once it scrolls into view (not at load).
  // Re-runs each render and re-queries the live node, so the seed -> data re-render is covered.
  function peekDialInfo() {
    _scrollPeekSel = ".dialinfo";
    maybeScrollPeek();
  }
  // A peek auto-opens a tooltip, stays immune to the scroll-close (via _peekEl), self-closes ~1.7s later.
  function firePeek(di) {
    if (!di) return;
    if (_dialTimer) { clearTimeout(_dialTimer); _dialTimer = null; }
    if (_peekEl && _peekEl !== di) _peekEl.classList.remove("open");
    _peekEl = di;
    di.classList.add("open"); positionTip(di);
    _dialTimer = setTimeout(function () { if (_peekEl === di) { di.classList.remove("open"); _peekEl = null; } }, 1700);
  }
  // Fire the scroll-triggered peek once its target is COMFORTABLY in view (re-queried live each call) -
  // clear of the sticky header (top) and the bottom dock, so the fixed tooltip never opens over them.
  function maybeScrollPeek() {
    if (_scrollPeekDone || !_scrollPeekSel) return;
    var di = document.querySelector(_scrollPeekSel); if (!di) return;
    var r = di.getBoundingClientRect(), vh = window.innerHeight || document.documentElement.clientHeight;
    if (r.height > 0 && r.top >= 56 && r.bottom <= vh - 100) { _scrollPeekDone = true; firePeek(di); }
  }
  // Window scroll: fire a pending scroll-peek when its target is comfortably in view; keep the transient peek
  // PINNED to its icon as the page scrolls (a position:fixed box would otherwise detach and float over the
  // dock) and close it once the icon scrolls off-screen. User-opened tooltips just close on scroll.
  function onTipScroll() {
    maybeScrollPeek();
    var op = document.querySelectorAll(".dialinfo.open");
    for (var i = 0; i < op.length; i++) {
      if (op[i] === _peekEl) {
        var b = op[i].querySelector(".dialinfo-btn"), r = b && b.getBoundingClientRect(), vh = window.innerHeight || 0;
        if (r && r.bottom > 4 && r.top < vh - 4) positionTip(op[i]);
        else { op[i].classList.remove("open"); _peekEl = null; }
      } else { op[i].classList.remove("open"); }
    }
  }

  // The "this monsoon vs last year" widget owns its own subtree (tabs / tooltip / collapse / desktop
  // small-multiples); recompute it from the grid on every render so it tracks the selected city.
  function mountTrend(c) {
    if (window.FeverWatchTrend) window.FeverWatchTrend.mount(document.getElementById("s-trend"), c, DATA, { mode: "desktop" });
  }

  function searchHero(c) {
    return '<section class="srch"><div class="srchin">' +
      '<h1>Live monsoon-fever risk for ' + esc(c.name) + ' in <em>one score</em>.</h1>' +
      '<p class="subtitle">Dengue, malaria, chikungunya and typhoid, blended from weather conditions, Google Search interest and PharmEasy lab signals.</p>' +
      '<div class="locwrap"><button class="loccard" data-act="combo">' + LOC_PIN + '<span class="locname">' + esc(c.name) + '</span>' +
        '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>' +
        '<div class="combopanel' + (state.comboOpen ? ' open' : '') + '"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>' +
      '</div>' +
      '<p class="searchnote loc-note">Updated ' + fmtDate(DATA.generated_at) + '. Available in select cities.</p>' + REVIEWBY + '</div></section>';
  }

  // s-week above-fold twin: REUSES the mobile-proven riskCard() verbatim, byte-identical to build_site.py
  // _risk_card (which _desktop_pre embeds). The proportional identity dial + legend + band chip + period
  // tabs all live in riskCard(); the section wrapper matches _desktop_pre.
  function weekSectionD(c, b) {
    return '<section id="s-week">' + riskCard(c, b) + '</section>';
  }

  // Band phrase with a {d} driver placeholder; composed into the dialmean read-out below.
  var BAND_MEAN = {
    "HIGH": "high, driven by {d}",
    "MODERATE": "moderate, {d} leading",
    "LOW-MODERATE": "slightly raised, {d} leading",
    "LOW": "low, {d} highest"
  };
  function riskCard(c, b) {
    var ordered = orderedDiseases(c);
    var segs = ordered.map(function (d) { return [cellFor(c.id, d.id).score, DISEASE[d.id] || "#888"]; });
    var leg = ordered.map(function (d) {
      var cell = cellFor(c.id, d.id), cc = DISEASE[d.id] || "#888";
      return '<div class="legrow"><span class="legdot" style="background:' + cc + '"></span>' +
        '<span class="legname">' + esc(d.label) + ' : <b>' + cell.score + '</b><span class="legmax">/100</span></span></div>';
    }).join("");
    var band = b.band, cbg = "#FFF8E3", cbd = "#F0D27A", cbc = "#F5B630";  // MODERATE = gold; others = ramp
    if (band !== "MODERATE") { cbg = RISK_SOFT[band]; cbd = RISK[band]; cbc = RISK[band]; }
    var dlabel = esc((diseaseObj(b.driver) || {}).label || ""), dscore = cellFor(c.id, b.driver).score;
    var info = '<span class="dialinfo"><button type="button" class="dialinfo-btn" data-act="dialInfo" aria-label="What this score means">i</button>' +
      '<span class="dialtip"><span class="tiprow"><b>' + dlabel + ' (' + dscore + ')</b> is the top fever here, making up about <b>80%</b> of this score. The other three add <b>20%</b>.</span>' +
      '<span class="tipbands"><span class="tb"><i style="background:#3f9d6f"></i>Low 0-24</span><span class="tb"><i style="background:#c2a93a"></i>Low-Mod 25-44</span><span class="tb"><i style="background:#d98a2b"></i>Moderate 45-69</span><span class="tb"><i style="background:#d64545"></i>High 70-100</span></span><span class="tipcaret"></span></span></span>';
    var chip = '<div class="bandchip" style="background:' + cbg + ';border-color:' + cbd + '">' +
      '<span class="beacon" style="--c:' + cbc + ';--bdur:' + (BEACON_DUR[band] || "1.6s") + '"><i></i></span>' +
      (BAND_TITLE[band] || band) + ' fever risk in ' + esc(c.name) + ' ' + info + '</div>';
    var mean = '<p class="dialmean">Right now ' + esc(c.name) + '\'s overall score is ' + b.score + '/100, ' + (BAND_MEAN[band] || "").replace("{d}", dlabel) + '. A daily look at local risk, not who\'s actually sick.</p>';
    return '<div class="card riskcard">' + periodTabs(DATA.periods) + '<div class="rtop">' + ring(segs, b.score, 120) + '<div class="leg">' + leg + '</div></div>' + chip + mean +
      '<div class="rfoot"><span class="note">Scores calculated from weather conditions, Google search interest and PharmEasy lab signals. <button class="knowmore" data-act="openMethod">Know more</button></span>' +
      '<button class="sharebtn" data-act="openShare">⤴ Share</button></div></div>';
  }

  // Weather conditions today (ported from mobile weatherCard; the WX strings + cards are
  // byte-frozen with the mobile twin / build_site.py _weather_card). JS-only, below the fold on desktop.
  function weatherSection(c) {
    return '<section id="s-weather">' + weatherCard(c) + '</section>';
  }
  function weatherCard(c) {
    var w = c.weather || {}, temp = w.temp_mean_c, r14 = w.rain_14d_mm, hum = w.humidity_pct;
    var cards = [
      [WX_TEMP, "Temperature", (temp == null ? "n/a" : Math.round(temp) + "°C"), "Warmth near 29°C speeds up mosquito-borne fevers."],
      [WX_RAIN, "Rainfall", (r14 == null ? "n/a" : Math.round(r14) + "mm"), "Last 2-week total; leftover rainwater raises mosquito and typhoid risk."],
      [WX_HUM, "Humidity", (hum == null ? "n/a" : Math.round(hum) + "%"), "Mosquitoes survive longer in humid air."]
    ];
    var cells = cards.map(function (x) {
      return '<div class="wxcard"><div class="wxtop">' + x[0] + '<span class="wxhead">' + esc(x[1]) +
        '<span class="wxsep"></span><b>' + esc(x[2]) + '</b></span></div><div class="wxsub">' + esc(x[3]) + '</div></div>';
    }).join("");
    return '<div class="card wxsec"><h2 class="sectiontitle">Weather conditions today</h2>' +
      '<p class="sectionsub">Conditions as of ' + fmtDate(DATA.generated_at) + ' and what they mean for fever risk.</p>' +
      '<div class="wxgrid">' + cells + '</div></div>';
  }

  // Why this score: the horizontal 3-signal breakdown, one accordion per disease (ported from mobile
  // breakdownCard). The driver accordion opens first (state.expanded init in boot/setCity).
  function whySection(c) {
    return '<section id="s-why">' + breakdownCard(c) + '</section>';
  }
  function breakdownCard(c) {
    var ORDER = ["positivity", "weather", "trends"];
    var ord = orderedDiseases(c);
    var hiId = ord[0].id, loId = ord[ord.length - 1].id;
    var spread = cellFor(c.id, hiId).score - cellFor(c.id, loId).score;
    var accs = ord.map(function (d) {
      var cell = cellFor(c.id, d.id), open = state.expanded === d.id, pts = contribs(cell);
      var order = ORDER.slice().sort(function (a, b) { return (pts[b] - pts[a]) || (ORDER.indexOf(a) - ORDER.indexOf(b)); });
      var rows = "", sum = [];
      order.forEach(function (k) { rows += sig(SIG[k], cell, k, pts[k]); if (cell.signals[k] != null) sum.push(SHORT[k] + " " + pts[k]); });
      var body = '<div class="accbody">' + rows + '<p class="accnote"><span style="display:block;font-weight:700;margin:0 0 4px">' + sum.join(" + ") + " = " + cell.score + '</span>' + cell.note + '</p></div>';
      var kind = spread > 0 && d.id === hiId ? "highest" : (spread > 0 && d.id === loId ? "lowest" : "");
      var why = kind ? whyChip(cell, kind) : "";
      var nameHtml = why ? '<span class="nmwrap"><span class="name">' + d.label + '</span><span class="whysub">' + why + '</span></span>' : '<span class="name">' + d.label + '</span>';
      return '<div class="acc' + (open ? ' open' : '') + '"><button class="acchead" data-act="expand" data-id="' + d.id + '">' +
        '<span class="emoji">' + d.emoji + '</span>' + nameHtml +
        '<span class="dot" style="background:' + (DISEASE[d.id] || "#888") + '"></span><span class="sc">' + cell.score + '</span>' +
        '<span class="chev">▾</span></button>' + body + '</div>';
    }).join("");
    return '<div class="card whycard"><h2 class="sechead">Why this score?</h2><p class="secsub">Tap a disease to see how each signal builds the score. <button class="knowmore" data-act="openMethod">Know more</button></p>' + accs + '</div>';
  }

  // Per-signal day-over-day badge (red up = rising / green down = easing). Empty unless a present,
  // non-zero delta exists - sig_delta is absent on cells today, so this stays hidden (same as mobile).
  function sigBadge(delta) {
    if (typeof delta !== "number" || delta === 0) return "";
    var up = delta > 0;
    var arrow = up
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7 17 17M17 9v8h-8"/></svg>';
    return '<span class="sigbadge ' + (up ? "up" : "down") + '" title="' + (up ? "Rising vs yesterday" : "Easing vs yesterday") + '">' + arrow + '</span>';
  }
  // Largest-remainder (Hamilton) apportionment of the displayed integer score across the signals'
  // weighted shares, so the per-signal contribution points sum EXACTLY to cell.score in every mode
  // (agree x1.08, disagree x0.96, forecast cap 69 are all absorbed - we apportion the final score, not base).
  function contribs(cell) {
    var s = cell.signals, w = cell.weights, score = cell.score, order = ["positivity", "weather", "trends"];
    var sh = {}, base = 0;
    order.forEach(function (k) { var v = s[k]; sh[k] = (v == null) ? 0 : (w[k] / 100) * v; base += sh[k]; });
    var pts = { positivity: 0, weather: 0, trends: 0 }, fr = {};
    if (base > 0) {
      var used = 0;
      order.forEach(function (k) { var e = score * sh[k] / base, f = Math.floor(e); pts[k] = f; fr[k] = e - f; used += f; });
      var rem = score - used, ranked = order.slice().sort(function (a, b) { return (fr[b] - fr[a]) || (order.indexOf(a) - order.indexOf(b)); });
      for (var i = 0; i < rem; i++) pts[ranked[i]] += 1;
    } else { pts[order[0]] = score; }
    return pts;
  }
  // Plain-language driver line for the highest / lowest disease chip (2nd line under the name in the
  // breakdown header). Names signals by CONTRIBUTION order so it cites the real lever; simplified
  // vocabulary, byte-identical to mobile.js whyChip + build_site.py _why_chip. "" => no chip.
  function whyChip(cell, kind) {
    var s = cell.signals, pts = contribs(cell), order = ["positivity", "weather", "trends"];
    var pres = order.filter(function (k) { return s[k] != null; });
    if (!pres.length) return "";
    var UP = { weather: "strong weather", positivity: "high positive tests", trends: "high search interest" };
    var UPM = { weather: "moderate weather", positivity: "some positive tests", trends: "some search interest" };
    var NOUN = { weather: "weather", positivity: "positive tests", trends: "search" };
    function up(k) { return level(s[k]) === "High" ? UP[k] : UPM[k]; }
    function cap(t) { return t.charAt(0).toUpperCase() + t.slice(1); }
    if (kind === "highest") {
      var byc = pres.slice().sort(function (a, b) { return (pts[b] - pts[a]) || (order.indexOf(a) - order.indexOf(b)); });
      var lead = byc.filter(function (k) { return level(s[k]) !== "Low"; }).slice(0, 2);
      if (!lead.length) return "";
      return cap(lead.map(up).join(" + ")) + ".";
    }
    var byv = pres.slice().sort(function (a, b) { return (s[a] - s[b]) || (order.indexOf(a) - order.indexOf(b)); });
    var weak = byv[0], strong = byv[byv.length - 1];
    if (level(s[strong]) === "Low") return "";
    return "Lower " + NOUN[weak] + " despite " + up(strong) + ".";
  }
  // One signal row: bar length = the signal's CONTRIBUTION points (so the three bars sum to the score),
  // coloured per signal; the raw value + weight stay as small provenance text. Absent (forecast) lab shows
  // a muted no-data tile (no bar) so the desktop 3-col grid keeps three tiles.
  function sig(meta, cell, k, pt) {
    var v = cell.signals[k];
    if (v == null) {
      return '<div class="sig"><div style="font-size:11.5px;font-weight:700;line-height:1.2;color:var(--pe-ink)">' + meta.label + '</div>' +
        '<div style="font-size:10px;color:var(--pe-muted);margin-top:5px">No confirmed lab data yet, conditions-only forecast.</div></div>';
    }
    var bw = Math.floor(pt / cell.score * 100 + 0.5);
    return '<div class="sig"><div style="display:flex;align-items:center;gap:5px"><span style="flex:1;font-size:11.5px;font-weight:700;color:var(--pe-ink);line-height:1.2">' + meta.label + '</span><span style="font-size:15px;font-weight:800;color:' + meta.c + '">+' + pt + '</span></div>' +
      '<div style="display:flex;align-items:center;gap:6px;margin:5px 0 2px"><span style="font-size:9.5px;font-weight:800;letter-spacing:.3px;line-height:1.3;padding:1px 7px;border-radius:999px;background:' + meta.bg + ';color:' + meta.fg + '">' + level(v) + '</span>' + sigBadge((cell.sig_delta || {})[k]) + '</div>' +
      '<div style="font-size:10px;color:var(--pe-muted-2);font-weight:600;margin:0 0 4px;white-space:nowrap">' + cell.weights[k] + '% weight × ' + v + '/100 <span class="dialinfo"><button type="button" class="dialinfo-btn" data-act="dialInfo" aria-label="What this number means">i</button><span class="dialtip">' + TIPINFO[k] + '<span class="tipcaret"></span></span></span></div>' +
      '<div class="track" style="height:6px"><div class="fill" style="width:' + bw + '%;background:' + meta.c + '"></div></div>' +
      '<div style="font-size:10px;color:var(--pe-muted);line-height:1.4;margin-top:6px">' + meta.what + '</div></div>';
  }

  function doSection(c) {
    var cards = ACTIONS.map(function (a) {
      return '<a class="actcard" href="' + a.href + '"><span class="ic">' + a.ic + '</span><span class="tx"><b>' + a.t + '</b><span>' + a.s + '</span></span><span class="go">›</span></a>';
    }).join("");
    return '<section id="s-do"><div class="card"><h2 class="sechead">What you can do</h2><p class="secsub">Practical follow-through for ' + c.name + ' today.</p>' +
      '<div class="actrow">' + cards + '</div><a class="ctabig" style="background:var(--pe-green)" href="' + (c.diag_url || "https://pharmeasy.in/diagnostics/health-checkup-packages?src=feverwatch&page=2#:~:text=Fever") + '">Book a fever panel test in ' + esc(c.name) + '</a></div></section>';
  }

  function methodSection() {
    return '<section id="s-method"><div class="card">' +
      '<h2 class="sechead" style="margin:0 0 2px">How we calculate the score</h2>' +
      '<button class="methhead" data-act="method"><span class="secsub" style="margin:0">Transparent and decomposable, not a black box.</span>' +
      '<span class="methtog" id="methtog">Show details ▾</span></button>' +
      '<div class="methbody' + (state.methodOpen ? ' open' : '') + '" id="methbody">' + METHOD + '<p class="dashnote">' + DASHNOTE + '</p></div></div></section>';
  }

  function otherSection(c) {
    var isOverall = state.leader === "overall";
    var label = isOverall ? "Overall" : diseaseObj(state.leader).label;
    var tabs = '<button class="lbtab' + (isOverall ? " on" : "") + '" data-act="leader" data-id="overall">📊 Overall</button>' +
      DATA.diseases.map(function (d) { return '<button class="lbtab' + (d.id === state.leader ? " on" : "") + '" data-act="leader" data-id="' + d.id + '">' + d.emoji + ' ' + d.label + '</button>'; }).join("");
    return '<section id="s-other"><div class="card"><h2 class="sechead">What is happening in other cities?</h2><p class="secsub">' + label + ' risk leaderboard today. Pick a disease to re-rank.</p>' +
      '<div class="lbtabs">' + tabs + '</div>' +
      '<input class="lbsearch" id="lbsearch" placeholder="Search a city" value="' + esc(state.lbQuery) + '" autocomplete="off" />' +
      '<div id="lbcontainer">' + leaderboardInner(c) + '</div>' + nearbyHtml(c) + '</div></section>';
  }

  // --- Phase-0 SEO blocks: fever tests / season insight / nearby cities ---------------------------
  // Facts must stay consistent with build_site.py (_tests_sec/_season_bits/_nearest_cities) and
  // mobile.js: same test names, same +/-8 season thresholds, same 0.00872664626 distance constant
  // and id tie-break. Edit all three together.
  // GATED (2026-07-08): tests section held back pending the medical review; flip with build_site.py
  // FW_TESTS_ENABLED and mobile.js FW_TESTS_ON, re-add '<a href="#s-tests">Fever tests</a>' after
  // "What you can do" in BOTH TOC twins (render() above + build_site._desktop_pre, byte-identical)
  // and "s-tests" after "s-do" in spyScroll ids.
  var FW_TESTS_ON = false;
  var FW_TESTS = [
    ["🦟", "Dengue", "NS1 antigen (first few days) or IgM antibody test", "A CBC alongside tracks platelets, which dengue can lower."],
    ["🦟", "Malaria", "Peripheral blood smear or a rapid antigen test", "Identifies the parasite and its species."],
    ["🦟", "Chikungunya", "IgM antibody test; RT-PCR in the first week", "Lingering joint pain is its signature."],
    ["💧", "Typhoid", "Blood culture (definitive); Widal is the common screen", "From contaminated food or water, so it builds slowly."]
  ];
  function testBandLine(nm, band) {
    if (band === "HIGH") return "With " + nm + " elevated right now, do not sit on a fever - if it lasts past 2 days, a test plus a doctor visit is the sensible move.";
    if (band === "MODERATE") return "At MODERATE, the practical rule of thumb: a fever that lasts more than 2 days is worth testing.";
    return "Even at lower risk, a fever that drags past 2 to 3 days or feels severe deserves a test and a doctor's opinion.";
  }
  function testsSection(c) {
    if (!FW_TESTS_ON) return "";
    var b = c.blend;
    var rows = FW_TESTS.map(function (t) {
      return '<div class="trow"><span class="tname">' + t[0] + ' ' + esc(t[1]) + '</span><span class="tinfo"><b>' + esc(t[2]) + '</b><span>' + esc(t[3]) + '</span></span></div>';
    }).join("");
    return '<section id="s-tests"><div class="card fwtests"><h2 class="sechead">Fever tests: which test confirms what?</h2>' +
      '<p class="secsub">As of ' + fmtDate(DATA.generated_at) + ', ' + esc(c.name) + "'s overall risk is " + b.score + '/100 (' + b.band + '). If a fever shows up and sticks around, testing is how it gets identified - here is what doctors typically order.</p>' +
      rows +
      '<p class="bandline">' + testBandLine(esc(c.name), b.band) + '</p>' +
      '<a class="ctabig" style="background:var(--pe-green)" href="' + (c.diag_url || "https://pharmeasy.in/diagnostics/health-checkup-packages?src=feverwatch&page=2#:~:text=Fever") + '">Book a fever panel test in ' + esc(c.name) + '</a>' +
      '<p class="fwdisc">Fever Watch is a risk indicator, not a diagnosis. Which test fits, and what a result means, is a doctor\'s call.</p></div></section>';
  }
  function seasonBits(c) {
    var ac = DATA.archive && DATA.archive.cities && DATA.archive.cities[c.id];
    var ov = (ac && ac.overall) || {};
    var ly = ov.ly || [], ty = ov.ty || [];
    if (ly.length !== 22 || !ty.length) return null;
    var i = Math.min(ty.length - 1, 21);
    var tyNow = ty[i], lySame = ly[i], diff = tyNow - lySame;
    var phrase = diff >= 8 ? "running above" : (diff <= -8 ? "running below" : "about level with");
    var pk = 0; for (var j = 0; j < 22; j++) { if (ly[j] > ly[pk]) pk = j; }
    var lyYear = new Date(new Date(DATA.generated_at).getTime() + 19800000).getUTCFullYear() - 1;
    var pd = new Date(Date.UTC(lyYear, 5, 1) + pk * 7 * 86400000);
    var peak = pd.getUTCDate() + " " + MONTHS[pd.getUTCMonth()] + " " + pd.getUTCFullYear();
    return { ty: tyNow, ly: lySame, phrase: phrase, peak: peak };
  }
  function seasonSection(c) {
    var s = seasonBits(c); if (!s) return "";
    return '<section class="fwseason-sec"><div class="card fwseason"><h2 class="sechead">How this monsoon compares</h2>' +
      '<p class="seasonp">As of ' + fmtDate(DATA.generated_at) + ', ' + esc(c.name) + "'s overall fever signal is <b>" + s.ty + '/100</b> - ' + s.phrase + ' the same week last monsoon (' + s.ly + "/100). Last season's high point came in the week of " + s.peak + '. Rain drives this number, so the picture shifts as the season moves - we refresh it daily.</p></div></section>';
  }
  function nearbyHtml(c) {
    if (!DATA.cities || DATA.cities.length < 2) return "";
    var la1 = c.lat || 0, lo1 = c.lon || 0, out = [];
    for (var i = 0; i < DATA.cities.length; i++) {
      var o = DATA.cities[i]; if (o.id === c.id) continue;
      var la2 = o.lat || 0, lo2 = o.lon || 0;
      var dx = (lo2 - lo1) * Math.cos((la1 + la2) * 0.00872664626), dy = la2 - la1;
      out.push([dx * dx + dy * dy, o.id, o]);
    }
    out.sort(function (a, b) { return a[0] - b[0] || (a[1] < b[1] ? -1 : 1); });
    var chips = out.slice(0, 5).map(function (t) {
      var o = t[2];
      return '<a class="fwnear-chip" href="' + cityHref(o.id) + '" data-act="pickrow" data-id="' + o.id + '"><b>' + esc(o.name) + '</b><span>' + o.blend.score + '/100</span></a>';
    }).join("");
    return '<div class="fwnear"><div class="fwnear-t">Nearby cities right now</div><div class="fwnear-row">' + chips + '</div></div>';
  }

  function leaderboardInner(c) {
    var PER = 10;
    var ranked = DATA.cities.map(function (ci) { var lr = leaderRow(ci); return { id: ci.id, name: ci.name, state: ci.state, score: lr.score, band: lr.band }; }).sort(function (a, b) { return b.score - a.score; });
    ranked.forEach(function (r, i) { r.rank = i + 1; });
    var me = null, mk; for (mk = 0; mk < ranked.length; mk++) { if (ranked[mk].id === state.cityId) { me = ranked[mk]; break; } }
    var q = (state.lbQuery || "").toLowerCase();
    var filtered = q ? ranked.filter(function (r) { return r.name.toLowerCase().indexOf(q) >= 0 || (r.state || "").toLowerCase().indexOf(q) >= 0; }) : ranked;
    var pages = Math.max(1, Math.ceil(filtered.length / PER));
    var page = Math.min(state.lbPage || 0, pages - 1);
    var slice = filtered.slice(page * PER, page * PER + PER);
    function rowFor(r, pin) {
      return '<tr class="' + (r.id === state.cityId ? "you" : "") + (pin ? " lb-pinned" : "") + '" data-act="pickrow" data-id="' + r.id + '"><td class="rk">' + r.rank + '</td><td><a class="lbcity" href="' + cityHref(r.id) + '">' + r.name + '</a>' + (r.id === state.cityId ? " (you)" : "") + '</td>' +
        '<td style="color:var(--pe-muted)">' + r.state + '</td><td class="bar"><i style="width:' + r.score + '%;background:' + RISK[r.band] + '"></i></td>' +
        '<td><span class="bd" style="background:' + RISK_SOFT[r.band] + ';color:' + RISK[r.band] + '">' + r.band + '</span></td><td style="font-weight:700;color:' + RISK[r.band] + '">' + r.score + '</td></tr>';
    }
    var body = slice.map(function (r) { return rowFor(r, false); }).join("");
    // Pin the user's own city as a last row whenever it is off this page (and not while searching), so
    // they always see their rank vs others without paging deep. Auto-suppressed once paging reaches it.
    var onPage = slice.some(function (r) { return r.id === state.cityId; });
    var pinned = (me && !onPage && !q) ? rowFor(me, true) : "";
    var table = '<table class="lbtable"><thead><tr><th>#</th><th>City</th><th>State</th><th>Risk</th><th>Band</th><th>Score</th></tr></thead><tbody>' +
      (body || '<tr><td colspan="6" style="text-align:center;color:var(--pe-muted);padding:18px">No city matches "' + esc(state.lbQuery) + '".</td></tr>') + pinned + '</tbody></table>';
    return table + pager(page, pages, filtered.length);
  }

  function pager(page, pages, total) {
    if (pages <= 1) return '<p class="lbnote">Showing all ' + total + ' cities. Each row opens that city.</p>';
    return '<div class="lbpager"><button class="pgbtn" data-act="lbpage" data-page="' + (page - 1) + '"' + (page === 0 ? " disabled" : "") + '>‹ Prev</button>' +
      '<span class="pginfo">Page ' + (page + 1) + ' of ' + pages + ' (' + total + ' cities)</span>' +
      '<button class="pgbtn" data-act="lbpage" data-page="' + (page + 1) + '"' + (page >= pages - 1 ? " disabled" : "") + '>Next ›</button></div>';
  }

  function renderLeaderboard() { var el = document.getElementById("lbcontainer"); if (el) el.innerHTML = leaderboardInner(cityObj(state.cityId)); }
  function wireLeaderboard() { var s = document.getElementById("lbsearch"); if (s) s.oninput = function () { state.lbQuery = s.value; state.lbPage = 0; renderLeaderboard(); }; }

  function readsSection() {
    var groups = [
      ["Dengue", [
        ["How to avoid dengue fever", "https://pharmeasy.in/blog/5-ways-to-avoid-dengue-fever/"],
        ["Home remedies for dengue", "https://pharmeasy.in/blog/home-remedies-for-dengue-by-dr-siddharth-gupta/"],
        ["Food for dengue: what to eat and avoid", "https://pharmeasy.in/blog/food-for-dengue-what-to-eat-and-what-to-avoid/"],
        ["Diabetes and dengue risk", "https://pharmeasy.in/blog/diabetes-can-make-dengue-more-lethal/"]
      ]],
      ["Malaria", [
        ["Types of malaria: symptoms and treatment", "https://pharmeasy.in/blog/types-of-malaria-symptoms-causes-and-treatment/"],
        ["Foods for malaria", "https://pharmeasy.in/blog/foods-for-malaria-what-to-eat-and-what-to-avoid/"],
        ["Home remedies for malaria", "https://pharmeasy.in/blog/home-remedies-for-malaria-by-dr-siddharth-gupta/"]
      ]],
      ["Mosquito bites and monsoon health", [
        ["Mosquito bite remedies", "https://pharmeasy.in/blog/home-remedies-for-mosquito-bite-by-dr-siddharth-gupta/"],
        ["Mosquito bites on babies", "https://pharmeasy.in/blog/child-care-mosquito-bites-on-babies-home-remedies-treatment-and-prevention/"],
        ["Common monsoon illnesses in India", "https://pharmeasy.in/blog/common-illnesses-during-monsoons-in-india/"],
        ["Monsoon health tips", "https://pharmeasy.in/blog/17-simple-health-tips-for-the-monsoons/"]
      ]]
    ];
    var cols = groups.map(function (g) {
      var lis = g[1].map(function (l) { return '<li><a href="' + l[1] + '" target="_blank" rel="noopener">' + l[0] + '</a></li>'; }).join("");
      return '<div class="related-col"><h3>' + g[0] + '</h3><ul>' + lis + '</ul></div>';
    }).join("");
    return '<section id="s-reads"><h2 class="sechead">Further reading from PharmEasy</h2>' +
      '<div class="card"><div class="related-grid">' + cols + '</div></div></section>';
  }

  function faqSection() {
    var faq = (window.FeverWatchFaq && DATA) ? FeverWatchFaq.forCity(cityObj(state.cityId), DATA, FW.seed) : FAQ;
    var items = faq.map(function (f, i) {
      return '<details class="faqitem"' + (i < 2 ? ' open' : '') + '><summary><span class="faq-q">' + f[0] + '</span><span class="faq-chev" aria-hidden="true"></span></summary><div class="faq-a">' + f[1] + '</div></details>';
    }).join("");
    return '<section id="s-faq"><h2 class="sechead">Common questions</h2><div class="faq-list">' + items + '</div></section>';
  }

  // The risk dial: a 270deg gauge FILLED to the overall score, the filled arc subdivided into one slot
  // per disease sized by its share of the summed scores, drawn in the disease IDENTITY colour with a
  // fixed ~6deg white gap between slots. Byte-identical to build_site.py _ring_svg() (above-fold, CLS 0).
  function ns(x) { return x === Math.floor(x) ? String(x) : ("" + x); }
  function ring(segs, score, size) {
    var sw = 12, cx = size / 2, r = (size - sw) / 2 - 1, C = 2 * Math.PI * r, arc = 0.75;
    var fillFrac = (score / 100) * arc;
    var total = segs.reduce(function (a, s) { return a + s[0]; }, 0) || 1;
    var GAP_PX = 13.5;  // no nudge: first segment starts at the track start (the "0" position)
    var track = (arc * C).toFixed(1), gapAll = (C - arc * C).toFixed(1), off = (C * 2).toFixed(1), cs = ns(cx), rs = ns(r);
    var trackC = '<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="#e9eef5" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gapAll + '" transform="rotate(135 ' + cs + ' ' + cs + ')"/>';
    var out = "", cum = 0;
    for (var i = 0; i < segs.length; i++) {
      var slotFrac = (segs[i][0] / total) * fillFrac, dashPx = slotFrac * C - GAP_PX;
      if (dashPx < 0) dashPx = 0;
      var dash = dashPx.toFixed(1), rot = (135 + cum * 360).toFixed(1);
      out += '<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="' + segs[i][1] + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + dash + ' ' + off + '" transform="rotate(' + rot + ' ' + cs + ' ' + cs + ')"/>';
      cum += slotFrac;
    }
    return '<div class="ringwrap" style="width:' + size + 'px;height:' + size + 'px">' +
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' + trackC + out +
      '</svg><div class="num"><div class="numtop"><b>' + score + '</b><span>/ 100</span></div><em>Overall fever risk score</em></div></div>';
  }
  // Day-over-day arrow (vs yesterday); empty unless a present, non-zero delta exists. Mirrors _delta_arrow().
  function deltaArrow(delta) {
    if (delta == null || delta === 0) return "";
    var up = delta > 0;
    return '<span class="legtrend ' + (up ? "up" : "down") + '">' + (up ? "▲" : "▼") + " " + Math.abs(delta) + "</span>";
  }

  function renderCombo() {
    var q = (document.getElementById("cityinput").value || "").toLowerCase();
    document.getElementById("combolist").innerHTML = DATA.cities.filter(function (c) { return c.name.toLowerCase().indexOf(q) >= 0; }).map(function (c) {
      var b = c.blend;
      return '<button class="cityopt" data-act="pickCity" data-id="' + c.id + '"><span>📍 ' + c.name + ' <small>' + c.state + '</small></span><span class="sb" style="background:' + RISK_SOFT[b.band] + ';color:' + RISK[b.band] + '">' + b.band + ' ' + b.score + '</span></button>';
    }).join("");
  }

  // Share-surface chrome (handoff): live ticker under the header + bottom-right share dock.
  function tickerItems() {
    return DATA.cities.slice().sort(function (a, b) { return b.blend.score - a.blend.score; }).slice(0, 12).map(function (c) {
      var b = c.blend, col = RISK[b.band] || "#888", soft = RISK_SOFT[b.band] || "#eee";
      return '<a class="fw-tick" href="' + cityHref(c.id) + '" data-act="pickrow" data-id="' + c.id + '">' +
        '<span class="tdot" style="background:' + col + '"></span>' + esc(c.name) + ' <b style="color:' + col + '">' + b.score + '</b>' +
        '<span class="tpill" style="color:' + col + ';background:' + soft + '">' + b.band + '</span></a>';
    }).join("");
  }
  // The ticker is baked server-side (right after the header) so it never shifts layout; just wire the
  // touch-hold pause once (hover pause is pure CSS).
  function buildTicker() {
    var el = document.getElementById("fwticker");
    if (!el || el.dataset.wired) return;
    el.dataset.wired = "1";
    el.addEventListener("touchstart", function () { el.classList.add("held"); }, { passive: true });
    ["touchend", "touchcancel"].forEach(function (ev) { el.addEventListener(ev, function () { el.classList.remove("held"); }); });
  }
  // Floating share dock. Severity-tiered copy keyed off the band (ported from mobile buildShareFooter /
  // footCopy) so a calm city never reads as "elevated". Persistent (no dismiss).
  function dockCopy(b, city) {
    if (b.band === "HIGH") return { t: "Fever risk is high in " + city + " right now", s: "Share this alert so people you care about can take precautions." };
    if (b.band === "MODERATE") return { t: "Worth watching: fever risk in " + city, s: "A quick heads-up helps your family stay ahead of monsoon fevers." };
    return { t: "Help your family stay ahead of monsoon fevers", s: "Share " + city + "'s daily fever-risk tracker." };
  }
  function buildDock() {
    if (document.getElementById("fwdock") || !DATA) return;
    var el = document.createElement("aside");
    el.className = "fw-dock"; el.id = "fwdock";
    el.innerHTML = '<div class="fw-dock-title" id="fwdocktitle"></div>' +
      '<div class="fw-dock-sub" id="fwdocksub"></div>' +
      '<div class="fw-dock-actions"><button class="fw-dock-share" data-act="share">⤴ Share</button>' +
      '<button class="fw-dock-copy" data-act="dockcopy" aria-label="Copy link">🔗</button></div>';
    document.body.appendChild(el);
    updateDock();
  }
  function updateDock() {
    var t = document.getElementById("fwdocktitle"), s = document.getElementById("fwdocksub");
    if (!DATA || (!t && !s)) return;
    var c = cityObj(state.cityId), copy = dockCopy(c.blend, c.name);
    if (t) t.textContent = copy.t;
    if (s) s.textContent = copy.s;
  }

  function shareUrl() { return (FW.canonicalBase || (location.origin + CITY_ROOT)) + state.cityId + "/"; }
  function shareText(c) { var b = c.blend, drv = diseaseObj(b.driver); return "Today: " + b.band + " monsoon-fever risk in " + c.name + ", " + b.score + "/100 (top concern: " + drv.label + "), modelled from weather conditions, Google search interest and PharmEasy lab signals. Know more here: " + shareUrl(); }
  function openShare() {
    // preview = the CI-baked share card itself (assets/img/share/{city}.jpg), so what the
    // user sees is byte-identical to what gets shared - no re-drawn mock to drift.
    var c = cityObj(state.cityId);
    var src = window.FeverWatchShare ? window.FeverWatchShare.imageUrl(state.cityId, DATA.generated_at) : "";
    document.getElementById("pop").innerHTML = '<div class="pophead"><h3>Share this risk</h3><button class="x" data-act="closeShare">✕</button></div><div class="popbody">' +
      '<img class="sharecard-img" src="' + src + '" alt="' + esc(c.name) + ' monsoon fever risk score card">' +
      '<div class="sharebtns"><button data-act="shareWA" style="background:#25D366">WhatsApp</button><button data-act="shareDL" style="background:var(--pe-green)">Save image</button><button data-act="shareCopy" style="background:var(--pe-blue)">Copy link</button></div>' +
      '<div class="sharetext">' + shareText(c) + '</div></div>';
    document.getElementById("scrim").classList.add("open");
  }

  function onClick(e) {
    Array.prototype.forEach.call(document.querySelectorAll(".dialinfo.open"), function (o) { if (!o.contains(e.target)) o.classList.remove("open"); });
    if (e.target.id === "scrim") { document.getElementById("scrim").classList.remove("open"); return; }
    var jump = e.target.closest ? e.target.closest('.toc a[href^="#"]') : null;
    if (jump) { if (e.preventDefault) e.preventDefault(); var hid = jump.getAttribute("href"); var t = document.getElementById(hid.slice(1)); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); try { history.pushState(null, "", hid); } catch (e2) {} var ls = document.querySelectorAll(".toc a"); for (var i = 0; i < ls.length; i++) ls[i].classList.remove("cur"); jump.classList.add("cur"); spyScroll.lock = Date.now() + 600; return; }
    var el = e.target.closest ? e.target.closest("[data-act]") : null;
    if (!el) { if (state.comboOpen) { state.comboOpen = false; render(); } return; }
    var a = el.getAttribute("data-act");
    if (a === "combo") { state.comboOpen = !state.comboOpen; render(); if (state.comboOpen) { var inp = document.getElementById("cityinput"); renderCombo(); inp.addEventListener("input", renderCombo); inp.focus(); } e.stopPropagation(); }
    else if (a === "useLoc") { useMyLocation(); e.stopPropagation(); }
    else if (a === "pickCity" || a === "pickrow") { if (e.preventDefault) e.preventDefault(); state.comboOpen = false; setCity(el.getAttribute("data-id"), true); window.scrollTo({ top: 0, behavior: "smooth" }); }
    else if (a === "leader") { state.leader = el.getAttribute("data-id"); state.lbPage = 0; render(); document.getElementById("s-other").scrollIntoView({ behavior: "smooth" }); }
    else if (a === "lbpage") { state.lbPage = parseInt(el.getAttribute("data-page"), 10) || 0; renderLeaderboard(); }
    else if (a === "method") { state.methodOpen = !state.methodOpen; var bdy = document.getElementById("methbody"); bdy.classList.toggle("open", state.methodOpen); document.getElementById("methtog").textContent = state.methodOpen ? "Hide details ▴" : "Show details ▾"; if (state.methodOpen && window.FeverWatchMethod) window.FeverWatchMethod.wire(bdy); }
    else if (a === "expand") { state.expanded = el.getAttribute("data-id"); render(); }
    else if (a === "dialInfo") { var di = el.closest(".dialinfo"); if (di) { if (_dialTimer) { clearTimeout(_dialTimer); _dialTimer = null; } _peekEl = null; var op = di.classList.toggle("open"); if (op) positionTip(di); } }    else if (a === "openMethod") {
      // The riskcard "Know more" opens + scrolls to the methodology section (which lives at #s-method).
      state.methodOpen = true;
      var mb = document.getElementById("methbody"); if (mb) mb.classList.add("open");
      if (mb && window.FeverWatchMethod) window.FeverWatchMethod.wire(mb);
      var mt = document.getElementById("methtog"); if (mt) mt.textContent = "Hide details ▴";
      var ms = document.getElementById("s-method"); if (ms) ms.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    else if (a === "openShare" || a === "share") openShare();
    else if (a === "shareWA") doShare("wa");
    else if (a === "shareDL") doShare("dl");
    else if (a === "shareCopy") doShare("copy");
    else if (a === "dockcopy") { if (window.FeverWatchShare) window.FeverWatchShare.copyLink(shareUrl()); el.classList.add("done"); setTimeout(function () { el.classList.remove("done"); }, 1400); }
    else if (a === "closeShare") document.getElementById("scrim").classList.remove("open");
  }

  function shareCardData() {
    var c = cityObj(state.cityId);
    return { text: shareText(c), url: shareUrl() };
  }
  function doShare(kind) {
    if (!window.FeverWatchShare) return;
    var d = shareCardData(), fn = "fever-watch-" + state.cityId + ".jpg";
    if (kind === "copy") { window.FeverWatchShare.copyLink(d.url); return; }
    if (kind === "wa") { window.FeverWatchShare.whatsapp(d.text, ""); return; }  // URL is already in d.text
    window.FeverWatchShare.loadCard(state.cityId, DATA.generated_at).then(function (blob) {
      window.FeverWatchShare.download(blob, fn);
    }).catch(function () {
      // image unavailable (e.g. brand-new city before the next bake): open it directly
      window.open(window.FeverWatchShare.imageUrl(state.cityId, DATA.generated_at), "_blank");
    });
  }

  var FAQ = [
    ["What is Fever Watch?", "Fever Watch is a daily risk indicator for India's top monsoon fevers (dengue, malaria, chikungunya and typhoid), shown as one decomposable score per city and disease. It blends weather conditions, public search interest and PharmEasy lab positivity."],
    ["Is this a diagnosis or medical advice?", "No. Fever Watch is a risk indicator only. It is not a diagnosis, not a count of actual cases or mosquitoes, and not a substitute for a doctor. If you feel unwell, consult a clinician."],
    ["How is the score calculated?", "It is a transparent weighted blend of three signals at different points in the illness pipeline: weather conditions (leading), search interest (coincident) and lab positivity (lagging ground truth). When lab data is present it leads the score, and the breakdown is always shown."],
    ["What does forecast-only mean?", "Where there is not enough lab data for a city and disease yet, the score is a conditions-based forecast and is capped below the HIGH band, so a forecast-only read can never show HIGH. This keeps the read honest."],
    ["How often is it updated?", "Weather is refreshed daily from NOAA CPC and NASA POWER, search interest weekly, and the lab signal daily. The score for each city is recomputed every day."],
    ["Which cities are covered?", "Fever Watch currently covers over 200 Indian cities, with more planned. Use the city search to see the read for your city."]
  ];

  // "How we calculate the score" methodology widget (desktop layout: 2-col deskgrid, sticky score builder).
  // Behaviour (popovers / accordion / score-builder + dial) lives in assets/js/method.js; FeverWatchMethod.wire()
  // is called when the section opens (the "method" / "openMethod" actions). Hooks are namespaced (data-mpop /
  // data-mtog / data-macc / data-mmode / data-mdial-*) and classes are .mthd-* so nothing collides with the page's
  // disease-breakdown accordion. Ported from prototypes/method-section-final.html (desktop frame).
  var mthWx = '<svg viewBox="0 0 24 24"><path d="M7 18h10a4 4 0 0 0 .3-8A5.5 5.5 0 0 0 6.6 9 3.5 3.5 0 0 0 7 18z" fill="currentColor"/></svg>',
      mthSr = '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" stroke-width="2.2"/><line x1="15.5" y1="15.5" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
      mthLb = '<svg viewBox="0 0 24 24"><path d="M10 3h4v5l4 8a2 2 0 0 1-1.8 3H7.8A2 2 0 0 1 6 16l4-8V3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
      mthSrc = '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M19 13v6H5V5h6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      mthDrop = '<svg viewBox="0 0 24 24"><path d="M12 2s7 8 7 13a7 7 0 0 1-14 0c0-5 7-13 7-13z" fill="currentColor"/></svg>';

  var METHOD =
    '<div class="mthd">' +
      '<p class="mthd-lead">One score from 0 to 100 for each city and fever. It shows how strongly the warning signs line up. A risk indicator, not a diagnosis, not a case count, and not medical advice.</p>' +
      '<div class="mthd-intro">We read <b>3 signals</b>. Each is scored <b>0 to 100 on its own first</b>, then we blend them into the single number you see. The score stays calm by default and only gets loud when the signals agree.' +
        '<div class="mthd-step3">' +
          '<span class="s"><span class="ic" style="color:var(--sig-weather)">' + mthWx + '</span>Weather</span>' +
          '<span class="arr">+</span>' +
          '<span class="s"><span class="ic" style="color:var(--sig-search)">' + mthSr + '</span>Searches</span>' +
          '<span class="arr">+</span>' +
          '<span class="s"><span class="ic" style="color:var(--sig-lab)">' + mthLb + '</span>Lab</span>' +
          '<span class="arr">=</span>' +
          '<span class="s" style="background:var(--pe-green);color:#fff;border-color:var(--pe-green);font-weight:800">One score</span>' +
        '</div>' +
      '</div>' +
      '<div class="mthd-acc" data-macc>' +
            '<div class="mthd-accitem open" data-sig="weather">' +
              '<button class="mthd-acchead" data-mtog>' +
                '<span class="badge">' + mthWx + '</span>' +
                '<span class="tt"><span class="nm">Weather <span class="role">leading</span></span><span class="ds">Is the weather raising risk right now?</span></span>' +
                '<span style="text-align:right"><span class="wt">30%</span><span class="wl">in blend</span></span><span class="chev"></span>' +
              '</button>' +
              '<div class="mthd-accbody">' +
                '<p class="bnote">For the mosquito fevers (dengue, malaria, chikungunya) the weather score mixes three things. The weights below are <span class="mthd-ourset" tabindex="0" data-mpop="set" data-title="Weather weights" data-body="The 45 / 35 / 20 split between temperature, rain and humidity is our own calibration, not a published constant.">our assumption</span>.</p>' +
                '<div class="mthd-wbar temp"><div class="top"><span class="nm">Temperature</span><span class="sub">best near 26-29C</span><span class="pct">45%</span></div><div class="mthd-track"><div class="mthd-fill" style="width:45%"></div></div><div class="mk"><span class="mthd-src" tabindex="0" data-mpop="source" data-title="Temperature drives transmission" data-body="Transmission is fastest around 26 to 29C and slows when it is colder or hotter. Temperature carries the most weight because it speeds up both the mosquito and the virus." data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC6518529/#sec5">' + mthSrc + 'Source</span></div></div>' +
                '<div class="mthd-wbar rain"><div class="top"><span class="nm">Rain</span><span class="sub">trailing 14 days, then capped</span><span class="pct">35%</span></div><div class="mthd-track"><div class="mthd-fill" style="width:35%"></div></div><div class="mk"><span class="mthd-src" tabindex="0" data-mpop="source" data-title="Rain makes mosquito sites" data-body="Puddles take about 1 to 3 weeks to become biting mosquitoes, so we look back across recent rain." data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC6518529">' + mthSrc + 'Source</span><span class="mthd-ourset" tabindex="0" data-mpop="set" data-title="14-day window" data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC6518529" data-body="The exact 14-day look-back, and capping rain past a point (beyond which more rain stops adding risk), are our calibration, informed by how long mosquitoes take to develop after rain.">our assumption</span></div></div>' +
                '<div class="mthd-wbar hum"><div class="top"><span class="nm">Humidity</span><span class="sub">helps adult mosquitoes survive</span><span class="pct">20%</span></div><div class="mthd-track"><div class="mthd-fill" style="width:20%"></div></div><div class="mk"><span class="mthd-src" tabindex="0" data-mpop="source" data-title="Humidity aids survival" data-body="Higher humidity lets adult mosquitoes live longer, so they have more time to bite." data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC6744319/">' + mthSrc + 'Source</span></div></div>' +
                '<div class="mthd-typnote"><div class="h">' + mthDrop + 'Typhoid is different: rain only</div>Typhoid is waterborne, so its weather score uses <b>recent plus lagged rain only</b> (dirty water after heavy rain), often within days. Temperature is minor here. The rain windows are <span class="mthd-ourset" tabindex="0" data-mpop="set" data-title="Typhoid rain windows" data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC8832923/" data-body="Which rain windows feed the typhoid contamination proxy is our calibration, informed by research linking heavy rain to typhoid.">our assumption</span>. <span class="mthd-src" tabindex="0" data-mpop="source" data-title="Rain and typhoid" data-body="Typhoid spreads through water dirtied by heavy rain, often within days of the rainfall." data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC8832923/">' + mthSrc + 'Source</span></div>' +
              '</div>' +
            '</div>' +
            '<div class="mthd-accitem" data-sig="search">' +
              '<button class="mthd-acchead" data-mtog>' +
                '<span class="badge">' + mthSr + '</span>' +
                '<span class="tt"><span class="nm">Searches <span class="role">coincident</span></span><span class="ds">How many people nearby search the symptoms</span></span>' +
                '<span style="text-align:right"><span class="wt">22%</span><span class="wl">in blend</span></span><span class="chev"></span>' +
              '</button>' +
              '<div class="mthd-accbody">' +
                '<p class="bnote">We count how often people near you search that fever&#39;s symptoms (Google Trends), measured against the <b>typical range for your own city</b> so a big city does not always look busy. It reflects public concern, alongside the weather, not after it.</p>' +
                '<p class="bnote">We trust it less when it spikes on news alone, which is exactly why it is only 1 of 3 signals. <span class="mthd-src" tabindex="0" data-mpop="source" data-title="Search tracks outbreaks" data-body="Search interest tracks real outbreaks, with the well-known caveat that search on its own can mislead during a news spike. That caveat is why search is never used alone here." data-href="https://pubmed.ncbi.nlm.nih.gov/30443418/" data-href2="https://link.springer.com/article/10.1186/s12879-025-10801-0">' + mthSrc + 'Source</span></p>' +
              '</div>' +
            '</div>' +
            '<div class="mthd-accitem" data-sig="lab">' +
              '<button class="mthd-acchead" data-mtog>' +
                '<span class="badge">' + mthLb + '</span>' +
                '<span class="tt"><span class="nm">Lab <span class="role">ground truth</span></span><span class="ds">Share of local tests that come back positive</span></span>' +
                '<span style="text-align:right"><span class="wt">48%</span><span class="wl">in blend</span></span><span class="chev"></span>' +
              '</button>' +
              '<div class="mthd-accbody">' +
                '<p class="bnote">From <b>PharmEasy Labs and its Partner Affiliates</b>, always aggregate and de-identified. Of the local tests taken for that fever over a recent window, what share come back <b>positive</b> (test positivity). It needs a minimum number of tests to count, a gate, so a handful of results never swings the score.</p>' +
                '<p class="bnote" style="margin-bottom:6px">The positivity that maps to a full 100 <b>differs by disease</b>, because each fever sits at its own normal baseline:</p>' +
                '<div class="mthd-labchips">' +
                  '<span class="chip"><span class="cdot" style="background:var(--dis-dengue)"></span>Dengue <b>25%</b></span>' +
                  '<span class="chip"><span class="cdot" style="background:var(--dis-chikungunya)"></span>Chikungunya <b>15%</b></span>' +
                  '<span class="chip"><span class="cdot" style="background:var(--dis-malaria)"></span>Malaria <b>4%</b></span>' +
                  '<span class="chip"><span class="cdot" style="background:var(--dis-typhoid)"></span>Typhoid <b>45%</b></span>' +
                '</div>' +
                '<p class="bnote" style="margin:13px 0 0">Malaria is usually under a few percent and typhoid is common year-round, so one shared cutoff would make malaria always look calm and typhoid always look alarming. These numbers are <span class="mthd-ourset" tabindex="0" data-mpop="set" data-title="Calibrated from our 2025 data" data-href="https://emergency.unhcr.org/emergency-assistance/health-and-nutrition/disease-surveillance-thresholds" data-body="The 25 / 15 / 4 / 45 thresholds are our benchmark, set near the 90th percentile of last season&#39;s positivity per disease in PharmEasy&#39;s own 2025 lab data, following the agency practice of a per-disease baseline.">our assumption</span> (from our 2025 lab data) and match how health agencies track each disease against its own baseline. <span class="mthd-src" tabindex="0" data-mpop="source" data-title="Surveillance thresholds" data-body="Public-health surveillance sets a per-disease threshold against each disease&#39;s own baseline, rather than one shared cutoff." data-href="https://emergency.unhcr.org/emergency-assistance/health-and-nutrition/disease-surveillance-thresholds">' + mthSrc + 'Thresholds</span> <span class="mthd-src" tabindex="0" data-mpop="source" data-title="Test positivity" data-body="Test positivity (the share of tests that come back positive) is a standard public-health measure of how active a disease is." data-href="https://pmc.ncbi.nlm.nih.gov/articles/PMC6609187/">' + mthSrc + 'Positivity</span></p>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div class="mthd-card" style="padding:14px 16px;margin-top:2px">' +
            '<p class="mthd-ch" style="margin:0 0 10px">Your city\'s one number</p>' +
            '<p style="margin:0;font-size:13px;color:var(--pe-ink-2);line-height:1.55">Each fever gets its own 0 to 100 score. The headline you see is led by the highest-risk fever (its driver) at about <b>80%</b>, plus a <b>20%</b> share of the other three - so it tracks what you most need to watch without ignoring the rest.</p>' +
          '</div>' +
          '<div class="mthd-card" style="padding:14px 16px;margin-top:2px">' +
            '<p class="mthd-ch" style="margin:0 0 10px">What the colour means</p>' +
            '<div class="mthd-bandstrip">' +
              '<span class="seg" style="background:var(--risk-low)"><span class="bn">Low</span><span class="br">0-24</span></span>' +
              '<span class="seg lowmod" style="background:var(--risk-lowmod)"><span class="bn">Low-mod</span><span class="br">25-44</span></span>' +
              '<span class="seg" style="background:var(--risk-mod)"><span class="bn">Moderate</span><span class="br">45-69</span></span>' +
              '<span class="seg" style="background:var(--risk-high)"><span class="bn">High</span><span class="br">70-100</span></span>' +
            '</div>' +
            '<p class="mthd-foot" style="margin:0">A forecast-only read (no lab data) is capped at 69, so it can never reach the red High band.</p>' +
          '</div>' +
        '<div class="mthd-exblock" data-mthd-examples></div>' +
      '<p class="mthd-foot" style="margin-top:16px"><span class="one">A risk indicator, not a diagnosis or a case count.</span>Sources: rainfall NOAA CPC; temperature and humidity NASA POWER; search Google Trends; positivity PharmEasy Labs and its Partner Affiliates (aggregate, de-identified).</p>' +
    '</div>';

  // All render() dependencies (FAQ, METHOD, ...) are now defined. Boot: seed first (instant first
  // paint from the inlined city data), then the full grid in the background for the leaderboard.
  function loadArchive(tries) {
    if (!FW.archiveUrl) return Promise.resolve(null);
    return fetch(FW.archiveUrl, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).catch(function (e) {
      if (tries > 1) return new Promise(function (res) { setTimeout(res, 500); }).then(function () { return loadArchive(tries - 1); });
      console.warn("archive load failed (season-trend falls back):", e && e.message); return null;
    });
  }
  if (FW.seed) { try { boot(FW.seed); idleWarm(); } catch (e) { console.error("seed boot failed:", e); } }
  // Kick off BOTH fetches immediately: the small (~82KB) archive no longer waits behind the ~950KB grid,
  // so the real season-trend lands as soon as possible. We boot once both settle so the leaderboard and the
  // full-archive trend hydrate together. There is NO mock: when the archive loads, every city renders real;
  // if the archive fetch hard-fails we carry the seed's inlined slice forward so the CURRENT city stays real,
  // and trend.js shows a skeleton (never a fabricated chart) for any city whose slice is not present.
  var pGrid = loadGrid(4), pArchive = loadArchive(3);
  pGrid.then(function (j) {
    return pArchive.then(function (a) {
      if (a) j.archive = a;
      else if (FW.seed && FW.seed.archive) j.archive = FW.seed.archive;
      boot(j); maybeGeo(); idleWarm();
    });
  }).catch(function (e) { console.error("grid load/boot failed:", e); if (!DATA) app.innerHTML = '<div class="shell"><div class="card">Could not load data: ' + e.message + '</div></div>'; });
})();
