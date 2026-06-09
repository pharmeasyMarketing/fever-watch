"""CachedTrendsProvider: serves the trends signal for the DAILY grid by reading the
weekly data/trends.json that build_trends.py produced. A city inherits its state's
interest for the disease, plus that disease's national news_spike flag. Missing
states fall back to the disease's national mean.
"""
from __future__ import annotations

import json

from .base import TrendsProvider

SIGNAL_FLOOR = 4


def _norm(s) -> str:
    return (s or "").strip().lower().replace("&", "and").replace("  ", " ")


class CachedTrendsProvider(TrendsProvider):
    name = "cached"

    def __init__(self, path: str):
        with open(path, "r", encoding="utf-8") as fh:
            self.data = json.load(fh)
        self.diseases = self.data.get("diseases", {})

    def fetch(self, city: dict, disease: dict) -> dict:
        d = self.diseases.get(disease["id"], {})
        by_state = {_norm(k): v for k, v in (d.get("by_state") or {}).items()}
        raw = by_state.get(_norm(city.get("state")))           # this state's Google Trends interest
        if raw is None:
            vals = list((d.get("by_state") or {}).values())     # no state row -> the disease's national mean
            raw = round(sum(vals) / len(vals)) if vals else None
        value = SIGNAL_FLOOR if raw is None else max(SIGNAL_FLOOR, min(100, int(raw)))
        # raw = pre-floor interest (so the sheet can show trends_score = MAX(floor, MIN(100, raw)));
        # as_of = when this disease last refreshed (build_trends carry-forward), for freshness tagging.
        return {"value": value, "raw": raw, "news_spike": bool(d.get("news_spike")), "as_of": d.get("as_of")}
