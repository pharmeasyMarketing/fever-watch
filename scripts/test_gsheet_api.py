"""Smoke-test the live Google Sheets positivity provider.

  python scripts/test_gsheet_api.py            # try a LIVE read using config/signals.json + service-account creds
  python scripts/test_gsheet_api.py --offline  # validate adapter/resolver/aggregation with synthetic rows (no creds)
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.citymap import CityResolver
from src.signals.gsheet_api import build_index


def offline():
    header = ["Report gen date", "city", "disease",
              "All test reports that has the respective disease parameter included",
              "confirmed positive cases"]
    rows = [header]
    # Mumbai dengue: 5 days, 40 tests / 8 positives in-window -> 20% -> /35*100 = 57
    for day, t, p in [(10, 8, 1), (11, 9, 2), (12, 7, 1), (13, 8, 2), (14, 8, 2)]:
        rows.append([f"{day}-06-2026", "mumbai", "dengue", t, p])
    rows.append(["12-06-2026", "bengaluru", "typhoid", 5, 1])     # below gate -> None
    rows.append(["12-06-2026", "KALYAN", "dengue", 40, 10])        # satellite fold -> thane
    rows.append(["12-06-2026", "Foobar Town", "dengue", 50, 9])    # unmapped -> logged, dropped
    r = CityResolver()
    idx = build_index(rows, r, window_days=28, min_tests=30, ref_pct=35.0)
    print("index:", idx)
    print("unmapped:", dict(r.unmapped))
    checks = [
        ("mumbai dengue signal == 57", idx.get(("mumbai", "dengue")) == 57),
        ("bengaluru typhoid gated to None", idx.get(("bengaluru", "typhoid")) is None),
        ("KALYAN folded to thane", idx.get(("thane", "dengue")) is not None),
        ("Foobar Town unmapped (not in index)", all(k[0] != "foobar town" for k in idx)),
        ("Foobar Town logged", any("FOOBAR" in u for u in r.unmapped)),
    ]
    ok = sum(1 for _, c in checks if c)
    for name, c in checks:
        print(f"  [{'OK' if c else 'FAIL'}] {name}")
    print(f"{ok}/{len(checks)} passed")
    return ok == len(checks)


def live():
    from src.signals import get_positivity_provider
    cfg = json.load(open(os.path.join("config", "signals.json")))["positivity"]
    print("reading tab:", cfg["gsheet_api"]["tab"])
    try:
        prov = get_positivity_provider("gsheet_api", cfg)
    except Exception as e:
        print("LIVE READ FAILED:", type(e).__name__, str(e)[:400])
        print("\nIf this is a credentials error, complete the service-account setup and share the sheet with the SA email (Viewer).")
        return
    idx = prov._index
    have = {k: v for k, v in idx.items() if v is not None}
    print(f"city x disease cells: {len(idx)} | with a signal (>=30 tests): {len(have)}")
    for k, v in list(have.items())[:12]:
        print("  ", k, "->", v)
    if os.path.exists("data/citymap/unmapped_live.csv"):
        print("unmapped strings logged to data/citymap/unmapped_live.csv (review + add to manual_aliases.csv)")


if __name__ == "__main__":
    if "--offline" in sys.argv:
        sys.exit(0 if offline() else 1)
    live()
