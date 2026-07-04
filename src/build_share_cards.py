# -*- coding: utf-8 -*-
"""Per-city share cards: the WhatsApp/portrait image + the OG/landscape link preview.

Replaces build_og.py (the old Pillow glass card). Renders the 2026-06 approved design
(dual-QA'd + content-team signed off; design source = the prototype generators in
dist/_share_options/b_resvg/, specs in dist/_share_options/SPEC.md + LANDSCAPE_SPEC.md):

  assets/img/og/{city}.jpg     1200x630 landscape  (og:image - path contract unchanged)
  assets/img/share/{city}.jpg  1080x1440 portrait  (fetched by assets/js/share.js)

Stack: parametric SVG (all text pre-shaped to outlines via src/textshape.py - see its
docstring for why) -> vendored resvg binary (tools/resvg/, pinned v0.47.0) at 2x ->
Pillow LANCZOS downscale -> opaque JPEG. Regional sub-line ("{city}, {state}" in the
state language) + the WhatsApp bar's regional phrase come from the state->language map
below + grid.json name_local/state_local; cities without QA'd local names fall back to
the English variant. Run AFTER build_daily.py and BEFORE build_site.py.

Usage: python src/build_share_cards.py [--only city_id[,city_id]] [--out-root DIR]
"""
import argparse
import base64
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textshape import shape_to_path  # noqa: E402

GRID_PATH = os.path.join(ROOT, "data", "grid.json")
LOGO_SVG = os.path.join(ROOT, "assets", "img", "pe_logo-white.svg")
# build-only fonts live under tools/ (NOT assets/) so build_site's assets copytree
# never ships ~6.6MB of shaping TTFs to Pages
FONT_DIR = os.path.join(ROOT, "tools", "fonts")

F_SEMI = os.path.join(FONT_DIR, "Inter-SemiBold.ttf")     # 600
F_BOLD = os.path.join(FONT_DIR, "Inter-Bold.ttf")         # 700
F_XBOLD = os.path.join(FONT_DIR, "Inter-ExtraBold.ttf")   # 800

# state -> language variant (content-team approved 2026-06-12: Goa / J&K / Ladakh /
# Sikkim / Assam / A&N / Chandigarh fold into Hindi; NE states fall back to English).
LANG_BY_STATE = {}
for _lang, _states in {
    "hindi": ["Uttar Pradesh", "Bihar", "Madhya Pradesh", "Rajasthan", "Haryana", "Delhi",
              "Chhattisgarh", "Jharkhand", "Uttarakhand", "Himachal Pradesh", "Chandigarh",
              "Jammu and Kashmir", "Ladakh", "Andaman and Nicobar Islands", "Sikkim", "Goa", "Assam"],
    "marathi": ["Maharashtra"],
    "gujarati": ["Gujarat", "Dadra and Nagar Haveli and Daman and Diu"],
    "punjabi": ["Punjab"],
    "bengali": ["West Bengal", "Tripura"],
    "odia": ["Odisha"],
    "telugu": ["Andhra Pradesh", "Telangana"],
    "kannada": ["Karnataka"],
    "tamil": ["Tamil Nadu", "Puducherry"],
    "malayalam": ["Kerala"],
}.items():
    for _s in _states:
        LANG_BY_STATE[_s] = _lang

LANG_FONT = {
    "hindi": "NotoSansDevanagari-Variable.ttf",
    "marathi": "NotoSansDevanagari-Variable.ttf",
    "gujarati": "NotoSansGujarati-Variable.ttf",
    "punjabi": "NotoSansGurmukhi-Variable.ttf",
    "bengali": "NotoSansBengali-Variable.ttf",
    "odia": "NotoSansOriya-Variable.ttf",
    "telugu": "NotoSansTelugu-Variable.ttf",
    "kannada": "NotoSansKannada-Variable.ttf",
    "tamil": "NotoSansTamil-Variable.ttf",
    "malayalam": "NotoSansMalayalam-Variable.ttf",
}

# the regional half of the portrait WhatsApp bar (dual-QA'd + content-team approved)
FAM_PHRASE = {
    "hindi": "परिवार को भेजें",
    "marathi": "कुटुंबाला पाठवा",
    "gujarati": "પરિવારને મોકલો",
    "punjabi": "ਪਰਿਵਾਰ ਨੂੰ ਭੇਜੋ",
    "bengali": "পরিবারকে পাঠান",
    "odia": "ପରିବାରକୁ ପଠାନ୍ତୁ",
    "telugu": "కుటుంబానికి పంపండి",
    "kannada": "ಕುಟುಂಬಕ್ಕೆ ಕಳುಹಿಸಿ",
    "tamil": "குடும்பத்திற்கு அனுப்புங்கள்",
    "malayalam": "കുടുംബത്തിന് അയയ്ക്കൂ",
}

BAND_COLOR = {"LOW": "#3FA535", "LOW-MODERATE": "#C7361F", "MODERATE": "#E0612A", "HIGH": "#D8331C"}
DEVA_VAR = {"wght": 600}
CAP = 0.727  # Inter cap-height factor, used for baseline placement
URL = "pharmeasy.in/fever-watch"

