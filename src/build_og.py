#!/usr/bin/env python3
"""Per-city Open Graph + share cards for Fever Watch.

Renders a 1200x630 OG image per city from the current data/grid.json so that when
a city page is shared, the social preview shows that city's latest read. The same
design function (render_card) backs the portrait 1080x1350 share card, so the OG
card and the WhatsApp/Stories card stay visually identical. Re-run whenever the
data refreshes (part of the daily build, before build_site.py).

Design: dark textured teal background (gradient + rain + soft glow), co-branded
PharmEasy + Fever Watch lockup, the OVERALL city risk score as the hero number
(NOT a single disease), a band pill, and a frosted "glass" info card with the
Location and the Top-concern disease. assets/img/og/{city}.png; build_site.py
points each city page's og:image at it.

Needs Pillow. Run:  python src/build_og.py
"""
from __future__ import annotations

import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OG_DIR = os.path.join(ROOT, "assets", "img", "og")
LOGO_PNG = os.path.join(ROOT, "assets", "img", "pe_logo-white.png")

BG_TOP = (15, 96, 89)            # deep teal, top
BG_BOT = (6, 47, 44)             # deeper teal, bottom
WHITE = (255, 255, 255)
SOFT = (203, 230, 227)           # muted white for secondary text
ACCENT = (74, 201, 190)          # bright teal for /100, labels, url
GLASS_FILL = (255, 255, 255, 16)
GLASS_BORDER = (255, 255, 255, 48)
BADGE_FILL = (4, 34, 32, 165)    # dark teal circle behind an icon
PIN_HOLE = (9, 52, 48)           # approx composited badge colour (for the pin cutout)
RISK = {"HIGH": (228, 87, 46), "MODERATE": (232, 146, 58), "LOW-MODERATE": (199, 169, 60), "LOW": (47, 166, 111)}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:
    print("ABORT: Pillow is required for build_og.py (pip install Pillow).", file=sys.stderr)
    raise SystemExit(1)

