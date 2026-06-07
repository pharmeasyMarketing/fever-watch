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
- **`raw_data`** - one row per city x disease, plus one **`disease="OVERALL"`** row per city (the
  headline blend). The project POSTs the full set of **raw inputs** (cols **A-S**):
  `date, run_id, city, state, disease, family, temp_c, humidity_pct, rain_7d_mm, rain_14d_mm,
  weather_score, trends_score, trends_keywords, news_spike, positivity, w_weather, w_trends,
  w_positivity, confidence`. The script then writes **`score`, `band`, `mode` (cols T-V) as in-sheet
  FORMULAS** over those inputs, so each cell shows *how* the score is derived (not a hard-coded
  number) and recomputes if you tweak an input. The disease-row formulas mirror
  `config/consolidation.json`, using the per-row weights (`w_weather` K, etc.) over the signal
  sub-scores (`weather_score` K, `trends_score` L, `positivity` O):
  - confirmed (positivity present): `score = ROUND(MIN(100, ((w_weather/100)*weather_score + (w_trends/100)*trends_score + (w_positivity/100)*positivity) * (1.08 if max-min < 22 else 0.96)))`
  - forecast (positivity blank): `score = ROUND(MIN(69, (w_weather/100)*weather_score + (w_trends/100)*trends_score))`
  - **OVERALL** row: `score = ROUND(0.8*top + 0.2*mean-of-rest)` over that run's disease rows for the city.
  Note: `temp_c / humidity_pct / rain_*` are the raw weather **inputs** to the per-family weather model
  (`src/weather_score.py` / `config/scoring.json`); `weather_score` is that model's output (logged as a
  value, not re-derived in-sheet). `trends_score` is the single Google Trends interest value for the
  OR-joined `trends_keywords`. When the real lab feed is wired, `tests_booked / positives` can be added
  ahead of `positivity` (they are not in `grid.json` today).
- **`daily_summary`** - date- and city-level scores, all **by formula** (auto-update as `raw_data` grows):
  avg disease score by `date x disease` (excludes OVERALL rows); a daily `avg / peak / cells`; and the
  **city headline blend** per `date x city`, read straight from the `OVERALL` rows (now exact, not the
  old `0.75*peak + 0.25*avg` approximation). Pure in-sheet formulas - edit/extend freely.

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
  // raw_data: cols A-S (the raw inputs) are POSTed; T score / U band / V mode are FORMULAS the
  // script writes per row, mirroring config/consolidation.json (FW-ENSEMBLE-0.1.0). Each city also
  // gets one disease="OVERALL" row whose score formula is the headline blend over its disease rows.
  raw_data: ['date','run_id','city','state','disease','family','temp_c','humidity_pct','rain_7d_mm','rain_14d_mm','weather_score','trends_score','trends_keywords','news_spike','positivity','w_weather','w_trends','w_positivity','confidence','score','band','mode'],
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
      if (body.sheet === 'raw_data') _setRawFormulas(sh, start, rows.length, rows);
    }
    _ensureSummary(ss);
    return _out({ ok: true, sheet: body.sheet, appended: rows.length });
  } catch (err) {
    return _out({ ok: false, error: String(err) });
  }
}

// score / band / mode as FORMULAS (cols T/U/V), mirroring config/consolidation.json.
// Disease rows: ensemble over the per-row weights (P w_weather, Q w_trends, R w_positivity) and the
// signal sub-scores (K weather_score, L trends_score, O positivity): with positivity -> weighted
// blend x1.08 if the three agree within 22 else x0.96; without positivity (O blank) -> weather+trends
// only, capped at 69. OVERALL rows (disease="OVERALL"): the city headline blend = 0.8*top +
// 0.2*mean-of-rest over that run's disease rows for the city (matched on run_id B + city C).
function _setRawFormulas(sh, start, n, rows) {
  const fT = [], fU = [], fV = [];
  for (let i = 0; i < n; i++) {
    const r = start + i;
    if (rows[i][4] === 'OVERALL') {
      const sel = '$T:$T,$B:$B,$B' + r + ',$C:$C,$C' + r + ',$E:$E,"<>OVERALL"';
      const mx = 'MAXIFS(' + sel + ')';
      const sm = 'SUMIFS(' + sel + ')';
      const ct = 'COUNTIFS($B:$B,$B' + r + ',$C:$C,$C' + r + ',$E:$E,"<>OVERALL")';
      fT.push(['=IFERROR(ROUND(0.8*' + mx + '+0.2*(' + sm + '-' + mx + ')/(' + ct + '-1)),ROUND(' + mx + '))']);
      fV.push(['="blend"']);
    } else {
      fT.push(['=IF($O' + r + '="",ROUND(MIN(69,($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r + ')),' +
        'ROUND(MIN(100,(($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r + '+($R' + r + '/100)*$O' + r + ')*' +
        'IF(MAX($K' + r + ',$L' + r + ',$O' + r + ')-MIN($K' + r + ',$L' + r + ',$O' + r + ')<22,1.08,0.96))))']);
      fV.push(['=IF($O' + r + '="","forecast","confirmed")']);
    }
    fU.push(['=IFS($T' + r + '>=70,"HIGH",$T' + r + '>=45,"MODERATE",$T' + r + '>=25,"LOW-MODERATE",TRUE,"LOW")']);
  }
  sh.getRange(start, 20, n, 1).setFormulas(fT);  // T score
  sh.getRange(start, 21, n, 1).setFormulas(fU);  // U band
  sh.getRange(start, 22, n, 1).setFormulas(fV);  // V mode
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
// Score is now col T; disease aggregates exclude the OVERALL rows; the city headline reads the
// OVERALL rows directly (exact blend, not the old 0.75*peak + 0.25*avg approximation).
function _ensureSummary(ss) {
  if (ss.getSheetByName('daily_summary')) return;
  const sh = ss.insertSheet('daily_summary');
  sh.getRange('A1').setValue('Avg disease score by date x disease').setFontWeight('bold');
  sh.getRange('A2').setFormula(
    "=QUERY(raw_data!A2:V, \"select A, avg(T) where A is not null and E <> 'OVERALL' group by A pivot E order by A desc label A 'Date'\", 0)");
  sh.getRange('I1').setValue('Daily overall: avg / peak / cells (disease rows)').setFontWeight('bold');
  sh.getRange('I2').setFormula(
    "=QUERY(raw_data!A2:V, \"select A, avg(T), max(T), count(T) where A is not null and E <> 'OVERALL' group by A order by A desc label A 'Date', avg(T) 'Avg', max(T) 'Peak', count(T) 'Cells'\", 0)");
  sh.getRange('N1').setValue('City headline blend by date x city (OVERALL rows)').setFontWeight('bold');
  sh.getRange('N2').setFormula(
    "=QUERY(raw_data!A2:V, \"select A, C, avg(T) where E = 'OVERALL' group by A, C order by A desc, C label A 'Date', C 'City', avg(T) 'Overall'\", 0)");
}

function _out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
```

## How the project writes to it

`.github/workflows/daily.yml` passes `SHEETS_WEBHOOK_URL` + `SHEETS_TOKEN` as env and, after each
step, runs `python src/sheetlog.py log <step> <outcome> <detail>`; after the grid build it runs
`python src/sheetlog.py raw data/grid.json` to push the day's ~1,368 rows (228 cities x [5 diseases +
1 OVERALL], chunked) - the **raw inputs only** (cols A-S); the Apps Script fills `score`/`band`/`mode`
(T-V) by formula. `src/sheetlog.py` is stdlib-only and a silent no-op when `SHEETS_WEBHOOK_URL` is unset.