IC_WARN = ('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
           '<path d="M12 9v4"/><path d="M12 17h.01"/>')
IC_DROP = ('<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5'
           'C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>')
IC_GLOBE = ('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
            '<path d="M2 12h20"/>')
IC_VIRUS = ('<circle cx="12" cy="12" r="5.5"/><path d="M12 3.5v3"/><path d="M12 17.5v3"/>'
            '<path d="M3.5 12h3"/><path d="M17.5 12h3"/><path d="m5.8 5.8 2.1 2.1"/>'
            '<path d="m16.1 16.1 2.1 2.1"/><path d="m18.2 5.8-2.1 2.1"/><path d="m7.9 16.1-2.1 2.1"/>'
            '<circle cx="10.2" cy="11" r=".6"/><circle cx="13.6" cy="13.2" r=".6"/>')
IC_WHATSAPP = ('<path fill="#25D366" d="M16 0a16 16 0 0 0-13.6 24.4L0 32l7.9-2.3A16 16 0 1 0 16 0z"/>'
               '<path fill="#fff" d="M23.4 19.3c-.4-.2-2.4-1.2-2.7-1.3-.4-.1-.6-.2-.9.2s-1 1.3-1.2 1.5'
               'c-.2.2-.4.3-.8.1a11 11 0 0 1-3.2-2 12 12 0 0 1-2.2-2.8c-.2-.4 0-.6.2-.8l.6-.7c.2-.2.3-.4'
               '.4-.7s0-.5 0-.7l-1.2-2.9c-.3-.7-.6-.6-.9-.6h-.7c-.2 0-.6.1-1 .5a4 4 0 0 0-1.2 3'
               'c0 1.7 1.3 3.4 1.5 3.7.2.2 2.5 3.9 6.1 5.4 3 1.3 3.6 1 4.3.9.7 0 2.3-.9 2.6-1.8'
               '.3-.9.3-1.6.2-1.8z"/>')


def is_regional(ch):
    o = ord(ch)
    return (0x0900 <= o <= 0x0DFF) or o in (0x200C, 0x200D)


def runs(text):
    """Split into (substr, regional?) runs; spaces/punctuation attach to the preceding run."""
    out, cur, cur_d = [], "", None
    for ch in text:
        d = is_regional(ch)
        if ch in " ,.":
            d = cur_d if cur_d is not None else d
        if cur_d is None:
            cur_d = d
        if d == cur_d:
            cur += ch
        else:
            out.append((cur, cur_d))
            cur, cur_d = ch, d
    if cur:
        out.append((cur, cur_d))
    return out


class Card:
    """One city's card painter. Holds the per-city data + the variant's regional font."""

    def __init__(self, ctx):
        self.c = ctx
        self.reg_font = ctx["reg_font"]  # may be None for the English variant

    def measure(self, text, font, size, variations=None):
        return self.text(text, 0, 0, font, size, "#000", measure_only=True)

    def text(self, text, x, y, font, size, color, anchor="start", letter=0.0, measure_only=False):
        """Pre-shaped text markup. Latin runs use `font`; regional runs use the variant font."""
        if letter:
            segs, adv = [], 0.0
            for ch in text:
                reg = is_regional(ch)
                fnt = (self.reg_font or font) if reg else font
                var = DEVA_VAR if reg else None
                gd, w = shape_to_path(ch, fnt, size, variations=var)
                segs.append((gd, w))
                adv += w + letter
            adv -= letter
            if measure_only:
                return adv
            if anchor == "middle":
                x -= adv / 2
            elif anchor == "end":
                x -= adv
            out, cx = [], x
            for gd, w in segs:
                out.append('<g transform="translate(%.3f,%.3f)" fill="%s">%s</g>' % (cx, y, color, gd))
                cx += w + letter
            return "".join(out)
        shaped, total = [], 0.0
        for sub, reg in runs(text):
            fnt = (self.reg_font or font) if reg else font
            var = DEVA_VAR if reg else None
            gd, w = shape_to_path(sub, fnt, size, variations=var)
            shaped.append((gd, w))
            total += w
        if measure_only:
            return total
        if anchor == "middle":
            x -= total / 2
        elif anchor == "end":
            x -= total
        out, cx = [], x
        for gd, w in shaped:
            out.append('<g transform="translate(%.3f,%.3f)" fill="%s">%s</g>' % (cx, y, color, gd))
            cx += w
        return "".join(out)


def icon(paths, size, color, sw, fill, ox, oy):
    sc = size / 24.0
    return ('<g transform="translate(%.2f,%.2f) scale(%.4f)" fill="%s" stroke="%s" '
            'stroke-width="%.2f" stroke-linecap="round" stroke-linejoin="round">%s</g>'
            % (ox, oy, sc, fill, color, sw, paths))


