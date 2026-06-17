"""Build the HISTORIC (last-season 2025) lab feed for Fever Watch.

Transforms the audited daily raw extract (TC Fever Watch Data 2025.xlsx) into the
documented weekly historic schema (docs/lab_feed_historic_format.md):
  week_start, season_week, city(config id), disease, tests_booked, positives

- Applies the verified city alias map (data/citymap/city_alias_map.csv) + the user's
  final decisions (BILASPUR->bilaspur, GOA/SOUTH GOA->panaji) idempotently, so it is
  correct even before those edits are persisted to the (currently Excel-locked) CSV.
- Sums consolidation groups automatically (group by config_id).
- 22 weekly buckets anchored to 1 June 2025; emits all 22 weeks for every city x disease
  that has any 2025 data (zeros where a week is empty); raw counts kept so the 30-test
  confidence gate works downstream.
"""
import pandas as pd, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CM = os.path.join(ROOT, 'data', 'citymap')
SEASON_START = pd.Timestamp('2025-06-01')
N_WEEKS = 22
OUT = os.path.join(ROOT, 'data', 'lab_feed_2025_historic.csv')

# ---- final alias map (persisted 241 + user round-2 edits, applied idempotently) ----
amap = pd.read_csv(os.path.join(CM, 'city_alias_map.csv'))
raw2id = dict(zip(amap.raw, amap.config_id))
for raw, cid in {'BILASPUR': 'bilaspur', 'GOA': 'panaji', 'SOUTH GOA': 'panaji'}.items():
    raw2id[raw] = cid
print('final alias map: %d strings -> %d config cities' % (len(raw2id), len(set(raw2id.values()))))

# ---- load audited source ----
df = pd.read_excel(os.path.join(ROOT, 'TC Fever Watch Data 2025.xlsx'), sheet_name='Sheet1')
df = df[df.city.notna()].copy()
df['city_id'] = df.city.map(raw2id)
mapped = df[df.city_id.notna()].copy()

dropped_tests = int(df[df.city_id.isna()].total_tests.sum())
print('source rows: %d | mapped rows: %d | unmapped(new/excluded) tests dropped: %d' % (len(df), len(mapped), dropped_tests))

# ---- weekly bucketing ----
mapped['season_week'] = ((mapped.dt - SEASON_START).dt.days // 7) + 1
mapped = mapped[(mapped.season_week >= 1) & (mapped.season_week <= N_WEEKS)]
agg = (mapped.groupby(['city_id', 'disease', 'season_week'], as_index=False)
       .agg(tests_booked=('total_tests', 'sum'), positives=('total_positive_cases', 'sum')))

# ---- emit all 22 weeks for every present city x disease ----
combos = agg[['city_id', 'disease']].drop_duplicates()
weeks = pd.DataFrame({'season_week': range(1, N_WEEKS + 1)})
grid = combos.merge(weeks, how='cross')
out = grid.merge(agg, on=['city_id', 'disease', 'season_week'], how='left')
out['tests_booked'] = out.tests_booked.fillna(0).astype(int)
out['positives'] = out.positives.fillna(0).astype(int)
# Computed positivity build-up (mirrors src/signals/gsheet_api._signal, the live feed) so this file shows
# HOW the last-year positivity score is derived, end to end:
#   positivity_pct    = positives / tests_booked * 100            (raw lab positivity rate)
#   positivity_signal = MIN(100, ROUND(positivity_pct / ref * 100)) (0-100 score; ref% = full signal),
#                       BLANK below the 30-test confidence gate -> "no data" (forecast-only downstream).
# ref is PER DISEASE (each fever has a different realistic 'high'): MUST match config/signals.json
# ref_positivity_pct_by_disease + src/build_archive.py LAB_REF_BY_DISEASE.
REF_BY_DISEASE, REF_FALLBACK, GATE = {'dengue': 25.0, 'malaria': 4.0, 'chikungunya': 15.0, 'typhoid': 45.0}, 35.0, 30
out['positivity_pct'] = (out.positives / out.tests_booked.where(out.tests_booked > 0) * 100).round(1)
out['positivity_signal'] = out.apply(
    lambda r: max(0, min(100, round(r.positivity_pct / REF_BY_DISEASE.get(r.disease, REF_FALLBACK) * 100)))
    if (r.tests_booked >= GATE and pd.notna(r.positivity_pct)) else None, axis=1)
out['week_start'] = (SEASON_START + pd.to_timedelta((out.season_week - 1) * 7, unit='D')).dt.strftime('%Y-%m-%d')
out = out.rename(columns={'city_id': 'city'})[['week_start', 'season_week', 'city', 'disease',
                                               'tests_booked', 'positives', 'positivity_pct', 'positivity_signal']]
out = out.sort_values(['city', 'disease', 'season_week'])
out.to_csv(OUT, index=False)

# ---- verify + report ----
assert out.tests_booked.sum() == mapped.total_tests.sum(), 'volume mismatch!'
assert out.positives.sum() == mapped.total_positive_cases.sum(), 'positives mismatch!'
print('\nWROTE %s' % OUT)
print('  rows: %d | cities: %d | city x disease combos: %d' % (len(out), out.city.nunique(), len(combos)))
print('  tests_booked total: %d | positives total: %d (reconciles to mapped source)' % (out.tests_booked.sum(), out.positives.sum()))

# how much of the last-year line will actually be visible at the 30-test gate
gate = out[out.tests_booked >= 30]
combo_any = gate.groupby(['city', 'disease']).size().shape[0]
combo_usable = (gate.groupby(['city', 'disease']).size() >= 11).sum()
print('\nVISIBILITY AT 30-TEST GATE:')
print('  weekly cells >= 30: %d / %d (%.1f%%)' % (len(gate), len(out), 100 * len(gate) / len(out)))
print('  city x disease with >=1 week >=30: %d / %d' % (combo_any, len(combos)))
print('  city x disease with a usable line (>=11/22 wks >=30): %d' % combo_usable)
print('  dengue cities with >=1 week >=30: %d' % gate[gate.disease == 'dengue'].city.nunique())
print('\nSAMPLE - Mumbai dengue weekly (last-year line):')
mb = out[(out.city == 'mumbai') & (out.disease == 'dengue')]
print('  tests:', mb.tests_booked.tolist())
print('  pos:  ', mb.positives.tolist())
