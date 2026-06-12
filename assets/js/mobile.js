(function () {
  "use strict";
  var FW = window.FW || {};
  var RISK = { "HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F" };
  var RISK_SOFT = { "HIGH": "#FCEBE4", "MODERATE": "#FBF0E2", "LOW-MODERATE": "#F7F3E1", "LOW": "#E4F4EC" };
  var BEACON_DUR = { "HIGH": "0.85s", "MODERATE": "1.3s", "LOW-MODERATE": "1.9s", "LOW": "2.8s" };
  function beacon(band) { return '<span class="beacon" style="--c:' + (RISK[band] || "#888") + ';--bdur:' + (BEACON_DUR[band] || "1.6s") + '"><i></i></span>'; }
  var SIG = {
    weather: { c: "#15ACA5", label: "🌧 Breeding weather", tag: "Leading. Conditions weeks ahead." },
    trends: { c: "#7C6CD6", label: "🔍 Google Search Interest", tag: "Coincident. Public concern." },
    positivity: { c: "#3661B0", label: "🧪 PharmEasy lab signal", tag: "Lagging. Confirmed positivity." }
  };
  var ACTIONS = [
    { ic: "🛡", t: "Monsoon precautions", s: "Cut breeding sites and bites", href: "#" },
    { ic: "💉", t: "Vaccination: does it work?", s: "What helps, what does not", href: "#" },
    { ic: "🌡", t: "Fever? Follow our framework", s: "When to test, when to wait", href: "#" },
    { ic: "🩺", t: "Not sure? Talk to a doctor", s: "Online consult on PharmEasy", href: "https://pharmeasy.in/doctor-consultation/landing?src=feverwatch" }
  ];
  var DASHNOTE = "This is a daily updated dashboard where we compute a monsoon-risk score (0-100) based on multiple data inputs, including weather data, Google search trends, and aggregate data from PharmEasy Labs and its Partner Affiliates.";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DATA = null, state = { cityId: null, expanded: null, leader: "overall", lbQuery: "", lbPage: 0 }, app = document.getElementById("fw-app");

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
  wireNav();  // PharmEasy hamburger menu, independent of the data layer
  window.addEventListener("popstate", onPop);

  // Instant first paint: render the designed view from the inlined per-city seed (no wait for the
  // ~850KB grid). The full grid then loads in the background to fill the other-cities leaderboard.
  var booted = false;
  function boot(j) {
    DATA = j;
    if (!state.cityId || !DATA.cities.some(function (c) { return c.id === state.cityId; })) state.cityId = pickDefaultCity();
    state.expanded = cityObj(state.cityId).blend.driver;
    if (!booted) {
      booted = true;
      document.addEventListener("click", onClick);
      var cs = document.getElementById("citysearch"); if (cs) cs.addEventListener("input", renderCityList);
    }
    renderCityList(); render(); buildTicker(); buildShareFooter();
  }
  // boot() is invoked at the very END of the IIFE - render() uses FAQ/METHOD, which are defined below.

  function pickDefaultCity() {
    if (FW.city && DATA.cities.some(function (c) { return c.id === FW.city; })) return FW.city;
    return DATA.cities.some(function (c) { return c.id === "bengaluru"; }) ? "bengaluru" : DATA.cities[0].id;
  }
  function useMyLocation() {
    if (!window.FeverWatchGeo) return;
    var row = document.querySelector('#citysheet [data-act="useLoc"]');
    if (row) { row.dataset.orig = row.dataset.orig || row.innerHTML; row.innerHTML = "◎ Finding your location..."; row.style.opacity = ".65"; }
    window.FeverWatchGeo.resolve(DATA.cities, { allowGPS: true }).then(function (res) {
      if (row) { row.innerHTML = row.dataset.orig; row.style.opacity = ""; }
      if (res && res.cityId && DATA.cities.some(function (c) { return c.id === res.cityId; })) {
        closeSheets(); setCity(res.cityId, true); window.scrollTo(0, 0);
      } else if (row) { row.innerHTML = "◎ Could not detect your location - pick a city below"; }
    }).catch(function () {
      if (row) { row.innerHTML = "◎ Location unavailable - pick a city below"; row.style.opacity = ""; }
    });
  }
  function maybeGeo() {
    if (FW.city || !window.FeverWatchGeo) return;  // city pages respect the URL; geo only steers the landing default
    window.FeverWatchGeo.resolve(DATA.cities).then(function (res) {
      if (res && res.cityId && res.cityId !== state.cityId && DATA.cities.some(function (c) { return c.id === res.cityId; })) {
        state.cityId = res.cityId; state.expanded = cityObj(state.cityId).blend.driver;
        try { history.replaceState(null, "", cityHref(res.cityId)); } catch (e) {}
        render();
      }
    }).catch(function () {});
  }
  function injectChrome() {
    if (document.getElementById("scrim")) return;
    var html =
      '<div class="scrim" id="scrim"></div>' +
      '<div class="sheet full" id="citysheet"><div class="sheethead"><h3>Choose your city</h3><button class="x" data-act="closeCity">✕</button></div>' +
      '<div class="sheetbody"><input class="citysearch" id="citysearch" placeholder="Type a city name" />' +
      '<div class="locrow" data-act="useLoc">◎ Use my location</div><div id="citylist"></div>' +
      '<p class="searchnote" style="margin-top:14px">Available in select cities.</p></div></div>' +
      '<div class="sheet" id="sharesheet"><div class="sheethead"><h3>Share this risk</h3><button class="x" data-act="closeShare">✕</button></div>' +
      '<div class="sheetbody" id="sharebody"></div></div>';
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    while (wrap.firstChild) document.body.appendChild(wrap.firstChild);
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
    state.expanded = cityObj(id).blend.driver;
    if (push) { try { history.pushState(null, "", cityHref(id)); } catch (e) {} }
    render();
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
    if (!burger || !topnav) return;
    function closeDrops() {
      Array.prototype.forEach.call(document.querySelectorAll(".pe-nav-item.open"), function (o) {
        o.classList.remove("open");
        var b = o.querySelector(".pe-nav-btn"); if (b) b.setAttribute("aria-expanded", "false");
      });
    }
    function closePanel() { topnav.classList.remove("open"); burger.setAttribute("aria-expanded", "false"); }
    burger.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = topnav.classList.toggle("open");
      burger.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) closeDrops();
    });
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

  function render() {
    var c = cityObj(state.cityId), b = c.blend;
    app.innerHTML =
      '<div class="hero"><h1>Live monsoon-fever risk for ' + esc(c.name) + ', in <em>one score</em>.</h1>' +
      '<p>Dengue, malaria, chikungunya and typhoid, blended from breeding weather, Google search interest and PharmEasy lab signals.</p></div>' +
      '<div class="searchwrap"><div class="searchfield" data-act="openCity"><span class="ico">🔎</span> Search your city</div>' +
      '<p class="searchnote">Available in select cities.</p></div>' +
      '<div class="wrap">' +
        '<div class="citymeta"><div><h2>' + c.name + '</h2><div class="date">This week, updated ' + fmtDate(DATA.generated_at) + '</div></div>' +
        '<button class="changecity" data-act="openCity">Change</button></div>' +
        riskCard(c, b) + methodologyCard() + breakdownCard(c) + actionsCard(c) + leaderboardCard(c) +
        '<section id="s-trend" class="fwtrend-host"></section>' + faqCard() + readsCard() +
      '</div>';
    wireLeaderboard();
    mountTrend(c);
    updateShareFooter();
    document.body.classList.add("fw-hydrated");
  }

  // The "this monsoon vs last year" widget owns its own subtree (tabs/tooltip/collapse); recompute it
  // from the grid on every render so it tracks the selected city, like the FAQ (faq.js).
  function mountTrend(c) {
    if (window.FeverWatchTrend) window.FeverWatchTrend.mount(document.getElementById("s-trend"), c, DATA, { mode: "mobile" });
  }

  function riskCard(c, b) {
    var col = RISK[b.band], drv = diseaseObj(b.driver), drvCell = cellFor(c.id, b.driver);
    var pills = orderedDiseases(c).map(function (d) {
      var cell = cellFor(c.id, d.id);
      return '<span class="dpill"><span class="dot" style="background:' + RISK[cell.band] + '"></span>' + d.emoji + ' ' + d.label + ' <b>' + cell.score + '</b></span>';
    }).join("");
    return '<div class="card"><div class="rtop">' + gauge(b.score, col, 116) +
      '<div class="rhead"><div class="ov">Overall monsoon-fever risk</div>' +
      '<div class="bandlbl" style="color:' + col + '">' + beacon(b.band) + b.band + '</div></div></div>' +
      '<div class="driverrow"><span class="driver" style="background:' + RISK_SOFT[drvCell.band] + ';color:' + RISK[drvCell.band] + '">Top concern: ' + drv.emoji + ' ' + drv.label + ' ' + drvCell.band + ' (' + b.driver_score + ')</span></div>' +
      '<div class="pills">' + pills + '</div>' +
      '<div class="rfoot"><span class="note">Scores modeled from breeding weather, Google search interest and PharmEasy lab signals.</span>' +
      '<button class="sharebtn" data-act="openShare">⤴ Share</button></div></div>';
  }

  function breakdownCard(c) {
    var accs = orderedDiseases(c).map(function (d) {
      var cell = cellFor(c.id, d.id), open = state.expanded === d.id, s = cell.signals, w = cell.weights;
      var body = '<div class="accbody">' + sig(SIG.weather, s.weather, w.weather) + sig(SIG.trends, s.trends, w.trends) +
        sig(SIG.positivity, s.positivity, w.positivity) + '<p class="accnote">' + cell.note + '</p></div>';
      return '<div class="acc' + (open ? ' open' : '') + '"><button class="acchead" data-act="expand" data-id="' + d.id + '">' +
        '<span class="emoji">' + d.emoji + '</span><span class="name">' + d.label + '</span>' +
        '<span class="dot" style="background:' + RISK[cell.band] + '"></span><span class="sc" style="color:' + RISK[cell.band] + '">' + cell.score + '</span>' +
        '<span class="chev">▾</span></button>' + body + '</div>';
    }).join("");
    return '<div class="card"><h2 class="sectiontitle">Why this score?</h2><p class="sectionsub">Tap a disease to see its three signals.</p>' + accs + '</div>';
  }

  function sig(meta, value, weight) {
    var absent = value == null;
    return '<div class="sig"><div class="row"><span class="lbl">' + meta.label + '</span>' +
      '<span class="v" style="color:' + meta.c + '">' + (absent ? "no data" : value + " (" + weight + "%)") + '</span></div>' +
      '<div class="tag">' + (absent ? "No confirmed-case data here yet." : meta.tag) + '</div>' +
      '<div class="track"><div class="fill" style="width:' + (absent ? 0 : value) + '%;background:' + meta.c + '"></div></div></div>';
  }

  function actionsCard(c) {
    var cards = ACTIONS.map(function (a) {
      return '<a class="actcard" href="' + a.href + '"><span class="ic">' + a.ic + '</span><span class="tx"><b>' + a.t + '</b><span>' + a.s + '</span></span><span class="go">›</span></a>';
    }).join("");
    return '<div class="card"><h2 class="sectiontitle">So, what should I do?</h2><p class="sectionsub">Quick, practical follow-through for ' + c.name + '.</p>' + cards +
      '<a class="ctabig" style="background:var(--pe-green)" href="https://pharmeasy.in/diag-pwa/content/Fever_LP?src=feverwatch">Book a fever panel test</a></div>';
  }

  function methodologyCard() {
    return '<div class="card"><h2 class="sectiontitle" style="margin-bottom:6px">How we calculate this</h2>' +
      '<button class="methhead" data-act="method"><span class="methsub">A transparent, decomposable formula, not a black box.</span><span class="methtog" id="methtog">Show ▾</span></button>' +
      '<div class="methbody" id="methbody">' + METHOD + '<p class="dashnote">' + DASHNOTE + '</p></div></div>';
  }

  function leaderboardCard(c) {
    var isOverall = state.leader === "overall";
    var label = isOverall ? "Overall" : diseaseObj(state.leader).label;
    var chips = '<button class="chip' + (isOverall ? ' on' : '') + '" data-act="leader" data-id="overall">📊 Overall</button>' +
      DATA.diseases.map(function (d) { return '<button class="chip' + (d.id === state.leader ? ' on' : '') + '" data-act="leader" data-id="' + d.id + '">' + d.emoji + ' ' + d.label + '</button>'; }).join("");
    return '<div class="card" id="others"><h2 class="sectiontitle">🏆 What is happening in other cities?</h2><p class="sectionsub">' + label + ' risk leaderboard this week.</p>' +
      '<div class="chips">' + chips + '</div>' +
      '<input class="citysearch" id="lbsearch" placeholder="Search a city" value="' + esc(state.lbQuery) + '" autocomplete="off" style="margin-bottom:10px" />' +
      '<div id="lbcontainer">' + leaderboardInner(c) + '</div></div>';
  }

  function leaderboardInner(c) {
    var PER = 10;
    var ranked = DATA.cities.map(function (ci) { var lr = leaderRow(ci); return { id: ci.id, name: ci.name, score: lr.score, band: lr.band }; }).sort(function (a, b) { return b.score - a.score; });
    ranked.forEach(function (r, i) { r.rank = i + 1; });
    var me = null, mk; for (mk = 0; mk < ranked.length; mk++) { if (ranked[mk].id === state.cityId) { me = ranked[mk]; break; } }
    var q = (state.lbQuery || "").toLowerCase();
    var filtered = q ? ranked.filter(function (r) { return r.name.toLowerCase().indexOf(q) >= 0; }) : ranked;
    var pages = Math.max(1, Math.ceil(filtered.length / PER));
    var page = Math.min(state.lbPage || 0, pages - 1);
    var slice = filtered.slice(page * PER, page * PER + PER);
    if (!slice.length) return '<p class="lbmore">No city matches "' + esc(state.lbQuery) + '".</p>';
    function rowFor(r, pin) {
      return '<div class="lbrow' + (r.id === state.cityId ? ' you' : '') + (pin ? ' lb-pinned' : '') + '"><span class="rk">' + r.rank + '</span>' +
        '<a class="nm lbcity" href="' + cityHref(r.id) + '">' + r.name + '</a>' +
        '<span class="lbbar"><i style="width:' + r.score + '%;background:' + RISK[r.band] + '"></i></span><span class="v" style="color:' + RISK[r.band] + '">' + r.score + '</span></div>';
    }
    var rowHtml = slice.map(function (r) { return rowFor(r, false); }).join("");
    // Pin the user's own city as a last row whenever it is off this page (and not while searching), so
    // they always see their rank vs others without paging deep. Auto-suppressed once paging reaches it.
    var onPage = slice.some(function (r) { return r.id === state.cityId; });
    var pinned = (me && !onPage && !q) ? rowFor(me, true) : "";
    return rowHtml + pinned + pager(page, pages, filtered.length);
  }

  function pager(page, pages, total) {
    if (pages <= 1) return '<p class="lbmore">Showing all ' + total + ' cities.</p>';
    return '<div class="lbpager">' +
      '<button class="pgbtn" data-act="lbpage" data-page="' + (page - 1) + '"' + (page === 0 ? ' disabled' : '') + '>‹ Prev</button>' +
      '<span class="pginfo">Page ' + (page + 1) + ' of ' + pages + '</span>' +
      '<button class="pgbtn" data-act="lbpage" data-page="' + (page + 1) + '"' + (page >= pages - 1 ? ' disabled' : '') + '>Next ›</button></div>';
  }

  function renderLeaderboard() { var el = document.getElementById("lbcontainer"); if (el) el.innerHTML = leaderboardInner(cityObj(state.cityId)); }
  function wireLeaderboard() { var s = document.getElementById("lbsearch"); if (s) s.oninput = function () { state.lbQuery = s.value; state.lbPage = 0; renderLeaderboard(); }; }

  function readsCard() {
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
    return '<div class="card" id="reads"><h2 class="sectiontitle">Further reading from PharmEasy</h2>' +
      '<div class="related-grid">' + cols + '</div></div>';
  }

  function faqCard() {
    var faq = (window.FeverWatchFaq && DATA) ? FeverWatchFaq.forCity(cityObj(state.cityId), DATA, FW.seed) : FAQ;
    var items = faq.map(function (f, i) {
      return '<details class="faqitem"' + (i < 2 ? ' open' : '') + '><summary><span class="faq-q">' + f[0] + '</span><span class="faq-chev" aria-hidden="true"></span></summary><div class="faq-a">' + f[1] + '</div></details>';
    }).join("");
    return '<section id="faq" class="faqsec"><h2 class="sectiontitle">Common questions</h2><div class="faq-list">' + items + '</div></section>';
  }

  function gauge(score, color, size) {
    var sw = 11, cx = size / 2, r = (size - sw) / 2 - 1, C = 2 * Math.PI * r, arc = 0.75;
    var track = (arc * C).toFixed(1), gap = (C - arc * C).toFixed(1), prog = (Math.max(0, Math.min(100, score)) / 100 * arc * C).toFixed(1);
    return '<div class="gaugewrap" style="width:' + size + 'px;height:' + size + 'px">' +
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="#e9eef5" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gap + '" transform="rotate(135 ' + cx + ' ' + cx + ')"/>' +
      '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + prog + ' ' + (C * 2).toFixed(1) + '" transform="rotate(135 ' + cx + ' ' + cx + ')" style="transition:stroke-dasharray 1s ease"/>' +
      '</svg><div class="num"><b style="color:' + color + '">' + score + '</b><span>/ 100</span></div></div>';
  }

  function renderCityList() {
    var q = (document.getElementById("citysearch").value || "").toLowerCase();
    document.getElementById("citylist").innerHTML = DATA.cities.filter(function (c) { return c.name.toLowerCase().indexOf(q) >= 0; }).map(function (c) {
      var b = c.blend;
      return '<button class="cityopt" data-act="pickCity" data-id="' + c.id + '"><span>📍 ' + c.name + ' <small>' + c.state + '</small></span>' +
        '<span class="sb" style="background:' + RISK_SOFT[b.band] + ';color:' + RISK[b.band] + '">' + b.band + ' ' + b.score + '</span></button>';
    }).join("");
  }

  function shareUrl() { return (FW.canonicalBase || (location.origin + CITY_ROOT)) + state.cityId + "/"; }
  function shareText(c) { var b = c.blend, drv = diseaseObj(b.driver); return "This Week: " + b.band + " monsoon-fever risk in " + c.name + ", " + b.score + "/100 (top concern: " + drv.label + "), modelled from breeding weather, Google search interest and PharmEasy lab signals. Know more here: " + shareUrl(); }
  function renderShare() {
    // preview = the CI-baked share card itself (assets/img/share/{city}.jpg), so what the
    // user sees is byte-identical to what gets shared - no re-drawn mock to drift.
    var c = cityObj(state.cityId);
    var src = window.FeverWatchShare ? window.FeverWatchShare.imageUrl(state.cityId, DATA.generated_at) : "";
    document.getElementById("sharebody").innerHTML =
      '<img class="sharecard-img" src="' + src + '" alt="' + esc(c.name) + ' monsoon fever risk score card">' +
      '<div class="sharetext">' + shareText(c) + '</div>' +
      '<div class="sharebtns"><button data-act="shareWA" style="background:#25D366">WhatsApp</button><button data-act="shareDL" style="background:#111">Save image</button><button data-act="shareCopy" style="background:var(--pe-blue)">Copy link</button></div>' +
      '<p class="sharehint" style="font-size:11.5px;color:var(--pe-muted-2);margin:11px 2px 0;line-height:1.5">On some Android phones WhatsApp attaches only the image and drops the caption. Tap Copy link to send the text and link too.</p>';
  }

  // Live ticker under the header (clickable cities, same component as desktop).
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
  // Floating awareness + share CTA bar (ticker now lives under the header).
  function buildShareFooter() {
    if (document.getElementById("fwfoot") || !DATA) return;
    var el = document.createElement("div");
    el.className = "fw-foot"; el.id = "fwfoot";
    el.innerHTML = '<div class="fw-foot-cta"><div class="fw-foot-text">' +
      '<div class="fw-foot-title">1 in 3 fevers in India isn\'t just a fever</div>' +
      '<div class="fw-foot-sub" id="fwfootsub"></div></div>' +
      '<button class="fw-foot-share" data-act="openShare">⤴ Share</button></div>';
    document.body.appendChild(el);
    updateShareFooter();
  }
  function updateShareFooter() {
    var s = document.getElementById("fwfootsub");
    if (s && DATA) s.textContent = "Spread awareness. Share " + cityObj(state.cityId).name + "'s score.";
  }

  function openSheet(id) { document.getElementById("scrim").classList.add("open"); document.getElementById(id).classList.add("open"); }
  function closeSheets() { document.getElementById("scrim").classList.remove("open"); document.getElementById("citysheet").classList.remove("open"); document.getElementById("sharesheet").classList.remove("open"); }

  function onClick(e) {
    var el = e.target.closest ? e.target.closest("[data-act]") : null; if (!el) return;
    var a = el.getAttribute("data-act");
    if (a === "openCity") { renderCityList(); openSheet("citysheet"); }
    else if (a === "closeCity" || a === "closeShare") closeSheets();
    else if (a === "pickCity" || a === "pickrow") { if (e.preventDefault) e.preventDefault(); closeSheets(); setCity(el.getAttribute("data-id"), true); window.scrollTo(0, 0); }
    else if (a === "useLoc") useMyLocation();
    else if (a === "expand") { var id = el.getAttribute("data-id"); state.expanded = state.expanded === id ? null : id; render(); }
    else if (a === "leader") { state.leader = el.getAttribute("data-id"); state.lbPage = 0; render(); document.getElementById("others").scrollIntoView({ behavior: "smooth" }); }
    else if (a === "lbpage") { state.lbPage = parseInt(el.getAttribute("data-page"), 10) || 0; renderLeaderboard(); }
    else if (a === "method") { var bdy = document.getElementById("methbody"); bdy.classList.toggle("open"); document.getElementById("methtog").textContent = bdy.classList.contains("open") ? "Hide ▴" : "Show ▾"; }
    else if (a === "openShare") { renderShare(); openSheet("sharesheet"); }
    else if (a === "shareWA") doShare("wa");
    else if (a === "shareDL") doShare("dl");
    else if (a === "shareCopy") doShare("copy");
  }

  function shareCardData() {
    var c = cityObj(state.cityId);
    return { text: shareText(c), url: shareUrl() };
  }
  function doShare(kind) {
    if (!window.FeverWatchShare) return;
    var d = shareCardData(), fn = "fever-watch-" + state.cityId + ".jpg";
    if (kind === "copy") { window.FeverWatchShare.copyLink(d.url); return; }
    window.FeverWatchShare.loadCard(state.cityId, DATA.generated_at).then(function (blob) {
      if (kind === "wa") window.FeverWatchShare.nativeShare(blob, d.text, "", fn);  // URL is already in d.text
      else window.FeverWatchShare.download(blob, fn);
    }).catch(function () {
      // image unavailable (e.g. brand-new city before the next bake): degrade gracefully
      if (kind === "wa") window.FeverWatchShare.whatsapp(d.text, "");
      else window.open(window.FeverWatchShare.imageUrl(state.cityId, DATA.generated_at), "_blank");
    });
  }
  document.getElementById("scrim").addEventListener("click", closeSheets);

  var FAQ = [
    ["What is Fever Watch?", "Fever Watch is a daily risk indicator for India's top monsoon fevers (dengue, malaria, chikungunya and typhoid), shown as one decomposable score per city and disease. It blends breeding weather, public search interest and PharmEasy lab positivity."],
    ["Is this a diagnosis or medical advice?", "No. Fever Watch is a risk indicator only. It is not a diagnosis, not a count of actual cases or mosquitoes, and not a substitute for a doctor. If you feel unwell, consult a clinician."],
    ["How is the score calculated?", "It is a transparent weighted blend of three signals at different points in the illness pipeline: breeding weather (leading), search interest (coincident) and lab positivity (lagging ground truth). When lab data is present it leads the score, and the breakdown is always shown."],
    ["What does forecast-only mean?", "Where there is not enough lab data for a city and disease yet, the score is a conditions-based forecast and is capped below the HIGH band, so a forecast-only read can never show HIGH. This keeps the read honest."],
    ["How often is it updated?", "Weather is refreshed daily from NASA POWER, search interest weekly, and the lab signal daily. The score for each city is recomputed every day."],
    ["Which cities are covered?", "Fever Watch currently covers over 200 Indian cities, with more planned. Use the city search to see the read for your city."]
  ];

  var METHOD =
    '<p>Every score is a transparent weighted formula, not a black box. It is built in three layers.</p>' +
    '<h3>1. Per-disease environmental score (0 to 100)</h3>' +
    '<p>From trailing daily weather, shaped by disease family:</p><ul>' +
    '<li><b>Mosquito-borne</b> (dengue, malaria, chikungunya): a unimodal temperature response peaking near <code>29&deg;C</code> (Aedes and Anopheles breed fastest at 25 to 30&deg;C, activity falls below ~18&deg;C and above ~35&deg;C), times lagged rainfall over the past ~14 days (standing-water sites emerge 1 to 2 weeks after rain), times relative humidity (above ~60% extends mosquito lifespan). Weights ~0.45 / 0.35 / 0.20.</li>' +
    '<li><b>Waterborne</b> (typhoid): recent (7-day) plus accumulated (14-day) rainfall as a contamination and runoff proxy; temperature secondary.</li></ul>' +
    '<h3>2. Three independent signals</h3><ul>' +
    '<li><b>Breeding weather</b> (leading, ~weeks ahead): the environmental score above.</li>' +
    '<li><b>Google Search Interest</b> (coincident): symptom-search attention, smoothed; down-weighted when it spikes alone (news-driven).</li>' +
    '<li><b>PharmEasy lab signal</b> (lagging, ground truth): aggregate, de-identified test-positivity trend.</li></ul>' +
    '<h3>3. Confirmation-weighted ensemble</h3>' +
    '<p>Not a flat average. With lab data present it dominates (weights ~<code>30 / 22 / 48</code> weather / search / positivity) and agreement across all three raises confidence. Without it, a capped <code>forecast-only</code> mode (max 69, below the HIGH threshold) keeps a conditions-only read honest. The city headline is a max-dominant blend (<code>0.8 &times; the top disease + 0.2 &times; the mean of the rest</code>) with the driver disease named.</p>' +
    '<h3>Data sources</h3><ul><li>Weather: NASA POWER (NASA Langley, US public domain / CC0)</li><li>Search: Google Trends</li><li>Positivity: PharmEasy diagnostics (aggregate, de-identified)</li></ul>' +
    '<h3>Selected research</h3>' +
    '<p class="cite">Ginsberg et al. Detecting influenza epidemics using search engine query data. <i>Nature</i>, 2009.</p>' +
    '<p class="cite">Mordecai et al. Thermal biology of mosquito-borne disease. <i>Ecology Letters</i>, 2019 (peak transmission ~29&deg;C).</p>' +
    '<p class="cite">Liu-Helmersson et al. Vectorial capacity of Aedes aegypti: effects of temperature and implications for dengue. <i>PLOS ONE</i>, 2014.</p>' +
    '<p class="cite">Brady et al. Modelling adult Aedes survival at different temperatures. <i>Parasites &amp; Vectors</i>, 2013.</p>' +
    '<p class="cite">Naish et al. Climate change and dengue: a systematic review. <i>BMC Infectious Diseases</i>, 2014.</p>' +
    '<p class="cite">IDSP Weekly Outbreak Reports, MoHFW (official surveillance).</p>' +
    '<p style="margin-top:12px;color:var(--pe-muted-2)">A risk indicator, not a diagnosis or a case count.</p>';

  // All render() dependencies (FAQ, METHOD, ...) are now defined. Boot: seed first (instant first
  // paint from the inlined city data), then the full grid in the background for the leaderboard.
  if (FW.seed) { try { boot(FW.seed); } catch (e) { console.error("seed boot failed:", e); } }
  loadGrid(4).then(function (j) {
    boot(j); maybeGeo();
  }).catch(function (e) { console.error("grid load/boot failed:", e); if (!DATA) app.innerHTML = '<div class="wrap"><div class="card">Could not load data: ' + e.message + '</div></div>'; });
})();
