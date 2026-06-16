"""Fever Watch daily grid builder (composes the 3 signals into the score grid).

Reads data/weather.json (signal 1, live from NASA POWER) plus the trends and
positivity providers (signals 2 + 3; MOCK by default), runs the confirmation-
weighted consolidation engine for every city x disease, and writes data/grid.json
for the static front end. Fail-loud guard: aborts and writes nothing if the
weather input is missing or too many cells fail.

Usage (from the project root):
    python src/build_weather.py        # produce data/weather.json first
    python src/build_daily.py          # then compose the grid

    python src/build_daily.py --trends mock --positivity mock
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, date, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import signals  # noqa: E402
from consolidate import band, consolidate  # noqa: E402
from iohelpers import write_json_atomic  # noqa: E402

ROOT = os.path.dirname(SRC_DIR)
DISCLAIMER = (
    "Fever Watch is a risk indicator that blends breeding weather, search interest "
    "and lab positivity into one decomposable score per city and disease. It is not "
    "a diagnosis, a count of actual cases or mosquitoes, or medical advice. "
    "Forecast-only locations are capped and cannot show HIGH."
)
_BAND_CODE = {"HIGH": "H", "MODERATE": "M", "LOW-MODERATE": "l", "LOW": "o"}
# A stale signal downgrades the cell's confidence one step (Forecast-only is left as is).
_CONF_DOWNGRADE = {"High": "Moderate", "Moderate": "Low", "Forecast only": "Forecast only"}


def _age_days(iso, now_dt):
    """Whole days between an ISO timestamp and now (UTC); None if missing/unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return max(0, (now_dt - dt).days)
    except Exception:
        return None


def _fresh_tag(age, stale_days):
    """fresh (today) | carried Nd (1..stale_days) | stale Nd (> budget) | unknown."""
    if age is None:
        return "unknown"
    if age <= 0:
        return "fresh"
    return ("carried %dd" % age) if age <= stale_days else ("stale %dd" % age)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --- rolling score history (real "up from N last week" source for the share card) ----------------
# The daily commits ARE the history; we keep a small rolling data/history.json so the share card can
# show a REAL week-over-week delta. prev_score is None until a >=4d-old day exists, so the card simply
# omits "up from last week" until there is real history (never a fabricated number).
HISTORY_PATH = os.path.join(ROOT, "data", "history.json")
HISTORY_KEEP_DAYS = 35
_PREV_LO, _PREV_HI, _PREV_TARGET = 4, 10, 7  # "last week" = the nearest committed day 4..10 days back


def _prev_week_scores(history: dict, today: date) -> dict:
    """Per-city blend score from ~7 days ago (nearest committed day in [4,10] days back), or {}."""
    best: dict = {}  # city_id -> (abs_diff_from_target, score)
    for entry in (history.get("days") or []):
        try:
            age = (today - date.fromisoformat(entry.get("date") or "")).days
        except Exception:
            continue
        if age < _PREV_LO or age > _PREV_HI:
            continue
        diff = abs(age - _PREV_TARGET)
        for cid, sc in (entry.get("scores") or {}).items():
            cur = best.get(cid)
            if cur is None or diff < cur[0]:
                best[cid] = (diff, sc)
    return {cid: v[1] for cid, v in best.items()}


def _yesterday_maps(history: dict, today: date):
    """The committed day exactly one day back, as (blend_scores, per_disease_cells, per_signal_sigs).
    Empty until a yesterday entry exists; the per-disease cells and per-signal sigs need the expanded
    schema, so each light up only once a full day has been written under it.
    sigs[city][disease] = [weather, trends, positivity] (the three signal values, null where absent)."""
    target = (today - timedelta(days=1)).isoformat()
    for entry in (history.get("days") or []):
        if entry.get("date") == target:
            return (entry.get("scores") or {}), (entry.get("cells") or {}), (entry.get("sigs") or {})
    return {}, {}, {}


