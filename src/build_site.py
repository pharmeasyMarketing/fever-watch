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
     "It blends breeding weather, public search interest and PharmEasy lab positivity."),
    ("Is this a diagnosis or medical advice?",
     "No. Fever Watch is a risk indicator only. It is not a diagnosis, not a count of actual cases "
     "or mosquitoes, and not a substitute for a doctor. If you feel unwell, consult a clinician."),
    ("How is the score calculated?",
     "It is a transparent weighted blend of three signals at different points in the illness pipeline: "
     "breeding weather (leading), search interest (coincident) and lab positivity (lagging ground "
     "truth). When lab data is present it leads the score, and the breakdown is always shown."),
    ("What does forecast-only mean?",
     "Where there is not enough lab data for a city and disease yet, the score is a conditions-based "
     "forecast and is capped below the HIGH band, so a forecast-only read can never show HIGH. This "
     "keeps the read honest."),
    ("How often is it updated?",
     "Weather is refreshed daily from NASA POWER, search interest weekly, and the lab signal daily. "
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
    "locations are capped below the HIGH band."
)

# Full methodology baked into the page (H3 subsections under the "How we calculate this" H2).
METHOD_HTML = (
    "<h3>1. Per-disease environmental score (0 to 100)</h3>"
    "<p>From trailing daily weather, shaped by disease family:</p><ul>"
    "<li><strong>Mosquito-borne</strong> (dengue, malaria, chikungunya): a unimodal temperature response "
    "peaking near 29C (Aedes and Anopheles breed fastest at 25 to 30C; activity falls below about 18C and "
    "above about 35C), times lagged rainfall over the past 14 days (standing-water sites emerge 1 to 2 weeks "
    "after rain), times relative humidity (above about 60% extends mosquito lifespan).</li>"
    "<li><strong>Waterborne</strong> (typhoid): recent (7-day) plus accumulated (14-day) rainfall as a "
    "contamination and runoff proxy; temperature secondary.</li></ul>"
    "<h3>2. Three independent signals</h3><ul>"
    "<li><strong>Breeding weather</strong> (leading, weeks ahead): the environmental score above.</li>"
    "<li><strong>Google Search Interest</strong> (coincident): symptom-search attention, smoothed and "
    "down-weighted when it spikes alone.</li>"
    "<li><strong>PharmEasy lab signal</strong> (lagging, ground truth): aggregate, de-identified "
    "test-positivity trend.</li></ul>"
    "<h3>3. Confirmation-weighted ensemble</h3>"
    "<p>Not a flat average. With lab data present it dominates (weights about 30 / 22 / 48 weather / search / "
    "positivity) and agreement across all three raises confidence. Without it, a capped forecast-only mode "
    "(maximum 69, below the HIGH threshold) keeps a conditions-only read honest. The city headline is a "
    "max-dominant blend (0.8 times the top disease plus 0.2 times the mean of the rest) with the driver disease named.</p>"
    "<h3>Data sources</h3><ul>"
    "<li>Weather: NASA POWER (NASA Langley, US public domain / CC0)</li>"
    "<li>Search: Google Trends</li>"
    "<li>Positivity: PharmEasy diagnostics (aggregate, de-identified)</li></ul>"
    "<h3>Selected research</h3><ul>"
    "<li>Mordecai et al. Thermal biology of mosquito-borne disease. Ecology Letters, 2019.</li>"
    "<li>Liu-Helmersson et al. Vectorial capacity of Aedes aegypti and temperature. PLOS ONE, 2014.</li>"
    "<li>Ginsberg et al. Detecting influenza epidemics using search engine query data. Nature, 2009.</li>"
    "<li>IDSP Weekly Outbreak Reports, MoHFW (official surveillance).</li></ul>"
)

CONSULT_HREF = "https://pharmeasy.in/doctor-consultation/landing?src=feverwatch"
ACTIONS = [
    ("Monsoon precautions", "Cut breeding sites and bites", ""),
    ("Vaccination: does it work?", "What helps, what does not", ""),
    ("Fever? Follow our framework", "When to test, when to wait", ""),
    ("Not sure? Talk to a doctor", "Online consult on PharmEasy", CONSULT_HREF),
]
CTA_LABEL, CTA_HREF = "Book a fever panel test", "https://pharmeasy.in/diag-pwa/content/Fever_LP?src=feverwatch"
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
{nav}
{ticker}
<div id="fw-app">{fallback}</div>
{footer}
<script>window.FW = {fw};</script>
<script src="{rel}assets/js/faq.js?v={av}" defer></script>
<script src="{rel}assets/js/trend.js?v={av}" defer></script>
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


