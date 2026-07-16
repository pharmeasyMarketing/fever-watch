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
  `timestamp, run_id, trigger, step, status, detail, reason`
  steps: `weather, trends, grid, site` (status `success`/`failure`/`skipped`/`cancelled`). **`reason`** is
  filled whenever a step does not succeed - e.g. a concurrency cancel (a concurrent deploy), a SerpApi
  failure, or a carry-forward - so a cancelled/skipped row explains itself instead of being blank.
- **`raw_data`** - one row per city x disease, plus one **`disease="OVERALL"`** row per city (the
  headline blend). The project POSTs the **raw inputs** (G-J weather, M-O trends/positivity, P-R weights,
  W-Z `trends_state_interest` + freshness); **`weather_score` (K), `trends_score` (L), `confidence` (S)
  and `score`/`band`/`mode` (T-V) are in-sheet FORMULAS** the script writes - the full BUILD-UP, so every
  derived cell shows *how* it is computed (and recomputes if you tweak an input):
  - `weather_score` (K): per-family environmental score from temp/humidity/rain, e.g. mosquito =
    `(0.45*tempfit + 0.35*rain14_unit + 0.20*humidity_unit)*100` (mirrors `config/scoring.json`).
  - `trends_score` (L) = `MAX(4, MIN(100, trends_state_interest))` - the state Google Trends index, floored.
  - `score` (T): ensemble over the weights (P/Q/R) and sub-scores (K/L/O), mirroring
    `config/consolidation.json`; OVERALL = `ROUND(0.8*top + 0.2*mean-of-rest)` over that city's disease rows.
  - `confidence` (S) downgrades one step (High->Moderate, Moderate->Low) when the cell is `stale` (Z) -
    i.e. it used a carried-forward reading.
  - **Labs build-up (live):** only `tests_booked` (AB) + `positives` (AC) are POSTed (the raw window-summed
    lab inputs, from the gitignored sidecar `data/positivity_detail.json` build_daily writes). Everything
    else is a FORMULA: `positivity_pct` (AD) = `positives/tests_booked*100`; the positivity signal (O) =
    `MIN(100, ROUND(positivity_pct/ref*100))`, gated to blank when `tests_booked < 30` (forecast-only).
    `ref` is PER DISEASE (each fever has a different realistic 'high'): dengue 25, malaria 4, chikungunya 15,
    typhoid 45 (else 35), looked up in-cell from the disease in column E.
    So the WHOLE chain is in-cell: tests_booked, positives -> positivity_pct -> positivity (O) -> score (T).
    AB/AC/AD are appended at the END so the existing A-AA letters never shift; O is an existing column (15)
    now written as a formula instead of a posted value.
- **`daily_summary`** - date- and city-level scores, all **by formula** (auto-update as `raw_data` grows):
  avg disease score by `date x disease` (excludes OVERALL rows); a daily `avg / peak / cells`; and the
  **city headline blend** per `date x city`, read straight from the `OVERALL` rows (now exact, not the
  old `0.75*peak + 0.25*avg` approximation). Pure in-sheet formulas - edit/extend freely.

