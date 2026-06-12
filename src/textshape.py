# -*- coding: utf-8 -*-
"""HarfBuzz text pre-shaping for the share-card SVGs (build_share_cards.py).

Turns (text, font, size) into positioned SVG glyph outlines so the PNG rasterizer
(resvg) needs ZERO runtime text shaping or fonts: Indic conjuncts/matras are shaped
here by HarfBuzz and frozen into <path> outlines, making output byte-stable across
Windows/Linux and immune to renderer shaping bugs (resvg's own <text> shaping drops
the Devanagari aa-matra, found in QA 2026-06-11 - never use it for Indic).

Sign convention (the bug that broke Nastaliq/nukta placement in the first cut):
HarfBuzz y_offset/y_advance are Y-UP (font space); SVG is Y-DOWN, so both are
NEGATED here. Deps: uharfbuzz + fonttools (pinned in the CI workflow).
"""
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

_HB = {}   # (path, variations) -> hb.Font
_TT = {}   # path -> (TTFont, glyphSet, unitsPerEm, glyphOrder)


def _load(font_path, variations=None):
    key = (font_path, tuple(sorted((variations or {}).items())))
    if key not in _HB:
        with open(font_path, "rb") as fh:
            data = fh.read()
        font = hb.Font(hb.Face(hb.Blob(data)))
        if variations:
            font.set_variations(variations)
        _HB[key] = font
    if font_path not in _TT:
        tt = TTFont(font_path)
        _TT[font_path] = (tt, tt.getGlyphSet(), tt["head"].unitsPerEm, tt.getGlyphOrder())
    return _HB[key], _TT[font_path]


def shape_to_path(text, font_path, size, features=None, variations=None):
    """Shape `text` and return (svg_markup, advance_px). Baseline at y=0, pen at x=0;
    the caller translates the group into place."""
    font, (tt, glyphset, upm, glyph_order) = _load(font_path, variations)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()   # script + direction (handles RTL) per run
    hb.shape(font, buf, features or {})
    scale = size / upm
    pen_x = 0.0
    pen_y = 0.0
    d_parts = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gid = info.codepoint  # post-shaping this is a glyph id
        gname = glyph_order[gid] if gid < len(glyph_order) else None
        gx = pen_x + pos.x_offset * scale
        gy = pen_y - pos.y_offset * scale   # HarfBuzz Y is up, SVG Y is down
        if gname is not None:
            spen = SVGPathPen(glyphset)
            try:
                glyphset[gname].draw(spen)
                gd = spen.getCommands()
            except Exception:
                gd = ""
            if gd:
                # scale into px and flip Y (font up = SVG down), translate to (gx, gy)
                d_parts.append('<g transform="translate(%.3f,%.3f) scale(%.5f,%.5f)">'
                               '<path d="%s"/></g>' % (gx, gy, scale, -scale, gd))
        pen_x += pos.x_advance * scale
        pen_y -= pos.y_advance * scale
    return "".join(d_parts), pen_x
