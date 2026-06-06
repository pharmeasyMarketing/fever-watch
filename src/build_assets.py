#!/usr/bin/env python3
"""One-off generator for Fever Watch brand placeholder assets.

Emits the favicon / PWA icon / Open Graph image set the SSG <head> references, so
no page ships a broken link before the brand delivers final art. On-brand only
(PharmEasy green), deliberately simple. Uses Pillow if installed for nicer raster
output; otherwise falls back to a tiny stdlib PNG/ICO encoder (solid green), so
this runs with no third-party dependency.

Outputs into assets/img/:
    favicon.svg  favicon.ico  apple-touch-icon.png
    icon-192.png  icon-512.png  icon-maskable-512.png  og-fever-watch.png

Run:  python src/build_assets.py
"""
from __future__ import annotations

import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "assets", "img")

GREEN = (16, 132, 126)        # #10847E PharmEasy Porcelain Green
GREEN_DARK = (10, 83, 79)     # #0A534F
WHITE = (255, 255, 255)

try:
    from PIL import Image, ImageDraw  # type: ignore
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


# --- favicon.svg (always stdlib) ---------------------------------------------

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#10847E"/>'
    '<text x="32" y="44" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="30" '
    'font-weight="700" text-anchor="middle" fill="#ffffff">FW</text></svg>\n'
)


# --- stdlib PNG / ICO fallback -----------------------------------------------

def _png_solid(w: int, h: int, rgb) -> bytes:
    row = bytes([0]) + bytes(rgb) * w
    raw = row * h

    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _ico_from_png(png: bytes, size: int) -> bytes:
    dim = 0 if size >= 256 else size
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), 22)
    return header + entry + png


# --- Pillow rendering (nicer placeholders) -----------------------------------

def _thermometer(draw, cx, cy, scale, color=WHITE):
    """A simple thermometer emblem centered at (cx, cy)."""
    stem_w = int(10 * scale)
    stem_h = int(46 * scale)
    bulb_r = int(13 * scale)
    top = cy - stem_h // 2
    draw.rounded_rectangle([cx - stem_w // 2, top, cx + stem_w // 2, cy + stem_h // 2],
                           radius=stem_w // 2, fill=color)
    draw.ellipse([cx - bulb_r, cy + stem_h // 2 - bulb_r, cx + bulb_r, cy + stem_h // 2 + bulb_r], fill=color)
    draw.ellipse([cx - bulb_r // 2, cy + stem_h // 2 - bulb_r // 2, cx + bulb_r // 2, cy + stem_h // 2 + bulb_r // 2], fill=GREEN)


def _icon_png_pil(size: int, maskable: bool = False) -> bytes:
    img = Image.new("RGB", (size, size), GREEN)
    d = ImageDraw.Draw(img)
    if not maskable:
        r = int(size * 0.22)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=GREEN)
    inner = 0.42 if maskable else 0.58   # maskable keeps the glyph inside the safe zone
    _thermometer(d, size // 2, size // 2, size / 64.0 * inner)
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _og_png_pil(w: int, h: int) -> bytes:
    img = Image.new("RGB", (w, h), GREEN)
    d = ImageDraw.Draw(img)
    for y in range(h):  # vertical green gradient
        t = y / float(h)
        d.line([(0, y), (w, y)], fill=tuple(int(GREEN[i] + (GREEN_DARK[i] - GREEN[i]) * t) for i in range(3)))
    _thermometer(d, w // 2, int(h * 0.42), (w / 64.0) * 0.9)
    try:
        from PIL import ImageFont
        f1 = ImageFont.load_default()
        d.text((w // 2, int(h * 0.74)), "Fever Watch", anchor="mm", fill=WHITE, font=f1)
        d.text((w // 2, int(h * 0.80)), "Monsoon fever risk by city  |  PharmEasy", anchor="mm", fill=(220, 240, 238), font=f1)
    except Exception:
        pass
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    os.makedirs(IMG, exist_ok=True)

    def write(name: str, data: bytes) -> None:
        with open(os.path.join(IMG, name), "wb") as fh:
            fh.write(data)

    with open(os.path.join(IMG, "favicon.svg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(FAVICON_SVG)

    if HAVE_PIL:
        write("favicon.ico", _icon_png_pil(48))           # PNG-in-ICO, fine for modern browsers
        write("apple-touch-icon.png", _icon_png_pil(180))
        write("icon-192.png", _icon_png_pil(192))
        write("icon-512.png", _icon_png_pil(512))
        write("icon-maskable-512.png", _icon_png_pil(512, maskable=True))
        write("og-fever-watch.png", _og_png_pil(1200, 630))
        renderer = "Pillow"
    else:
        write("favicon.ico", _ico_from_png(_png_solid(48, 48, GREEN), 48))
        write("apple-touch-icon.png", _png_solid(180, 180, GREEN))
        write("icon-192.png", _png_solid(192, 192, GREEN))
        write("icon-512.png", _png_solid(512, 512, GREEN))
        write("icon-maskable-512.png", _png_solid(512, 512, GREEN))
        write("og-fever-watch.png", _png_solid(1200, 630, GREEN))
        renderer = "stdlib (solid green placeholders)"

    print("Wrote brand placeholder assets to %s  (renderer: %s)" % (IMG, renderer))
    print("  favicon.svg favicon.ico apple-touch-icon.png icon-192/512/maskable-512.png og-fever-watch.png")
    print("  Replace with final brand art before launch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
