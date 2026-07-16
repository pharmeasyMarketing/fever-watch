"""Build the compact, committed season-trend archive from the (gitignored) backfill inputs.

Consumes:
  - data/backfill/weather_{2025,2026}.json  (NASA POWER daily by_date -> per-family scores; build_weather.py --start/--end)
  - data/backfill/trends_history.json        (SerpApi per-state weekly interest-over-time; backfill_trends.py)
  - config/cities.json, config/diseases.json, config/in_state_geo.json
  - data/grid.json generated_at              (for the "as of" current week index)

Produces (committed, compact ~60 KB):
  - data/archive/trend_series.json

This is the REAL replacement for the deterministic mock last-year line in the season-trend module. main()
builds the WEATHER and SEARCH metrics; the one-off --history step then merges in the REAL labs.ly (from the
TC 2025 weekly feed) and the REAL, dial-consistent OVERALL line (so all four tabs are real). The two main()
metrics mirror exactly how the trend module derives them from the live grid:
  - weather metric = mean over the 4 diseases of each disease's weather sub-score (= its family score),
    i.e. (3 x mosquito + 1 x waterborne) / 4, matching trend.js meanSignal(cells,'weather') / _t_mean.
  - search metric  = mean over the 4 diseases of the city's state weekly search interest, matching
    meanSignal(cells,'trends'). A null/empty state falls back to that disease's national mean (mean over
    the states present), mirroring CachedTrendsProvider's national-mean fallback.

Both metrics are stored for BOTH years (ly = 2025 full 22-week season, ty = 2026 partial up to the current
week). The search metric MUST take this-year from the same per-state TIMESERIES as last-year (not the live
GEO_MAP_0 value) so the two lines share one normalisation. Weeks are anchored to 1 Jun + 7 day steps, exactly
like trend.js build() / _trend_series, so the archive lines align with the module's week axis.

Four modes (run from the repo root):
  python src/build_archive.py                 # full build from the backfills (weather + search, both years)
  python src/build_archive.py --daily         # CI daily: extend weather ty + labs ty + overall ty from grid.json;
                                              #   length-pad search ty
  python src/build_archive.py --search-only   # CI weekly: recompute EXACT search ly+ty from a fresh per-state
                                              #   TIMESERIES (data/backfill/trends_history.json), weather untouched.
                                              #   Fed by refresh_trends_timeseries.py. This is what makes the
                                              #   cross-year SEARCH YoY EXACT (one normalisation for both years).
  python src/build_archive.py --history       # ONE-OFF (re-run on a new 2025 lab pull): MERGE the REAL labs.ly
                                              #   (from data/lab_feed_2025_historic.csv, the TC 2025 weekly feed,
                                              #   COUNTS-FREE 0-100 only) AND the REAL, dial-consistent overall
                                              #   {ly,ty} into the committed archive, PRESERVING each city's
                                              #   weather/search blocks. Run build_lab_feed_2025_historic.py + the
                                              #   full build first so the inputs and city blocks exist. (Alias:
                                              #   --labs-history, kept for back-compat, now also builds overall.)
"""
import argparse
import csv
import datetime
import json
import math
import os

from iohelpers import write_json_atomic

try:  # works whether src/ is on sys.path (import signals) or imported as src.signals
    from signals.gsheet_api import _signal as _lab_signal
    from consolidate import consolidate as _consolidate
except (ImportError, ValueError):  # pragma: no cover - import path shim
    from .signals.gsheet_api import _signal as _lab_signal
    from .consolidate import consolidate as _consolidate

