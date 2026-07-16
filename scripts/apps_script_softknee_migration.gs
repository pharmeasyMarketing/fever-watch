/**
 * ONE-OFF MIGRATION - rewrite historical raw_data `score` (T) formulas to the SOFT-KNEE taper.
 * ============================================================================================
 * Context: until 2026-07-16 the forecast (no-lab) score was a HARD CLIP, ROUND(MIN(69, blend)),
 * which piled 184/790 cells onto exactly 69. The engine (src/consolidate.py) now applies a
 * soft-knee taper: pass-through at or below 55, then compress [55,100] into [55,69]. The live
 * logger appends rows and writes formulas ONLY for the rows it just appended, so historical rows
 * keep the old clip frozen in their cells. This script rewrites them.
 *
 * WHAT IT TOUCHES (deliberately narrow):
 *   - Column T (score) ONLY, and ONLY on per-disease rows (column E != 'OVERALL').
 *   - It does NOT touch the OVERALL city-blend rows: their formula aggregates $T:$T via
 *     MAXIFS/SUMIFS over that city's disease rows, so they RECOMPUTE THEMSELVES once the
 *     disease rows change. (Blindly filling column T down would CORRUPT these rows.)
 *   - It does NOT touch band (U): that reads $T and follows automatically.
 *   - K/L/S/V (weather, trends, confidence, mode) are unaffected by the engine change.
 *
 * The new forecast branch mirrors src/consolidate.py _soft_knee and src/backfill_sheetlog.py
 * _f_score byte-for-byte:  ROUND(IF(FB<=55, FB, 55+(FB-55)*14/45))   [14 = 69-55, 45 = 100-55]
 * FB is parenthesised so the spreadsheet's <= precedence is unambiguous. The confirmed branch
 * (positivity present) is IDENTICAL to the old one - confirmed cells are untouched by design.
 *
 * INSTALL - this is an ADD-ON, it does NOT replace the logger:
 *   Open the SAME Apps Script project as the logger (the one with doPost/_setRawFormulas), then
 *   Files > "+" > Script, name it `softknee_migration`, delete the myFunction() stub, paste this
 *   whole file, Save. Do NOT edit or overwrite the logger file. Nothing here collides with it (all
 *   names are SK_/_sk-prefixed) and no re-Deploy is needed - these are run by hand, not by the webhook.
 *
 * HOW TO RUN (pick the function in the editor's dropdown, press Run):
 *   1. previewSoftKneeRewrite()   - DRY RUN. Writes nothing. Check the log, then:
 *   2. rewriteScoreFormulasSoftKnee()  - run repeatedly until the log says COMPLETE.
 *      It is chunked + resumable (cursor in ScriptProperties) to stay inside the 6-min limit.
 *   3. verifySoftKneeRewrite()    - sanity: forecast rows sitting on exactly 69 should be ~0.
 *   resetSoftKneeCursor() restarts from the top if you need to re-run.
 *   Afterwards this file can simply be deleted - it is one-off.
 *
 * SAFETY: take a copy of the sheet first (this rewrites in place and is not undoable at scale).
 * The ONLY write is setFormulas on column T, rows >= 2 - the header row (used by CRM automation),
 * the column count and the column order are never touched.
 */

var SK_SHEET = 'raw_data';
// Rows per execution slice. Each slice is only ~4 batched Range calls, so this comfortably clears a
// full season's sheet (~27k rows) in ONE run, well inside the 6-minute limit. Kept chunked + resumable
// anyway: if a run ever times out, the cursor is only advanced AFTER a successful write, so simply
// running the function again resumes safely (re-writing a row is idempotent - the formula is derived
// purely from the row number). Lower this if you ever do hit a timeout.
var SK_CHUNK = 30000;
var SK_COL_DISEASE = 5;     // E
var SK_COL_SCORE = 20;      // T
var SK_CURSOR_KEY = 'sk_cursor';

