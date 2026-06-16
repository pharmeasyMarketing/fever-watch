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

    # Historical backfill (NASA POWER only): recompute per-date weather sub-scores
    # for past dates into the committed, per-year, minified archive store under
    # data/backfill/. The live daily path above is UNCHANGED when no backfill
    # flags are given.
    python src/build_weather.py --start 2025-06-01 --end 2025-10-30
    python src/build_weather.py --as-of 2025-09-15

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
from datetime import date, datetime, timedelta, timezone
from statistics import mean

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import providers  # noqa: E402
from iohelpers import load_json_or, write_json_atomic  # noqa: E402
from weather_score import aggregate, score_family, window_for_date  # noqa: E402

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
    # Historical backfill (NASA POWER only). With NO backfill flag the existing
    # daily path runs verbatim. --start/--end give a range; --as-of a single
    # date. They are mutually exclusive (a range OR one date). Each has an env
    # fallback so the archive runner can drive this without flags.
    p.add_argument("--start", default=os.environ.get("WEATHER_START"),
                   help="Backfill range start, YYYY-MM-DD (use with --end)")
    p.add_argument("--end", default=os.environ.get("WEATHER_END"),
                   help="Backfill range end, YYYY-MM-DD (use with --start)")
    p.add_argument("--as-of", dest="as_of", default=os.environ.get("WEATHER_AS_OF"),
                   help="Backfill a single date, YYYY-MM-DD (mutually exclusive with --start/--end)")
    p.add_argument("--out-archive", default=os.path.join(ROOT, "data", "backfill"),
                   help="Directory for the per-year minified backfill store (default: %(default)s)")
    return p.parse_args()


