"""NOAA CPC rainfall provider (DEFAULT; hybrid).

This is a HYBRID provider, chosen after a 228-city benchmark against IMD gauge
truth showed NASA POWER over-reads pre-monsoon rainfall in the South/peninsula
(inflating the breeding score) while NOAA CPC -- a gauge-based analysis that
ingests the Indian gauge reports IMD shares internationally via WMO/GTS -- tracks
the gauges far better at the same ~0.5deg resolution, and is US PUBLIC DOMAIN
(no licensing). See docs / the decision memo.

Split of responsibilities:
  - RAINFALL (precip_mm)            -> NOAA CPC Global Unified Gauge-Based Analysis
  - TEMPERATURE + HUMIDITY (all else)-> NASA POWER (composed, not subclassed)

So this provider delegates temp/humidity to a NasaPowerProvider instance and
overlays CPC precip per date. Everything downstream of data/weather.json is
provider-agnostic (DailyWeather already carries both), so nothing else changes.

Revert to all-NASA at any time with:  --provider nasa-power  (or WEATHER_PROVIDER=nasa-power)

CPC access: one NetCDF per calendar year from NOAA PSL (variable `precip`,
mm/day, 0.5deg, lon 0-360, latitude descending), downloaded + cached locally and
read with xarray. xarray/netCDF4 are imported LAZILY so `import providers` keeps
working even where those libs are absent (only USING this provider needs them).
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from httputil import get_bytes

from .base import DailyWeather, WeatherProvider
from .nasa_power import NasaPowerProvider

CPC_URL = "https://downloads.psl.noaa.gov/Datasets/cpc_global_precip/precip.{year}.nc"


class CpcProvider(WeatherProvider):
    name = "cpc"
    attribution = (
        "Rainfall by NOAA CPC (Climate Prediction Center Global Unified "
        "Gauge-Based Analysis, public domain); temperature and humidity by "
        "NASA POWER (MERRA-2 / GMAO, public domain)"
    )

    def __init__(self, cache_dir: str | None = None):
        self._nasa = NasaPowerProvider()        # temp/humidity + the revert path
        self._cache_dir = cache_dir or os.path.join("data", "cpc_cache")
        self._var_cache: dict[int, object] = {}  # year -> xarray DataArray ('precip')
        self._refetched: dict[int, bool] = {}    # year -> already re-downloaded a stale cache this process

    # ------------------------------------------------------------------ #
    # public interface
    # ------------------------------------------------------------------ #
    def fetch_daily(self, lat: float, lon: float, past_days: int = 16) -> list[DailyWeather]:
        nasa = self._nasa.fetch_daily(lat, lon, past_days)
        end = date.today()
        start = end - timedelta(days=past_days + 6)  # mirror NASA's latency pad
        cpc = self._cpc_rainfall(lat, lon, start, end)
        return self._merge(nasa, cpc)

    def fetch_range(self, lat: float, lon: float, start: date, end: date) -> list[DailyWeather]:
        """Inclusive [start, end] daily series: NASA temp/humidity + CPC rain.

        Implemented (not inherited) so the backfill path accepts this provider.
        """
        nasa = self._nasa.fetch_range(lat, lon, start, end)
        cpc = self._cpc_rainfall(lat, lon, start, end)
        return self._merge(nasa, cpc)

    # ------------------------------------------------------------------ #
    # CPC rainfall extraction
    # ------------------------------------------------------------------ #
    def _download(self, year: int, path: str) -> None:
        os.makedirs(self._cache_dir, exist_ok=True)
        blob = get_bytes(CPC_URL.format(year=year), timeout=300)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, path)

    @staticmethod
    def _last_day(var):
        """Last date actually present in the DataArray, or None."""
        import numpy as np

        t = np.atleast_1d(var.time.values)
        return date.fromisoformat(str(t[-1])[:10]) if t.size else None

    def _get_var(self, year: int, need_through: date | None = None):
        """Return the cached 'precip' DataArray for `year`, downloading once.

        The CURRENT year's file GROWS as NOAA appends each day, so a cached copy goes
        stale. If it does not reach `need_through`, re-download it ONCE per process.
        This matters because a short file fails SILENTLY: dates past its end simply drop
        out of _cpc_rainfall, _merge leaves precip_mm None, and the aggregate reads 0mm.
        A stale cache therefore produces "zero rain" (and a waterborne score of 0) in
        peak monsoon, which is exactly the silent garbage the fail-loud guard exists to
        prevent. (Seen for real: a precip.2026.nc cached on 16 Jun served 0mm rain for
        every date after 20 Jun, which corrupted the whole 2026 archive season line.)
        """
        import xarray as xr  # lazy: only needed when CPC is actually used

        path = os.path.join(self._cache_dir, f"precip.{year}.nc")
        if year not in self._var_cache:
            if not os.path.exists(path):
                self._download(year, path)
            self._var_cache[year] = xr.open_dataset(path)["precip"]

        if need_through is not None and not self._refetched.get(year):
            last = self._last_day(self._var_cache[year])
            if last is not None and last < need_through:
                # Stale current-year cache: refresh once, then re-open.
                self._refetched[year] = True
                try:
                    self._var_cache[year].close()
                except Exception:
                    pass
                self._var_cache.pop(year, None)
                self._download(year, path)
                self._var_cache[year] = xr.open_dataset(path)["precip"]
                fresh = self._last_day(self._var_cache[year])
                if fresh is not None and fresh < need_through:
                    # Still short after a fresh pull: normal for the last ~1-3 days (CPC
                    # latency). Say so LOUDLY rather than quietly scoring those days as 0mm.
                    print(f"WARNING: CPC precip.{year} reaches {fresh}, short of {need_through}; "
                          f"days after {fresh} have NO rain data and must not be read as 0mm.")
        return self._var_cache[year]

    def _pick_cell(self, pr, lat: float, lon: float, t0: str, t1: str):
        """Nearest 0.5deg grid cell that actually has CPC data over [t0, t1].

        CPC is a LAND gauge analysis; a coastal city's nearest cell can be ocean
        (all-NaN). Search the surrounding cells (nearest first) and take the
        closest one with mostly-valid data; fall back to the most-valid seen.
        Returns grid (lat, lon-in-0-360).
        """
        import numpy as np

        cands = sorted(
            [(lat + a, lon + b) for a in (-1.0, -0.5, 0.0, 0.5, 1.0)
             for b in (-1.0, -0.5, 0.0, 0.5, 1.0)],
            key=lambda p: (p[0] - lat) ** 2 + (p[1] - lon) ** 2,
        )
        best = None
        for la, lo in cands:
            c = pr.sel(lat=la, lon=lo % 360, method="nearest").sel(time=slice(t0, t1))
            vals = np.atleast_1d(c.values).astype(float)
            nvalid = int(np.sum(~np.isnan(vals)))
            glat, glon = float(c.lat), float(c.lon)
            if vals.size and nvalid >= 0.5 * vals.size:
                return glat, glon
            if best is None or nvalid > best[2]:
                best = (glat, glon, nvalid)
        return (best[0], best[1]) if best else (lat, lon % 360)

    def _cpc_rainfall(self, lat: float, lon: float, start: date, end: date) -> dict:
        """{iso_date: precip_mm} for [start, end], spanning calendar years."""
        import numpy as np

        out: dict[str, float] = {}
        cell = None
        for year in range(start.year, end.year + 1):
            need_through = min(end, date(year, 12, 31))
            pr = self._get_var(year, need_through=need_through)
            t0 = max(start, date(year, 1, 1)).isoformat()
            t1 = need_through.isoformat()
            if cell is None:
                cell = self._pick_cell(pr, lat, lon, t0, t1)
            glat, glon = cell
            s = pr.sel(lat=glat, lon=glon, method="nearest").sel(time=slice(t0, t1))
            for t, v in zip(np.atleast_1d(s.time.values), np.atleast_1d(s.values)):
                mm = float(v)
                if not np.isnan(mm) and mm >= 0:
                    out[str(t)[:10]] = round(mm, 2)
        return out

    # ------------------------------------------------------------------ #
    # merge
    # ------------------------------------------------------------------ #
    @staticmethod
    def _merge(nasa_records: list[DailyWeather], cpc: dict) -> list[DailyWeather]:
        """NASA temp/humidity with CPC precip overlaid (CPC wins for rainfall).

        CPC-only dates (CPC latency ~1d < NASA ~3d, so CPC may reach a more recent
        day) are emitted with temp/humidity None; the scorer skips None per-field.
        """
        out: dict[str, DailyWeather] = {}
        for r in nasa_records:
            out[r.date] = DailyWeather(
                date=r.date,
                temp_mean_c=r.temp_mean_c,
                temp_max_c=r.temp_max_c,
                temp_min_c=r.temp_min_c,
                humidity_pct=r.humidity_pct,
                precip_mm=cpc.get(r.date),  # CPC rain replaces NASA rain
            )
        for d, mm in cpc.items():
            if d not in out:
                out[d] = DailyWeather(date=d, temp_mean_c=None, temp_max_c=None,
                                      temp_min_c=None, humidity_pct=None, precip_mm=mm)
        return sorted(out.values(), key=lambda r: r.date)