/** The soft-knee score formula for row r - byte-mirror of backfill_sheetlog.py _f_score(r). */
function _skScoreFormula(r) {
  var fb = '(($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r + ')';
  var forecast = 'ROUND(IF(' + fb + '<=55,' + fb + ',55+(' + fb + '-55)*14/45))';
  var confirmed = 'ROUND(MIN(100,(($P' + r + '/100)*$K' + r + '+($Q' + r + '/100)*$L' + r +
    '+($R' + r + '/100)*$O' + r + ')*' +
    'IF(MAX($K' + r + ',$L' + r + ',$O' + r + ')-MIN($K' + r + ',$L' + r + ',$O' + r + ')<22,1.08,0.96)))';
  return '=IF($O' + r + '="",' + forecast + ',' + confirmed + ')';
}

/**
 * Resolve the raw_data sheet the SAME way the logger does - by ID. The project may be STANDALONE
 * (script.google.com) rather than container-bound, where SpreadsheetApp.getActive() returns null;
 * and if it were bound to some OTHER spreadsheet, getActive() would target the wrong file. SHEET_ID
 * is the global the logger file already defines (all .gs files in a project share one scope), so we
 * always hit the same spreadsheet the logger writes to. getActive() is only a fallback.
 */
function _skSheet() {
  var ss = null;
  try {
    if (typeof SHEET_ID !== 'undefined' && SHEET_ID) ss = SpreadsheetApp.openById(SHEET_ID);
  } catch (e) {
    throw new Error('Could not open SHEET_ID (' + e.message + ') - is this script in the same project as the logger?');
  }
  if (!ss) ss = SpreadsheetApp.getActive();   // container-bound fallback
  if (!ss) throw new Error('No spreadsheet: SHEET_ID is undefined and the script is not bound to a sheet. ' +
                           'Paste this file into the SAME Apps Script project as the logger (which defines SHEET_ID).');
  Logger.log('target spreadsheet: %s', ss.getName());
  var sh = ss.getSheetByName(SK_SHEET);
  if (!sh) throw new Error('Sheet/tab not found: ' + SK_SHEET + ' (in "' + ss.getName() + '")');
  return sh;
}

/** DRY RUN: report scope + show a real before/after, and flag anything unexpected. Writes nothing. */
function previewSoftKneeRewrite() {
  var sh = _skSheet(), last = sh.getLastRow(), n = last - 1;
  if (n < 1) { Logger.log('No data rows.'); return; }
  var dis = sh.getRange(2, SK_COL_DISEASE, n, 1).getValues();
  var frm = sh.getRange(2, SK_COL_SCORE, n, 1).getFormulas();
  var nDisease = 0, nOverall = 0, nOldClip = 0, nAlready = 0, nOverallNoFormula = 0, sample = null;
  for (var i = 0; i < n; i++) {
    var isOverall = String(dis[i][0]).trim() === 'OVERALL';
    var f = frm[i][0] || '';
    if (isOverall) { nOverall++; if (f.charAt(0) !== '=') nOverallNoFormula++; continue; }
    nDisease++;
    if (f.indexOf('MIN(69') !== -1) { nOldClip++; if (!sample) sample = { row: i + 2, before: f, after: _skScoreFormula(i + 2) }; }
    else if (f.indexOf('14/45') !== -1) nAlready++;
  }
  Logger.log('--- DRY RUN (nothing written) ---');
  Logger.log('data rows: %s  (disease rows: %s, OVERALL rows: %s)', n, nDisease, nOverall);
  Logger.log('disease rows still on the OLD hard clip MIN(69,...): %s', nOldClip);
  Logger.log('disease rows already on the soft knee (14/45):       %s', nAlready);
  Logger.log('OVERALL rows WITHOUT a formula (expect 0):           %s', nOverallNoFormula);
  if (nOverallNoFormula > 0) Logger.log('WARNING: some OVERALL rows hold literals, not formulas - they are preserved as-is, but inspect them.');
  if (sample) {
    Logger.log('sample row %s\n  BEFORE: %s\n  AFTER : %s', sample.row, sample.before, sample.after);
  } else {
    Logger.log('No rows on the old clip - nothing to migrate.');
  }
  Logger.log('Chunks needed at %s rows/run: ~%s', SK_CHUNK, Math.ceil(n / SK_CHUNK));
}

