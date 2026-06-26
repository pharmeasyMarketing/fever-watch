/* Fever Watch - "How we calculate the score" methodology widget behaviour (shared, JS-only).
 *
 * The methodology markup (METHOD_HTML in build_site.py + the byte-identical METHOD strings in mobile.js /
 * desktop.js) is static; this module adds the interactivity: the "Source" / "Our setting" popovers, the
 * signal accordions, and the with-lab / no-lab score-builder toggle that animates the dial. Ported from
 * prototypes/method-section-B-layers.html. Hooks are namespaced (data-mpop / data-mtog / data-mmode) so they
 * never collide with the page's own data-act handlers. Call FeverWatchMethod.wire(rootEl) once after the
 * methodology HTML is injected into a container (the mobile methsheet body or the desktop methbody). Safe to
 * call again; it no-ops if already wired. All markup classes are scoped under .mthd in tokens.css.
 */
(function () {
  "use strict";

  var pop, popx, poptitle, popbody, poplink, poplink2, anchor = null, wiredDoc = false;

  function ensurePopover() {
    if (pop) return;
    pop = document.createElement("div");
    pop.className = "mthd-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", "Explanation");
    pop.innerHTML =
      '<button class="mthd-popx" type="button" aria-label="Close">&times;</button>'
      + '<div class="mthd-pop-ttl"></div><div class="mthd-pop-body"></div>'
      + '<a class="mthd-pop-link" target="_blank" rel="nofollow noopener noreferrer" hidden>View source '
      + '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M19 13v6H5V5h6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>'
      + '<a class="mthd-pop-link" target="_blank" rel="nofollow noopener noreferrer" hidden>View source '
      + '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M19 13v6H5V5h6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>';
    document.body.appendChild(pop);
    popx = pop.querySelector(".mthd-popx");
    poptitle = pop.querySelector(".mthd-pop-ttl");
    popbody = pop.querySelector(".mthd-pop-body");
    var links = pop.querySelectorAll(".mthd-pop-link");
    poplink = links[0];
    poplink2 = links[1];
  }

  function placePop(el) {
    var r = el.getBoundingClientRect(), pw = pop.offsetWidth, ph = pop.offsetHeight,
        vw = window.innerWidth, vh = window.innerHeight,
        left = r.left + r.width / 2 - pw / 2, top = r.bottom + 9;
    if (left < 8) left = 8;
    if (left + pw > vw - 8) left = vw - pw - 8;
    if (top + ph > vh - 8) top = r.top - ph - 9;   // flip above if no room below
    if (top < 8) top = 8;
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  // The info icon shown in the "Published source" popover title (matches the ⓘ trigger icon).
  var INFO = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="8.2" r="1.25" fill="currentColor"/><path d="M12 11.4v5.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';

  function openPop(el) {
    ensurePopover();
    var kind = el.getAttribute("data-mpop"),                 // set | source
        title = el.getAttribute("data-title") || "",
        body = el.getAttribute("data-body") || "",
        href = el.getAttribute("data-href"),
        informed = (kind !== "source" && !!href);            // an "our setting" backed by published research
    poptitle.className = "mthd-pop-ttl " + (kind === "source" ? "source" : "set");
    poptitle.innerHTML = (kind === "source"
        ? '<span class="ic">' + INFO + '</span>Published source'
        : informed
          ? '<span class="ic"></span>Our assumption, informed by research'
          : '<span class="ic"></span>Our assumption')
      + '<span style="flex:1"></span>';
    popbody.innerHTML = "";
    var lead = document.createElement("div");
    lead.style.cssText = "font-weight:800;color:var(--pe-ink);margin:0 0 4px";
    lead.textContent = title;
    popbody.appendChild(lead);
    var p = document.createElement("div"); p.textContent = body; popbody.appendChild(p);
    if (href) { poplink.href = href; poplink.hidden = false; poplink.childNodes[0].nodeValue = (kind === "source" ? "View source " : "Read the research "); }
    else { poplink.hidden = true; }
    var href2 = el.getAttribute("data-href2");
    if (href && href2) { poplink2.href = href2; poplink2.hidden = false; poplink2.childNodes[0].nodeValue = (kind === "source" ? "View source " : "Read the research "); }
    else { poplink2.hidden = true; }
    pop.classList.add("show");
    anchor = el;
    placePop(el);
  }
  function closePop() { if (pop) pop.classList.remove("show"); anchor = null; }

  // The with-lab / no-lab dial reflects the active ledger mode (one builder per methodology block).
  function setDial(builder, mode) {
    var arc = builder.querySelector("[data-mdial-arc]"), num = builder.querySelector("[data-mdial-num]"),
        band = builder.querySelector("[data-mdial-band]"), sub = builder.querySelector("[data-mdial-sub]"),
        cap = builder.querySelector("[data-mdial-cap]"), C = 2 * Math.PI * 33;
    if (!arc) return;
    var v, col, label, subhtml;
    if (mode === "fc") {
      v = 68; col = "var(--risk-mod)"; label = "Moderate - typhoid";
      subhtml = "<b>41 + 27 = 68</b>, capped at 69. Forecast only, never red.";
      if (cap) cap.classList.add("show");
    } else {
      v = 86; col = "var(--risk-high)"; label = "High - dengue";
      subhtml = "<b>80 blended x 1.08</b> for agreement = <b>86</b>. The driver is dengue.";
      if (cap) cap.classList.remove("show");
    }
    arc.setAttribute("stroke", col);
    arc.setAttribute("stroke-dasharray", C.toFixed(1));
    arc.setAttribute("stroke-dashoffset", (C * (1 - v / 100)).toFixed(1));
    num.textContent = v; num.style.color = col;
    band.textContent = label;
    band.style.background = (mode === "fc" ? "#FFF1E0" : "#FCEBE4");
    band.style.color = (mode === "fc" ? "#B5651D" : "var(--risk-high)");
    sub.innerHTML = subhtml;
  }

  function wireDocOnce() {
    if (wiredDoc) return;
    wiredDoc = true;
    document.addEventListener("click", function (e) {
      var trg = e.target.closest ? e.target.closest("[data-mpop]") : null,
          tog = e.target.closest ? e.target.closest("[data-mtog]") : null,
          md = e.target.closest ? e.target.closest("[data-mmode]") : null;
      if (trg) { e.stopPropagation(); if (anchor === trg) { closePop(); return; } closePop(); openPop(trg); return; }
      if (pop && (e.target === popx || (e.target.closest && e.target.closest(".mthd-popx")))) { closePop(); return; }
      if (pop && e.target.closest && e.target.closest(".mthd-pop")) return;   // clicks inside stay open
      if (tog) {
        closePop();
        var item = tog.closest(".mthd-accitem"), stack = tog.closest("[data-macc]"),
            wasOpen = item.classList.contains("open");
        if (stack) stack.querySelectorAll(".mthd-accitem.open").forEach(function (n) { n.classList.remove("open"); });
        if (!wasOpen) item.classList.add("open");
        return;
      }
      if (md) {
        closePop();
        var mode = md.getAttribute("data-mmode"), builder = md.closest(".mthd-builder"),
            grp = md.closest("[data-mmodetog]");
        grp.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b === md); });
        builder.querySelectorAll("[data-mmodeview]").forEach(function (v) { v.hidden = (v.getAttribute("data-mmodeview") !== mode); });
        setDial(builder, mode);
        return;
      }
      closePop();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closePop(); return; }
      if ((e.key === "Enter" || e.key === " ") && document.activeElement && document.activeElement.matches && document.activeElement.matches("[data-mpop]")) {
        e.preventDefault();
        var el = document.activeElement;
        if (anchor === el) closePop(); else { closePop(); openPop(el); }
      }
    });
    window.addEventListener("resize", function () { if (anchor) placePop(anchor); });
    window.addEventListener("scroll", function () { if (anchor) placePop(anchor); }, true);
  }

  // Wire a methodology block (idempotent). root = the container the METHOD html was injected into.
  function wire(root) {
    if (!root || root._mthdWired) return;
    root._mthdWired = true;
    wireDocOnce();
    root.querySelectorAll(".mthd-builder").forEach(function (b) { setDial(b, "full"); });   // init dial geometry
  }

  // --- Dynamic worked examples ("see the parts add up") -----------------------------------------
  // Build example cards from REAL grid cells, mirroring src/consolidate.py exactly:
  //   confirmed: base = .30*weather + .22*search + .48*lab; spread<22 -> x1.08 (cap 100) else x0.96
  //   forecast : base = .60*weather + .40*search; capped at 69.  final = round(...) == cell.score.
  // The per-signal pieces are apportioned (largest remainder) so they SUM EXACTLY to the blended value.
  var BANDRANGE = { HIGH: "70 to 100", MODERATE: "45 to 69", "LOW-MODERATE": "25 to 44", LOW: "0 to 24" };
  function titleCase(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s; }
  function apportion(vals, total) {           // integer parts summing EXACTLY to total (largest remainder)
    var fl = vals.map(function (v) { return Math.floor(v); }),
        used = fl.reduce(function (a, b) { return a + b; }, 0),
        fr = vals.map(function (v, i) { return v - fl[i]; }),
        idx = vals.map(function (_, i) { return i; }).sort(function (a, b) { return (fr[b] - fr[a]) || (a - b); }),
        rem = total - used;
    for (var i = 0; i < rem && i < idx.length; i++) fl[idx[i]] += 1;
    return fl;
  }
  function SW(col) { return '<span class="sw" style="background:' + col + '"></span>'; }
  function exCard(cell, disease, city) {
    var s = cell.signals || {}, w = +s.weather || 0, t = +s.trends || 0, p = s.positivity,
        conf = (cell.mode === "confirmed" && p != null), rows, capped = false;
    if (conf) {
      var pw = 0.30 * w, pt = 0.22 * t, pp = 0.48 * p, blended = Math.round(pw + pt + pp),
          parts = apportion([pw, pt, pp], blended),
          agree = (Math.max(w, t, p) - Math.min(w, t, p)) < 22;
      rows = '<div class="exrow">' + SW("var(--sig-weather)") + '<span class="l">Weather ' + w + '</span><span class="c">x 0.30</span><span class="o">' + parts[0] + '</span></div>' +
        '<div class="exrow">' + SW("var(--sig-search)") + '<span class="l">Searches ' + t + '</span><span class="c">x 0.22</span><span class="o">' + parts[1] + '</span></div>' +
        '<div class="exrow">' + SW("var(--sig-lab)") + '<span class="l">Lab ' + p + '</span><span class="c">x 0.48</span><span class="o">' + parts[2] + '</span></div>' +
        '<div class="exhr"></div>' +
        '<div class="exrow">' + SW("var(--pe-muted-2)") + '<span class="l">Blended</span><span class="c">' + parts[0] + '+' + parts[1] + '+' + parts[2] + '</span><span class="o">' + blended + '</span></div>' +
        '<div class="exrow">' + SW(agree ? "var(--pe-green)" : "var(--risk-mod)") + '<span class="l">' + (agree ? "Signals agree, +8%" : "Signals diverge, -4%") + '</span><span class="c">' + blended + ' x ' + (agree ? "1.08" : "0.96") + '</span><span class="o">' + cell.score + '</span></div>';
    } else {
      var fw = 0.60 * w, ft = 0.40 * t, fblend = Math.round(fw + ft), fparts = apportion([fw, ft], fblend);
      capped = fblend > cell.score;
      rows = '<div class="exrow">' + SW("var(--sig-weather)") + '<span class="l">Weather ' + w + '</span><span class="c">x 0.60</span><span class="o">' + fparts[0] + '</span></div>' +
        '<div class="exrow">' + SW("var(--sig-search)") + '<span class="l">Searches ' + t + '</span><span class="c">x 0.40</span><span class="o">' + fparts[1] + '</span></div>' +
        '<div class="exrow">' + SW("var(--pe-line)") + '<span class="l" style="color:var(--pe-muted)">Lab none yet</span><span class="c">-</span><span class="o" style="color:var(--pe-muted-2)">0</span></div>' +
        '<div class="exhr"></div>' +
        '<div class="exrow">' + SW("var(--pe-muted-2)") + '<span class="l">Forecast blend</span><span class="c">' + fparts[0] + '+' + fparts[1] + '</span><span class="o">' + fblend + '</span></div>' +
        (capped ? '<div class="exrow">' + SW("var(--risk-mod)") + '<span class="l">Held below red</span><span class="c">cap 69</span><span class="o">' + cell.score + '</span></div>' : '');
    }
    var eq = conf ? ((BANDRANGE[cell.band] ? "= " + BANDRANGE[cell.band] + " band" : "")) : (capped ? "capped, never High" : "forecast only");
    return '<div class="mthd-ex ' + (conf ? "full" : "fc") + '">' +
      '<span class="tag">' + (conf ? "With lab - 3 signals" : "No lab - forecast only") + '</span>' +
      '<div class="mthd-exh4">' + disease + ' in ' + city + '</div>' + rows +
      '<div class="extot"><span class="big" style="color:' + cell.color + '">' + cell.score + '</span><span class="bp" style="background:' + cell.soft + ';color:' + cell.color + '">' + titleCase(cell.band || "") + '</span><span class="eq">' + eq + '</span></div>' +
    '</div>';
  }
  // picks: [{cell, disease}, ...] (1 or 2). Returns the "worked examples" block (header + exwrap of cards).
  function examplesHtml(picks, city, isDesktop) {
    if (!picks || !picks.length) return "";
    var cards = picks.map(function (pk) { return exCard(pk.cell, pk.disease, city); }).join(""),
        head = '<p class="mthd-eyebrow"' + (isDesktop ? ' style="margin-top:18px"' : '') + '>' + (picks.length > 1 ? "Two worked examples" : "Worked example") + '</p>' +
          '<p class="mthd-title" style="font-size:' + (isDesktop ? "17px" : "16px") + ';margin-bottom:' + (isDesktop ? "4px" : "10px") + '">See the parts add up</p>' +
          (isDesktop ? '<p class="mthd-lead" style="font-size:13px;margin-bottom:12px">Real scores for ' + city + (picks.length > 1 ? ", two fevers on different paths." : ".") + '</p>' : '');
    return head + '<div class="mthd-exwrap">' + cards + '</div>';
  }

  window.FeverWatchMethod = { wire: wire, examplesHtml: examplesHtml };
})();
