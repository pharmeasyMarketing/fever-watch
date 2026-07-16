#!/usr/bin/env python3
"""Fever Watch static-site generator (stdlib only).

Emits one indexable page per city plus a landing page into dist/fever-watch/,
each device-adaptive (a single URL serves the mobile OR desktop flow, chosen at
load by assets/js/fw-loader.js). Per page we bake: per-city SEO <head>
(title / description / canonical / Open Graph / a JSON-LD @graph with WebPage +
Dataset + FAQPage, NO medical schema), a crawler-readable / no-JS fallback inside
#fw-app, and the shared PharmEasy nav + footer. The chosen flow then hydrates
#fw-app from data/grid.json.

base_url lives only in config/site.json; every in-page path is relative via a
per-page depth prefix, so the same build works on the github.io staging origin
and on a reverse-proxied production subpath. SITE_ENV=staging|production controls
robots.txt and the page robots meta. Modeled on Mosquito Watch's build_site.py.

Usage (from the project root):
    python src/build_assets.py        # one-off: favicons / OG / PWA icons
    python src/build_site.py          # -> dist/fever-watch/
    SITE_ENV=production python src/build_site.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import shutil
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC_DIR)
DIST = os.path.join(ROOT, "dist", "fever-watch")

# The locked brand risk ramp (matches the JS RISK map and tokens.css --risk-*).
RISK = {"HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F"}
RISK_SOFT = {"HIGH": "#FCEBE4", "MODERATE": "#FBF0E2", "LOW-MODERATE": "#F7F3E1", "LOW": "#E4F4EC"}

FAQ_ITEMS = [
    ("What is Fever Watch?",
     "Fever Watch is a daily risk indicator for India's top monsoon fevers (dengue, malaria, "
     "chikungunya and typhoid), shown as one decomposable score per city and disease. "
     "It blends weather conditions, public search interest and PharmEasy lab positivity."),
    ("Is this a diagnosis or medical advice?",
     "No. Fever Watch is a risk indicator only. It is not a diagnosis, not a count of actual cases "
     "or mosquitoes, and not a substitute for a doctor. If you feel unwell, consult a clinician."),
    ("How is the score calculated?",
     "It is a transparent weighted blend of three signals at different points in the illness pipeline: "
     "weather conditions (leading), search interest (coincident) and lab positivity (lagging ground "
     "truth). When lab data is present it leads the score, and the breakdown is always shown."),
    ("What does forecast-only mean?",
     "Where there is not enough lab data for a city and disease yet, the score is a conditions-based "
     "forecast and is held below the HIGH band, so a forecast-only read can never show HIGH. This "
     "keeps the read honest."),
    ("How often is it updated?",
     "Weather is refreshed daily from NOAA CPC and NASA POWER, search interest weekly, and the lab signal daily. "
     "The score for each city is recomputed every day."),
    ("Which cities are covered?",
     "Fever Watch currently covers over 200 Indian cities, with more planned. Use the city search "
     "to see the read for your city."),
]

METHOD_SUMMARY = (
    "Each score is a transparent weighted formula, not a black box. A per-disease environmental score "
    "is built from trailing daily weather (temperature near 29C with lagged rainfall and humidity for "
    "mosquito-borne diseases, and rainfall for waterborne typhoid). That weather signal is then blended "
    "with population search interest and PharmEasy "
    "lab positivity in a confirmation-weighted ensemble, with the driver disease named. Forecast-only "
    "locations are held below the HIGH band."
)

# Full methodology baked into the page (H3 subsections under the "How we calculate this" H2).
METHOD_HTML = (
    "<h3>1. Per-disease environmental score (0 to 100)</h3>"
    "<p>From trailing daily weather, shaped by disease family:</p><ul>"
    "<li><strong>Mosquito-borne</strong> (dengue, malaria, chikungunya): a unimodal temperature response "
    "peaking near 29C (Aedes and Anopheles multiply fastest at 25 to 30C; activity falls below about 18C and "
    "above about 35C), times lagged rainfall over the past 14 days (standing-water sites emerge 1 to 2 weeks "
    "after rain), times relative humidity (above about 60% extends mosquito lifespan).</li>"
    "<li><strong>Waterborne</strong> (typhoid): recent (7-day) plus accumulated (14-day) rainfall as a "
    "contamination and runoff proxy; temperature secondary.</li></ul>"
    "<h3>2. Three independent signals</h3><ul>"
    "<li><strong>Weather conditions</strong> (leading, weeks ahead): the environmental score above.</li>"
    "<li><strong>Google Search Interest</strong> (coincident): symptom-search attention, smoothed and "
    "down-weighted when it spikes alone.</li>"
    "<li><strong>PharmEasy lab signal</strong> (lagging, ground truth): aggregate, de-identified "
    "test-positivity trend, scaled against a <strong>per-disease baseline</strong> because a 'high' positivity "
    "differs sharply by fever (a full signal is reached around 25% positivity for dengue, 4% for malaria, "
    "15% for chikungunya and 45% for typhoid), and held back until enough tests confirm the read.</li></ul>"
    "<h3>3. Confirmation-weighted ensemble</h3>"
    "<p>Not a flat average. With lab data present it dominates (weights about 30 / 22 / 48 weather / search / "
    "positivity); when all three signals agree we nudge the score up by about 8%, and when they disagree we ease "
    "off by about 4% and lean on the lab. Without lab data, a forecast-only mode eases the score back as it "
    "climbs toward the HIGH threshold (a soft cap held below 70) so it can approach but never enter HIGH, "
    "keeping a conditions-only read honest. The city headline is a "
    "max-dominant blend (0.8 times the top disease plus 0.2 times the mean of the rest) with the driver disease named.</p>"
    "<p>In the breakdown each signal is shown as a plain <strong>High / Moderate / Low</strong> level with its "
    "weight and underlying 0 to 100 score, and the three contributions add up exactly to the displayed score.</p>"
    "<h3>Score bands</h3>"
    "<p>Low (0 to 24), Low-moderate (25 to 44), Moderate (45 to 69) and High (70 to 100). A forecast-only "
    "read (no lab data) is eased back as it climbs and held below 70, so it can never reach the red High band.</p>"
    "<h3>Data sources</h3><ul>"
    "<li>Rainfall: NOAA CPC (US public domain)</li>"
    "<li>Temperature and humidity: NASA POWER (NASA Langley, US public domain / CC0)</li>"
    "<li>Search: Google Trends</li>"
    "<li>Positivity: PharmEasy Labs and its Partner Affiliates (aggregate, de-identified)</li></ul>"
    "<h3>Selected research</h3><ul>"
    "<li>Mordecai et al. Thermal biology of mosquito-borne disease. Ecology Letters, 2019.</li>"
    "<li>Liu-Helmersson et al. Vectorial capacity of Aedes aegypti and temperature. PLOS ONE, 2014.</li>"
    "<li>Ginsberg et al. Detecting influenza epidemics using search engine query data. Nature, 2009.</li>"
    "<li>IDSP Weekly Outbreak Reports, MoHFW (official surveillance).</li></ul>"
)

CONSULT_HREF = "https://pharmeasy.in/online-doctor-consultation/?src=feverwatch"
ACTIONS = [
    ("Monsoon precautions", "Cut mosquito sites and bites", "https://pharmeasy.in/blog/17-simple-health-tips-for-the-monsoons/?src=feverwatch"),
    ("Vaccination: does it work?", "What helps, what does not", "https://pharmeasy.in/blog/vaccine-vaccination-what-it-is-how-it-works-and-why-it-matters/?src=feverwatch"),
    ("Fever? Follow our framework", "When to test, when to wait", "https://pharmeasy.in/blog/fever-high-temperature-causes-stages-treatments-and-red-flags/?src=feverwatch"),
    ("Not sure? Talk to a doctor", "Online consult on PharmEasy", CONSULT_HREF),
]
CTA_LABEL = "Book a fever panel test"
# Per-city diagnostics deep-link for the CTA (same link in the SSR fallback and both JS flows; params locked
# with marketing). config/diag_links.json maps {city_id -> clean local packages URL}; unmatched -> DIAG_DEFAULT.
DIAG_SUFFIX = "?src=feverwatch&page=2#:~:text=Fever"
DIAG_DEFAULT = "https://pharmeasy.in/diagnostics/health-checkup-packages"
# Legal-provided disclaimers (verbatim except en-dash normalized to ASCII hyphen per the house style).
MEDICAL_DISCLAIMER = ("Fever Watch is a risk indicator and not a diagnosis or representation of actual case "
                      "counts. It is for informational purposes only and should not constitute medical advice; "
                      "please consult a doctor for any symptoms or health concerns.")
DASHBOARD_NOTE = ("This is a daily updated dashboard where we compute a monsoon-risk score (0-100) based on "
                  "multiple data inputs, including weather data, Google search trends, and aggregate data from "
                  "PharmEasy Labs and its Partner Affiliates.")

READS = [
    ("Dengue", [
        ("How to avoid dengue fever", "https://pharmeasy.in/blog/5-ways-to-avoid-dengue-fever/"),
        ("Home remedies for dengue", "https://pharmeasy.in/blog/home-remedies-for-dengue-by-dr-siddharth-gupta/"),
        ("Food for dengue: what to eat and avoid", "https://pharmeasy.in/blog/food-for-dengue-what-to-eat-and-what-to-avoid/"),
        ("Diabetes and dengue risk", "https://pharmeasy.in/blog/diabetes-can-make-dengue-more-lethal/"),
    ]),
    ("Malaria", [
        ("Types of malaria: symptoms and treatment", "https://pharmeasy.in/blog/types-of-malaria-symptoms-causes-and-treatment/"),
        ("Foods for malaria", "https://pharmeasy.in/blog/foods-for-malaria-what-to-eat-and-what-to-avoid/"),
        ("Home remedies for malaria", "https://pharmeasy.in/blog/home-remedies-for-malaria-by-dr-siddharth-gupta/"),
    ]),
    ("Mosquito bites and monsoon health", [
        ("Mosquito bite remedies", "https://pharmeasy.in/blog/home-remedies-for-mosquito-bite-by-dr-siddharth-gupta/"),
        ("Mosquito bites on babies", "https://pharmeasy.in/blog/child-care-mosquito-bites-on-babies-home-remedies-treatment-and-prevention/"),
        ("Common monsoon illnesses in India", "https://pharmeasy.in/blog/common-illnesses-during-monsoons-in-india/"),
        ("Monsoon health tips", "https://pharmeasy.in/blog/17-simple-health-tips-for-the-monsoons/"),
    ]),
]

PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','GTM-W5PR55Z');</script>
<!-- End Google Tag Manager -->
{head}
{jsonld}
<link rel="preload" href="{rel}assets/fonts/inter-latin-700-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{rel}assets/fonts/inter-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{rel}assets/js/mobile.js?v={av}" as="script" media="(max-width: 819px), (pointer: coarse)">
<link rel="preload" href="{rel}assets/js/desktop.js?v={av}" as="script" media="(min-width: 820px) and (pointer: fine)">
<link rel="stylesheet" href="{rel}assets/css/tokens.css?v={av}">
<link rel="stylesheet" href="{rel}assets/css/mobile.css?v={av}" media="(max-width: 819px), (pointer: coarse)">
<link rel="stylesheet" href="{rel}assets/css/desktop.css?v={av}" media="(min-width: 820px) and (pointer: fine)">
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-W5PR55Z" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
{nav}
{ticker}
<div id="fw-app">{fallback}</div>
{footer}
<script>window.FW = {fw};</script>
<script src="{rel}assets/js/faq.js?v={av}" defer></script>
<script src="{rel}assets/js/trend.js?v={av}" defer></script>
<script src="{rel}assets/js/method.js?v={av}" defer></script>
<script src="{rel}assets/js/fw-loader.js?v={av}" defer></script>
<script src="{rel}assets/js/geo.js?v={av}" defer></script>
<script src="{rel}assets/js/share.js?v={av}" defer></script>
</body>
</html>
"""

# Anti-CLS: the baked fallback (#fw-app .fw-fallback) stays VISIBLE as first paint - it is complete,
# real content rendered from the same grid, so the footer sits in its final position immediately. The
# flow then replaces #fw-app in one shot on hydration (footer never jumps). The header ticker is baked
# server-side too (ticker_html) so injecting it can't shift the layout either.


def esc(s) -> str:
    # Mirror assets/js/mobile.js esc() exactly (incl. the single quote -> &#39;), so the server-rendered
    # above-the-fold block stays byte-identical to the JS repaint even for a name containing an apostrophe.
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# Per-city header "Medicines" nav target: config/med_links.json maps {city_id -> local online-medicine-order
# page}; unmatched cities (and the national landing) use MED_DEFAULT. Same alias map as diag_links. The header
# is baked per page (SSR) and reflects the page's city; it does not re-render on client-side city switch.
MED_SUFFIX = "?src=feverwatch"
MED_DEFAULT = "https://pharmeasy.in/online-medicine-order"
try:
    MED_LINKS = {k: v for k, v in load_json(os.path.join(ROOT, "config", "med_links.json")).items()
                 if not k.startswith("_")}
except Exception:
    MED_LINKS = {}
def _meds_href(city_id):
    return (MED_LINKS.get(city_id, MED_DEFAULT) if city_id else MED_DEFAULT) + MED_SUFFIX


