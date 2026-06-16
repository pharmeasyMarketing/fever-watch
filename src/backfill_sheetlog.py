#!/usr/bin/env python3
"""One-time historical backfill generator for the Google Sheets raw_data tab.

Replicates the live raw_data schema (the 26 columns A..Z) for historical dates so
the user can import them into the Sheet. OFFLINE only: never POSTs to the webhook,
needs no token. It is the STRICT, one-shot counterpart to the best-effort live
logger (src/sheetlog.py).

Two output formats for the SAME rows:

  * xlsx (DEFAULT, the deliverable): the computed columns K weather_score,
    L trends_score, S confidence, T score, U band, V mode are written as REAL
    in-sheet FORMULAS - byte-faithful to the Apps Script `_setRawFormulas`
    templates (docs/sheets_logging.md) with the 1-based row number substituted -
    so the whole build-up is transparent and recomputes on import. Google Sheets
    evaluates these on import. Requires openpyxl (a dev-only dependency, imported
    lazily inside the xlsx path; the csv path stays stdlib-only).

  * csv (--format csv): the legacy path - the computed columns hold LITERAL VALUES
    (the Python-computed results). Correct for fixed historical data, no deps.

The raw-input columns (A-J, M-R, W-Z) are identical VALUES in both formats; only
K/L/S/T/U/V differ (formulas vs literals). The header row is byte-identical to the
live raw_data header in both.

Two date ranges (locked decisions):
  * 2026 backfill: 2026-06-01 .. latest backfilled date. (The raw_data tab was RESET 2026-06-16 for the
    NOAA CPC rain switch, so the FULL Jun 1 history is regenerated; was 06-01..06-08 when the live tab
    already held 06-09+.) -> data/backfill/sheet/raw_data_2026_backfill.{xlsx,csv}  (import into the tab).
  * 2025 backfill: 2025-06-01 .. 2025-10-30, DAILY (exact replicate).
    -> data/backfill/sheet/raw_data_2025.{xlsx,csv}  (a SEPARATE new spreadsheet).

Per (date, city) we emit 5 rows: one per city x disease + one disease="OVERALL"
city-blend row. 228 cities -> 5 x 228 = 1,140 rows/day.

Inputs (all under data/backfill/, which is gitignored):
  weather_{year}.json : by_date[YYYY-MM-DD][cityId] = {agg:{...}, families:{...}}
  trends_history.json : diseases[id].by_state[state] = [[week_start_iso, value], ...]
Plus the live configs (cities, diseases, signals, consolidation) and the same
mock positivity + cached _norm rules the live pipeline uses, so every value
matches what the live engine would have produced.

Run (from the project root):
    python src/backfill_sheetlog.py                 # xlsx (default, with formulas)
    python src/backfill_sheetlog.py --format csv    # legacy literal-value CSVs
    python src/backfill_sheetlog.py --format both    # both
"""
from __future__ import annotations

import csv
import json
import os
import sys
from bisect import bisect_right
from datetime import date, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from consolidate import band, consolidate  # noqa: E402
from signals.cached import SIGNAL_FLOOR, _norm  # same state-norm + floor as the live cached provider
from signals.mock import MockPositivityProvider  # date-independent positivity seed {city}|{disease}|v1

ROOT = os.path.dirname(SRC_DIR)
BACKFILL_DIR = os.path.join(ROOT, "data", "backfill")
OUT_DIR = os.path.join(BACKFILL_DIR, "sheet")
WEATHER_SOURCE = "rain: NOAA CPC (public domain); temp/humidity: NASA POWER (public domain)"

# The 27-column raw_data header, byte-identical to HEADERS.raw_data in the Apps
# Script (docs/sheets_logging.md) and the order src/sheetlog.py posts.
HEADER = [
    "date", "run_id", "city", "state", "disease", "family",
    "temp_c", "humidity_pct", "rain_7d_mm", "rain_14d_mm",
    "weather_score", "trends_score", "trends_keywords", "news_spike", "positivity",
    "w_weather", "w_trends", "w_positivity",
    "confidence", "score", "band", "mode",
    "trends_state_interest", "weather_fresh", "trends_fresh", "stale", "weather_source",
]


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def daterange(start: date, end_inclusive: date):
    n = (end_inclusive - start).days
    for i in range(n + 1):
        yield start + timedelta(days=i)


