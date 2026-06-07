# Google Sheets logging (run logs + raw data)

The daily build logs to a Google Sheet via a **Google Apps Script Web App webhook** -
no GCP, no service-account keys, no extra Python deps. The project's only "access" to
the sheet is a **webhook URL** kept in a GitHub Actions secret; `src/sheetlog.py` POSTs
to it with the standard library. Logging is best-effort: if the secret is unset or the
POST fails, the build is unaffected.

Sheet (logs): https://docs.google.com/spreadsheets/d/1Iz9nAf38PB1UnQr8wR7umuMId4lp9RQuaaJ3HBKcjgc/edit
The Apps Script targets this sheet **by ID** (`openById`), so it writes here whether the script is
container-bound or standalone - change `SHEET_ID` below to retarget.

## Tabs (auto-created by the script)

- **`run_log`** - one row per pipeline step, every run:
  `timestamp, run_id, trigger, step, status, detail`
  steps: `weather, trends, grid, site` (status `success`/`failure`/`skipped`).
- **`raw_data`** - the day's full grid, one row per city x disease (the end-of-monsoon dataset):
  `date, run_id, city, state, disease, weather, trends, positivity, news_spike, score, band, mode`
- **`daily_summary`** - date-level scores computed **by formula** (auto-updates as `raw_data` grows):
  a `QUERY` pivot of avg disease score by `date x disease`, plus a daily `avg / peak / cell-count`
  block. No project code writes here - it is pure in-sheet formulas, so you can edit/extend freely.

## One-time setup (~5 min)

1. Open the logs sheet -> **Extensions > Apps Script** (or a standalone project at script.google.com - the script
   targets the sheet by `SHEET_ID`, so the host doesn't matter).
2. Replace `Code.gs` with the script below; set `TOKEN` to any random string and confirm `SHEET_ID` is the logs sheet.
3. **Deploy > New deployment > type: Web app** -> *Execute as:* **Me** -> *Who has access:* **Anyone**
   -> **Deploy**, and authorise when prompted. (`Anyone` is required so the CI - which has no Google
   login - can POST; the `TOKEN` guards the endpoint and the app runs as you, writing to your sheet.)
4. Copy the **Web app URL**.
5. In GitHub: **repo > Settings > Secrets and variables > Actions > New repository secret**, add:
   - `SHEETS_WEBHOOK_URL` = the Web app URL
   - `SHEETS_TOKEN` = the same `TOKEN` string
6. Done. The next `daily.yml` run (scheduled or `gh workflow run daily.yml`) will populate `run_log`
   + `raw_data`, and `daily_summary` will compute date-level scores. (Re-deploy the Apps Script as a
   **new version** whenever you change `Code.gs`.)

> Keep the URL + token private - anyone with both can append rows. Rotate by editing `TOKEN` +
> re-deploying + updating the secret.

## Code.gs

```javascript
// Fever Watch -> Google Sheet logger. Set TOKEN + SHEET_ID, deploy as a Web App.
const TOKEN = 'CHANGE_ME';  // must equal the SHEETS_TOKEN Actions secret
const SHEET_ID = '1Iz9nAf38PB1UnQr8wR7umuMId4lp9RQuaaJ3HBKcjgc';  // the logs sheet (target by ID)

const HEADERS = {
  run_log:  ['timestamp','run_id','trigger','step','status','detail'],
  raw_data: ['date','run_id','city','state','disease','weather','trends','positivity','news_spike','score','band','mode'],
};

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (TOKEN && body.token !== TOKEN) return _out({ ok: false, error: 'bad token' });
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const sh = _ensure(ss, body.sheet);
    const rows = body.rows || [];
    if (rows.length) sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
    _ensureSummary(ss);
    return _out({ ok: true, sheet: body.sheet, appended: rows.length });
  } catch (err) {
    return _out({ ok: false, error: String(err) });
  }
}

function _ensure(ss, name) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    if (HEADERS[name]) { sh.appendRow(HEADERS[name]); sh.setFrozenRows(1); }
  }
  return sh;
}

// daily_summary: date-level scores by FORMULA, so they recompute as raw_data grows.
function _ensureSummary(ss) {
  if (ss.getSheetByName('daily_summary')) return;
  const sh = ss.insertSheet('daily_summary');
  sh.getRange('A1').setValue('Avg disease score by date x disease (formula over raw_data)').setFontWeight('bold');
  sh.getRange('A2').setFormula(
    "=QUERY(raw_data!A2:L, \"select A, avg(J) where A is not null group by A pivot E order by A desc label A 'Date'\", 0)");
  sh.getRange('I1').setValue('Daily overall: avg / peak / cells').setFontWeight('bold');
  sh.getRange('I2').setFormula(
    "=QUERY(raw_data!A2:L, \"select A, avg(J), max(J), count(J) where A is not null group by A order by A desc label A 'Date', avg(J) 'Avg', max(J) 'Peak', count(J) 'Cells'\", 0)");
}

function _out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
```

## How the project writes to it

`.github/workflows/daily.yml` passes `SHEETS_WEBHOOK_URL` + `SHEETS_TOKEN` as env and, after each
step, runs `python src/sheetlog.py log <step> <outcome> <detail>`; after the grid build it runs
`python src/sheetlog.py raw data/grid.json` to push the day's ~1,140 city x disease rows (chunked).
`src/sheetlog.py` is stdlib-only and a silent no-op when `SHEETS_WEBHOOK_URL` is unset.
