"""Per-family weather shaping for Fever Watch (transparent, not machine learning).

Each scorer turns a window of trailing daily weather into a 0-100 environmental
favourability sub-score for one disease 'family'. That sub-score becomes the
'weather' signal of the consolidation engine.

Families:
  mosquito    unimodal temperature near the optimum, times lagged rainfall
              (standing water), times humidity. Aedes / Anopheles breeding.
  waterborne  recent plus accumulated rainfall as a contamination / runoff proxy.
  febrile     humidity plus day-to-day temperature variability plus some rain.

Inputs are aggregated from the normalized DailyWeather records the weather
providers return; None values are skipped when aggregating. All tunables live in
config/scoring.json so the formula stays transparent and easy to defend.
"""
from __future__ import annotations

from statistics import mean


def _sat(value: float, saturation: float) -> float:
    """Saturating ramp: value / saturation, clamped to [0, 1]."""
    if not saturation or saturation <= 0:
        return 0.0
    return max(0.0, min(1.0, value / saturation))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _humidity_unit(humidity_pct, fam) -> float:
    """Map relative humidity onto [0, 1] between the family floor and ceiling."""
    if humidity_pct is None:
        return 0.0
    span = fam["humidity_ceiling_pct"] - fam["humidity_floor_pct"]
    if span <= 0:
        return 0.0
    return _clamp01((humidity_pct - fam["humidity_floor_pct"]) / span)


def temp_fit(temp_c, fam) -> float:
    """Unimodal temperature response peaking at temp_optimal_c, zero outside
    [temp_min_c, temp_max_c], quadratic falloff with half-width temp_width."""
    if temp_c is None:
        return 0.0
    if temp_c <= fam["temp_min_c"] or temp_c >= fam["temp_max_c"]:
        return 0.0
    v = 1.0 - ((temp_c - fam["temp_optimal_c"]) / fam["temp_width"]) ** 2
    return _clamp01(v)


def aggregate(records) -> dict:
    """Collapse a list of DailyWeather into the window stats the families need.

    Records may arrive in any order; we sort by date and use trailing windows.
    Because providers drop missing days, the n-day windows are 'last n available
    days', a reasonable proxy given NASA POWER's occasional interior gaps.
    """
    recs = sorted(records, key=lambda r: r.date)
    temps = [r.temp_mean_c for r in recs if r.temp_mean_c is not None]
    hums = [r.humidity_pct for r in recs if r.humidity_pct is not None]
    precs = [r.precip_mm for r in recs if r.precip_mm is not None]

    def rain_last(n: int) -> float:
        window = precs[-n:] if n else precs
        return sum(window)

    swings = [abs(temps[i] - temps[i - 1]) for i in range(1, len(temps))]

    return {
        "n_days": len(recs),
        "temp_mean_c": round(mean(temps), 1) if temps else None,
        "humidity_pct": round(mean(hums), 1) if hums else None,
        "rain_7d_mm": round(rain_last(7), 1),
        "rain_14d_mm": round(rain_last(14), 1),
        "temp_swing_c": round(mean(swings), 2) if swings else 0.0,
        "has_temp": bool(temps),
        "has_precip": bool(precs),
    }


def score_mosquito(agg, fam):
    t = temp_fit(agg["temp_mean_c"], fam)
    rain = _sat(agg["rain_14d_mm"], fam["rain_saturation_mm"])
    hum = _humidity_unit(agg["humidity_pct"], fam)
    w = fam["weights"]
    score = (w["temp"] * t + w["rain_lagged"] * rain + w["humidity"] * hum) * 100
    return round(score), {"temp": round(t, 3), "rain_lagged": round(rain, 3), "humidity": round(hum, 3)}


def score_waterborne(agg, fam):
    recent = _sat(agg["rain_7d_mm"], fam["rain_saturation_mm"])
    lagged = _sat(agg["rain_14d_mm"], fam["rain_saturation_mm"])
    w = fam["weights"]
    score = (w["rain_recent"] * recent + w["rain_lagged"] * lagged) * 100
    return round(score), {"rain_recent": round(recent, 3), "rain_lagged": round(lagged, 3)}


def score_febrile(agg, fam):
    hum = _humidity_unit(agg["humidity_pct"], fam)
    swing = _sat(agg["temp_swing_c"], fam["temp_swing_saturation_c"])
    rain = _sat(agg["rain_14d_mm"], fam["rain_saturation_mm"])
    w = fam["weights"]
    score = (w["humidity"] * hum + w["temp_swing"] * swing + w["rain"] * rain) * 100
    return round(score), {"humidity": round(hum, 3), "temp_swing": round(swing, 3), "rain": round(rain, 3)}


FAMILY_SCORERS = {
    "mosquito": score_mosquito,
    "waterborne": score_waterborne,
    "febrile": score_febrile,
}


def score_family(family: str, agg: dict, families_cfg: dict):
    """Dispatch to the right scorer. Returns (score_0_100, components dict)."""
    if family not in FAMILY_SCORERS:
        raise ValueError(f"Unknown disease family '{family}'. Known: {', '.join(FAMILY_SCORERS)}")
    return FAMILY_SCORERS[family](agg, families_cfg[family])