# --- trends history: weekly value carried across the week, with national-mean fallback ---------
class TrendsHistory:
    """Mirror of signals.cached.CachedTrendsProvider, but date-aware: for a given
    date it resolves the latest weekly value (week_start <= date) per disease/state,
    carrying the weekly reading across its week. National-mean fallback (over the
    per-state values AT that week) when the city's state has no row, matching the
    live _norm rule and rounding."""

    def __init__(self, path: str):
        data = load_json(path)
        self.diseases = data.get("diseases", {})
        # Per disease: normalized-state -> (sorted week_start list, parallel value list)
        self._idx: dict = {}
        # Per disease: ordered list of week_starts shared by all states (validated identical).
        self._weeks: dict = {}
        for did, d in self.diseases.items():
            by_state = d.get("by_state") or {}
            if not by_state:
                raise SystemExit(f"ABORT: trends_history disease '{did}' has no by_state data.")
            week_shapes = set()
            norm_map: dict = {}
            for st, series in by_state.items():
                weeks = [w[0] for w in series]
                vals = [w[1] for w in series]
                if weeks != sorted(weeks):
                    raise SystemExit(f"ABORT: trends weeks not sorted for {did}/{st}.")
                week_shapes.add(tuple(weeks))
                norm_map[_norm(st)] = (weeks, vals)
            if len(week_shapes) != 1:
                raise SystemExit(f"ABORT: trends week_start sets differ across states for '{did}'.")
            self._idx[did] = norm_map
            self._weeks[did] = list(next(iter(week_shapes)))

    def _week_pos(self, did: str, iso_date: str) -> int:
        """Index of the latest week_start <= iso_date for this disease; -1 if none (before history)."""
        weeks = self._weeks[did]
        # bisect_right on the sorted ISO strings (lexicographic == chronological for YYYY-MM-DD).
        return bisect_right(weeks, iso_date) - 1

    def raw_for(self, disease_id: str, state: str, iso_date: str):
        """Pre-floor state interest for (disease, state) on iso_date: the carried weekly
        value, or the national mean (over per-state values at that week) when the state
        is absent. None only if iso_date precedes all history (caller treats as fail-loud)."""
        norm_map = self._idx[disease_id]
        pos = self._week_pos(disease_id, iso_date)
        if pos < 0:
            return None
        st_entry = norm_map.get(_norm(state))
        if st_entry is not None:
            return st_entry[1][pos]
        # National-mean fallback: mean of every state's value at this week, rounded (matches cached.py).
        vals = [v[pos] for (_w, v) in norm_map.values()]
        return round(sum(vals) / len(vals)) if vals else None


def floor_trends(raw):
    """Engine input from the pre-floor state interest: max(4, min(100, raw)) (cached.py)."""
    return SIGNAL_FLOOR if raw is None else max(SIGNAL_FLOOR, min(100, int(raw)))


# --- in-sheet FORMULA strings for the computed columns (xlsx path only) -------------------------
# These are byte-faithful to the Apps Script `_setRawFormulas` templates in
# docs/sheets_logging.md (the live formulas, already verified to reproduce the
# grid score), with the literal `'... ' + r + ' ...'` JS concatenations collapsed
# to the actual 1-based sheet row number `r`. Excel-compatible (IF, IFS, MIN, MAX,
# ROUND, MAXIFS, SUMIFS, COUNTIFS, IFERROR all exist in both Excel and Sheets).
#
# Disease (non-OVERALL) rows: K, L, S, T, V are per-row build-ups; U is shared.
# OVERALL rows: K, L, S are blank (=""); T/U/V are the blend formulas.

def _f_weather(r: int) -> str:  # K weather_score - family-weighted build-up over G/H/I/J
    return (
        '=IF($F' + str(r) + '="mosquito",ROUND((0.45*IF(OR($G' + str(r) + '<=14,$G' + str(r)
        + '>=38),0,MAX(0,MIN(1,1-(($G' + str(r) + '-29)/13)^2)))+0.35*MAX(0,MIN(1,$J' + str(r)
        + '/60))+0.20*MAX(0,MIN(1,($H' + str(r) + '-40)/50)))*100),IF($F' + str(r)
        + '="waterborne",ROUND((0.6*MAX(0,MIN(1,$I' + str(r) + '/80))+0.4*MAX(0,MIN(1,$J' + str(r)
        + '/80)))*100),""))'
    )


def _f_trends(r: int) -> str:  # L trends_score - the state Trends interest W, floored 4 capped 100
    return '=IF($W' + str(r) + '="","",MAX(4,MIN(100,$W' + str(r) + ')))'


