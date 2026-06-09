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
     "chikungunya, typhoid and viral fever), shown as one decomposable score per city and disease. "
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
    "mosquito-borne diseases, rainfall for waterborne typhoid, humidity and temperature swings for "
    "viral fever). That weather signal is then blended with population search interest and PharmEasy "
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
    "contamination and runoff proxy; temperature secondary.</li>"
    "<li><strong>Febrile</strong> (viral fever): humidity, day-to-day temperature variability, and rainfall.</li></ul>"
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

ACTIONS = [
    ("Monsoon precautions", "Cut breeding sites and bites"),
    ("Vaccination: does it work?", "What helps, what does not"),
    ("Fever? Follow our framework", "When to test, when to wait"),
    ("Not sure? Talk to a doctor", "Online consult on PharmEasy"),
]
CTA_LABEL, CTA_HREF = "Book a fever panel test", "https://pharmeasy.in/diagnostics"

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
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


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
                "assets/js/geo.js", "assets/js/share.js", "assets/js/fw-loader.js",
                "assets/js/mobile.js", "assets/js/desktop.js"):
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
            '<span class="fw-ticker-label"><span class="livedot"></span> Live this week</span>'
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
        '<span class="footdisc">Fever Watch is a risk indicator, not a diagnosis or a count of actual cases. Live weather via NASA POWER (public domain); Google search and lab signals are simulated in this preview.</span>'
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
            "description": "Daily dengue, malaria, chikungunya, typhoid and viral fever risk for "
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
    temp = str(int(round(w.get("temp_mean_c", 0)))); hum = str(int(round(w.get("humidity_pct", 0))))
    rain14 = str(int(round(w.get("rain_14d_mm", 0))))
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
         "Right now " + nm + "'s overall read is " + bs + "/100, which lands in the " + bb + " band - and " + dl + " is the main thing nudging it up (it's sitting at " + dsc + "). Think of the score as a daily snapshot of conditions across the five fevers we track, not a tally of who's actually sick, so it's a heads-up rather than a diagnosis. We recompute it every day; this one's from " + date_str + "."),
        ("Is dengue something to watch in " + nm + " this week?",
         "Dengue's at " + den_s + "/100 in " + nm + " (" + den_b + ") this week, which makes it the " + _ORD.get(drank, "biggest") + " concern of the five fevers here. " + den_mode[0].upper() + den_mode[1:] + ". Either way it's a risk signal built from breeding weather, search interest and lab data - not a count of cases or mosquitoes, and not a diagnosis."),
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


def _gauge_svg(score: int, color: str, size: int = 116) -> str:
    """Byte-for-byte the same SVG the flows' gauge() builds, so hydration is a no-op repaint."""
    sw = 11
    cx = size / 2.0
    r = (size - sw) / 2.0 - 1
    c = 2 * math.pi * r
    arc = 0.75
    track, gap = "%.1f" % (arc * c), "%.1f" % (c - arc * c)
    prog, c2 = "%.1f" % (max(0, min(100, score)) / 100.0 * arc * c), "%.1f" % (c * 2)
    cs, rs = _num(cx), _num(r)
    return ('<div class="gaugewrap" style="width:' + str(size) + 'px;height:' + str(size) + 'px">'
            '<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 ' + str(size) + ' ' + str(size) + '">'
            '<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="#e9eef5" stroke-width="' + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + track + ' ' + gap + '" transform="rotate(135 ' + cs + ' ' + cs + ')"/>'
            '<circle cx="' + cs + '" cy="' + cs + '" r="' + rs + '" fill="none" stroke="' + color + '" stroke-width="' + str(sw) + '" stroke-linecap="round" stroke-dasharray="' + prog + ' ' + c2 + '" transform="rotate(135 ' + cs + ' ' + cs + ')" style="transition:stroke-dasharray 1s ease"/>'
            '</svg><div class="num"><b style="color:' + color + '">' + str(score) + '</b><span>/ 100</span></div></div>')