NW = 22                      # weeks in the season window (1 Jun -> 30 Oct), matches TREND_SHAPE length
LY_YEAR, TY_YEAR = 2025, 2026
TREND_TOL_DAYS = 4           # nearest-week match tolerance (Google's weekly buckets drift vs the 1-Jun anchor across a year)
OUT_PATH = os.path.join("data", "archive", "trend_series.json")
CONSOL_PATH = os.path.join("config", "consolidation.json")
LAB_FEED_2025_CSV = os.path.join("data", "lab_feed_2025_historic.csv")   # TC 2025 weekly feed (build_lab_feed_2025_historic.py)
LAB_MIN_TESTS = 30        # confidence gate (matches gsheet_api default / lab_feed builder)
LAB_REF_PCT = 35.0        # fallback positivity reference for any disease not in the per-disease map
# Per-disease positivity reference (% positivity -> full 100 signal). MUST match
# config/signals.json ref_positivity_pct_by_disease + scripts/build_lab_feed_2025_historic.py.
LAB_REF_BY_DISEASE = {"dengue": 25.0, "malaria": 4.0, "chikungunya": 15.0, "typhoid": 45.0}


def _r(x):
    """Round half up; identical to trend.js r() / build_site.py _t_r."""
    return int(math.floor((x or 0) + 0.5))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _as_of(generated_at):
    ga = generated_at or ""
    try:  # IST (UTC+5:30) date parts, matching trend.js + build_site as_of so the archive ty length stays in sync
        _gi = datetime.datetime.fromisoformat(ga.replace("Z", "+00:00")) + datetime.timedelta(hours=5, minutes=30)
        gy, gm, gd = _gi.year, _gi.month, _gi.day
    except Exception:
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


def _prune_to_config(arch):
    """Drop archive city blocks not in config/cities.json (the locked 209-city scope), so the committed
    archive stays exactly the live city set. Returns how many were dropped. Cities removed from config
    (e.g. the 19 with no lab data) never render a page, so their stale blocks are pure bloat."""
    c = _load(os.path.join("config", "cities.json"))
    ids = {x["id"] for x in (c["cities"] if isinstance(c, dict) and "cities" in c else c)}
    cities = arch.get("cities", {})
    drop = [k for k in cities if k not in ids]
    for k in drop:
        del cities[k]
    return len(drop)


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
            # None (not 0) when NO state has a point within tolerance of this week - i.e. the week is
            # beyond the latest timeseries pull (between weekly refreshes). Lets carry_forward inherit the
            # last good value instead of collapsing the current week to a misleading 0.
            natmean_cache[key] = (sum(vals) / len(vals)) if vals else None
        return natmean_cache[key]

    def search_metric(year, w, state):
        target = _week_date(year, w)
        vals = []
        for did in dids:
            s = tseries[did].get(state)
            v = _nearest(s, target) if s else None
            if v is None:
                v = national_mean(did, target)
            if v is not None:
                vals.append(v)
        return _r(sum(vals) / float(len(vals))) if vals else None  # None = no data this week -> carried forward

    blocks, weak = {}, 0
    for c in cities:
        cid, state = c["id"], c.get("state", "")
        blocks[cid] = {
            "ly": carry_forward([search_metric(LY_YEAR, w, state) for w in range(nw)]),
            "ty": carry_forward([search_metric(TY_YEAR, w, state) for w in range(as_of + 1)]),
        }
        if state not in tseries[dids[0]] and state not in tseries[dids[-1]]:
            weak += 1
    return blocks, weak


def _search_per_disease(tseries, dids):
    """Return a closure search_d(did, year, w, state) -> int 0-100 = that ONE disease's state weekly
    interest at week w, with the SAME nearest-week match + national-mean fallback as _search_blocks
    (one Google normalisation across both years). This is the per-disease decomposition of the mean
    that _search_blocks collapses, so the per-disease consolidate() below sees the exact search the live
    grid would have for that disease/state/week."""
    natmean_cache = {}

    def national_mean(did, target):
        key = (did, target)
        if key not in natmean_cache:
            vals = [_nearest(s, target) for s in tseries[did].values()]
            vals = [v for v in vals if v is not None]
            natmean_cache[key] = (sum(vals) / len(vals)) if vals else 0.0
        return natmean_cache[key]

    def search_d(did, year, w, state):
        target = _week_date(year, w)
        s = tseries[did].get(state)
        v = _nearest(s, target) if s else None
        if v is None:
            v = national_mean(did, target)
        return _r(v)
    return search_d