def _base_conf(r: int) -> str:  # the label expression reused inside the S downgrade
    return (
        'IF($O' + str(r) + '="","Forecast only",IF(MAX($K' + str(r) + ',$L' + str(r) + ',$O'
        + str(r) + ')-MIN($K' + str(r) + ',$L' + str(r) + ',$O' + str(r) + ')<22,"High","Moderate"))'
    )


def _f_confidence(r: int) -> str:  # S confidence - base label with a one-step STALE (Z) downgrade
    base = _base_conf(r)
    return (
        '=IF($Z' + str(r) + '=TRUE,IFS(' + base + '="High","Moderate",' + base
        + '="Moderate","Low",TRUE,' + base + '),' + base + ')'
    )


def _f_score(r: int) -> str:  # T score - forecast (capped 69) vs confirmed (agree multiplier)
    return (
        '=IF($O' + str(r) + '="",ROUND(MIN(69,($P' + str(r) + '/100)*$K' + str(r) + '+($Q' + str(r)
        + '/100)*$L' + str(r) + ')),'
        + 'ROUND(MIN(100,(($P' + str(r) + '/100)*$K' + str(r) + '+($Q' + str(r) + '/100)*$L' + str(r)
        + '+($R' + str(r) + '/100)*$O' + str(r) + ')*'
        + 'IF(MAX($K' + str(r) + ',$L' + str(r) + ',$O' + str(r) + ')-MIN($K' + str(r) + ',$L'
        + str(r) + ',$O' + str(r) + ')<22,1.08,0.96))))'
    )


def _f_mode(r: int) -> str:  # V mode
    return '=IF($O' + str(r) + '="","forecast","confirmed")'


def _f_band(r: int) -> str:  # U band - shared by disease + OVERALL rows
    return (
        '=IFS($T' + str(r) + '>=70,"HIGH",$T' + str(r) + '>=45,"MODERATE",$T' + str(r)
        + '>=25,"LOW-MODERATE",TRUE,"LOW")'
    )


def _f_overall_score(r: int) -> str:  # T (OVERALL) - 0.8*top + 0.2*mean-of-rest over the city's disease rows
    sel = ('$T:$T,$B:$B,$B' + str(r) + ',$C:$C,$C' + str(r) + ',$E:$E,"<>OVERALL"')
    mx = 'MAXIFS(' + sel + ')'
    sm = 'SUMIFS(' + sel + ')'
    ct = ('COUNTIFS($B:$B,$B' + str(r) + ',$C:$C,$C' + str(r) + ',$E:$E,"<>OVERALL")')
    return ('=IFERROR(ROUND(0.8*' + mx + '+0.2*(' + sm + '-' + mx + ')/(' + ct + '-1)),ROUND(' + mx + '))')


