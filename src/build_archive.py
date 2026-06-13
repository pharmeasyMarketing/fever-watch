"""Build the compact, committed season-trend archive from the (gitignored) backfill inputs.

Consumes:
  - data/backfill/weather_{2025,2026}.json  (NASA POWER daily by_date -> per-family scores; build_weather.py --start/--end)
  - data/backfill/trends_history.json        (SerpApi per-state weekly interest-over-time; backfill_trends.py)
  - config/cities.json, config/diseases.json, config/in_state_geo.json
  - data/grid.json generated_at              (for the "as of" current week index)

Produces (committed, compact ~60 KB):
  - data/archive/trend_series.json

This is the REAL replacement for the deterministic mock last-year line in the season-trend module, for the
WEATHER and SEARCH metrics only. Overall + Labs stay on the mock until real lab positivity history lands
(no PharmEasy lab history exists yet). The two real metrics mirror exactly how the trend module derives them
from the live grid:
  - weather metric = mean over the 4 diseases of each disease's weather sub-score (= its family score),
    i.e. (3 x mosquito + 1 x waterborne) / 4, matching trend.js meanSignal(cells,'weather') / _t_mean.
  - search metric  = mean over the 4 diseases of the city's state weekly search interest, matching
    meanSignal(cells,'trends'). A null/empty state falls back to that disease's national mean (mean over
    the states present), mirroring CachedTrendsProvider's national-mean fallback.

Both metrics are stored for BOTH years (ly = 2025 full 22-week season, ty = 2026 partial up to the current
week). The search metric MUST take this-year from the same per-state TIMESERIES as last-year (not the live
GEO_MAP_0 value) so the two lines share one normalisation. Weeks are anchored to 1 Jun + 7 day steps, exactly
like trend.js build() / _trend_series, so the archive lines align with the module's week axis.

Run from the repo root: python src/build_archive.py
"""
import datetime
import json
import math
import os

from iohelpers import write_json_atomic

NW = 22                      # weeks in the season window (1 Jun -> 30 Oct), matches TREND_SHAPE length
LY_YEAR, TY_YEAR = 2025, 2026
TREND_TOL_DAYS = 4           # nearest-week match tolerance (Google's weekly buckets drift vs the 1-Jun anchor across a year)
OUT_PATH = os.path.join("data", "archive", "trend_series.json")


