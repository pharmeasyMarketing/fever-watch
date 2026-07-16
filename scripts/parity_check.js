// SSR <-> JS above-the-fold parity harness.
// Runs the REAL assets/js/{mobile,desktop}.js inside a minimal DOM stub against the same per-page seed
// the SSG inlines, captures what render() assigns to #fw-app, and diffs it against the server-rendered
// .fw-pre-m / .fw-pre-d region from the built page. Any divergence BEFORE the first JS-only section = a
// CLS risk. Every fixture must report PARITY OK or the build is not byte-stable.
//
// Fixtures: the city HUB (gulbarga) always; plus a DISEASE child (gulbarga/dengue) when it was built
// (FW_DISEASE_PAGES_ENABLED). Build the disease pages first for the disease fixtures:
//   FW_DISEASE_PAGES=1 SITE_ENV=production python src/build_site.py   (or flip the flag), then run this.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
let failed = false;

function loadPage(rel) {
  const p = path.join(ROOT, "dist", "fever-watch", rel);
  return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : null;
}

// Run one flow file under a fresh minimal DOM stub against a page's inlined seed; return what render()
// painted into #fw-app. locPath is the page's location.pathname (drives CITY_ROOT / cityFromPath).
function runFlow(jsRel, pageHtml, locPath) {
  const m = pageHtml.match(/window\.FW = (\{.*?\});<\/script>/s);
  if (!m) { console.error("could not find window.FW seed in page"); process.exit(2); }
  const FW = JSON.parse(m[1]);
  let appHTML = "";
  function fakeEl(id) {
    return {
      id, dataset: {}, style: {}, classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
      set innerHTML(v) { if (id === "fw-app") appHTML = v; }, get innerHTML() { return ""; },
      addEventListener() {}, appendChild() {}, removeChild() {}, querySelector() { return null; },
      querySelectorAll() { return []; }, setAttribute() {}, getAttribute() { return null; },
      scrollIntoView() {}, parentNode: null, value: "",
      getBoundingClientRect() { return { top: 9999, bottom: 9999, left: 0, right: 0, height: 0, width: 0 }; },
    };
  }
  const els = {};
  function getEl(id) { return (els[id] = els[id] || fakeEl(id)); }
  global.window = { FW, addEventListener() {}, requestIdleCallback: null, innerHeight: 800, scrollY: 0, pageYOffset: 0 };
  global.document = {
    getElementById: getEl,
    createElement: () => fakeEl("_new"),
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    body: { classList: { add() {}, remove() {} }, appendChild() {} },
    documentElement: { scrollHeight: 99999 },
  };
  global.location = { pathname: locPath, origin: "https://x", href: "https://x" + locPath };
  global.history = { pushState() {}, replaceState() {} };
  global.sessionStorage = { getItem: () => null, setItem() {} };
  global.fetch = () => Promise.reject(new Error("no fetch in harness")); // forces seed-only render
  global.Image = function () {};
  global.setTimeout = (fn) => 0;
  delete require.cache[require.resolve(path.join(ROOT, "assets", "js", jsRel))];
  require(path.join(ROOT, "assets", "js", jsRel));
  return appHTML;
}

// Compare a flow's render() output against its server-rendered pre region: the common prefix must reach
// the first JS-only section (BREAK) so the whole above-fold SSR twin is byte-identical (CLS 0 on hydrate).
function check(label, jsRel, pageHtml, locPath, preMarker, BREAK) {
  const appHTML = runFlow(jsRel, pageHtml, locPath);
  const pm = pageHtml.indexOf(preMarker);
  if (pm < 0) { console.error(label + ": could not find SSR marker " + JSON.stringify(preMarker)); process.exit(2); }
  const ssrInner = pageHtml.slice(pm + preMarker.length);
  let i = 0;
  const n = Math.min(appHTML.length, ssrInner.length);
  while (i < n && appHTML[i] === ssrInner[i]) i++;
  const jsBreakAt = appHTML.indexOf(BREAK);
  console.log("[" + label + "] common prefix length:", i, " js length:", appHTML.length, " js break at:", jsBreakAt);
  if (i >= jsBreakAt && jsBreakAt > 0) {
    console.log("[" + label + "] PARITY OK: the above-the-fold SSR twin is byte-identical; divergence begins at the first JS-only section.");
    return;
  }
  failed = true;
  console.log("[" + label + "] PARITY MISMATCH at index", i);
  console.log("--- SSR ...:", JSON.stringify(ssrInner.slice(Math.max(0, i - 60), i + 80)));
  console.log("--- JS  ...:", JSON.stringify(appHTML.slice(Math.max(0, i - 60), i + 80)));
}

// --- HUB fixtures (always) ---
const hub = loadPage(path.join("gulbarga", "index.html"));
if (!hub) { console.error("hub page not built; run build_site.py first"); process.exit(2); }
// MOBILE: SSR closes its pre after the weather card; the breakdown card is the first JS-only section.
check("mobile hub", "mobile.js", hub, "/fever-watch/gulbarga/",
  '<div class="fw-pre fw-pre-m">', '<div class="card"><h2 class="sectiontitle">Why this score?');
// DESKTOP: SSR closes its pre after s-why; the .main wrapper is the first JS-only markup.
check("desktop hub", "desktop.js", hub, "/fever-watch/gulbarga/",
  '<div class="fw-pre fw-pre-d">', '<div class="main">');

// --- DISEASE fixtures (only when the disease pages were built) ---
const dis = loadPage(path.join("gulbarga", "dengue", "index.html"));
if (dis) {
  // MOBILE disease: SSR pre closes after the disease weather card; diseaseBreakdown is the first JS-only section.
  check("mobile disease", "mobile.js", dis, "/fever-watch/gulbarga/dengue/",
    '<div class="fw-pre fw-pre-m">', '<div class="card whycard discard-why">');
  // DESKTOP disease: SSR pre closes after s-why; the .main wrapper is the first JS-only markup.
  check("desktop disease", "desktop.js", dis, "/fever-watch/gulbarga/dengue/",
    '<div class="fw-pre fw-pre-d">', '<div class="main">');
} else {
  console.log("[disease] SKIPPED: gulbarga/dengue not built (FW_DISEASE_PAGES_ENABLED off). Build with FW_DISEASE_PAGES=1 to test.");
}

process.exit(failed ? 1 : 0);