def _weather_per_disease(weather_by_date, fam_of):
    """Return a closure weather_d(did, year, w, cid) -> int|None = that ONE disease's family weather
    score from the backfill (families[family_of[did]]) for the city/week, or None if no backfill cell.
    Per-disease decomposition of weather_metric()'s mean, so consolidate() sees the live grid's weather."""
    def weather_d(did, year, w, cid):
        e = weather_by_date.get(year, {}).get(_week_date(year, w).isoformat(), {}).get(cid)
        if not e:
            return None
        return e.get("families", {}).get(fam_of[did])
    return weather_d


def _load_labs_2025_weekly(path, dids, *, min_tests=LAB_MIN_TESTS, ref_pct=LAB_REF_PCT):
    """Parse the TC 2025 weekly feed (data/lab_feed_2025_historic.csv) into
    labs2025[(cid, did, season_week-1)] = 0-100 gated signal (None below the gate), using _signal()
    exactly like the live feed. season_week 1 (1 Jun) -> archive index 0 = week 0 = _week_date(LY,0).
    Raw counts stay local; only the 0-100 signal is materialised (COUNTS-FREE). Returns (sig_map, cids_seen)."""
    sig = {}
    cids_seen = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = (row.get("city") or "").strip()
            did = (row.get("disease") or "").strip().lower()
            if not cid or did not in dids:
                continue
            try:
                wk = int(row.get("season_week", 0)) - 1
            except (TypeError, ValueError):
                continue
            if wk < 0 or wk >= NW:
                continue
            tests = _to_int_lab(row.get("tests_booked"))
            pos = _to_int_lab(row.get("positives")) or 0
            if tests is None:
                continue
            cids_seen.add(cid)
            ref = LAB_REF_BY_DISEASE.get(did, ref_pct)  # per-disease reference, ref_pct fallback
            sig[(cid, did, wk)] = _lab_signal(tests, pos, min_tests, ref)  # 0-100 or None below the 30 gate
    return sig, cids_seen


def _state_search_none(tseries, dids):
    """Per-disease per-state weekly search with None (not 0) beyond the pull, mirroring _search_blocks'
    None-propagation so carry_forward pads stale weeks instead of collapsing them to a misleading 0.
    (This differs from _search_per_disease, whose 0.0 fallback exists to feed consolidate seeds.)"""
    natmean_cache = {}

    def national_mean(did, target):
        key = (did, target)
        if key not in natmean_cache:
            vals = [_nearest(s, target) for s in tseries[did].values()]
            vals = [v for v in vals if v is not None]
            natmean_cache[key] = (sum(vals) / len(vals)) if vals else None
        return natmean_cache[key]

    def f(did, year, w, state):
        target = _week_date(year, w)
        s = tseries[did].get(state)
        v = _nearest(s, target) if s else None
        if v is None:
            v = national_mean(did, target)
        return _r(v) if v is not None else None
    return f


def _state_search_blocks(tseries, dids, states, as_of, nw=NW):
    """archive['states'] = {state: {disease: {ly, ty}}} - the per-disease decomposition of the city search
    metric, keyed by STATE so 209 cities share ~30 compact blocks (search is state-resolution anyway).
    Both years read from ONE timeseries pull (one Google normalisation), same as _search_blocks. Feeds the
    city x disease pages' Searches tab + sparklines."""
    sd = _state_search_none(tseries, dids)
    out = {}
    for st in sorted(states):
        out[st] = {}
        for did in dids:
            out[st][did] = {
                "ly": carry_forward([sd(did, LY_YEAR, w, st) for w in range(nw)]),
                "ty": carry_forward([sd(did, TY_YEAR, w, st) for w in range(as_of + 1)]),
            }
    return out


def _labs_ly_from_tc(labs2025, cids_seen, dids):
    """COUNTS-FREE last-year (2025) labs.ly per city from the TC weekly signal map. Week metric = mean over
    the diseases with a non-None signal that week (None if all None), then carry_forward. An all-None city
    -> all zeros so the frontend keeps the 'coming soon' empty state. Returns {cid: [22 ints]}."""
    blocks = {}
    for cid in cids_seen:
        weekly = []
        for wk in range(NW):
            sigs = [labs2025.get((cid, did, wk)) for did in dids]
            sigs = [s for s in sigs if s is not None]
            weekly.append(_r(sum(sigs) / float(len(sigs))) if sigs else None)
        ly = carry_forward(weekly)
        blocks[cid] = ly if any(v is not None for v in weekly) else [0] * NW
    return blocks