> **Applying the new columns/formulas to your existing sheet:** the column set changed again - `raw_data`
> gained `tests_booked` (AB), `positives` (AC) and the `positivity_pct` (AD) build-up formula (the live
> labs chain). So: paste the updated `Code.gs`, re-deploy a **new version**, then **delete the `raw_data`
> + `daily_summary` tabs** (the script recreates them with the new columns + formulas on the next run).
> Then re-run `gh workflow run daily.yml` (or wait for the scheduled cron). No secret changes are needed -
> the labs values flow through the existing `raw_data` push.

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
  run_log:  ['timestamp','run_id','trigger','step','status','detail','reason'],
  // raw_data: the POSTed cells are the raw inputs (G-J weather, M-O trends/positivity, P-R weights,
  // W-Z trends_state_interest + freshness, AA weather_source provenance). weather_score (K), trends_score (L), confidence (S) and
  // score/band/mode (T-V) are FORMULAS the script writes per row - the full BUILD-UP, so each derived
  // cell shows HOW it is computed (mirrors config/scoring.json + config/consolidation.json). Each city
  // also gets one disease="OVERALL" row whose score formula is the headline blend over its disease rows.
  // AE/AF (push_image_url_prod, push_image_url_staging) = the per-city Android push-notification card URLs
  // (?v= cache-bust), posted as literal values, repeated on every row of the city.
  // AG/AH (city_url_prod, city_url_staging) = the per-city page URLs (prod + staging origins, base + city + "/",
  // matching the page canonical), posted as literal values, repeated on every row of the city.
  raw_data: ['date','run_id','city','state','disease','family','temp_c','humidity_pct','rain_7d_mm','rain_14d_mm','weather_score','trends_score','trends_keywords','news_spike','positivity','w_weather','w_trends','w_positivity','confidence','score','band','mode','trends_state_interest','weather_fresh','trends_fresh','stale','weather_source','tests_booked','positives','positivity_pct','push_image_url_prod','push_image_url_staging','city_url_prod','city_url_staging'],
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
    _ensureDictionary(ss);
    return _out({ ok: true, sheet: body.sheet, appended: rows.length });
  } catch (err) {
    return _out({ ok: false, error: String(err) });
  }
}