def iso_date(iso) -> str:
    """IST (UTC+5:30) calendar date of the build, YYYY-MM-DD - the sitemap <lastmod>. Shifts the UTC
    generated_at +5:30 so the lastmod matches the India date shown on the page."""
    try:
        return (datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    except Exception:
        return (iso or "")[:10]


def iso_datetime_ist(iso) -> str:
    """IST (UTC+5:30) ISO-8601 timestamp of the build, e.g. '2026-06-24T05:08:42+05:30' - the JSON-LD
    dateModified. Shifts the UTC generated_at +5:30 so its calendar date matches the IST sitemap
    <lastmod> (iso_date) and the visible 'Updated' text (_fmt_date_js); a 22:30-UTC cron build is
    already the next day in IST, so without this the structured-data date trails the page by one day."""
    try:
        d = datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
        return d.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    except Exception:
        return iso or ""


def og_version(iso) -> str:
    """Compact digits of generated_at (YYYYMMDDHHMMSS) used as an og:image cache-bust,
    so social platforms fetch a fresh preview whenever the scores are recomputed."""
    return "".join(ch for ch in (iso or "") if ch.isdigit())[:14]


def asset_version() -> str:
    """Short content hash of the CSS/JS bundle, appended as ?v= to every asset URL so a new
    release busts the browser cache (GitHub Pages serves files by URL with max-age=600, so an
    unversioned mobile.js stays stale on a phone that already cached it). Hash is content-based,
    so a data-only daily rebuild keeps the same version and does not force a needless refetch."""
    h = hashlib.md5()
    for rel in ("prototypes/tokens.css", "assets/css/mobile.css", "assets/css/desktop.css",
                "assets/js/geo.js", "assets/js/share.js", "assets/js/faq.js", "assets/js/trend.js",
                "assets/js/method.js", "assets/js/fw-loader.js", "assets/js/mobile.js", "assets/js/desktop.js"):
        try:
            with open(os.path.join(ROOT, rel), "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:10]


# --- shared baked chrome -----------------------------------------------------

def nav_html(rel: str, meds_href: str) -> str:
    items = (
        '<div class="pe-nav-item"><button type="button" class="pe-nav-btn" aria-expanded="false" aria-haspopup="true">Healthcare <span class="pe-caret" aria-hidden="true">&#9662;</span></button>'
        '<div class="pe-nav-drop">'
        '<a href="' + meds_href + '">Medicines</a>'
        '<a href="https://pharmeasy.in/diagnostics?src=homecard">Lab tests</a>'
        '<a href="https://pharmeasy.in/online-doctor-consultation/">Doctor consult</a>'
        '<a href="https://pharmeasy.in/health-care?src=homecard">Healthcare products</a>'
        '</div></div>'
        '<div class="pe-nav-item"><button type="button" class="pe-nav-btn" aria-expanded="false" aria-haspopup="true">Health Hub <span class="pe-caret" aria-hidden="true">&#9662;</span></button>'
        '<div class="pe-nav-drop">'
        '<a href="https://pharmeasy.in/blog?src=homecard">Blog</a>'
        '<a href="https://pharmeasy.in/conditions">Conditions</a>'
        '<a href="https://pharmeasy.in/qna">AskEasy</a>'
        '</div></div>'
        '<a class="pe-nav-link" href="https://pharmeasy.in/legal/editorial-policy">Editorial Policy</a>'
        '<div class="pe-nav-item"><button type="button" class="pe-nav-btn" aria-expanded="false" aria-haspopup="true">Research &amp; Insights <span class="pe-caret" aria-hidden="true">&#9662;</span></button>'
        '<div class="pe-nav-drop">'
        '<a href="https://pharmeasy.in/research/dengue">Dengue Research 2025</a>'
        '<a href="https://pharmeasy.in/research/diabetes">Diabetes Research</a>'
        '<a href="https://pharmeasy.in/research/branded-vs-generics">Generic Medicines Research</a>'
        '</div></div>'
    )
    return (
        '<header class="fw-nav"><div class="navin">'
        '<a class="pe-logo" href="https://pharmeasy.in/" aria-label="PharmEasy Fever Watch home">'
        '<img class="pe-mark" src="' + rel + 'assets/img/pe_logo-white.svg" alt="PharmEasy">'
        '<span class="pe-rule" aria-hidden="true"></span>'
        '<span class="fw-word">Fever Watch</span></a>'
        '<nav class="pe-topnav" id="pe-topnav" aria-label="PharmEasy">' + items + '</nav>'
        '<button type="button" class="pe-burger" aria-label="Open menu" aria-expanded="false" aria-controls="pe-topnav">&#9776;</button>'
        '</div></header>'
    )


def ticker_html(all_cities: list, rel: str) -> str:
    """Baked 'live this week' ticker (top cities by blend), emitted server-side right after the header
    so it is present at first paint - no JS injection, no layout shift. Anchors are crawlable and the
    flow wires the marquee pause behavior over them on hydration."""
    ranked = sorted(all_cities, key=lambda c: c["blend"]["score"], reverse=True)[:12]
    items = ""
    for c in ranked:
        b = c["blend"]
        col = RISK.get(b["band"], "#888")
        soft = RISK_SOFT.get(b["band"], "#eee")
        items += ('<a class="fw-tick" href="' + rel + esc(c["id"]) + '/" data-act="pickrow" data-id="' + esc(c["id"]) + '">'
                  '<span class="tdot" style="background:' + col + '"></span>' + esc(c["name"])
                  + ' <b style="color:' + col + '">' + str(b["score"]) + '</b>'
                  + '<span class="tpill" style="color:' + col + ';background:' + soft + '">' + esc(b["band"]) + '</span></a>')
    return ('<div class="fw-ticker" id="fwticker"><div class="fw-ticker-in">'
            '<span class="fw-ticker-label"><span class="livedot"></span> Live</span>'
            '<div class="fw-ticker-vp"><div class="fw-ticker-track">' + items + items + '</div></div></div></div>')


# Footer regrouped to the PharmEasy reference: 3 link columns (Company+Services / Featured Categories /
# Need Help+Policy) + a Follow Us column with social icons. No payment row (removed per request).
FOOT_COMPANY = [("About Us", "https://pharmeasy.in/about-us"), ("Careers", "https://pharmeasy.in/careers"),
                ("Blog", "https://pharmeasy.in/blog"), ("Partner with PharmEasy", "https://pharmeasy.in/franchisestores")]
FOOT_SERVICES = [("Order Medicine", "https://pharmeasy.in/"), ("Healthcare Products", "https://pharmeasy.in/health-care"),
                 ("Lab Tests", "https://pharmeasy.in/diagnostics")]
FOOT_CATEGORIES = [
    ("Must Haves", "https://pharmeasy.in/health-care/top-products-9297"),
    ("Vitamin Store", "https://pharmeasy.in/health-care/fitness-supplements-623"),
    ("Sexual Wellness", "https://pharmeasy.in/health-care/sexual-wellness-575"),
    ("Personal Care", "https://pharmeasy.in/health-care/personal-care-877"),
    ("Homeopathy Care", "https://pharmeasy.in/health-care/homeopathy-care-12811"),
    ("Summer Store", "https://pharmeasy.in/health-care/summer-store-16709"),
    ("Health Food and Drinks", "https://pharmeasy.in/health-care/health-food-and-drinks-648"),
    ("Diabetes Essentials", "https://pharmeasy.in/health-care/diabetic-care-145"),
    ("Ayurvedic Care", "https://pharmeasy.in/health-care/ayurvedic-care-712"),
    ("Mother and Baby Care", "https://pharmeasy.in/health-care/mother-and-baby-care-911"),
    ("Mobility & Elderly Care", "https://pharmeasy.in/health-care/elderly-care-12810"),
    ("Sports Nutrition", "https://pharmeasy.in/health-care/sports-nutrition-624"),
    ("Healthcare Devices", "https://pharmeasy.in/health-care/healthcare-devices-882"),
    ("Skin Care", "https://pharmeasy.in/health-care/skin-care-576"),
    ("Health Concerns", "https://pharmeasy.in/health-care/health-conditions-13624"),
    ("Explore More", "https://pharmeasy.in/health-care"),
]
FOOT_HELP = [("Browse All Medicines", "https://pharmeasy.in/online-medicine-order/browse"),
             ("Browse All Molecules", "https://pharmeasy.in/molecules"),
             ("Browse All Cities & Areas", "https://pharmeasy.in/online-medicine-order/browse/areas"),
             ("FAQs", "https://pharmeasy.in/help")]
FOOT_POLICY = [("Editorial Policy", "https://pharmeasy.in/legal/editorial-policy"),
               ("Privacy Policy", "https://pharmeasy.in/legal/privacy-policy"),
               ("Vulnerability Disclosure Policy", "https://pharmeasy.in/vulnerability-disclosure-policy"),
               ("Terms and condition", "https://pharmeasy.in/terms-and-conditions"),
               ("Declaration on Dark Pattern", "https://assets.pharmeasy.in/web-assets/legal/circulars/Axelia_Self-Declaration_Dark_Patterns.pdf"),
               ("Customer Support Policy", "https://pharmeasy.in/customer-support-policy"),
               ("Return Policy", "https://pharmeasy.in/return-policy"),
               ("Smartbuy Policy", "https://pharmeasy.in/smartbuy-policy")]
_IG = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5.4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.2" cy="6.8" r="1.3" fill="currentColor"/></svg>'
_FB = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.8 3.7-3.8 1.1 0 2.2.2 2.2.2v2.4h-1.2c-1.2 0-1.6.8-1.6 1.5V12h2.7l-.4 2.9h-2.3v7A10 10 0 0 0 22 12z"/></svg>'
_YT = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M23 7.5a2.9 2.9 0 0 0-2-2C19.1 5 12 5 12 5s-7.1 0-9 .5a2.9 2.9 0 0 0-2 2A30 30 0 0 0 .5 12 30 30 0 0 0 1 16.5a2.9 2.9 0 0 0 2 2c1.9.5 9 .5 9 .5s7.1 0 9-.5a2.9 2.9 0 0 0 2-2 30 30 0 0 0 .5-4.5A30 30 0 0 0 23 7.5zM9.8 15.3V8.7l5.7 3.3z"/></svg>'
_TW = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M22 5.9c-.7.3-1.5.5-2.3.6a4 4 0 0 0 1.8-2.2c-.8.5-1.7.8-2.6 1A4 4 0 0 0 12 9.2c0 .3 0 .6.1.9A11.4 11.4 0 0 1 3.1 4.6a4 4 0 0 0 1.2 5.4c-.6 0-1.2-.2-1.7-.4a4 4 0 0 0 3.2 4c-.5.1-1.1.2-1.7.1a4 4 0 0 0 3.7 2.8A8.1 8.1 0 0 1 2 18a11.4 11.4 0 0 0 6.1 1.8c7.4 0 11.5-6.1 11.5-11.5v-.5c.8-.6 1.5-1.3 2-2z"/></svg>'
FOOTER_SOCIAL = [("Instagram", "https://www.instagram.com/pharmeasyapp/", _IG),
                 ("Facebook", "https://www.facebook.com/pharmeasy/", _FB),
                 ("YouTube", "https://www.youtube.com/channel/UCDats_DLX-bGZH3-KGu8JhA", _YT),
                 ("Twitter", "https://www.twitter.com/pharmeasyapp/", _TW)]


def footer_html() -> str:
    def sec(h, links):
        return ('<div class="footsec"><h2>' + esc(h) + '</h2>'
                + "".join('<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(t) + '</a>' for t, u in links)
                + '</div>')
    col1 = '<div class="footcol">' + sec("Company", FOOT_COMPANY) + sec("Our Services", FOOT_SERVICES) + '</div>'
    col2 = '<div class="footcol">' + sec("Featured Categories", FOOT_CATEGORIES) + '</div>'
    col3 = '<div class="footcol">' + sec("Need Help", FOOT_HELP) + sec("Policy Info", FOOT_POLICY) + '</div>'
    social = "".join('<a href="' + esc(u) + '" target="_blank" rel="noopener" aria-label="' + esc(t) + '">' + svg + '</a>' for t, u, svg in FOOTER_SOCIAL)
    col4 = '<div class="footcol footfollow"><h2>Follow Us</h2><div class="footsocial">' + social + '</div></div>'
    return (
        '<footer class="footer"><div class="footin">' + col1 + col2 + col3 + col4 + '</div>'
        '<div class="footbar"><div class="footbarin">'
        '<span class="footdisc">' + MEDICAL_DISCLAIMER + ' The data used to calculate the risk is derived from: live rainfall via NOAA CPC (public domain) and temperature/humidity via NASA POWER (public domain); Google search trends via Serpapi; aggregate lab data from PharmEasy Labs and its Partner Affiliates.</span>'
        '<span>&#169; 2026 PharmEasy. All Rights Reserved</span></div></div></footer>'
    )


# --- per-page SEO ------------------------------------------------------------

def head_meta(cfg: dict, env: str, title: str, desc: str, canonical: str, rel: str, og_url: str, og_alt: str) -> str:
    og_img = og_url
    robots = "index,follow,max-image-preview:large" if env == "production" else "noindex,nofollow"
    parts = [
        '<title>' + esc(title) + '</title>',
        '<meta name="description" content="' + esc(desc) + '">',
        '<link rel="canonical" href="' + esc(canonical) + '">',
        '<meta name="robots" content="' + robots + '">',
        '<meta name="theme-color" content="' + cfg.get("theme_color", "#10847E") + '">',
        '<meta name="color-scheme" content="light">',
        '<meta name="geo.region" content="IN"><meta name="geo.placename" content="India">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="' + esc(cfg["site_name"]) + '">',
        '<meta property="og:title" content="' + esc(title) + '">',
        '<meta property="og:description" content="' + esc(desc) + '">',
        '<meta property="og:url" content="' + esc(canonical) + '">',
        '<meta property="og:image" content="' + esc(og_img) + '">',
        '<meta property="og:image:type" content="' + ("image/jpeg" if ".jpg" in og_img else "image/png") + '">',
        '<meta property="og:image:width" content="' + str(cfg.get("og_image_width", 1200)) + '">',
        '<meta property="og:image:height" content="' + str(cfg.get("og_image_height", 630)) + '">',
        '<meta property="og:image:alt" content="' + esc(og_alt) + '">',
        '<meta property="og:locale" content="' + cfg.get("locale", "en_IN") + '">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="' + esc(title) + '">',
        '<meta name="twitter:description" content="' + esc(desc) + '">',
        '<meta name="twitter:image" content="' + esc(og_img) + '">',
    ]
    if cfg.get("twitter_handle"):
        parts.append('<meta name="twitter:site" content="' + esc(cfg["twitter_handle"]) + '">')
    parts += [
        '<link rel="icon" href="' + rel + 'assets/img/favicon.ico" sizes="any">',
        '<link rel="icon" type="image/svg+xml" href="' + rel + 'assets/img/favicon.svg">',
        '<link rel="apple-touch-icon" href="' + rel + 'assets/img/apple-touch-icon.png">',
        '<link rel="manifest" href="' + rel + 'site.webmanifest">',
    ]
    return "\n".join(parts)


def jsonld(cfg: dict, generated_at: str, diseases: list, city: dict | None, og_url: str, faq: list,
          disease: dict | None = None) -> str:
    base = cfg["base_url"]
    # dateModified must express the IST calendar date - the same one the sitemap <lastmod> and the
    # visible "Updated" text show. generated_at is minted in UTC, so shift it +5:30 once here so all
    # three @graph nodes below inherit the India date (otherwise a 22:30-UTC build reads a day behind).
    generated_at = iso_datetime_ist(generated_at)
    pub = cfg["publisher"]
    lang = cfg.get("language", "en-IN")
    org = {"@type": "Organization", "@id": base + "#organization", "name": pub["name"],
           "url": pub["url"], "logo": pub.get("logo"), "sameAs": list(pub.get("sameAs", []))}
    if pub.get("legal_name"):
        org["legalName"] = pub["legal_name"]
    website = {"@type": "WebSite", "@id": base + "#website", "name": cfg["site_name"],
               "url": base, "inLanguage": lang, "publisher": {"@id": base + "#organization"}}
    faqpage = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    graph = [org, website]
    if city and disease:
        url = base + city["id"] + "/" + disease["id"] + "/"
        hub_url = base + city["id"] + "/"
        dl = disease["label"]
        graph.append({
            "@type": "WebPage", "@id": url, "url": url,
            "name": dl + " risk in " + city["name"] + " | Fever Watch",
            "description": "Daily " + dl + " risk score (0 to 100) for " + city["name"]
                           + ", India, blended from weather conditions, search interest and lab positivity.",
            "inLanguage": lang, "isPartOf": {"@id": base + "#website"},
            "about": [dl, "monsoon fever risk in India"],
            "primaryImageOfPage": og_url, "dateModified": generated_at,
            "breadcrumb": {"@id": url + "#breadcrumb"},
            "reviewedBy": [{"@type": "Person", "@id": r["url"] + "#person", "name": r["name"], "url": r["url"],
                            "jobTitle": "Doctor", "worksFor": {"@id": base + "#organization"}} for r in REVIEWERS],
        })
        graph.append({
            "@type": "BreadcrumbList", "@id": url + "#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": pub["name"], "item": pub["url"] + "/"},
                {"@type": "ListItem", "position": 2, "name": cfg["site_name"], "item": base},
                {"@type": "ListItem", "position": 3, "name": city["name"], "item": hub_url},
                {"@type": "ListItem", "position": 4, "name": dl, "item": url},
            ],
        })
        graph.append({
            "@type": "Dataset", "@id": url + "#dataset",
            "name": "Fever Watch " + dl + " risk scores for " + city["name"],
            "description": "A daily, decomposable " + dl + " risk score (0 to 100) for " + city["name"]
                           + ", India, blended from weather conditions, search interest and lab positivity. "
                           "A risk indicator, not case counts.",
            "url": url, "inLanguage": lang, "isAccessibleForFree": True,
            "creator": {"@id": base + "#organization"}, "publisher": {"@id": base + "#organization"},
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "spatialCoverage": {"@type": "Place", "name": city["name"] + ", India",
                                "geo": {"@type": "GeoCoordinates", "latitude": city["lat"], "longitude": city["lon"]}},
            "temporalCoverage": iso_date(generated_at)[:4] + "-06-01/..",
            "measurementTechnique": "Confirmation-weighted blend of weather suitability (NOAA CPC rainfall; "
                                    "NASA POWER temperature and humidity), Google search interest and PharmEasy "
                                    "lab test positivity, normalized 0 to 100 per disease and recomputed daily. "
                                    "Cities without lab confirmation are held below the HIGH band.",
            "isBasedOn": [
                {"@type": "CreativeWork", "name": "NOAA CPC Global Unified Gauge-Based Analysis of Daily Precipitation",
                 "url": "https://psl.noaa.gov/data/gridded/data.cpc.globalprecip.html"},
                {"@type": "CreativeWork", "name": "NASA POWER meteorology", "url": "https://power.larc.nasa.gov/"},
                {"@type": "CreativeWork", "name": "Google Trends search interest (via SerpApi)", "url": "https://trends.google.com/"},
                {"@type": "CreativeWork", "name": "PharmEasy lab test positivity (aggregated, de-identified)",
                 "url": "https://pharmeasy.in/diagnostics"},
            ],
            "variableMeasured": [{"@type": "PropertyValue", "name": disease["id"] + "_risk_score",
                                  "minValue": 0, "maxValue": 100},
                                 {"@type": "PropertyValue", "name": disease["id"] + "_weather_signal", "minValue": 0, "maxValue": 100},
                                 {"@type": "PropertyValue", "name": disease["id"] + "_search_signal", "minValue": 0, "maxValue": 100},
                                 {"@type": "PropertyValue", "name": disease["id"] + "_lab_positivity_signal", "minValue": 0, "maxValue": 100}],
            "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": base + "data/grid.json"},
            "dateModified": generated_at,
        })
        graph.append(faqpage)
    elif city:
        url = base + city["id"] + "/"
        graph.append({
            "@type": "WebPage", "@id": url, "url": url,
            "name": city["name"] + " monsoon fever risk | Fever Watch",
            "description": "Daily dengue, malaria, chikungunya and typhoid risk for "
                           + city["name"] + ", India.",
            "inLanguage": lang, "isPartOf": {"@id": base + "#website"},
            "about": [d["label"] for d in diseases] + ["monsoon fever risk in India"],
            "primaryImageOfPage": og_url, "dateModified": generated_at,
            "breadcrumb": {"@id": url + "#breadcrumb"},
            "reviewedBy": [{"@type": "Person", "@id": r["url"] + "#person", "name": r["name"], "url": r["url"],
                            "jobTitle": "Doctor", "worksFor": {"@id": base + "#organization"}} for r in REVIEWERS],
        })
        # Breadcrumb trail (PharmEasy > Fever Watch > {City}) - a GENERIC navigation entity, not medical
        # schema, so it stays inside the no-medical-JSON-LD guardrail.
        graph.append({
            "@type": "BreadcrumbList", "@id": url + "#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": pub["name"], "item": pub["url"] + "/"},
                {"@type": "ListItem", "position": 2, "name": cfg["site_name"], "item": base},
                {"@type": "ListItem", "position": 3, "name": city["name"], "item": url},
            ],
        })
        graph.append({
            "@type": "Dataset", "@id": url + "#dataset",
            "name": "Fever Watch risk scores for " + city["name"],
            "description": "A daily, decomposable monsoon-fever risk score (0 to 100) per disease for "
                           + city["name"] + ", India, blended from weather conditions, search interest and "
                           "lab positivity. A risk indicator, not case counts.",
            "url": url, "inLanguage": lang, "isAccessibleForFree": True,
            "creator": {"@id": base + "#organization"}, "publisher": {"@id": base + "#organization"},
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "spatialCoverage": {"@type": "Place", "name": city["name"] + ", India",
                                "geo": {"@type": "GeoCoordinates", "latitude": city["lat"], "longitude": city["lon"]}},
            # temporalCoverage: this monsoon season, open-ended (ISO 8601 interval; ".." = ongoing).
            "temporalCoverage": iso_date(generated_at)[:4] + "-06-01/..",
            "measurementTechnique": "Confirmation-weighted blend of weather suitability (NOAA CPC rainfall; "
                                    "NASA POWER temperature and humidity), Google search interest and PharmEasy "
                                    "lab test positivity, normalized 0 to 100 per disease and recomputed daily. "
                                    "Cities without lab confirmation are held below the HIGH band.",
            "isBasedOn": [
                {"@type": "CreativeWork", "name": "NOAA CPC Global Unified Gauge-Based Analysis of Daily Precipitation",
                 "url": "https://psl.noaa.gov/data/gridded/data.cpc.globalprecip.html"},
                {"@type": "CreativeWork", "name": "NASA POWER meteorology", "url": "https://power.larc.nasa.gov/"},
                {"@type": "CreativeWork", "name": "Google Trends search interest (via SerpApi)", "url": "https://trends.google.com/"},
                {"@type": "CreativeWork", "name": "PharmEasy lab test positivity (aggregated, de-identified)",
                 "url": "https://pharmeasy.in/diagnostics"},
            ],
            "variableMeasured": [{"@type": "PropertyValue", "name": "overall_fever_risk_score",
                                  "minValue": 0, "maxValue": 100}]
                               + [{"@type": "PropertyValue", "name": d["id"] + "_risk_score",
                                   "minValue": 0, "maxValue": 100} for d in diseases],
            "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": base + "data/grid.json"},
            "dateModified": generated_at,
        })
        graph.append(faqpage)
    else:
        graph.append({
            "@type": "WebApplication", "@id": base + "#webapplication", "name": cfg["site_name"], "url": base,
            "applicationCategory": "ReferenceApplication", "operatingSystem": "Web",
            "browserRequirements": "The headline read is available without JavaScript; the interactive flow needs it.",
            "isAccessibleForFree": True, "inLanguage": lang, "description": cfg["description"],
            "dateModified": generated_at, "isPartOf": {"@id": base + "#website"},
            "creator": {"@id": base + "#organization"}, "publisher": {"@id": base + "#organization"},
            "reviewedBy": [{"@type": "Person", "@id": r["url"] + "#person", "name": r["name"], "url": r["url"],
                            "jobTitle": "Doctor", "worksFor": {"@id": base + "#organization"}} for r in REVIEWERS],
        })
        graph.append({
            "@type": "BreadcrumbList", "@id": base + "#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": pub["name"], "item": pub["url"] + "/"},
                {"@type": "ListItem", "position": 2, "name": cfg["site_name"], "item": base},
            ],
        })
        graph.append(faqpage)
    body = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return '<script type="application/ld+json">\n' + body + '\n</script>'


# --- baked full content (crawler / no-JS; hidden for JS users, which hydrate over it) ---------

SIG_COLS = [("weather", "Weather conditions"), ("trends", "Search interest"), ("positivity", "Lab positivity")]