def iso_date(iso) -> str:
    return (iso or "")[:10]


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
                "assets/js/fw-loader.js", "assets/js/mobile.js", "assets/js/desktop.js"):
        try:
            with open(os.path.join(ROOT, rel), "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:10]


# --- shared baked chrome -----------------------------------------------------

def nav_html(rel: str) -> str:
    items = (
        '<div class="pe-nav-item"><button type="button" class="pe-nav-btn" aria-expanded="false" aria-haspopup="true">Healthcare <span class="pe-caret" aria-hidden="true">&#9662;</span></button>'
        '<div class="pe-nav-drop">'
        '<a href="https://pharmeasy.in/online-medicine-order?src=homecard">Medicines</a>'
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
        '<span class="footdisc">' + MEDICAL_DISCLAIMER + ' Live weather via NASA POWER (public domain); Google search trends via Google Trends; aggregate lab data from PharmEasy Labs and its Partner Affiliates.</span>'
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


def jsonld(cfg: dict, generated_at: str, diseases: list, city: dict | None, og_url: str, faq: list) -> str:
    base = cfg["base_url"]
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
    if city:
        url = base + city["id"] + "/"
        graph.append({
            "@type": "WebPage", "@id": url, "url": url,
            "name": city["name"] + " monsoon fever risk | Fever Watch",
            "description": "Daily dengue, malaria, chikungunya and typhoid risk for "
                           + city["name"] + ", India.",
            "inLanguage": lang, "isPartOf": {"@id": base + "#website"},
            "about": [d["label"] for d in diseases] + ["monsoon fever risk in India"],
            "primaryImageOfPage": og_url, "dateModified": generated_at,
        })
        graph.append({
            "@type": "Dataset", "@id": url + "#dataset",
            "name": "Fever Watch risk scores for " + city["name"],
            "description": "A daily, decomposable monsoon-fever risk score (0 to 100) per disease for "
                           + city["name"] + ", India, blended from breeding weather, search interest and "
                           "lab positivity. A risk indicator, not case counts.",
            "url": url, "inLanguage": lang, "isAccessibleForFree": True,
            "creator": {"@id": base + "#organization"}, "publisher": {"@id": base + "#organization"},
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "spatialCoverage": {"@type": "Place", "name": city["name"] + ", India",
                                "geo": {"@type": "GeoCoordinates", "latitude": city["lat"], "longitude": city["lon"]}},
            "variableMeasured": {"@type": "PropertyValue", "name": "monsoon_fever_risk_score", "minValue": 0, "maxValue": 100},
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
        })
        graph.append(faqpage)
    body = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return '<script type="application/ld+json">\n' + body + '\n</script>'


# --- baked full content (crawler / no-JS; hidden for JS users, which hydrate over it) ---------

SIG_COLS = [("weather", "Breeding weather"), ("trends", "Search interest"), ("positivity", "Lab positivity")]


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
                      else "Lab data hasn't reached " + nm + " yet, so for now it's a weather-and-search forecast (about 60/40), capped at 69 so it can't hit HIGH until the labs back it up")
    season_clause = ("that's firmly in breeding-friendly territory" if dw >= 60 else ("that's middling - not nothing, not alarming" if dw >= 25 else "that's on the quiet side for now"))
    band_open = {
        "HIGH": "A HIGH reading (" + bs + "/100) means conditions and signals in " + nm + " are lining up strongly this week - the moment to be most careful about bites, clearing standing water, and not shrugging off a fever that drags past a couple of days.",
        "MODERATE": "A MODERATE reading (" + bs + "/100) means things in " + nm + " are a touch elevated but mixed - not a red alert, just a nudge to take the usual precautions.",
        "LOW-MODERATE": "A LOW-MODERATE reading (" + bs + "/100) means " + nm + " is fairly calm this week - low pressure overall, though the monsoon can turn that around fast.",
        "LOW": "A LOW reading (" + bs + "/100) means it's quiet in " + nm + " right now - conditions and signals are all on the gentle side.",
    }.get(bb, "A " + bb + " reading (" + bs + "/100) is the headline for " + nm + " this week.")
    cap_clause = (" And since " + nm + " is on a conditions-only forecast for now, it's capped at 69 - it won't show HIGH until lab data confirms it." if not any_conf else "")
    news_clause = (", and there's a national news spike around dengue at the moment" if news else "")

    return [
        ("How worried should I be about monsoon fevers in " + nm + " right now?",
         "Right now " + nm + "'s overall read is " + bs + "/100, which lands in the " + bb + " band - and " + dl + " is the main thing nudging it up (it's sitting at " + dsc + "). Think of the score as a daily snapshot of conditions across the four fevers we track, not a tally of who's actually sick, so it's a heads-up rather than a diagnosis. We recompute it every day; this one's from " + date_str + "."),
        ("Is dengue something to watch in " + nm + " this week?",
         "Dengue's at " + den_s + "/100 in " + nm + " (" + den_b + ") this week, which makes it the " + _ORD.get(drank, "biggest") + " concern of the four fevers here. " + den_mode[0].upper() + den_mode[1:] + ". Either way it's a risk signal built from breeding weather, search interest and lab data - not a count of cases or mosquitoes, and not a diagnosis."),
        ("Of all the monsoon fevers, which one should " + nm + " keep an eye on?",
         "This week it's " + dl + ", at " + dsc + "/100 (" + dbd + "). Here's the full order right now, highest to lowest: " + rank_list + ". Worth checking back, though - we rerun this daily, and the ranking really does shuffle as the weather, searches and lab signals move."),
        ("How is " + nm + "'s weather affecting the mosquito-fever risk?",
         nm + " has a " + clim + " climate, and this week it's averaging about " + temp + "C with " + hum + "% humidity and roughly " + rain14 + " mm of rain over the last fortnight. Mosquitoes like Aedes and Anopheles breed fastest near 29C and love the standing water that shows up a week or two after rain, so warm, wet spells push our breeding-weather signal up and drier or cooler ones pull it back down. (Worth flagging: that's outdoor weather, not body-temperature fever.)"),
        ("Where does the " + nm + " score actually come from?",
         "Three signals, blended: breeding weather (from NASA's open POWER data), how much people are searching for these illnesses, and PharmEasy's lab positivity. " + weights_clause + ". We always show the breakdown - it's never a mystery number. For reference, the bands are LOW (0-24), LOW-MODERATE (25-44), MODERATE (45-69) and HIGH (70 and up)."),
        ("Is it dengue season in " + nm + " yet?",
         "Monsoon fevers follow the rain more than the calendar. This week " + nm + "'s breeding-weather signal for the mosquito-borne ones is " + den_w + "/100, with about " + rain14 + " mm of rain over the past fortnight feeding standing water - " + season_clause + ". So rather than guessing by the month, just check back here; it updates daily, and you'll see conditions climb or ease in real time."),
        ("Is " + nm + " better or worse off than other Indian cities right now?",
         "Out of the " + str(ncit) + " cities we cover, " + nm + " ranks #" + str(rank) + " this week on the overall score (" + bs + "/100, " + bb + "), which puts it in " + tert + " nationally. That ordering shifts through the season, though, because every city is rescored each day from its own weather, searches and lab signals."),
        ("What does a " + bb + " reading actually mean for " + nm + "?",
         band_open + " The bands run LOW, LOW-MODERATE, MODERATE, then HIGH." + cap_clause),
        ("Are dengue cases actually rising in " + nm + "?",
         "We can't give you case counts - Fever Watch doesn't report those. What we can show is how much " + st + " is searching for dengue, which is " + den_t_s + "/100 this week" + news_clause + ". Search spikes often track public worry and can run ahead of, or alongside, an outbreak - but they aren't confirmed cases. For the confirmed side we lean on PharmEasy's aggregated, de-identified lab positivity wherever it's available."),
        ("What should someone in " + nm + " actually do this week?",
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
    """Match the flow's fmtDate(): '<UTC day> <Mon> <year>' (e.g. 7 Jun 2026)."""
    iso = generated_at or ""
    try:
        return "%d %s %d" % (int(iso[8:10]), _MONTHS[int(iso[5:7]) - 1], int(iso[0:4]))
    except Exception:
        return ""


# --- redesign: segmented ring, legend, band chip, breeding-weather cards (mirror mobile.js + desktop.js) -
# Both flows now share these above-fold helpers: mobile _mobile_pre and desktop _desktop_pre both embed
# _risk_card / _weather_card, and BOTH mobile.js + desktop.js emit byte-identical markup. Each helper is
# above the fold for at least one flow, so hydration must be a no-op repaint (CLS 0) - edit ALL twins
# together (build_site.py + mobile.js + desktop.js).
BAND_TITLE = {"HIGH": "High", "MODERATE": "Moderate", "LOW-MODERATE": "Low-Moderate", "LOW": "Low"}

# Per-disease IDENTITY colours (NOT the severity ramp) - used for the dial segments, the legend dots and
# the breakdown dots so the risk card reads consistently (Figma node 49-1303, measured from the render).
DISEASE = {"dengue": "#F1839D", "malaria": "#887ADE", "chikungunya": "#46CFE7", "typhoid": "#4681EF"}

# Red map-pin ("location drop") icon for the location card, matching the Figma (replaces the emoji).
# Kept byte-identical to the LOC_PIN string in assets/js/mobile.js (above the fold).
LOC_PIN = ('<svg class="locpin" viewBox="0 0 24 24" width="19" height="19" aria-hidden="true">'
           '<path fill="#F0493F" d="M12 2.2c-3.9 0-7 3.1-7 7 0 5 7 12.6 7 12.6s7-7.6 7-12.6c0-3.9-3.1-7-7-7z"/>'
           '<circle cx="12" cy="9.2" r="2.6" fill="#fff"/></svg>')

# Outline icons for the breeding-weather cards (droplet / rain cloud / water waves / sparkle). Kept
# byte-identical to the WX_* strings in assets/js/mobile.js (above the fold).
_WX_A = '<svg class="wxic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
WX_HUM = _WX_A + '<path d="M12 3.6c2.9 3.8 5.3 6.5 5.3 9.5a5.3 5.3 0 0 1-10.6 0c0-3 2.4-5.7 5.3-9.5Z"/></svg>'
WX_RAIN = _WX_A + '<path d="M7.6 14.4a3.5 3.5 0 0 1 .3-7 4.6 4.6 0 0 1 8.8 1.3 3.2 3.2 0 0 1 .2 5.4"/><path d="M8.4 17.4 7.5 20M12 17.4 11.1 20M15.6 17.4 14.7 20"/></svg>'
WX_STAG = _WX_A + '<path d="M3 7.6q2.25-2.4 4.5 0t4.5 0 4.5 0 4.5 0"/><path d="M3 12q2.25-2.4 4.5 0t4.5 0 4.5 0 4.5 0"/><path d="M3 16.4q2.25-2.4 4.5 0t4.5 0 4.5 0 4.5 0"/></svg>'
WX_PEAK = _WX_A + '<path d="M12 3v18M3 12h18M5.6 5.6 18.4 18.4M18.4 5.6 5.6 18.4"/></svg>'

# Period tabs above the dial. Only granularities present in grid["periods"] render (the data layer gates
# week/month by how many committed days exist); "today" is always the active default.
_PERIOD_LABELS = [("today", "Today"), ("week", "This week"), ("month", "This month")]


def _period_tabs(periods: list) -> str:
    avail = set(periods or ["today"])
    out = ""
    for key, label in _PERIOD_LABELS:
        if key not in avail:
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
            '<em>Overall fever risk</em></div></div>')


def _legend_rows(city: dict, diseases: list, cells_by: dict) -> str:
    """Per-disease legend beside the dial: identity-colour dot + "Name : score" + (dormant) day-over-day
    arrow, ordered by score descending. No emoji, no "Top concern" badge. Mirrors mobile.js legend."""
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    rows = ""
    for d in ordered:
        cell = cells_by[(cid, d["id"])]; col = DISEASE.get(d["id"], "#888")
        rows += ('<div class="legrow"><span class="legdot" style="background:' + col + '"></span>'
                 '<span class="legname">' + esc(d["label"]) + ' : <b>' + str(cell["score"]) + '</b></span>'
                 + _delta_arrow(cell.get("delta_1d")) + '</div>')
    return '<div class="leg">' + rows + '</div>'


def _band_chip(city: dict) -> str:
    # MODERATE uses the Figma gold; other bands keep the locked risk ramp. Beacon colour follows suit.
    band = city["blend"]["band"]
    if band == "MODERATE":
        bg, bd, bc = "#FFF8E3", "#F0D27A", "#F5B630"
    else:
        bg, bd, bc = RISK_SOFT.get(band, "#eee"), RISK.get(band, "#888"), RISK.get(band, "#888")
    beacon = ('<span class="beacon" style="--c:' + bc + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')
    return ('<div class="bandchip" style="background:' + bg + ';border-color:' + bd + '">'
            + beacon + BAND_TITLE.get(band, band) + ' fever risk in ' + esc(city["name"]) + '</div>')


def _risk_card(city: dict, diseases: list, cells_by: dict, periods: list) -> str:
    """The mobile .card risk card, byte-identical to mobile.js riskCard(): period tabs, the segmented dial
    + per-disease legend, the band chip with the animated beacon, then a caption with Know-more + Share."""
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    segs = [(cells_by[(cid, d["id"])]["score"], DISEASE.get(d["id"], "#888")) for d in ordered]
    return ('<div class="card riskcard">' + _period_tabs(periods) + '<div class="rtop">'
            + _ring_svg(segs, city["blend"]["score"], 120) + _legend_rows(city, diseases, cells_by) + '</div>'
            + _band_chip(city)
            + '<div class="rfoot"><span class="note">Scores calculated from breeding weather, Google search '
            'interest and PharmEasy lab signals. <button class="knowmore" data-act="openMethod">Know more</button></span>'
            '<button class="sharebtn" data-act="openShare">⤴ Share</button></div></div>')


def _weather_card(city: dict) -> str:
    """Breeding-weather conditions today: humidity + recent rain (live), an ESTIMATED stagnation index
    and the static dawn/dusk peak tip, each as an outline icon + "Label . value" + a short line. Mirrors
    mobile.js weatherCard(). Above the fold, so byte-identical to the JS twin."""
    w = city.get("weather") or {}
    hum, r7 = w.get("humidity_pct"), w.get("rain_7d_mm")
    stag = (w.get("stagnation") or {}).get("level")
    cards = [
        (WX_HUM, "Humidity", ("n/a" if hum is None else str(_t_r(hum)) + "%"), "Mosquitoes survive longer and breed more."),
        (WX_RAIN, "Rainfall", ("n/a" if r7 is None else str(_t_r(r7)) + "mm"), "Standing water increases mosquito growth."),
        (WX_STAG, "Stagnation", (stag.lower() if stag else "n/a"), "Increases mosquito breeding (estimated)."),
        (WX_PEAK, "Mosquito peak", "Dawn & Dusk", "Use extra protection."),
    ]
    cells = ""
    for ic, label, val, sub in cards:
        cells += ('<div class="wxcard"><div class="wxtop">' + ic + '<span class="wxhead">' + esc(label)
                  + '<span class="wxsep"></span><b>' + esc(val) + '</b></span></div>'
                  '<div class="wxsub">' + esc(sub) + '</div></div>')
    return ('<div class="card wxsec"><h2 class="sectiontitle">Breeding weather conditions today</h2>'
            '<p class="sectionsub">What today\'s weather means for mosquito breeding.</p>'
            '<div class="wxgrid">' + cells + '</div></div>')


def _mobile_pre(city: dict, diseases: list, cells_by: dict, date_str: str, periods: list) -> str:
    nm = esc(city["name"])
    return ('<div class="fw-pre fw-pre-m">'
            '<div class="hero"><h1>Live monsoon-fever risk for ' + nm + ' in <em>one score</em>.</h1>'
            '<p>Dengue, malaria, chikungunya and typhoid, blended from breeding weather, Google search interest and PharmEasy lab signals.</p></div>'
            '<button class="loccard" data-act="openCity">' + LOC_PIN + '<span class="locname">' + nm + '</span>'
            '<span class="locchange">Change <span class="loccaret" aria-hidden="true">▾</span></span></button>'
            '<p class="searchnote loc-note">Updated ' + date_str + '. Available in select cities.</p>'
            '<div class="wrap">' + _risk_card(city, diseases, cells_by, periods) + _weather_card(city) + '</div></div>')


SIGCOL = {"weather": [21, 172, 165], "trends": [124, 108, 214], "positivity": [54, 97, 176]}
SIGNAME = {"weather": "Breeding weather", "trends": "Google Search Interest", "positivity": "PharmEasy labs"}


def _beacon(band: str) -> str:
    """The pulsing risk beacon, byte-identical to the flows' beacon()."""
    return ('<span class="beacon" style="--c:' + RISK.get(band, "#888")
            + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')


def _search_hero_d(city: dict, generated_at: str) -> str:
    """Byte-identical to desktop.js searchHero(c) at first render (state.comboOpen = false). H1 drops the
    comma (keeps the city); the hero gets the mobile vertical-fade gradient (CSS) plus a centered
    Updated/date note below the search bar. Edit BOTH this and searchHero() together (CLS 0)."""
    nm = city["name"]
    return ('<section class="srch"><div class="srchin">'
            '<h1>Live monsoon-fever risk for ' + esc(nm) + ' in <em>one score</em>.</h1>'
            '<p class="subtitle">Dengue, malaria, chikungunya and typhoid, blended from breeding weather, Google Search interest and PharmEasy lab signals.</p>'
            '<div class="searchbar"><span class="ico">\U0001F50E</span>'
            '<button class="field" data-act="combo">\U0001F4CD ' + nm + '  <span class="ph">| change your city</span></button>'
            '<button class="searchbtn" data-act="combo">Search</button>'
            '<div class="combopanel"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>'
            '</div><p class="microcopy">Available in select cities.</p>'
            '<p class="searchnote loc-note">Updated ' + _fmt_date_js(generated_at) + '. Available in selected cities.</p></div></section>')


def _week_section_d(city: dict, diseases: list, cells_by: dict, periods: list) -> str:
    """Desktop s-week above-fold twin. REUSES _risk_card verbatim (the mobile-proven proportional identity
    dial + legend + band chip + period tabs), wrapped in the desktop section. Byte-identical to
    desktop.js weekSectionD(c, b)."""
    return ('<section id="s-week"><h2 class="sechead">Overall fever risk in ' + esc(city["name"]) + '</h2>'
            + _risk_card(city, diseases, cells_by, periods) + '</section>')


def _desktop_pre(city: dict, diseases: list, cells_by: dict, generated_at: str, periods: list) -> str:
    """Desktop seamless first paint. Server-render .srch + .shell{.toc + .main{s-week}} so it is
    byte-identical to what desktop.js render() paints from the inlined seed; hydration is then a no-op
    repaint over identical above-fold DOM (kills the desktop CLS). The .fw-below SEO block underneath
    stays for crawlers / no-JS. Mirrors the mobile _mobile_pre / _risk_card pattern. Gated .fw-pre-d."""
    # NOTE: this TOC must stay byte-identical to desktop.js render()'s .toc so desktop hydration is a
    # no-op repaint (CLS 0). Edit BOTH together. The data-jump set MUST equal desktop.js spyScroll()'s
    # ids array, with one section id per jump target and vice-versa (s-method is reached via "Know more",
    # so it is intentionally NOT a TOC jump target).
    toc = ('<aside class="toc">'
           '<a class="cur" data-jump="s-week">Overall fever risk</a><a data-jump="s-why">Why this score</a>'
           '<a data-jump="s-weather">Breeding weather</a><a data-jump="s-do">Take the right precautions</a>'
           '<a data-jump="s-trend">This year vs last year</a><a data-jump="s-other">City-level insights</a>'
           '<a data-jump="s-faq">Common questions</a><a data-jump="s-reads">Monsoon reads</a></aside>')
    return ('<div class="fw-pre fw-pre-d">' + _search_hero_d(city, generated_at)
            + '<div class="shell">' + toc + '<div class="main">'
            + _week_section_d(city, diseases, cells_by, periods) + '</div></div></div>')


# --- "This monsoon vs last year" trend module (static SSR; mirrors assets/js/trend.js) -----------
# The series math below is intentionally identical to assets/js/trend.js metricSeries()/build(). Edit
# BOTH and keep them in sync. Here we bake only the static "Overall" chart + verdict for crawlers and
# no-JS; the JS widget owns the interactive flows (tabs, tooltip, collapse, desktop small-multiples).
TREND_SHAPE = [0.60, 0.63, 0.66, 0.69, 0.73, 0.77, 0.81, 0.85, 0.89, 0.92, 0.95, 0.97, 0.99, 1.00,
               0.96, 0.91, 0.86, 0.81, 0.78, 0.75, 0.73, 0.71]
TREND_NW = len(TREND_SHAPE)
TREND_PEAK = 13
TREND_MONTHS = ["Jun", "Jul", "Aug", "Sep", "Oct"]  # equidistant HTML axis labels (mirrors trend.js MONTHS_ROW)
TREND_ZONES = [(70, 100, "#E4572E"), (45, 69, "#E8923A"), (25, 44, "#C7A93C"), (0, 24, "#2FA66F")]
_TW, _TH, _TPADL, _TPADR, _TPADT, _TPADB = 340, 110, 26, 12, 6, 4  # compact; left gutter for y-axis; HTML month labels; y zooms (see _trend_chart_static)


def _t_r(x) -> int:
    return int(math.floor((x or 0) + 0.5))


def _t_clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _t_hash(s: str) -> int:
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


# Last-year is a STABLE per-city, per-metric mock peak seeded ONLY from the city id (never from this
# year's score or the current week), so "last year peaked at X" never drifts; this year's real score
# floats against it. Band 64-95 = a plausible HIGH last-monsoon peak, tuned so most cities read calmly
# "below/around last year" with a modest "above" tail (all 3 verdicts kept). Mirrors trend.js lyPeak.
TREND_LY_MIN, TREND_LY_MAX = 64, 95


def _t_lypeak(cid: str, metric: str) -> int:
    return TREND_LY_MIN + _t_hash(cid + ":" + metric + ":lypeak") % (TREND_LY_MAX - TREND_LY_MIN + 1)


def _t_band(score: int) -> str:
    return "HIGH" if score >= 70 else "MODERATE" if score >= 45 else "LOW-MODERATE" if score >= 25 else "LOW"


def _t_mean(cells: list, key: str):
    vals = [c.get("signals", {}).get(key) for c in cells]
    vals = [v for v in vals if v is not None]
    return _t_r(sum(vals) / len(vals)) if vals else None


def _t_metric_series(cid: str, metric: str, V: int, asOf: int) -> dict:
    denom = TREND_SHAPE[asOf]
    ty = [_t_clamp(_t_r(V * TREND_SHAPE[w] / denom), 0, 100) for w in range(asOf + 1)]
    p_ly = _t_lypeak(cid, metric)  # fixed last-year peak (independent of V and asOf)
    ly = [_t_clamp(_t_r(p_ly * TREND_SHAPE[w]), 0, 100) for w in range(TREND_NW)]
    a, b = ty[asOf], ly[asOf]
    delta = _t_r((a - b) / b * 100) if b > 0 else 0
    slope = ty[asOf] - ty[asOf - 1] if asOf >= 1 else 0
    return {"now": V, "series": ty, "last": ly, "delta": delta, "slope": slope, "peak": ly[TREND_PEAK], "avail": True}


def _trend_series(city: dict, cells: list, generated_at: str) -> dict:
    cid = city["id"]
    blend = city["blend"]
    ga = generated_at or ""
    gy = int(ga[0:4]) if ga[0:4].isdigit() else 2026
    gm = int(ga[5:7]) if ga[5:7].isdigit() else 6
    gd = int(ga[8:10]) if ga[8:10].isdigit() else 1
    as_of = _t_clamp((datetime.date(gy, gm, gd) - datetime.date(gy, 6, 1)).days // 7, 0, TREND_NW - 1)
    weather_now, search_now, labs_now = _t_mean(cells, "weather"), _t_mean(cells, "trends"), _t_mean(cells, "positivity")
    metrics = {
        "overall": _t_metric_series(cid, "overall", blend["score"], as_of),
        "weather": {"avail": False} if weather_now is None else _t_metric_series(cid, "weather", weather_now, as_of),
        "search": {"avail": False} if search_now is None else _t_metric_series(cid, "search", search_now, as_of),
        "labs": {"avail": False} if labs_now is None else _t_metric_series(cid, "labs", labs_now, as_of),
    }
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
    context = "Last year peaked at " + str(ov["peak"]) + " (" + _t_band(ov["peak"]) + ") in late August."
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
        return {"below": "Breeding conditions are running below last year.",
                "above": "Breeding conditions are running hotter than last year.",
                "inline": "Breeding conditions are tracking last year."}[lvl]
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
    dot = ('<circle cx="' + str(_tf(_tX(model["asOf"]))) + '" cy="' + str(_tf(_tY(ty[-1], ymax)))
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
    labels = ('<text x="' + str(_tf(_tX(model["asOf"]))) + '" y="' + str(_tf(max(fs + 2, _tY(nv, ymax) - 7)))
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


def _trend_html(city: dict, diseases: list, cells_by: dict, generated_at: str) -> str:
    cid = city["id"]
    cells = [cells_by[(cid, d["id"])] for d in diseases if (cid, d["id"]) in cells_by]
    model = _trend_series(city, cells, generated_at)
    col = RISK[_t_band(model["metrics"]["overall"]["now"])]
    tone = model["tone"]
    tone_icon = {"below": "▼", "above": "▲", "inline": "≈"}[tone]
    tabs = ""
    for k, lbl in (("overall", "Overall"), ("weather", "Weather"), ("search", "Searches"), ("labs", "Labs")):
        on = k == "overall"
        avail = model["metrics"][k].get("avail")
        tabs += ('<button class="fwtrend-tab' + (" on" if on else "") + ("" if avail else " soon")
                 + '" data-tact="metric" data-metric="' + k + '"' + (' aria-current="true"' if on else "")
                 + '>' + lbl + ("" if avail else ' <i>soon</i>') + '</button>')
    months = '<div class="fwtrend-months">' + "".join('<span>' + m + '</span>' for m in TREND_MONTHS) + '</div>'
    # Title + subtitle OUTSIDE the card (matches the other page sections); the flow JS re-renders this.
    return ('<section id="s-trend" class="fwtrend-host">'
            '<div class="fwtrend-sectop"><div class="fwtrend-sechead">'
            '<h2 class="sechead">This monsoon vs last in ' + esc(city["name"]) + '</h2>'
            '<p class="secsub">Season trend</p></div>'
            '<button class="fwtrend-toggle" data-tact="toggle" aria-expanded="true"><span class="t">Hide</span>'
            '<span class="chev" aria-hidden="true"></span></button></div>'
            '<div class="card fwtrend open" data-metric="overall">'
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
            '<p class="fwtrend-sources">Sources: NASA POWER, Google Trends, PharmEasy labs. A risk indicator, not a case count.</p>'
            '</div></div></section>')


def render_content(city: dict, diseases: list, cells_by: dict, all_cities: list,
                   generated_at: str, disclaimer: str, rel: str, faq: list, periods: list) -> str:
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

    method_sec = ('<section><h2>How we calculate this</h2>' + METHOD_HTML
                  + '<p class="dashnote">' + esc(DASHBOARD_NOTE) + '</p></section>')

    acts = "".join(
        ('<li><a href="' + esc(h) + '"><strong>' + esc(t) + '</strong> - ' + esc(s) + '</a></li>')
        if h else ('<li><strong>' + esc(t) + '</strong> - ' + esc(s) + '</li>')
        for t, s, h in ACTIONS)
    do_sec = ('<section><h2>So, what should I do?</h2><ul class="fw-actions">' + acts + '</ul>'
              '<p><a class="fw-cta" href="' + esc(CTA_HREF) + '">' + esc(CTA_LABEL) + '</a></p></section>')

    other_sec = ('<section><h2>What is happening in other cities?</h2>'
                 '<p>Overall monsoon-fever risk this week across ' + str(len(all_cities))
                 + ' cities, highest first.</p>' + _cities_table(all_cities, rel) + '</section>')

    trend_sec = _trend_html(city, diseases, cells_by, generated_at)
    faq_sec = '<section><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'

    return (pre + '<div class="fw-fallback fw-below">' + why_sec + method_sec + do_sec
            + other_sec + trend_sec + faq_sec + reads_sec + '<p class="fw-disc">' + esc(MEDICAL_DISCLAIMER) + '</p></div>')


def render_landing(cfg: dict, all_cities: list, generated_at: str, disclaimer: str, faq: list) -> str:
    hero = (
        '<header class="fw-hero">'
        '<h1>Fever Watch: live monsoon-fever risk for your city, in one score.</h1>'
        '<p class="lede">' + esc(cfg["description"]) + '</p>'
        '<div class="fw-search" aria-hidden="true">Search your city</div>'
        '<p class="microcopy">Available in select cities.</p></header>'
    )
    other_sec = ('<section><h2>Monsoon fever risk by city, this week</h2>'
                 '<p>Overall risk across ' + str(len(all_cities)) + ' cities, highest first. Open any city for its full read.</p>'
                 + _cities_table(all_cities, "") + '</section>')
    method_sec = ('<section><h2>How we calculate this</h2>' + METHOD_HTML
                  + '<p class="dashnote">' + esc(DASHBOARD_NOTE) + '</p></section>')
    faq_sec = '<section><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'
    return ('<div class="fw-fallback">' + hero + other_sec + method_sec + faq_sec + reads_sec
            + '<p class="fw-disc">' + esc(disclaimer) + '</p></div>')


# --- page assembly -----------------------------------------------------------

def page(cfg: dict, grid: dict, cells_by: dict, city: dict | None, env: str, av: str) -> str:
    rel = "../" if city else ""
    diseases = grid["diseases"]
    generated_at = grid.get("generated_at", "")
    disclaimer = grid.get("disclaimer", "")
    if city:
        title = city["name"] + " monsoon fever risk this week | Dengue, malaria, typhoid | Fever Watch"
        desc = ("This week's dengue, malaria, chikungunya and typhoid risk for " + city["name"]
                + ", " + city["state"] + ": one decomposable score from breeding weather, search interest "
                "and lab positivity. A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"] + city["id"] + "/"
        faq = faq_items(city, diseases, cells_by, grid["cities"], generated_at)
        periods = grid.get("periods", ["today"])
        fallback = render_content(city, diseases, cells_by, grid["cities"], generated_at, disclaimer, rel, faq, periods)
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
        fw = {"city": city["id"], "gridUrl": rel + "data/grid.json", "base": rel,
              "logo": rel + "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"], "ver": av, "seed": seed}
        og_url = cfg["base_url"] + "assets/img/og/" + city["id"] + ".jpg"
        og_alt = city["name"] + " monsoon fever risk score card from Fever Watch"
    else:
        title = cfg["title"]
        desc = cfg["description"]
        canonical = cfg["base_url"]
        faq = faq_items_landing()
        fallback = render_landing(cfg, grid["cities"], generated_at, disclaimer, faq)
        fw = {"gridUrl": "data/grid.json", "base": "", "logo": "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"], "ver": av}
        og_url = cfg["base_url"] + cfg.get("og_image", "")
        og_alt = cfg.get("og_image_alt", "")
    # Cache-bust the per-city OG card on the social meta so platforms re-fetch the preview when
    # scores are recomputed (keyed on grid.generated_at). JSON-LD keeps the clean URL.
    ver = og_version(generated_at)
    og_meta = (og_url + "?v=" + ver) if (city and ver) else og_url
    return PAGE.format(
        lang=cfg.get("language", "en-IN"),
        head=head_meta(cfg, env, title, desc, canonical, rel, og_meta, og_alt),
        jsonld=jsonld(cfg, generated_at, diseases, city, og_url, faq),
        rel=rel, nav=nav_html(rel), ticker=ticker_html(grid["cities"], rel),
        fallback=fallback, footer=footer_html(),
        fw=json.dumps(fw, ensure_ascii=False).replace("</", "<\\/"), av=av,
    )


# --- site plumbing -----------------------------------------------------------

def write_robots(cfg: dict, env: str) -> None:
    rule = "Allow: /" if env == "production" else "Disallow: /"
    body = "User-agent: *\n" + rule + "\n\nSitemap: " + cfg["base_url"] + "sitemap.xml\n"
    _write("robots.txt", body)


def write_sitemap(cfg: dict, cities: list, generated_at: str) -> None:
    base, lm = cfg["base_url"], iso_date(generated_at)
    rows = ['  <url><loc>' + esc(base) + '</loc><lastmod>' + lm + '</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>']
    for c in cities:
        rows.append('  <url><loc>' + esc(base + c["id"] + "/") + '</loc><lastmod>' + lm
                    + '</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>')
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

    print("SITE_ENV=" + env + "  base_url=" + cfg["base_url"])
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
    shutil.copy(grid_path, os.path.join(DIST, "data", "grid.json"))

    # landing
    av = asset_version()
    _write("index.html", page(cfg, grid, cells_by, None, env, av))
    # cities
    for c in cities:
        _write(os.path.join(c["id"], "index.html"), page(cfg, grid, cells_by, c, env, av))

    write_robots(cfg, env)
    write_sitemap(cfg, cities, grid.get("generated_at", ""))
    write_manifest(cfg)

    print("Wrote %d pages (1 landing + %d cities) -> %s" % (len(cities) + 1, len(cities), DIST))
    print("robots.txt (%s), sitemap.xml (%d urls), site.webmanifest written." % (env, len(cities) + 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
