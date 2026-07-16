"""Explain a Fever Watch score, step by step, from live signals - including the labs build-up.

Shows EXACTLY how a city x disease score is derived from the three signals (weather,
search, lab positivity), so you can review the maths locally now that real lab data is
flowing. Uses the live Google Sheets positivity provider (needs secrets/gsheets_sa.json),
the cached/mock trends, and data/weather.json.

  python scripts/explain_score.py                     # a few metros x dengue+typhoid
  python scripts/explain_score.py mumbai delhi        # all 4 diseases for these cities
  python scripts/explain_score.py --city bengaluru --disease typhoid
"""
import argparse, io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import signals  # noqa: E402
from consolidate import consolidate, band  # noqa: E402


def _load(p):
    return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cities", nargs="*", help="city ids (default: a few metros)")
    ap.add_argument("--city")
    ap.add_argument("--disease", help="restrict to one disease id")
    args = ap.parse_args()

    consol = _load("config/consolidation.json")
    sig_cfg = _load("config/signals.json")
    diseases = {d["id"]: d for d in _load("config/diseases.json")["diseases"]}
    cities = {c["id"]: c for c in _load("config/cities.json")["cities"]}
    weather_by_city = {c["id"]: c for c in _load("data/weather.json")["cities"]}

    want = args.cities or ([args.city] if args.city else ["mumbai", "delhi", "bengaluru", "chennai", "patna"])
    dz = [args.disease] if args.disease else (["dengue", "typhoid"] if not (args.cities or args.city) else list(diseases))

    pos_cfg = sig_cfg.get("positivity", {})
    positivity_p = signals.get_positivity_provider("gsheet_api", pos_cfg)
    trends_cfg = sig_cfg.get("trends", {})
    tname = "cached" if os.path.exists(os.path.join(ROOT, (trends_cfg.get("cached") or {}).get("path", "data/trends.json"))) else "mock"
    if tname == "cached":
        trends_cfg = {**trends_cfg, "cached": {"path": os.path.join(ROOT, trends_cfg["cached"]["path"])}}
    trends_p = signals.get_trends_provider(tname, trends_cfg)
    wp = consol["with_positivity"]["weights"]
    fo = consol["forecast_only"]
    ref = float((pos_cfg.get("gsheet_api") or {}).get("ref_positivity_pct", 35))
    gate = int((pos_cfg.get("gsheet_api") or {}).get("min_tests", 30))

    print("Fever Watch score derivation (live)  |  trends=%s  positivity=%s  ref_pct=%g  gate=%d tests" % (trends_p.name, positivity_p.name, ref, gate))
    print("weights with-positivity = weather %.2f / trends %.2f / positivity %.2f ; forecast = weather %.2f / trends %.2f soft-knee %g cap %d"
          % (wp["weather"], wp["trends"], wp["positivity"], fo["weights"]["weather"], fo["weights"]["trends"], fo.get("soft_knee", fo["score_cap"]), fo["score_cap"]))

    for cid in want:
        c = cities.get(cid)
        wc = weather_by_city.get(cid)
        if not c or not wc:
            print("\n%s: not in config/weather" % cid); continue
        for did in dz:
            d = diseases.get(did)
            if not d:
                continue
            fam = d["family"]
            W = wc.get("families", {}).get(fam)
            tr = trends_p.fetch(c, d); T = tr["value"]
            P = positivity_p.fetch(c, d)
            det = positivity_p.detail(c, d)
            print("\n" + "=" * 78)
            print("%s / %s   (family: %s)" % (c["name"], d["id"], fam))
            print("-" * 78)
            # 1) LABS build-up
            if det:
                pct = det["pct"]
                line = "  LABS:  tests=%d  positives=%d  over last %dd  ->  positivity_pct = %d/%d = %s%%" % (
                    det["tests"], det["positives"], det["window_days"], det["positives"], det["tests"],
                    ("%.1f" % pct) if pct is not None else "n/a")
                print(line)
                if det["gated"]:
                    print("         tests %d < gate %d  ->  NO DATA (forecast-only)" % (det["tests"], gate))
                else:
                    print("         signal = min(100, round(%.1f / %g x 100)) = %s" % (pct, ref, P))
            else:
                print("  LABS:  no rows for this city/disease  ->  NO DATA (forecast-only)")
            # 2) sub-scores
            print("  SUB-SCORES (0-100):  weather=%s  trends=%s  positivity=%s" % (W, T, P if P is not None else "-"))
            # 3) blend (authoritative via consolidate) + manual arithmetic
            r = consolidate({"weather": W, "trends": T, "positivity": P, "news_spike": tr.get("news_spike")}, consol)
            if P is not None:
                base = wp["weather"] * W + wp["trends"] * T + wp["positivity"] * P
                spread = max(W, T, P) - min(W, T, P)
                agree = spread < consol["with_positivity"]["agreement_spread_max"]
                mult = consol["with_positivity"]["agree_multiplier"] if agree else consol["with_positivity"]["disagree_multiplier"]
                print("  BLEND:  base = 0.30x%s + 0.22x%s + 0.48x%s = %.1f" % (W, T, P, base))
                print("          spread = %d-%d = %d  ->  %s (<%d?)  ->  x%.2f" % (
                    max(W, T, P), min(W, T, P), spread, "AGREE" if agree else "DISAGREE",
                    consol["with_positivity"]["agreement_spread_max"], mult))
                print("          score = round(min(100, %.1f x %.2f)) = %d" % (base, mult, r["score"]))
            else:
                base = fo["weights"]["weather"] * W + fo["weights"]["trends"] * T
                knee, capv = fo.get("soft_knee", fo["score_cap"]), fo["score_cap"]
                print("  BLEND (forecast-only):  base = 0.60x%s + 0.40x%s = %.1f" % (W, T, base))
                if base <= knee:
                    print("          score = round(%.1f) = %d  (below the %g soft-knee, unchanged; cannot reach HIGH)" % (base, r["score"], knee))
                else:
                    print("          score = round(%g + (%.1f-%g)x%d/%d) = %d  (soft-knee taper, cannot reach HIGH)" % (
                        knee, base, knee, capv - knee, 100 - knee, r["score"]))
            print("  =>  SCORE %d  [%s]  %s  (%s)" % (r["score"], band(r["score"], consol)["label"], r["mode"], r["confidence"]))


if __name__ == "__main__":
    main()