CLIMATE_PHRASE = {
    "tropical_wet": "warm, high-rainfall tropical",
    "tropical_savanna": "seasonal tropical (wet and dry)",
    "semi_arid": "hot, semi-arid",
    "humid_subtropical": "humid subtropical",
    "temperate": "cooler, temperate",
}
_ORD = {1: "biggest", 2: "second-biggest", 3: "third-biggest", 4: "fourth-biggest", 5: "smallest"}


def faq_items_landing() -> list:
    return list(FAQ_ITEMS)


def faq_items(city: dict, diseases: list, cells_by: dict, all_cities: list, generated_at: str) -> list:
    """10 humanized, per-city FAQ (question, answer) pairs that weave in the live data, so every city
    page gets a unique, SEO-rich FAQ. Conversational voice; risk-indicator framing only; ASCII hyphens;
    no diagnosis or medical claims; positivity only as an aggregate trend; weather is not body fever."""
    cid = city["id"]; nm = city["name"]; st = city["state"]
    b = city["blend"]; bs = str(b["score"]); bb = b["band"]
    drv = next((d for d in diseases if d["id"] == b["driver"]), diseases[0])
    dl = drv["label"]; dsc = str(b["driver_score"]); dbd = cells_by[(cid, b["driver"])]["band"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    rank_list = ", ".join(d["label"] + " (" + str(cells_by[(cid, d["id"])]["score"]) + ")" for d in ordered)
    den = cells_by[(cid, "dengue")]; den_s = str(den["score"]); den_b = den["band"]
    dw = int(den.get("signals", {}).get("weather") or 0); den_w = str(dw)
    den_t = den.get("signals", {}).get("trends"); den_t_s = "no data" if den_t is None else str(den_t)
    news = bool(den.get("signals", {}).get("news_spike"))
    drank = next((i + 1 for i, d in enumerate(ordered) if d["id"] == "dengue"), 1)
    any_conf = any(cells_by[(cid, d["id"])].get("mode") == "confirmed" for d in diseases)
    w = city.get("weather", {})
    temp = str(int(math.floor(w.get("temp_mean_c", 0) + 0.5))); hum = str(int(math.floor(w.get("humidity_pct", 0) + 0.5)))
    rain14 = str(int(math.floor(w.get("rain_14d_mm", 0) + 0.5)))
    clim = CLIMATE_PHRASE.get(city.get("climate", ""), "monsoon")
    ranked = sorted(all_cities, key=lambda c: c["blend"]["score"], reverse=True)
    rank = next((i + 1 for i, c in enumerate(ranked) if c["id"] == cid), len(all_cities)); ncit = len(all_cities)
    tert = "the higher-risk third" if rank <= ncit / 3.0 else ("the middle band" if rank <= 2 * ncit / 3.0 else "the lower half")
    date_str = _fmt_date_js(generated_at)

    den_mode = ("we don't have confirmed lab numbers for " + nm + " yet, so this is a conditions-based estimate that we deliberately cap below the HIGH band to keep it honest"
                if den.get("mode") != "confirmed"
                else "PharmEasy lab results feed into this one, so it reflects what's actually turning up in tests, not just the weather")
    weights_clause = ("When lab data is in, it leads - the mix is roughly 30/22/48 across weather, search and labs, with a small confidence bump when all three agree"
                      if any_conf
                      else "Lab data hasn't reached " + nm + " yet, so for now it's a weather-and-search forecast (about 60/40) that we hold below the HIGH band until the labs back it up")
    season_clause = ("that's firmly in risk-raising territory" if dw >= 60 else ("that's middling - not nothing, not alarming" if dw >= 25 else "that's on the quiet side for now"))
    band_open = {
        "HIGH": "A HIGH reading (" + bs + "/100) means conditions and signals in " + nm + " are lining up strongly right now - the moment to be most careful about bites, clearing standing water, and not shrugging off a fever that drags past a couple of days.",
        "MODERATE": "A MODERATE reading (" + bs + "/100) means things in " + nm + " are a touch elevated but mixed - not a red alert, just a nudge to take the usual precautions.",
        "LOW-MODERATE": "A LOW-MODERATE reading (" + bs + "/100) means " + nm + " is fairly calm right now - low pressure overall, though the monsoon can turn that around fast.",
        "LOW": "A LOW reading (" + bs + "/100) means it's quiet in " + nm + " right now - conditions and signals are all on the gentle side.",
    }.get(bb, "A " + bb + " reading (" + bs + "/100) is the headline for " + nm + " right now.")
    cap_clause = (" And since " + nm + " is on a conditions-only forecast for now, we hold it below the HIGH band - it won't show HIGH until lab data confirms it." if not any_conf else "")
    news_clause = (", and there's a national news spike around dengue at the moment" if news else "")

    return [
        ("How worried should I be about monsoon fevers in " + nm + " right now?",
         "Right now " + nm + "'s overall score is " + bs + "/100, which lands in the " + bb + " band - and " + dl + " is the main thing nudging it up (it's sitting at " + dsc + "). Think of the score as a daily look at local risk across the four fevers we track, not who's actually sick, so it's a heads-up rather than a diagnosis. We recompute it every day; this one's from " + date_str + "."),
        ("Is dengue something to watch in " + nm + " right now?",
         "Dengue's at " + den_s + "/100 in " + nm + " (" + den_b + ") today, which makes it the " + _ORD.get(drank, "biggest") + " concern of the four fevers here. " + den_mode[0].upper() + den_mode[1:] + ". Either way it's a risk signal built from weather conditions, search interest and lab data - not a count of cases or mosquitoes, and not a diagnosis."),
        ("Of all the monsoon fevers, which one should " + nm + " keep an eye on?",
         "Today it's " + dl + ", at " + dsc + "/100 (" + dbd + "). Here's the full order right now, highest to lowest: " + rank_list + ". Worth checking back, though - we rerun this daily, and the ranking really does shuffle as the weather, searches and lab signals move."),
        ("How is " + nm + "'s weather affecting the mosquito-fever risk?",
         nm + " has a " + clim + " climate, and right now it's averaging about " + temp + "C with " + hum + "% humidity and roughly " + rain14 + " mm of rain over the last fortnight. Mosquitoes like Aedes and Anopheles multiply fastest near 29C and use the standing water that shows up a week or two after rain, so warm, wet spells push our weather signal up and drier or cooler ones pull it back down. (Worth flagging: that's outdoor weather, not body-temperature fever.)"),
        ("Where does the " + nm + " score actually come from?",
         "Three signals, blended: weather conditions (from NASA's open POWER data), how much people are searching for these illnesses, and PharmEasy's lab positivity. " + weights_clause + ". We always show the breakdown - it's never a mystery number. For reference, the bands are LOW (0-24), LOW-MODERATE (25-44), MODERATE (45-69) and HIGH (70 and up)."),
        ("Is it dengue season in " + nm + " yet?",
         "Monsoon fevers follow the rain more than the calendar. Right now " + nm + "'s weather signal for the mosquito-borne ones is " + den_w + "/100, with about " + rain14 + " mm of rain over the past fortnight leaving standing water - " + season_clause + ". So rather than guessing by the month, just check back here; it updates daily, and you'll see conditions climb or ease in real time."),
        ("Is " + nm + " better or worse off than other Indian cities right now?",
         "Out of the " + str(ncit) + " cities we cover, " + nm + " ranks #" + str(rank) + " today on the overall score (" + bs + "/100, " + bb + "), which puts it in " + tert + " nationally. That ordering shifts through the season, though, because every city is rescored each day from its own weather, searches and lab signals."),
        ("What does a " + bb + " reading actually mean for " + nm + "?",
         band_open + " The bands run LOW, LOW-MODERATE, MODERATE, then HIGH." + cap_clause),
        ("Are dengue cases actually rising in " + nm + "?",
         "We can't give you case counts - Fever Watch doesn't report those. What we can show is how much " + st + " is searching for dengue, which is " + den_t_s + "/100 today" + news_clause + ". Search spikes often track public worry and can run ahead of, or alongside, an outbreak - but they aren't confirmed cases. For the confirmed side we lean on PharmEasy's aggregated, de-identified lab positivity wherever it's available."),
        ("What should someone in " + nm + " actually do right now?",
         "With " + nm + " at " + bb + " (" + bs + "/100) and " + dl + " leading, the sensible basics: tip out any standing water and use repellent for the mosquito-borne ones, stick to safe drinking water to keep typhoid at bay, and don't brush off a fever that lasts more than a couple of days. If you're feeling off, a fever panel test or a quick online doctor consult on PharmEasy is an easy next step. And the usual reminder - this is a risk indicator, not medical advice, so do see a doctor if you're unwell."),
    ]


def _faq_html(faq) -> str:
    """The accordion (brand-recreated from the design handoff): rounded cards, a chevron tile that
    flips, the first two open. Native <details> so it works with no JS and for crawlers."""
    out = ""
    for i, (q, a) in enumerate(faq):
        op = " open" if i < 2 else ""
        out += ('<details class="faqitem"' + op + '><summary><span class="faq-q">' + esc(q)
                + '</span><span class="faq-chev" aria-hidden="true"></span></summary>'
                '<div class="faq-a">' + esc(a) + '</div></details>')
    return '<div class="faq-list">' + out + '</div>'


def _reads_html() -> str:
    cols = ""
    for title, links in READS:
        lis = "".join('<li><a href="' + esc(u) + '" rel="noopener">' + esc(t) + '</a></li>' for t, u in links)
        cols += '<div><h3>' + esc(title) + '</h3><ul>' + lis + '</ul></div>'
    return '<div class="fw-reads">' + cols + '</div>'


def _cities_table(all_cities: list, rel: str) -> str:
    ranked = sorted(all_cities, key=lambda c: c["blend"]["score"], reverse=True)
    rows = ""
    for i, c in enumerate(ranked):
        b = c["blend"]
        rows += ('<tr><td>' + str(i + 1) + '</td>'
                 '<td><a href="' + rel + esc(c["id"]) + '/">' + esc(c["name"]) + '</a></td>'
                 '<td>' + esc(c.get("state", "")) + '</td>'
                 '<td>' + esc(b["band"]) + '</td>'
                 '<td><strong>' + str(b["score"]) + '</strong></td></tr>')
    return ('<table class="fw-table"><thead><tr><th scope="col">#</th><th scope="col">City</th>'
            '<th scope="col">State</th><th scope="col">Band</th><th scope="col">Score</th></tr></thead>'
            '<tbody>' + rows + '</tbody></table>')


BEACON_DUR = {"HIGH": "0.85s", "MODERATE": "1.3s", "LOW-MODERATE": "1.9s", "LOW": "2.8s"}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _num(x: float) -> str:
    """Match JS Number -> String (drops a trailing .0)."""
    return str(int(x)) if float(x).is_integer() else ("%g" % x)


def _fmt_date_js(generated_at: str) -> str:
    """Match the flow's fmtDate(): the IST (UTC+5:30) day/month/year of generated_at, e.g. '18 Jun 2026'.
    generated_at is minted in UTC; we shift +5:30 so India sees its own calendar date (a 23:59 UTC build
    is already the next day in IST). Byte-identical to fmtDate() in mobile.js/desktop.js/faq.js."""
    try:
        d = datetime.datetime.fromisoformat((generated_at or "").replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
        return "%d %s %d" % (d.day, _MONTHS[d.month - 1], d.year)
    except Exception:
        return ""


# --- redesign: segmented ring, legend, band chip, breeding-weather cards (mirror mobile.js + desktop.js) -
# Both flows now share these above-fold helpers: mobile _mobile_pre and desktop _desktop_pre both embed
# _risk_card / _weather_card, and BOTH mobile.js + desktop.js emit byte-identical markup. Each helper is
# above the fold for at least one flow, so hydration must be a no-op repaint (CLS 0) - edit ALL twins
# together (build_site.py + mobile.js + desktop.js).
BAND_TITLE = {"HIGH": "High", "MODERATE": "Moderate", "LOW-MODERATE": "Low-Moderate", "LOW": "Low"}
# Band phrase with a {d} driver placeholder; composed into the dialmean read-out (mirror the JS twins).
BAND_MEAN = {
    "HIGH": "high, driven by {d}",
    "MODERATE": "moderate, {d} leading",
    "LOW-MODERATE": "slightly raised, {d} leading",
    "LOW": "low, {d} highest",
}

# Per-disease IDENTITY colours (NOT the severity ramp) - used for the dial segments, the legend dots and
# the breakdown dots so the risk card reads consistently (Figma node 49-1303, measured from the render).
DISEASE = {"dengue": "#F1839D", "malaria": "#887ADE", "chikungunya": "#46CFE7", "typhoid": "#4681EF"}

# Red map-pin ("location drop") icon for the location card, matching the Figma (replaces the emoji).
# Kept byte-identical to the LOC_PIN string in assets/js/mobile.js (above the fold).
LOC_PIN = ('<svg class="locpin" viewBox="0 0 24 24" width="19" height="19" aria-hidden="true">'
           '<path fill="#F0493F" d="M12 2.2c-3.9 0-7 3.1-7 7 0 5 7 12.6 7 12.6s7-7.6 7-12.6c0-3.9-3.1-7-7-7z"/>'
           '<circle cx="12" cy="9.2" r="2.6" fill="#fff"/></svg>')

# Reviewer byline (E-E-A-T trust strip). REVIEWBY is the visible markup, byte-identical to the REVIEWBY
# constant in mobile.js + desktop.js (above the fold, parity-gated). REVIEWERS feeds the JSON-LD reviewedBy.
REVIEWERS = [
    {"name": "Dr. Nikita Toshi", "url": "https://pharmeasy.in/legal/editorial-policy/dr-nikita-toshi-2"},
    {"name": "Dr. Avinav Gupta", "url": "https://pharmeasy.in/legal/editorial-policy/dr-avinav-gupta-165"},
]
REVIEWBY = ('<p class="reviewline"><svg class="revico" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 4v5c0 4-3 7-7 8-4-1-7-4-7-8V7l7-4z"/><path d="M9 12l2 2 4-4"/></svg> Reviewed by <a href="https://pharmeasy.in/legal/editorial-policy/dr-nikita-toshi-2" target="_blank" rel="noopener">Dr. Nikita Toshi</a> and <a href="https://pharmeasy.in/legal/editorial-policy/dr-avinav-gupta-165" target="_blank" rel="noopener">Dr. Avinav Gupta</a></p>')

# Outline icons for the breeding-weather cards (droplet / rain cloud / water waves / sparkle). Kept
# byte-identical to the WX_* strings in assets/js/mobile.js (above the fold).
_WX_A = '<svg class="wxic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
WX_HUM = _WX_A + '<path d="M12 3.6c2.9 3.8 5.3 6.5 5.3 9.5a5.3 5.3 0 0 1-10.6 0c0-3 2.4-5.7 5.3-9.5Z"/></svg>'
WX_RAIN = _WX_A + '<path d="M7.6 14.4a3.5 3.5 0 0 1 .3-7 4.6 4.6 0 0 1 8.8 1.3 3.2 3.2 0 0 1 .2 5.4"/><path d="M8.4 17.4 7.5 20M12 17.4 11.1 20M15.6 17.4 14.7 20"/></svg>'
WX_TEMP = _WX_A + '<path d="M14 14.3V5.5a2 2 0 0 0-4 0v8.8a3.4 3.4 0 1 0 4 0Z"/><path d="M12 9.5v4.8"/></svg>'

# Period tabs above the dial. Only granularities present in grid["periods"] render (the data layer gates
# week/month by how many committed days exist); "today" is always the active default.
_PERIOD_LABELS = [("today", "Today"), ("week", "This week"), ("month", "This month")]


def _period_tabs(periods: list) -> str:
    avail = set(periods or ["today"])
    out = ""
    for key, label in _PERIOD_LABELS:
        if key != "today" or key not in avail:
            continue
        out += '<button class="ftab' + (" on" if key == "today" else "") + '" type="button">' + label + '</button>'
    return '<div class="ftabs">' + out + '</div>'


def _delta_arrow(delta) -> str:
    """Day-over-day arrow (vs yesterday). Empty unless a present, non-zero delta exists; up = risk rose
    (red), down = risk eased (green). Mirrors mobile.js deltaArrow(). Stays empty until history.json has
    a yesterday entry, so today it renders nothing."""
    if delta is None or delta == 0:
        return ""
    up = delta > 0
    return ('<span class="legtrend ' + ("up" if up else "down") + '">' + ("▲" if up else "▼")
            + " " + str(abs(delta)) + "</span>")


def _ring_svg(segs: list, score: int, size: int = 120) -> str:
    """The risk dial: a 270deg gauge FILLED to the overall score, the filled arc subdivided into one slot
    per disease sized by that disease's share of the summed scores, drawn in the disease IDENTITY colour
    with a fixed ~6deg white gap between slots, grey track behind. Centre = overall score (dark) + /100 +
    "Overall fever risk". Byte-identical to mobile.js ring(): rotations + dashes use %.1f == toFixed(1)."""
    sw = 12
    cx = size / 2.0
    r = (size - sw) / 2.0 - 1
    c = 2 * math.pi * r
    arc = 0.75
    fill_frac = (score / 100.0) * arc            # fraction of the full circle that is coloured
    total = sum(s for s, _ in segs) or 1
    # Rounded segment caps (per Figma): a round cap adds ~sw/2 of arc on each end. The dash is shortened
    # by GAP_PX (~= sw + a tiny ~1.5deg visible gap, matching the Figma's near-touching caps). NO nudge:
    # each segment starts at its slot start, so the FIRST segment starts at the track start (the "0"
    # position) with no leading grey gap; its round cap aligns with the grey track's round cap.
    GAP_PX = 13.5
    track, gap_all, off = "%.1f" % (arc * c), "%.1f" % (c - arc * c), "%.1f" % (c * 2)
    cs, rs = _num(cx), _num(r)
    track_c = ('<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="#e9eef5" stroke-width="'
               + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gap_all
               + '" transform="rotate(135 ' + cs + ' ' + cs + ')"/>')
    segs_html = ""
    cum = 0.0
    for s, col in segs:
        slot_frac = (s / total) * fill_frac
        dash_px = slot_frac * c - GAP_PX
        if dash_px < 0:
            dash_px = 0.0
        dash = "%.1f" % dash_px
        rot = "%.1f" % (135 + cum * 360)
        segs_html += ('<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="' + col
                      + '" stroke-width="' + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + dash + ' ' + off
                      + '" transform="rotate(' + rot + ' ' + cs + ' ' + cs + ')"/>')
        cum += slot_frac
    return ('<div class="ringwrap" style="width:' + str(size) + 'px;height:' + str(size) + 'px">'
            '<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 ' + str(size) + ' ' + str(size) + '">'
            + track_c + segs_html +
            '</svg><div class="num"><div class="numtop"><b>' + str(score) + '</b><span>/ 100</span></div>'
            '<em>Overall fever risk score</em></div></div>')


def _legend_rows(city: dict, diseases: list, cells_by: dict) -> str:
    """Per-disease legend beside the dial: identity-colour dot + "Name : score" + (dormant) day-over-day
    arrow, ordered by score descending. No emoji, no "Top concern" badge. Mirrors mobile.js legend."""
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    rows = ""
    for d in ordered:
        cell = cells_by[(cid, d["id"])]; col = DISEASE.get(d["id"], "#888")
        rows += ('<div class="legrow"><span class="legdot" style="background:' + col + '"></span>'
                 '<span class="legname">' + esc(d["label"]) + ' : <b>' + str(cell["score"]) + '</b><span class="legmax">/100</span></span></div>')
    return '<div class="leg">' + rows + '</div>'


def _band_chip(city: dict, info: str = "") -> str:
    # MODERATE uses the Figma gold; other bands keep the locked risk ramp. Beacon colour follows suit.
    band = city["blend"]["band"]
    if band == "MODERATE":
        bg, bd, bc = "#FFF8E3", "#F0D27A", "#F5B630"
    else:
        bg, bd, bc = RISK_SOFT.get(band, "#eee"), RISK.get(band, "#888"), RISK.get(band, "#888")
    beacon = ('<span class="beacon" style="--c:' + bc + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')
    return ('<div class="bandchip" style="background:' + bg + ';border-color:' + bd + '">'
            + beacon + BAND_TITLE.get(band, band) + ' fever risk in ' + esc(city["name"]) + ' ' + info + '</div>')


def _risk_card(city: dict, diseases: list, cells_by: dict, periods: list) -> str:
    """The mobile .card risk card, byte-identical to mobile.js riskCard(): period tabs, the segmented dial
    + per-disease legend, the band chip with the animated beacon, then a caption with Know-more + Share."""
    cid = city["id"]
    b = city["blend"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    segs = [(cells_by[(cid, d["id"])]["score"], DISEASE.get(d["id"], "#888")) for d in ordered]
    drv = next((d for d in diseases if d["id"] == b["driver"]), diseases[0])
    dlabel = esc(drv["label"])
    dscore = cells_by[(cid, b["driver"])]["score"]
    info = ('<span class="dialinfo"><button type="button" class="dialinfo-btn" data-act="dialInfo" aria-label="What this score means">i</button>'
            '<span class="dialtip"><span class="tiprow"><b>' + dlabel + ' (' + str(dscore) + ')</b> is the top fever here, making up about <b>80%</b> of this score. The other three add <b>20%</b>.</span>'
            '<span class="tipbands"><span class="tb"><i style="background:#3f9d6f"></i>Low 0-24</span><span class="tb"><i style="background:#c2a93a"></i>Low-Mod 25-44</span><span class="tb"><i style="background:#d98a2b"></i>Moderate 45-69</span><span class="tb"><i style="background:#d64545"></i>High 70-100</span></span><span class="tipcaret"></span></span></span>')
    mean = ('<p class="dialmean">Right now ' + esc(city["name"]) + "'s overall score is " + str(b["score"]) + '/100, '
            + BAND_MEAN.get(b["band"], "").replace("{d}", dlabel) + ". A daily look at local risk, not who's actually sick.</p>")
    return ('<div class="card riskcard">' + _period_tabs(periods) + '<div class="rtop">'
            + _ring_svg(segs, b["score"], 120) + _legend_rows(city, diseases, cells_by) + '</div>'
            + _band_chip(city, info) + mean
            + '<div class="rfoot"><span class="note">Scores calculated from weather conditions, Google search '
            'interest and PharmEasy lab signals. <button class="knowmore" data-act="openMethod">Know more</button></span>'
            '<button class="sharebtn" data-act="openShare">⤴ Share</button></div></div>')


def _weather_card(city: dict, date_str: str) -> str:
    """Weather conditions today: the live inputs that drive the mosquito weather sub-score -
    temperature (near the ~29C optimum, the dominant term), 14-day lagged rainfall (standing water) and
    humidity, each as an outline icon + "Label . value" + a short line. Mirrors mobile.js weatherCard().
    Above the fold, so byte-identical to the JS twin. The sub is DATED (AI-citability): a quotable,
    dated weather read the daily rebuild re-stamps."""
    w = city.get("weather") or {}
    temp, r14 = w.get("temp_mean_c"), w.get("rain_14d_mm")
    hum = w.get("humidity_pct")
    cards = [
        (WX_TEMP, "Temperature", ("n/a" if temp is None else str(_t_r(temp)) + "°C"), "Warmth near 29°C speeds up mosquito-borne fevers."),
        (WX_RAIN, "Rainfall", ("n/a" if r14 is None else str(_t_r(r14)) + "mm"), "Last 2-week total; leftover rainwater raises mosquito and typhoid risk."),
        (WX_HUM, "Humidity", ("n/a" if hum is None else str(_t_r(hum)) + "%"), "Mosquitoes survive longer in humid air."),
    ]
    cells = ""
    for ic, label, val, sub in cards:
        cells += ('<div class="wxcard"><div class="wxtop">' + ic + '<span class="wxhead">' + esc(label)
                  + '<span class="wxsep"></span><b>' + esc(val) + '</b></span></div>'
                  '<div class="wxsub">' + esc(sub) + '</div></div>')
    return ('<div class="card wxsec"><h2 class="sectiontitle">Weather conditions today</h2>'
            '<p class="sectionsub">Conditions as of ' + date_str + ' and what they mean for fever risk.</p>'
            '<div class="wxgrid">' + cells + '</div></div>')


def _mobile_pre(city: dict, diseases: list, cells_by: dict, date_str: str, periods: list) -> str:
    nm = esc(city["name"])
    return ('<div class="fw-pre fw-pre-m">'
            '<div class="hero"><h1>Live monsoon-fever risk for ' + nm + ' in <em>one score</em>.</h1>'
            '<p>Dengue, malaria, chikungunya and typhoid, blended from weather conditions, Google search interest and PharmEasy lab signals.</p></div>'
            '<button class="loccard" data-act="openCity">' + LOC_PIN + '<span class="locname">' + nm + '</span>'
            '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>'
            '<p class="searchnote loc-note">Updated ' + date_str + '. Available in select cities.</p>' + REVIEWBY
            + '<div class="wrap">' + _risk_card(city, diseases, cells_by, periods) + _weather_card(city, date_str) + '</div></div>')


SIGCOL = {"weather": [21, 172, 165], "trends": [124, 108, 214], "positivity": [54, 97, 176]}
SIGNAME = {"weather": "Weather conditions", "trends": "Google Search Interest", "positivity": "PharmEasy labs"}

# Per-signal breakdown metadata, byte-identical to the SIG map in assets/js/desktop.js (and mobile.js).
# The emoji bytes in the labels are intentional and must stay UTF-8-exact (the JS twin emits them raw).
SIG = {
    "weather": {"c": "#15ACA5", "bg": "#DBF3EF", "fg": "#0c5a55", "label": "\U0001F327 Weather", "what": "How much recent weather raises fever risk."},
    "trends": {"c": "#7C6CD6", "bg": "#ECE8FB", "fg": "#4b3fa3", "label": "\U0001F50D Search", "what": "How often people here search these symptoms."},
    "positivity": {"c": "#3661B0", "bg": "#E7EEFA", "fg": "#22468f", "label": "\U0001F9EA Lab", "what": "How many local tests come back positive."},
}
SHORT = {"positivity": "Lab", "weather": "Weather", "trends": "Search"}


def _level(v):
    """0-100 sub-score -> plain level word; SSR twin of mobile.js/desktop.js level()."""
    return "High" if v >= 67 else ("Moderate" if v >= 34 else "Low")


def _beacon(band: str) -> str:
    """The pulsing risk beacon, byte-identical to the flows' beacon()."""
    return ('<span class="beacon" style="--c:' + RISK.get(band, "#888")
            + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')


def _search_hero_d(city: dict, generated_at: str) -> str:
    """Byte-identical to desktop.js searchHero(c) at first render (state.comboOpen = false). H1 keeps the
    city; the hero gets the mobile vertical-fade gradient (CSS), a centered location pill (the mobile
    .loccard, reused as the city picker trigger via data-act="combo") with the existing desktop
    .combopanel dropdown anchored under it, plus a centered Updated/date note. SSR omits the " open"
    class the JS adds when state.comboOpen is true, so the first-paint byte string is exactly
    "combopanel". Edit BOTH this and searchHero() together (CLS 0)."""
    nm = esc(city["name"])
    return ('<section class="srch"><div class="srchin">'
            '<h1>Live monsoon-fever risk for ' + nm + ' in <em>one score</em>.</h1>'
            '<p class="subtitle">Dengue, malaria, chikungunya and typhoid, blended from weather conditions, Google Search interest and PharmEasy lab signals.</p>'
            '<div class="locwrap"><button class="loccard" data-act="combo">' + LOC_PIN + '<span class="locname">' + nm + '</span>'
            '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>'
            '<div class="combopanel"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>'
            '</div>'
            '<p class="searchnote loc-note">Updated ' + _fmt_date_js(generated_at) + '. Available in select cities.</p>' + REVIEWBY + '</div></section>')


def _sig_badge(delta) -> str:
    """Per-signal day-over-day badge, byte-identical to desktop.js sigBadge(). Empty unless a present,
    non-zero delta exists; sig_delta is absent on cells today, so this renders nothing (same as the JS)."""
    if not isinstance(delta, (int, float)) or isinstance(delta, bool) or delta == 0:
        return ""
    up = delta > 0
    arrow = ('<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"/></svg>'
             if up else
             '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7 17 17M17 9v8h-8"/></svg>')
    return ('<span class="sigbadge ' + ("up" if up else "down") + '" title="'
            + ("Rising vs yesterday" if up else "Easing vs yesterday") + '">' + arrow + '</span>')


def _contribs(cell: dict) -> dict:
    """Largest-remainder (Hamilton) apportionment of cell.score across the signals' weighted shares, so the
    per-signal contribution points sum EXACTLY to the displayed integer score in every mode (agree x1.08,
    disagree x0.96, forecast soft-knee taper absorbed). Byte-identical results to desktop.js contribs(cell)."""
    s = cell.get("signals", {}); w = cell.get("weights", {}); score = cell["score"]; order = ["positivity", "weather", "trends"]
    sh = {}; base = 0.0
    for k in order:
        v = s.get(k); sh[k] = 0.0 if v is None else (w.get(k, 0) / 100) * v; base += sh[k]
    pts = {"positivity": 0, "weather": 0, "trends": 0}; fr = {}
    if base > 0:
        used = 0
        for k in order:
            e = score * sh[k] / base; f = math.floor(e); pts[k] = f; fr[k] = e - f; used += f
        rem = score - used
        ranked = sorted(order, key=lambda k: (-fr[k], order.index(k)))
        for i in range(rem):
            pts[ranked[i]] += 1
    else:
        pts[order[0]] = score
    return pts


def _why_chip(cell: dict, kind: str) -> str:
    """Plain-language driver line for the highest / lowest disease chip (2nd line under the name in
    the breakdown header). Names signals by CONTRIBUTION order; byte-identical to the flows' whyChip."""
    s = cell.get("signals", {}); pts = _contribs(cell); order = ["positivity", "weather", "trends"]
    pres = [k for k in order if s.get(k) is not None]
    if not pres:
        return ""
    UP = {"weather": "strong weather", "positivity": "high positive tests", "trends": "high search interest"}
    UPM = {"weather": "moderate weather", "positivity": "some positive tests", "trends": "some search interest"}
    NOUN = {"weather": "weather", "positivity": "positive tests", "trends": "search"}
    def up(k): return UP[k] if _level(s[k]) == "High" else UPM[k]
    def cap(t): return t[:1].upper() + t[1:]
    if kind == "highest":
        byc = sorted(pres, key=lambda k: (-pts[k], order.index(k)))
        lead = [k for k in byc if _level(s[k]) != "Low"][:2]
        if not lead:
            return ""
        return cap(" + ".join(up(k) for k in lead)) + "."
    byv = sorted(pres, key=lambda k: (s[k], order.index(k)))
    weak = byv[0]; strong = byv[-1]
    if _level(s[strong]) == "Low":
        return ""
    return "Lower " + NOUN[weak] + " despite " + up(strong) + "."


TIPINFO = {
    "weather": "How much recent weather helps these fevers spread, on a 0-100 scale.",
    "trends": "How much people near you search these symptoms, vs what's normal for your city. 0-100.",
    "positivity": "It's the share of local tests coming back positive. For a full 100, dengue needs 25%, malaria 4%, chikungunya 15%, typhoid 45% - each fever has its own level.",
}


def _sig(meta: dict, cell: dict, k: str, pt) -> str:
    """One signal row, byte-identical to desktop.js sig(meta, cell, k, pt). Bar length = the signal's
    CONTRIBUTION points; the readout line shows a plain High/Moderate/Low level pill + the
    weight x raw-score derivation (the +N contribution stays top-right, split from the trend badge).
    meta.label carries the UTF-8 emoji RAW (no esc), matching the JS. Absent (forecast) lab -> muted
    no-data tile, no bar."""
    v = cell.get("signals", {}).get(k)
    if v is None:
        return ('<div class="sig"><div style="font-size:11.5px;font-weight:700;line-height:1.2;color:var(--pe-ink)">' + meta["label"] + '</div>'
                '<div style="font-size:10px;color:var(--pe-muted);margin-top:5px">No confirmed lab data yet, conditions-only forecast.</div></div>')
    bw = math.floor(pt / cell["score"] * 100 + 0.5)
    return ('<div class="sig"><div style="display:flex;align-items:center;gap:5px"><span style="flex:1;font-size:11.5px;font-weight:700;color:var(--pe-ink);line-height:1.2">' + meta["label"] + '</span><span style="font-size:15px;font-weight:800;color:' + meta["c"] + '">+' + str(pt) + '</span></div>'
            '<div style="display:flex;align-items:center;gap:6px;margin:5px 0 2px"><span style="font-size:9.5px;font-weight:800;letter-spacing:.3px;line-height:1.3;padding:1px 7px;border-radius:999px;background:' + meta["bg"] + ';color:' + meta["fg"] + '">' + _level(v) + '</span>' + _sig_badge((cell.get("sig_delta") or {}).get(k)) + '</div>'
            '<div style="font-size:10px;color:var(--pe-muted-2);font-weight:600;margin:0 0 4px;white-space:nowrap">' + str(cell["weights"][k]) + '% weight × ' + str(v) + '/100 <span class="dialinfo"><button type="button" class="dialinfo-btn" data-act="dialInfo" aria-label="What this number means">i</button><span class="dialtip">' + TIPINFO[k] + '<span class="tipcaret"></span></span></span></div>'
            '<div class="track" style="height:6px"><div class="fill" style="width:' + str(bw) + '%;background:' + meta["c"] + '"></div></div>'
            '<div style="font-size:10px;color:var(--pe-muted);line-height:1.4;margin-top:6px">' + meta["what"] + '</div></div>')


def _breakdown_card_d(city: dict, diseases: list, cells_by: dict) -> str:
    """The horizontal 3-signal breakdown, one accordion per disease, byte-identical to desktop.js
    breakdownCard(c). Diseases sorted by cell score descending (stable, == orderedDiseases). The driver
    disease (city blend driver) is the pre-opened accordion, matching the JS boot (state.expanded =
    blend.driver). cell["note"] and d["emoji"]/d["label"] are emitted RAW (no esc), matching the JS."""
    cid = city["id"]
    driver = city["blend"]["driver"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    hi_id = ordered[0]["id"]; lo_id = ordered[-1]["id"]
    spread = cells_by[(cid, hi_id)]["score"] - cells_by[(cid, lo_id)]["score"]
    ORDER = ["positivity", "weather", "trends"]
    accs = ""
    for d in ordered:
        cell = cells_by[(cid, d["id"])]
        open_ = driver == d["id"]
        pts = _contribs(cell)
        order = sorted(ORDER, key=lambda k: (-pts[k], ORDER.index(k)))
        rows = ""
        sumparts = []
        for k in order:
            rows += _sig(SIG[k], cell, k, pts[k])
            if cell.get("signals", {}).get(k) is not None:
                sumparts.append(SHORT[k] + " " + str(pts[k]))
        body = ('<div class="accbody">' + rows
                + '<p class="accnote"><span style="display:block;font-weight:700;margin:0 0 4px">'
                + " + ".join(sumparts) + " = " + str(cell["score"]) + '</span>' + cell["note"] + '</p></div>')
        kind = "highest" if (spread > 0 and d["id"] == hi_id) else ("lowest" if (spread > 0 and d["id"] == lo_id) else "")
        why = _why_chip(cell, kind) if kind else ""
        name_html = ('<span class="nmwrap"><span class="name">' + d["label"] + '</span><span class="whysub">' + why + '</span></span>') if why else ('<span class="name">' + d["label"] + '</span>')
        accs += ('<div class="acc' + (" open" if open_ else "") + '"><button class="acchead" data-act="expand" data-id="' + d["id"] + '">'
                 '<span class="emoji">' + d["emoji"] + '</span>' + name_html
                 + '<span class="dot" style="background:' + (DISEASE.get(d["id"], "#888")) + '"></span><span class="sc">' + str(cell["score"]) + '</span>'
                 '<span class="chev">▾</span></button>' + body + '</div>')
    return ('<div class="card whycard"><h2 class="sechead">Why this score?</h2>'
            '<p class="secsub">Tap a disease to see how each signal builds the score. <button class="knowmore" data-act="openMethod">Know more</button></p>' + accs + '</div>')


def _why_section_d(city: dict, diseases: list, cells_by: dict) -> str:
    """Desktop s-why above-fold twin. Byte-identical to desktop.js whySection(c) ("Why this score?" WITH
    the question mark). The title + subtitle now live INSIDE the card (see _breakdown_card_d). Now lives
    in the first fold (right rail of the 3-col shell)."""
    return ('<section id="s-why">'
            + _breakdown_card_d(city, diseases, cells_by) + '</section>')


def _week_section_d(city: dict, diseases: list, cells_by: dict, periods: list) -> str:
    """Desktop s-week above-fold twin. REUSES _risk_card verbatim (the mobile-proven proportional identity
    dial + legend + band chip + period tabs), wrapped in the desktop section. The outside title is removed
    (matches the reference snap); the TOC link "Overall fever risk" -> #s-week still works. Byte-identical
    to desktop.js weekSectionD(c, b)."""
    return ('<section id="s-week">'
            + _risk_card(city, diseases, cells_by, periods) + '</section>')


def _desktop_pre(city: dict, diseases: list, cells_by: dict, generated_at: str, periods: list) -> str:
    """Desktop seamless first paint. Server-render .srch + .shell{.toc + s-week + s-why} so it is
    byte-identical to what desktop.js render() paints from the inlined seed; hydration is then a no-op
    repaint over identical above-fold DOM (kills the desktop CLS). s-why (the breakdown) is now in the
    first fold (3-col shell right rail), so the SSR twin extends through it. The .fw-below SEO block
    underneath stays for crawlers / no-JS. Mirrors the mobile _mobile_pre / _risk_card pattern. Gated
    .fw-pre-d. The first JS-only bytes are '<div class="main">'."""
    # NOTE: this TOC must stay byte-identical to desktop.js render()'s .toc so desktop hydration is a
    # no-op repaint (CLS 0). Edit BOTH together. The href target set MUST equal desktop.js spyScroll()'s
    # ids array, with one section id per TOC link and vice-versa (s-method is reached via "Know more",
    # and s-reads renders below but is intentionally NOT a TOC target).
    toc = ('<aside class="toc"><h2>Quick Links</h2>'
           '<a class="cur" href="#s-week">Overall fever risk</a><a href="#s-why">Why this score?</a>'
           '<a href="#s-weather">Weather conditions today</a><a href="#s-do">What you can do</a>'
           '<a href="#s-trend">This year vs last year</a><a href="#s-other">What is happening in other cities?</a>'
           '<a href="#s-faq">Common questions</a></aside>')
    return ('<div class="fw-pre fw-pre-d">' + _search_hero_d(city, generated_at)
            + '<div class="shell">' + toc
            + _week_section_d(city, diseases, cells_by, periods)
            + _why_section_d(city, diseases, cells_by) + '</div></div>')


# --- "This monsoon vs last year" trend module (static SSR; mirrors assets/js/trend.js) -----------
# The series math below is intentionally identical to assets/js/trend.js realSeries()/build(). Edit BOTH
# and keep them in sync. ALL trend data is REAL (from data/archive/trend_series.json); there is NO mock - a
# metric with no usable real data bakes an honest "coming soon" empty state. Here we bake only the static
# "Overall" chart + verdict for crawlers and no-JS; the JS widget owns the interactive flows.
TREND_NW = 22  # weeks in the season (1 Jun .. 30 Oct)
TREND_MONTHS = ["Jun", "Jul", "Aug", "Sep", "Oct"]  # equidistant HTML axis labels (mirrors trend.js MONTHS_ROW)
TREND_ZONES = [(70, 100, "#E4572E"), (45, 69, "#E8923A"), (25, 44, "#C7A93C"), (0, 24, "#2FA66F")]
_TW, _TH, _TPADL, _TPADR, _TPADT, _TPADB = 340, 110, 26, 12, 6, 4  # compact; left gutter for y-axis; HTML month labels; y zooms (see _trend_chart_static)


def _t_r(x) -> int:
    return int(math.floor((x or 0) + 0.5))


def _t_clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _t_band(score: int) -> str:
    return "HIGH" if score >= 70 else "MODERATE" if score >= 45 else "LOW-MODERATE" if score >= 25 else "LOW"


def _t_mean(cells: list, key: str):
    vals = [c.get("signals", {}).get(key) for c in cells]
    vals = [v for v in vals if v is not None]
    return _t_r(sum(vals) / len(vals)) if vals else None


def _t_real_series(blk: dict, asOf: int) -> dict:
    """REAL last-year + this-year series from the committed archive block ({ly, ty}); mirror of trend.js
    realSeries(). Peak is the real last-year MAX. The this-year line may trail the current week by one (if the
    daily archive cron has not extended it yet); we chart up to the last real point (cur) so a short ty degrades
    to a real partial line, never a fabricated one."""
    ly, ty = blk["ly"], blk["ty"]
    cur = asOf if asOf < len(ty) - 1 else len(ty) - 1
    a, b = ty[cur], ly[cur]
    delta = _t_r((a - b) / b * 100) if b > 0 else 0
    slope = ty[cur] - ty[cur - 1] if cur >= 1 else 0
    return {"now": a, "series": ty, "last": ly, "delta": delta, "slope": slope, "peak": max(ly), "avail": True}


def _trend_series(city: dict, cells: list, generated_at: str, archive_city: dict | None = None) -> dict:
    cid = city["id"]
    blend = city["blend"]
    ga = generated_at or ""
    try:  # IST (UTC+5:30) date parts, matching trend.js build(); keeps the "you are here" week in sync with the India date
        _gi = datetime.datetime.fromisoformat(ga.replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
        gy, gm, gd = _gi.year, _gi.month, _gi.day
    except Exception:
        gy, gm, gd = 2026, 6, 1
    as_of = _t_clamp((datetime.date(gy, gm, gd) - datetime.date(gy, 6, 1)).days // 7, 0, TREND_NW - 1)
    labs_now = _t_mean(cells, "positivity")
    # ALL series are REAL (from the committed archive). A metric with no usable real data -> {"avail": False}
    # (honest "coming soon"); there is NO synthetic fallback. The gate is LENIENT on the this-year length (ty
    # may trail asOf by a week before the daily cron extends it; _t_real_series charts up to the last real
    # point), and the last-year line (ly) must be the full 22-week season. Mirrors trend.js build().
    def _lenty(b):
        return bool(b) and bool(b.get("ty")) and 1 <= len(b["ty"]) <= as_of + 1
    weather_blk = (archive_city or {}).get("weather") if archive_city else None
    search_blk = (archive_city or {}).get("search") if archive_city else None
    overall_blk = (archive_city or {}).get("overall") if archive_city else None
    w_real = bool(weather_blk) and len(weather_blk.get("ly", [])) == TREND_NW and _lenty(weather_blk)
    s_real = bool(search_blk) and len(search_blk.get("ly", [])) == TREND_NW and _lenty(search_blk)
    o_real = bool(overall_blk) and len(overall_blk.get("ly", [])) == TREND_NW and _lenty(overall_blk)
    # Labs: real when the archive's last-year line is full-season and not all-zero; this-year carries the live
    # mean flat across the weeks if its archive ty is short/missing (real-derived, never synthetic).
    labs_blk = (archive_city or {}).get("labs") if archive_city else None
    labs_ly = labs_blk.get("ly") if labs_blk else None
    labs_has_ly = bool(labs_ly) and len(labs_ly) == TREND_NW and any(v > 0 for v in labs_ly)
    labs_ty = labs_blk.get("ty") if (labs_blk and labs_blk.get("ty")) else []
    labs_ty_ok = bool(labs_ty) and 1 <= len(labs_ty) <= as_of + 1 and all(v is not None for v in labs_ty)
    if labs_ty_ok:
        labs_ty_final = labs_ty
    elif labs_now is not None:
        labs_ty_final = [labs_now] * (as_of + 1)
    else:
        labs_ty_final = None
    labs_real = labs_has_ly and labs_ty_final is not None
    metrics = {
        "overall": _t_real_series(overall_blk, as_of) if o_real else {"avail": False},
        "weather": _t_real_series(weather_blk, as_of) if w_real else {"avail": False},
        "search": _t_real_series(search_blk, as_of) if s_real else {"avail": False},
        "labs": _t_real_series({"ly": labs_ly, "ty": labs_ty_final}, as_of) if labs_real else {"avail": False},
    }
    # No real Overall line -> the whole widget is "unavailable" (honest empty state, never fabricated). In
    # production this is unreachable: the build asserts every city has a real overall line before writing pages.
    if not metrics["overall"].get("avail"):
        return {"city": city["name"], "cityId": cid, "asOf": as_of, "metrics": metrics, "unavailable": True}
    ov = metrics["overall"]
    level = "below" if ov["delta"] <= -6 else ("above" if ov["delta"] >= 6 else "inline")
    direction = "rising" if ov["slope"] >= 2 else ("falling" if ov["slope"] <= -2 else "steady")
    vtext = {"below": "Tracking below last year so far", "above": "Running higher than last year",
             "inline": "About the same as last year so far"}[level]
    if level == "above":
        tail = ", and still rising" if direction == "rising" else (", but easing" if direction == "falling" else "")
    elif level == "below":
        tail = ", but creeping up" if direction == "rising" else (", and still easing" if direction == "falling" else "")
    else:
        tail = ", edging up" if direction == "rising" else (", edging down" if direction == "falling" else "")
    if level == "inline" and abs(ov["delta"]) < 3:
        chip = "~0%"
    else:
        chip = ("+" if ov["delta"] > 0 else ("-" if ov["delta"] < 0 else "")) + str(abs(ov["delta"])) + "%"
    # Peak month: name the month of the actual peak week in the REAL overall.ly (1 Jun + 7*idx).
    peak_idx = max(range(TREND_NW), key=lambda w: overall_blk["ly"][w])
    peak_when = " in " + _MONTHS[(datetime.date(gy, 6, 1) + datetime.timedelta(days=7 * peak_idx)).month - 1] + "."
    context = "Last year peaked at " + str(ov["peak"]) + " (" + _t_band(ov["peak"]) + ")" + peak_when
    return {"city": city["name"], "cityId": cid, "asOf": as_of, "metrics": metrics, "level": level,
            "dir": direction, "verdict": vtext + tail, "chip": chip, "tone": level, "context": context}


def _trend_caption(model: dict, metric: str) -> str:
    m = model["metrics"][metric]
    if not m.get("avail"):
        return "Lab positivity history is not available for " + model["city"] + " yet."
    lvl = "below" if m["delta"] <= -6 else ("above" if m["delta"] >= 6 else "inline")
    if metric == "overall":
        return {"rising": "Risk is climbing as the monsoon builds.", "falling": "Risk is easing as rainfall tapers.",
                "steady": "Risk is holding close to last year."}[model["dir"]]
    if metric == "weather":
        return {"below": "Weather conditions are running below last year.",
                "above": "Weather conditions are running hotter than last year.",
                "inline": "Weather conditions are tracking last year."}[lvl]
    if metric == "search":
        return {"below": "Public concern is below last year's level.",
                "above": "Public concern is above last year's level.",
                "inline": "Public concern is tracking last year."}[lvl]
    return {"below": "Positivity is tracking below last year.", "above": "Positivity is running above last year.",
            "inline": "Positivity is tracking last year closely."}[lvl]


def _tX(i):
    return _TPADL + i / (TREND_NW - 1) * (_TW - _TPADL - _TPADR)


def _tY(v, ymax=100):
    return _TPADT + (1 - _t_clamp(v, 0, ymax) / float(ymax)) * (_TH - _TPADT - _TPADB)


def _tf(n):
    return round(n * 10) / 10


def _t_linepath(arr, ymax=100) -> str:
    return "".join(("L" if i else "M") + str(_tf(_tX(i))) + " " + str(_tf(_tY(arr[i], ymax))) for i in range(len(arr)))


def _trend_chart_static(model: dict) -> str:
    """Static 'Overall' SVG, visually mirroring assets/js/trend.js chartSVG (need not be pixel-exact:
    the JS replaces it on hydration; this is the crawlable / no-JS render). The y-axis zooms to the data
    (top = peak + 15%, capped 100); Overall peaks ~90 so it stays ~0-100 and keeps the risk zones."""
    m = model["metrics"]["overall"]
    col = RISK[_t_band(m["now"])]
    dmax = max(m["peak"], max(m["series"]) if m["series"] else 0)
    ymax = min(100, max(45, int(math.floor(dmax * 1.15 + 0.5))))
    base_y = _tY(0, ymax)
    zones = "".join('<rect x="%d" y="%s" width="%d" height="%s" fill="%s" opacity="0.06"/>'
                    % (_TPADL, _tf(_tY(min(z[1], ymax), ymax)), _TW - _TPADL - _TPADR,
                       _tf(_tY(z[0], ymax) - _tY(min(z[1], ymax), ymax)), z[2])
                    for z in TREND_ZONES if z[0] < ymax)
    ly_line = _t_linepath(m["last"], ymax)
    area = ("M" + str(_tf(_tX(0))) + " " + str(_tf(base_y)) + "L" + ly_line[1:]
            + "L" + str(_tf(_tX(TREND_NW - 1))) + " " + str(_tf(base_y)) + "Z")
    ly_area = '<path d="' + area + '" fill="#9fb0c4" opacity="0.16"/>'
    ly_stroke = '<path d="' + ly_line + '" fill="none" stroke="#aab6c6" stroke-width="1.6" stroke-linejoin="round"/>'
    ty = m["series"]
    ty_line = ('<path d="' + _t_linepath(ty, ymax) + '" fill="none" stroke="' + col
               + '" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>') if len(ty) > 1 else ""
    dot = ('<circle cx="' + str(_tf(_tX(len(ty) - 1))) + '" cy="' + str(_tf(_tY(ty[-1], ymax)))
           + '" r="4.2" fill="' + col + '" stroke="#fff" stroke-width="2.2"/>')
    # Y-axis ticks (0 / mid / top) in the left gutter + faint gridlines; mirrors trend.js chartSVG.
    fs = 8.5
    yaxis = ""
    for tv in (0, _t_r(ymax / 2.0), ymax):
        yv = _tY(tv, ymax)
        if tv > 0:
            yaxis += ('<line x1="' + str(_TPADL) + '" y1="' + str(_tf(yv)) + '" x2="' + str(_TW - _TPADR)
                      + '" y2="' + str(_tf(yv)) + '" stroke="#eef1f5" stroke-width="1"/>')
        yaxis += ('<text x="' + str(_TPADL - 5) + '" y="' + str(_tf(yv + fs * 0.35))
                  + '" text-anchor="end" font-size="' + str(fs) + '" font-weight="600" fill="#9aa6b1">' + str(tv) + '</text>')
    # Spaced data labels: you-are-here (this year, in colour) + a few last-year reference points.
    nv = ty[-1]
    labels = ('<text x="' + str(_tf(_tX(len(ty) - 1))) + '" y="' + str(_tf(max(fs + 2, _tY(nv, ymax) - 7)))
              + '" text-anchor="middle" font-size="' + str(fs + 0.5) + '" font-weight="800" fill="' + col + '">' + str(nv) + '</text>')
    for lx in (6, 13, 19):
        if abs(lx - model["asOf"]) < 2:
            continue
        lv = m["last"][lx]
        labels += ('<text x="' + str(_tf(_tX(lx))) + '" y="' + str(_tf(max(fs, _tY(lv, ymax) - 5)))
                   + '" text-anchor="middle" font-size="' + str(fs - 1) + '" font-weight="600" fill="#8995a3">' + str(lv) + '</text>')
    # Month labels are HTML (.fwtrend-months); the SVG only carries the baseline axis rule.
    axis = ('<line x1="' + str(_TPADL) + '" y1="' + str(_tf(base_y)) + '" x2="' + str(_TW - _TPADR) + '" y2="'
            + str(_tf(base_y)) + '" stroke="#edf0f5" stroke-width="1"/>')
    return ('<svg viewBox="0 0 ' + str(_TW) + ' ' + str(_TH) + '" class="fwtrend-svg"'
            ' role="img" aria-label="Overall risk this year versus last year">'
            + zones + yaxis + ly_area + ly_stroke + ty_line + dot + labels + axis + '</svg>')


def _trend_html(city: dict, diseases: list, cells_by: dict, generated_at: str, archive_city: dict | None = None,
                disease: dict | None = None) -> str:
    cid = city["id"]
    cells = [cells_by[(cid, d["id"])] for d in diseases if (cid, d["id"]) in cells_by]
    model = _trend_series(city, cells, generated_at, archive_city)
    # On a disease page the trend is scoped to THAT disease (overall line = its own weekly score), so the
    # title + the "Overall" tab are labeled with the disease to make that explicit. Mirrors trend.js.
    _ttl = (("This monsoon vs last for " + esc(disease["label"]) + " in " + esc(city["name"])) if disease
            else ("This monsoon vs last in " + esc(city["name"])))
    _overall_lbl = disease["label"] if disease else "Overall"
    # No real Overall line -> honest "coming soon" empty state (mirrors trend.js unavailableCard). Unreachable
    # in production: page() asserts every city has a real overall line before any page is written.
    if model.get("unavailable"):
        return ('<section id="s-trend" class="fwtrend-host">'
                '<div class="card fwtrend open" data-metric="overall">'
                '<div class="fwtrend-head"><div>'
                '<h2 class="fwtrend-title">' + _ttl + '</h2></div>'
                '<button class="fwtrend-toggle" data-tact="toggle" aria-expanded="true"><span class="t">Hide</span>'
                '<span class="chev" aria-hidden="true"></span></button></div>'
                '<div class="fwtrend-soon"><span class="i">📈</span><b>Season trend coming soon</b>'
                '<p>We will chart this year versus last year for ' + esc(city["name"]) + ' here as soon as the data is available.</p></div></div></section>')
    col = RISK[_t_band(model["metrics"]["overall"]["now"])]
    tone = model["tone"]
    tone_icon = {"below": "▼", "above": "▲", "inline": "≈"}[tone]
    tabs = ""
    for k, lbl in (("overall", _overall_lbl), ("weather", "Weather"), ("search", "Searches"), ("labs", "Labs")):
        on = k == "overall"
        avail = model["metrics"][k].get("avail")
        tabs += ('<button class="fwtrend-tab' + (" on" if on else "") + ("" if avail else " soon")
                 + '" data-tact="metric" data-metric="' + k + '"' + (' aria-current="true"' if on else "")
                 + '>' + esc(lbl) + '</button>')
    months = '<div class="fwtrend-months">' + "".join('<span>' + m + '</span>' for m in TREND_MONTHS) + '</div>'
    # Title + Hide toggle INSIDE the card (matches the mobile twin + the desktop JS branch); the flow JS
    # re-renders this. Below the fold, so no parity impact (the trend host is a JS-only section).
    return ('<section id="s-trend" class="fwtrend-host">'
            '<div class="card fwtrend open" data-metric="overall">'
            '<div class="fwtrend-head"><div>'
            '<h2 class="fwtrend-title">' + _ttl + '</h2></div>'
            '<button class="fwtrend-toggle" data-tact="toggle" aria-expanded="true"><span class="t">Hide</span>'
            '<span class="chev" aria-hidden="true"></span></button></div>'
            '<div class="fwtrend-verdict"><span class="fwtrend-vicon ' + tone + '">' + tone_icon + '</span>'
            '<span class="fwtrend-vtext">' + esc(model["verdict"]) + '</span>'
            '<span class="fwtrend-chip ' + tone + '">' + esc(model["chip"]) + '</span></div>'
            '<p class="fwtrend-context">' + esc(model["context"]) + '</p>'
            '<div class="fwtrend-body"><div class="fwtrend-tabs" role="tablist">' + tabs + '</div>'
            '<div class="fwtrend-chartwrap">' + _trend_chart_static(model) + '<div class="fwtrend-tip" hidden></div></div>'
            + months +
            '<p class="fwtrend-axiscap">Vertical scale starts at 0; higher means greater risk.</p>'
            '<div class="fwtrend-legend"><span><i class="ly"></i>Last year</span>'
            '<span><i class="ty" style="background:' + col + '"></i>This year</span>'
            '<span class="here"><i class="dot" style="background:' + col + '"></i>You are here</span></div>'
            '<p class="fwtrend-caption">' + esc(_trend_caption(model, "overall")) + '</p>'
            '<p class="fwtrend-sources">Sources: NOAA CPC, NASA POWER, Google Trends, PharmEasy labs. A risk indicator, not a case count.</p>'
            '</div></div></section>')


# --- Phase-0 SEO blocks: fever tests / season insight / nearby cities ----------------------------
# SSR versions here; the interactive flows render their own versions in mobile.js (testCard/seasonCard/
# nearbyHtml) and desktop.js (testsSection/seasonSection/nearbyHtml). The FACTS must stay consistent
# across all three: same test names, same +/-8 season thresholds, same distance math with the same
# 0.00872664626 (pi/360... avg-lat radians) constant and id tie-break. Edit all three together.
# GATE (2026-07-08): the fever-tests block is BUILT but held back pending the medical/counsel review
# planned for next week. To ship it, flip this to True TOGETHER with FW_TESTS_ON in mobile.js and
# desktop.js, re-add '<a href="#s-tests">Fever tests</a>' after "What you can do" in the _desktop_pre
# TOC AND desktop.js render() (byte-identical twins), and put "s-tests" back in desktop.js spyScroll ids.
FW_TESTS_ENABLED = False
FW_TESTS = [
    ("🦟", "Dengue", "NS1 antigen (first few days) or IgM antibody test",
     "A CBC alongside tracks platelets, which dengue can lower."),
    ("🦟", "Malaria", "Peripheral blood smear or a rapid antigen test",
     "Identifies the parasite and its species."),
    ("🦟", "Chikungunya", "IgM antibody test; RT-PCR in the first week",
     "Lingering joint pain is its signature."),
    ("💧", "Typhoid", "Blood culture (definitive); Widal is the common screen",
     "From contaminated food or water, so it builds slowly."),
]


def _tests_band_line(nm: str, band: str) -> str:
    if band == "HIGH":
        return ("With " + nm + " elevated right now, do not sit on a fever - if it lasts past 2 days, "
                "a test plus a doctor visit is the sensible move.")
    if band == "MODERATE":
        return "At MODERATE, the practical rule of thumb: a fever that lasts more than 2 days is worth testing."
    return ("Even at lower risk, a fever that drags past 2 to 3 days or feels severe deserves a test "
            "and a doctor's opinion.")


def _tests_sec(city: dict, generated_at: str) -> str:
    """Crawler-readable fever-tests section (which test confirms which fever + a band-tied nudge).
    Careful copy: informational, doctor-deferring, risk-indicator framing - not diagnostic advice."""
    b = city["blend"]; nm = city["name"]
    lead = ("As of " + _fmt_date_js(generated_at) + ", " + nm + "'s overall risk is " + str(b["score"])
            + "/100 (" + b["band"] + "). If a fever shows up and sticks around, testing is how it gets "
            "identified - here is what doctors typically order.")
    rows = "".join('<li><strong>' + esc(e + " " + t) + '</strong> - ' + esc(w) + '. <em>' + esc(n) + '</em></li>'
                   for e, t, w, n in FW_TESTS)
    return ('<section><h2>Fever tests: which test confirms what?</h2>'
            '<p>' + esc(lead) + '</p><ul>' + rows + '</ul>'
            '<p>' + esc(_tests_band_line(nm, b["band"])) + '</p>'
            '<p><a class="fw-cta" href="' + esc(city.get("diag_url") or (DIAG_DEFAULT + DIAG_SUFFIX))
            + '">Book a fever panel test in ' + esc(nm) + '</a></p>'
            '<p class="microcopy">Fever Watch is a risk indicator, not a diagnosis. Which test fits, '
            'and what a result means, is a doctor\'s call.</p></section>')


def _season_bits(archive_city: dict | None, generated_at: str) -> dict | None:
    """Season-comparison facts from the archive (overall ly vs ty). None when the slice is absent or
    malformed - the section is then omitted, honest like the trend fallback ladder. Number-for-number
    twin of the JS seasonBits(): same index, same first-max peak, same year derivation (IST year - 1)."""
    ov = (archive_city or {}).get("overall") or {}
    ly, ty = ov.get("ly") or [], ov.get("ty") or []
    if len(ly) != TREND_NW or not ty:
        return None
    i = min(len(ty) - 1, TREND_NW - 1)
    ty_now, ly_same = ty[i], ly[i]
    diff = ty_now - ly_same
    phrase = "running above" if diff >= 8 else ("running below" if diff <= -8 else "about level with")
    pk = 0
    for j in range(TREND_NW):
        if ly[j] > ly[pk]:
            pk = j
    try:
        d0 = datetime.datetime.fromisoformat((generated_at or "").replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
        ly_year = d0.year - 1
    except Exception:
        ly_year = 2025
    pdate = datetime.date(ly_year, 6, 1) + datetime.timedelta(days=7 * pk)
    peak = str(pdate.day) + " " + _MONTHS[pdate.month - 1] + " " + str(pdate.year)
    return {"ty": ty_now, "ly": ly_same, "phrase": phrase, "peak": peak}


def _season_sec(city: dict, archive_city: dict | None, generated_at: str) -> str:
    s = _season_bits(archive_city, generated_at)
    if not s:
        return ""
    nm = city["name"]
    return ('<section><h2>How this monsoon compares for ' + esc(nm) + '</h2>'
            '<p>As of ' + esc(_fmt_date_js(generated_at)) + ', ' + esc(nm) + '\'s overall fever signal is '
            + str(s["ty"]) + '/100 - ' + s["phrase"] + ' the same week last monsoon (' + str(s["ly"])
            + '/100). Last season\'s high point came in the week of ' + esc(s["peak"]) + '. Rain drives '
            'this number, so the picture shifts as the season moves - we refresh it daily.</p></section>')


def _nearest_cities(city: dict, all_cities: list, n: int = 5) -> list:
    """Nearest cities by equirectangular distance (dx scaled by cos of the average latitude). Tie-break
    by id so Python and JS order identically."""
    la1, lo1 = float(city.get("lat") or 0), float(city.get("lon") or 0)
    out = []
    for c in all_cities:
        if c["id"] == city["id"]:
            continue
        la2, lo2 = float(c.get("lat") or 0), float(c.get("lon") or 0)
        dx = (lo2 - lo1) * math.cos((la1 + la2) * 0.00872664626)
        dy = la2 - la1
        out.append((dx * dx + dy * dy, c["id"], c))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out[:n]]


# --- SEO Phase 1: per-city per-disease pages (/fever-watch/{city}/{disease}/) --------------------
# Children of the city hub, one per disease. The hub (disease=None) code path below is UNTOUCHED; all
# disease-scoped SSR lives in these helpers so the hub stays byte-identical (parity-gated).
#
# GATE (2026-07-11): disease-page EMISSION is held behind FW_DISEASE_PAGES_ENABLED. Default OFF = the build
# writes only the landing + 209 hubs (byte-identical to today, 210 pages). Set the env var FW_DISEASE_PAGES=1
# to build all 836 children (for LOCAL review + the disease parity fixtures) without editing code; when the
# W2b JS is signed off + the About/early-estimate copy clears counsel, flip the default here (or set the env
# in the deploy workflow) to ship. It MUST stay off in production until the JS FW.disease first paint ships,
# else a JS user on a child page repaints the hub over the disease SSR. Same safety idea as FW_TESTS_ENABLED.
FW_DISEASE_PAGES_ENABLED = os.environ.get("FW_DISEASE_PAGES", "").strip().lower() in ("1", "true", "yes")

# Disease-family weather mechanism line (module 4). ASCII hyphens only.
DIS_MECH = {
    "mosquito": "Mosquitoes breed in the standing water left after rain and bite most around 29C, so warm, "
                "wet spells lift this score and drier or cooler ones ease it.",
    "waterborne": "Typhoid is waterborne, so heavy rain that can wash contamination into the water supply "
                  "drives this score more than temperature does.",
}

# About-{disease}: 2-sentence, non-diagnostic, doctor-deferring blurb + the locked "full guide" blog link
# (user decision 2026-07-11). PENDING medical/counsel sign-off in the ~2026-07-15 review bundle - keep the
# copy factual and non-diagnostic; do not add symptoms-as-advice or case language.
DIS_ABOUT = {
    "dengue": ("Dengue is a viral fever spread by the day-biting Aedes mosquito, which breeds in the clean "
               "standing water that collects in and after the monsoon. It is a risk that rises with the rains; "
               "most people recover with rest and fluids, but a fever that worsens or persists needs a doctor.",
               "https://pharmeasy.in/blog/5-ways-to-avoid-dengue-fever/"),
    "malaria": ("Malaria is caused by a parasite carried by the night-biting Anopheles mosquito, and tends to "
                "climb through the rainy months. It is treatable, and testing early helps identify the parasite; "
                "a fever with chills is a reason to see a doctor.",
                "https://pharmeasy.in/blog/types-of-malaria-symptoms-causes-and-treatment/"),
    "chikungunya": ("Chikungunya is a viral fever spread by the same Aedes mosquito as dengue, so it shares the "
                    "monsoon timing. Its hallmark is fever with joint pain that can linger; care is supportive, so "
                    "rest, fluids and a doctor's guidance matter.",
                    "https://pharmeasy.in/blog/vaccine-viral-fever-causes-symptoms-and-treatment-options/"),
    "typhoid": ("Typhoid is a bacterial infection spread through food and water contaminated during the monsoon, "
                "not by mosquitoes. It tends to build gradually; safe drinking water, hygiene and timely testing "
                "are the practical defences, and a sustained fever is worth a doctor's visit.",
                "https://pharmeasy.in/blog/typhoid-causes-symptoms-and-treatment/"),
}

# Confidence-chip colours (early-estimate lead darkened to AA per the design review).
_CONF_LAB = ("#E4F4EC", "#1c7a4f")
_CONF_EST = ("#FBF0E2", "#96520F")


def _dis_by_id(diseases: list, did: str) -> dict:
    return next((d for d in diseases if d["id"] == did), diseases[0])


def _dis_family(diseases: list, did: str) -> str:
    return _dis_by_id(diseases, did).get("family", "mosquito")


def _disease_ring(score: int, col: str, dlabel: str, size: int = 120) -> str:
    """Single-arc dial for a disease page: the 270deg gauge FILLED to that disease's score in its identity
    colour, centre = score/100 + "{Disease} risk". Same geometry as _ring_svg with one segment; byte-identical
    to the diseaseRing() twin in mobile.js/desktop.js (W2b)."""
    sw = 12
    cx = size / 2.0
    r = (size - sw) / 2.0 - 1
    c = 2 * math.pi * r
    arc = 0.75
    GAP_PX = 13.5
    track, gap_all, off = "%.1f" % (arc * c), "%.1f" % (c - arc * c), "%.1f" % (c * 2)
    cs, rs = _num(cx), _num(r)
    dash_px = (score / 100.0) * arc * c - GAP_PX
    if dash_px < 0:
        dash_px = 0.0
    dash = "%.1f" % dash_px
    track_c = ('<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="#e9eef5" stroke-width="'
               + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gap_all
               + '" transform="rotate(135 ' + cs + ' ' + cs + ')"/>')
    seg = ('<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="' + col
           + '" stroke-width="' + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + dash + ' ' + off
           + '" transform="rotate(135 ' + cs + ' ' + cs + ')"/>')
    return ('<div class="ringwrap" style="width:' + str(size) + 'px;height:' + str(size) + 'px">'
            '<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 ' + str(size) + ' ' + str(size) + '">'
            + track_c + seg +
            '</svg><div class="num"><div class="numtop"><b>' + str(score) + '</b><span>/ 100</span></div>'
            '<em>' + esc(dlabel) + ' risk</em></div></div>')


def _conf_chip(cell: dict) -> str:
    """Lab-confirmed vs Early-estimate honesty chip for the disease hero. 'Early estimate' is the locked
    replacement for 'Forecast only' (user 2026-07-11); the full-project sweep is W2c."""
    if cell.get("mode") == "confirmed":
        bg, fg = _CONF_LAB
        return ('<span class="confchip" style="background:' + bg + ';color:' + fg + '">Lab-confirmed</span>')
    bg, fg = _CONF_EST
    return ('<span class="confchip" style="background:' + bg + ';color:' + fg + '">Early estimate, capped below HIGH</span>')


def _disease_rank(city: dict, did: str, dlabel: str, cells_by: dict, all_cities: list, diseases: list) -> tuple:
    """(national rank for this disease, how this disease ranks among the city's 4). Both live facts."""
    cid = city["id"]
    ranked = sorted(all_cities, key=lambda c: cells_by[(c["id"], did)]["score"], reverse=True)
    nat = next((i + 1 for i, c in enumerate(ranked) if c["id"] == cid), len(all_cities))
    local = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    k = next((i + 1 for i, d in enumerate(local) if d["id"] == did), 1)
    return nat, len(all_cities), k


def _rank_strip(city: dict, did: str, dlabel: str, cells_by: dict, all_cities: list, diseases: list) -> str:
    nat, ncit, k = _disease_rank(city, did, dlabel, cells_by, all_cities, diseases)
    return ('<div class="rankstrip"><span class="rankfact">' + esc(city["name"]) + ' ranks <b>#' + str(nat)
            + '</b> of ' + str(ncit) + ' cities for ' + esc(dlabel) + ' today.</span>'
            '<span class="rankfact">' + esc(dlabel) + ' is ' + esc(city["name"]) + "'s <b>#" + str(k)
            + '</b> fever concern of 4 right now.</span></div>')


def _disease_band_chip(city: dict, dlabel: str, band: str, info: str = "") -> str:
    if band == "MODERATE":
        bg, bd, bc = "#FFF8E3", "#F0D27A", "#F5B630"
    else:
        bg, bd, bc = RISK_SOFT.get(band, "#eee"), RISK.get(band, "#888"), RISK.get(band, "#888")
    beacon = ('<span class="beacon" style="--c:' + bc + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')
    return ('<div class="bandchip" style="background:' + bg + ';border-color:' + bd + '">'
            + beacon + BAND_TITLE.get(band, band) + ' ' + esc(dlabel) + ' risk in ' + esc(city["name"]) + ' ' + info + '</div>')


def _disease_meaning(city: dict, dlabel: str, cell: dict) -> str:
    return ('<p class="dialmean">Right now ' + esc(city["name"]) + "'s " + esc(dlabel) + ' score is '
            + str(cell["score"]) + '/100 (' + BAND_TITLE.get(cell["band"], cell["band"]) + '). A daily look at local '
            + esc(dlabel.lower()) + ' risk, not who\'s actually sick.</p>')


def _disease_card(city: dict, disease: dict, cell: dict, cells_by: dict, all_cities: list, diseases: list, periods: list) -> str:
    """The disease hero card (module 1 + 2): single-arc dial + confidence chip + rank facts, band chip with
    beacon, plain-language meaning line. Byte-identical to the diseaseCard() twin (W2b)."""
    did = disease["id"]
    col = DISEASE.get(did, "#888")
    band = cell["band"]
    info = ('<span class="dialinfo"><button type="button" class="dialinfo-btn" data-act="dialInfo" aria-label="What this score means">i</button>'
            '<span class="dialtip"><span class="tiprow">This is ' + esc(city["name"]) + "'s " + esc(disease["label"])
            + ' risk today on a 0-100 scale, blended from weather, search and lab signals.</span>'
            '<span class="tipbands"><span class="tb"><i style="background:#3f9d6f"></i>Low 0-24</span><span class="tb"><i style="background:#c2a93a"></i>Low-Mod 25-44</span><span class="tb"><i style="background:#d98a2b"></i>Moderate 45-69</span><span class="tb"><i style="background:#d64545"></i>High 70-100</span></span><span class="tipcaret"></span></span></span>')
    aside = ('<div class="disaside">' + _conf_chip(cell)
             + _rank_strip(city, did, disease["label"], cells_by, all_cities, diseases) + '</div>')
    return ('<div class="card riskcard discard">' + _period_tabs(periods) + '<div class="rtop">'
            + _disease_ring(cell["score"], col, disease["label"], 120) + aside + '</div>'
            + _disease_band_chip(city, disease["label"], band, info) + _disease_meaning(city, disease["label"], cell)
            + '<div class="rfoot"><span class="note">Scored from weather conditions, Google search interest and '
            'PharmEasy lab signals. <button class="knowmore" data-act="openMethod">Know more</button></span></div></div>')


def _disease_weather_card(city: dict, family: str, date_str: str) -> str:
    """Reuses the hub weather card and appends the disease-family mechanism line (module 4)."""
    base = _weather_card(city, date_str)
    mech = '<p class="wxmech">' + esc(DIS_MECH.get(family, DIS_MECH["mosquito"])) + '</p>'
    return base[:-6] + mech + '</div>' if base.endswith('</div>') else base + mech


def _disease_breakdown(city: dict, disease: dict, cell: dict) -> str:
    """Single-disease "Why this score?" (module 3): the 3 signal rows for this cell, pre-expanded (no
    accordion of the other diseases), + the reconciliation note. Reuses _sig / _contribs / SIG."""
    did = disease["id"]
    pts = _contribs(cell)
    ORDER = ["positivity", "weather", "trends"]
    order = sorted(ORDER, key=lambda k: (-pts[k], ORDER.index(k)))
    rows = ""
    sumparts = []
    for k in order:
        rows += _sig(SIG[k], cell, k, pts[k])
        if cell.get("signals", {}).get(k) is not None:
            sumparts.append(SHORT[k] + " " + str(pts[k]))
    note = ('<p class="accnote"><span style="display:block;font-weight:700;margin:0 0 4px">'
            + " + ".join(sumparts) + " = " + str(cell["score"]) + '</span>' + cell["note"] + '</p>')
    # The body is wrapped in an always-open .acc so it inherits the exact opened-accordion layout (mobile
    # display:block; desktop 3-col grid + equal-height), instead of the collapsed .accbody default. It reads
    # like one opened hub accordion, minus the clickable header (there is only one disease here).
    return ('<div class="card whycard discard-why"><h2 class="sechead">Why this ' + esc(disease["label"]) + ' score?</h2>'
            '<p class="secsub">How each signal builds ' + esc(city["name"]) + "'s " + esc(disease["label"])
            + ' score. <button class="knowmore" data-act="openMethod">Know more</button></p>'
            '<div class="acc open"><div class="accbody">' + rows + note + '</div></div></div>')


def _disease_switcher(city: dict, rel: str, diseases: list, cells_by: dict, active: str | None = None) -> str:
    """Crawlable disease cross-link row: chips to this city's 4 disease pages (+ a hub link). On the hub it
    links all 4 children (internal-linking + sitemap discovery); on a child it links the 3 siblings + hub.
    Below-fold SEO markup (not parity-gated); the in-app JS switcher is W2b."""
    cid = city["id"]
    chips = ""
    for d in diseases:
        cell = cells_by[(cid, d["id"])]
        on = " on" if d["id"] == active else ""
        chips += ('<a class="disswitch-chip' + on + '" href="' + rel + esc(cid) + '/' + esc(d["id"]) + '/">'
                  '<span class="dsc-dot" style="background:' + DISEASE.get(d["id"], "#888") + '"></span>'
                  + esc(d["label"]) + ' <b>' + str(cell["score"]) + '</b></a>')
    hub = ('<a class="disswitch-chip" href="' + rel + esc(cid) + '/">All fevers in ' + esc(city["name"])
           + ' <b>' + str(city["blend"]["score"]) + '</b></a>') if active else ""
    # No inner .disswitch-t label: both call sites (the hub's gated section and the disease page's
    # "Explore other fevers" section) carry their own outer H2, so an inner title would duplicate it.
    return '<div class="disswitch"><div class="disswitch-row">' + chips + hub + '</div></div>'


def _disease_archive_view(archive_city: dict | None, states: dict, state: str, did: str, family: str) -> dict | None:
    """Remap the per-disease archive slices into the {overall,weather,search,labs} shape that the existing
    _trend_series / _season_bits already read, so the disease season module reuses the hub trend math verbatim.
    overall = byDisease.{did}.score (its own dial line), weather = byFamily.{family}, search =
    states.{state}.{did}, labs = byDisease.{did}.labs (only where 2025 history exists)."""
    if not archive_city:
        return None
    bd = (archive_city.get("byDisease") or {}).get(did) or {}
    bf = (archive_city.get("byFamily") or {}).get(family) or {}
    ssearch = ((states or {}).get(state) or {}).get(did) or {}
    view = {}
    if bd.get("score"):
        view["overall"] = bd["score"]
    if bf:
        view["weather"] = bf
    if ssearch:
        view["search"] = ssearch
    if bd.get("labs"):
        view["labs"] = bd["labs"]
    return view or None


def _disease_leaderboard_table(all_cities: list, cells_by: dict, did: str, dlabel: str, rel: str, top: int = 20) -> str:
    """Top cities for THIS disease today, ranked by the disease cell score, each linking to the same disease
    page of that city (same-disease crawl mesh). Reuses the hub table styling."""
    ranked = sorted(all_cities, key=lambda c: cells_by[(c["id"], did)]["score"], reverse=True)[:top]
    rows = ""
    for i, c in enumerate(ranked):
        cell = cells_by[(c["id"], did)]
        rows += ('<tr><td>' + str(i + 1) + '</td>'
                 '<td><a href="' + rel + esc(c["id"]) + '/' + esc(did) + '/">' + esc(c["name"]) + '</a></td>'
                 '<td>' + esc(c.get("state", "")) + '</td>'
                 '<td>' + esc(cell["band"]) + '</td>'
                 '<td><strong>' + str(cell["score"]) + '</strong></td></tr>')
    return ('<table class="fw-table"><thead><tr><th scope="col">#</th><th scope="col">City</th>'
            '<th scope="col">State</th><th scope="col">Band</th><th scope="col">Score</th></tr></thead>'
            '<tbody>' + rows + '</tbody></table>')


def _disease_nearby_p(city: dict, did: str, dlabel: str, all_cities: list, cells_by: dict, rel: str) -> str:
    near = _nearest_cities(city, all_cities)
    return ('<p class="fw-near">Nearby for ' + esc(dlabel) + ': ' + ", ".join(
        '<a href="' + rel + esc(c["id"]) + '/' + esc(did) + '/">' + esc(c["name"]) + '</a> ('
        + str(cells_by[(c["id"], did)]["score"]) + '/100, ' + esc(cells_by[(c["id"], did)]["band"]) + ')'
        for c in near) + '.</p>')


def _about_disease(disease: dict) -> str:
    txt, guide = DIS_ABOUT.get(disease["id"], ("", ""))
    if not txt:
        return ""
    # Chikungunya's only blog match is a generic viral-fever page, not a chikungunya guide, so per user
    # feedback the "Read the full guide" link is omitted for chikungunya (the blurb stays).
    link = ('<p><a class="fw-guidelink" href="' + esc(guide) + '" target="_blank" rel="noopener">Read the full '
            + esc(disease["label"]) + ' guide on PharmEasy</a></p>') if (guide and disease["id"] != "chikungunya") else ""
    return ('<section id="s-about"><h2>About ' + esc(disease["label"]) + '</h2>'
            '<p>' + esc(txt) + '</p>' + link + '</section>')


def _disease_season_sec(city: dict, disease: dict, view: dict | None, generated_at: str) -> str:
    s = _season_bits(view, generated_at)
    if not s:
        return ""
    nm = city["name"]; dl = disease["label"]
    return ('<section><h2>How this monsoon compares for ' + esc(dl) + ' in ' + esc(nm) + '</h2>'
            '<p>As of ' + esc(_fmt_date_js(generated_at)) + ', ' + esc(nm) + "'s " + esc(dl) + ' signal is '
            + str(s["ty"]) + '/100 - ' + s["phrase"] + ' the same week last monsoon (' + str(s["ly"])
            + '/100). Last season\'s high point came in the week of ' + esc(s["peak"]) + '. Rain drives '
            'this number, so the picture shifts as the season moves - we refresh it daily.</p></section>')


def faq_items_disease(city: dict, disease: dict, cells_by: dict, all_cities: list, generated_at: str, diseases: list) -> list:
    """Per-city per-disease FAQ (question, answer) pairs weaving the live cell numbers. Risk-indicator
    framing only; ASCII hyphens; no diagnosis, no case counts; positivity as an aggregate trend only.
    Byte-mirrored by faq.js buildDisease() (W2b) for the interactive flow; this baked SSR + the FAQPage
    JSON-LD are the crawlable source."""
    cid = city["id"]; nm = city["name"]; st = city["state"]; dl = disease["label"]; did = disease["id"]
    cell = cells_by[(cid, did)]; sc = str(cell["score"]); bd = cell["band"]
    sigs = cell.get("signals", {})
    w = sigs.get("weather"); wv = "no data" if w is None else str(w)
    tv = sigs.get("trends"); tvs = "no data" if tv is None else str(tv)
    conf = cell.get("mode") == "confirmed"
    news = bool(sigs.get("news_spike")) and did == "dengue"
    nat, ncit, k = _disease_rank(city, did, dl, cells_by, all_cities, diseases)
    date_str = _fmt_date_js(generated_at)
    tert = "the higher-risk third" if nat <= ncit / 3.0 else ("the middle band" if nat <= 2 * ncit / 3.0 else "the lower half")
    fam = disease.get("family", "mosquito")
    wwrd = "warm, wet spells" if fam == "mosquito" else "heavy rain that can dirty the water supply"
    mode_clause = ("PharmEasy lab results feed this one, so it reflects what's actually turning up in tests, not just the weather"
                   if conf else "we don't have enough confirmed lab data for " + nm + " yet, so this is an early, conditions-based estimate that we cap below the HIGH band to stay honest")
    news_clause = (", and there's a national news spike around dengue at the moment" if news else "")
    band_line = {
        "HIGH": "A HIGH reading (" + sc + "/100) means " + dl + " signals in " + nm + " are lining up strongly right now.",
        "MODERATE": "A MODERATE reading (" + sc + "/100) means " + dl + " risk in " + nm + " is a touch elevated but mixed.",
        "LOW-MODERATE": "A LOW-MODERATE reading (" + sc + "/100) means " + dl + " risk in " + nm + " is fairly calm right now.",
        "LOW": "A LOW reading (" + sc + "/100) means " + dl + " is quiet in " + nm + " right now.",
    }.get(bd, "A " + bd + " reading (" + sc + "/100) is the " + dl + " headline for " + nm + " right now.")
    cap_clause = (" It stays below the HIGH band until lab data confirms it, so it can't show HIGH yet." if not conf else "")
    return [
        ("What is " + nm + "'s " + dl + " risk today?",
         nm + "'s " + dl + " score is " + sc + "/100 (" + bd + ") as of " + date_str + ", where 0 is quiet and 100 "
         "is the loudest we show. " + band_line[0].upper() + band_line[1:] + " It's a daily risk indicator across "
         "weather, search and lab signals, not a diagnosis or a count of cases."),
        ("Is " + dl + " rising in " + nm + " right now?",
         "We can't give case counts - Fever Watch doesn't report those. What we can show is that " + st + "'s search "
         "interest for " + dl.lower() + " is " + tvs + "/100 today" + news_clause + ", and the weather signal for it is "
         + wv + "/100. Search and weather can run ahead of an outbreak, but they aren't confirmed cases; for the "
         "confirmed side we lean on PharmEasy's aggregated, de-identified lab positivity where it's available."),
        ("How is " + nm + "'s " + dl + " score calculated?",
         "Three signals, blended and always shown: weather conditions, how much people nearby search " + dl.lower()
         + " symptoms, and PharmEasy lab positivity. " + mode_clause[0].upper() + mode_clause[1:] + "." + cap_clause
         + " The bands are LOW (0-24), LOW-MODERATE (25-44), MODERATE (45-69) and HIGH (70 and up)."),
        ("Is it " + dl + " season in " + nm + "?",
         "Monsoon fevers follow the rain more than the calendar. Right now " + nm + "'s weather signal for " + dl.lower()
         + " is " + wv + "/100, so " + wwrd + " push it up and drier or cooler spells pull it back. Rather than guessing "
         "by the month, check back here - it updates daily."),
        ("How does " + nm + " compare with other cities for " + dl + "?",
         "Out of the " + str(ncit) + " cities we cover, " + nm + " ranks #" + str(nat) + " today for " + dl + " (" + sc
         + "/100, " + bd + "), which puts it in " + tert + " nationally. That ordering shifts through the season because "
         "every city is rescored each day from its own weather, search and lab signals."),
        ("What should someone in " + nm + " do about " + dl + "?",
         ("Keep up the basics: clear standing water and use repellent, since " + dl + " is mosquito-borne, and don't brush "
          "off a fever that lasts more than a couple of days." if fam == "mosquito"
          else "Stick to safe drinking water and good food hygiene, since typhoid is waterborne, and don't brush off a "
          "fever that lasts more than a couple of days.") + " If you're feeling off, a fever panel test or a quick online "
         "doctor consult on PharmEasy is an easy next step. This is a risk indicator, not medical advice, so do see a "
         "doctor if you're unwell."),
    ]


def render_disease_content(city: dict, disease: dict, diseases: list, cells_by: dict, all_cities: list,
                           generated_at: str, rel: str, faq: list, periods: list,
                           archive_city: dict | None = None, states: dict | None = None) -> str:
    """Full crawler-readable content for a /{city}/{disease}/ child page: the disease hero pre (parity twin
    with the W2b JS first paint) + the .fw-below deep SEO block."""
    cid = city["id"]; did = disease["id"]
    cell = cells_by[(cid, did)]
    family = disease.get("family", "mosquito")
    date_str = _fmt_date_js(generated_at)
    view = _disease_archive_view(archive_city, states or {}, city.get("state", ""), did, family)

    pre = (_disease_pre_m(city, disease, cell, cells_by, all_cities, diseases, date_str, periods)
           + _disease_pre_d(city, disease, cell, cells_by, all_cities, diseases, generated_at, periods))

    # --- below-fold SEO block (crawlers / no-JS) ---
    why_sec = ('<section><h2>Why this ' + esc(disease["label"]) + ' score</h2>'
               + _disease_breakdown(city, disease, cell) + '</section>')
    method_sec = ('<section><h2>How we calculate the score</h2>' + METHOD_HTML
                  + '<p class="dashnote">' + esc(DASHBOARD_NOTE) + '</p></section>')
    acts = "".join(
        ('<li><a href="' + esc(h) + '"><strong>' + esc(t) + '</strong> - ' + esc(s) + '</a></li>')
        if h else ('<li><strong>' + esc(t) + '</strong> - ' + esc(s) + '</li>')
        for t, s, h in ACTIONS)
    do_sec = ('<section id="s-do"><h2>What you can do</h2><ul class="fw-actions">' + acts + '</ul>'
              '<p><a class="fw-cta" href="' + esc(city.get("diag_url") or (DIAG_DEFAULT + DIAG_SUFFIX)) + '">'
              + esc(CTA_LABEL + " in " + city["name"]) + '</a></p></section>')
    switch_sec = ('<section><h2>Explore other fevers in ' + esc(city["name"]) + '</h2>'
                  + _disease_switcher(city, rel, diseases, cells_by, active=did) + '</section>')
    other_sec = ('<section id="s-other"><h2>' + esc(disease["label"]) + ' risk in other cities today</h2>'
                 '<p>Top cities for ' + esc(disease["label"]) + ' right now, highest first.</p>'
                 + _disease_nearby_p(city, did, disease["label"], all_cities, cells_by, rel)
                 + _disease_leaderboard_table(all_cities, cells_by, did, disease["label"], rel) + '</section>')
    trend_sec = _trend_html(city, [disease], cells_by, generated_at, view, disease)
    season_sec = _disease_season_sec(city, disease, view, generated_at)
    about_sec = _about_disease(disease)
    faq_sec = '<section id="s-faq"><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'

    return (pre + '<div class="fw-fallback fw-below">' + why_sec + switch_sec + method_sec + do_sec
            + other_sec + trend_sec + season_sec + about_sec + faq_sec + reads_sec
            + '<p class="fw-disc">' + esc(MEDICAL_DISCLAIMER) + '</p></div>')


def _disease_pre_m(city: dict, disease: dict, cell: dict, cells_by: dict, all_cities: list, diseases: list,
                   date_str: str, periods: list) -> str:
    nm = esc(city["name"]); dl = esc(disease["label"])
    return ('<div class="fw-pre fw-pre-m">'
            '<div class="hero"><h1>' + dl + ' risk in ' + nm + ' today, in <em>one score</em>.</h1>'
            '<p>A daily ' + dl + ' risk score for ' + nm + ', blended from weather conditions, Google search interest and PharmEasy lab signals.</p></div>'
            '<button class="loccard" data-act="openCity">' + LOC_PIN + '<span class="locname">' + nm + '</span>'
            '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>'
            '<p class="searchnote loc-note">Updated ' + date_str + '. Available in select cities.</p>' + REVIEWBY
            + '<div class="wrap">' + _disease_card(city, disease, cell, cells_by, all_cities, diseases, periods)
            + _disease_weather_card(city, disease.get("family", "mosquito"), date_str) + '</div></div>')


def _search_hero_disease_d(city: dict, disease: dict, generated_at: str) -> str:
    nm = esc(city["name"]); dl = esc(disease["label"])
    return ('<section class="srch"><div class="srchin">'
            '<h1>' + dl + ' risk in ' + nm + ' today, in <em>one score</em>.</h1>'
            '<p class="subtitle">A daily ' + dl + ' risk score for ' + nm + ', blended from weather conditions, Google Search interest and PharmEasy lab signals.</p>'
            '<div class="locwrap"><button class="loccard" data-act="combo">' + LOC_PIN + '<span class="locname">' + nm + '</span>'
            '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>'
            '<div class="combopanel"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>'
            '</div>'
            '<p class="searchnote loc-note">Updated ' + _fmt_date_js(generated_at) + '. Available in select cities.</p>' + REVIEWBY + '</div></section>')


def _disease_toc(disease: dict) -> str:
    return ('<aside class="toc"><h2>Quick Links</h2>'
            '<a class="cur" href="#s-week">' + esc(disease["label"]) + ' risk</a><a href="#s-why">Why this score?</a>'
            '<a href="#s-weather">Weather conditions today</a><a href="#s-do">What you can do</a>'
            '<a href="#s-trend">This year vs last year</a><a href="#s-about">About ' + esc(disease["label"]) + '</a>'
            '<a href="#s-other">Other cities</a><a href="#s-faq">Common questions</a></aside>')


def _disease_pre_d(city: dict, disease: dict, cell: dict, cells_by: dict, all_cities: list, diseases: list,
                   generated_at: str, periods: list) -> str:
    return ('<div class="fw-pre fw-pre-d">' + _search_hero_disease_d(city, disease, generated_at)
            + '<div class="shell">' + _disease_toc(disease)
            + '<section id="s-week">' + _disease_card(city, disease, cell, cells_by, all_cities, diseases, periods) + '</section>'
            + '<section id="s-why">' + _disease_breakdown(city, disease, cell) + '</section></div></div>')


def render_content(city: dict, diseases: list, cells_by: dict, all_cities: list,
                   generated_at: str, disclaimer: str, rel: str, faq: list, periods: list,
                   archive_city: dict | None = None) -> str:
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    date_str = _fmt_date_js(generated_at)

    # Designed above-fold, server-rendered to match each flow's JS output, so the FIRST paint is the
    # product (dial + legend) - not a plain list - and the flow hydrates over identical DOM (no flash).
    pre = _mobile_pre(city, diseases, cells_by, date_str, periods) + _desktop_pre(city, diseases, cells_by, generated_at, periods)

    head = "".join('<th scope="col">' + esc(lbl) + '</th>' for _, lbl in SIG_COLS)
    rows = ""
    for d in ordered:
        cell = cells_by[(cid, d["id"])]
        sigs = cell.get("signals", {})
        tds = "".join('<td>' + ("no data" if sigs.get(k) is None else str(sigs.get(k))) + '</td>' for k, _ in SIG_COLS)
        rows += ('<tr><th scope="row">' + esc(d["emoji"] + " " + d["label"]) + '</th>' + tds
                 + '<td><strong>' + str(cell["score"]) + '</strong></td></tr>')
    why_sec = (
        '<section><h2>Why this score</h2>'
        '<p>Each disease score is a confirmation-weighted blend of three signals (0 to 100 each), shown below.</p>'
        '<table class="fw-table"><thead><tr><th scope="col">Disease</th>' + head
        + '<th scope="col">Score</th></tr></thead><tbody>' + rows + '</tbody></table></section>'
    )

    method_sec = ('<section><h2>How we calculate the score</h2>' + METHOD_HTML
                  + '<p class="dashnote">' + esc(DASHBOARD_NOTE) + '</p></section>')

    acts = "".join(
        ('<li><a href="' + esc(h) + '"><strong>' + esc(t) + '</strong> - ' + esc(s) + '</a></li>')
        if h else ('<li><strong>' + esc(t) + '</strong> - ' + esc(s) + '</li>')
        for t, s, h in ACTIONS)
    do_sec = ('<section><h2>What you can do</h2><ul class="fw-actions">' + acts + '</ul>'
              '<p><a class="fw-cta" href="' + esc(city.get("diag_url") or (DIAG_DEFAULT + DIAG_SUFFIX)) + '">' + esc(CTA_LABEL + " in " + city["name"]) + '</a></p></section>')

    near = _nearest_cities(city, all_cities)
    near_p = ('<p class="fw-near">Nearby: ' + ", ".join(
        '<a href="' + rel + esc(c["id"]) + '/">' + esc(c["name"]) + '</a> (' + str(c["blend"]["score"])
        + '/100, ' + esc(c["blend"]["band"]) + ')' for c in near) + '.</p>')
    other_sec = ('<section><h2>What is happening in other cities?</h2>'
                 '<p>Overall monsoon-fever risk today across ' + str(len(all_cities))
                 + ' cities, highest first.</p>' + near_p + _cities_table(all_cities, rel) + '</section>')

    tests_sec = _tests_sec(city, generated_at) if FW_TESTS_ENABLED else ""
    # Crawlable disease-switcher row -> this city's 4 child pages (internal linking + sitemap discovery).
    # Gated with the child-page emission so the hub never links to pages the build did not write.
    switch_sec = ('<section><h2>' + esc(city["name"]) + ' by fever</h2>'
                  + _disease_switcher(city, rel, diseases, cells_by) + '</section>') if FW_DISEASE_PAGES_ENABLED else ""
    season_sec = _season_sec(city, archive_city, generated_at)
    trend_sec = _trend_html(city, diseases, cells_by, generated_at, archive_city)
    faq_sec = '<section><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'

    return (pre + '<div class="fw-fallback fw-below">' + why_sec + switch_sec + method_sec + do_sec + tests_sec
            + other_sec + trend_sec + season_sec + faq_sec + reads_sec + '<p class="fw-disc">' + esc(MEDICAL_DISCLAIMER) + '</p></div>')


def render_landing(cfg: dict, all_cities: list, generated_at: str, disclaimer: str, faq: list) -> str:
    hero = (
        '<header class="fw-hero">'
        '<h1>Fever Watch: live monsoon-fever risk for your city, in one score.</h1>'
        '<p class="lede">' + esc(cfg["description"]) + '</p>'
        '<div class="fw-search" aria-hidden="true">Search your city</div>'
        '<p class="microcopy">Available in select cities.</p>' + REVIEWBY + '</header>'
    )
    other_sec = ('<section><h2>Monsoon fever risk by city, today</h2>'
                 '<p>Overall risk across ' + str(len(all_cities)) + ' cities, highest first. Open any city for its full read.</p>'
                 + _cities_table(all_cities, "") + '</section>')
    method_sec = ('<section><h2>How we calculate the score</h2>' + METHOD_HTML
                  + '<p class="dashnote">' + esc(DASHBOARD_NOTE) + '</p></section>')
    faq_sec = '<section><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'
    return ('<div class="fw-fallback">' + hero + other_sec + method_sec + faq_sec + reads_sec
            + '<p class="fw-disc">' + esc(disclaimer) + '</p></div>')


# --- page assembly -----------------------------------------------------------

def page(cfg: dict, grid: dict, cells_by: dict, city: dict | None, env: str, av: str,
         archive: dict | None = None, disease: dict | None = None) -> str:
    rel = "../../" if (city and disease) else ("../" if city else "")
    diseases = grid["diseases"]
    generated_at = grid.get("generated_at", "")
    disclaimer = grid.get("disclaimer", "")
    if city and disease:
        did = disease["id"]; dl = disease["label"]
        cell = cells_by[(city["id"], did)]
        # Title: front-load the exact "{disease} in {city}" query, date re-stamps daily, no raw score
        # (band/score churn would churn the title; the meta carries the numbers).
        title = dl + " in " + city["name"] + ": Risk Score Today, " + _fmt_date_js(generated_at) + " | Fever Watch by PharmEasy"
        _d = cell.get("delta_1d")
        _vy = ("steady vs yesterday" if not _d else (("up " + str(_d)) if _d > 0 else ("down " + str(abs(_d)))) + " vs yesterday")
        _sig = cell.get("signals", {})
        _wt = "no data" if _sig.get("weather") is None else str(_sig.get("weather"))
        _st = "no data" if _sig.get("trends") is None else str(_sig.get("trends"))
        _lt = "no data yet" if _sig.get("positivity") is None else str(_sig.get("positivity"))
        desc = (dl + " risk in " + city["name"] + " today, " + _fmt_date_js(generated_at) + ": " + str(cell["score"])
                + "/100 (" + cell["band"] + "), " + _vy + ". Signals: weather " + _wt + ", search " + _st
                + ", labs " + _lt + ". A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"] + city["id"] + "/" + did + "/"
        faq = faq_items_disease(city, disease, cells_by, grid["cities"], generated_at, diseases)
        periods = grid.get("periods", ["today"])
        archive_city = ((archive or {}).get("cities", {}) or {}).get(city["id"])
        states = (archive or {}).get("states")
        fallback = render_disease_content(city, disease, diseases, cells_by, grid["cities"], generated_at,
                                          rel, faq, periods, archive_city, states)
        # Inline the disease seed so the W2b JS disease mode first-paints instantly (city cell + rank +
        # this city's archive slice incl. its state search line for the per-disease trend).
        city_cells = [cells_by[(city["id"], d["id"])] for d in diseases if (city["id"], d["id"]) in cells_by]
        _ranked = sorted(grid["cities"], key=lambda c: c["blend"]["score"], reverse=True)
        rank = next((i + 1 for i, c in enumerate(_ranked) if c["id"] == city["id"]), len(grid["cities"]))
        # National rank for THIS disease (ranked by the disease cell score), inlined so the rank strip
        # first-paints the same number the SSR computed from the full grid (seed carries only one city).
        drank = _disease_rank(city, did, dl, cells_by, grid["cities"], diseases)[0]
        seed = {"generated_at": generated_at, "diseases": diseases, "bands": grid.get("bands", []),
                "trends_provider": grid.get("trends_provider"), "positivity_provider": grid.get("positivity_provider"),
                "periods": periods, "disease": did,
                "cities": [city], "grid": city_cells, "rank": rank, "ncities": len(grid["cities"]),
                "disease_rank": drank}
        if archive_city:
            seed["archive"] = {"cities": {city["id"]: archive_city},
                               "states": {city.get("state", ""): ((states or {}).get(city.get("state", "")) or {})}}
        dv = og_version(generated_at)
        fw = {"city": city["id"], "disease": did, "gridUrl": rel + "data/grid.json?v=" + dv,
              "archiveUrl": rel + "data/archive/trend_series.json?v=" + dv,
              "base": rel, "logo": rel + "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"], "ver": av, "seed": seed}
        og_url = cfg["base_url"] + "assets/img/og/" + city["id"] + ".jpg"  # v1 reuses the CITY og card
        og_alt = dl + " risk in " + city["name"] + " from Fever Watch"
    elif city:
        title = city["name"] + " Monsoon Fever Risk, " + _fmt_date_js(generated_at) + " | Dengue, Malaria, Chikungunya, Typhoid | Fever Watch"
        # Driver-led, dated, number-rich description rebuilt on every daily build - front-loads the live
        # numbers a searcher (and an AI overview) wants, so Google keeps OUR description instead of
        # stitching its own snippet from the FAQ.
        _b = city["blend"]
        _drv = next((d for d in diseases if d["id"] == _b["driver"]), diseases[0])
        _dband = cells_by.get((city["id"], _b["driver"]), {}).get("band", _b["band"])
        _s = lambda did: str(cells_by[(city["id"], did)]["score"]) if (city["id"], did) in cells_by else "-"
        desc = (city["name"] + " fever risk today, " + _fmt_date_js(generated_at) + ": " + _drv["label"].lower()
                + " leads at " + str(_b["driver_score"]) + "/100 (" + _dband + "). Dengue " + _s("dengue")
                + ", malaria " + _s("malaria") + ", chikungunya " + _s("chikungunya") + ", typhoid " + _s("typhoid")
                + ". A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"] + city["id"] + "/"
        faq = faq_items(city, diseases, cells_by, grid["cities"], generated_at)
        periods = grid.get("periods", ["today"])
        archive_city = ((archive or {}).get("cities", {}) or {}).get(city["id"])
        fallback = render_content(city, diseases, cells_by, grid["cities"], generated_at, disclaimer, rel, faq, periods, archive_city)
        # Inline per-city seed so the JS paints the designed view instantly (no wait for the ~850KB
        # grid). The full grid still loads in the background for the other-cities leaderboard.
        city_cells = [cells_by[(city["id"], d["id"])] for d in diseases if (city["id"], d["id"]) in cells_by]
        _ranked = sorted(grid["cities"], key=lambda c: c["blend"]["score"], reverse=True)
        rank = next((i + 1 for i, c in enumerate(_ranked) if c["id"] == city["id"]), len(grid["cities"]))
        # seed.faq is no longer inlined: the FAQ is recomputed client-side from the grid by faq.js
        # (Option A) so it refreshes on every city switch and the page stays lean. The CRAWLABLE FAQ
        # is the Python-baked SSR accordion (_faq_html) + the per-city FAQPage JSON-LD, both unchanged.
        # We keep the national rank so the "vs other cities" answer first-paints right before the grid.
        seed = {"generated_at": generated_at, "diseases": diseases, "bands": grid.get("bands", []),
                "trends_provider": grid.get("trends_provider"), "positivity_provider": grid.get("positivity_provider"),
                "periods": periods,
                "cities": [city], "grid": city_cells, "rank": rank, "ncities": len(grid["cities"])}
        # Inline THIS city's real season-trend slice (last-year + this-year series) into the seed so the
        # instant first paint renders the REAL "this monsoon vs last year" chart immediately, instead of the
        # deterministic mock the JS would otherwise show until the full trend_series.json fetch lands (the
        # cold-load "mock graphs first" bug). Shape matches DATA.archive (cities keyed by id), so trend.js
        # forCity() reads it identically whether it came from the seed or the fetched archive. ~0.4KB/page.
        if archive_city:
            seed["archive"] = {"cities": {city["id"]: archive_city}}
        dv = og_version(generated_at)  # data version (grid.generated_at digits) -> cache-bust the data fetches
        fw = {"city": city["id"], "gridUrl": rel + "data/grid.json?v=" + dv, "archiveUrl": rel + "data/archive/trend_series.json?v=" + dv,
              "base": rel, "logo": rel + "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"], "ver": av, "seed": seed}
        og_url = cfg["base_url"] + "assets/img/og/" + city["id"] + ".jpg"
        og_alt = city["name"] + " monsoon fever risk score card from Fever Watch"
    else:
        title = "Monsoon Fever Risk in India, " + _fmt_date_js(generated_at) + " | Dengue, Malaria, Chikungunya, Typhoid | Fever Watch"
        desc = ("Monsoon fever risk in " + str(len(grid["cities"])) + " Indian cities today, "
                + _fmt_date_js(generated_at) + ": dengue, malaria, chikungunya and typhoid scored 0-100 daily "
                "from weather, search and lab signals. A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"]
        faq = faq_items_landing()
        fallback = render_landing(cfg, grid["cities"], generated_at, disclaimer, faq)
        dv = og_version(generated_at)
        fw = {"gridUrl": "data/grid.json?v=" + dv, "base": "", "logo": "assets/img/pe_logo-white.svg",
              "canonicalBase": cfg["base_url"], "ver": av}
        # The landing JS renders the DEFAULT city's full dashboard (incl. the season-trend) - the same flow as a
        # city page - so it needs the archive exactly like a city page; without it the home trend has no real
        # data. Inline the default city's seed + its real archive slice (matching pickDefaultCity(): bengaluru if
        # present, else the first city) + archiveUrl, mirroring the city branch, so the home first-paints REAL
        # from the seed (never mock) and only upgrades the leaderboard from the fetch. We deliberately do NOT set
        # fw["city"] (that would disable maybeGeo()'s IP redirect, which is gated on !FW.city on the landing).
        _clist = grid["cities"]
        _def = next((c for c in _clist if c["id"] == "bengaluru"), _clist[0]) if _clist else None
        if _def:
            periods = grid.get("periods", ["today"])
            _dcells = [cells_by[(_def["id"], d["id"])] for d in diseases if (_def["id"], d["id"]) in cells_by]
            _ranked = sorted(_clist, key=lambda c: c["blend"]["score"], reverse=True)
            _drank = next((i + 1 for i, c in enumerate(_ranked) if c["id"] == _def["id"]), len(_clist))
            seed = {"generated_at": generated_at, "diseases": diseases, "bands": grid.get("bands", []),
                    "trends_provider": grid.get("trends_provider"), "positivity_provider": grid.get("positivity_provider"),
                    "periods": periods,
                    "cities": [_def], "grid": _dcells, "rank": _drank, "ncities": len(_clist)}
            _darch = ((archive or {}).get("cities", {}) or {}).get(_def["id"])
            if _darch:
                seed["archive"] = {"cities": {_def["id"]: _darch}}
            fw["archiveUrl"] = "data/archive/trend_series.json?v=" + dv
            fw["seed"] = seed
        og_url = cfg["base_url"] + cfg.get("og_image", "")
        og_alt = cfg.get("og_image_alt", "")
    # Cache-bust the per-city OG card on the social meta so platforms re-fetch the preview when
    # scores are recomputed (keyed on grid.generated_at). JSON-LD keeps the clean URL.
    ver = og_version(generated_at)
    og_meta = (og_url + "?v=" + ver) if (city and ver) else og_url
    meds_href = _meds_href(city["id"] if city else None)
    return PAGE.format(
        lang=cfg.get("language", "en-IN"),
        head=head_meta(cfg, env, title, desc, canonical, rel, og_meta, og_alt),
        jsonld=jsonld(cfg, generated_at, diseases, city, og_url, faq, disease),
        rel=rel, nav=nav_html(rel, meds_href), ticker=ticker_html(grid["cities"], rel),
        fallback=fallback, footer=footer_html(),
        fw=json.dumps(fw, ensure_ascii=False).replace("</", "<\\/"), av=av,
    )


# --- site plumbing -----------------------------------------------------------

def write_robots(cfg: dict, env: str) -> None:
    rule = "Allow: /" if env == "production" else "Disallow: /"
    body = "User-agent: *\n" + rule + "\n\nSitemap: " + cfg["base_url"] + "sitemap.xml\n"
    _write("robots.txt", body)


def write_sitemap(cfg: dict, cities: list, generated_at: str, diseases: list | None = None) -> None:
    base, lm = cfg["base_url"], iso_date(generated_at)
    rows = ['  <url><loc>' + esc(base) + '</loc><lastmod>' + lm + '</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>']
    for c in cities:
        rows.append('  <url><loc>' + esc(base + c["id"] + "/") + '</loc><lastmod>' + lm
                    + '</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>')
        # Child disease pages (emitted only when the disease pages are enabled; gated so the sitemap never
        # advertises a URL the build did not write).
        if FW_DISEASE_PAGES_ENABLED and diseases:
            for d in diseases:
                rows.append('  <url><loc>' + esc(base + c["id"] + "/" + d["id"] + "/") + '</loc><lastmod>' + lm
                            + '</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>')
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")
    _write("sitemap.xml", body)


def write_manifest(cfg: dict) -> None:
    m = {
        "name": cfg["site_name"] + " by " + cfg.get("brand", "PharmEasy"), "short_name": cfg["site_name"],
        "description": cfg["description"], "start_url": ".", "scope": ".", "display": "standalone",
        "background_color": "#F5F8FC", "theme_color": cfg.get("theme_color", "#10847E"),
        "lang": cfg.get("language", "en-IN"),
        "icons": [
            {"src": "assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "assets/img/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    _write("site.webmanifest", json.dumps(m, ensure_ascii=False, indent=2) + "\n")


def _write(relpath: str, body: str) -> None:
    full = os.path.join(DIST, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    env = (os.environ.get("SITE_ENV") or "staging").strip().lower()
    cfg = load_json(os.path.join(ROOT, "config", "site.json"))
    # Until the production reverse-proxy route is finalized, staging builds canonicalize to the
    # /fever-watch/-rooted staging URL; production uses base_url. Both live only in config/site.json.
    if env != "production":
        cfg["base_url"] = cfg.get("staging_url") or cfg["base_url"]
    grid_path = os.path.join(ROOT, "data", "grid.json")
    if not os.path.exists(grid_path):
        print("ABORT: data/grid.json not found. Run build_daily.py first.", file=sys.stderr)
        return 1
    grid = load_json(grid_path)
    cities, diseases = grid["cities"], grid["diseases"]
    cells_by = {(r["city"], r["disease"]): r for r in grid["grid"]}

    # Per-city diagnostics CTA target: stored on each city as diag_url so the "Book a fever panel test" CTA
    # tracks the rendered city in the SSR fallback AND the JS flows (which swap city client-side without reload).
    diag_links = {}
    try:
        diag_links = {k: v for k, v in load_json(os.path.join(ROOT, "config", "diag_links.json")).items()
                      if not k.startswith("_")}
    except Exception as _e:
        print("WARN: config/diag_links.json not loaded (%s); CTAs use the default packages page." % _e, file=sys.stderr)
    for _c in cities:
        _c["diag_url"] = diag_links.get(_c["id"], DIAG_DEFAULT) + DIAG_SUFFIX

    print("SITE_ENV=" + env + "  base_url=" + cfg["base_url"])
    print("Diagnostics CTA: %d/%d cities mapped to a local page (rest -> default)."
          % (sum(1 for _c in cities if _c["id"] in diag_links), len(cities)))
    print("Cities: %d  diseases: %d  grid cells: %d" % (len(cities), len(diseases), len(grid["grid"])))

    # fresh output
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    # copy runtime assets + data (+ tokens.css from prototypes)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(DIST, "assets"))
    os.makedirs(os.path.join(DIST, "assets", "css"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "prototypes", "tokens.css"), os.path.join(DIST, "assets", "css", "tokens.css"))
    os.makedirs(os.path.join(DIST, "data"), exist_ok=True)
    # Re-serialize (not a raw copy) so the per-city diag_url enrichment above ships in the fetched grid.
    with open(os.path.join(DIST, "data", "grid.json"), "w", encoding="utf-8") as _gf:
        json.dump(grid, _gf, ensure_ascii=False, separators=(",", ":"))
    arch_path = os.path.join(ROOT, "data", "archive", "trend_series.json")
    archive = None
    if os.path.exists(arch_path):
        os.makedirs(os.path.join(DIST, "data", "archive"), exist_ok=True)
        shutil.copy(arch_path, os.path.join(DIST, "data", "archive", "trend_series.json"))
        # Load once so the SSR labs-tab avail flag (and the no-JS first paint) matches what trend.js will
        # hydrate from the committed archive (real labs line for cities with 2025 history, "coming soon" else).
        archive = load_json(arch_path)

    # Guardrail (no mock, no blank): every city's season-trend needs a REAL overall archive line, else the
    # widget falls to the "coming soon" empty state. The lenient ty gate already charts a short this-year line
    # as a real partial, so this only fires on a genuinely malformed/missing overall (ly not 22 weeks, or an
    # empty ty). Abort the build then - the previous good deploy stays live - rather than ship a blank trend.
    if archive is not None:
        _ga = grid.get("generated_at", "")
        try:
            _gi = datetime.datetime.fromisoformat(_ga.replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
            _as_of = _t_clamp((datetime.date(_gi.year, _gi.month, _gi.day) - datetime.date(_gi.year, 6, 1)).days // 7, 0, TREND_NW - 1)
        except Exception:
            _as_of = 0
        _acities = archive.get("cities") or {}
        _bad = [c["id"] for c in cities
                if not (len(((_acities.get(c["id"]) or {}).get("overall") or {}).get("ly") or []) == TREND_NW
                        and 1 <= len(((_acities.get(c["id"]) or {}).get("overall") or {}).get("ty") or []) <= _as_of + 1)]
        if _bad:
            raise SystemExit("ABORT build_site: season-trend archive is missing a REAL overall line for %d/%d "
                             "cities (e.g. %s) at as_of=%d. Run build_archive.py first; refusing to ship a blank "
                             "trend." % (len(_bad), len(cities), ", ".join(_bad[:8]), _as_of))

    # landing
    av = asset_version()
    _write("index.html", page(cfg, grid, cells_by, None, env, av, archive))
    # cities (+ per-disease children when enabled)
    n_children = 0
    for c in cities:
        _write(os.path.join(c["id"], "index.html"), page(cfg, grid, cells_by, c, env, av, archive))
        if FW_DISEASE_PAGES_ENABLED:
            for d in diseases:
                _write(os.path.join(c["id"], d["id"], "index.html"),
                       page(cfg, grid, cells_by, c, env, av, archive, d))
                n_children += 1

    write_robots(cfg, env)
    write_sitemap(cfg, cities, grid.get("generated_at", ""), diseases)
    write_manifest(cfg)

    n_pages = len(cities) + 1 + n_children
    print("Wrote %d pages (1 landing + %d cities + %d disease children) -> %s"
          % (n_pages, len(cities), n_children, DIST))
    print("robots.txt (%s), sitemap.xml (%d urls), site.webmanifest written." % (env, n_pages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
