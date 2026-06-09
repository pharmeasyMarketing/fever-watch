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
from datetime import datetime, timezone

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

    if not os.path.exists(args.weather):
        print(f"ABORT: {args.weather} not found. Run build_weather.py first.", file=sys.stderr)
        return 1
    weather = load_json(args.weather)
    weather_by_city = {c["id"]: c for c in weather.get("cities", [])}

    # Freshness budget: a signal older than stale_days flags the cell + downgrades its confidence.
    # Weather has one timestamp for the whole pull; trends freshness is per-disease (build_trends as_of).
    now_dt = datetime.now(timezone.utc)
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
        enriched_cities.append({**c, "weather": {
            "temp_mean_c": wsum.get("temp_mean_c"),
            "humidity_pct": wsum.get("humidity_pct"),
            "rain_7d_mm": wsum.get("rain_7d_mm"),
            "rain_14d_mm": wsum.get("rain_14d_mm"),
        }, "blend": city_blend(c["id"])})

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
