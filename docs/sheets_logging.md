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
- **`raw_data`** - one row per city x disease (the end-of-monsoon dataset). The project POSTs only the
  **raw inputs** (`date, run_id, city, state, disease, weather, trends, positivity, news_spike`); the
  script then writes **`score`, `band`, `mode` as in-sheet FORMULAS** over those inputs, so each cell
  shows *how* the score is derived (not a hard-coded number) and recomputes if you tweak an input.
  The formulas mirror `config/consolidation.json`:
  - confirmed (positivity present): `score = ROUND(MIN(100, (0.30*weather + 0.22*trends + 0.48*positivity) * (1.08 if max-min < 22 else 0.96)))`
  - forecast (positivity blank): `score = ROUND(MIN(69, 0.60*weather + 0.40*trends))`
- **`daily_summary`** - date- and city-level scores, all **by formula** (auto-update as `raw_data` grows):
  avg disease score by `date x disease`; a daily `avg / peak / cells`; and the **city overall blend**
  per `date x city` = `0.75*peak + 0.25*avg` (= `0.8*top + 0.2*mean-of-rest` for 5 diseases). Pure
  in-sheet formulas - edit/extend freely.

> **Applying the formulas to an existing sheet:** if `raw_data`/`daily_summary` already exist (with
> hard-coded scores from the earlier version), **delete those two tabs**, paste the updated `Code.gs`,
> re-deploy a **new version**, then re-run (`gh workflow run daily.yml`). The script recreates both tabs
> with the formula columns. Older rows that were hard-coded stay as-is unless you delete the tab.

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
  // raw_data: cols A-I (the raw inputs) are POSTed; J score / K band / L mode are FORMULAS the
  // script writes per row, mirroring config/consolidation.json (FW-ENSEMBLE-0.1.0).
  raw_data: ['date','run_id','city','state','disease','weather','trends','positivity','news_spike','score','band','mode'],
};

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (TOKEN && body.token !== TOKEN) return _out({ ok: false, error: 'bad token' });
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const sh = _ensure(ss, body.sheet);
    const rows = body.rows || [];
    if (rows.length) {
      const start = sh.getLastRow() + 1;
      sh.getRange(start, 1, rows.length, rows[0].length).setValues(rows);
      if (body.sheet === 'raw_data') _setRawFormulas(sh, start, rows.length);
    }
    _ensureSummary(ss);
    return _out({ ok: true, sheet: body.sheet, appended: rows.length });
  } catch (err) {
    return _out({ ok: false, error: String(err) });
  }
}

// score / band / mode as FORMULAS over the raw inputs (F=weather, G=trends, H=positivity),
// mirroring config/consolidation.json: with positivity -> 0.30*w + 0.22*t + 0.48*p, x1.08 if the
// three agree within 22 else x0.96; without positivity (H blank) -> 0.60*w + 0.40*t, capped at 69.
function _setRawFormulas(sh, start, n) {
  const fj = [], fk = [], fl = [];
  for (let i = 0; i < n; i++) {
    const r = start + i;
    fj.push(['=IF(H' + r + '="",ROUND(MIN(69,0.6*F' + r + '+0.4*G' + r + ')),' +
      'ROUND(MIN(100,(0.3*F' + r + '+0.22*G' + r + '+0.48*H' + r + ')*' +
      'IF(MAX(F' + r + ':H' + r + ')-MIN(F' + r + ':H' + r + ')<22,1.08,0.96))))']);
    fk.push(['=IFS(J' + r + '>=70,"HIGH",J' + r + '>=45,"MODERATE",J' + r + '>=25,"LOW-MODERATE",TRUE,"LOW")']);
    fl.push(['=IF(H' + r + '="","forecast","confirmed")']);
  }
  sh.getRange(start, 10, n, 1).setFormulas(fj);  // J score
  sh.getRange(start, 11, n, 1).setFormulas(fk);  // K band
  sh.getRange(start, 12, n, 1).setFormulas(fl);  // L mode
}

function _ensure(ss, name) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    if (HEADERS[name]) { sh.appendRow(HEADERS[name]); sh.setFrozenRows(1); }
  }
  return sh;
}

// daily_summary: date- and city-level scores, all by in-sheet formula (recompute as raw_data grows).
function _ensureSummary(ss) {
  if (ss.getSheetByName('daily_summary')) return;
  const sh = ss.insertSheet('daily_summary');
  sh.getRange('A1').setValue('Avg disease score by date x disease').setFontWeight('bold');
  sh.getRange('A2').setFormula(
    "=QUERY(raw_data!A2:L, \"select A, avg(J) where A is not null group by A pivot E order by A desc label A 'Date'\", 0)");
  sh.getRange('I1').setValue('Daily overall: avg / peak / cells').setFontWeight('bold');
  sh.getRange('I2').setFormula(
    "=QUERY(raw_data!A2:L, \"select A, avg(J), max(J), count(J) where A is not null group by A order by A desc label A 'Date', avg(J) 'Avg', max(J) 'Peak', count(J) 'Cells'\", 0)");
  // City overall (blend) per date x city = 0.75*peak + 0.25*avg  (== 0.8*top + 0.2*mean-of-rest for 5 diseases).
  sh.getRange('N1').setValue('City overall blend by date x city').setFontWeight('bold');
  sh.getRange('N2').setFormula(
    "=QUERY(raw_data!A2:L, \"select A, C, max(J), avg(J) where A is not null group by A, C order by A desc, C label A 'Date', C 'City', max(J) 'Peak', avg(J) 'Avg'\", 0)");
  sh.getRange('R2').setValue('Overall').setFontWeight('bold');
  sh.getRange('R3').setFormula("=ARRAYFORMULA(IF(P3:P=\"\",\"\",ROUND(0.75*P3:P+0.25*Q3:Q)))");
}

function _out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
```

## How the project writes to it

`.github/workflows/daily.yml` passes `SHEETS_WEBHOOK_URL` + `SHEETS_TOKEN` as env and, after each
step, runs `python src/sheetlog.py log <step> <outcome> <detail>`; after the grid build it runs
`python src/sheetlog.py raw data/grid.json` to push the day's ~1,140 city x disease rows (chunked) -
the **raw inputs only** (cols A-I); the Apps Script fills `score`/`band`/`mode` (J-L) by formula.
`src/sheetlog.py` is stdlib-only and a silent no-op when `SHEETS_WEBHOOK_URL` is unset.
