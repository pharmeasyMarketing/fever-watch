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

import json
import os
import shutil
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC_DIR)
DIST = os.path.join(ROOT, "dist", "fever-watch")

# The locked brand risk ramp (matches the JS RISK map and tokens.css --risk-*).
RISK = {"HIGH": "#E4572E", "MODERATE": "#E8923A", "LOW-MODERATE": "#C7A93C", "LOW": "#2FA66F"}

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
     "Fever Watch currently covers around 120 Indian cities, with more planned. Use the city search "
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

PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{head}
{jsonld}
<link rel="stylesheet" href="{rel}assets/css/tokens.css">
<link rel="stylesheet" href="{rel}assets/css/mobile.css" media="(max-width: 819px), (pointer: coarse)">
<link rel="stylesheet" href="{rel}assets/css/desktop.css" media="(min-width: 820px) and (pointer: fine)">
</head>
<body>
{nav}
<div id="fw-app">{fallback}</div>
{footer}
<script>window.FW = {fw};</script>
<script src="{rel}assets/js/geo.js" defer></script>
<script src="{rel}assets/js/share.js" defer></script>
<script src="{rel}assets/js/fw-loader.js" defer></script>
</body>
</html>
"""


def esc(s) -> str:
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def iso_date(iso) -> str:
    return (iso or "")[:10]


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
        '<a class="pe-logo" href="https://pharmeasy.in/" aria-label="PharmEasy home">'
        '<img class="navlock" src="' + rel + 'assets/img/fever-watch-lockup-white.svg" alt="PharmEasy Fever Watch"></a>'
        '<nav class="pe-topnav" id="pe-topnav" aria-label="PharmEasy">' + items + '</nav>'
        '<button type="button" class="pe-burger" aria-label="Open menu" aria-expanded="false" aria-controls="pe-topnav">&#9776;</button>'
        '</div></header>'
    )


FOOTER_COLS = [
    ("Company", [("About Us", "https://pharmeasy.in/about-us"), ("Careers", "https://pharmeasy.in/careers"),
                 ("Blog", "https://pharmeasy.in/blog"), ("Partner with PharmEasy", "https://pharmeasy.in/franchisestores")]),
    ("Our Services", [("Healthcare Products", "https://pharmeasy.in/health-care"), ("Lab Tests", "https://pharmeasy.in/diagnostics")]),
    ("Featured Categories", [
        ("Must Haves", "https://pharmeasy.in/health-care/top-products-9297"),
        ("Vitamin Store", "https://pharmeasy.in/health-care/fitness-supplements-623"),
        ("Sexual Wellness", "https://pharmeasy.in/health-care/sexual-wellness-575"),
        ("Personal Care", "https://pharmeasy.in/health-care/personal-care-877"),
        ("Homeopathy Care", "https://pharmeasy.in/health-care/homeopathy-care-12811"),
        ("Summer Store", "https://pharmeasy.in/health-care/summer-store-16709"),
        ("Health Food and Drinks", "https://pharmeasy.in/health-care/health-food-and-drinks-648"),
        ("Diabetes Essentials", "https://pharmeasy.in/health-care/diabetic-care-145"),
    ]),
    ("Need Help", [("Browse All Molecules", "https://pharmeasy.in/molecules"),
                   ("Browse All Cities & Areas", "https://pharmeasy.in/online-medicine-order/browse/areas"),
                   ("FAQs", "https://pharmeasy.in/help")]),
    ("Policy Info", [("Editorial Policy", "https://pharmeasy.in/legal/editorial-policy"),
                     ("Privacy Policy", "https://pharmeasy.in/legal/privacy-policy"),
                     ("Vulnerability Disclosure Policy", "https://pharmeasy.in/vulnerability-disclosure-policy"),
                     ("Terms and condition", "https://pharmeasy.in/terms-and-conditions"),
                     ("Declaration on Dark Pattern", "https://assets.pharmeasy.in/web-assets/legal/circulars/Axelia_Self-Declaration_Dark_Patterns.pdf"),
                     ("Customer Support Policy", "https://pharmeasy.in/customer-support-policy"),
                     ("Return Policy", "https://pharmeasy.in/return-policy"),
                     ("Smartbuy Policy", "https://pharmeasy.in/smartbuy-policy")]),
]
FOOTER_SOCIAL = [("Instagram", "https://www.instagram.com/pharmeasyapp/"), ("Facebook", "https://www.facebook.com/pharmeasy/"),
                 ("YouTube", "https://www.youtube.com/channel/UCDats_DLX-bGZH3-KGu8JhA"), ("Twitter", "https://www.twitter.com/pharmeasyapp/")]
FOOTER_PAYS = ["Visa", "Mastercard", "RuPay", "Maestro", "Diners", "Google Pay", "Paytm", "Amazon Pay", "PhonePe", "Mobikwik", "Airtel Money", "Ola Money"]
FOOTER_TRUST = ["100% NABL & ISO Certified Labs", "700+ Collection Centers", "7,000 Quality & Trained Phlebotomists"]


def footer_html() -> str:
    cols = "".join(
        '<div><h5>' + esc(h) + '</h5>' + "".join(
            '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(t) + '</a>' for t, u in links
        ) + '</div>' for h, links in FOOTER_COLS)
    social = "".join('<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(t) + '</a>' for t, u in FOOTER_SOCIAL)
    pays = "".join('<span class="paychip">' + esc(p) + '</span>' for p in FOOTER_PAYS)
    return (
        '<footer class="footer">'
        '<div class="footin">' + cols + '</div>'
        '<div class="footmeta"><div class="footsocial"><span>Follow us</span>' + social + '</div>'
        '<div class="footpay"><span>We accept</span>' + pays + '</div></div>'
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


def jsonld(cfg: dict, generated_at: str, diseases: list, city: dict | None, og_url: str) -> str:
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
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ_ITEMS]}
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


# --- baked fallback ----------------------------------------------------------

def render_fallback(city: dict, diseases: list, cells_by: dict, generated_at: str, disclaimer: str) -> str:
    blend = city["blend"]
    driver = next((d for d in diseases if d["id"] == blend["driver"]), diseases[0])
    ordered = sorted(diseases, key=lambda d: cells_by[(city["id"], d["id"])]["score"], reverse=True)
    rows = []
    for d in ordered:
        cell = cells_by[(city["id"], d["id"])]
        pos = cell.get("signals", {}).get("positivity")
        lab = ("lab positivity signal " + str(pos) + " / 100") if pos is not None else "no lab data yet (forecast only)"
        rows.append('<li><strong>' + esc(d["emoji"] + " " + d["label"]) + '</strong>: '
                    + str(cell["score"]) + ' / 100, ' + esc(cell["band"]) + ' risk (' + lab + ')</li>')
    faq = "".join('<details><summary>' + esc(q) + '</summary><p>' + esc(a) + '</p></details>' for q, a in FAQ_ITEMS)
    return (
        '<article class="fw-fallback">'
        '<h1>Monsoon fever risk in ' + esc(city["name"]) + ', ' + esc(city["state"]) + '</h1>'
        '<p>Overall risk this week is <strong>' + str(blend["score"]) + ' / 100 (' + esc(blend["band"]) + ')</strong>, '
        'driven by ' + esc(driver["emoji"] + " " + driver["label"]) + '. Updated ' + esc(iso_date(generated_at)) + '.</p>'
        '<h2>Risk by disease</h2><ul>' + "".join(rows) + '</ul>'
        '<h2>How this is calculated</h2><p>' + esc(METHOD_SUMMARY) + '</p>'
        '<h2>Common questions</h2>' + faq +
        '<p>' + esc(disclaimer) + '</p>'
        '</article>'
    )


# --- page assembly -----------------------------------------------------------

def page(cfg: dict, grid: dict, cells_by: dict, city: dict | None, env: str) -> str:
    rel = "../" if city else ""
    diseases = grid["diseases"]
    generated_at = grid.get("generated_at", "")
    disclaimer = grid.get("disclaimer", "")
    if city:
        title = city["name"] + " monsoon fever risk today | Dengue, malaria, typhoid | Fever Watch"
        desc = ("Today's dengue, malaria, chikungunya, typhoid and viral fever risk for " + city["name"]
                + ", " + city["state"] + ": one decomposable score from breeding weather, search interest "
                "and lab positivity. A risk indicator, not a diagnosis.")
        canonical = cfg["base_url"] + city["id"] + "/"
        fallback = render_fallback(city, diseases, cells_by, generated_at, disclaimer)
        fw = {"city": city["id"], "gridUrl": rel + "data/grid.json", "base": rel,
              "logo": rel + "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"]}
        og_url = cfg["base_url"] + "assets/img/og/" + city["id"] + ".png"
        og_alt = city["name"] + " monsoon fever risk score card from Fever Watch"
    else:
        title = cfg["title"]
        desc = cfg["description"]
        canonical = cfg["base_url"]
        fallback = ('<article class="fw-fallback"><h1>Fever Watch: monsoon fever risk for your city</h1>'
                    '<p>' + esc(cfg["description"]) + '</p>'
                    '<h2>Common questions</h2>'
                    + "".join('<details><summary>' + esc(q) + '</summary><p>' + esc(a) + '</p></details>' for q, a in FAQ_ITEMS)
                    + '<p>' + esc(disclaimer) + '</p></article>')
        fw = {"gridUrl": "data/grid.json", "base": "", "logo": "assets/img/pe_logo-white.svg", "canonicalBase": cfg["base_url"]}
        og_url = cfg["base_url"] + cfg.get("og_image", "")
        og_alt = cfg.get("og_image_alt", "")
    return PAGE.format(
        lang=cfg.get("language", "en-IN"),
        head=head_meta(cfg, env, title, desc, canonical, rel, og_url, og_alt),
        jsonld=jsonld(cfg, generated_at, diseases, city, og_url),
        rel=rel, nav=nav_html(rel), fallback=fallback, footer=footer_html(),
        fw=json.dumps(fw, ensure_ascii=False),
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
    _write("index.html", page(cfg, grid, cells_by, None, env))
    # cities
    for c in cities:
        _write(os.path.join(c["id"], "index.html"), page(cfg, grid, cells_by, c, env))

    write_robots(cfg, env)
    write_sitemap(cfg, cities, grid.get("generated_at", ""))
    write_manifest(cfg)

    print("Wrote %d pages (1 landing + %d cities) -> %s" % (len(cities) + 1, len(cities), DIST))
    print("robots.txt (%s), sitemap.xml (%d urls), site.webmanifest written." % (env, len(cities) + 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
