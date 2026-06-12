/* Fever Watch share helpers: baked-image fetch + deep links.
 *
 * The share image is NO LONGER drawn on a canvas here. CI bakes every city's card
 * (src/build_share_cards.py - the 2026-06 approved design, regional sub-line included)
 * to assets/img/share/{city}.jpg (portrait 1080x1440); this module just fetches it,
 * so the WhatsApp image, the modal preview and the og:image are one renderer with
 * zero drift. Cache-busted with the grid's generated_at (same scheme as og:image).
 *
 * nativeShare() uses the OS share sheet (mobile); desktop falls back to a
 * WhatsApp-web link + image download.
 */
window.FeverWatchShare = (function () {
  "use strict";
  var base = (window.FW && window.FW.base) || "";

  /* compact digits of an ISO timestamp - mirrors build_site.py og_version() */
  function ver(iso) {
    return String(iso || "").replace(/\D/g, "").slice(0, 14);
  }

  function imageUrl(cityId, generatedAt) {
    var v = ver(generatedAt);
    return base + "assets/img/share/" + cityId + ".jpg" + (v ? "?v=" + v : "");
  }

  var _cache = {};   // url -> Promise<Blob>
  function loadCard(cityId, generatedAt) {
    var url = imageUrl(cityId, generatedAt);
    if (!_cache[url]) {
      _cache[url] = fetch(url, { cache: "force-cache" }).then(function (r) {
        if (!r.ok) throw new Error("share image " + r.status);
        return r.blob();
      });
      _cache[url].catch(function () { delete _cache[url]; });
    }
    return _cache[url];
  }

  function download(blob, filename) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename || "fever-watch.jpg";
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  }

  function whatsapp(text, url) {
    window.open("https://wa.me/?text=" + encodeURIComponent(url ? text + " " + url : text), "_blank");
  }

  function copyLink(url) {
    if (navigator.clipboard) return navigator.clipboard.writeText(url);
    return Promise.resolve();
  }

  function nativeShare(blob, text, url, filename) {
    var file = new File([blob], filename || "fever-watch.jpg", { type: "image/jpeg" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      // Some Android targets (notably WhatsApp) attach only the image and drop the caption when a
      // file is present - the receiving app decides. Best-effort: copy the message so it can be pasted.
      try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url ? text + " " + url : text); } catch (e) {}
      var payload = { files: [file], text: text };
      if (url) payload.url = url;
      return navigator.share(payload);
    }
    download(blob, filename);
    whatsapp(text, url);
    return Promise.resolve(null);
  }

  return { imageUrl: imageUrl, loadCard: loadCard, download: download, whatsapp: whatsapp, copyLink: copyLink, nativeShare: nativeShare };
})();