# --- per-date grid construction (reuses build_daily's signal assembly + city blend) -------------
def build_grid_for_date(
    iso_date: str, weather_by_date: dict, cities: list, diseases: list,
    consol: dict, trends_hist: TrendsHistory, pos_provider, terms: dict, run_id: str,
) -> list:
    """Return the list of raw_data rows (each a 26-value list in HEADER order) for one
    date: 4 disease rows + 1 OVERALL row per city. Fail-loud on any missing weather."""
    day_w = weather_by_date.get(iso_date)
    if day_w is None:
        raise SystemExit(f"ABORT: weather has no by_date entry for {iso_date}.")

    cb = consol.get("city_blend", {"top_weight": 0.8, "rest_weight": 0.2})
    rows: list = []

    for city in cities:
        cid = city["id"]
        wc = day_w.get(cid)
        if wc is None:
            raise SystemExit(f"ABORT: weather missing city '{cid}' on {iso_date}.")
        agg = wc.get("agg") or {}
        fams = wc.get("families") or {}
        for k in ("temp_mean_c", "humidity_pct", "rain_7d_mm", "rain_14d_mm"):
            if agg.get(k) is None:
                raise SystemExit(f"ABORT: weather '{cid}' {iso_date} missing agg.{k}.")
        temp = agg["temp_mean_c"]
        hum = agg["humidity_pct"]
        r7 = agg["rain_7d_mm"]
        r14 = agg["rain_14d_mm"]

        disease_scores: list = []  # (disease_id, score) for the city blend
        for disease in diseases:
            fam = disease["family"]
            weather_val = fams.get(fam)
            if weather_val is None:
                raise SystemExit(f"ABORT: weather '{cid}' {iso_date} missing family '{fam}'.")
            raw = trends_hist.raw_for(disease["id"], city.get("state", ""), iso_date)
            if raw is None:
                raise SystemExit(
                    f"ABORT: no trends week <= {iso_date} for '{disease['id']}' (before history start)."
                )
            trends_floored = floor_trends(raw)
            pos = pos_provider.fetch(city, disease)  # date-independent mock; None -> forecast-only
            sig = {
                "weather": weather_val,
                "trends": trends_floored,
                "positivity": None if pos is None else pos,
                "news_spike": False,  # trends_history carries no spike flag; do not invent one
            }
            res = consolidate(sig, consol)
            bnd = band(res["score"], consol)
            disease_scores.append((disease["id"], res["score"]))

            w = res["weights"]
            kw = ", ".join(terms.get(disease["id"], [])) if terms else ""
            # K weather_score = the family weather sub-score; L trends_score = floored interest.
            rows.append([
                iso_date, run_id, city.get("name", cid), city.get("state", ""),
                disease["label"], fam,
                temp, hum, r7, r14,                              # G-J raw weather
                weather_val, trends_floored,                     # K weather_score, L trends_score (LITERAL)
                kw, "", pos,                                     # M trends_keywords, N news_spike (blank), O positivity
                w.get("weather"), w.get("trends"), w.get("positivity"),  # P-R weights
                res["confidence"], res["score"], bnd["label"], res["mode"],  # S-V (LITERAL)
                raw, "fresh", "fresh", "FALSE",                  # W trends_state_interest, X/Y fresh, Z stale
                WEATHER_SOURCE,                                  # AA weather provenance
            ])

        # OVERALL city-blend row: score = round(0.8*top + 0.2*mean-of-rest), same as build_daily.
        items = sorted(disease_scores, key=lambda x: x[1], reverse=True)
        top_score = items[0][1]
        rest = [s for _, s in items[1:]]
        mean_rest = (sum(rest) / len(rest)) if rest else float(top_score)
        blended = int(round(cb["top_weight"] * top_score + cb["rest_weight"] * mean_rest))
        bnd = band(blended, consol)
        rows.append([
            iso_date, run_id, city.get("name", cid), city.get("state", ""),
            "OVERALL", "city-blend",
            temp, hum, r7, r14,                                  # G-J raw weather
            "", "",                                              # K weather_score, L trends_score blank
            "", "", "",                                          # M-O blank
            "", "", "",                                          # P-R weights blank
            "", blended, bnd["label"], "blend",                  # S blank; T score, U band, V "blend"
            "", "fresh", "fresh", "FALSE",                       # W blank; X/Y fresh, Z stale
            WEATHER_SOURCE,                                      # AA weather provenance
        ])

    return rows


def write_csv(path: str, rows: list) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        wtr = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        wtr.writerow(HEADER)
        wtr.writerows(rows)
    return len(rows)


# Zero-based HEADER positions of the computed columns we overwrite with formulas.
_IDX = {
    "disease": HEADER.index("disease"),            # E
    "weather_score": HEADER.index("weather_score"),  # K
    "trends_score": HEADER.index("trends_score"),    # L
    "confidence": HEADER.index("confidence"),        # S
    "score": HEADER.index("score"),                  # T
    "band": HEADER.index("band"),                    # U
    "mode": HEADER.index("mode"),                    # V
}


def write_xlsx(path: str, rows: list) -> int:
    """Stream the rows to an .xlsx in openpyxl WRITE-ONLY mode (low memory, fast for
    the 173K-row file). The raw-input cells (A-J, M-R, W-Z) carry the same VALUES as
    the CSV; K/L/S/T/U/V are overwritten with the live `_setRawFormulas` formula
    strings, with the actual sheet row number baked in. Data starts at sheet row 2
    (row 1 is the header), so a row at list index i lives at sheet row r = i + 2."""
    from openpyxl import Workbook  # lazy: keeps the CSV / stdlib path dependency-free

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="raw_data")
    ws.append(HEADER)  # row 1

    i_dis = _IDX["disease"]
    i_k, i_l, i_s = _IDX["weather_score"], _IDX["trends_score"], _IDX["confidence"]
    i_t, i_u, i_v = _IDX["score"], _IDX["band"], _IDX["mode"]

    for i, src in enumerate(rows):
        r = i + 2  # 1-based sheet row of this data row
        row = list(src)  # copy: raw inputs stay as literal values
        is_overall = row[i_dis] == "OVERALL"
        if is_overall:
            row[i_k] = '=""'
            row[i_l] = '=""'
            row[i_s] = '=""'
            row[i_t] = _f_overall_score(r)
            row[i_v] = '="blend"'
        else:
            row[i_k] = _f_weather(r)
            row[i_l] = _f_trends(r)
            row[i_s] = _f_confidence(r)
            row[i_t] = _f_score(r)
            row[i_v] = _f_mode(r)
        row[i_u] = _f_band(r)  # band is a formula for both row kinds
        ws.append(row)

    wb.save(path)
    return len(rows)


