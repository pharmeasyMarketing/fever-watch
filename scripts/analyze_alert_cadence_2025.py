"""
2025 score-movement / push-notification cadence analysis.

Reads the reconstructed 2025 daily score series (data/backfill/sheet/raw_data_2025.csv:
one row per city x disease x day, plus an OVERALL headline row per city/day) and answers:

  1. How often does a city's score CROSS a band boundary (LOW / LOW-MODERATE / MODERATE / HIGH)
     - per week, per disease, per month, and as alert-relevant "entered MODERATE+/HIGH" events.
  2. How often does the score MOVE >= 5 pts, day-over-day and week-over-week, bucketed by
     magnitude, and across how many distinct cities per week.
  3. A guardrail simulation: alert VOLUME under naive-daily vs weekly vs weekly+hysteresis+cooldown.

Bands (config/consolidation.json): LOW 0-24, LOW-MODERATE 25-44, MODERATE 45-69, HIGH 70+.
Forecast-only cells are soft-capped (held below 69, can never reach HIGH) - see the lab-coverage caveat printed.

Output: a printed report + data/analytics/alert_cadence_2025/*.csv weekly tables.
Run: python scripts/analyze_alert_cadence_2025.py
"""
import os
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "backfill", "sheet", "raw_data_2025.csv")
OUT = os.path.join(ROOT, "data", "analytics", "alert_cadence_2025")
os.makedirs(OUT, exist_ok=True)

RANK = {"LOW": 0, "LOW-MODERATE": 1, "MODERATE": 2, "HIGH": 3}
DISEASES = ["Dengue", "Malaria", "Chikungunya", "Typhoid"]
PCT = lambda x: f"{x:.1f}%"