def _city_headline(scores, cb):
    """The live city headline blend = top_weight x max(scores) + rest_weight x mean(the OTHER scores),
    rounded - byte-identical to build_daily.city_blend() / mobile.js / desktop.js. `scores` is the list of
    per-disease 'score' values; cb = config consolidation.json city_blend."""
    if not scores:
        return None
    ordered = sorted(scores, reverse=True)
    top = ordered[0]
    rest = ordered[1:]
    mean_rest = (sum(rest) / len(rest)) if rest else float(top)
    return int(round(cb["top_weight"] * top + cb["rest_weight"] * mean_rest))


def _overall_blocks(cities, dids, fam_of, weather, tseries, labs2025, consol, as_of):
    """Build the REAL, DIAL-CONSISTENT overall {ly, ty} per city, computed the SAME max-dominant way the
    live dial is. For each (city, week, disease) we run consolidate() on (weather_d, search_d, labs_d):
      - ly (2025, full 22 weeks): weather from weather_2025, search from the per-state timeseries, labs from
        the TC 2025 weekly signal (None below the gate -> that disease is forecast-capped that week);
      - ty (2026, weeks 0..as_of): weather from weather_2026, search from the timeseries this year, labs
        unavailable historically -> positivity=None (every disease forecast-capped). update_daily() then
        overwrites ty[as_of] from the live grid headline (which DOES carry live positivity), so the current
        week equals the dial; the seeded earlier weeks are the best historical reconstruction.
    The per-disease scores are combined with _city_headline (0.8 max + 0.2 mean-rest), then carry_forward.
    Returns {cid: {"ly": [22 ints], "ty": [as_of+1 ints]}}. COUNTS-FREE (only 0-100 -> 0-100)."""
    cb = consol["city_blend"]
    search_d = _search_per_disease(tseries, dids)
    weather_d = _weather_per_disease(weather, fam_of)

    def headline(year, w, cid, state, with_labs):
        scores = []
        for did in dids:
            wx = weather_d(did, year, w, cid)
            if wx is None:
                return None  # no weather backfill for this city/week -> week is missing, carry_forward fills it
            sr = search_d(did, year, w, state)
            pos = labs2025.get((cid, did, w)) if with_labs else None
            scores.append(_consolidate({"weather": wx, "trends": sr, "positivity": pos}, consol)["score"])
        return _city_headline(scores, cb)

    blocks = {}
    for c in cities:
        cid, state = c["id"], c.get("state", "")
        ly = carry_forward([headline(LY_YEAR, w, cid, state, with_labs=True) for w in range(NW)])
        ty = carry_forward([headline(TY_YEAR, w, cid, state, with_labs=False) for w in range(as_of + 1)])
        blocks[cid] = {"ly": ly, "ty": ty}
    return blocks


