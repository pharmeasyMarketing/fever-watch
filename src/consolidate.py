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
  * Without positivity: "Forecast only" mode blends weather and trends and CAPS
    the score, so a conditions-only read can never reach HIGH. This honesty
    mechanism protects credibility.
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
            "All three signals agree: confirmed positivity, search interest and weather line up."
            if agree
            else "Signals diverge, so confirmed positivity leads the score and weather and search count for less."
        )
        mode = "confirmed"
    else:
        c = cfg["forecast_only"]
        w = c["weights"]
        base = w["weather"] * weather + w["trends"] * trends
        score = min(c["score_cap"], base)
        weights = {
            "weather": round(w["weather"] * 100),
            "trends": round(w["trends"] * 100),
            "positivity": 0,
        }
        confidence = "Forecast only"
        note = "No confirmed-case data here yet, so this is a conditions-based forecast and the score is capped."
        if news_spike:
            note += " Search interest may be news-driven, so it is down-weighted."
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


if __name__ == "__main__":
    import json
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "consolidation.json"), "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    cases = [
        ("Confirmed, all agree", {"weather": 78, "trends": 74, "positivity": 80, "news_spike": False}),
        ("Confirmed, diverging", {"weather": 80, "trends": 30, "positivity": 35, "news_spike": False}),
        ("Forecast only (capped)", {"weather": 90, "trends": 85, "positivity": None, "news_spike": False}),
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
    print("  expect: forecast-only never reaches HIGH (cap 69 < 70); confirmed+agree can amplify.")
