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
  raw_data: date, run_id, city, state, disease, weather, trends, positivity,
            news_spike, score, band, mode

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


def _post(sheet: str, rows: list) -> bool:
    if not URL or not rows:
        return False
    body = json.dumps({"token": TOKEN, "sheet": sheet, "rows": rows}).encode("utf-8")
    try:
        req = urllib.request.Request(
            URL, data=body, method="POST",
            headers={"Content-Type": "text/plain;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        return True
    except Exception as e:  # logging is best-effort; never fail the build
        print("sheetlog: POST to %s failed: %s" % (sheet, e), file=sys.stderr)
        return False


def log(step: str, status: str, detail: str = "") -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _post("run_log", [[ts, RUN_ID, TRIGGER, step, status, str(detail)]])


def push_raw(grid: dict) -> int:
    date = (grid.get("generated_at") or "")[:10]
    labels = {d["id"]: d["label"] for d in grid.get("diseases", [])}
    by_city = {c["id"]: c for c in grid.get("cities", [])}
    rows = []
    for r in grid.get("grid", []):
        c = by_city.get(r["city"], {})
        s = r.get("signals", {})
        rows.append([
            date, RUN_ID, c.get("name", r["city"]), c.get("state", ""),
            labels.get(r["disease"], r["disease"]),
            s.get("weather"), s.get("trends"), s.get("positivity"), s.get("news_spike"),
            r.get("score"), r.get("band"), r.get("mode"),
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