_FONT_CACHE: dict = {}
_BOLD = ["arialbd.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
_SEMI = ["seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
_REG = ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"]
_EMOJI = ["seguiemj.ttf", "C:/Windows/Fonts/seguiemj.ttf", "NotoColorEmoji.ttf",
          "/System/Library/Fonts/Apple Color Emoji.ttc"]
_DIRS = ["", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/",
         "/usr/share/fonts/truetype/liberation/", "/Library/Fonts/"]


def font(size: int, weight: str = "bold"):
    key = (size, weight)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    names = {"bold": _BOLD, "semi": _SEMI, "reg": _REG}[weight]
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
            f = ImageFont.load_default(size=size)
        except Exception:
            f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def emoji_font(size: int):
    """A color-emoji font. Segoe UI Emoji (Windows) scales to any size; Noto Color
    Emoji (Linux/CI) is a bitmap font that only loads at fixed strike sizes, so try
    a range and let _emoji_img rescale the glyph."""
    key = ("emoji", size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    f = None
    for n in _EMOJI:
        for sz in (size, 137, 136, 128, 120, 109, 96, 72):
            try:
                f = ImageFont.truetype(n, sz)
                break
            except Exception:
                continue
        if f:
            break
    _FONT_CACHE[key] = f
    return f


def _w(draw, s, fnt) -> int:
    b = draw.textbbox((0, 0), s, font=fnt)
    return b[2] - b[0]


def _emoji_img(ch: str, px: int):
    """Render one emoji glyph to its own RGBA image (color), scaled to px tall."""
    ef = emoji_font(109)
    if ef is None:
        return None
    canvas = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    try:
        d.text((160, 160), ch, font=ef, embedded_color=True, anchor="mm")
    except Exception:
        return None
    bbox = canvas.getbbox()
    if not bbox:
        return None
    glyph = canvas.crop(bbox)
    w, h = glyph.size
    nw = max(1, int(w * px / h))
    return glyph.resize((nw, px), Image.LANCZOS)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _bg(W: int, H: int) -> "Image.Image":
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(BG_TOP, BG_BOT, y / float(H - 1)))
    img = img.convert("RGBA")
    # soft radial glow near the upper area for depth
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gr = int(W * 0.42)
    ImageDraw.Draw(glow).ellipse([W * 0.5 - gr, -gr * 0.7, W * 0.5 + gr, gr * 1.1],
                                 fill=(64, 170, 160, 60))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    # soft darker pools at the bottom corners (clouds / foliage hint)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dark)
    dd.ellipse([-W * 0.2, H * 0.82, W * 0.42, H * 1.25], fill=(0, 20, 19, 90))
    dd.ellipse([W * 0.62, H * 0.85, W * 1.2, H * 1.3], fill=(0, 20, 19, 90))
    img.alpha_composite(dark.filter(ImageFilter.GaussianBlur(60)))
    # rain streaks (deterministic)
    rain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rain)
    rng = random.Random(7)
    for _ in range(int(W * H / 9000)):
        x, y = rng.randint(0, W), rng.randint(0, int(H * 0.95))
        ln = rng.randint(int(H * 0.018), int(H * 0.04))
        rd.line([(x, y), (x - ln * 0.45, y + ln)], fill=(255, 255, 255, rng.randint(7, 16)), width=2)
    img.alpha_composite(rain)
    return img


def _lockup(img, d, cx_or_x, y_mid, logo_h, centered):
    gap = int(logo_h * 0.55)
    try:
        logo = Image.open(LOGO_PNG).convert("RGBA")
        lw = int(logo.width * logo_h / logo.height)
        logo = logo.resize((lw, logo_h), Image.LANCZOS)
    except Exception:
        logo, lw = None, 0
    fw_font = font(int(logo_h * 0.92), "semi")
    fw_txt = "Fever Watch"
    fw_w = _w(d, fw_txt, fw_font)
    total = (lw if logo else 0) + gap + 2 + gap + fw_w
    x = int(cx_or_x - total / 2) if centered else int(cx_or_x)
    if logo:
        img.paste(logo, (x, int(y_mid - logo_h / 2)), logo)
        x += lw + gap
    else:
        pe = font(int(logo_h * 1.05), "bold")
        d.text((x, y_mid), "PharmEasy", font=pe, fill=WHITE, anchor="lm")
        x += _w(d, "PharmEasy", pe) + gap
    d.line([(x, int(y_mid - logo_h * 0.62)), (x, int(y_mid + logo_h * 0.62))], fill=(255, 255, 255, 130), width=2)
    x += 2 + gap
    d.text((x, y_mid), fw_txt, font=fw_font, fill=WHITE, anchor="lm")


def _pill(img, d, x, y_mid, text, color, fsize, padx, h, align="center"):
    """Frosted white pill with band-colour text and a soft glow."""
    pf = font(fsize, "bold")
    tw = _w(d, text, pf)
    w = tw + padx * 2
    x0 = x if align == "left" else int(x - w / 2)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([x0 - 6, y_mid - h / 2 - 6, x0 + w + 6, y_mid + h / 2 + 6],
                                           radius=int(h / 2) + 6, fill=(255, 255, 255, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))
    d.rounded_rectangle([x0, int(y_mid - h / 2), x0 + w, int(y_mid + h / 2)], radius=int(h / 2), fill=WHITE)
    d.text((x0 + w / 2, y_mid), text, font=pf, fill=color, anchor="mm")


def _glass(img, box, radius):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=GLASS_FILL, outline=GLASS_BORDER, width=2)
    img.alpha_composite(layer)


def _badge(img, cx, cy, r):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=BADGE_FILL)
    img.alpha_composite(layer)


def _pin(d, cx, cy, size):
    """White map-pin icon centred at (cx, cy), about `size` tall."""
    r = size * 0.34
    ty = cy - size * 0.16
    d.ellipse([cx - r, ty - r, cx + r, ty + r], fill=WHITE)
    d.polygon([(cx - r * 0.84, ty + r * 0.42), (cx + r * 0.84, ty + r * 0.42), (cx, cy + size * 0.5)], fill=WHITE)
    hr = r * 0.42
    d.ellipse([cx - hr, ty - hr, cx + hr, ty + hr], fill=PIN_HOLE)


def _globe(d, cx, cy, r, color):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    d.ellipse([cx - r * 0.5, cy - r, cx + r * 0.5, cy + r], outline=color, width=2)
    d.line([(cx - r, cy), (cx + r, cy)], fill=color, width=2)