def _r(x):
    """Round half up; identical to trend.js r() / build_site.py _t_r."""
    return int(math.floor((x or 0) + 0.5))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _as_of(generated_at):
    ga = generated_at or ""
    try:
        gy, gm, gd = int(ga[0:4]), int(ga[5:7]), int(ga[8:10])
    except ValueError:
        gy, gm, gd = TY_YEAR, 6, 1
    days = (datetime.date(gy, gm, gd) - datetime.date(gy, 6, 1)).days
    return max(0, min(days // 7, NW - 1))


def _week_date(year, w):
    return datetime.date(year, 6, 1) + datetime.timedelta(days=7 * w)


def _nearest(series_dates, target):
    """series_dates: list[(date, value)] sorted; return the value nearest `target` within TREND_TOL_DAYS, else None."""
    best, best_gap = None, TREND_TOL_DAYS + 1
    for d, v in series_dates:
        gap = abs((d - target).days)
        if gap < best_gap:
            best, best_gap = v, gap
    return best


def main():
    cities = _load(os.path.join("config", "cities.json"))
    cities = cities["cities"] if isinstance(cities, dict) and "cities" in cities else cities
    diseases = _load(os.path.join("config", "diseases.json"))
    diseases = diseases["diseases"] if isinstance(diseases, dict) and "diseases" in diseases else diseases
    fam_of = {d["id"]: d["family"] for d in diseases}
    dids = [d["id"] for d in diseases]

    weather = {
        LY_YEAR: _load(os.path.join("data", "backfill", "weather_%d.json" % LY_YEAR)).get("by_date", {}),
        TY_YEAR: _load(os.path.join("data", "backfill", "weather_%d.json" % TY_YEAR)).get("by_date", {}),
    }
    trends = _load(os.path.join("data", "backfill", "trends_history.json")).get("diseases", {})
    # Pre-parse each disease x state weekly series into sorted (date, value) lists for nearest-week lookup.
    tseries = {}
    for did in dids:
        by_state = trends.get(did, {}).get("by_state", {})
        tseries[did] = {st: sorted((datetime.date.fromisoformat(p[0]), p[1]) for p in pts)
                        for st, pts in by_state.items()}

    generated_at = _load(os.path.join("data", "grid.json")).get("generated_at", "")
    as_of = _as_of(generated_at)

    # National mean per disease per target week (mean over the states present for that disease), used as the
    # fallback for cities whose state has no Trends subregion (null geo) or no data for that disease.
    natmean_cache = {}

    def national_mean(did, target):
        key = (did, target)
        if key not in natmean_cache:
            vals = [_nearest(s, target) for s in tseries[did].values()]
            vals = [v for v in vals if v is not None]
            natmean_cache[key] = (sum(vals) / len(vals)) if vals else 0.0
        return natmean_cache[key]

    def weather_metric(year, w, cid):
        e = weather[year].get(_week_date(year, w).isoformat(), {}).get(cid)
        if not e:
            return None
        fams = e.get("families", {})
        scores = [fams.get(fam_of[did], 0) for did in dids]
        return _r(sum(scores) / float(len(scores)))

    def search_metric(year, w, state):
        target = _week_date(year, w)
        per_disease = []
        for did in dids:
            s = tseries[did].get(state)
            v = _nearest(s, target) if s else None
            if v is None:
                v = national_mean(did, target)
            per_disease.append(v)
        return _r(sum(per_disease) / float(len(per_disease)))

    def carry_forward(arr):
        """Replace any None with the previous (then next) non-None, so a stray missing week never breaks the line."""
        out, last = list(arr), None
        for i, v in enumerate(out):
            if v is None:
                out[i] = last
            else:
                last = v
        nxt = None
        for i in range(len(out) - 1, -1, -1):
            if out[i] is None:
                out[i] = nxt
            else:
                nxt = out[i]
        return [v if v is not None else 0 for v in out]

    out_cities = {}
    weak_weather, weak_search = 0, 0
    for c in cities:
        cid, state = c["id"], c.get("state", "")
        w_ly = carry_forward([weather_metric(LY_YEAR, w, cid) for w in range(NW)])
        w_ty = carry_forward([weather_metric(TY_YEAR, w, cid) for w in range(as_of + 1)])
        s_ly = [search_metric(LY_YEAR, w, state) for w in range(NW)]
        s_ty = [search_metric(TY_YEAR, w, state) for w in range(as_of + 1)]
        if not any(weather[LY_YEAR].get(_week_date(LY_YEAR, w).isoformat(), {}).get(cid) for w in range(NW)):
            weak_weather += 1
        if state not in tseries[dids[0]] and state not in tseries[dids[-1]]:
            weak_search += 1
        out_cities[cid] = {"weather": {"ly": w_ly, "ty": w_ty}, "search": {"ly": s_ly, "ty": s_ty}}

    out = {
        "generated_at": generated_at,
        "ly_year": LY_YEAR, "ty_year": TY_YEAR, "nw": NW, "asOf": as_of,
        "cities": out_cities,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    write_json_atomic(OUT_PATH, out, indent=None)
    size = os.path.getsize(OUT_PATH)
    print("Wrote %s : %d cities, asOf week %d (ty len %d), %d bytes" % (OUT_PATH, len(out_cities), as_of, as_of + 1, size))
    print("  cities with NO weather backfill: %d ; cities on national-mean search fallback: %d" % (weak_weather, weak_search))


if __name__ == "__main__":
    main()