def _risk_card(city: dict, diseases: list, cells_by: dict) -> str:
    """The .card risk card, identical to the flows' riskCard (shared classes, styled by both)."""
    cid = city["id"]; b = city["blend"]; band = b["band"]; col = RISK.get(band, "#888")
    drv = next((d for d in diseases if d["id"] == b["driver"]), diseases[0])
    dc = cells_by[(cid, b["driver"])]; db = dc["band"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    pills = "".join(
        '<span class="dpill"><span class="dot" style="background:' + RISK.get(cells_by[(cid, d["id"])]["band"], "#888")
        + '"></span>' + d["emoji"] + ' ' + esc(d["label"]) + ' <b>' + str(cells_by[(cid, d["id"])]["score"]) + '</b></span>'
        for d in ordered)
    beacon = '<span class="beacon" style="--c:' + col + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>'
    return ('<div class="card"><div class="rtop">' + _gauge_svg(b["score"], col, 116)
            + '<div class="rhead"><div class="ov">Overall monsoon-fever risk</div>'
            '<div class="bandlbl" style="color:' + col + '">' + beacon + band + '</div></div></div>'
            '<div class="driverrow"><span class="driver" style="background:' + RISK_SOFT.get(db, "#eee") + ';color:' + RISK.get(db, "#888")
            + '">Top concern: ' + drv["emoji"] + ' ' + esc(drv["label"]) + ' ' + db + ' (' + str(b["driver_score"]) + ')</span></div>'
            '<div class="pills">' + pills + '</div>'
            '<div class="rfoot"><span class="note">Scores modeled from breeding weather, Google search interest and PharmEasy lab signals.</span>'
            '<button class="sharebtn" data-act="openShare">⤴ Share</button></div></div>')


def _mobile_pre(city: dict, diseases: list, cells_by: dict, date_str: str) -> str:
    nm = esc(city["name"])
    return ('<div class="fw-pre fw-pre-m">'
            '<div class="hero"><h1>Live monsoon-fever risk for ' + nm + ', in <em>one score</em>.</h1>'
            '<p>Dengue, malaria, chikungunya, typhoid and viral fever, blended from breeding weather, Google search interest and PharmEasy lab signals.</p></div>'
            '<div class="searchwrap"><div class="searchfield" data-act="openCity"><span class="ico">\U0001F50E</span> Search your city</div>'
            '<p class="searchnote">Available in select cities, more coming soon.</p></div>'
            '<div class="wrap"><div class="citymeta"><div><h2>' + nm + '</h2><div class="date">This week, updated ' + date_str + '</div></div>'
            '<button class="changecity" data-act="openCity">Change</button></div>' + _risk_card(city, diseases, cells_by) + '</div></div>')


SIGCOL = {"weather": [21, 172, 165], "trends": [124, 108, 214], "positivity": [54, 97, 176]}
SIGNAME = {"weather": "Breeding weather", "trends": "Google Search Interest", "positivity": "PharmEasy labs"}


def _beacon(band: str) -> str:
    """The pulsing risk beacon, byte-identical to the flows' beacon()."""
    return ('<span class="beacon" style="--c:' + RISK.get(band, "#888")
            + ';--bdur:' + BEACON_DUR.get(band, "1.6s") + '"><i></i></span>')


def _search_hero_d(city: dict) -> str:
    """Byte-identical to desktop.js searchHero(c) at first render (state.comboOpen = false)."""
    nm = city["name"]
    return ('<section class="srch"><div class="srchin">'
            '<h1>Live monsoon-fever risk for ' + esc(nm) + ', in <em>one score</em>.</h1>'
            '<p class="subtitle">Dengue, malaria, chikungunya, typhoid and viral fever, blended from breeding weather, Google Search interest and PharmEasy lab signals.</p>'
            '<div class="searchbar"><span class="ico">\U0001F50E</span>'
            '<button class="field" data-act="combo">\U0001F4CD ' + nm + '  <span class="ph">| change your city</span></button>'
            '<button class="searchbtn" data-act="combo">Search</button>'
            '<div class="combopanel"><input id="cityinput" placeholder="Where are you from? Type a city" autocomplete="off"><div class="comboloc" data-act="useLoc">◎ Use my location</div><div class="combolist" id="combolist"></div></div>'
            '</div><p class="microcopy">Available in select cities, more coming soon.</p></div></section>')


_CAT = {"mosquito": "Mosquito-borne", "waterborne": "Water / food-borne", "febrile": "Viral, airborne"}


def _heatmap_card(city: dict, diseases: list, cells_by: dict) -> str:
    """Ranked composite bars, byte-identical to desktop.js heatmapCard(c): each fever as one composite bar
    (segment width = signal / sum * score, integer %; Math.round mirrored via floor(x+0.5)), ordered by
    score high to low, top concern flagged, score in its band colour."""
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    rows = ""
    for i, d in enumerate(ordered):
        cell = cells_by[(cid, d["id"])]; col = RISK.get(cell["band"], "#888"); sg = cell.get("signals", {})
        weather = sg.get("weather"); search = sg.get("trends"); labs = sg.get("positivity")
        wn = weather or 0; sn = search or 0; ln = labs or 0; denom = wn + sn + ln; sc = cell["score"]
        ww = int(math.floor(wn / denom * sc + 0.5)) if denom else 0
        ws = int(math.floor(sn / denom * sc + 0.5)) if denom else 0
        wl = int(math.floor(ln / denom * sc + 0.5)) if denom else 0
        wv = "n/a" if weather is None else str(weather)
        sv = "n/a" if search is None else str(search)
        lv = "n/a" if labs is None else str(labs)
        top = '<span class="sbar-top">Top concern</span>' if i == 0 else ''
        rows += ('<div class="sbar-row"><div class="sbar-id"><span class="sbar-rank">' + str(i + 1) + '</span><span class="sbar-emoji">' + d["emoji"] + '</span><span class="sbar-name"><b>' + d["label"] + '</b><i>' + _CAT.get(cell["family"], "") + '</i></span></div>'
                 + '<div class="sbar-mid"><div class="sbar-track"><span style="width:' + str(ww) + '%;background:#15ACA5"></span><span style="width:' + str(ws) + '%;background:#7C6CD6"></span><span style="width:' + str(wl) + '%;background:#3661B0"></span></div>'
                 + '<div class="sbar-strip"><span><i style="background:#15ACA5"></i>Weather ' + wv + '</span><span><i style="background:#7C6CD6"></i>Search ' + sv + '</span><span><i style="background:#3661B0"></i>Labs ' + lv + '</span></div></div>'
                 + '<div class="sbar-score" style="color:' + col + '">' + str(sc) + top + '</div></div>')
    return ('<div class="card sbars"><div class="sbar-head"><div class="sbar-title">This week\'s outbreak signal score</div><div class="sbar-sub">Ranked by composite score - five fevers we track in ' + city["name"] + '</div></div><div class="sbar-list">' + rows + '</div>'
            '<div class="sbar-legend"><span class="k"><span class="sw" style="background:#15ACA5"></span>Weather (leading)</span>'
            '<span class="k"><span class="sw" style="background:#7C6CD6"></span>Search (coincident)</span>'
            '<span class="k"><span class="sw" style="background:#3661B0"></span>Labs (ground truth)</span></div></div>')


def _week_section(city: dict, diseases: list, cells_by: dict, generated_at: str) -> str:
    """Byte-identical to desktop.js weekSection(c, b): the gauge card + heatmap inside .grid2."""
    cid = city["id"]; b = city["blend"]; band = b["band"]; col = RISK.get(band, "#888")
    drv_cell = cells_by[(cid, b["driver"])]
    drv = next((d for d in diseases if d["id"] == b["driver"]), diseases[0])
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    pills = "".join(
        '<span class="dpill"><span class="dot" style="background:' + RISK.get(cells_by[(cid, d["id"])]["band"], "#888")
        + '"></span>' + d["emoji"] + ' ' + d["label"] + ' <b>' + str(cells_by[(cid, d["id"])]["score"]) + '</b></span>'
        for d in ordered)
    card = ('<div class="card risk"><div class="rtop">' + _gauge_svg(b["score"], col, 112)
            + '<div class="rhead"><div class="ov">Overall monsoon-fever risk, this week</div>'
            '<div class="bandlbl" style="color:' + col + '">' + _beacon(band) + band + '</div></div></div>'
            '<div class="driverrow"><span class="driver" style="background:' + RISK_SOFT.get(drv_cell["band"], "#eee")
            + ';color:' + RISK.get(drv_cell["band"], "#888") + '">Top concern: ' + drv["emoji"] + ' ' + drv["label"]
            + ' ' + drv_cell["band"] + ' (' + str(b["driver_score"]) + ')</span></div>'
            '<div class="pills">' + pills + '</div>'
            '<div class="rfoot"><span class="note">Scores modeled from breeding weather, Google search interest and PharmEasy lab signals.</span>'
            '<button class="sharebtn" data-act="share">⤴ Share</button></div></div>')
    return ('<section id="s-week"><h2 class="sechead">' + city["name"] + ', this week</h2>'
            '<p class="secsub">Updated ' + _fmt_date_js(generated_at) + '. One headline score plus the signal mix behind it.</p>'
            '<div class="grid2">' + card + _heatmap_card(city, diseases, cells_by) + '</div></section>')


def _desktop_pre(city: dict, diseases: list, cells_by: dict, generated_at: str) -> str:
    """Desktop seamless first paint. Server-render .srch + .shell{.toc + .main{weekSection}} so it is
    byte-identical to what desktop.js render() paints from the inlined seed; hydration is then a no-op
    repaint over identical above-fold DOM (kills the desktop CLS). The .fw-below SEO block underneath
    stays for crawlers / no-JS. Mirrors the mobile _mobile_pre / _risk_card pattern. Gated .fw-pre-d."""
    toc = ('<aside class="toc">'
           '<a class="cur" data-jump="s-week">This week</a><a data-jump="s-method">Scoring methodology</a>'
           '<a data-jump="s-do">What to do</a><a data-jump="s-other">City-level insights</a>'
           '<a data-jump="s-faq">Common questions</a><a data-jump="s-reads">Monsoon reads</a></aside>')
    return ('<div class="fw-pre fw-pre-d">' + _search_hero_d(city)
            + '<div class="shell">' + toc + '<div class="main">'
            + _week_section(city, diseases, cells_by, generated_at) + '</div></div></div>')


def render_content(city: dict, diseases: list, cells_by: dict, all_cities: list,
                   generated_at: str, disclaimer: str, rel: str, faq: list) -> str:
    cid = city["id"]
    ordered = sorted(diseases, key=lambda d: cells_by[(cid, d["id"])]["score"], reverse=True)
    date_str = _fmt_date_js(generated_at)

    # Designed above-fold, server-rendered to match each flow's JS output, so the FIRST paint is the
    # product (gauge + pills) - not a plain list - and the flow hydrates over identical DOM (no flash).
    pre = _mobile_pre(city, diseases, cells_by, date_str) + _desktop_pre(city, diseases, cells_by, generated_at)

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

    method_sec = '<section><h2>How we calculate this</h2>' + METHOD_HTML + '</section>'

    acts = "".join('<li><strong>' + esc(t) + '</strong> - ' + esc(s) + '</li>' for t, s in ACTIONS)
    do_sec = ('<section><h2>So, what should I do?</h2><ul class="fw-actions">' + acts + '</ul>'
              '<p><a class="fw-cta" href="' + esc(CTA_HREF) + '">' + esc(CTA_LABEL) + '</a></p></section>')

    other_sec = ('<section><h2>What is happening in other cities?</h2>'
                 '<p>Overall monsoon-fever risk this week across ' + str(len(all_cities))
                 + ' cities, highest first.</p>' + _cities_table(all_cities, rel) + '</section>')

    faq_sec = '<section><h2>Common questions</h2>' + _faq_html(faq) + '</section>'
    reads_sec = '<section><h2>Further reading from PharmEasy</h2>' + _reads_html() + '</section>'

    return (pre + '<div class="fw-fallback fw-below">' + why_sec + method_sec + do_sec
            + other_sec + faq_sec + reads_sec + '<p class="fw-disc">' + esc(disclaimer) + '</p></div>')


def render_landing(cfg: dict, all_cities: list, generated_at: str, disclaimer: str, faq: list) -> str:
    hero = (
        '<header class="fw-hero">'
        '<h1>Fever Watch: live monsoon-fever risk for your city, in one score.</h1>'
        '<p class="lede">' + esc(cfg["description"]) + '</p>'
        '<div class="fw-search" aria-hidden="true">Search your city</div>'
        '<p class="microcopy">Available in select cities, more coming soon.</p></header>'
    )
    other_sec = ('<section><h2>Monsoon fever risk by city, this week</h2>'
                 '<p>Overall risk across ' + str(len(all_cities)) + ' cities, highest first. Open any city for its full read.</p>'
                 + _cities_table(all_cities, "") + '</section>')
    method_sec = '<section><h2>How we calculate this</h2>' + METHOD_HTML + '</section>'
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
        desc = ("This week's dengue, malaria, chikungunya, typhoid and viral fever risk for " + city["name"]
                + ", " + city["state"] + ": one decomposable score from breeding weather, search interest "
                "and lab positivity. A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"] + city["id"] + "/"
        faq = faq_items(city, diseases, cells_by, grid["cities"], generated_at)
        fallback = render_content(city, diseases, cells_by, grid["cities"], generated_at, disclaimer, rel, faq)
        # Inline per-city seed so the JS paints the designed view instantly (no wait for the ~850KB
        # grid). The full grid still loads in the background for the other-cities leaderboard.
        city_cells = [cells_by[(city["id"], d["id"])] for d in diseases if (city["id"], d["id"]) in cells_by]
        seed = {"generated_at": generated_at, "diseases": diseases, "bands": grid.get("bands", []),
                "trends_provider": grid.get("trends_provider"), "positivity_provider": grid.get("positivity_provider"),
                "cities": [city], "grid": city_cells, "faq": faq}
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