def _dashed(d, x0, x1, y, color, dash=10, gap=8, width=2):
    x = x0
    while x < x1:
        d.line([(x, y), (min(x + dash, x1), y)], fill=color, width=width)
        x += dash + gap


def _info_card(img, d, box, rows, label_f, vmax, vmin, badge_r, pad):
    """Glass card with stacked icon rows. rows = [(icon, label, value_str), ...].
    Each value is shrink-to-fit (then a 2-line comma split, then an ellipsis) so a
    long city + state never overflows the card, whatever the width."""
    x0, y0, x1, y1 = box
    _glass(img, box, radius=int((y1 - y0) * 0.12))
    n = len(rows)
    seg = (y1 - y0) / n
    bx = x0 + pad + badge_r
    tx = bx + badge_r + pad * 0.7
    max_w = (x1 - pad) - tx
    for i, (icon, label, value) in enumerate(rows):
        cy = int(y0 + seg * (i + 0.5))
        _badge(img, bx, cy, badge_r)
        if icon == "pin":
            _pin(d, bx, cy, badge_r * 1.15)
        else:
            g = _emoji_img(icon, int(badge_r * 1.2))
            if g:
                img.paste(g, (int(bx - g.width / 2), int(cy - g.height / 2)), g)
        lines, vf = _fit_value(d, value, max_w, vmax, vmin)
        lh = vf.size + 6
        block_h = label_f.size + 8 + lh * len(lines)
        ty = cy - block_h / 2
        d.text((tx, ty), label, font=label_f, fill=ACCENT, anchor="lt")
        vy = ty + label_f.size + 8
        for ln in lines:
            d.text((tx, vy), ln, font=vf, fill=WHITE, anchor="lt")
            vy += lh
        if i < n - 1:
            _dashed(d, tx, x1 - pad, int(y0 + seg * (i + 1)), (255, 255, 255, 55))


def _footer(img, d, W, H, top, align_left):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([0, top, W, H], fill=(255, 255, 255, 12))
    img.alpha_composite(layer)
    d.line([(0, top), (W, top)], fill=(255, 255, 255, 40), width=2)
    cy = int((top + H) / 2)
    fs = int((H - top) * 0.32)
    pre, url = "Check your city at ", "pharmeasy.in/fever-watch"
    pf = font(fs, "semi")
    uf = font(fs, "bold")
    gr = fs * 0.62
    total = gr * 2 + 16 + _w(d, pre, pf) + _w(d, url, uf)
    x = 64 if align_left else int((W - total) / 2)
    _globe(d, int(x + gr), cy, int(gr), ACCENT)
    x += gr * 2 + 16
    d.text((x, cy), pre, font=pf, fill=WHITE, anchor="lm")
    x += _w(d, pre, pf)
    d.text((x, cy), url, font=uf, fill=ACCENT, anchor="lm")


def _truncate(d, s, fnt, max_w):
    if _w(d, s, fnt) <= max_w:
        return s
    while s and _w(d, s + "…", fnt) > max_w:
        s = s[:-1]
    return (s + "…") if s else s


def _fit_value(d, text, max_w, max_size, min_size, weight="bold"):
    """Largest font (max..min) at which `text` fits one line; else a two-line comma
    split at that size; else (last resort) the min size with an ellipsis."""
    parts = text.split(", ", 1)
    size = int(max_size)
    while size >= int(min_size):
        f = font(size, weight)
        if _w(d, text, f) <= max_w:
            return [text], f
        if len(parts) == 2:
            l1, l2 = parts[0] + ",", parts[1]
            if _w(d, l1, f) <= max_w and _w(d, l2, f) <= max_w:
                return [l1, l2], f
        size -= 2
    f = font(int(min_size), weight)
    lines = [parts[0] + ",", parts[1]] if len(parts) == 2 else [text]
    return [_truncate(d, ln, f, max_w) for ln in lines], f


