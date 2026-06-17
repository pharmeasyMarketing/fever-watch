"""Google Sheet positivity provider (signal 3, read daily).

Reads the PharmEasy lab feed published as CSV (see docs/lab_feed_format.md): one
row per city x disease x period with tests_booked + positives (or positivity_pct).
Computes a 0-100 lab signal scaled by a reference positivity, keeps only the most
recent period per city/disease, and returns None for sparse cells (below min_tests
or missing) so they drop to the capped forecast-only mode.

Aggregate and de-identified; surfaced as a trend, not a rate. Stdlib only
(urllib + csv). Supports file:// URLs for local testing against the sample CSV.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from typing import Optional

from .base import PositivityProvider


class GoogleSheetPositivityProvider(PositivityProvider):
    name = "googlesheet"

    def __init__(self, config: dict):
        cfg = config or {}
        self.csv_url = (cfg.get("csv_url") or "").strip()
        self.min_tests = int(cfg.get("min_tests", 30))
        self.ref_pct = float(cfg.get("ref_positivity_pct", 35.0))
        # Per-disease reference positivity (each fever scored against its own 'high'); ref_pct fallback.
        self.ref_by_disease = {str(k).lower(): float(v)
                               for k, v in (cfg.get("ref_positivity_pct_by_disease") or {}).items()}
        if not self.csv_url:
            raise ValueError("googlesheet positivity provider needs config.csv_url")
        self._index: dict = {}
        self._load()

    def _load(self) -> None:
        req = urllib.request.Request(self.csv_url, headers={"User-Agent": "FeverWatch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        latest: dict = {}  # (city, disease) -> (week_start, row); keep most recent period
        for row in reader:
            city = (row.get("city") or "").strip().lower()
            disease = (row.get("disease") or "").strip().lower()
            if not city or not disease:
                continue
            wk = (row.get("week_start") or "").strip()
            key = (city, disease)
            if key not in latest or wk >= latest[key][0]:
                latest[key] = (wk, row)
        for key, (_wk, row) in latest.items():
            self._index[key] = self._signal(row)

    def _signal(self, row: dict) -> Optional[int]:
        tests = _to_int(row.get("tests_booked"))
        pct = _to_float(row.get("positivity_pct"))
        if pct is None:
            positives = _to_int(row.get("positives"))
            if positives is not None and tests:
                pct = positives / tests * 100.0
        if pct is None:
            return None
        # sparse coverage -> treat as no data (forecast-only downstream)
        if tests is not None and tests < self.min_tests:
            return None
        disease = (row.get("disease") or "").strip().lower()
        ref = self.ref_by_disease.get(disease, self.ref_pct)  # per-disease ref, ref_pct fallback
        if ref <= 0:
            return None
        return max(0, min(100, round(pct / ref * 100)))

    def fetch(self, city: dict, disease: dict) -> Optional[int]:
        return self._index.get((city["id"].lower(), disease["id"].lower()))


def _to_int(v):
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
