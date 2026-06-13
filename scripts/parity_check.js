// SSR <-> JS above-the-fold parity harness.
// Runs the REAL assets/js/{mobile,desktop}.js inside a minimal DOM stub against the same per-city seed
// the SSG inlines, captures what render() assigns to #fw-app, and diffs it against the server-rendered
// .fw-pre-m / .fw-pre-d region from the built page. Any divergence BEFORE the first JS-only section = a
// CLS risk. Both flows must report PARITY OK or the build is not byte-stable.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const page = fs.readFileSync(path.join(ROOT, "dist", "fever-watch", "gulbarga", "index.html"), "utf8");

// pull the inlined seed (window.FW = {...};) from the built page (shared by both flows)
const m = page.match(/window\.FW = (\{.*?\});<\/script>/s);
if (!m) { console.error("could not find window.FW seed"); process.exit(2); }
const FW = JSON.parse(m[1]);

// Run one flow file under a fresh minimal DOM stub against the seed; return what render() painted into
// #fw-app. The stub mirrors just enough of the DOM for the IIFE + render() + spyScroll() to execute.
function runFlow(jsRel) {
  let appHTML = "";
  function fakeEl(id) {
    return {
      id, dataset: {}, style: {}, classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
      set innerHTML(v) { if (id === "fw-app") appHTML = v; }, get innerHTML() { return ""; },
      addEventListener() {}, appendChild() {}, removeChild() {}, querySelector() { return null; },
      querySelectorAll() { return []; }, setAttribute() {}, getAttribute() { return null; },
      scrollIntoView() {}, parentNode: null, value: "",
      // desktop.js spyScroll() reads getBoundingClientRect() on each section; mobile.js never calls it.
      getBoundingClientRect() { return { top: 9999, bottom: 9999, left: 0, right: 0, height: 0, width: 0 }; },
    };
  }
  const els = {};
  function getEl(id) { return (els[id] = els[id] || fakeEl(id)); }
  // Fresh global sandbox per run so the two IIFEs don't see each other's listeners/state.
  global.window = { FW, addEventListener() {}, requestIdleCallback: null, innerHeight: 800, scrollY: 0, pageYOffset: 0 };
  global.document = {
    getElementById: getEl,
    createElement: () => fakeEl("_new"),
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    body: { classList: { add() {}, remove() {} }, appendChild() {} },
    documentElement: { scrollHeight: 99999 },
  };
  global.location = { pathname: "/fever-watch/gulbarga/", origin: "https://x", href: "https://x/fever-watch/gulbarga/" };
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
function check(label, jsRel, preMarker, BREAK) {
  const appHTML = runFlow(jsRel);
  const pm = page.indexOf(preMarker);
  if (pm < 0) { console.error(label + ": could not find SSR marker " + JSON.stringify(preMarker)); process.exit(2); }
  const ssrInner = page.slice(pm + preMarker.length);
  let i = 0;
  const n = Math.min(appHTML.length, ssrInner.length);
  while (i < n && appHTML[i] === ssrInner[i]) i++;
  const jsBreakAt = appHTML.indexOf(BREAK);
  console.log("[" + label + "] common prefix length:", i);
  console.log("[" + label + "] js output length:", appHTML.length, " js break starts at:", jsBreakAt);
  if (i >= jsBreakAt && jsBreakAt > 0) {
    console.log("[" + label + "] PARITY OK: the above-the-fold SSR twin is byte-identical; divergence begins at the first JS-only section.");
    return true;
  }
  console.log("[" + label + "] PARITY MISMATCH at index", i);
  console.log("--- SSR ...:", JSON.stringify(ssrInner.slice(Math.max(0, i - 60), i + 80)));
  console.log("--- JS  ...:", JSON.stringify(appHTML.slice(Math.max(0, i - 60), i + 80)));
  process.exit(1);
}

// MOBILE: SSR closes its pre after the weather card; the breakdown card is the first JS-only section.
check("mobile", "mobile.js", '<div class="fw-pre fw-pre-m">', '<div class="card"><h2 class="sectiontitle">Why this score?');
// DESKTOP: SSR closes its pre after the s-why section (s-why is now in the first fold); the .main wrapper
// holding the below-fold JS-only sections is the first JS-only markup.
check("desktop", "desktop.js", '<div class="fw-pre fw-pre-d">', '<div class="main">');