def build_history():
    """ONE-OFF / RE-RUNNABLE (CHANGE #1 + #2): MERGE the REAL, COUNTS-FREE labs.ly (from the TC 2025 weekly
    feed) AND the REAL, DIAL-CONSISTENT overall {ly, ty} into the EXISTING committed archive, PRESERVING each
    city's weather{ly,ty} and search{ly,ty}. Does NOT run the full main() (which would regenerate weather/
    search from the gitignored local backfills and could clobber the committed lines).

    Inputs (all local; weather backfills are gitignored, so this is a one-off, not a CI step):
      - data/lab_feed_2025_historic.csv      (TC 2025 weekly: regenerate first via build_lab_feed_2025_historic.py)
      - data/backfill/weather_{2025,2026}.json  (per-disease family weather for ly + ty seeds)
      - data/backfill/trends_history.json       (per-disease/state weekly search for ly + ty)
      - config/{cities,diseases,consolidation}.json + data/grid.json (as-of week)

    Run the full build first so the per-city weather/search blocks exist; this only ADDS/REPLACES labs + overall.
    The daily cron (update_daily) then keeps overall.ty + labs.ty current from the live grid."""
    if not os.path.exists(OUT_PATH):
        print("build_history: %s missing - run the full build_archive first. Skipping." % OUT_PATH)
        return
    if not os.path.exists(LAB_FEED_2025_CSV):
        print("build_history: %s missing - run scripts/build_lab_feed_2025_historic.py first. Skipping." % LAB_FEED_2025_CSV)
        return

    cities = _load(os.path.join("config", "cities.json"))
    cities = cities["cities"] if isinstance(cities, dict) and "cities" in cities else cities
    diseases = _load(os.path.join("config", "diseases.json"))
    diseases = diseases["diseases"] if isinstance(diseases, dict) and "diseases" in diseases else diseases
    fam_of = {d["id"]: d["family"] for d in diseases}
    dids = [d["id"] for d in diseases]
    consol = _load(CONSOL_PATH)

    weather = {
        LY_YEAR: _load(os.path.join("data", "backfill", "weather_%d.json" % LY_YEAR)).get("by_date", {}),
        TY_YEAR: _load(os.path.join("data", "backfill", "weather_%d.json" % TY_YEAR)).get("by_date", {}),
    }
    trends = _load(os.path.join("data", "backfill", "trends_history.json")).get("diseases", {})
    tseries = _parse_tseries(trends, dids)

    generated_at = _load(os.path.join("data", "grid.json")).get("generated_at", "")
    as_of = _as_of(generated_at)

    # CHANGE #1: real labs.ly from the TC 2025 weekly feed (COUNTS-FREE 0-100 gated signal).
    labs2025, labs_cids = _load_labs_2025_weekly(LAB_FEED_2025_CSV, dids)
    ly_blocks = _labs_ly_from_tc(labs2025, labs_cids, dids)

    # CHANGE #2: real, dial-consistent overall {ly, ty-seed}.
    overall_blocks = _overall_blocks(cities, dids, fam_of, weather, tseries, labs2025, consol, as_of)

    arch = _load(OUT_PATH)
    cities_blk = arch.setdefault("cities", {})
    labs_nonzero = 0

    # --- v1.1 (city x disease pages): per-disease decompositions, all COUNTS-FREE 0-100 ---
    # scores: the disease's own dial line, consolidate()d per week exactly like overall but unblended.
    # ly runs with the 2025 labs signal; ty is seeded labs-free and update_daily overwrites ty[as_of]
    # daily from the live grid cell (which DOES carry live positivity), so the line ends on the dial.
    search_d = _search_per_disease(tseries, dids)
    weather_d = _weather_per_disease(weather, fam_of)

    def disease_score(cid, state, did, year, w, with_labs):
        wx = weather_d(did, year, w, cid)
        if wx is None:
            return None
        sr = search_d(did, year, w, state)
        pos = labs2025.get((cid, did, w)) if with_labs else None
        return _consolidate({"weather": wx, "trends": sr, "positivity": pos}, consol)["score"]

    fams = sorted(set(fam_of.values()))

    def fam_metric(year, w, cid, fam):
        e = weather.get(year, {}).get(_week_date(year, w).isoformat(), {}).get(cid)
        return None if not e else e.get("families", {}).get(fam)

    for c in cities:
        cid = c["id"]
        block = cities_blk.setdefault(cid, {})  # add even if absent from the prior weather/search build
        ly = ly_blocks.get(cid, [0] * NW)
        prior_labs_ty = (block.get("labs") or {}).get("ty", [])
        block["labs"] = {"ly": ly, "ty": prior_labs_ty}  # keep grid-seeded labs.ty (extended by update_daily)
        block["overall"] = overall_blocks.get(cid, {"ly": [0] * NW, "ty": []})
        if any(v for v in ly):
            labs_nonzero += 1

        # per-family weather lines (mosquito diseases share one; typhoid the other) - the disease pages'
        # Weather tab. Preserve prior ty tail beyond the backfill via merge with the existing block.
        prior_bf = block.get("byFamily") or {}
        block["byFamily"] = {}
        for fam in fams:
            f_ly = carry_forward([fam_metric(LY_YEAR, w, cid, fam) for w in range(NW)])
            f_ty = carry_forward([fam_metric(TY_YEAR, w, cid, fam) for w in range(as_of + 1)])
            prior_ty = (prior_bf.get(fam) or {}).get("ty", [])
            for i, pv in enumerate(prior_ty[:len(f_ty)]):
                # the daily cron upserts live grid values; prefer those over backfill carry-forward
                if pv is not None and i > 0 and f_ty[i] == f_ty[i - 1]:
                    f_ty[i] = pv
            block["byFamily"][fam] = {"ly": f_ly, "ty": f_ty}

        # per-disease: score line always; labs line ONLY where the 2025 feed has real weekly signal
        # (its absence keeps the honest "coming soon" state on that disease's Labs tab).
        prior_bd = block.get("byDisease") or {}
        bd = {}
        for did in dids:
            entry = {"score": {
                "ly": carry_forward([disease_score(cid, c.get("state", ""), did, LY_YEAR, w, True) for w in range(NW)]),
                "ty": carry_forward([disease_score(cid, c.get("state", ""), did, TY_YEAR, w, False) for w in range(as_of + 1)]),
            }}
            weekly = [labs2025.get((cid, did, wk)) for wk in range(NW)]
            if any(v is not None for v in weekly):
                entry["labs"] = {"ly": carry_forward(weekly),
                                 "ty": (prior_bd.get(did) or {}).get("labs", {}).get("ty", [])}
            bd[did] = entry
        block["byDisease"] = bd

    # per-state per-disease EXACT search lines (the Searches tab). ly (2025) is stable history; ty is as
    # fresh as the local trends_history pull and is fully recomputed by the WEEKLY CI refresh_search().
    arch["states"] = _state_search_blocks(tseries, dids, {c.get("state", "") for c in cities}, as_of)

    _prune_to_config(arch)
    write_json_atomic(OUT_PATH, arch, indent=None)
    size = os.path.getsize(OUT_PATH)
    print("build_history: merged real labs.ly + overall{ly,ty} + v1.1 byDisease/byFamily/states into %s "
          "for %d config cities (%d with real >0 lab history; ty seeded to as-of week %d, len %d). %d bytes. "
          "weather/search city blocks PRESERVED."
          % (OUT_PATH, len(cities), labs_nonzero, as_of, as_of + 1, size))


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
      - LABS is extended from the live grid the same way as weather: ty[as_of] = mean over the diseases of
        each cell's signals.positivity (already the 0-100 gated positivity signal, so it stays COUNTS-FREE).
        It shares the same scale as labs.ly (both apply gsheet_api._signal vs ref 35%), so the lab YoY is
        exact. Cities with no live positivity (mock/no-data) keep their existing ty (no overwrite).
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
    fam_of = {d["id"]: d.get("family") for d in diseases}

    consol = _load(CONSOL_PATH)
    cb = consol["city_blend"]

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

    def headline(cells):
        # The live dial headline = 0.8 x max disease score + 0.2 x mean of the rest (build_daily.city_blend /
        # mobile.js / desktop.js). overall.ty[as_of] MUST equal this so the trend line ends on the dial value.
        scores = [cells[did]["score"] for did in dids if did in cells and cells[did].get("score") is not None]
        return _city_headline(scores, cb)

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
        # LABS: extend ty from the live grid like weather (mean of signals.positivity over diseases). Only
        # cities that already have a labs block (i.e. real 2025 labs.ly) get a ty - a city with no lab
        # history stays on the "coming soon" empty state. signals.positivity is already the 0-100 gated
        # signal, so this is COUNTS-FREE.
        labs = block.get("labs")
        if labs is not None:
            labs.setdefault("ty", [])
            upsert(labs["ty"], as_of, metric(cells, "positivity"))
        # OVERALL: upsert ty[as_of] = the live grid city headline (0.8 max + 0.2 mean-rest over the 4 disease
        # scores). This MUST equal the dial. Earlier ty weeks keep their historical seed (build_history); only
        # the current week is overwritten daily from the live grid. Only cities that already carry a real
        # overall block (length-22 ly) get a ty update - others stay on the JS mock fallback.
        overall = block.get("overall")
        if overall is not None and len(overall.get("ly", [])) == NW:
            overall.setdefault("ty", [])
            upsert(overall["ty"], as_of, headline(cells))
        # v1.1 (city x disease pages): keep the per-family weather, per-disease score and per-disease labs
        # ty vectors current from the live grid, same COUNTS-FREE rules as their city-level counterparts.
        bf = block.get("byFamily")
        if bf:
            for fam, vec in bf.items():
                did = next((d for d in dids if fam_of.get(d) == fam and d in cells), None)
                if did is not None and isinstance(vec, dict):
                    upsert(vec.setdefault("ty", []), as_of, cells[did].get("signals", {}).get("weather"))
        bd = block.get("byDisease")
        if bd:
            for did, entry in bd.items():
                if did not in cells or not isinstance(entry, dict):
                    continue
                sc = entry.get("score")
                if sc is not None and len(sc.get("ly", [])) == NW:
                    upsert(sc.setdefault("ty", []), as_of, cells[did].get("score"))
                lb = entry.get("labs")
                if lb is not None:
                    upsert(lb.setdefault("ty", []), as_of, cells[did].get("signals", {}).get("positivity"))
        updated += 1

    # v1.1: length-pad the per-state per-disease search ty (recomputed EXACT by the weekly refresh_search).
    for st_block in (arch.get("states") or {}).values():
        for vec in st_block.values():
            if isinstance(vec, dict):
                pad_only(vec.setdefault("ty", []), as_of)

    arch["generated_at"] = generated_at
    arch["asOf"] = as_of
    _prune_to_config(arch)
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

    # v1.1: recompute the per-state per-disease EXACT search blocks from the same fresh pull, with the
    # same thin-pull guard (a state absent from this run keeps its last-good block).
    all_states = {c.get("state", "") for c in cities}
    fresh_states = _state_search_blocks(tseries, dids, all_states & states_present, as_of)
    st_arch = arch.setdefault("states", {})
    st_arch.update(fresh_states)

    arch["generated_at"] = generated_at
    arch["asOf"] = as_of
    _prune_to_config(arch)
    write_json_atomic(OUT_PATH, arch, indent=None)
    print("refresh_search: recomputed EXACT search for %d cities to as-of week %d (ty len %d); "
          "%d preserved (state had no series this run)." % (updated, as_of, as_of + 1, preserved))