def _parse_iso(value: str, flag: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise SystemExit(f"ABORT: {flag} must be an ISO date YYYY-MM-DD, got {value!r}.")


def resolve_targets(args) -> list[date] | None:
    """Return the sorted list of target dates for a backfill, or None for the
    normal daily path. Validates the mutually-exclusive --start/--end vs --as-of
    contract and aborts loudly on a bad combination."""
    has_range = bool(args.start or args.end)
    has_as_of = bool(args.as_of)
    if not has_range and not has_as_of:
        return None
    if has_as_of and has_range:
        raise SystemExit("ABORT: --as-of is mutually exclusive with --start/--end.")
    if has_range and not (args.start and args.end):
        raise SystemExit("ABORT: --start and --end must be given together.")

    if has_as_of:
        d = _parse_iso(args.as_of, "--as-of")
        return [d]
    start = _parse_iso(args.start, "--start")
    end = _parse_iso(args.end, "--end")
    if end < start:
        raise SystemExit(f"ABORT: --end ({end}) is before --start ({start}).")
    span = (end - start).days
    return [start + timedelta(days=i) for i in range(span + 1)]


# Lead-in pad for the per-city range fetch: a 14-day trailing window plus NASA
# POWER's ~6-day latency, so the EARLIEST target's 14-day window is fully
# covered even with interior gaps. Free: it is the same single per-city call.
BACKFILL_LEAD_IN_DAYS = 20


def windowed_agg(records, as_of):
    """Build an aggregate-shaped dict for one target date from EXPLICIT
    date-bounded trailing windows (FIX A).

    rain_7d_mm / rain_14d_mm are summed over window_for_date(..., 7|14) anchored
    on `as_of`, NOT aggregate()'s precs[-n:] ('last n AVAILABLE days'), which is
    wrong across interior gaps. temp_mean_c / humidity_pct are meaned over the
    14-day window. Returns None when the 14-day window has no usable obs at all
    (expected for the most-recent latency-gapped dates) so the caller can treat
    it as a non-fatal per-date skip rather than a city failure.
    """
    win14 = window_for_date(records, as_of, 14)
    win7 = window_for_date(records, as_of, 7)

    temps = [r.temp_mean_c for r in win14 if r.temp_mean_c is not None]
    hums = [r.humidity_pct for r in win14 if r.humidity_pct is not None]
    precs14 = [r.precip_mm for r in win14 if r.precip_mm is not None]
    precs7 = [r.precip_mm for r in win7 if r.precip_mm is not None]

    if not temps and not precs14:
        return None  # no usable observation in the trailing window for this date

    return {
        "n_days": len(win14),
        "temp_mean_c": round(mean(temps), 1) if temps else None,
        "humidity_pct": round(mean(hums), 1) if hums else None,
        "rain_7d_mm": round(sum(precs7), 1),
        "rain_14d_mm": round(sum(precs14), 1),
        # temp_swing only feeds the retired febrile family; not used by the
        # mosquito/waterborne scorers, kept at 0.0 so score_family stays happy.
        "temp_swing_c": 0.0,
        "has_temp": bool(temps),
        "has_precip": bool(precs14),
    }


def run_backfill(args, targets: list[date]) -> int:
    """Recompute weather sub-scores for each target date per city and merge them
    into the committed, per-year, minified backfill store under --out-archive.

    The live daily path is untouched; this only runs when a backfill flag is set.
    """
    cities = load_json(os.path.join(args.config_dir, "cities.json"))["cities"]
    diseases = load_json(os.path.join(args.config_dir, "diseases.json"))["diseases"]
    scoring = load_json(os.path.join(args.config_dir, "scoring.json"))
    families_cfg = scoring["families"]
    san = scoring["sanity"]

    used_families = sorted({d["family"] for d in diseases})
    provider = providers.get_provider(args.provider)

    # Backfill needs real daily history. NASA POWER and the CPC hybrid both
    # implement fetch_range; open-meteo intentionally inherits the base raise.
    if type(provider).fetch_range is providers.WeatherProvider.fetch_range:
        raise SystemExit(
            f"ABORT: historical backfill requires a provider that implements "
            f"fetch_range (nasa-power or cpc), got '{provider.name}'. "
            f"Re-run with --provider cpc or --provider nasa-power."
        )

    earliest_target = targets[0]
    latest_target = targets[-1]
    fetch_start = earliest_target - timedelta(days=BACKFILL_LEAD_IN_DAYS)  # FIX C
    fetch_end = latest_target

    print(
        f"Backfill | Provider: {provider.name} | Cities: {len(cities)} | "
        f"Families: {', '.join(used_families)}"
    )
    print(
        f"Targets: {earliest_target.isoformat()} .. {latest_target.isoformat()} "
        f"({len(targets)} dates) | fetch {fetch_start.isoformat()} .. "
        f"{fetch_end.isoformat()} (incl. {BACKFILL_LEAD_IN_DAYS}-day lead-in)"
    )
    print("-" * 86)

    target_isos = [d.isoformat() for d in targets]
    # by_date[year][iso][cityId] = record. Two-axis fail-loud (FIX D): only a
    # CITY-FETCH failure counts toward the abort fraction; a per-date "no usable
    # obs" is a non-fatal skip excluded from the denominator.
    by_year_date: dict[int, dict[str, dict]] = {}
    city_failures: list[dict] = []
    skipped_dates = 0  # per-date "no usable obs" skips across all cities
    warnings: list[str] = []

    for i, city in enumerate(cities, 1):
        label = f"{city['name']}, {city['state']}"
        cid = city["id"]
        try:
            records = provider.fetch_range(city["lat"], city["lon"], fetch_start, fetch_end)
        except Exception as err:  # network / parse hard failure for this city
            city_failures.append({"city": label, "reason": str(err)})
            print(f"[{i:>3}/{len(cities)}] FAIL  {label:<32} ({err})")
            if args.sleep:
                time.sleep(args.sleep)
            continue

        emitted = 0
        for d, iso in zip(targets, target_isos):
            agg = windowed_agg(records, d)
            if agg is None:
                skipped_dates += 1
                continue
            t = agg["temp_mean_c"]
            if t is not None and not (san["plausible_temp_min_c"] <= t <= san["plausible_temp_max_c"]):
                warnings.append(f"{label} {iso}: implausible mean temp {t}C")
            fam_scores = {fam: score_family(fam, agg, families_cfg)[0] for fam in used_families}
            rec = {
                "agg": {
                    "temp_mean_c": agg["temp_mean_c"],
                    "humidity_pct": agg["humidity_pct"],
                    "rain_7d_mm": agg["rain_7d_mm"],
                    "rain_14d_mm": agg["rain_14d_mm"],
                },
                "families": fam_scores,
            }
            year = d.year
            by_year_date.setdefault(year, {}).setdefault(iso, {})[cid] = rec
            emitted += 1

        print(
            f"[{i:>3}/{len(cities)}] OK    {label:<32} "
            f"{emitted}/{len(targets)} dates emitted "
            f"(records fetched={len(records)})"
        )
        if args.sleep:
            time.sleep(args.sleep)

    total = len(cities)
    fail_fraction = len(city_failures) / total if total else 1.0
    print("-" * 86)
    if not by_year_date:
        print(
            "ABORT: no city produced any usable backfill date. Writing nothing.",
            file=sys.stderr,
        )
        return 1
    if fail_fraction > san["max_fail_fraction"]:
        print(
            f"ABORT: {len(city_failures)}/{total} cities failed to FETCH "
            f"({fail_fraction:.0%} > {san['max_fail_fraction']:.0%} threshold). "
            f"Writing nothing. (Per-date 'no usable obs' skips are NON-fatal and "
            f"excluded from this fraction; {skipped_dates} such date-skips this run.)",
            file=sys.stderr,
        )
        for f in city_failures:
            print(f"   - {f['city']}: {f['reason']}", file=sys.stderr)
        return 1

    os.makedirs(args.out_archive, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written = []
    for year in sorted(by_year_date):
        path = os.path.join(args.out_archive, f"weather_{year}.json")
        existing = load_json_or(path, default=None) or {}
        merged_by_date = dict(existing.get("by_date") or {})  # FIX E: merge, never clobber
        for iso, city_map in by_year_date[year].items():
            day = dict(merged_by_date.get(iso) or {})
            day.update(city_map)  # overwrite this city's entry; keep other cities/dates
            merged_by_date[iso] = day
        payload = {
            "year": year,
            "provider": provider.name,
            "attribution": provider.attribution,
            "generated_at": generated_at,
            "by_date": {iso: merged_by_date[iso] for iso in sorted(merged_by_date)},
        }
        write_json_atomic(path, payload, indent=None)  # minified (FIX B)
        size = os.path.getsize(path)
        written.append((path, len(merged_by_date), size))

    for w in warnings:
        print(f"WARN: {w}")
    if city_failures:
        print(f"Note: {len(city_failures)} city(ies) failed to fetch but stayed under the abort threshold.")
    if skipped_dates:
        print(f"Note: {skipped_dates} per-date 'no usable obs' skips (latency gaps), non-fatal.")
    for path, ndates, size in written:
        print(f"\nWrote {path}  ({ndates} dates total, {size:,} bytes)")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_args()

    # Backfill dispatch: with a --start/--end range or --as-of date set, recompute
    # past weather sub-scores into data/backfill/. With NO backfill flag we fall
    # straight through to the EXISTING daily path below, verbatim.
    targets = resolve_targets(args)
    if targets is not None:
        return run_backfill(args, targets)

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
