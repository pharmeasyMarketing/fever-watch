#!/usr/bin/env python3
"""Per-city Open Graph score cards for Fever Watch.

Renders a 1200x630 share image per city from the current data/grid.json (city,
driver disease, score, band), so that when a city page is shared the social
preview shows that city's latest score card. Re-run whenever the data refreshes
(it is part of the daily build, before build_site.py). Writes
assets/img/og/{city}.png; build_site.py points each city page's og:image at it.

Needs Pillow. Run:  python src/build_og.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OG_DIR = os.path.join(ROOT, "assets", "img", "og")

GREEN = (16, 132, 126)
GREEN_DARK = (10, 83, 79)
WHITE = (255, 255, 255)
RISK = {"HIGH": (228, 87, 46), "MODERATE": (232, 146, 58), "LOW-MODERATE": (199, 169, 60), "LOW": (47, 166, 111)}

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    print("ABORT: Pillow is required for build_og.py (pip install Pillow).", file=sys.stderr)
    raise SystemExit(1)

_FONT_CACHE: dict = {}
_BOLD = ["arialbd.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
_REG = ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"]
_DIRS = ["", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/", "/Library/Fonts/"]


def font(size: int, bold: bool = True):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    names = _BOLD if bold else _REG
    f = None
    for d in _DIRS:
        for n in names:
            try:
                f = ImageFont.truetype(d + n, size)
                break
            except Exception:
                continue
        if f:
            break
    if f is None:
        try:
            f = ImageFont.load_default(size=size)   # Pillow >= 10.1
        except Exception:
            f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _text_w(draw, s, fnt) -> int:
    try:
        b = draw.textbbox((0, 0), s, font=fnt)
        return b[2] - b[0]
    except Exception:
        return draw.textlength(s, font=fnt) if hasattr(draw, "textlength") else len(s) * 10


def card(city: dict, drv_label: str, score: int, band: str) -> "Image.Image":
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    for y in range(H):  # diagonal-ish vertical gradient
        t = y / float(H)
        d.line([(0, y), (W, y)], fill=tuple(int(GREEN[i] + (GREEN_DARK[i] - GREEN[i]) * t) for i in range(3)))

    d.text((W // 2, 86), "FEVER WATCH  by PharmEasy", anchor="mm", font=font(40), fill=WHITE)

    d.text((W // 2, 250), str(score), anchor="mm", font=font(200), fill=WHITE)
    sw = _text_w(d, str(score), font(200))
    d.text((W // 2 + sw // 2 + 36, 290), "/100", anchor="mm", font=font(48), fill=(214, 238, 235))

    # band pill
    label = (band or "") + " RISK"
    pf = font(46)
    pw = _text_w(d, label, pf) + 80
    px0, py0, px1, py1 = (W - pw) // 2, 360, (W + pw) // 2, 432
    d.rounded_rectangle([px0, py0, px1, py1], radius=36, fill=WHITE)
    d.text((W // 2, (py0 + py1) // 2), label, anchor="mm", font=pf, fill=RISK.get(band, GREEN_DARK))

    d.text((W // 2, 500), drv_label + " risk in " + city["name"], anchor="mm", font=font(48), fill=WHITE)
    d.text((W // 2, 566), "Check your city at pharmeasy.in/fever-watch", anchor="mm", font=font(30, bold=False), fill=(206, 234, 232))
    return img


def main() -> int:
    grid_path = os.path.join(ROOT, "data", "grid.json")
    if not os.path.exists(grid_path):
        print("ABORT: data/grid.json not found. Run build_daily.py first.", file=sys.stderr)
        return 1
    with open(grid_path, "r", encoding="utf-8") as fh:
        grid = json.load(fh)
    cities, diseases = grid["cities"], grid["diseases"]
    cells = {(r["city"], r["disease"]): r for r in grid["grid"]}
    dis_by = {d["id"]: d for d in diseases}

    os.makedirs(OG_DIR, exist_ok=True)
    n = 0
    for city in cities:
        b = city["blend"]
        drv = dis_by.get(b["driver"], diseases[0])
        cell = cells.get((city["id"], b["driver"]), {})
        band = cell.get("band", b.get("band", "LOW"))
        img = card(city, drv["label"], b.get("driver_score", b.get("score", 0)), band)
        img.save(os.path.join(OG_DIR, city["id"] + ".png"), "PNG")
        n += 1
    print("Wrote %d per-city OG cards (1200x630) -> %s" % (n, OG_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