// weather_score (K), trends_score (L), confidence (S), score (T), band (U), mode (V) are all FORMULAS -
// the full build-up - mirroring config/scoring.json + config/consolidation.json:
//  - weather_score (K): per-family environmental score from temp_c (G), humidity (H), rain_7d (I),
//    rain_14d (J). mosquito = (0.45*tempfit + 0.35*rain14_unit + 0.20*humidity_unit)*100; waterborne =
//    (0.6*rain7_unit + 0.4*rain14_unit)*100. tempfit = unimodal response peaking at 29C, 0 outside
//    14-38C; *_unit = saturating ramps (rain/saturation, humidity over its 40-90 band).
//  - trends_score (L) = MAX(4, MIN(100, trends_state_interest W)) - the state Google Trends index, floored.
//  - confidence (S): Forecast-only if no positivity; else High if the 3 signals agree (spread<22) else
//    Moderate; downgraded one step (High->Moderate, Moderate->Low) when the cell is STALE (Z=TRUE).
//  - score (T): ensemble over the weights (P/Q/R) and sub-scores (K/L/O). OVERALL rows: 0.8*top +
//    0.2*mean-of-rest over that run's disease rows for the city (matched on run_id B + city C).
function _setRawFormulas(sh, start, n, rows) {
  const fK = [], fL = [], fS = [], fT = [], fU = [], fV = [], fAD = [], fO = [];
  for (let i = 0; i < n; i++) {
    const r = start + i;
    if (rows[i][4] === 'OVERALL') {
      const sel = '$T:$T,$B:$B,$B' + r + ',$C:$C,$C' + r + ',$E:$E,"<>OVERALL"';
      const mx = 'MAXIFS(' + sel + ')';
      const sm = 'SUMIFS(' + sel + ')';
      const ct = 'COUNTIFS($B:$B,$B' + r + ',$C:$C,$C' + r + ',$E:$E,"<>OVERALL")';
      fK.push(['=""']); fL.push(['=""']); fS.push(['=""']);  // no per-signal sub-scores on the blend row
      fT.push(['=IFERROR(ROUND(0.8*' + mx + '+0.2*(' + sm + '-' + mx + ')/(' + ct + '-1)),ROUND(' + mx + '))']);
      fV.push(['="blend"']); fAD.push(['=""']); fO.push(['=""']);
    } else {
      // weather_score (K): family-weighted build-up over G temp_c / H humidity / I rain_7d / J rain_14d.
      fK.push(['=IF($F' + r + '="mosquito",ROUND((0.45*IF(OR($G' + r + '<=14,$G' + r + '>=38),0,MAX(0,MIN(1,1-(($G' + r + '-29)/13)^2)))+0.35*MAX(0,MIN(1,$J' + r + '/60))+0.20*MAX(0,MIN(1,($H' + r + '-40)/50)))*100),IF($F' + r + '="waterborne",ROUND((0.6*MAX(0,MIN(1,$I' + r + '/80))+0.4*MAX(0,MIN(1,$J' + r + '/80)))*100),""))']);
      // trends_score (L): the state Google Trends interest W, floored at 4 and capped at 100.
      fL.push(['=IF($W' + r + '="","",MAX(4,MIN(100,$W' + r + ')))']);
      // confidence (S): base label, then a one-step downgrade if the cell is STALE (Z=TRUE).
      const base = 'IF($O' + r + '="","Forecast only",IF(MAX($K' + r + ',$L' + r + ',$O' + r + ')-MIN($K' + r + ',$L' + r + ',$O' + r + ')<22,"High","Moderate"))';
      fS.push(['=IF($Z' + r + '=TRUE,IFS(' + base + '="High","Moderate",' + base + '="Moderate","Low",TRUE,' + base + '),' + base + ')']);
      // score (T) forecast branch = SOFT-KNEE taper of the weather+search blend (mirror of
      // src/consolidate.py _soft_knee): <=55 pass-through, else 55+(blend-55)*14/45 into [55,69], so a
      // no-lab read approaches but never reaches the HIGH floor of 70. FB is wrapped so <= is unambiguous.
      const fb = '(($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r + ')';
      fT.push(['=IF($O' + r + '="",ROUND(IF(' + fb + '<=55,' + fb + ',55+(' + fb + '-55)*14/45)),' +
        'ROUND(MIN(100,(($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r + '+($R' + r + '/100)*$O' + r + ')*' +
        'IF(MAX($K' + r + ',$L' + r + ',$O' + r + ')-MIN($K' + r + ',$L' + r + ',$O' + r + ')<22,1.08,0.96))))']);
      fV.push(['=IF($O' + r + '="","forecast","confirmed")']);
      // AD positivity_pct: the raw labs build-up = positives(AC)/tests_booked(AB)*100. The
      // positivity signal (O) = MIN(100, ROUND(positivity_pct/ref*100)) and is blank (forecast-only)
      // when tests_booked < 30. So the full chain is AB,AC -> AD -> O -> T (score).
      fAD.push(['=IF(OR($AB' + r + '="",$AB' + r + '=0),"",ROUND($AC' + r + '/$AB' + r + '*100,1))']);
      // O positivity (the lab signal) = MIN(100, ROUND(positivity_pct/ref*100)), gated to "" below 30
      // tests_booked (forecast-only) - mirrors src/signals/gsheet_api._signal. ref is PER DISEASE (each
      // fever has a different realistic 'high'): dengue 25, malaria 4, chikungunya 15, typhoid 45 (else 35),
      // looked up from the disease label in column E. So the whole lab build-up tests_booked(AB) ->
      // positives(AC) -> positivity_pct(AD) -> positivity(O) -> score(T) is visible in-cell.
      const ref = 'IFS($E' + r + '="Dengue",25,$E' + r + '="Malaria",4,$E' + r + '="Chikungunya",15,$E' + r + '="Typhoid",45,TRUE,35)';
      fO.push(['=IF(OR($AB' + r + '="",$AB' + r + '<30),"",MIN(100,ROUND($AD' + r + '/' + ref + '*100)))']);
    }
    fU.push(['=IFS($T' + r + '>=70,"HIGH",$T' + r + '>=45,"MODERATE",$T' + r + '>=25,"LOW-MODERATE",TRUE,"LOW")']);
  }
  sh.getRange(start, 11, n, 1).setFormulas(fK);  // K weather_score (build-up)
  sh.getRange(start, 12, n, 1).setFormulas(fL);  // L trends_score
  sh.getRange(start, 19, n, 1).setFormulas(fS);  // S confidence
  sh.getRange(start, 20, n, 1).setFormulas(fT);  // T score
  sh.getRange(start, 21, n, 1).setFormulas(fU);  // U band
  sh.getRange(start, 22, n, 1).setFormulas(fV);  // V mode
  sh.getRange(start, 15, n, 1).setFormulas(fO);  // O positivity (gated build-up from AB/AC/AD)
  sh.getRange(start, 30, n, 1).setFormulas(fAD); // AD positivity_pct (raw labs build-up)
}

