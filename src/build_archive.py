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

Three modes (run from the repo root):
  python src/build_archive.py                 # full build from the backfills (weather + search, both years)
  python src/build_archive.py --daily         # CI daily: extend weather ty from grid.json; length-pad search ty
  python src/build_archive.py --search-only   # CI weekly: recompute EXACT search ly+ty from a fresh per-state
                                              #   TIMESERIES (data/backfill/trends_history.json), weather untouched.
                                              #   Fed by refresh_trends_timeseries.py. This is what makes the
                                              #   cross-year SEARCH YoY EXACT (one normalisation for both years).
"""
import argparse
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


def _parse_tseries(trends_diseases, dids):
    """Parse each disease x state weekly series into sorted [(date, value), ...] for nearest-week lookup."""
    tseries = {}
    for did in dids:
        by_state = trends_diseases.get(did, {}).get("by_state", {})
        tseries[did] = {st: sorted((datetime.date.fromisoformat(p[0]), p[1]) for p in pts)
                        for st, pts in by_state.items()}
    return tseries


def _search_blocks(tseries, dids, cities, as_of, nw=NW):
    """Per-city search {ly, ty} = mean over the diseases of the city's STATE weekly interest, with BOTH years
    read from the SAME timeseries (one Google normalisation). A null/empty state falls back to that disease's
    national mean (mean over the states present), mirroring CachedTrendsProvider. Returns (blocks, weak_count)."""
    natmean_cache = {}

    def national_mean(did, target):
        key = (did, target)
        if key not in natmean_cache:
            vals = [_nearest(s, target) for s in tseries[did].values()]
            vals = [v for v in vals if v is not None]
            natmean_cache[key] = (sum(vals) / len(vals)) if vals else 0.0
        return natmean_cache[key]

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

    blocks, weak = {}, 0
    for c in cities:
        cid, state = c["id"], c.get("state", "")
        blocks[cid] = {
            "ly": [search_metric(LY_YEAR, w, state) for w in range(nw)],
            "ty": [search_metric(TY_YEAR, w, state) for w in range(as_of + 1)],
        }
        if state not in tseries[dids[0]] and state not in tseries[dids[-1]]:
            weak += 1
    return blocks, weak


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
    tseries = _parse_tseries(trends, dids)

    generated_at = _load(os.path.join("data", "grid.json")).get("generated_at", "")
    as_of = _as_of(generated_at)

    # EXACT search ly+ty from the per-state TIMESERIES so both years share one Google normalisation.
    search_by_city, weak_search = _search_blocks(tseries, dids, cities, as_of)

    def weather_metric(year, w, cid):
        e = weather[year].get(_week_date(year, w).isoformat(), {}).get(cid)
        if not e:
            return None
        fams = e.get("families", {})
        scores = [fams.get(fam_of[did], 0) for did in dids]
        return _r(sum(scores) / float(len(scores)))

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
    weak_weather = 0
    for c in cities:
        cid = c["id"]
        w_ly = carry_forward([weather_metric(LY_YEAR, w, cid) for w in range(NW)])
        w_ty = carry_forward([weather_metric(TY_YEAR, w, cid) for w in range(as_of + 1)])
        if not any(weather[LY_YEAR].get(_week_date(LY_YEAR, w).isoformat(), {}).get(cid) for w in range(NW)):
            weak_weather += 1
        out_cities[cid] = {"weather": {"ly": w_ly, "ty": w_ty}, "search": search_by_city[cid]}

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


def update_daily():
    """DAILY CRON MODE: extend the committed archive's THIS-YEAR (ty) vectors with today's metrics taken
    straight from data/grid.json. Reads ONLY data/grid.json + the committed data/archive/trend_series.json -
    NOT the gitignored backfills - so it is safe to run in CI (the daily.yml cron). Run after build_daily.

    Metric definitions are identical to the full build (mean over the 4 diseases of each signal sub-score),
    so the values line up with the rest of the page:
      - WEATHER is EXACT: grid signals.weather are the same NASA family scores the last-year backfill used,
        so this-year and last-year weather share one scale (YoY is exact and genuinely changes daily).
      - SEARCH is NOT injected from the live grid here. This cron only LENGTH-PADS search ty (carry-forward
        of the last value) so the trend.js real-branch length guard (search.ty.length === asOf+1) keeps
        holding as the season advances. The EXACT search ly+ty - both years read from ONE per-state TIMESERIES
        normalisation - is recomputed WEEKLY by refresh_search() (--search-only), fed by
        refresh_trends_timeseries.py. So the cross-year search YoY is now EXACT, not directional.
    """
    if not os.path.exists(OUT_PATH):
        print("update_daily: %s missing - run the full build_archive first. Skipping." % OUT_PATH)
        return
    arch = _load(OUT_PATH)
    diseases = _load(os.path.join("config", "diseases.json"))
    diseases = diseases["diseases"] if isinstance(diseases, dict) and "diseases" in diseases else diseases
    dids = [d["id"] for d in diseases]

    grid = _load(os.path.join("data", "grid.json"))
    generated_at = grid.get("generated_at", "")
    gy = int(generated_at[0:4]) if generated_at[0:4].isdigit() else TY_YEAR
    if gy != arch.get("ty_year"):
        print("update_daily: grid year %s != archive ty_year %s (season rolled over) - re-run the full "
              "backfill for the new season. Skipping." % (gy, arch.get("ty_year")))
        return
    as_of = _as_of(generated_at)

    cells_by = {}
    for r in grid.get("grid", []):
        cells_by.setdefault(r["city"], {})[r["disease"]] = r

    def metric(cells, key):
        vals = [cells[did].get("signals", {}).get(key) for did in dids if did in cells]
        vals = [v for v in vals if v is not None]
        return _r(sum(vals) / len(vals)) if vals else None

    def upsert(vec, idx, val):
        # Pad any skipped weeks by carrying the last value forward (the cron runs daily, so idx grows by
        # at most 1 per week and gaps are not expected), then set the current week.
        while len(vec) <= idx:
            vec.append(vec[-1] if vec else (val if val is not None else 0))
        if val is not None:
            vec[idx] = val

    def pad_only(vec, idx):
        # Extend the vector to length idx+1 by carrying the last value forward, WITHOUT overwriting the
        # current week. Keeps trend.js's length guard (search.ty.length === asOf+1) satisfied between the
        # weekly EXACT refreshes, without injecting the directional live cross-state value.
        while len(vec) <= idx:
            vec.append(vec[-1] if vec else 0)

    updated = 0
    for cid, block in arch.get("cities", {}).items():
        cells = cells_by.get(cid)
        if not cells:
            continue
        upsert(block.get("weather", {}).get("ty", []), as_of, metric(cells, "weather"))
        # SEARCH: only keep the length in step; the EXACT search ly+ty is recomputed weekly by refresh_search()
        # from a fresh per-state TIMESERIES pull (refresh_trends_timeseries.py). See the module docstring.
        pad_only(block.get("search", {}).get("ty", []), as_of)
        updated += 1

    arch["generated_at"] = generated_at
    arch["asOf"] = as_of
    write_json_atomic(OUT_PATH, arch, indent=None)
    print("update_daily: extended %d cities to as-of week %d (ty len %d) from data/grid.json (%s)."
          % (updated, as_of, as_of + 1, generated_at[:10]))


def refresh_search():
    """WEEKLY MODE: recompute the EXACT search ly+ty from a fresh per-state TIMESERIES pull
    (data/backfill/trends_history.json, written by refresh_trends_timeseries.py in the same CI job),
    leaving the committed weather blocks untouched.

    This is what makes the cross-year SEARCH YoY EXACT: both years are read from the SAME single-window
    timeseries pull (one Google normalisation), replacing the directional live cross-state value the daily
    cron used to inject. Reads ONLY committed / CI-available inputs (the archive, cities/diseases/grid, and
    the fresh trends_history the weekly pull just wrote) - NOT the gitignored weather backfills - so it is
    CI-safe. Run AFTER --daily (so weather ty and search ty share the same as_of length). Skips gracefully if
    the archive or the trends history is missing, or if the season has rolled over.
    """
    th_path = os.path.join("data", "backfill", "trends_history.json")
    if not os.path.exists(OUT_PATH):
        print("refresh_search: %s missing - run the full build_archive first. Skipping." % OUT_PATH)
        return
    if not os.path.exists(th_path):
        print("refresh_search: %s missing - run refresh_trends_timeseries.py first. Skipping." % th_path)
        return
    arch = _load(OUT_PATH)
    cities = _load(os.path.join("config", "cities.json"))
    cities = cities["cities"] if isinstance(cities, dict) and "cities" in cities else cities
    diseases = _load(os.path.join("config", "diseases.json"))
    diseases = diseases["diseases"] if isinstance(diseases, dict) and "diseases" in diseases else diseases
    dids = [d["id"] for d in diseases]

    generated_at = _load(os.path.join("data", "grid.json")).get("generated_at", "")
    gy = int(generated_at[0:4]) if generated_at[0:4].isdigit() else TY_YEAR
    if gy != arch.get("ty_year"):
        print("refresh_search: grid year %s != archive ty_year %s (season rolled over) - re-run the full "
              "backfill for the new season. Skipping." % (gy, arch.get("ty_year")))
        return
    as_of = _as_of(generated_at)

    trends = _load(th_path).get("diseases", {})
    tseries = _parse_tseries(trends, dids)
    search_by_city, _ = _search_blocks(tseries, dids, cities, as_of)

    # Guard against a thin / degraded pull silently overwriting good committed lines: only overwrite a city
    # whose STATE actually produced a series this run. A state with no series for ANY disease this run would
    # otherwise drop to the national-mean / zero fallback, so we PRESERVE its prior committed block instead.
    states_present = set()
    for did in dids:
        states_present |= set(tseries.get(did, {}).keys())
    state_by_cid = {c["id"]: c.get("state", "") for c in cities}

    updated, preserved = 0, 0
    for cid, block in arch.get("cities", {}).items():
        sb = search_by_city.get(cid)
        if sb is None:
            continue
        if state_by_cid.get(cid, "") in states_present:
            block["search"] = sb
            updated += 1
        else:
            preserved += 1  # null-geo / no series this run: keep last-good rather than degrade to fallback

    arch["generated_at"] = generated_at
    arch["asOf"] = as_of
    write_json_atomic(OUT_PATH, arch, indent=None)
    print("refresh_search: recomputed EXACT search for %d cities to as-of week %d (ty len %d); "
          "%d preserved (state had no series this run)." % (updated, as_of, as_of + 1, preserved))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build or refresh the committed season-trend archive.")
    ap.add_argument("--daily", action="store_true",
                    help="CI daily: extend weather ty from data/grid.json; length-pad search ty (no backfills needed).")
    ap.add_argument("--search-only", action="store_true",
                    help="CI weekly: recompute EXACT search ly+ty from data/backfill/trends_history.json "
                         "(written by refresh_trends_timeseries.py); leaves weather blocks untouched.")
    args = ap.parse_args()
    if args.search_only:
        refresh_search()
    elif args.daily:
        update_daily()
    else:
        main()