def render_card(ctx: dict, story: bool = False) -> "Image.Image":
    band = ctx["band"]
    rc = RISK.get(band, BG_BOT)
    loc = ctx["city"] + ", " + ctx["state"] if ctx.get("state") else ctx["city"]
    drv_emoji = ctx.get("driver_emoji") or "\U0001FA9F"

    if story:
        W, H = 1080, 1350
        img = _bg(W, H)
        d = ImageDraw.Draw(img)
        _lockup(img, d, W / 2, 120, 54, centered=True)
        g = _emoji_img(drv_emoji, 150)
        if g:
            img.paste(g, (int(W / 2 - g.width / 2), 230), g)
        d.text((W / 2, 430), "Monsoon Fever Risk Score", font=font(42, "semi"), fill=SOFT, anchor="mm")
        sf = font(250, "bold")
        sw = _w(d, str(ctx["score"]), sf)
        d.text((W / 2 - 56, 590), str(ctx["score"]), font=sf, fill=WHITE, anchor="mm")
        d.text((W / 2 - 56 + sw / 2 + 26, 640), "/100", font=font(70, "bold"), fill=ACCENT, anchor="lm")
        _pill(img, d, W / 2, 790, band + " RISK", rc, 58, 54, 100)
        card_box = (120, 905, 960, 1155)
        lf = font(30, "semi")
        rows = [("pin", "Location", loc), (drv_emoji, "Top concern", ctx["driver_label"])]
        _info_card(img, d, card_box, rows, lf, 46, 32, badge_r=58, pad=34)
        cg = _emoji_img("\U0001F4C5", 38)
        date_f = font(36, "semi")
        dw = _w(d, ctx["date"], date_f) + (cg.width + 12 if cg else 0)
        dx = int(W / 2 - dw / 2)
        if cg:
            img.paste(cg, (dx, 1200), cg)
            dx += cg.width + 12
        d.text((dx, 1219), ctx["date"], font=date_f, fill=SOFT, anchor="lm")
        _footer(img, d, W, H, 1262, align_left=False)
        return img.convert("RGB")

    W, H = 1200, 630
    img = _bg(W, H)
    d = ImageDraw.Draw(img)
    _lockup(img, d, 64, 76, 42, centered=False)
    lx = 80
    d.text((lx, 250), "Monsoon Fever Risk Score", font=font(34, "semi"), fill=SOFT, anchor="lm")
    sf = font(150, "bold")
    d.text((lx, 360), str(ctx["score"]), font=sf, fill=WHITE, anchor="lm")
    sw = _w(d, str(ctx["score"]), sf)
    d.text((lx + sw + 18, 392), "/100", font=font(46, "bold"), fill=ACCENT, anchor="lm")
    _pill(img, d, lx, 480, band + " RISK", rc, 40, 40, 76, align="left")
    card_box = (690, 150, 1150, 500)
    lf = font(27, "semi")
    rows = [("pin", "Location", loc), (drv_emoji, "Top concern", ctx["driver_label"])]
    _info_card(img, d, card_box, rows, lf, 40, 26, badge_r=50, pad=30)
    _footer(img, d, W, H, 562, align_left=True)
    return img.convert("RGB")


def _fmt_date(iso: str) -> str:
    iso = iso or ""
    try:
        y, m, dd = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
        return "This week, %d %s %d" % (dd, MONTHS[m - 1], y)
    except Exception:
        return "This week"


def ctx_for(city: dict, diseases: list, cells: dict) -> dict:
    b = city["blend"]
    dis_by = {d["id"]: d for d in diseases}
    drv = dis_by.get(b["driver"], diseases[0])
    return {
        "city": city["name"], "state": city.get("state", ""),
        "score": b.get("score", 0), "band": b.get("band", "LOW"),
        "driver_label": drv["label"], "driver_emoji": drv.get("emoji", ""),
    }


def main() -> int:
    grid_path = os.path.join(ROOT, "data", "grid.json")
    if not os.path.exists(grid_path):
        print("ABORT: data/grid.json not found. Run build_daily.py first.", file=sys.stderr)
        return 1
    with open(grid_path, "r", encoding="utf-8") as fh:
        grid = json.load(fh)
    cities, diseases = grid["cities"], grid["diseases"]
    cells = {(r["city"], r["disease"]): r for r in grid["grid"]}
    date = _fmt_date((grid.get("generated_at") or "")[:10])

    os.makedirs(OG_DIR, exist_ok=True)
    n = 0
    for city in cities:
        ctx = ctx_for(city, diseases, cells)
        ctx["date"] = date
        render_card(ctx, story=False).save(os.path.join(OG_DIR, city["id"] + ".png"), "PNG")
        n += 1
    print("Wrote %d per-city OG cards (1200x630) -> %s" % (n, OG_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