def _to_int_lab(v):
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def carry_forward(arr):
    """Replace any None with the previous (then next) non-None, so a stray missing week never breaks the line.
    Identical to main()'s local carry_forward; lifted to module scope so the labs builder reuses it."""
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build or refresh the committed season-trend archive.")
    ap.add_argument("--daily", action="store_true",
                    help="CI daily: extend weather ty + labs ty + overall ty from data/grid.json; length-pad "
                         "search ty (no backfills needed).")
    ap.add_argument("--search-only", action="store_true",
                    help="CI weekly: recompute EXACT search ly+ty from data/backfill/trends_history.json "
                         "(written by refresh_trends_timeseries.py); leaves weather blocks untouched.")
    ap.add_argument("--history", action="store_true",
                    help="ONE-OFF: MERGE the REAL COUNTS-FREE labs.ly (from data/lab_feed_2025_historic.csv, the "
                         "TC 2025 feed) AND the REAL dial-consistent overall{ly,ty} into the archive, PRESERVING "
                         "each city's weather/search blocks. Run build_lab_feed_2025_historic.py + the full build first.")
    ap.add_argument("--labs-history", dest="history", action="store_true",
                    help="Deprecated alias for --history (now builds labs.ly from the TC feed AND overall).")
    args = ap.parse_args()
    if args.history:
        build_history()
    elif args.search_only:
        refresh_search()
    elif args.daily:
        update_daily()
    else:
        main()
