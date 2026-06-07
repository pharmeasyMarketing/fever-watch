#!/usr/bin/env python3
"""Best-effort logger -> Google Sheet via an Apps Script Web App webhook.

The daily build POSTs (a) one run-log row per pipeline step and (b) the day's full
city x disease grid as raw data, to a Google Apps Script Web App bound to the sheet.
No Google auth / no GCP / no third-party deps: the project's only "access" is the
webhook URL, kept in the SHEETS_WEBHOOK_URL Actions secret (optional SHEETS_TOKEN
shared secret guards the public endpoint). NEVER raises - logging must not break a
build - and is a silent no-op when SHEETS_WEBHOOK_URL is unset (e.g. local runs).

Payload (text/plain JSON, so the webhook is a CORS-simple request):
  {"token": <secret>, "sheet": "run_log"|"raw_data", "rows": [[...], ...]}

Columns the Apps Script expects:
  run_log : timestamp, run_id, trigger, step, status, detail
  raw_data: date, run_id, city, state, disease, family, temp_c, humidity_pct, rain_7d_mm,
            rain_14d_mm, weather_score, trends_score, trends_keywords, news_spike, positivity,
            w_weather, w_trends, w_positivity, confidence
            (INPUTS only, cols A-S; score/band/mode in cols T-V are in-sheet FORMULAS the
            Apps Script writes, mirroring config/consolidation.json. Each city also gets one
            disease="OVERALL" row whose score is the city headline blend by formula
            (0.8*top + 0.2*mean-of-rest). See docs/sheets_logging.md)

CLI (used by .github/workflows/daily.yml so build scripts stay untouched):
  python src/sheetlog.py log <step> <status> [detail]
  python src/sheetlog.py raw <path/to/grid.json>
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

URL = os.environ.get("SHEETS_WEBHOOK_URL", "").strip()
TOKEN = os.environ.get("SHEETS_TOKEN", "").strip()
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")
TRIGGER = os.environ.get("GITHUB_EVENT_NAME", "manual")
CHUNK = 400  # rows per POST (keeps each request modest for Apps Script)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _post(sheet: str, rows: list) -> bool:
    if not URL or not rows:
        return False
    body = json.dumps({"token": TOKEN, "sheet": sheet, "rows": rows}).encode("utf-8")
    try:
        req = urllib.request.Request(
            URL, data=body, method="POST",
            headers={"Content-Type": "text/plain;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            resp = r.read().decode("utf-8", "ignore")
        try:
            ok = json.loads(resp).get("ok", True)
        except Exception:
            ok = True  # non-JSON (e.g. an Apps Script wrapper) -> assume delivered
        if not ok:
            print("sheetlog: webhook returned not-ok for %s: %s" % (sheet, resp[:200]), file=sys.stderr)
            return False
        return True
    except Exception as e:  # logging is best-effort; never fail the build
        print("sheetlog: POST to %s failed: %s" % (sheet, e), file=sys.stderr)
        return False


def log(step: str, status: str, detail: str = "") -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _post("run_log", [[ts, RUN_ID, TRIGGER, step, status, str(detail)]])


def _load_terms() -> dict:
    """Per-disease Google Trends search terms (config/signals.json) for the
    trends_keywords column. Best-effort: {} if unavailable."""
    try:
        with open(os.path.join(ROOT, "config", "signals.json"), "r", encoding="utf-8") as fh:
            sj = json.load(fh)
        return (((sj.get("trends") or {}).get("serpapi") or {}).get("terms")) or {}
    except Exception:
        return {}


def push_raw(grid: dict) -> int:
    """Push the day's full city x disease grid as raw INPUT columns (A-S). The Apps
    Script derives score/band/mode (T-V) as in-sheet formulas. Per city we also append
    one disease='OVERALL' row whose score formula is the headline blend over that
    city's disease rows (0.8*top + 0.2*mean-of-rest)."""
    date = (grid.get("generated_at") or "")[:10]
    labels = {d["id"]: d["label"] for d in grid.get("diseases", [])}
    terms = _load_terms()
    cells_by_city: dict = {}
    for r in grid.get("grid", []):
        cells_by_city.setdefault(r["city"], []).append(r)

    rows = []
    for c in grid.get("cities", []):
        cid = c["id"]
        cells = cells_by_city.get(cid, [])
        if not cells:
            continue
        cw = c.get("weather") or {}
        temp, hum = cw.get("temp_mean_c"), cw.get("humidity_pct")
        r7, r14 = cw.get("rain_7d_mm"), cw.get("rain_14d_mm")
        for r in cells:
            s = r.get("signals", {})
            w = r.get("weights", {})
            kw = ", ".join(terms.get(r["disease"], [])) if terms else ""
            rows.append([
                date, RUN_ID, c.get("name", cid), c.get("state", ""),
                labels.get(r["disease"], r["disease"]), r.get("family", ""),
                temp, hum, r7, r14,
                s.get("weather"), s.get("trends"), kw, s.get("news_spike"), s.get("positivity"),
                w.get("weather"), w.get("trends"), w.get("positivity"),
                r.get("confidence", ""),
            ])  # A-S inputs; T-V (score/band/mode) are formulas the Apps Script writes
        # One city-overall line item: the headline blend, score derived by formula.
        rows.append([
            date, RUN_ID, c.get("name", cid), c.get("state", ""),
            "OVERALL", "city-blend", temp, hum, r7, r14,
            "", "", "", "", "", "", "", "", "",
        ])

    sent = 0
    for i in range(0, len(rows), CHUNK):
        if _post("raw_data", rows[i:i + CHUNK]):
            sent += len(rows[i:i + CHUNK])
    return sent


def main(argv: list) -> int:
    if not argv:
        print("usage: sheetlog.py log <step> <status> [detail] | raw <grid.json>", file=sys.stderr)
        return 0
    if not URL:
        print("sheetlog: SHEETS_WEBHOOK_URL unset; skipping.")
        return 0
    if argv[0] == "log" and len(argv) >= 3:
        log(argv[1], argv[2], argv[3] if len(argv) > 3 else "")
    elif argv[0] == "raw" and len(argv) >= 2:
        with open(argv[1], "r", encoding="utf-8") as fh:
            n = push_raw(json.load(fh))
        print("sheetlog: pushed %d raw rows" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
