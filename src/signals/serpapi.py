"""SerpApi Google Trends access (signal 2 source, used WEEKLY by build_trends.py).

Google Trends has no official production API; SerpApi is the managed access we use,
with up to 5 API keys (Actions secrets) and failover on quota/errors. Per disease
we run two cheap queries:
  - GEO_MAP (interest by region across India) -> per-state value 0-100, comparable
    across states;
  - a national interest-over-time -> a news_spike flag (latest well above trailing).

This is NOT a grid TrendsProvider (it does not implement fetch(city, disease)); it
is the upstream fetcher that build_trends.py turns into data/trends.json, which the
daily grid then reads via CachedTrendsProvider.

Stdlib only (urllib). Keys from env: SERPAPI_KEY, SERPAPI_KEY_2 .. _5 (or SERPAPI_KEYS=csv).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

ENDPOINT = "https://serpapi.com/search.json"


def load_keys() -> list[str]:
    keys: list[str] = []
    for name in ("SERPAPI_KEY", "SERPAPI_KEY_2", "SERPAPI_KEY_3", "SERPAPI_KEY_4", "SERPAPI_KEY_5"):
        v = (os.environ.get(name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    for v in (os.environ.get("SERPAPI_KEYS") or "").split(","):
        v = v.strip()
        if v and v not in keys:
            keys.append(v)
    return keys


class SerpApiTrendsProvider:
    name = "serpapi"

    def __init__(self, config: Optional[dict] = None, keys: Optional[list] = None):
        self.cfg = config or {}
        self.geo = self.cfg.get("geo", "IN")
        self.keys = keys if keys is not None else load_keys()
        if not self.keys:
            raise ValueError("SerpApi needs at least one API key (set SERPAPI_KEY)")
        self._ki = 0

    def _get(self, params: dict) -> dict:
        """GET with key failover on quota / HTTP errors."""
        last_err = None
        for _ in range(len(self.keys)):
            q = dict(params)
            q["api_key"] = self.keys[self._ki]
            url = ENDPOINT + "?" + urllib.parse.urlencode(q)
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    data = json.load(r)
                if data.get("error"):
                    last_err = data["error"]
                    self._ki = (self._ki + 1) % len(self.keys)
                    continue
                return data
            except Exception as e:  # network / parse / HTTP error -> rotate key
                last_err = str(e)
                self._ki = (self._ki + 1) % len(self.keys)
                time.sleep(0.5)
        raise RuntimeError(f"SerpApi failed on all {len(self.keys)} key(s): {last_err}")

    def interest_by_region(self, query: str) -> dict:
        """Return {state_name: value 0-100} across India for a query (GEO_MAP)."""
        data = self._get({
            "engine": "google_trends",
            "data_type": "GEO_MAP",
            "q": query,
            "geo": self.geo,
            "region": "REGION",
            "date": self.cfg.get("geo_timeframe", "today 1-m"),
        })
        out: dict = {}
        for row in (data.get("interest_by_region") or []):
            loc = (row.get("location") or "").strip()
            val = row.get("extracted_value")
            if loc and val is not None:
                out[loc] = int(val)
        return out

    def national_news_spike(self, query: str) -> bool:
        """True if the latest national interest is well above its trailing average."""
        data = self._get({
            "engine": "google_trends",
            "data_type": "TIMESERIES",
            "q": query,
            "geo": self.geo,
            "date": self.cfg.get("timeframe", "today 3-m"),
        })
        series = []
        for pt in ((data.get("interest_over_time") or {}).get("timeline_data") or []):
            vals = pt.get("values") or []
            if vals and vals[0].get("extracted_value") is not None:
                series.append(int(vals[0]["extracted_value"]))
        if len(series) < 6:
            return False
        latest, trailing = series[-1], series[-6:-1]
        avg = sum(trailing) / len(trailing)
        return latest >= max(40, avg * 1.5)
