/* Fever Watch - "This monsoon vs last year" season-trend module (shared client widget).
   Mirrors the faq.js pattern: a self-contained, per-city component that RECOMPUTES from the loaded
   grid on every city switch (no full reload). The series is a deterministic MOCK derived from the
   city's real current scores (blend + signal sub-scores) until a real data/history.json lands
   (format: docs/lab_feed_historic_format.md). The build_site.py helpers _trend_* mirror the same
   series math + bake a static "Overall" SVG into every page for crawlers / no-JS; this module owns
   the interactive flows (tabs, tooltip, collapse, desktop small-multiples). Loaded on every page so
   both mobile.js and desktop.js can call window.FeverWatchTrend.mount(host, city, DATA, {mode}).

   IMPORTANT: the series math here (SHAPE / hashStr / lyFactor / r) is intentionally kept identical
   to src/build_site.py _trend_series(). Edit BOTH and keep them in sync. */
(function () {
  "use strict";

  // --- shared deterministic series math (keep identical to build_site.py _trend_series) ----------
  // A 22-week seasonal risk curve (1 Jun -> 30 Oct, weekly), normalised so the late-Aug peak = 1.00.
  // It shapes BOTH series: this-year is scaled so it ends at the city's real current score; last-year is
  // scaled to a fixed per-city seeded peak (see lyPeak). Compressed trough-to-peak range (June ~0.60 of
  // peak) keeps the early-season curves in a realistic 0-100 band.
  var SHAPE = [0.60, 0.63, 0.66, 0.69, 0.73, 0.77, 0.81, 0.85, 0.89, 0.92, 0.95, 0.97, 0.99, 1.00,
               0.96, 0.91, 0.86, 0.81, 0.78, 0.75, 0.73, 0.71];
  var NW = SHAPE.length;                       // 22
  var PEAK_IDX = 13;                           // late August
  var MONTHS_ROW = ["Jun", "Jul", "Aug", "Sep", "Oct"];   // equidistant HTML axis labels (not SVG text)
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function r(x) { return Math.floor((x || 0) + 0.5); }           // round-half-up (matches Python floor(x+0.5))
  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function hashStr(s) { var h = 5381, i; for (i = 0; i < s.length; i++) { h = (h * 33 + s.charCodeAt(i)) >>> 0; } return h; }
  // Last-year is a STABLE per-city, per-metric mock: a fixed seasonal peak seeded ONLY from the city id
  // (never from this year's score or the current week), so "last year peaked at X" never drifts. This
  // year's REAL score floats against it. Band 64-95 = a plausible HIGH last-monsoon peak; tuned so most
  // cities read "tracking below/around last year" (calm) with a modest "above" tail, all 3 verdicts kept.
  // (Replaced by a real data/history.json lookup later; format docs/lab_feed_historic_format.md.)
  var LY_MIN = 64, LY_MAX = 95;
  function lyPeak(cityId, metric) { return LY_MIN + hashStr(cityId + ":" + metric + ":lypeak") % (LY_MAX - LY_MIN + 1); }
  function bandOf(score) { return score >= 70 ? "HIGH" : score >= 45 ? "MODERATE" : score >= 25 ? "LOW-MODERATE" : "LOW"; }

  var RISK = { "HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F" };
  var SIGCOL = { weather: "#15ACA5", search: "#7C6CD6", labs: "#3661B0" };
  var ZONES = [[70, 100, "#E4572E"], [45, 69, "#E8923A"], [25, 44, "#C7A93C"], [0, 24, "#2FA66F"]];

  // Build one metric's two series from a single current value V (0-100) at the current week `asOf`.
  // thisYear is partial (rises along SHAPE to exactly V at asOf); lastYear is the full 22-week season,
  // scaled to the city's FIXED seeded peak so it never moves with V or the week.
  function metricSeries(cityId, metric, V, asOf) {
    var denom = SHAPE[asOf], ty = [], ly = [], w;
    for (w = 0; w <= asOf; w++) ty.push(clamp(r(V * SHAPE[w] / denom), 0, 100));
    var P = lyPeak(cityId, metric);                       // fixed last-year peak (independent of V and asOf)
    for (w = 0; w < NW; w++) ly.push(clamp(r(P * SHAPE[w]), 0, 100));
    var a = ty[asOf], b = ly[asOf];
    var delta = b > 0 ? r((a - b) / b * 100) : 0;
    var slope = asOf >= 1 ? ty[asOf] - ty[asOf - 1] : 0;
    var peak = ly[PEAK_IDX];
    return { now: V, series: ty, last: ly, delta: delta, slope: slope, peak: peak, avail: true };
  }

  // REAL last-year + this-year series from the committed archive (data/archive/trend_series.json), used
  // for the WEATHER and SEARCH tabs when DATA.archive is present. Same return shape as metricSeries so
  // everything downstream (chart, caption, tooltip) is unchanged; peak is the real last-year MAX (not a
  // seeded mock). JS-ONLY by design: the SSR (build_site.py) bakes only the Overall chart, which stays on
  // the mock, so Overall + Labs keep the deterministic mock until real lab-positivity history lands.
  function realSeries(blk, asOf) {
    var ly = blk.ly, ty = blk.ty;
    var a = ty[asOf], b = ly[asOf];
    var delta = b > 0 ? r((a - b) / b * 100) : 0;
    var slope = asOf >= 1 ? ty[asOf] - ty[asOf - 1] : 0;
    return { now: a, series: ty, last: ly, delta: delta, slope: slope, peak: Math.max.apply(null, ly), avail: true };
  }

  function meanSignal(cells, key) {
    var sum = 0, n = 0, i, v;
    for (i = 0; i < cells.length; i++) { v = cells[i].signals ? cells[i].signals[key] : null; if (v != null) { sum += v; n++; } }
    return n ? r(sum / n) : null;
  }

  // The full per-city data model the widget renders from.
  function build(city, cells, generatedAt, arch) {
    var cid = city.id, blend = city.blend;
    var ga = generatedAt || "";
    var gy = +ga.slice(0, 4) || 2026, gm = +ga.slice(5, 7) || 6, gd = +ga.slice(8, 10) || 1;
    var asOf = clamp(Math.floor((Date.UTC(gy, gm - 1, gd) - Date.UTC(gy, 5, 1)) / 604800000), 0, NW - 1);

    var weeks = [], wd, i;
    for (i = 0; i < NW; i++) { wd = new Date(Date.UTC(gy, 5, 1 + 7 * i)); weeks.push(wd.getUTCDate() + " " + MONTHS[wd.getUTCMonth()]); }

    var weatherNow = meanSignal(cells, "weather");
    var searchNow = meanSignal(cells, "trends");
    var labsNow = meanSignal(cells, "positivity");

    // Use REAL archive series for weather + search when present (both years share one normalisation);
    // else fall back to the deterministic mock. Overall + labs stay on the mock (see realSeries note).
    var wReal = arch && arch.weather && arch.weather.ly && arch.weather.ly.length === NW && arch.weather.ty && arch.weather.ty.length === asOf + 1;
    var sReal = arch && arch.search && arch.search.ly && arch.search.ly.length === NW && arch.search.ty && arch.search.ty.length === asOf + 1;
    var metrics = {
      overall: metricSeries(cid, "overall", blend.score, asOf),
      weather: wReal ? realSeries(arch.weather, asOf) : (weatherNow == null ? { avail: false } : metricSeries(cid, "weather", weatherNow, asOf)),
      search: sReal ? realSeries(arch.search, asOf) : (searchNow == null ? { avail: false } : metricSeries(cid, "search", searchNow, asOf)),
      labs: labsNow == null ? { avail: false } : metricSeries(cid, "labs", labsNow, asOf)
    };

    var ov = metrics.overall;
    var level = ov.delta <= -6 ? "below" : (ov.delta >= 6 ? "above" : "inline");
    var dir = ov.slope >= 2 ? "rising" : (ov.slope <= -2 ? "falling" : "steady");
    var vtext = level === "below" ? "Tracking below last year so far"
      : level === "above" ? "Running higher than last year"
        : "About the same as last year so far";
    var tail = "";
    if (level === "above") tail = dir === "rising" ? ", and still rising" : (dir === "falling" ? ", but easing" : "");
    else if (level === "below") tail = dir === "rising" ? ", but creeping up" : (dir === "falling" ? ", and still easing" : "");
    else tail = dir === "rising" ? ", edging up" : (dir === "falling" ? ", edging down" : "");
    var chip = (level === "inline" && Math.abs(ov.delta) < 3) ? "~0%" : (ov.delta > 0 ? "+" : (ov.delta < 0 ? "-" : "")) + Math.abs(ov.delta) + "%";

    var peakBand = bandOf(ov.peak);
    var context = "Last year peaked at " + ov.peak + " (" + peakBand + ") in late August.";

    return {
      city: city.name, cityId: cid, asOf: asOf, weeks: weeks,
      metrics: metrics, level: level, dir: dir,
      verdict: vtext + tail, chip: chip, tone: level,
      context: context, band: blend.band
    };
  }

  function forCity(city, DATA) {
    var cid = city.id;
    var cells = DATA.grid.filter(function (g) { return g.city === cid; });
    var arch = (DATA.archive && DATA.archive.cities) ? DATA.archive.cities[cid] : null;
    return build(city, cells, DATA.generated_at, arch);
  }

  // --- captions (one sentence restating the takeaway for the selected metric) --------------------
  function caption(model, metric) {
    var m = model.metrics[metric];
    if (!m || !m.avail) return "Lab positivity history is not available for " + model.city + " yet.";
    var lvl = m.delta <= -6 ? "below" : (m.delta >= 6 ? "above" : "inline");
    if (metric === "overall") return model.dir === "rising" ? "Risk is climbing as the monsoon builds."
      : model.dir === "falling" ? "Risk is easing as rainfall tapers." : "Risk is holding close to last year.";
    if (metric === "weather") return lvl === "below" ? "Breeding conditions are running below last year."
      : lvl === "above" ? "Breeding conditions are running hotter than last year." : "Breeding conditions are tracking last year.";
    if (metric === "search") return lvl === "below" ? "Public concern is below last year's level."
      : lvl === "above" ? "Public concern is above last year's level." : "Public concern is tracking last year.";
    return lvl === "below" ? "Positivity is tracking below last year."
      : lvl === "above" ? "Positivity is running above last year." : "Positivity is tracking last year closely.";
  }

  // --- chart geometry -----------------------------------------------------------------------------
  // The SVG scales to its container width (width:100%, height:auto), so the viewBox ASPECT sets the
  // rendered height: a shorter viewBox on desktop (which is much wider) keeps the chart compact there
  // while mobile stays taller. The y-axis ZOOMS to the data (top = peak + ~15%, capped 100), so the
  // curve fills the height instead of leaving an empty top; Overall and high signals (peak ~90) keep
  // the full 0-100 so the risk zones stay meaningful. Month labels live in an HTML row under the SVG.
  function f1(n) { return Math.round(n * 10) / 10; }
  function metricCol(model, metric) { return metric === "overall" ? RISK[bandOf(model.metrics.overall.now)] : SIGCOL[metric]; }
  function chartGeom(mini, mode, m) {
    var dataMax = Math.max(m.peak, m.series.length ? Math.max.apply(null, m.series) : 0);
    return {
      W: 340, PADL: mini ? 12 : 26, PADR: 12, PADT: 6, PADB: 4,
      H: mini ? 120 : (mode === "desktop" ? 92 : 150),
      yMax: Math.min(100, Math.max(45, Math.round(dataMax * 1.15)))
    };
  }
  function geomXY(g) {
    return {
      X: function (i) { return g.PADL + i / (NW - 1) * (g.W - g.PADL - g.PADR); },
      Y: function (v) { return g.PADT + (1 - clamp(v, 0, g.yMax) / g.yMax) * (g.H - g.PADT - g.PADB); }
    };
  }

  function chartSVG(model, metric, mini, mode) {
    var m = model.metrics[metric];
    if (!m || !m.avail) return "";
    var g = chartGeom(mini, mode, m), xy = geomXY(g), X = xy.X, Y = xy.Y, i;
    function lp(arr) { var d = "", k; for (k = 0; k < arr.length; k++) d += (k ? "L" : "M") + f1(X(k)) + " " + f1(Y(arr[k])); return d; }
    var col = metricCol(model, metric), baseY = Y(0);
    var zones = "";
    if (metric === "overall" && !mini) {
      for (i = 0; i < ZONES.length; i++) {
        var z = ZONES[i]; if (z[0] >= g.yMax) continue;
        var yt = Y(Math.min(z[1], g.yMax)), yb = Y(z[0]);
        zones += '<rect x="' + g.PADL + '" y="' + f1(yt) + '" width="' + (g.W - g.PADL - g.PADR) + '" height="' + f1(yb - yt) + '" fill="' + z[2] + '" opacity="0.06"/>';
      }
    }
    // Signal tabs have no risk zones, so they'd read as plain white next to the tinted Overall. Give them
    // a soft backdrop glow in the signal's own colour (teal/purple/blue) so every tab feels consistent.
    var bg = "";
    if (metric !== "overall" && !mini) {
      var gid = "fwtg-" + metric;
      bg = '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">'
        + '<stop offset="0" stop-color="' + col + '" stop-opacity="0.015"/>'
        + '<stop offset="1" stop-color="' + col + '" stop-opacity="0.12"/></linearGradient></defs>'
        + '<rect x="' + g.PADL + '" y="' + f1(g.PADT) + '" width="' + (g.W - g.PADL - g.PADR) + '" height="' + f1(g.H - g.PADT - g.PADB) + '" fill="url(#' + gid + ')"/>';
    }
    // last-year soft gray band (area to baseline + edge line)
    var lyLine = lp(m.last);
    var area = "M" + f1(X(0)) + " " + f1(baseY) + lyLine.replace(/^M/, "L") + "L" + f1(X(NW - 1)) + " " + f1(baseY) + "Z";
    var lyArea = '<path d="' + area + '" fill="#9fb0c4" opacity="0.16"/>';
    var lyStroke = '<path d="' + lyLine + '" fill="none" stroke="#aab6c6" stroke-width="' + (mini ? 1.3 : 1.6) + '" stroke-linejoin="round"/>';
    // this-year bold line + you-are-here dot
    var ty = m.series, tyLine = ty.length > 1 ? '<path d="' + lp(ty) + '" fill="none" stroke="' + col + '" stroke-width="' + (mini ? 2 : 2.6) + '" stroke-linecap="round" stroke-linejoin="round"/>' : "";
    var dot = '<circle cx="' + f1(X(model.asOf)) + '" cy="' + f1(Y(ty[ty.length - 1])) + '" r="' + (mini ? 3 : 4.2) + '" fill="' + col + '" stroke="#fff" stroke-width="' + (mini ? 1.5 : 2.2) + '"/>';
    // Y-axis: 0 / mid / top ticks (the top zooms with the data) in the left gutter + faint gridlines, so
    // the vertical scale is readable. SVG font scales with width, so size it per mode. Skipped on the mini
    // sparklines. Mirrored byte-for-feel in build_site.py _trend_chart_static.
    var fs = mode === "desktop" ? 6.5 : 9.5, yaxis = "", labels = "";
    if (!mini) {
      var ticks = [0, Math.round(g.yMax / 2), g.yMax], ti;
      for (ti = 0; ti < ticks.length; ti++) {
        var tv = ticks[ti], yv = Y(tv);
        if (tv > 0) yaxis += '<line x1="' + g.PADL + '" y1="' + f1(yv) + '" x2="' + (g.W - g.PADR) + '" y2="' + f1(yv) + '" stroke="#eef1f5" stroke-width="1"/>';
        yaxis += '<text x="' + (g.PADL - 5) + '" y="' + f1(yv + fs * 0.35) + '" text-anchor="end" font-size="' + fs + '" font-weight="600" fill="#9aa6b1">' + tv + '</text>';
      }
      // Spaced data labels: the you-are-here value (this year, in colour) + a few last-year reference points.
      var nv = ty[ty.length - 1];
      labels += '<text x="' + f1(X(model.asOf)) + '" y="' + f1(Math.max(fs + 2, Y(nv) - 7)) + '" text-anchor="middle" font-size="' + (fs + 0.5) + '" font-weight="800" fill="' + col + '">' + nv + '</text>';
      var lbi = [6, 13, 19], li2;
      for (li2 = 0; li2 < lbi.length; li2++) {
        var lx = lbi[li2]; if (Math.abs(lx - model.asOf) < 2) continue;
        var lv = m.last[lx];
        labels += '<text x="' + f1(X(lx)) + '" y="' + f1(Math.max(fs, Y(lv) - 5)) + '" text-anchor="middle" font-size="' + (fs - 1) + '" font-weight="600" fill="#8995a3">' + lv + '</text>';
      }
    }
    // Month labels are HTML (.fwtrend-months); the SVG carries only the baseline axis rule.
    var axis = mini ? "" : '<line x1="' + g.PADL + '" y1="' + f1(baseY) + '" x2="' + (g.W - g.PADR) + '" y2="' + f1(baseY) + '" stroke="#edf0f5" stroke-width="1"/>';
    var hit = mini ? "" : '<rect class="fwtrend-hit" x="' + g.PADL + '" y="' + g.PADT + '" width="' + (g.W - g.PADL - g.PADR) + '" height="' + (g.H - g.PADT - g.PADB) + '" fill="transparent"/>';
    return '<svg viewBox="0 0 ' + g.W + ' ' + g.H + '" class="fwtrend-svg' + (mini ? " mini" : "") + '" role="img" aria-label="' + esc(metric) + ' this year versus last year">'
      + zones + bg + yaxis + lyArea + lyStroke + tyLine + dot + labels + axis + hit + '</svg>';
  }

  // --- HTML render ------------------------------------------------------------------------------
  var TABS = [["overall", "Overall"], ["weather", "Weather"], ["search", "Searches"], ["labs", "Labs"]];
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]; }); }

  function tabsHtml(model, metric) {
    return TABS.map(function (t) {
      var avail = model.metrics[t[0]].avail, on = t[0] === metric;
      return '<button class="fwtrend-tab' + (on ? " on" : "") + (avail ? "" : " soon") + '" data-tact="metric" data-metric="' + t[0] + '"'
        + (on ? ' aria-current="true"' : "") + '>' + t[1] + (avail ? "" : ' <i>soon</i>') + '</button>';
    }).join("");
  }

  function soonHtml(model) {
    return '<div class="fwtrend-soon"><span class="i">🧪</span><b>Lab trend coming soon</b>'
      + '<p>We will chart last year\'s lab positivity for ' + esc(model.city) + ' here once PharmEasy historic lab data is available.</p></div>';
  }

  function smallsHtml(model, metric, mode) {
    var keys = ["weather", "search", "labs"];
    var cells = keys.map(function (k) {
      var m = model.metrics[k], on = k === metric, lbl = k === "search" ? "Searches" : (k === "labs" ? "Labs" : "Weather");
      var inner = (m && m.avail) ? chartSVG(model, k, true, mode)
        : '<div class="fwtrend-smini-soon">soon</div>';
      var tag = (m && m.avail) ? '<b style="color:' + SIGCOL[k] + '">' + m.now + '</b>' : "";
      return '<button class="fwtrend-smini' + (on ? " on" : "") + '" data-tact="small" data-metric="' + k + '">'
        + '<span class="t">' + lbl + ' ' + tag + '</span>' + inner + '</button>';
    }).join("");
    return '<div class="fwtrend-smalls" aria-hidden="true"><div class="fwtrend-smalls-h">Signals at a glance</div><div class="fwtrend-smalls-row">' + cells + '</div></div>';
  }

  function renderCard(model, st) {
    var metric = model.metrics[st.metric].avail ? st.metric : "overall";
    var col = metricCol(model, metric);
    // Trend-line icon (up for "above", down for "below", flat for "inline"), white on the tone circle.
    var _ti = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">';
    var toneIcon = model.tone === "below" ? (_ti + '<path d="M4 8l5 5 3-3 8 8"/><path d="M20 14v4h-4"/></svg>')
      : model.tone === "above" ? (_ti + '<path d="M4 16l5-5 3 3 8-8"/><path d="M20 10V6h-4"/></svg>')
      : (_ti + '<path d="M5 12h14"/></svg>');
    var phrase = model.tone === "above" ? "higher than last year"
      : model.tone === "below" ? "lower than last year" : "about the same as last year";
    var avail = model.metrics[metric].avail;
    st.geo = avail ? chartGeom(false, st.mode, model.metrics[metric]) : null;  // for the tooltip's coords
    var title = "This monsoon vs last in " + esc(model.city);
    var toggle = '<button class="fwtrend-toggle" data-tact="toggle" aria-expanded="' + (st.expanded ? "true" : "false") + '">'
      + '<span class="t">' + (st.expanded ? "Hide" : "Show") + '</span><span class="chev" aria-hidden="true"></span></button>';
    var monthsRow = avail ? '<div class="fwtrend-months">' + MONTHS_ROW.map(function (mn) { return '<span>' + mn + '</span>'; }).join("") + '</div>' : "";
    var body =
      '<div class="fwtrend-tabs" role="tablist">' + tabsHtml(model, metric) + '</div>'
      + '<div class="fwtrend-chartwrap">'
      + (avail ? chartSVG(model, metric, false, st.mode) : soonHtml(model))
      + '<div class="fwtrend-tip" hidden></div></div>'
      + monthsRow
      + '<p class="fwtrend-axiscap">Vertical scale starts at 0; higher means greater risk.</p>'
      + '<div class="fwtrend-legend"><span><i class="ly"></i>Last year</span>'
      + '<span><i class="ty" style="background:' + col + '"></i>This year</span>'
      + '<span class="here"><i class="dot" style="background:' + col + '"></i>You are here</span></div>'
      + '<p class="fwtrend-caption">' + esc(caption(model, metric)) + '</p>'
      + (st.mode === "desktop" ? smallsHtml(model, metric, st.mode) : "")
      + '<p class="fwtrend-sources">Sources: NOAA CPC, NASA POWER, Google Trends, PharmEasy labs. A risk indicator, not a case count.</p>';
    var lead =
      '<div class="fwtrend-pill ' + model.tone + '"><span class="fwtrend-vicon">' + toneIcon + '</span>'
      + '<b>' + esc(model.chip) + '</b> ' + phrase + '</div>'
      + '<p class="fwtrend-context">' + esc(model.context) + '</p>';
    if (st.mode === "desktop") {
      // Desktop: title + Hide toggle INSIDE the card (like mobile), so the section title rides with the
      // card; the desktop small-multiples still live in the body (smallsHtml, gated on st.mode above).
      return '<div class="card fwtrend' + (st.expanded ? " open" : "") + '" data-metric="' + metric + '">'
        + '<div class="fwtrend-head"><div>'
        + '<h2 class="fwtrend-title">' + title + '</h2></div>' + toggle + '</div>'
        + lead + '<div class="fwtrend-body">' + body + '</div></div>';
    }
    // Mobile: keep the title inside the card, like the other mobile cards.
    return '<div class="card fwtrend' + (st.expanded ? " open" : "") + '" data-metric="' + metric + '">'
      + '<div class="fwtrend-head"><div>'
      + '<h2 class="fwtrend-title">' + title + '</h2></div>' + toggle + '</div>'
      + lead + '<div class="fwtrend-body">' + body + '</div></div>';
  }

  // --- tooltip ----------------------------------------------------------------------------------
  function wireTip(host, getState) {
    function hide() { var tip = host.querySelector(".fwtrend-tip"); if (tip) tip.hidden = true; }
    function at(e) {
      var st = getState(), model = st.model, metric = model.metrics[st.metric].avail ? st.metric : "overall";
      if (!model.metrics[metric].avail || !st.geo) return hide();
      var g = st.geo, xy = geomXY(g), X = xy.X, Y = xy.Y;
      var svg = host.querySelector(".fwtrend-chartwrap .fwtrend-svg"), wrap = host.querySelector(".fwtrend-chartwrap"), tip = host.querySelector(".fwtrend-tip");
      if (!svg || !wrap || !tip) return;
      var rect = svg.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom + 2) { hide(); return; }
      var stepPx = (g.W - g.PADL - g.PADR) / (NW - 1) * (rect.width / g.W);
      var i = clamp(Math.round((e.clientX - rect.left - g.PADL * rect.width / g.W) / stepPx), 0, NW - 1);
      var m = model.metrics[metric], ly = m.last[i], tyHas = i <= model.asOf, ty = tyHas ? m.series[i] : null;
      var col = metricCol(model, metric);
      var wrapRect = wrap.getBoundingClientRect();
      var xPx = X(i) * (rect.width / g.W) + (rect.left - wrapRect.left);
      var yRef = tyHas ? Y(ty) : Y(ly);
      var yPx = yRef * (rect.height / g.H) + (rect.top - wrapRect.top);
      tip.innerHTML = '<b>Week of ' + esc(model.weeks[i]) + '</b>'
        + '<span><i style="background:' + col + '"></i>This year ' + (tyHas ? ty : "n/a") + '</span>'
        + '<span><i style="background:#aab6c6"></i>Last year ' + ly + '</span>';
      tip.style.left = clamp(xPx, 38, wrapRect.width - 38) + "px";
      tip.style.top = Math.max(2, yPx - 10) + "px";
      tip.hidden = false;
    }
    host.addEventListener("pointermove", at);
    host.addEventListener("pointerdown", at);
    host.addEventListener("pointerleave", hide);
    host.addEventListener("mouseleave", hide);
  }

  // --- mount ------------------------------------------------------------------------------------
  function mount(host, city, DATA, opts) {
    if (!host || !window || !DATA) return;
    var st = { metric: "overall", expanded: true, mode: (opts && opts.mode) || "mobile", model: forCity(city, DATA) };
    function paint() { host.innerHTML = renderCard(st.model, st); }
    paint();
    if (!host._fwTrendWired) {
      host._fwTrendWired = true;
      host.addEventListener("click", function (e) {
        var t = e.target.closest ? e.target.closest("[data-tact]") : null; if (!t) return;
        var act = t.getAttribute("data-tact");
        if (act === "metric" || act === "small") { if (!st.model.metrics[t.getAttribute("data-metric")].avail) return; st.metric = t.getAttribute("data-metric"); if (act === "metric") st.expanded = true; paint(); }
        else if (act === "toggle") { st.expanded = !st.expanded; paint(); }
      });
      wireTip(host, function () { return st; });
    }
    host._fwTrendState = st;  // expose for re-mount on city switch
    return st;
  }

  window.FeverWatchTrend = { build: build, forCity: forCity, mount: mount, caption: caption };
})();