def gauge(value, ox, oy, w, r, sw, needle_base, hub):
    cx = w / 2
    cy = r + sw / 2 + 4
    h = cy + sw / 2 + 4

    def pt(t):
        phi = math.pi - t * math.pi
        return (cx + r * math.cos(phi), cy - r * math.sin(phi))

    g = ['<g transform="translate(%.2f,%.2f)">' % (ox, oy)]
    for t0, t1, col in ((0.005, 0.32, "#3FA535"), (0.345, 0.655, "#F4C82E"), (0.68, 0.995, "#E0421E")):
        x0, y0 = pt(t0)
        x1, y1 = pt(t1)
        g.append('<path d="M%.3f,%.3f A%.1f,%.1f 0 0 1 %.3f,%.3f" fill="none" '
                 'stroke="%s" stroke-width="%.1f" stroke-linecap="round"/>' % (x0, y0, r, r, x1, y1, col, sw))
    t = max(0, min(100, value)) / 100.0
    phi = math.pi - t * math.pi
    tip = (cx + (r - sw * 0.15) * math.cos(phi), cy - (r - sw * 0.15) * math.sin(phi))
    ba = phi + math.pi / 2
    b1 = (cx + needle_base * math.cos(ba), cy - needle_base * math.sin(ba))
    b2 = (cx - needle_base * math.cos(ba), cy + needle_base * math.sin(ba))
    g.append('<path d="M%.3f,%.3f L%.3f,%.3f L%.3f,%.3f Z" fill="#FFFFFF" stroke="#FFFFFF" '
             'stroke-width="2" stroke-linejoin="round"/>' % (b1[0], b1[1], tip[0], tip[1], b2[0], b2[1]))
    g.append('<circle cx="%.2f" cy="%.2f" r="%d" fill="#FFFFFF"/>' % (cx, cy, hub))
    g.append('</g>')
    return "".join(g), w, h, cx, cy


_LOGO_URI = None


def logo_uri():
    global _LOGO_URI
    if _LOGO_URI is None:
        with open(LOGO_SVG, "rb") as fh:
            _LOGO_URI = "data:image/svg+xml;base64," + base64.b64encode(fh.read()).decode()
    return _LOGO_URI


def svg_head(w, h, pill_dy, pill_std):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d"><defs>'
            '<radialGradient id="surf" cx="50%%" cy="22%%" r="80%%" gradientUnits="objectBoundingBox">'
            '<stop offset="0%%" stop-color="#13534C"/><stop offset="52%%" stop-color="#0C3B37"/>'
            '<stop offset="100%%" stop-color="#082A28"/></radialGradient>'
            '<linearGradient id="hdr" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%%" stop-color="#0E625A"/><stop offset="100%%" stop-color="#0A4A44"/></linearGradient>'
            '<filter id="pillshadow" x="-30%%" y="-40%%" width="160%%" height="200%%">'
            '<feDropShadow dx="0" dy="%d" stdDeviation="%d" flood-color="#000000" flood-opacity="0.25"/>'
            '</filter></defs>'
            '<rect x="0" y="0" width="%d" height="%d" fill="url(#surf)"/>' % (w, h, w, h, pill_dy, pill_std, w, h))


def header_bar(card, parts, W, side, topm, hdr_h, rx, logo_h, rule_h, fw_size, gap1, gap2, letter):
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.0f" rx="%d" fill="url(#hdr)" '
                 'stroke="#ffffff" stroke-opacity="0.08" stroke-width="1.5"/>' % (side, topm, W - 2 * side, hdr_h, rx))
    logo_w = logo_h * (121.0 / 24.0)
    fw_w = card.measure("Fever Watch", F_XBOLD, fw_size)
    gx = W / 2 - (logo_w + gap1 + 2 + gap2 + fw_w) / 2
    hcy = topm + hdr_h / 2
    parts.append('<image x="%.2f" y="%.2f" width="%.2f" height="%.2f" href="%s"/>'
                 % (gx, hcy - logo_h / 2, logo_w, logo_h, logo_uri()))
    rx_ = gx + logo_w + gap1
    parts.append('<rect x="%.2f" y="%.2f" width="2" height="%d" rx="2" fill="#ffffff" fill-opacity="0.45"/>'
                 % (rx_, hcy - rule_h / 2, rule_h))
    parts.append(card.text("Fever Watch", rx_ + 2 + gap2, hcy + fw_size * CAP / 2, F_XBOLD, fw_size, "#ffffff",
                           letter=letter))


