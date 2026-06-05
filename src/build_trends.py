"""Fever Watch weekly Google Trends builder (signal 2).

Uses SerpApi (5 keys, failover) to write data/trends.json: per disease, the
per-state search interest (0-100, comparable across states via GEO_MAP) and a
national news_spike flag. The DAILY grid reads this cached file via
CachedTrendsProvider, so SerpApi is hit only ~10 times per week, not per day.

Usage (weekly, with keys in env):
    SERPAPI_KEY=... python src/build_trends.py

Fail-loud guard: aborts and writes nothing if no disease returns regional data.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from signals.serpapi import SerpApiTrendsProvider  # noqa: E402

ROOT = os.path.dirname(SRC_DIR)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    cfg_dir = os.path.join(ROOT, "config")
    diseases = load_json(os.path.join(cfg_dir, "diseases.json"))["diseases"]
    signals_cfg = load_json(os.path.join(cfg_dir, "signals.json"))
    serp_cfg = (signals_cfg.get("trends") or {}).get("serpapi", {})
    terms = serp_cfg.get("terms", {})
    out_path = os.path.join(ROOT, "data", "trends.json")

    provider = SerpApiTrendsProvider(serp_cfg)
    print(f"SerpApi keys: {len(provider.keys)}  |  geo: {provider.geo}  |  diseases: {len(diseases)}")
    print("-" * 72)

    result: dict = {}
    failures = []
    for d in diseases:
        did = d["id"]
        query = (terms.get(did) or [d["label"]])[0]  # primary term
        try:
            by_state = provider.interest_by_region(query)
            spike = provider.national_news_spike(query)
            if not by_state:
                failures.append(f"{did}: no regional data")
                print(f"  {did:14} SKIP (no regional data for '{query}')")
                continue
            result[did] = {"query": query, "news_spike": spike, "by_state": by_state}
            print(f"  {did:14} OK  states={len(by_state)}  news_spike={spike}")
        except Exception as err:
            failures.append(f"{did}: {err}")
            print(f"  {did:14} FAIL ({err})")
        time.sleep(0.5)

    print("-" * 72)
    if not result:
        print("ABORT: no disease returned trends data. Writing nothing.", file=sys.stderr)
        for f in failures:
            print("   -", f, file=sys.stderr)
        return 1

    payload = {
        "signal": "trends",
        "source": "serpapi-google-trends",
        "geo": provider.geo,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Relative Google search interest (0-100), not case counts. State-level granularity; a city inherits its state.",
        "failed": failures,
        "diseases": result,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}  ({len(result)}/{len(diseases)} diseases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