def load():
    df = pd.read_csv(SRC, usecols=["date", "city", "disease", "score", "band", "mode"])
    df["date"] = pd.to_datetime(df["date"])
    df["score"] = df["score"].astype(int)
    df["rank"] = df["band"].map(RANK)
    iso = df["date"].dt.isocalendar()
    df["yw"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    df["month"] = df["date"].dt.strftime("%b")
    return df.sort_values(["city", "disease", "date"]).reset_index(drop=True)


def add_diffs(df):
    g = df.groupby(["city", "disease"], sort=False)
    df["prev_rank"] = g["rank"].shift()
    df["prev_score"] = g["score"].shift()
    df["d_rank"] = df["rank"] - df["prev_rank"]
    df["d_score"] = df["score"] - df["prev_score"]
    df["adscore"] = df["d_score"].abs()
    df["is_cross"] = df["prev_rank"].notna() & (df["d_rank"] != 0)
    df["cross_up"] = df["is_cross"] & (df["d_rank"] > 0)
    df["cross_dn"] = df["is_cross"] & (df["d_rank"] < 0)
    df["entered_high"] = (df["prev_rank"] < 3) & (df["rank"] == 3)
    df["entered_modplus"] = (df["prev_rank"] < 2) & (df["rank"] >= 2)
    return df


def section(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def main():
    df = load()
    weeks = sorted(df["yw"].unique())
    nweeks = len(weeks)
    months = ["Jun", "Jul", "Aug", "Sep", "Oct"]
    dd = df[df["disease"].isin(DISEASES)].copy()        # 4 per-disease series
    ov = df[df["disease"] == "OVERALL"].copy()          # 1 headline series/city
    dd = add_diffs(dd)
    ov = add_diffs(ov)
    ncities = df["city"].nunique()
    n_series = dd.groupby(["city", "disease"]).ngroups   # 912
    cd_weeks = n_series * nweeks                          # city-disease-weeks

    section("SETUP")
    print(f"Season {df.date.min().date()} .. {df.date.max().date()}  "
          f"({df.date.nunique()} days, {nweeks} ISO weeks)")
    print(f"Cities: {ncities}   per-disease series (city x disease): {n_series}   "
          f"city-disease-weeks: {cd_weeks}")
    cov = dd["mode"].value_counts(normalize=True) * 100
    print("Per-disease lab coverage:  " +
          "  ".join(f"{k}={PCT(v)}" for k, v in cov.items()))
    print("CAVEAT: forecast-only cells are soft-capped below 69 (never HIGH). 2025 coverage is far higher "
          "than 2026-live\n        (most 2026 cities are forecast-only), so 2025 OVER-states HIGH "
          "crossings vs what 2026 can fire.")

    # ---- A. band share (where city-days sit) ----
    section("A.  WHERE SCORES SIT  (share of city-days by band)")
    for nm, d in [("per-disease", dd), ("OVERALL", ov)]:
        sh = d["band"].value_counts(normalize=True).reindex(list(RANK))[::-1] * 100
        print(f"  {nm:12s}: " + "  ".join(f"{b}={PCT(sh[b])}" for b in ["HIGH", "MODERATE", "LOW-MODERATE", "LOW"]))

    # ---- B. band crossings, day-to-day ----
    section("B.  BAND CROSSINGS  (day-to-day, per-disease series)")
    tot = int(dd["is_cross"].sum()); up = int(dd["cross_up"].sum()); dn = int(dd["cross_dn"].sum())
    print(f"Total crossings (912 series x 151 day-pairs = {n_series*(df.date.nunique()-1):,}): {tot:,}")
    print(f"  up: {up:,}   down: {dn:,}")
    print(f"\nPER WEEK, across ALL {n_series} city-disease series:")
    print(f"  total crossings/week (sum over all series): {tot/nweeks:,.0f}   "
          f"(up {up/nweeks:,.0f}, down {dn/nweeks:,.0f})")
    # per single city-disease per week
    per = dd.groupby(["city", "disease", "yw"])["is_cross"].sum()
    per_full = per.reindex(pd.MultiIndex.from_product(
        [dd.city.unique(), DISEASES, weeks], names=["city", "disease", "yw"]), fill_value=0)
    print(f"  per ONE city-disease: mean {per_full.mean():.2f} crossings/week, "
          f"median {per_full.median():.0f}, p90 {per_full.quantile(.9):.0f}, max {per_full.max():.0f}")
    dist = per_full.value_counts(normalize=True).sort_index() * 100
    buck = {"0": dist.get(0, 0), "1": dist.get(1, 0), "2": dist.get(2, 0),
            "3+": dist[dist.index >= 3].sum()}
    print("  share of city-disease-weeks with N crossings:  " +
          "  ".join(f"{k}:{PCT(v)}" for k, v in buck.items()))

    # boundary breakdown (up) per week
    section("B2. UP-CROSSINGS BY BOUNDARY  (per week, summed over all city-disease series)")
    def boundary(row):
        a, b = int(row["prev_rank"]), int(row["rank"])
        return f"{['LO','LM','MO','HI'][a]}->{['LO','LM','MO','HI'][b]}"
    ups = dd[dd["cross_up"]].copy()
    ups["bnd"] = ups.apply(boundary, axis=1)
    bc = ups["bnd"].value_counts()
    for k, v in bc.items():
        print(f"  {k}:  {v/nweeks:6.0f}/week   ({v:,} total)")
    print(f"  --> entered MODERATE-or-higher: {dd['entered_modplus'].sum()/nweeks:,.0f}/week "
          f"({int(dd['entered_modplus'].sum()):,} total)")
    print(f"  --> entered HIGH:               {dd['entered_high'].sum()/nweeks:,.0f}/week "
          f"({int(dd['entered_high'].sum()):,} total)")
    eh_city = dd[dd["entered_high"]].groupby("yw")["city"].nunique()
    em_city = dd[dd["entered_modplus"]].groupby("yw")["city"].nunique()
    print(f"  distinct CITIES/week with an entered-HIGH (any disease): mean {eh_city.mean():.0f}, "
          f"max {eh_city.max()}")
    print(f"  distinct CITIES/week with an entered-MOD+ (any disease): mean {em_city.mean():.0f}, "
          f"max {em_city.max()}")

    # by disease and month
    section("B3. CROSSINGS BY DISEASE & MONTH  (per week)")
    print("  by disease (crossings/week summed over its 228 city series):")
    for ds in DISEASES:
        s = dd[dd.disease == ds]
        print(f"    {ds:12s} {s['is_cross'].sum()/nweeks:6.0f}/wk   "
              f"entered-HIGH {s['entered_high'].sum()/nweeks:5.1f}/wk   "
              f"entered-MOD+ {s['entered_modplus'].sum()/nweeks:5.1f}/wk")
    print("  by month (all diseases, crossings/week):")
    for m in months:
        s = dd[dd.month == m]
        wk = s["yw"].nunique()
        print(f"    {m}: {s['is_cross'].sum()/max(wk,1):6.0f}/wk   "
              f"entered-HIGH {s['entered_high'].sum()/max(wk,1):5.1f}/wk")

    # ---- D. >=5pt moves ----
    section("D.  >=5pt MOVES")
    def buckets(series_abs):
        b1 = ((series_abs >= 5) & (series_abs < 10)).sum()
        b2 = ((series_abs >= 10) & (series_abs < 20)).sum()
        b3 = (series_abs >= 20).sum()
        return int(b1), int(b2), int(b3)
    # day over day
    dod = dd[dd["d_score"].notna()]
    n5 = int((dod["adscore"] >= 5).sum())
    b1, b2, b3 = buckets(dod["adscore"])
    print(f"DAY-over-DAY (per-disease):  moves >=5pt = {n5:,} total = {n5/nweeks:,.0f}/week")
    print(f"  buckets/week:  5-9: {b1/nweeks:,.0f}   10-19: {b2/nweeks:,.0f}   20+: {b3/nweeks:,.0f}")
    cdmove = dod[dod["adscore"] >= 5].groupby("yw")["city"].nunique()
    print(f"  distinct cities/week with any >=5pt day move: mean {cdmove.mean():.0f} of {ncities}")

    # week over week on end-of-week snapshot
    wk = (dd.sort_values("date").groupby(["city", "disease", "yw"])
            .agg(score=("score", "last"), band=("band", "last")).reset_index())
    wk["rank"] = wk["band"].map(RANK)
    wk = wk.sort_values(["city", "disease", "yw"])
    g = wk.groupby(["city", "disease"], sort=False)
    wk["d_score"] = g["score"].diff()
    wk["adscore"] = wk["d_score"].abs()
    wk["prev_rank"] = g["rank"].shift()
    wk["cross"] = wk["prev_rank"].notna() & (wk["rank"] != wk["prev_rank"])
    wk["entered_high"] = (wk["prev_rank"] < 3) & (wk["rank"] == 3)
    wk["entered_modplus"] = (wk["prev_rank"] < 2) & (wk["rank"] >= 2)
    wow = wk[wk["d_score"].notna()]
    n5w = int((wow["adscore"] >= 5).sum())
    b1, b2, b3 = buckets(wow["adscore"])
    npairs = len(wow)
    print(f"\nWEEK-over-WEEK (end-of-week snapshot):  moves >=5pt = {n5w:,} of {npairs:,} "
          f"city-disease-week-steps ({PCT(100*n5w/npairs)})")
    print(f"  buckets (share of all week-steps):  "
          f"5-9: {PCT(100*b1/npairs)}   10-19: {PCT(100*b2/npairs)}   20+: {PCT(100*b3/npairs)}")
    cdw = wow[wow["adscore"] >= 5].groupby("yw")["city"].nunique()
    print(f"  distinct cities/week with any >=5pt WoW move (any disease): mean {cdw.mean():.0f} of {ncities}")

    # ---- E. guardrail simulation ----
    section("E.  GUARDRAIL SIMULATION  -  alert VOLUME under 3 policies")
    print("Trigger = an UP move into MODERATE-or-higher (the natural 'your risk rose' push).")
    # P0: daily, every entered-mod+ crossing
    p0 = int(dd["entered_modplus"].sum())
    # P1: weekly snapshot, every entered-mod+ crossing
    p1 = int(wk["entered_modplus"].sum())
    # P2: weekly + hysteresis (must clear boundary+5) + 2-week cooldown per city-disease
    BUF, COOL = 5, 2
    alerts = 0
    wk_sorted = wk.sort_values(["city", "disease", "yw"])
    wkidx = {w: i for i, w in enumerate(weeks)}
    for (c, ds), grp in wk_sorted.groupby(["city", "disease"], sort=False):
        last_alert_i = -COOL - 1
        last_band = None
        for _, r in grp.iterrows():
            rk, prk = r["rank"], r["prev_rank"]
            if pd.isna(prk):
                last_band = rk
                continue
            i = wkidx[r["yw"]]
            entered = (prk < 2) and (rk >= 2)
            # hysteresis: require the score to clear the band floor by BUF
            floor = 70 if rk == 3 else 45
            holds = r["score"] >= floor + BUF
            escalated = (last_band is None) or (rk > last_band)
            cooled = (i - last_alert_i) >= COOL
            if entered and holds and (escalated or cooled):
                alerts += 1
                last_alert_i = i
                last_band = rk
            else:
                last_band = rk
        # note: last_band tracking approximate; policy is illustrative
    p2 = alerts
    for nm, n in [("P0 naive daily (every day a city crosses up into MOD+)", p0),
                  ("P1 weekly snapshot (1 read/week, up into MOD+)", p1),
                  ("P2 weekly + 5pt hysteresis + 2-wk cooldown", p2)]:
        print(f"  {nm:52s}: {n:6,} alerts/season  = {n/nweeks:6.0f}/week "
              f"= {n/nweeks/ncities:.2f}/city/week")
    print(f"\n  P1 cuts naive daily volume by {PCT(100*(1-p1/p0))};  "
          f"P2 cuts it by {PCT(100*(1-p2/p0))}.")

    # ---- weekly tables to CSV ----
    tbl = (dd.groupby("yw").agg(
        crossings=("is_cross", "sum"), up=("cross_up", "sum"), down=("cross_dn", "sum"),
        entered_high=("entered_high", "sum"), entered_modplus=("entered_modplus", "sum"),
        moves_5pt=("adscore", lambda s: int((s >= 5).sum()))).reset_index())
    tbl.to_csv(os.path.join(OUT, "weekly_summary.csv"), index=False)
    perdis = (dd.groupby(["disease", "yw"]).agg(
        crossings=("is_cross", "sum"), entered_high=("entered_high", "sum"),
        entered_modplus=("entered_modplus", "sum")).reset_index())
    perdis.to_csv(os.path.join(OUT, "weekly_by_disease.csv"), index=False)
    print(f"\nWrote weekly tables -> {os.path.relpath(OUT, ROOT)}/ "
          f"(weekly_summary.csv, weekly_by_disease.csv)")


if __name__ == "__main__":
    main()
