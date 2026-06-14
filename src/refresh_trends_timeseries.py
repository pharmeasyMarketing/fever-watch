"""Weekly per-state Google Trends TIMESERIES refresh (signal 2; point #5: EXACT cross-year search YoY).

Re-pulls the per-state x disease WEEKLY interest-over-time over a window that spans BOTH the last-year season
and this year to date ("2025-06-01 .. today"), so last-year and this-year sit on ONE Google normalisation
(Google normalises 0-100 across the whole window of a single query). Writes data/backfill/trends_history.json
(gitignored, regenerable). The season-trend archive is then recomputed from it via:

    python src/build_archive.py --search-only

This is the CI-friendly sibling of src/backfill_trends.py: it SHARES the same pull / carry-forward / quota
logic (pull_history) but loads keys from the ENVIRONMENT (Actions secrets SERPAPI_KEY .. _5), not apify.env,
and sets the window end to today. Runs WEEKLY (Mondays, aligned to the 1-Jun week boundary) inside daily.yml.

Quota: ~33 geo-states x 4 diseases ~= 132 SerpApi searches per run (null-geo states skipped); ~570/month
during the monsoon season, 0 off-season. Failover rotates across the 5 keys on quota / HTTP errors.

Stdlib only. ASCII hyphens only.
"""
from __future__ import annotations

import os
import sys
from datetime import date

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from backfill_trends import pull_history  # noqa: E402  (shared pull / merge / quota logic)
from iohelpers import load_json  # noqa: E402
from signals.serpapi import SerpApiTrendsProvider, load_keys  # noqa: E402

ROOT = os.path.dirname(SRC_DIR)
SEASON_START = "2025-06-01"   # last-year season start; the window must span both years for one normalisation


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    cfg_dir = os.path.join(ROOT, "config")
    diseases = load_json(os.path.join(cfg_dir, "diseases.json"))["diseases"]
    signals_cfg = load_json(os.path.join(cfg_dir, "signals.json"))
    serp_cfg = (signals_cfg.get("trends") or {}).get("serpapi", {})
    terms = serp_cfg.get("terms", {})
    geo_map = load_json(os.path.join(cfg_dir, "in_state_geo.json"))["geo"]
    out_path = os.path.join(ROOT, "data", "backfill", "trends_history.json")

    keys = load_keys()  # SERPAPI_KEY, SERPAPI_KEY_2 .. _5 from the environment (Actions secrets)
    if not keys:
        print("No SERPAPI keys in the environment (SERPAPI_KEY .. _5); aborting.", file=sys.stderr)
        return 1

    date_range = f"{SEASON_START} {date.today().isoformat()}"
    provider = SerpApiTrendsProvider(serp_cfg, keys=keys)
    print(f"Weekly TIMESERIES refresh -> {out_path}  (window: {date_range})")
    return pull_history(provider, diseases, terms, geo_map, date_range, out_path)


if __name__ == "__main__":
    raise SystemExit(main())
