"""Fever Watch weather builder (signal 1 of 3).

Fetch trailing daily weather per city from the default provider (NASA POWER,
public domain), aggregate it, and compute a 0-100 environmental-favourability
sub-score for each disease *family* (mosquito / waterborne / febrile). Writes
data/weather.json, which the daily grid builder later feeds into the
consolidation engine as the 'weather' signal.

Usage (from the project root):
    python src/build_weather.py                       # NASA POWER (default)
    python src/build_weather.py --provider open-meteo
    WEATHER_PROVIDER=open-meteo python src/build_weather.py

Fail-loud guard: aborts and writes nothing if no city scores, or if more than
sanity.max_fail_fraction of cities fail. A branded product must never silently
publish garbage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import providers  # noqa: E402
from iohelpers import write_json_atomic  # noqa: E402
from weather_score import aggregate, score_family  # noqa: E402

ROOT = os.path.dirname(SRC_DIR)
DISCLAIMER = (
    "Weather-driven environmental favourability sub-scores per disease family, "
    "for city-level screening and comparison. One input to the Fever Watch risk "
    "indicator, not a disease forecast, a case count, or an individual health estimate."
)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Fever Watch weather.json (signal 1)")
    p.add_argument(
        "--provider",
        default=os.environ.get("WEATHER_PROVIDER", providers.DEFAULT_PROVIDER),
        help=f"Weather provider, one of: {', '.join(providers.available())} (default: %(default)s)",
    )
    p.add_argument("--config-dir", default=os.path.join(ROOT, "config"))
    p.add_argument("--out", default=os.path.join(ROOT, "data", "weather.json"))
    p.add_argument("--past-days", type=int, default=18, help="Days of history to request per city")
    p.add_argument("--sleep", type=float, default=0.25, help="Polite delay between city requests (s)")
    return p.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_args()
    cities = load_json(os.path.join(args.config_dir, "cities.json"))["cities"]
    diseases = load_json(os.path.join(args.config_dir, "diseases.json"))["diseases"]
    scoring = load_json(os.path.join(args.config_dir, "scoring.json"))
    families_cfg = scoring["families"]
    san = scoring["sanity"]

    used_families = sorted({d["family"] for d in diseases})
    provider = providers.get_provider(args.provider)

    print(f"Provider: {provider.name}  |  Cities: {len(cities)}  |  Families: {', '.join(used_families)}")
    print("-" * 86)

    scored: list[dict] = []
    failures: list[dict] = []
    warnings: list[str] = []

    for i, city in enumerate(cities, 1):
        label = f"{city['name']}, {city['state']}"
        try:
            records = provider.fetch_daily(city["lat"], city["lon"], past_days=args.past_days)
            agg = aggregate(records)
            if not agg["has_temp"] and not agg["has_precip"]:
                failures.append({"city": label, "reason": "no usable weather records"})
                print(f"[{i:>2}/{len(cities)}] SKIP  {label:<32} (no usable records)")
                continue
            t = agg["temp_mean_c"]
            if t is not None and not (san["plausible_temp_min_c"] <= t <= san["plausible_temp_max_c"]):
                warnings.append(f"{label}: implausible mean temp {t}C")
            fam_scores: dict = {}
            fam_components: dict = {}
            for fam in used_families:
                s, comp = score_family(fam, agg, families_cfg)
                fam_scores[fam] = s
                fam_components[fam] = comp
            scored.append({**city, "weather": agg, "families": fam_scores, "components": fam_components})
            print(
                f"[{i:>2}/{len(cities)}] OK    {label:<32} "
                f"T={t}C RH={agg['humidity_pct']}% R14={agg['rain_14d_mm']}mm  "
                f"mos={fam_scores.get('mosquito','-')} "
                f"wat={fam_scores.get('waterborne','-')} "
                f"feb={fam_scores.get('febrile','-')}"
            )
        except Exception as err:  # network / parse hard failure
            failures.append({"city": label, "reason": str(err)})
            print(f"[{i:>2}/{len(cities)}] FAIL  {label:<32} ({err})")
        if args.sleep:
            time.sleep(args.sleep)

    total = len(cities)
    fail_fraction = len(failures) / total if total else 1.0
    print("-" * 86)
    if not scored:
        print("ABORT: no cities scored. Writing nothing.", file=sys.stderr)
        return 1
    if fail_fraction > san["max_fail_fraction"]:
        print(
            f"ABORT: {len(failures)}/{total} cities failed ({fail_fraction:.0%} > "
            f"{san['max_fail_fraction']:.0%} threshold). Writing nothing.",
            file=sys.stderr,
        )
        for f in failures:
            print(f"   - {f['city']}: {f['reason']}", file=sys.stderr)
        return 1

    payload = {
        "signal": "weather",
        "model_version": scoring.get("model_version", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "attribution": provider.attribution,
        "disclaimer": DISCLAIMER,
        "families": used_families,
        "scoring_config": scoring,
        "city_count": len(scored),
        "failed_count": len(failures),
        "failures": failures,
        "cities": scored,
    }

    write_json_atomic(args.out, payload)  # atomic: a crash never corrupts the last-good weather.json

    for w in warnings:
        print(f"WARN: {w}")
    if failures:
        print(f"Note: {len(failures)} city(ies) failed but stayed under the abort threshold.")
    print(f"\nWrote {args.out}  ({len(scored)} cities, provider={provider.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