def render_portrait(ctx):
    """1080x1440 WhatsApp/share card (approved 2026-06-11/12 design)."""
    card = Card(ctx)
    W, H = 1080, 1440
    CX, SIDE, TOPM, HDR_H, GAP = W / 2.0, 52.0, 56.0, 104.0, 8.0
    BODYW = W - 2 * SIDE
    ICON_AXIS = SIDE + 26.0 + 30.0
    TEXT_X = SIDE + 26.0 + 60.0 + 22.0
    p = [svg_head(W, H, 10, 15)]
    header_bar(card, p, W, SIDE, TOPM, HDR_H, 26, 62.0, 42, 38.0, 22.0, 20.0, -0.38)

    y = TOPM + HDR_H + 52 + GAP
    # updated row (thin-rule separator per the house no-middot rule)
    up = 22.0
    wa = card.measure("Updated today", F_SEMI, up)
    wc = card.measure(ctx["updated"], F_SEMI, up)
    halo, gA, gB, rsep = 13.0, 9.0, 14.0, 2.0
    ux = CX - (halo + gA + wa + gB + rsep + gB + wc) / 2
    uy = y + up * CAP
    dcy = uy - up * CAP / 2
    p.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="#43D17F" fill-opacity="0.18"/>' % (ux + halo / 2, dcy, 11.5))
    p.append('<circle cx="%.2f" cy="%.2f" r="6.5" fill="#43D17F"/>' % (ux + halo / 2, dcy))
    cur = ux + halo + gA
    p.append('<g fill-opacity="0.82">%s</g>' % card.text("Updated today", cur, uy, F_SEMI, up, "#ffffff"))
    cur += wa + gB
    p.append('<rect x="%.2f" y="%.2f" width="%.1f" height="18" rx="1" fill="#ffffff" fill-opacity="0.35"/>'
             % (cur, dcy - 9, rsep))
    cur += rsep + gB
    p.append('<g fill-opacity="0.82">%s</g>' % card.text(ctx["updated"], cur, uy, F_SEMI, up, "#ffffff"))
    y = uy + up * (1 - CAP) + 24 + GAP

    # city (size tiers for long names; freed height re-padded below to keep the anchor)
    n = len(ctx["city"])
    csize = 108.0 if n <= 9 else (84.0 if n <= 14 else 64.0)
    tier_pad = (108.0 - csize) * (CAP + 0.06)  # re-pads BOTH the cap height and the csize*0.06 advance
    cb = y + csize * CAP
    p.append(card.text(ctx["city"], CX, cb, F_XBOLD, csize, "#ffffff", anchor="middle", letter=-0.02 * csize))
    y = cb + csize * 0.06
    sub = 34.0
    y += 14
    sb = y + sub * 0.72
    p.append(card.text(ctx["citySub"], CX, sb, F_SEMI, sub, "#8FD6AE", anchor="middle"))
    y = sb + sub * 0.28

    # score title
    y += 28 + GAP + tier_pad
    st = 30.0
    st_w = card.measure("Monsoon Fever Risk Score", F_BOLD, st)
    sx = CX - (54 + 18 + st_w + 18 + 54) / 2
    p.append('<rect x="%.2f" y="%.2f" width="54" height="2" fill="#ffffff" fill-opacity="0.25"/>' % (sx, y + st / 2 - 1))
    p.append(card.text("Monsoon Fever Risk Score", sx + 54 + 18, y + st * CAP, F_BOLD, st, "#ffffff"))
    p.append('<rect x="%.2f" y="%.2f" width="54" height="2" fill="#ffffff" fill-opacity="0.25"/>'
             % (sx + 54 + 18 + st_w + 18, y + st / 2 - 1))
    y += st

    # gauge + 0/100 + score
    y += 16 + GAP
    gw = 416.0
    gox = CX - gw / 2
    gm, _, gH, gcx, gcy = gauge(ctx["score"], gox, y, gw, 186.0, 40.0, 12.0, 13)
    p.append(gm)
    for lbl, lx in (("0", gox + gcx - 186.0), ("100", gox + gcx + 186.0)):
        p.append('<g fill-opacity="0.7">%s</g>' % card.text(lbl, lx, y + gcy + 58, F_BOLD, 26.0, "#ffffff", anchor="middle"))
    y += gH + 30
    y += 10
    s_str = str(ctx["score"])
    sw_s = card.text(s_str, 0, 0, F_XBOLD, 122.0, "#000", letter=-3.66, measure_only=True)
    sw_sl = card.measure("/100", F_BOLD, 46.0)
    sxx = CX - (sw_s + 8 + sw_sl) / 2
    s_base = y + 122.0 * CAP
    p.append(card.text(s_str, sxx, s_base, F_XBOLD, 122.0, "#F5C518", letter=-3.66))
    p.append(card.text("/100", sxx + sw_s + 8, s_base, F_BOLD, 46.0, "#ffffff"))
    y = s_base + 122.0 * 0.10

    # prev pill (omitted gracefully until history.json has a comparable day; its
    # vertical budget is redistributed so the card stays bottom-anchored)
    if ctx["prev"] is not None:
        y += 18 + GAP
        word = "Up" if ctx["score"] >= ctx["prev"] else "Down"
        pt_text = "%s from %d last week" % (word, ctx["prev"])
        ptw = card.measure(pt_text, F_XBOLD, 25.0)
        pw = 22 + 22 + 10 + ptw + 22
        ph = 12 + 25 + 12
        px = CX - pw / 2
        p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" fill="#F5C518"/>' % (px, y, pw, ph, ph / 2))
        pcy = y + ph / 2
        p.append(icon(IC_WARN, 22.0, "#0A2E2C", 2.2, "none", px + 22, pcy - 11))
        p.append(card.text(pt_text, px + 22 + 22 + 10, pcy + 25.0 * CAP / 2, F_XBOLD, 25.0, "#0A2E2C"))
        y += ph
        band_gap, info_gap = 16.0, 36.0
    else:
        band_gap, info_gap = 16.0 + 40.0, 36.0 + 35.0  # redistribute the pill's 75px budget

    # band pill
    y += band_gap + GAP
    bcol = BAND_COLOR[ctx["band"]]
    btw = card.text(ctx["band"], 0, 0, F_XBOLD, 44.0, "#000", letter=0.44, measure_only=True)
    bw = 40 + 30 + 16 + btw + 40
    bh = 16 + 44 + 16
    bx = CX - bw / 2
    p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" fill="#ffffff" filter="url(#pillshadow)"/>'
             % (bx, y, bw, bh, bh / 2))
    bcy = y + bh / 2
    p.append(icon(IC_DROP, 30.0, "#E0421E", 0, "#E0421E", bx + 40, bcy - 15))
    p.append(card.text(ctx["band"], bx + 40 + 30 + 16, bcy + 44.0 * CAP / 2, F_XBOLD, 44.0, bcol, letter=0.44))
    y += bh

    # info row (top concern) + dotted deco
    y += info_gap + GAP
    ir_h = 17 + 60 + 17
    p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="20" fill="#ffffff" fill-opacity="0.05" '
             'stroke="#ffffff" stroke-opacity="0.12" stroke-width="1.5"/>' % (SIDE, y, BODYW, ir_h))
    icy = y + ir_h / 2
    p.append('<circle cx="%.2f" cy="%.2f" r="30" fill="#062624" fill-opacity="0.55" '
             'stroke="#9FE3D6" stroke-opacity="0.5" stroke-width="1.5"/>' % (ICON_AXIS, icy))
    p.append('<circle cx="%.2f" cy="%.2f" r="27.5" fill="none" stroke="#ffffff" stroke-opacity="0.03" '
             'stroke-width="4"/>' % (ICON_AXIS, icy))
    p.append(icon(IC_VIRUS, 30.0, "#9FE3D6", 1.9, "none", ICON_AXIS - 15, icy - 15))
    blk = 24 * 0.72 + 12 + 36 * 0.72
    btop = icy - blk / 2
    p.append('<g fill-opacity="0.62">%s</g>' % card.text("Top concern today", TEXT_X, btop + 24 * 0.72, F_SEMI, 24.0, "#ffffff"))
    p.append(card.text(ctx["topConcern"], TEXT_X, btop + 24 * 0.72 + 12 + 36 * 0.78, F_XBOLD, 36.0, "#ffffff"))
    dots = []
    gright = SIDE + BODYW - 26.0
    gtop = icy - 16.0
    for rr in range(3):
        for cc in range(7):
            dots.append('<circle cx="%.2f" cy="%.2f" r="3"/>' % (gright - 96 + cc * 16, gtop + rr * 16))
    p.append('<g fill="#9FE3D6" fill-opacity="0.30">%s</g>' % "".join(dots))
    y += ir_h

    # gold CTA (left-axis aligned with the info row, per the approved portrait)
    y += 28 + GAP
    cta_h = 18 + 48 + 18
    p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="18" fill="#F5C518"/>' % (SIDE, y, BODYW, cta_h))
    gcy2 = y + cta_h / 2
    p.append('<circle cx="%.2f" cy="%.2f" r="24" fill="#0A2E2C" fill-opacity="0.12"/>' % (ICON_AXIS, gcy2))
    p.append(icon(IC_GLOBE, 26.0, "#0A2E2C", 2.2, "none", ICON_AXIS - 13, gcy2 - 13))
    pre = "Check your city at "
    p.append(card.text(pre, TEXT_X, gcy2 + 26.0 * CAP / 2, F_BOLD, 26.0, "#0A2E2C"))
    p.append(card.text(URL, TEXT_X + card.measure(pre, F_BOLD, 26.0), gcy2 + 26.0 * CAP / 2, F_XBOLD, 26.0, "#0A2E2C"))
    y += cta_h

    # white WhatsApp bar (regional phrase after a thin rule; English-only when no phrase)
    y += 14
    w2 = 27.0
    w2_h = 16 + max(34, int(w2) + 8) + 16
    p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="18" fill="#ffffff"/>' % (SIDE, y, BODYW, w2_h))
    wcy = y + w2_h / 2
    p.append('<g transform="translate(%.2f,%.2f) scale(%.4f)">%s</g>'
             % (ICON_AXIS - 17, wcy - 17, 34 / 32.0, IC_WHATSAPP))
    fb = wcy + w2 * CAP / 2
    if ctx["fam"]:
        en = "Send to your family group"
        p.append(card.text(en, TEXT_X, fb, F_XBOLD, w2, "#0A2E2C"))
        rx0 = TEXT_X + card.measure(en, F_XBOLD, w2) + 16
        p.append('<rect x="%.2f" y="%.2f" width="2" height="26" rx="1" fill="#0A2E2C" fill-opacity="0.3"/>'
                 % (rx0, wcy - 13))
        p.append(card.text(ctx["fam"], rx0 + 2 + 16, fb, F_XBOLD, w2, "#0A2E2C"))
    else:
        p.append(card.text("Send to your family group", TEXT_X, fb, F_XBOLD, w2, "#0A2E2C"))
    y += w2_h
    if y > H - 30:
        raise RuntimeError("portrait overflow for %s: bottom y=%d" % (ctx["id"], y))
    p.append('</svg>')
    return "".join(p)