function _ensure(ss, name) {
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  // Self-heal headers: write them when the sheet is new OR was cleared (no rows), so clearing
  // the cells (instead of deleting the whole tab) still ends up with a proper header row.
  if (HEADERS[name] && sh.getLastRow() === 0) { sh.appendRow(HEADERS[name]); sh.setFrozenRows(1); }
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

// data_dictionary: a one-time legend tab describing every raw_data column + how it is derived.
const DICT = [
  ['Column', 'What it is / how it is derived'],
  ['date', 'UTC date of the run (grid generated_at).'],
  ['run_id', 'GitHub Actions run id; groups one pipeline run.'],
  ['city', 'City name.'],
  ['state', 'State / UT.'],
  ['disease', 'Disease label, or OVERALL for the city headline row.'],
  ['family', 'Weather model family: mosquito / waterborne / febrile (selects how weather is shaped).'],
  ['temp_c', 'Trailing mean air temperature (C), NASA POWER. Input to weather_score.'],
  ['humidity_pct', 'Trailing mean relative humidity (%), NASA POWER. Input to weather_score.'],
  ['rain_7d_mm', 'Rainfall over the last 7 days (mm), NOAA CPC (gauge-based, US public domain). Input to weather_score.'],
  ['rain_14d_mm', 'Rainfall over the last 14 days (mm), NOAA CPC (gauge-based, US public domain); the lagged breeding signal.'],
  ['weather_score', 'FORMULA (build-up): 0-100 breeding/transmission favourability, derived in-cell from temp_c/humidity_pct/rain_7d_mm/rain_14d_mm. mosquito = (0.45*tempfit + 0.35*rain14_unit + 0.20*humidity_unit)*100; waterborne = (0.6*rain7_unit + 0.4*rain14_unit)*100. tempfit = unimodal peak at 29C (0 outside 14-38C); *_unit = saturating ramps (config/scoring.json).'],
  ['trends_score', 'FORMULA: MAX(4, MIN(100, trends_state_interest)) - the state Google Trends index for trends_keywords, floored at 4 and capped at 100.'],
  ['trends_keywords', 'The search terms (OR-joined) whose combined interest is trends_score.'],
  ['news_spike', 'TRUE if national interest spiked recently (news-driven); trends is down-weighted in forecast mode when TRUE.'],
  ['positivity', 'FORMULA: 0-100 PharmEasy lab positivity (lagging ground truth) = MIN(100, ROUND(positivity_pct(AD)/ref*100)), gated to blank when tests_booked(AB) < 30 (forecast-only). ref is PER DISEASE (dengue 25, malaria 4, chikungunya 15, typhoid 45, else 35), looked up in-cell from the disease in column E. Derived in-cell from the raw labs columns, not posted.'],
  ['w_weather', 'Weight (%) on weather_score in the blend (30 confirmed / 60 forecast).'],
  ['w_trends', 'Weight (%) on trends_score (22 confirmed / 40 forecast).'],
  ['w_positivity', 'Weight (%) on positivity (48 confirmed / 0 forecast).'],
  ['confidence', 'FORMULA: Forecast only if no positivity; else High if the three signals agree (max-min < 22) else Moderate; downgraded one step (High->Moderate, Moderate->Low) when stale=TRUE.'],
  ['score', 'FORMULA. confirmed = (w_weather*weather + w_trends*trends + w_positivity*positivity) x1.08 if signals agree else x0.96. forecast = weather+trends only, soft-knee taper (<=55 unchanged, else 55+(blend-55)*14/45) held below 70. OVERALL = 0.8*top disease + 0.2*mean of the rest.'],
  ['band', 'FORMULA: HIGH >=70, MODERATE >=45, LOW-MODERATE >=25, LOW <25 (from score).'],
  ['mode', 'FORMULA: confirmed (positivity present) or forecast (capped, no positivity); OVERALL rows = blend.'],
  ['trends_state_interest', 'Raw Google Trends interest (0-100) for the city state (or the disease national mean if the state has no row), BEFORE the floor. trends_score = MAX(4, MIN(100, this)).'],
  ['weather_fresh', 'How fresh the weather data is: fresh (today) / carried Nd (1..stale_days old) / stale Nd (older). From weather.json generated_at.'],
  ['trends_fresh', 'How fresh this disease trends data is (build_trends carries forward the last-good per disease on a SerpApi failure): fresh / carried Nd / stale Nd / unknown.'],
  ['stale', 'TRUE if any signal is older than stale_days (config/consolidation.json) - the cell used a carried-forward reading and its confidence is downgraded one step.'],
  ['weather_source', 'Provenance of the weather inputs: rainfall from NOAA CPC (gauge-based, US public domain); temperature and humidity from NASA POWER.'],
  ['tests_booked', 'Aggregate lab tests for this city/disease over the trailing window (config window_days), live PharmEasy/ThyroCare feed via the Sheets API. Raw input to positivity; logged here only (never in the public site).'],
  ['positives', 'Aggregate positive results over the same window. positivity_pct = positives / tests_booked * 100.'],
  ['positivity_pct', 'FORMULA: positives(AC)/tests_booked(AB)*100. The positivity signal (O) = MIN(100, ROUND(positivity_pct/ref*100)) with a PER-DISEASE ref (dengue 25, malaria 4, chikungunya 15, typhoid 45, else 35), blank (forecast-only) when tests_booked < 30. Completes the build-up: tests_booked, positives -> positivity_pct -> positivity (O) -> score (T).'],
  ['push_image_url_prod', 'Per-city Android push-notification big-picture image URL on the production origin (pharmeasy.in/fever-watch/assets/img/push/<city>.jpg), with a ?v= daily cache-bust. Same value on every row of the city. Posted as a literal by sheetlog.py.'],
  ['push_image_url_staging', 'The same Android push image on the github.io staging origin (with the ?v= cache-bust). Posted as a literal by sheetlog.py.'],
  ['city_url_prod', 'Per-city page URL on the production origin (pharmeasy.in/fever-watch/<city>/), matching the page canonical. Same value on every row of the city. Posted as a literal by sheetlog.py.'],
  ['city_url_staging', 'The same city page URL on the github.io staging origin (pharmeasymarketing.github.io/fever-watch/<city>/). Posted as a literal by sheetlog.py.'],
];
function _ensureDictionary(ss) {
  if (ss.getSheetByName('data_dictionary')) return;
  const sh = ss.insertSheet('data_dictionary');
  sh.getRange(1, 1, DICT.length, 2).setValues(DICT);
  sh.setFrozenRows(1);
  sh.getRange('A1:B1').setFontWeight('bold');
  sh.setColumnWidth(1, 150);
  sh.setColumnWidth(2, 760);
}

function _out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
```

## How the project writes to it

`.github/workflows/daily.yml` passes `SHEETS_WEBHOOK_URL` + `SHEETS_TOKEN` as env and, after each
step, runs `python src/sheetlog.py log <step> <outcome> <detail>`; after the grid build it runs
`python src/sheetlog.py raw data/grid.json` to push the day's ~1,140 rows (228 cities x [4 diseases +
1 OVERALL], chunked) - the **raw inputs**; the Apps Script fills `weather_score`/`trends_score`/
`confidence` (K/L/S) + `score`/`band`/`mode` (T-V) by formula. `src/sheetlog.py` is stdlib-only and a
silent no-op when `SHEETS_WEBHOOK_URL` is unset.
