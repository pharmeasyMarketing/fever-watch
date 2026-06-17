"""Live (2026) PharmEasy/ThyroCare lab positivity via the Google Sheets API.

Reads a PRIVATE Google Sheet tab with a service account (no "publish to web"
needed), adapts the verbose header + DD-MM-YYYY dates to the internal schema,
maps every city string through the shared CityResolver (so the live feed shares
last year's city axis), aggregates daily rows over a trailing window, applies the
30-test confidence gate, and returns a 0-100 positivity signal per city/disease
(None where sparse -> capped forecast-only downstream).

Auth: a Google Cloud service account with the Sheets API enabled; share the sheet
with the service-account email (Viewer). Credentials resolve from, in order:
config.key_file, env GOOGLE_SHEETS_SA_FILE (path), or env GOOGLE_SHEETS_SA_JSON
(raw JSON). Read-only scope. Depends on google-auth + google-api-python-client
(behind this provider only; the default mock/cached build stays stdlib).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Optional

from .base import PositivityProvider

try:  # works whether src/ is on sys.path (import signals) or imported as src.signals
    from ..citymap import CityResolver
except (ImportError, ValueError):
    from citymap import CityResolver

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_DATE = {"report gen date", "dt", "week_start", "date"}
_CITY = {"city"}
_DISEASE = {"disease"}
_TESTS = {"all test reports that has the respective disease parameter included",
          "total_tests", "tests_booked", "tests"}
_POS = {"confirmed positive cases", "total_positive_cases", "positives", "positive_cases"}


def _load_credentials(cfg: dict):
    from google.oauth2 import service_account
    raw = os.environ.get("GOOGLE_SHEETS_SA_JSON")
    if raw:
        return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    path = (cfg.get("key_file") or os.environ.get("GOOGLE_SHEETS_SA_FILE") or "").strip()
    if path and os.path.exists(path):
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    raise ValueError(
        "gsheet_api needs service-account credentials: set config.key_file, "
        "env GOOGLE_SHEETS_SA_FILE (path), or env GOOGLE_SHEETS_SA_JSON (raw JSON).")


def read_values(spreadsheet_id: str, tab: str, cfg: dict, *, retries: int = 3) -> list[list]:
    from googleapiclient.discovery import build
    creds = _load_credentials(cfg)
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    rng = f"'{tab}'" if tab else "A:E"
    last = None
    for attempt in range(1, retries + 1):
        try:
            resp = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=rng,
                majorDimension="ROWS", valueRenderOption="FORMATTED_VALUE").execute()
            return resp.get("values", [])
        except Exception as e:  # transient network / API blip -> retry with backoff
            last = e
            if attempt < retries:
                import time
                time.sleep(2 * attempt)
    raise RuntimeError(f"Sheets API read failed after {retries} attempts: {last}")


def _parse_date(s) -> Optional[_dt.date]:
    s = str(s).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_int(v) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def build_index(values: list[list], resolver: CityResolver, *, window_days: int = 28,
                min_tests: int = 30, ref_pct: float = 35.0, ref_by_disease: Optional[dict] = None,
                with_detail: bool = False):
    """Aggregate raw rows -> {(city_id, disease): signal|None}. Pure, testable offline.

    ref_by_disease (optional) maps a disease id to its own reference positivity %, so each
    fever is scored against its own realistic 'high' (malaria ~2% vs typhoid ~28%); ref_pct
    is the fallback for any disease not in the map.

    With with_detail=True, returns (index, detail) where detail[(city_id, disease)] =
    {tests, positives, pct, window_days, gated} for the trailing window - the raw labs
    inputs used to derive the signal (for the score-derivation logger / explainer; these
    raw counts are NEVER written to the public grid.json)."""
    refs = ref_by_disease or {}
    if not values:
        return ({}, {}) if with_detail else {}
    header = [str(h).strip().lower() for h in values[0]]

    def col(names):
        for i, h in enumerate(header):
            if h in names:
                return i
        return None
    ci = {k: col(v) for k, v in (("date", _DATE), ("city", _CITY), ("disease", _DISEASE),
                                 ("tests", _TESTS), ("pos", _POS))}
    missing = [k for k, v in ci.items() if v is None]
    if missing:
        raise ValueError(f"sheet header missing columns {missing}; saw {header}")

    daily = {}  # (city_id, disease) -> list[(date, tests, pos)]
    for row in values[1:]:
        def g(k):
            j = ci[k]
            return row[j] if j is not None and j < len(row) else None
        d = _parse_date(g("date"))
        cid = resolver.resolve(g("city"))
        disease = (str(g("disease") or "").strip().lower())
        tests = _to_int(g("tests"))
        pos = _to_int(g("pos"))
        if d is None or cid is None or not disease or tests is None:
            continue
        daily.setdefault((cid, disease), []).append((d, tests, pos or 0))

    if not daily:
        return {}
    max_date = max(d for recs in daily.values() for (d, _, _) in recs)
    cutoff = max_date - _dt.timedelta(days=window_days - 1) if window_days and window_days > 0 else _dt.date.min

    index, detail = {}, {}
    for key, recs in daily.items():
        t = sum(tt for (d, tt, _) in recs if d >= cutoff)
        p = sum(pp for (d, _, pp) in recs if d >= cutoff)
        ref = refs.get(key[1], ref_pct)  # key = (city_id, disease); per-disease ref, ref_pct fallback
        index[key] = _signal(t, p, min_tests, ref)
        detail[key] = {"tests": t, "positives": p,
                       "pct": round(p / t * 100, 1) if t else None,
                       "ref_pct": ref, "window_days": window_days, "gated": t < min_tests}
    return (index, detail) if with_detail else index


def _signal(tests: int, positives: int, min_tests: int, ref_pct: float) -> Optional[int]:
    if tests < min_tests or ref_pct <= 0:
        return None
    pct = positives / tests * 100.0
    return max(0, min(100, round(pct / ref_pct * 100)))


class GSheetApiPositivityProvider(PositivityProvider):
    name = "gsheet_api"

    def __init__(self, config: dict):
        cfg = config or {}
        self.spreadsheet_id = (cfg.get("spreadsheet_id") or "").strip()
        self.tab = (cfg.get("tab") or "").strip()
        if not self.spreadsheet_id or not self.tab:
            raise ValueError("gsheet_api needs config.spreadsheet_id and config.tab")
        self.min_tests = int(cfg.get("min_tests", 30))
        self.ref_pct = float(cfg.get("ref_positivity_pct", 35.0))
        # Per-disease reference positivity (each fever scored against its own 'high'); ref_pct fallback.
        self.ref_by_disease = {str(k).lower(): float(v)
                               for k, v in (cfg.get("ref_positivity_pct_by_disease") or {}).items()}
        self.window_days = int(cfg.get("window_days", 28))
        resolver = CityResolver()
        values = read_values(self.spreadsheet_id, self.tab, cfg)
        self._index, self.detail_map = build_index(
            values, resolver, window_days=self.window_days,
            min_tests=self.min_tests, ref_pct=self.ref_pct,
            ref_by_disease=self.ref_by_disease, with_detail=True)
        self.ref_pct_used = self.ref_by_disease or self.ref_pct
        unmapped_path = cfg.get("unmapped_log", os.path.join("data", "citymap", "unmapped_live.csv"))
        if resolver.unmapped:
            resolver.dump_unmapped(unmapped_path)

    def fetch(self, city: dict, disease: dict) -> Optional[int]:
        return self._index.get((city["id"].lower(), disease["id"].lower()))

    def detail(self, city: dict, disease: dict) -> Optional[dict]:
        """Raw labs inputs (tests, positives, pct) behind the signal, or None. Local/logging only."""
        return self.detail_map.get((city["id"].lower(), disease["id"].lower()))
