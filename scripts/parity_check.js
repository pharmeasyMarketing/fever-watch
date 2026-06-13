// SSR <-> JS above-the-fold parity harness.
// Runs the REAL assets/js/mobile.js inside a minimal DOM stub against the same per-city seed the SSG
// inlines, captures what render() assigns to #fw-app, and diffs it against the server-rendered
// .fw-pre-m region from the built page. Any divergence BEFORE the breakdown card = a CLS risk.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const page = fs.readFileSync(path.join(ROOT, "dist", "fever-watch", "gulbarga", "index.html"), "utf8");

// 1) pull the inlined seed (window.FW = {...};) from the built page
const m = page.match(/window\.FW = (\{.*?\});<\/script>/s);
if (!m) { console.error("could not find window.FW seed"); process.exit(2); }
const FW = JSON.parse(m[1]);

// 2) minimal DOM so the IIFE in mobile.js runs and render() fires from the seed
let appHTML = "";
function fakeEl(id) {
  return {
    id, dataset: {}, style: {}, classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    set innerHTML(v) { if (id === "fw-app") appHTML = v; }, get innerHTML() { return ""; },
    addEventListener() {}, appendChild() {}, removeChild() {}, querySelector() { return null; },
    querySelectorAll() { return []; }, setAttribute() {}, getAttribute() { return null; },
    scrollIntoView() {}, parentNode: null, value: "",
  };
}
const els = {};
function getEl(id) { return (els[id] = els[id] || fakeEl(id)); }
global.window = { FW, addEventListener() {}, requestIdleCallback: null };
global.document = {
  getElementById: getEl,
  createElement: () => fakeEl("_new"),
  addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
  body: { classList: { add() {}, remove() {} }, appendChild() {} },
};
global.location = { pathname: "/fever-watch/gulbarga/", origin: "https://x", href: "https://x/fever-watch/gulbarga/" };
global.history = { pushState() {}, replaceState() {} };
global.sessionStorage = { getItem: () => null, setItem() {} };
global.fetch = () => Promise.reject(new Error("no fetch in harness")); // forces seed-only render
global.Image = function () {};
global.setTimeout = (fn) => 0;

require(path.join(ROOT, "assets", "js", "mobile.js"));

// 3) server-rendered pre region
const pm = page.indexOf('<div class="fw-pre fw-pre-m">');
const ssrInner = page.slice(pm + '<div class="fw-pre fw-pre-m">'.length);

// 4) compare common prefix; the JS output should match the SSR pre right up to where SSR closes the
//    pre (wrap + breakdown onward only exist in the JS render). Report the first divergence.
let i = 0;
const n = Math.min(appHTML.length, ssrInner.length);
while (i < n && appHTML[i] === ssrInner[i]) i++;
const BREAK = '<div class="card"><h2 class="sectiontitle">Why this score?';
const jsBreakAt = appHTML.indexOf(BREAK);

console.log("common prefix length:", i);
console.log("js output length:", appHTML.length, " js breakdown starts at:", jsBreakAt);
if (i >= jsBreakAt && jsBreakAt > 0) {
  console.log("PARITY OK: above-the-fold (hero + loccard + ring + weather) is byte-identical; divergence begins at the breakdown card, which is JS-only.");
} else {
  console.log("PARITY MISMATCH at index", i);
  console.log("--- SSR ...:", JSON.stringify(ssrInner.slice(Math.max(0, i - 60), i + 80)));
  console.log("--- JS  ...:", JSON.stringify(appHTML.slice(Math.max(0, i - 60), i + 80)));
  process.exit(1);
}
