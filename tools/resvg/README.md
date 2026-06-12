# Vendored resvg (SVG -> PNG rasterizer)

Used by `src/build_share_cards.py` to rasterize the per-city share cards. Vendored so the
daily CI build is hermetic (no release-download step, no network dependency).

| file | platform | source |
|---|---|---|
| `resvg-linux-x86_64` | ubuntu CI | https://github.com/linebender/resvg/releases/tag/v0.47.0 (`resvg-linux-x86_64.tar.gz`) |
| `resvg-win64.exe` | local dev (Windows) | same release (`resvg-win64.zip`) |

Pinned at **v0.47.0**. If you upgrade: both binaries together, and re-verify a Devanagari
card render (the pipeline pre-shapes text to outlines, so resvg's own text engine - which
drops the Devanagari aa-matra as of v0.47 - is deliberately never used; `--skip-system-fonts`
keeps it that way). CI runs `chmod +x` on the linux binary because git may not preserve the
executable bit from a Windows commit.
