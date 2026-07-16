"""Fever Watch consolidation engine.

Confirmation-weighted ensemble of three signals into ONE risk score per
(city, disease). This is the deliberate inverse of Mosquito Watch, which keeps
its layers separate and never blends them; here, blending into a single
*decomposable* score is the whole product.

Signals (each sits at a different point in the illness pipeline):
    weather     leading      environmental breeding / transmission favourability
    trends      coincident   population search attention (news-spike aware)
    positivity  lagging      PharmEasy lab positivity, the ground truth (if any)

Rules (all numbers live in config/consolidation.json):
  * With positivity: it dominates (weights ~30/22/48). When all three signals
    agree (small spread) a confidence multiplier is applied; otherwise the
    score is damped slightly and confidence drops to Moderate.
  * Without positivity: "Forecast only" mode blends weather and trends and applies
    a SOFT-KNEE taper toward the cap, so a conditions-only read can never reach
    HIGH. Below the knee the blend passes through unchanged; above it every extra
    raw point buys proportionally less displayed score, so scores approach but
    never pile up on the cap. This honesty mechanism protects credibility while
    preserving the real differences between cities (the old hard clip flattened
    every strong-conditions city onto the same number). Set soft_knee == score_cap
    in config to recover the legacy hard clip.
  * The output is always decomposable (weights + per-signal values + a plain
    note), never a mystery number.

Pure and dependency-free: callers pass a signals dict and the loaded config; the
builder layer owns all IO. A small self-test runs under __main__.
"""
from __future__ import annotations


def consolidate(signals: dict, cfg: dict) -> dict:
    """Blend a signal triplet into a score plus full provenance.

    signals: {"weather": 0-100, "trends": 0-100,
              "positivity": 0-100 or None, "news_spike": bool}
    cfg:     parsed config/consolidation.json
    returns: {"score": int, "weights": {...}, "confidence": str,
              "note": str, "mode": "confirmed" | "forecast"}
    """
    weather = _clamp(signals.get("weather"))
    trends = _clamp(signals.get("trends"))
    raw_pos = signals.get("positivity")
    positivity = _clamp(raw_pos) if raw_pos is not None else None
    news_spike = bool(signals.get("news_spike"))

    if positivity is not None:
        c = cfg["with_positivity"]
        w = c["weights"]
        base = w["weather"] * weather + w["trends"] * trends + w["positivity"] * positivity
        spread = max(weather, trends, positivity) - min(weather, trends, positivity)
        agree = spread < c["agreement_spread_max"]
        score = min(100.0, base * c["agree_multiplier"]) if agree else base * c["disagree_multiplier"]
        weights = {
            "weather": round(w["weather"] * 100),
            "trends": round(w["trends"] * 100),
            "positivity": round(w["positivity"] * 100),
        }
        confidence = "High" if agree else "Moderate"
        note = (
            "All three signals agree - lab tests, search and weather point the same way."
            if agree
            else "Signals disagree: we trust the lab tests most, and weather and search matter less."
        )
        mode = "confirmed"
    else:
        c = cfg["forecast_only"]
        w = c["weights"]
        base = w["weather"] * weather + w["trends"] * trends
        score = _soft_knee(base, c.get("soft_knee", c["score_cap"]), c["score_cap"])
        weights = {
            "weather": round(w["weather"] * 100),
            "trends": round(w["trends"] * 100),
            "positivity": 0,
        }
        confidence = "Forecast only"
        note = "No confirmed test data here yet, so the score uses weather and search only, and can't reach HIGH."
        if news_spike:
            note += " Search may be driven by news, so we trust it less."
        mode = "forecast"

    return {
        "score": int(round(score)),
        "weights": weights,
        "confidence": confidence,
        "note": note,
        "mode": mode,
    }


def band(score: int, cfg: dict) -> dict:
    """Map a 0-100 score to its band dict (bands listed high to low in config)."""
    for b in cfg["bands"]:
        if score >= b["min"]:
            return b
    return cfg["bands"][-1]


def _clamp(value, lo: float = 0.0, hi: float = 100.0) -> float:
    if value is None:
        return lo
    try:
        f = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, f))


def _soft_knee(base: float, knee: float, cap: float) -> float:
    """Soft-knee taper for the forecast-only (no-lab) score.

    Below `knee` the blend passes through unchanged; from `knee` up to a raw
    blend of 100 it is compressed linearly into [`knee`, `cap`]. So the cap is
    only reached at a theoretical raw blend of 100 (both weather and search
    maxed at once) and never becomes a wall that many cities pile onto. Strictly
    monotonic, continuous at the knee, and identical to a hard clip when
    knee == cap. Standard dynamic-range compression, same construction the AQI
    uses to map raw values through piecewise-linear breakpoints.
    """
    b = min(base, 100.0)
    if b <= knee or knee >= 100.0:
        return min(b, cap)
    return knee + (b - knee) * (cap - knee) / (100.0 - knee)


if __name__ == "__main__":
    import json
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "consolidation.json"), "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    cases = [
        ("Confirmed, all agree", {"weather": 78, "trends": 74, "positivity": 80, "news_spike": False}),
        ("Confirmed, diverging", {"weather": 80, "trends": 30, "positivity": 35, "news_spike": False}),
        ("Forecast, below knee", {"weather": 55, "trends": 40, "positivity": None, "news_spike": False}),
        ("Forecast, mid taper", {"weather": 80, "trends": 70, "positivity": None, "news_spike": False}),
        ("Forecast, near max", {"weather": 100, "trends": 95, "positivity": None, "news_spike": False}),
        ("Forecast only + news spike", {"weather": 40, "trends": 88, "positivity": None, "news_spike": True}),
        ("Low everywhere", {"weather": 12, "trends": 9, "positivity": 7, "news_spike": False}),
    ]
    print("Fever Watch consolidation smoke test")
    print("-" * 74)
    for name, sig in cases:
        r = consolidate(sig, cfg)
        bnd = band(r["score"], cfg)
        print(f"  {name:28} score={r['score']:>3}  {bnd['label']:<13} [{r['confidence']:<13}] {r['mode']}")
    print("-" * 74)

    # Soft-knee invariants (fail loud if the taper ever regresses).
    fo = cfg["forecast_only"]
    knee, cap = fo.get("soft_knee", fo["score_cap"]), fo["score_cap"]
    assert _soft_knee(knee, knee, cap) == knee, "identity must hold at the knee"
    assert _soft_knee(0.0, knee, cap) == 0.0 and _soft_knee(30.0, knee, cap) == 30.0, "pass-through below the knee"
    assert abs(_soft_knee(100.0, knee, cap) - cap) < 1e-9, "raw 100 maps exactly to the cap"
    ladder = [_soft_knee(x, knee, cap) for x in range(0, 101)]
    assert all(ladder[i] <= ladder[i + 1] + 1e-9 for i in range(len(ladder) - 1)), "must be monotonic"
    assert max(ladder) <= cap + 1e-9, "never exceeds the cap"
    assert _soft_knee(85.0, cap, cap) == cap, "knee==cap recovers the legacy hard clip"
    forecast_scores = [consolidate({"weather": w, "trends": t, "positivity": None}, cfg)["score"]
                       for w in range(0, 101, 5) for t in range(0, 101, 5)]
    assert max(forecast_scores) < 70, "forecast-only can NEVER reach the HIGH band (>=70)"
    print(f"  soft-knee OK: knee={knee} cap={cap}; forecast range "
          f"{min(forecast_scores)}..{max(forecast_scores)} (all < 70, no HIGH). Only raw 100 -> {cap}.")
