/* Fever Watch device-adaptive loader.
 *
 * One URL serves either the purpose-built MOBILE flow or the DESKTOP flow (not
 * responsive). At load we pick one by device and inject ONLY that flow's CSS +
 * JS, so the other flow never downloads. The page bakes a crawler-readable
 * fallback inside #fw-app plus the shared nav/footer; the chosen flow then
 * hydrates #fw-app. base path + data url come from window.FW (set per page).
 */
(function () {
  "use strict";
  var FW = window.FW || (window.FW = {});
  var base = FW.base || "";
  var mode = window.matchMedia("(max-width: 819px), (pointer: coarse)").matches ? "mobile" : "desktop";
  FW.mode = mode;
  document.body.classList.add("fw-" + mode);
  // CSS for both flows is media-gated in <head> (so first paint is styled, no FOUC); here we only
  // load the active flow's JS, so the inactive flow's script never downloads.
  var script = document.createElement("script");
  script.src = base + "assets/js/" + mode + ".js" + (FW.ver ? "?v=" + FW.ver : "");
  script.defer = true;
  document.body.appendChild(script);
})();