def run_year(label: str, weather_path: str, start: date, end: date,
             cities, diseases, consol, trends_hist, pos_provider, terms,
             out_base: str, fmt: str) -> dict:
    """Build every row for [start, end] once, then write the requested format(s).
    `out_base` is the path WITHOUT extension; `.xlsx` / `.csv` is appended."""
    if not os.path.exists(weather_path):
        raise SystemExit(f"ABORT: {weather_path} not found.")
    wdata = load_json(weather_path)
    weather_by_date = wdata.get("by_date") or {}
    rows: list = []
    dates = list(daterange(start, end))
    for d in dates:
        iso = d.isoformat()
        run_id = "bf-" + d.strftime("%Y%m%d")  # UNIQUE per date so nothing aggregates across days
        rows.extend(build_grid_for_date(
            iso, weather_by_date, cities, diseases, consol, trends_hist, pos_provider, terms, run_id))

    written = []
    if fmt in ("xlsx", "both"):
        import time
        path = out_base + ".xlsx"
        t0 = time.perf_counter()
        n = write_xlsx(path, rows)
        dt = time.perf_counter() - t0
        size = os.path.getsize(path)
        print(f"[{label}] {len(dates)} dates ({start} .. {end}) -> {n} rows -> {path} "
              f"({size:,} bytes, {dt:.1f}s)")
        written.append({"path": path, "rows": n, "bytes": size, "seconds": dt})
    if fmt in ("csv", "both"):
        path = out_base + ".csv"
        n = write_csv(path, rows)
        size = os.path.getsize(path)
        print(f"[{label}] {len(dates)} dates ({start} .. {end}) -> {n} rows -> {path} ({size:,} bytes)")
        written.append({"path": path, "rows": n, "bytes": size})

    return {"rows": len(rows), "dates": len(dates), "written": written}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    # --format xlsx (default) | csv | both. xlsx bakes the live formulas; csv keeps literals.
    fmt = "xlsx"
    argv = sys.argv[1:]
    if "--format" in argv:
        i = argv.index("--format")
        if i + 1 >= len(argv) or argv[i + 1] not in ("xlsx", "csv", "both"):
            raise SystemExit("usage: backfill_sheetlog.py [--format xlsx|csv|both]")
        fmt = argv[i + 1]

    cities = load_json(os.path.join(ROOT, "config", "cities.json"))["cities"]
    diseases = load_json(os.path.join(ROOT, "config", "diseases.json"))["diseases"]
    consol = load_json(os.path.join(ROOT, "config", "consolidation.json"))
    signals_cfg = load_json(os.path.join(ROOT, "config", "signals.json"))
    terms = (((signals_cfg.get("trends") or {}).get("serpapi") or {}).get("terms")) or {}

    trends_hist = TrendsHistory(os.path.join(BACKFILL_DIR, "trends_history.json"))
    pos_provider = MockPositivityProvider()

    print(f"Engine: {consol.get('model_version')}  |  cities={len(cities)}  "
          f"diseases={len(diseases)}  |  format={fmt}")
    print("-" * 80)

    run_year(
        "2026", os.path.join(BACKFILL_DIR, "weather_2026.json"),
        date(2026, 6, 1), date(2026, 6, 14),
        cities, diseases, consol, trends_hist, pos_provider, terms,
        os.path.join(OUT_DIR, "raw_data_2026_backfill"), fmt)

    run_year(
        "2025", os.path.join(BACKFILL_DIR, "weather_2025.json"),
        date(2025, 6, 1), date(2025, 10, 30),
        cities, diseases, consol, trends_hist, pos_provider, terms,
        os.path.join(OUT_DIR, "raw_data_2025"), fmt)

    print("-" * 80)
    print(f"Done. Outputs ({fmt}) written under", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