def render_landscape(ctx):
    """1200x630 OG link-preview card (approved 2026-06-12 design, centered gold CTA)."""
    card = Card(ctx)
    W, H = 1200, 630
    SIDE, TOPM, HDR_H = 48.0, 36.0, 84.0
    LX, LW = 60.0, 560.0
    ICON_AXIS = LX + 20.0 + 30.0
    TEXT_X = LX + 20.0 + 60.0 + 18.0
    RCX = 888.0
    p = [svg_head(W, H, 8, 12)]
    header_bar(card, p, W, SIDE, TOPM, HDR_H, 22, 46.0, 32, 30.0, 18.0, 16.0, -0.3)

    # left column
    up = 18.0
    uy = TOPM + HDR_H + 50.0
    dcy = uy - up * CAP / 2
    cur = LX
    p.append('<circle cx="%.2f" cy="%.2f" r="9.5" fill="#43D17F" fill-opacity="0.18"/>' % (cur + 5.5, dcy))
    p.append('<circle cx="%.2f" cy="%.2f" r="5.5" fill="#43D17F"/>' % (cur + 5.5, dcy))
    cur += 11 + 8
    p.append('<g fill-opacity="0.82">%s</g>' % card.text("Updated today", cur, uy, F_SEMI, up, "#ffffff"))
    cur += card.measure("Updated today", F_SEMI, up) + 12
    p.append('<rect x="%.2f" y="%.2f" width="2" height="14" rx="1" fill="#ffffff" fill-opacity="0.35"/>' % (cur, dcy - 7))
    cur += 2 + 12
    p.append('<g fill-opacity="0.82">%s</g>' % card.text(ctx["updated"], cur, uy, F_SEMI, up, "#ffffff"))

    n = len(ctx["city"])
    csize = 92.0 if n <= 9 else (68.0 if n <= 14 else 52.0)
    cb = uy + 28 + csize * CAP
    p.append(card.text(ctx["city"], LX, cb, F_XBOLD, csize, "#ffffff", letter=-0.02 * csize))
    sb = cb + 24 + 30.0 * 0.72
    p.append(card.text(ctx["citySub"], LX, sb, F_SEMI, 30.0, "#8FD6AE"))
    tier_pad = (92.0 - csize) * CAP
    stb = sb + 52.0 + tier_pad
    st_cy = stb - 22.0 * CAP / 2
    p.append('<rect x="%.2f" y="%.2f" width="40" height="2" fill="#ffffff" fill-opacity="0.25"/>' % (LX, st_cy - 1))
    p.append(card.text("Monsoon Fever Risk Score", LX + 52, stb, F_BOLD, 22.0, "#ffffff"))
    stw = card.measure("Monsoon Fever Risk Score", F_BOLD, 22.0)
    p.append('<rect x="%.2f" y="%.2f" width="40" height="2" fill="#ffffff" fill-opacity="0.25"/>' % (LX + 52 + stw + 12, st_cy - 1))

    ir_y = stb + 34.0
    ir_h = 16 + 60 + 16
    p.append('<rect x="%.2f" y="%.2f" width="%.1f" height="%.1f" rx="16" fill="#ffffff" fill-opacity="0.05" '
             'stroke="#ffffff" stroke-opacity="0.12" stroke-width="1.5"/>' % (LX, ir_y, LW, ir_h))
    icy = ir_y + ir_h / 2
    p.append('<circle cx="%.2f" cy="%.2f" r="30" fill="#062624" fill-opacity="0.55" '
             'stroke="#9FE3D6" stroke-opacity="0.5" stroke-width="1.5"/>' % (ICON_AXIS, icy))
    p.append('<circle cx="%.2f" cy="%.2f" r="27.5" fill="none" stroke="#ffffff" stroke-opacity="0.03" '
             'stroke-width="4"/>' % (ICON_AXIS, icy))
    p.append(icon(IC_VIRUS, 28.0, "#9FE3D6", 1.9, "none", ICON_AXIS - 14, icy - 14))
    blk = 18 * 0.72 + 10 + 28 * 0.72
    btop = icy - blk / 2
    p.append('<g fill-opacity="0.62">%s</g>' % card.text("Top concern today", TEXT_X, btop + 18 * 0.72, F_SEMI, 18.0, "#ffffff"))
    p.append(card.text(ctx["topConcern"], TEXT_X, btop + 18 * 0.72 + 10 + 28 * 0.78, F_XBOLD, 28.0, "#ffffff"))

    cta_y = ir_y + ir_h + 24.0
    cta_h = 13 + 48 + 13
    p.append('<rect x="%.2f" y="%.2f" width="%.1f" height="%.1f" rx="14" fill="#F5C518"/>' % (LX, cta_y, LW, cta_h))
    gcy2 = cta_y + cta_h / 2
    pre = "Check your city at "
    pre_w = card.measure(pre, F_BOLD, 20.0)
    url_w = card.measure(URL, F_XBOLD, 20.0)
    grp_x = LX + (LW - (48 + 18 + pre_w + url_w)) / 2
    p.append('<circle cx="%.2f" cy="%.2f" r="24" fill="#0A2E2C" fill-opacity="0.12"/>' % (grp_x + 24, gcy2))
    p.append(icon(IC_GLOBE, 24.0, "#0A2E2C", 2.2, "none", grp_x + 12, gcy2 - 12))
    ctx_x = grp_x + 48 + 18
    p.append(card.text(pre, ctx_x, gcy2 + 20.0 * CAP / 2, F_BOLD, 20.0, "#0A2E2C"))
    p.append(card.text(URL, ctx_x + pre_w, gcy2 + 20.0 * CAP / 2, F_XBOLD, 20.0, "#0A2E2C"))

    # right column
    g_top = 158.0
    gm, _, gH, gcx, gcy = gauge(ctx["score"], RCX - 180.0, g_top, 360.0, 158.0, 36.0, 10.0, 12)
    p.append(gm)
    acy = g_top + gcy
    for lbl, lx in (("0", RCX - 158.0), ("100", RCX + 158.0)):
        p.append('<g fill-opacity="0.7">%s</g>' % card.text(lbl, lx, acy + 46, F_BOLD, 20.0, "#ffffff", anchor="middle"))
    s_str = str(ctx["score"])
    sw_s = card.text(s_str, 0, 0, F_XBOLD, 96.0, "#000", letter=-2.9, measure_only=True)
    sw_sl = card.measure("/100", F_BOLD, 36.0)
    s_base = acy + 46 + 26 + 96.0 * CAP
    sxx = RCX - (sw_s + 10 + sw_sl) / 2
    p.append(card.text(s_str, sxx, s_base, F_XBOLD, 96.0, "#F5C518", letter=-2.9))
    p.append(card.text("/100", sxx + sw_s + 10, s_base, F_BOLD, 36.0, "#ffffff"))
    bcol = BAND_COLOR[ctx["band"]]
    btw = card.text(ctx["band"], 0, 0, F_XBOLD, 30.0, "#000", letter=0.3, measure_only=True)
    bw = 30 + 24 + 12 + btw + 30
    bh = 14 + 30 + 14
    by = s_base + 45.0
    bx = RCX - bw / 2
    p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" fill="#ffffff" filter="url(#pillshadow)"/>'
             % (bx, by, bw, bh, bh / 2))
    bcy = by + bh / 2
    p.append(icon(IC_DROP, 24.0, "#E0421E", 0, "#E0421E", bx + 30, bcy - 12))
    p.append(card.text(ctx["band"], bx + 30 + 24 + 12, bcy + 30.0 * CAP / 2, F_XBOLD, 30.0, bcol, letter=0.3))
    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------- pipeline

