"""One-time historical Google Trends backfill (signal 2) via SerpApi.

Pulls a per-state, per-disease WEEKLY interest-over-time series spanning the last
year (one date-ranged TIMESERIES call per state x disease covers BOTH years) into
data/backfill/trends_history.json, a gitignored regenerable intermediate. The
downstream archive runner consumes this to compute the city-level cross-disease
"search" mean and the last-year peak; this runner stores RAW per-state per-disease
series only and derives nothing.

Quota: ~35 states x 4 diseases = ~140 SerpApi calls (null-geo states skipped).
Keys are loaded from apify.env (gitignored, NOT committed); failover skips an
exhausted key (429 / quota) and moves to the next. Carry-forward over an existing
file makes a partial / interrupted run resumable.

Usage:
    python src/backfill_trends.py

Stdlib only. ASCII hyphens only.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from iohelpers import load_json, load_json_or, write_json_atomic  # noqa: E402
from signals.serpapi import SerpApiTrendsProvider  # noqa: E402

ROOT = os.path.dirname(SRC_DIR)
DATE_RANGE = "2025-06-01 2026-06-13"
SLEEP_S = 1.0
KEY_NAMES = ("SERPAPI_KEY", "SERPAPI_KEY_2", "SERPAPI_KEY_3", "SERPAPI_KEY_4", "SERPAPI_KEY_5")

ACCOUNT_ENDPOINT = "https://serpapi.com/account.json"

# The shared SerpApiTrendsProvider._get() failover raises RuntimeError("failed on all
# N key(s): <last_err>") for BOTH a genuine quota wipeout AND a per-query SerpApi
# 'error' (e.g. a tiny state with no Google Trends data -> "hasn't returned any
# results"), and the surfaced last_err can even be the exhausted KEY_1's "out of
# searches" message regardless of the true cause. So we do NOT trust the message: on
# a RuntimeError we check live remaining quota across the keys. Quota left > 0 means
# it was a no-data / bad-geo error for that one state (skip it, no real search spent);
# quota left == 0 means a genuine wipeout (abort and persist progress).


def _total_searches_left(keys: list) -> int:
    import json
    import urllib.parse
    import urllib.request
    total = 0
    for k in keys:
        url = ACCOUNT_ENDPOINT + "?" + urllib.parse.urlencode({"api_key": k})
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
            total += int(d.get("total_searches_left") or 0)
        except Exception:
            # An account-check failure is not proof of exhaustion; assume some quota
            # remains so a transient blip does not falsely abort the run.
            total += 1
    return total


def load_keys_from_envfile(path: str) -> list:
    """Read SERPAPI_KEY[_2.._5] from a KEY=value env file (NOT committed).

    Plain unquoted KEY=value lines; tolerates surrounding quotes and an optional
    'export ' prefix. Never logs or returns anything but the raw key strings.
    """
    found = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.lower().startswith("export "):
                    s = s[7:].strip()
                key, sep, val = s.partition("=")
                if not sep:
                    continue
                key = key.strip()
                val = val.strip().strip('"').strip("'").strip()
                if key in KEY_NAMES and val:
                    found[key] = val
    # Preserve KEY_NAMES order so the (typically exhausted) SERPAPI_KEY is first
    # and failover rotates forward into KEY_2..5.
    keys, seen = [], set()
    for name in KEY_NAMES:
        v = found.get(name)
        if v and v not in seen:
            keys.append(v)
            seen.add(v)
    return keys


def pull_history(provider, diseases, terms, geo_map, date_range, out_path, sleep_s=SLEEP_S) -> int:
    """Pull a per-state x disease WEEKLY interest-over-time series for date_range, carry-forward merge over
    any existing out_path, and write atomically. Shared by the one-time backfill (main, apify.env keys) and
    the recurring weekly refresh (refresh_trends_timeseries.py, env/Actions-secret keys). Returns a process
    exit code: 0 = wrote a clean run, 1 = nothing returned OR the run aborted on a genuine quota wipeout
    (carry-forward keeps any partial progress so a re-run resumes)."""
    states_with_geo = [(s, g) for s, g in geo_map.items() if g]
    null_states = [s for s, g in geo_map.items() if not g]
    planned = len(states_with_geo) * len(diseases)
    print(f"SerpApi keys: {len(provider.keys)}  |  date_range: {date_range}")
    print(f"diseases: {len(diseases)}  |  states(geo): {len(states_with_geo)}  |  null-skipped: {len(null_states)}")
    print(f"planned calls: ~{planned}")
    print("-" * 72)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_diseases: dict = {}
    calls_made = 0
    empty = []   # (disease, state) that returned an empty series / no Google Trends data
    errored = []  # (disease, state, msg) that raised a non-quota error
    aborted = False

    for d in diseases:
        did = d["id"]
        query = (terms.get(did) or [d["label"]])[0]  # primary term, same pick as build_trends.py
        by_state: dict = {}
        for state, geo in states_with_geo:
            try:
                series = provider.interest_over_time_by_state(query, geo, date_range)
                calls_made += 1
                if series:
                    by_state[state] = series
                    print(f"  {did:12} {state:42} {geo:6} OK pts={len(series)}")
                else:
                    empty.append((did, state))
                    print(f"  {did:12} {state:42} {geo:6} EMPTY (no Google Trends data)")
            except RuntimeError as err:
                # _get() exhausted its rotation. Disambiguate via live quota: a tiny state with no data
                # raises the same RuntimeError as a real wipeout.
                if _total_searches_left(provider.keys) <= 0:
                    errored.append((did, state, str(err)))
                    print(f"  {did:12} {state:42} {geo:6} STOP (quota exhausted: {err})", file=sys.stderr)
                    aborted = True
                    break
                # Quota remains -> this state simply has no Trends data (or a bad geo). Skip it.
                empty.append((did, state))
                print(f"  {did:12} {state:42} {geo:6} EMPTY (no results / unsupported geo)")
            except Exception as err:
                errored.append((did, state, str(err)))
                print(f"  {did:12} {state:42} {geo:6} FAIL ({err})", file=sys.stderr)
            time.sleep(sleep_s)
        if by_state:
            out_diseases[did] = {"query": query, "by_state": by_state}
        if aborted:
            break

    print("-" * 72)
    if not out_diseases:
        # Fail-loud: nothing came back -> do NOT write, so any prior file stays intact.
        print("No series returned for any disease/state; leaving any existing file untouched.", file=sys.stderr)
        for did, state, msg in errored:
            print(f"   - {did} / {state}: {msg}", file=sys.stderr)
        return 1

    # Carry-forward merge over an existing file: keep prior per-state series for any disease/state we did not
    # (re)fetch this run, overlay this run's results. Makes a partial / quota-stopped run resumable on re-run.
    prev = load_json_or(out_path, {}) or {}
    prev_diseases = prev.get("diseases") or {}
    merged: dict = {}
    all_dids = set(prev_diseases) | set(out_diseases)
    for did in all_dids:
        cur = out_diseases.get(did)
        old = prev_diseases.get(did)
        if cur and old:
            states = dict(old.get("by_state") or {})
            states.update(cur.get("by_state") or {})  # this run's states win
            merged[did] = {"query": cur.get("query") or old.get("query"), "by_state": states}
        else:
            merged[did] = cur or old

    payload = {
        "generated_at": now,
        "date_range": date_range,
        "diseases": merged,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    write_json_atomic(out_path, payload, indent=None)  # minified, atomic

    n_states = sum(len(v.get("by_state") or {}) for v in merged.values())
    print(f"Wrote {out_path}")
    print(f"calls made: {calls_made}  |  diseases: {len(merged)}  |  total state-series: {n_states}")
    if empty:
        print(f"empty series: {len(empty)} -> " + ", ".join(f"{a}/{b}" for a, b in empty))
    if errored:
        print(f"errored: {len(errored)}")
    if aborted:
        print("NOTE: run stopped early (all usable keys exhausted). Re-run to resume; carry-forward keeps progress.")
        return 1
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    cfg_dir = os.path.join(ROOT, "config")
    diseases = load_json(os.path.join(cfg_dir, "diseases.json"))["diseases"]
    signals_cfg = load_json(os.path.join(cfg_dir, "signals.json"))
    serp_cfg = (signals_cfg.get("trends") or {}).get("serpapi", {})
    terms = serp_cfg.get("terms", {})
    geo_map = load_json(os.path.join(cfg_dir, "in_state_geo.json"))["geo"]
    out_path = os.path.join(ROOT, "data", "backfill", "trends_history.json")

    keys = load_keys_from_envfile(os.path.join(ROOT, "apify.env"))
    if not keys:
        print("No SERPAPI keys found in apify.env; aborting.", file=sys.stderr)
        return 1
    provider = SerpApiTrendsProvider(serp_cfg, keys=keys)
    return pull_history(provider, diseases, terms, geo_map, DATE_RANGE, out_path)


if __name__ == "__main__":
    raise SystemExit(main())