/** The migration. Run repeatedly until COMPLETE. Chunked + resumable. */
function rewriteScoreFormulasSoftKnee() {
  var sh = _skSheet(), last = sh.getLastRow();
  var props = PropertiesService.getScriptProperties();
  var start = Number(props.getProperty(SK_CURSOR_KEY) || 2);   // row 1 = header
  // HARD GUARD: never let the write range reach row 1. The header row is consumed by CRM automation,
  // so clobbering it would break downstream systems. Also catches a NaN/garbage cursor property.
  if (!(start >= 2)) start = 2;
  if (start > last) { props.deleteProperty(SK_CURSOR_KEY); Logger.log('COMPLETE - nothing left to do.'); return; }

  var end = Math.min(start + SK_CHUNK - 1, last), n = end - start + 1;
  var dis = sh.getRange(start, SK_COL_DISEASE, n, 1).getValues();
  var curF = sh.getRange(start, SK_COL_SCORE, n, 1).getFormulas();
  var curV = sh.getRange(start, SK_COL_SCORE, n, 1).getValues();
  var out = [], rewritten = 0, preserved = 0;

  for (var i = 0; i < n; i++) {
    var r = start + i;
    if (String(dis[i][0]).trim() === 'OVERALL') {
      // Preserve the blend row EXACTLY: write its own formula back (a no-op). If it somehow holds a
      // literal rather than a formula, write the literal back so we never blank a cell.
      out.push([curF[i][0] ? curF[i][0] : curV[i][0]]);
      preserved++;
      continue;
    }
    out.push([_skScoreFormula(r)]);
    rewritten++;
  }
  sh.getRange(start, SK_COL_SCORE, n, 1).setFormulas(out);

  props.setProperty(SK_CURSOR_KEY, String(end + 1));
  Logger.log('rows %s-%s: %s disease rows rewritten, %s OVERALL rows preserved.', start, end, rewritten, preserved);
  if (end < last) Logger.log('NOT DONE - run rewriteScoreFormulasSoftKnee() again (next row %s of %s).', end + 1, last);
  else { props.deleteProperty(SK_CURSOR_KEY); Logger.log('COMPLETE - all %s rows processed. Now run verifySoftKneeRewrite().', last - 1); }
}

/** Sanity check after migrating: forecast rows (O blank) parked on exactly 69 should be ~0. */
function verifySoftKneeRewrite() {
  var sh = _skSheet(), last = sh.getLastRow(), n = last - 1;
  var dis = sh.getRange(2, SK_COL_DISEASE, n, 1).getValues();
  var pos = sh.getRange(2, 15, n, 1).getValues();            // O positivity ('' => forecast)
  var sc = sh.getRange(2, SK_COL_SCORE, n, 1).getValues();   // T evaluated
  var frm = sh.getRange(2, SK_COL_SCORE, n, 1).getFormulas();
  var fc = 0, fc69 = 0, fcMax = 0, oldLeft = 0, over69 = 0;
  for (var i = 0; i < n; i++) {
    if (String(dis[i][0]).trim() === 'OVERALL') continue;
    if ((frm[i][0] || '').indexOf('MIN(69') !== -1) oldLeft++;
    var isForecast = pos[i][0] === '' || pos[i][0] === null;
    var v = Number(sc[i][0]);
    if (!isForecast || isNaN(v)) continue;
    fc++;
    if (v === 69) fc69++;
    if (v > 69) over69++;
    if (v > fcMax) fcMax = v;
  }
  Logger.log('--- VERIFY ---');
  Logger.log('forecast disease rows: %s', fc);
  Logger.log('forecast rows at exactly 69 (expect ~0): %s', fc69);
  Logger.log('forecast rows ABOVE 69 (MUST be 0 - no-lab can never reach HIGH): %s', over69);
  Logger.log('forecast max score (expect <= 69, typically 68): %s', fcMax);
  Logger.log('disease rows still on the old clip (expect 0): %s', oldLeft);
  if (over69 > 0 || oldLeft > 0) Logger.log('FAIL - investigate before trusting the sheet.');
  else Logger.log('PASS');
}

/** Restart the migration from the top. */
function resetSoftKneeCursor() {
  PropertiesService.getScriptProperties().deleteProperty(SK_CURSOR_KEY);
  Logger.log('cursor reset - next run starts at row 2.');
}