def resvg_path():
    name = "resvg-win64.exe" if os.name == "nt" else "resvg-linux-x86_64"
    path = os.path.join(ROOT, "tools", "resvg", name)
    if not os.path.exists(path):
        raise SystemExit("FATAL: vendored resvg binary missing: " + path)
    return path


def rasterize(svg, out_jpg, target_size, resvg, tmp_png):
    from PIL import Image
    r = subprocess.run([resvg, "--skip-system-fonts", "--zoom", "2", "-", tmp_png],
                       input=svg.encode("utf-8"), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("resvg failed: " + r.stderr.decode("utf-8", "replace")[:400])
    img = Image.open(tmp_png).convert("RGBA")
    img = img.resize(target_size, Image.LANCZOS)
    flat = Image.new("RGBA", img.size, (8, 42, 40, 255))
    flat.alpha_composite(img)
    # q75 + 4:2:0 chroma subsampling: ~40% lighter than the original q85/4:4:4 with no
    # visible difference on this card (large type on a dark surface) - verified at q70 too,
    # q75 keeps a safety margin against gradient banding.
    flat.convert("RGB").save(out_jpg, "JPEG", quality=75, optimize=True, progressive=True, subsampling=2)


def rasterize_push(svg, out_jpg, resvg, tmp_png, canvas=(1024, 512)):
    """Android push "big picture": render the SAME OG landscape card and FIT it (aspect preserved -
    gauge/circles stay round) into a strict 2:1 canvas, centred on the OG dark-green background.
    The OG is 1200x630 (~1.9:1) so it scales to ~975x512 with ~24px dark margins each side that blend
    into the card's own edge colour. resvg renders at 2x; Pillow LANCZOS downscales + composites."""
    from PIL import Image
    r = subprocess.run([resvg, "--skip-system-fonts", "--zoom", "2", "-", tmp_png],
                       input=svg.encode("utf-8"), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("resvg(push) failed: " + r.stderr.decode("utf-8", "replace")[:400])
    img = Image.open(tmp_png).convert("RGBA")
    cw, ch = canvas
    scale = min(cw / img.width, ch / img.height)            # contain (never crop / never stretch)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (cw, ch), (8, 42, 40, 255))     # same flat colour as the OG edge
    out.alpha_composite(img, ((cw - w) // 2, (ch - h) // 2))
    out.convert("RGB").save(out_jpg, "JPEG", quality=75, optimize=True, progressive=True, subsampling=2)


def fmt_date(iso):
    # generated_at is UTC; shift +5:30 so the share card shows the India calendar date (matches the page).
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(hours=5, minutes=30)
        return "%d %s %d" % (d.day, d.strftime("%b"), d.year)
    except (ValueError, AttributeError):
        return ""


def city_ctx(city, diseases, updated_label):
    blend = city.get("blend") or {}
    if not blend.get("band") or blend.get("score") is None or not blend.get("driver"):
        raise RuntimeError("city %s has an incomplete blend (band/score/driver) - refusing to render" % city["id"])
    lang = LANG_BY_STATE.get(city.get("state", ""))
    name_local, state_local = city.get("name_local"), city.get("state_local")
    if lang and name_local and state_local:
        city_sub = "%s, %s" % (name_local, state_local)
        reg_font = os.path.join(FONT_DIR, LANG_FONT[lang])
        fam = FAM_PHRASE[lang]
    else:
        city_sub = "%s, %s" % (city["name"], city.get("state", ""))
        reg_font, fam = None, None
    dlabel = {d["id"]: d["label"] for d in diseases}
    score = int(round(blend["score"]))
    # prev comes from grid.json blend.prev_score - build_daily.py owns the "last week" lookup
    # (nearest committed day to 7d back within 4-10d). Absent until history accrues. An EQUAL
    # score is dropped too: "Up from N" would be wrong and "no change" copy has no sign-off.
    prev = blend.get("prev_score")
    prev = int(round(prev)) if prev is not None else None
    if prev == score:
        prev = None
    return {
        "id": city["id"],
        "city": city["name"],
        "citySub": city_sub,
        "updated": updated_label,
        "score": score,
        "band": blend["band"],
        "topConcern": dlabel.get(blend["driver"], blend["driver"].title()),
        "prev": prev,
        "fam": fam,
        "reg_font": reg_font,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated city ids (default: all)")
    ap.add_argument("--out-root", default=ROOT, help="root for assets/img output (tests)")
    args = ap.parse_args()

    for f in [F_SEMI, F_BOLD, F_XBOLD, LOGO_SVG] + [os.path.join(FONT_DIR, v) for v in set(LANG_FONT.values())]:
        if not os.path.exists(f):
            raise SystemExit("FATAL: missing asset: " + f)
    with open(GRID_PATH, encoding="utf-8") as fh:
        grid = json.load(fh)
    date_str = fmt_date(grid.get("generated_at") or "")
    if not date_str:
        raise SystemExit("FATAL: grid.json generated_at missing/unparseable - the cards would say 'Today, '")
    updated_label = "Today, " + date_str
    cities = grid["cities"]
    if args.only:
        keep = set(args.only.split(","))
        cities = [c for c in cities if c["id"] in keep]
        if not cities:
            raise SystemExit("FATAL: --only matched no cities")

    og_dir = os.path.join(args.out_root, "assets", "img", "og")
    share_dir = os.path.join(args.out_root, "assets", "img", "share")
    push_dir = os.path.join(args.out_root, "assets", "img", "push")
    os.makedirs(og_dir, exist_ok=True)
    os.makedirs(share_dir, exist_ok=True)
    os.makedirs(push_dir, exist_ok=True)
    resvg = resvg_path()
    tmp_png = os.path.join(tempfile.gettempdir(), "fw_card_%d.png" % os.getpid())

    diseases = grid["diseases"]
    errors = []
    done = 0
    for city in cities:
        try:
            ctx = city_ctx(city, diseases, updated_label)
            # og stays 1200x630 (the og:image meta contract); the share portrait downsamples
            # to 900x1200 - WhatsApp recompresses past that anyway, and the modal loads faster
            lsvg = render_landscape(ctx)  # the OG card; the push image is the SAME card fit to 1024x512 (2:1)
            rasterize(lsvg, os.path.join(og_dir, city["id"] + ".jpg"), (1200, 630), resvg, tmp_png)
            rasterize(render_portrait(ctx), os.path.join(share_dir, city["id"] + ".jpg"), (900, 1200), resvg, tmp_png)
            rasterize_push(lsvg, os.path.join(push_dir, city["id"] + ".jpg"), resvg, tmp_png)
            done += 1
        except Exception as exc:  # collect everything, fail loud at the end
            errors.append("%s: %s" % (city["id"], exc))
    if os.path.exists(tmp_png):
        os.remove(tmp_png)
    print("share cards: %d cities x 3 layouts -> %s , %s , %s" % (done, og_dir, share_dir, push_dir))
    if errors:
        for e in errors:
            print("ERROR " + e, file=sys.stderr)
        raise SystemExit("FATAL: %d of %d cities failed - not publishing partial cards" % (len(errors), len(cities)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
