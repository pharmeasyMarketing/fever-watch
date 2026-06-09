(function () {
  "use strict";
  var FW = window.FW || {};
  var LOGO = FW.logo || "assets/img/pe_logo-white.svg";
  var RISK = { "HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F" };
  var RISK_SOFT = { "HIGH": "#FCEBE4", "MODERATE": "#FBF0E2", "LOW-MODERATE": "#F7F3E1", "LOW": "#E4F4EC" };
  var BEACON_DUR = { "HIGH": "0.85s", "MODERATE": "1.3s", "LOW-MODERATE": "1.9s", "LOW": "2.8s" };
  function beacon(band) { return '<span class="beacon" style="--c:' + (RISK[band] || "#888") + ';--bdur:' + (BEACON_DUR[band] || "1.6s") + '"><i></i></span>'; }
  var SIGCOL = { weather: [21, 172, 165], trends: [124, 108, 214], positivity: [54, 97, 176] };
  var SIGNAME = { weather: "Breeding weather", trends: "Google Search Interest", positivity: "PharmEasy labs" };
  var ACTIONS = [
    { ic: "🛡", t: "Monsoon precautions", s: "Cut breeding sites and bites", lnk: "Read the guide" },
    { ic: "💉", t: "Vaccination: does it work?", s: "What helps, what does not", lnk: "Learn more" },
    { ic: "🌡", t: "Fever? Our framework", s: "When to test, when to wait", lnk: "See the steps" },
    { ic: "🩺", t: "Not sure? Talk to a doctor", s: "Online consult on PharmEasy", lnk: "Book a consult" }
  ];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DATA = null, state = { cityId: null, leader: "overall", comboOpen: false, methodOpen: false, lbQuery: "", lbPage: 0 }, app = document.getElementById("fw-app");

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
    if (!booted) { booted = true; document.addEventListener("click", onClick); }
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
  function fmtDate(iso) { if (!iso) return ""; var d = new Date(iso); return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear(); }
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
    if (push) { try { history.pushState(null, "", cityHref(id)); } catch (e) {} }
    render();
  }
  function onPop() {
    if (!DATA) return;
    var id = cityFromPath();
    if (id && id !== state.cityId && DATA.cities.some(function (c) { return c.id === id; })) {
      state.cityId = id; render(); window.scrollTo(0, 0);
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
    var ids = ["s-week", "s-method", "s-do", "s-other", "s-faq", "s-reads"], cur = ids[0];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el && el.getBoundingClientRect().top <= 110) cur = ids[i];
    }
    var doc = document.documentElement;
    if ((window.innerHeight + (window.scrollY || window.pageYOffset || 0)) >= (doc.scrollHeight - 4)) cur = ids[ids.length - 1];
    var links = document.querySelectorAll(".toc a");
    for (var j = 0; j < links.length; j++) links[j].classList.toggle("cur", links[j].getAttribute("data-jump") === cur);
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
    app.innerHTML = searchHero(c) +
      '<div class="shell"><aside class="toc">' +
        '<a class="cur" data-jump="s-week">This week</a><a data-jump="s-method">Scoring methodology</a><a data-jump="s-do">What to do</a><a data-jump="s-other">City-level insights</a><a data-jump="s-faq">Common questions</a><a data-jump="s-reads">Monsoon reads</a>' +
      '</aside><div class="main">' + weekSection(c, b) + methodSection() + doSection(c) + otherSection(c) + faqSection() + readsSection() + '</div></div>';
    wireLeaderboard();
    wireScrollSpy();
    updateDock();
    document.body.classList.add("fw-hydrated");
  }

  function searchHero(c) {
    return '<section class="srch"><div class="srchin">' +
      '<h1>Live monsoon-fever risk for ' + esc(c.name) + ', in <em>one score</em>.</h1>' +
      '<p class="subtitle">Dengue, malaria, chikungunya, typhoid and viral fever, blended from breeding weather, Google Search interest and PharmEasy lab signals.</p>' +
      '<div class="searchbar"><span class="ico">🔎</span>' +
        '<button class="field" data-act="combo">📍 ' + c.name + '  <span class="ph">| change your city</span></button>' +
        '<button class="searchbtn" data-act="combo">Search</button>' +
        '<div class="combopanel' + (state.comboOpen ? ' open' : '') + '"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>' +
      '</div><p class="microcopy">Available in select cities, more coming soon.</p></div></section>';
  }

  function weekSection(c, b) {
    var col = RISK[b.band], drvCell = cellFor(c.id, b.driver), drv = diseaseObj(b.driver);
    var pills = orderedDiseases(c).map(function (d) { var cell = cellFor(c.id, d.id); return '<span class="dpill"><span class="dot" style="background:' + RISK[cell.band] + '"></span>' + d.emoji + ' ' + d.label + ' <b>' + cell.score + '</b></span>'; }).join("");
    var card = '<div class="card risk"><div class="rtop">' + gauge(b.score, col, 112) +
      '<div class="rhead"><div class="ov">Overall monsoon-fever risk, this week</div><div class="bandlbl" style="color:' + col + '">' + beacon(b.band) + b.band + '</div></div></div>' +
      '<div class="driverrow"><span class="driver" style="background:' + RISK_SOFT[drvCell.band] + ';color:' + RISK[drvCell.band] + '">Top concern: ' + drv.emoji + ' ' + drv.label + ' ' + drvCell.band + ' (' + b.driver_score + ')</span></div>' +
      '<div class="pills">' + pills + '</div>' +
      '<div class="rfoot"><span class="note">Scores modeled from breeding weather, Google search interest and PharmEasy lab signals.</span><button class="sharebtn" data-act="share">⤴ Share</button></div></div>';
    return '<section id="s-week"><h2 class="sechead">' + c.name + ', this week</h2>' +
      '<p class="secsub">Updated ' + fmtDate(DATA.generated_at) + '. One headline score plus the signal mix behind it.</p>' +
      '<div class="grid2">' + card + heatmapCard(c) + '</div></section>';
  }

  // Ranked composite bars (brand-recreated from the design handoff). Each fever is one composite bar,
  // segmented by its three signals (segment width = signal / sum * score, integer %), ordered high to
  // low with the top concern flagged and the score in its band colour. Replaces the old heatmap.
  var CAT = { mosquito: "Mosquito-borne", waterborne: "Water / food-borne", febrile: "Viral, airborne" };
  function heatmapCard(c) {
    var rows = orderedDiseases(c).map(function (d, i) {
      var cell = cellFor(c.id, d.id), col = RISK[cell.band], sg = cell.signals;
      var weather = sg.weather, search = sg.trends, labs = sg.positivity;
      var wn = weather || 0, sn = search || 0, ln = labs || 0, denom = wn + sn + ln, sc = cell.score;
      var ww = denom ? Math.round(wn / denom * sc) : 0, ws = denom ? Math.round(sn / denom * sc) : 0, wl = denom ? Math.round(ln / denom * sc) : 0;
      var wv = weather == null ? "n/a" : weather, sv = search == null ? "n/a" : search, lv = labs == null ? "n/a" : labs;
      var top = i === 0 ? '<span class="sbar-top">Top concern</span>' : '';
      return '<div class="sbar-row"><div class="sbar-id"><span class="sbar-rank">' + (i + 1) + '</span><span class="sbar-emoji">' + d.emoji + '</span><span class="sbar-name"><b>' + d.label + '</b><i>' + (CAT[cell.family] || "") + '</i></span></div>' +
        '<div class="sbar-mid"><div class="sbar-track"><span style="width:' + ww + '%;background:#15ACA5"></span><span style="width:' + ws + '%;background:#7C6CD6"></span><span style="width:' + wl + '%;background:#3661B0"></span></div>' +
        '<div class="sbar-strip"><span><i style="background:#15ACA5"></i>Weather ' + wv + '</span><span><i style="background:#7C6CD6"></i>Search ' + sv + '</span><span><i style="background:#3661B0"></i>Labs ' + lv + '</span></div></div>' +
        '<div class="sbar-score" style="color:' + col + '">' + sc + top + '</div></div>';
    }).join("");
    return '<div class="card sbars"><div class="sbar-head"><div class="sbar-title">This week\'s outbreak signal score</div><div class="sbar-sub">Ranked by composite score - five fevers we track in ' + c.name + '</div></div><div class="sbar-list">' + rows + '</div>' +
      '<div class="sbar-legend"><span class="k"><span class="sw" style="background:#15ACA5"></span>Weather (leading)</span>' +
      '<span class="k"><span class="sw" style="background:#7C6CD6"></span>Search (coincident)</span>' +
      '<span class="k"><span class="sw" style="background:#3661B0"></span>Labs (ground truth)</span></div></div>';
  }

  function doSection(c) {
    var cards = ACTIONS.map(function (a) { return '<div class="actcard"><div class="ic">' + a.ic + '</div><b>' + a.t + '</b><span>' + a.s + '</span><a class="lnk" href="#">' + a.lnk + ' ›</a></div>'; }).join("");
    return '<section id="s-do"><h2 class="sechead">So, what should I do?</h2><p class="secsub">Practical follow-through for ' + c.name + ' this week.</p>' +
      '<div class="actrow">' + cards + '</div><button class="ctabig" style="background:var(--pe-green)">Book a fever panel test</button></section>';
  }

  function methodSection() {
    return '<section id="s-method"><div class="card">' +
      '<h2 class="sechead" style="margin:0 0 2px">How we calculate this</h2>' +
      '<button class="methhead" data-act="method"><span class="secsub" style="margin:0">Transparent and decomposable, not a black box.</span>' +
      '<span class="methtog" id="methtog">Show details ▾</span></button>' +
      '<div class="methbody' + (state.methodOpen ? ' open' : '') + '" id="methbody">' + METHOD + '</div></div></section>';
  }

  function otherSection(c) {
    var isOverall = state.leader === "overall";
    var label = isOverall ? "Overall" : diseaseObj(state.leader).label;
    var tabs = '<button class="lbtab' + (isOverall ? " on" : "") + '" data-act="leader" data-id="overall">📊 Overall</button>' +
      DATA.diseases.map(function (d) { return '<button class="lbtab' + (d.id === state.leader ? " on" : "") + '" data-act="leader" data-id="' + d.id + '">' + d.emoji + ' ' + d.label + '</button>'; }).join("");
    return '<section id="s-other"><h2 class="sechead">What is happening in other cities?</h2><p class="secsub">' + label + ' risk leaderboard this week. Pick a disease to re-rank.</p>' +
      '<div class="lbtabs">' + tabs + '</div>' +
      '<input class="lbsearch" id="lbsearch" placeholder="Search a city" value="' + esc(state.lbQuery) + '" autocomplete="off" />' +
      '<div id="lbcontainer">' + leaderboardInner(c) + '</div></section>';
  }

  function leaderboardInner(c) {
    var PER = 10;
    var ranked = DATA.cities.map(function (ci) { var lr = leaderRow(ci); return { id: ci.id, name: ci.name, state: ci.state, score: lr.score, band: lr.band }; }).sort(function (a, b) { return b.score - a.score; });
    ranked.forEach(function (r, i) { r.rank = i + 1; });
    var q = (state.lbQuery || "").toLowerCase();
    var filtered = q ? ranked.filter(function (r) { return r.name.toLowerCase().indexOf(q) >= 0 || (r.state || "").toLowerCase().indexOf(q) >= 0; }) : ranked;
    var pages = Math.max(1, Math.ceil(filtered.length / PER));
    var page = Math.min(state.lbPage || 0, pages - 1);
    var slice = filtered.slice(page * PER, page * PER + PER);
    var body = slice.map(function (r) {
      return '<tr class="' + (r.id === state.cityId ? "you" : "") + '" data-act="pickrow" data-id="' + r.id + '"><td class="rk">' + r.rank + '</td><td><a class="lbcity" href="' + cityHref(r.id) + '">' + r.name + '</a>' + (r.id === state.cityId ? " (you)" : "") + '</td>' +
        '<td style="color:var(--pe-muted)">' + r.state + '</td><td class="bar"><i style="width:' + r.score + '%;background:' + RISK[r.band] + '"></i></td>' +
        '<td><span class="bd" style="background:' + RISK_SOFT[r.band] + ';color:' + RISK[r.band] + '">' + r.band + '</span></td><td style="font-weight:700;color:' + RISK[r.band] + '">' + r.score + '</td></tr>';
    }).join("");
    var table = '<table class="lbtable"><thead><tr><th>#</th><th>City</th><th>State</th><th>Risk</th><th>Band</th><th>Score</th></tr></thead><tbody>' +
      (body || '<tr><td colspan="6" style="text-align:center;color:var(--pe-muted);padding:18px">No city matches "' + esc(state.lbQuery) + '".</td></tr>') + '</tbody></table>';
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

  function gauge(score, color, size) {
    var sw = 11, cx = size / 2, r = (size - sw) / 2 - 1, C = 2 * Math.PI * r, arc = 0.75;
    var track = (arc * C).toFixed(1), gap = (C - arc * C).toFixed(1), prog = (Math.max(0, Math.min(100, score)) / 100 * arc * C).toFixed(1);
    return '<div class="gaugewrap" style="width:' + size + 'px;height:' + size + 'px"><svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="#e9eef5" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gap + '" transform="rotate(135 ' + cx + ' ' + cx + ')"/>' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + prog + ' ' + (C * 2).toFixed(1) + '" transform="rotate(135 ' + cx + ' ' + cx + ')" style="transition:stroke-dasharray 1s ease"/>' +
      '</svg><div class="num"><b style="color:' + color + '">' + score + '</b><span>/ 100</span></div></div>';
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
  function buildDock() {
    if (document.getElementById("fwdock") || !DATA) return;
    var el = document.createElement("aside");
    el.className = "fw-dock"; el.id = "fwdock";
    el.innerHTML = '<div class="fw-dock-title">1 in 3 fevers in India isn\'t just a fever</div>' +
      '<div class="fw-dock-sub" id="fwdocksub"></div>' +
      '<div class="fw-dock-actions"><button class="fw-dock-share" data-act="share">⤴ Share</button>' +
      '<button class="fw-dock-copy" data-act="dockcopy" aria-label="Copy link">🔗</button></div>';
    document.body.appendChild(el);
    updateDock();
  }
  function updateDock() {
    var s = document.getElementById("fwdocksub");
    if (s && DATA) s.textContent = "Spread awareness. Share " + cityObj(state.cityId).name + "'s score.";
  }

  function shareUrl() { return (FW.canonicalBase || (location.origin + CITY_ROOT)) + state.cityId + "/"; }
  function shareText(c) { var b = c.blend, drv = diseaseObj(b.driver); return "This Week: " + b.band + " monsoon-fever risk in " + c.name + ", " + b.score + "/100 (top concern: " + drv.label + "), modelled from breeding weather, Google search interest and PharmEasy lab signals. Know more here: " + shareUrl(); }
  function openShare() {
    var c = cityObj(state.cityId), b = c.blend, drv = diseaseObj(b.driver), col = RISK[b.band];
    document.getElementById("pop").innerHTML = '<div class="pophead"><h3>Share this risk</h3><button class="x" data-act="closeShare">✕</button></div><div class="popbody">' +
      '<div class="sharecard"><div class="sc-head"><img src="' + LOGO + '" alt="PharmEasy"><span class="fw">Fever Watch</span></div>' +
      '<div class="sc-body"><div class="sc-emoji">' + drv.emoji + '</div><div class="sc-label">Monsoon Fever Risk Score</div>' +
      '<div class="sc-score">' + b.score + '<span>/100</span></div>' +
      '<span class="sc-band" style="color:' + col + '">' + b.band + ' RISK</span><div class="sc-title">📍 ' + c.name + '</div>' +
      '<div class="sc-sub">' + drv.emoji + ' Top concern: ' + drv.label + '. This week, ' + fmtDate(DATA.generated_at) + '</div></div><div class="sc-foot">Check your city at pharmeasy.in/fever-watch</div></div>' +
      '<div class="sharetext">' + shareText(c) + '</div>' +
      '<div class="sharebtns"><button data-act="shareWA" style="background:#25D366">WhatsApp</button><button data-act="shareDL" style="background:var(--pe-green)">Save image</button><button data-act="shareCopy" style="background:var(--pe-blue)">Copy link</button></div></div>';
    document.getElementById("scrim").classList.add("open");
  }

  function onClick(e) {
    if (e.target.id === "scrim") { document.getElementById("scrim").classList.remove("open"); return; }
    var el = e.target.closest ? e.target.closest("[data-act],[data-jump]") : null;
    if (!el) { if (state.comboOpen) { state.comboOpen = false; render(); } return; }
    if (el.hasAttribute("data-jump")) { var t = document.getElementById(el.getAttribute("data-jump")); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); var ls = document.querySelectorAll(".toc a"); for (var i = 0; i < ls.length; i++) ls[i].classList.remove("cur"); el.classList.add("cur"); spyScroll.lock = Date.now() + 600; return; }
    var a = el.getAttribute("data-act");
    if (a === "combo") { state.comboOpen = !state.comboOpen; render(); if (state.comboOpen) { var inp = document.getElementById("cityinput"); renderCombo(); inp.addEventListener("input", renderCombo); inp.focus(); } e.stopPropagation(); }
    else if (a === "useLoc") { useMyLocation(); e.stopPropagation(); }
    else if (a === "pickCity" || a === "pickrow") { if (e.preventDefault) e.preventDefault(); state.comboOpen = false; setCity(el.getAttribute("data-id"), true); window.scrollTo({ top: 0, behavior: "smooth" }); }
    else if (a === "leader") { state.leader = el.getAttribute("data-id"); state.lbPage = 0; render(); document.getElementById("s-other").scrollIntoView({ behavior: "smooth" }); }
    else if (a === "lbpage") { state.lbPage = parseInt(el.getAttribute("data-page"), 10) || 0; renderLeaderboard(); }
    else if (a === "method") { state.methodOpen = !state.methodOpen; var bdy = document.getElementById("methbody"); bdy.classList.toggle("open", state.methodOpen); document.getElementById("methtog").textContent = state.methodOpen ? "Hide details ▴" : "Show details ▾"; }
    else if (a === "share") openShare();
    else if (a === "shareWA") doShare("wa");
    else if (a === "shareDL") doShare("dl");
    else if (a === "shareCopy") doShare("copy");
    else if (a === "dockcopy") { if (window.FeverWatchShare) window.FeverWatchShare.copyLink(shareUrl()); el.classList.add("done"); setTimeout(function () { el.classList.remove("done"); }, 1400); }
    else if (a === "closeShare") document.getElementById("scrim").classList.remove("open");
  }

  function shareCardData() {
    var c = cityObj(state.cityId), b = c.blend, drv = diseaseObj(b.driver);
    return {
      card: { score: b.score, band: b.band, bandColor: RISK[b.band], city: c.name, state: c.state, driverLabel: drv.label, driverEmoji: drv.emoji, date: "This week, " + fmtDate(DATA.generated_at) },
      text: shareText(c), url: shareUrl()
    };
  }
  function doShare(kind) {
    if (!window.FeverWatchShare) return;
    var d = shareCardData(), fn = "fever-watch-" + state.cityId + ".jpg";
    if (kind === "copy") { window.FeverWatchShare.copyLink(d.url); return; }
    window.FeverWatchShare.renderCard(d.card).then(function (canvas) {
      if (kind === "wa") window.FeverWatchShare.whatsapp(d.text, "");  // URL is already in d.text
      else window.FeverWatchShare.download(canvas, fn);
    });
  }

  var FAQ = [
    ["What is Fever Watch?", "Fever Watch is a daily risk indicator for India's top monsoon fevers (dengue, malaria, chikungunya, typhoid and viral fever), shown as one decomposable score per city and disease. It blends breeding weather, public search interest and PharmEasy lab positivity."],
    ["Is this a diagnosis or medical advice?", "No. Fever Watch is a risk indicator only. It is not a diagnosis, not a count of actual cases or mosquitoes, and not a substitute for a doctor. If you feel unwell, consult a clinician."],
    ["How is the score calculated?", "It is a transparent weighted blend of three signals at different points in the illness pipeline: breeding weather (leading), search interest (coincident) and lab positivity (lagging ground truth). When lab data is present it leads the score, and the breakdown is always shown."],
    ["What does forecast-only mean?", "Where there is not enough lab data for a city and disease yet, the score is a conditions-based forecast and is capped below the HIGH band, so a forecast-only read can never show HIGH. This keeps the read honest."],
    ["How often is it updated?", "Weather is refreshed daily from NASA POWER, search interest weekly, and the lab signal daily. The score for each city is recomputed every day."],
    ["Which cities are covered?", "Fever Watch currently covers over 200 Indian cities, with more planned. Use the city search to see the read for your city."]
  ];

  var METHOD =
    '<div class="methgrid"><div>' +
    '<h3>1. Per-disease environmental score (0 to 100)</h3><p>From trailing daily weather, shaped by disease family:</p><ul>' +
    '<li><b>Mosquito-borne</b> (dengue, malaria, chikungunya): a unimodal temperature response peaking near <code>29&deg;C</code> (Aedes and Anopheles breed fastest at 25 to 30&deg;C; activity falls below ~18&deg;C and above ~35&deg;C), times lagged rainfall over the past ~14 days (standing-water sites emerge 1 to 2 weeks after rain), times relative humidity (above ~60% extends mosquito lifespan). Weights ~0.45 / 0.35 / 0.20.</li>' +
    '<li><b>Waterborne</b> (typhoid): recent (7-day) plus accumulated (14-day) rainfall as a contamination and runoff proxy; temperature secondary.</li>' +
    '<li><b>Febrile</b> (viral fever): humidity, day-to-day temperature variability, and rainfall.</li></ul>' +
    '<h3>2. Three independent signals</h3><ul>' +
    '<li><b>Breeding weather</b> (leading, ~weeks ahead): the environmental score above.</li>' +
    '<li><b>Google Search Interest</b> (coincident): symptom-search attention, smoothed; down-weighted when it spikes alone.</li>' +
    '<li><b>PharmEasy lab signal</b> (lagging, ground truth): aggregate, de-identified test-positivity trend.</li></ul>' +
    '<h3>3. Confirmation-weighted ensemble</h3><p>Not a flat average. With lab data present it dominates (weights ~<code>30 / 22 / 48</code> weather / search / positivity) and agreement raises confidence. Without it, a capped <code>forecast-only</code> mode (max 69, below HIGH) keeps a conditions-only read honest. The city headline is a max-dominant blend (<code>0.8 &times; top + 0.2 &times; mean of the rest</code>) with the driver disease named.</p>' +
    '</div><div class="side"><h3>Data sources</h3><ul><li>Weather: NASA POWER (US public domain / CC0)</li><li>Search: Google Trends</li><li>Positivity: PharmEasy diagnostics (aggregate, de-identified)</li></ul>' +
    '<h3>Selected research</h3>' +
    '<p class="cite">Ginsberg et al. Detecting influenza epidemics using search engine query data. <i>Nature</i>, 2009.</p>' +
    '<p class="cite">Mordecai et al. Thermal biology of mosquito-borne disease. <i>Ecology Letters</i>, 2019.</p>' +
    '<p class="cite">Liu-Helmersson et al. Vectorial capacity of Aedes aegypti and temperature. <i>PLOS ONE</i>, 2014.</p>' +
    '<p class="cite">Brady et al. Modelling adult Aedes survival at different temperatures. <i>Parasites &amp; Vectors</i>, 2013.</p>' +
    '<p class="cite">Naish et al. Climate change and dengue: a systematic review. <i>BMC Infectious Diseases</i>, 2014.</p>' +
    '<p class="cite">IDSP Weekly Outbreak Reports, MoHFW.</p>' +
    '<p style="margin-top:12px;color:var(--pe-muted-2);font-size:11.5px">A risk indicator, not a diagnosis or a case count.</p></div></div>';

  // All render() dependencies (FAQ, METHOD, ...) are now defined. Boot: seed first (instant first
  // paint from the inlined city data), then the full grid in the background for the leaderboard.
  if (FW.seed) { try { boot(FW.seed); } catch (e) { console.error("seed boot failed:", e); } }
  loadGrid(4).then(function (j) {
    boot(j); maybeGeo();
  }).catch(function (e) { console.error("grid load/boot failed:", e); if (!DATA) app.innerHTML = '<div class="shell"><div class="card">Could not load data: ' + e.message + '</div></div>'; });
})();