def _stagnation(weather: dict):
    """Estimated standing-water index from the lagged rain (rain that fell 8-14 days ago and is now
    sitting), the 1-2 week breeding lag the methodology already designs around. NOT a measurement -
    a heuristic three-band index, labelled as estimated in the UI. None when rain inputs are missing.
    Only the level is exposed (the raw mm is intentionally not surfaced, to avoid implying precision)."""
    r7, r14 = weather.get("rain_7d_mm"), weather.get("rain_14d_mm")
    if r7 is None or r14 is None:
        return None
    standing = max(0.0, r14 - r7)
    level = "High" if standing >= 22 else ("Moderate" if standing >= 9 else "Low")
    return {"level": level}


def normalize_signal(value, city, disease):
    """Per-city z-score normalization hook (kills big-city bias).

    Real implementation needs historical per-city baselines, which accrue once
    the daily grid.json snapshots pile up in Git. Until then this is the identity
    so the pipeline is wired end to end and the swap is a one-function change.
    """
    return value


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Fever Watch grid.json from the 3 signals")
    p.add_argument("--config-dir", default=os.path.join(ROOT, "config"))
    p.add_argument("--weather", default=os.path.join(ROOT, "data", "weather.json"))
    p.add_argument("--out", default=os.path.join(ROOT, "data", "grid.json"))
    p.add_argument("--trends", default=None, help="Override trends provider (mock|cached); default from config/signals.json")
    p.add_argument("--positivity", default=None, help="Override positivity provider (mock|googlesheet); default from config/signals.json")
    p.add_argument("--signals-config", default=os.path.join(ROOT, "config", "signals.json"))
    p.add_argument("--max-fail-fraction", type=float, default=0.5)
    return p.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_args()
    cities = load_json(os.path.join(args.config_dir, "cities.json"))["cities"]
    diseases = load_json(os.path.join(args.config_dir, "diseases.json"))["diseases"]
    consol = load_json(os.path.join(args.config_dir, "consolidation.json"))
    # Native-script city/state names for the share image (Wikidata pull -> PharmEasy QA fills this;
    # merged into grid.json only when present, English fallback otherwise).
    names_local_path = os.path.join(args.config_dir, "city_names_local.json")
    local_names = load_json(names_local_path) if os.path.exists(names_local_path) else {}

    if not os.path.exists(args.weather):
        print(f"ABORT: {args.weather} not found. Run build_weather.py first.", file=sys.stderr)
        return 1
    weather = load_json(args.weather)
    weather_by_city = {c["id"]: c for c in weather.get("cities", [])}

    # Freshness budget: a signal older than stale_days flags the cell + downgrades its confidence.
    # Weather has one timestamp for the whole pull; trends freshness is per-disease (build_trends as_of).
    now_dt = datetime.now(timezone.utc)
    today = now_dt.date()
    history = load_json(HISTORY_PATH) if os.path.exists(HISTORY_PATH) else {"days": []}
    prev_by_city = _prev_week_scores(history, today)
    y_blend, y_cells, y_sigs = _yesterday_maps(history, today)  # day-over-day "vs yesterday" source
    stale_days = int((consol.get("freshness") or {}).get("stale_days", 3))
    weather_age = _age_days(weather.get("generated_at"), now_dt)
    weather_fresh = _fresh_tag(weather_age, stale_days)

    sig_cfg = load_json(args.signals_config) if os.path.exists(args.signals_config) else {}
    trends_cfg = sig_cfg.get("trends", {})
    pos_cfg = sig_cfg.get("positivity", {})
    trends_name = args.trends or os.environ.get("TRENDS_PROVIDER") or trends_cfg.get("provider", "mock")
    pos_name = args.positivity or os.environ.get("POSITIVITY_PROVIDER") or pos_cfg.get("provider", "mock")

    # 'cached' trends needs the weekly data/trends.json; fall back to mock if it
    # is not there yet so the daily build never hard-fails on a missing weekly run.
    if trends_name == "cached":
        cached_path = (trends_cfg.get("cached") or {}).get("path", os.path.join("data", "trends.json"))
        if not os.path.isabs(cached_path):
            cached_path = os.path.join(ROOT, cached_path)
        if not os.path.exists(cached_path):
            print(f"WARN: trends provider 'cached' but {cached_path} missing; using mock.", file=sys.stderr)
            trends_name = "mock"
        else:
            trends_cfg = {**trends_cfg, "cached": {"path": cached_path}}

    trends_p = signals.get_trends_provider(trends_name, trends_cfg)
    positivity_p = signals.get_positivity_provider(pos_name, pos_cfg)

    print(
        f"Engine: {consol.get('model_version')}  |  trends={trends_p.name}  "
        f"positivity={positivity_p.name}  |  weather from {weather.get('provider')}"
    )
    print("-" * 88)

    # Sidecar for the score-derivation logger (src/sheetlog.py): the RAW labs inputs
    # (tests + positives) behind each positivity signal. GITIGNORED on purpose - raw lab
    # counts are proprietary and must never enter the public grid.json; only the derived
    # 0-100 signal is public. The logging Google Sheet (internal) shows the full build-up.
    _pos_detail = getattr(positivity_p, "detail_map", None)
    if _pos_detail:
        try:
            with open(os.path.join(ROOT, "data", "positivity_detail.json"), "w", encoding="utf-8") as _f:
                json.dump({"%s|%s" % (k[0], k[1]): {"tests": v["tests"], "positives": v["positives"], "pct": v["pct"]}
                           for k, v in _pos_detail.items()}, _f)
        except Exception as _e:
            print("WARN: could not write positivity_detail sidecar: %s" % _e, file=sys.stderr)

    rows: list[dict] = []
    failures: list[dict] = []

    for city in cities:
        wc = weather_by_city.get(city["id"])
        if not wc:
            failures.append({"city": city["id"], "reason": "no weather row"})
            continue
        fam_scores = wc.get("families", {})
        for disease in diseases:
            fam = disease["family"]
            weather_val = fam_scores.get(fam)
            if weather_val is None:
                failures.append({"city": city["id"], "disease": disease["id"], "reason": f"no '{fam}' family score"})
                continue
            tr = trends_p.fetch(city, disease)
            pos = positivity_p.fetch(city, disease)
            sig = {
                "weather": normalize_signal(weather_val, city, disease),
                "trends": normalize_signal(tr["value"], city, disease),
                "positivity": None if pos is None else normalize_signal(pos, city, disease),
                "news_spike": tr["news_spike"],
            }
            res = consolidate(sig, consol)
            bnd = band(res["score"], consol)
            # Freshness / carry-forward provenance. The cached/committed files already supply last-good
            # values (Phase 1); here we tag how old each signal is and downgrade confidence when stale.
            tr_age = _age_days(tr.get("as_of"), now_dt)
            pos_fresh = "mock" if positivity_p.name == "mock" else "fresh"  # real lab-feed date hook (future)
            freshness = {"weather": weather_fresh, "trends": _fresh_tag(tr_age, stale_days), "positivity": pos_fresh}
            cell_stale = (weather_age is not None and weather_age > stale_days) or (tr_age is not None and tr_age > stale_days)
            confidence, note = res["confidence"], res["note"]
            if cell_stale:
                confidence = _CONF_DOWNGRADE.get(confidence, confidence)
                oldest = max([a for a in (weather_age, tr_age) if a is not None] or [0])
                note += " Using the most recent available reading (%dd old)." % oldest
            rows.append({
                "city": city["id"],
                "disease": disease["id"],
                "family": fam,
                "score": res["score"],
                "band": bnd["label"],
                "color": bnd["color"],
                "soft": bnd["soft"],
                "emoji": bnd["emoji"],
                "confidence": confidence,
                "mode": res["mode"],
                "note": note,
                "weights": res["weights"],
                "freshness": freshness,
                "stale": cell_stale,
                "signals": {
                    "weather": weather_val,
                    "trends": tr["value"],
                    "trends_raw": tr.get("raw"),
                    "trends_as_of": tr.get("as_of"),
                    "positivity": pos,
                    "news_spike": tr["news_spike"],
                },
            })

    # Day-over-day deltas vs yesterday's committed cell. None (key omitted) until a yesterday entry
    # under the expanded schema exists; the front end shows an arrow only for a present, non-zero delta.
    # PER-SIGNAL delta (sig_delta) powers the breakdown trend badges (red up = rising, green down =
    # falling). Needs a yesterday entry that carries 'sigs', so it lights up one day after this ships.
    _SIG_KEYS = ("weather", "trends", "positivity")
    for r in rows:
        py = (y_cells.get(r["city"]) or {}).get(r["disease"])
        if py is not None:
            r["delta_1d"] = r["score"] - py
        ys = (y_sigs.get(r["city"]) or {}).get(r["disease"])  # [weather, trends, positivity] or None
        if ys:
            sd = {}
            for i, k in enumerate(_SIG_KEYS):
                cur = r["signals"].get(k)
                prev = ys[i] if i < len(ys) else None
                if cur is not None and prev is not None:
                    sd[k] = cur - prev
            if sd:
                r["sig_delta"] = sd

    print_matrix(cities, diseases, rows)

    # --- data-quality guard -------------------------------------------------
    expected = len(cities) * len(diseases)
    fail_fraction = len(failures) / expected if expected else 1.0
    print("-" * 88)
    if not rows:
        print("ABORT: no grid cells produced. Writing nothing.", file=sys.stderr)
        return 1
    if fail_fraction > args.max_fail_fraction:
        print(
            f"ABORT: {len(failures)}/{expected} cells failed "
            f"({fail_fraction:.0%} > {args.max_fail_fraction:.0%}). Writing nothing.",
            file=sys.stderr,
        )
        return 1

    # City-level blended headline score: a max-dominant blend (top_weight x the
    # highest disease + rest_weight x the mean of the rest), with the driver
    # disease named. Kept max-dominant so a single HIGH disease keeps the city
    # near HIGH; never hides a HIGH disease behind a calm average.
    cb = consol.get("city_blend", {"top_weight": 0.8, "rest_weight": 0.2})
    scores_by_city: dict = {}
    for r in rows:
        scores_by_city.setdefault(r["city"], []).append((r["disease"], r["score"]))

    def city_blend(city_id: str):
        items = sorted(scores_by_city.get(city_id, []), key=lambda x: x[1], reverse=True)
        if not items:
            return None
        top_disease, top_score = items[0]
        rest = [s for _, s in items[1:]]
        mean_rest = (sum(rest) / len(rest)) if rest else float(top_score)
        blended = int(round(cb["top_weight"] * top_score + cb["rest_weight"] * mean_rest))
        bnd = band(blended, consol)
        return {
            "score": blended, "band": bnd["label"], "color": bnd["color"],
            "soft": bnd["soft"], "emoji": bnd["emoji"],
            "driver": top_disease, "driver_score": top_score,
        }

    # Carry each city's raw weather readout (the "live weather" trust line) plus
    # the blended headline so the front end has a single data source.
    enriched_cities = []
    for c in cities:
        wsum = (weather_by_city.get(c["id"], {}) or {}).get("weather", {})
        b = city_blend(c["id"])
        if b is not None:
            if c["id"] in prev_by_city:
                b["prev_score"] = prev_by_city[c["id"]]  # real blend score ~7 days ago (share-card "up from N last week")
            yb = y_blend.get(c["id"])
            if yb is not None:
                b["delta_1d"] = b["score"] - yb  # vs yesterday (headline trend arrow)
        ec = {**c, "weather": {
            "temp_mean_c": wsum.get("temp_mean_c"),
            "humidity_pct": wsum.get("humidity_pct"),
            "rain_7d_mm": wsum.get("rain_7d_mm"),
            "rain_14d_mm": wsum.get("rain_14d_mm"),
            "stagnation": _stagnation(wsum),
        }, "blend": b}
        nl = (local_names.get("cities") or {}).get(c["id"])
        sl = (local_names.get("states") or {}).get(c.get("state", ""))
        if nl:
            ec["name_local"] = nl
        if sl:
            ec["state_local"] = sl
        enriched_cities.append(ec)

    # Roll today's scores into the rolling history. Per-city blend scores feed the "last week" delta;
    # per-disease cells are stored too, so tomorrow's build has a real per-disease yesterday for the
    # day-over-day arrows. (The past-7-days strip recomputes its trail from this history when its UI
    # lands; we do not pre-bake a trail array into grid.json, to keep every page lean.)
    today_iso = today.isoformat()
    today_scores = {c["id"]: c["blend"]["score"] for c in enriched_cities if c.get("blend")}
    today_cells: dict = {}
    today_sigs: dict = {}  # sigs[city][disease] = [weather, trends, positivity] - feeds tomorrow's per-signal deltas
    for r in rows:
        today_cells.setdefault(r["city"], {})[r["disease"]] = r["score"]
        s = r["signals"]
        today_sigs.setdefault(r["city"], {})[r["disease"]] = [s.get("weather"), s.get("trends"), s.get("positivity")]
    hist_days = [d for d in (history.get("days") or []) if d.get("date") != today_iso]
    hist_days.append({"date": today_iso, "scores": today_scores, "cells": today_cells, "sigs": today_sigs})
    hist_days.sort(key=lambda d: d.get("date", ""))
    hist_days = hist_days[-HISTORY_KEEP_DAYS:]

    # Which period tabs the front end may show: "today" always; "week"/"month" only once enough
    # committed days exist to make that granularity honest (the UI hides tabs not listed here).
    ndays = len(hist_days)
    periods = ["today"] + (["week"] if ndays >= 7 else []) + (["month"] if ndays >= 28 else [])

    payload = {
        "engine_version": consol.get("model_version", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "weather": {
            "generated_at": weather.get("generated_at"),
            "provider": weather.get("provider"),
            "attribution": weather.get("attribution"),
            "model_version": weather.get("model_version"),
        },
        "trends_provider": trends_p.name,
        "positivity_provider": positivity_p.name,
        "periods": periods,
        "cities": enriched_cities,
        "diseases": diseases,
        "bands": consol.get("bands", []),
        "cell_count": len(rows),
        "failed_count": len(failures),
        "stale_days": stale_days,
        "stale_count": sum(1 for r in rows if r.get("stale")),
        "failures": failures,
        "grid": rows,
    }

    write_json_atomic(args.out, payload)  # atomic: a crash never corrupts the last-good grid.json

    # Persist the rolling history (built above). Carries per-city blend scores (the "last week" source)
    # plus per-disease cells (tomorrow's per-disease "vs yesterday" source).
    write_json_atomic(HISTORY_PATH, {"updated": payload["generated_at"], "days": hist_days})

    if failures:
        print(f"Note: {len(failures)} cell(s) failed but stayed under the abort threshold.")
    print(f"\nWrote {args.out}  ({len(rows)} cells = {len(cities)} cities x {len(diseases)} diseases)")
    return 0


def print_matrix(cities: list[dict], diseases: list[dict], rows: list[dict]) -> None:
    by_key = {(r["city"], r["disease"]): r for r in rows}
    header = f"{'City':<11}" + "".join(f"{d['label'][:9]:>11}" for d in diseases)
    print(header)
    for city in cities:
        cells = []
        for disease in diseases:
            r = by_key.get((city["id"], disease["id"]))
            if r is None:
                cells.append(f"{'-':>11}")
                continue
            code = _BAND_CODE.get(r["band"], "?")
            star = "*" if r["mode"] == "confirmed" else "~"
            cells.append(f"{r['score']:>6}{code}{star:<1}{'':>3}".rstrip().rjust(11))
        print(f"{city['name']:<11}" + "".join(cells))
    print("  legend: score + band (H/M/l/o) + mode (* confirmed, ~ forecast-only capped)")


if __name__ == "__main__":
    raise SystemExit(main())
