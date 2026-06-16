"""Audit the live lab feed: gate-coverage across trailing windows + unmapped cities.

Use to (a) re-tune positivity.gsheet_api.window_days as the season fills (longer window =
more cells clear the 30-test gate, but less 'recent'), and (b) review live city strings that
did not resolve, so they can be added to data/citymap/manual_aliases.csv (correctness over
coverage - nothing is auto-mapped). Reads the live sheet once via the Sheets API.

  python scripts/positivity_audit.py
"""
import io, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from citymap import CityResolver  # noqa: E402
from signals.gsheet_api import read_values, build_index, _to_int  # noqa: E402

cfg = json.load(io.open(os.path.join(ROOT, "config", "signals.json"), encoding="utf-8"))["positivity"]["gsheet_api"]
gate = int(cfg.get("min_tests", 30))
ref = float(cfg.get("ref_positivity_pct", 35))
vals = read_values(cfg["spreadsheet_id"], cfg["tab"], cfg)
hdr = [str(h).strip().lower() for h in vals[0]]
ic = hdr.index("city")
it = next(i for i, h in enumerate(hdr) if "all test reports" in h or h in ("total_tests", "tests"))

print("tab: %s  |  rows: %d  |  gate: %d tests  |  ref_pct: %g" % (cfg["tab"], len(vals) - 1, gate, ref))
print("\nGATE COVERAGE vs trailing window (city x disease cells with a signal):")
for wd in (7, 14, 21, 28, 0):
    r = CityResolver()
    idx = build_index(vals, r, window_days=wd, min_tests=gate, ref_pct=ref)
    signals_n = sum(1 for v in idx.values() if v is not None)
    cities_n = len({k[0] for k, v in idx.items() if v is not None})
    label = "ALL season" if wd == 0 else "%2dd" % wd
    print("  window %-9s ->  %3d cells with signal  across %3d cities  (current config.window_days=%d)"
          % (label, signals_n, cities_n, cfg.get("window_days", 28)))

# unmapped strings (with test volume) for manual_aliases review
r = CityResolver()
unmapped = defaultdict(int)
for row in vals[1:]:
    city = row[ic] if ic < len(row) else ""
    if city and r.resolve(city) is None:
        unmapped[str(city).strip()] += (_to_int(row[it] if it < len(row) else None) or 0)
print("\nUNMAPPED live city strings: %d distinct, %d tests total (expected = the 2025 'new cities' tail)"
      % (len(unmapped), sum(unmapped.values())))
print("Top 20 by test volume (add genuine config-city variants to data/citymap/manual_aliases.csv):")
for k, v in sorted(unmapped.items(), key=lambda x: -x[1])[:20]:
    print("  %-28s %d tests" % (k, v))
