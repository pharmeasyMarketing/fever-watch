/* Fever Watch shareable-card export + deep links.
 *
 * Renders the city's risk card to a PNG (portrait, WhatsApp/Instagram-Stories
 * friendly) on a canvas, and exposes share / copy / download actions with a deep
 * link back to /fever-watch/{city}. On mobile, nativeShare() uses the OS share
 * sheet (which covers WhatsApp, Instagram, etc.); on desktop it falls back to a
 * WhatsApp-web link + image download.
 */
window.FeverWatchShare = (function () {
  "use strict";
  var LOGO_SRC = "/assets/img/pe_logo-white.svg";

  function loadImg(src) {
    return new Promise(function (res, rej) {
      var i = new Image();
      i.onload = function () { res(i); };
      i.onerror = rej;
      i.src = src;
    });
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* card = {emoji, score, band, bandColor, title, sub} -> Promise<canvas> */
  function renderCard(card) {
    var W = 1080, H = 1350;
    var c = document.createElement("canvas");
    c.width = W; c.height = H;
    var ctx = c.getContext("2d");

    var g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, "#10847E");
    g.addColorStop(1, "#0A534F");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";

    ctx.font = "150px sans-serif";
    ctx.fillText(card.emoji || "🦟", W / 2, 540);

    ctx.fillStyle = "#fff";
    ctx.font = "800 300px Inter, 'Segoe UI', sans-serif";
    ctx.fillText(String(card.score), W / 2, 830);
    ctx.font = "600 70px Inter, 'Segoe UI', sans-serif";
    ctx.fillText("/100", W / 2, 900);

    var bandText = (card.band || "") + " RISK";
    ctx.font = "800 56px Inter, 'Segoe UI', sans-serif";
    var bw = ctx.measureText(bandText).width + 90;
    ctx.fillStyle = "#fff";
    roundRect(ctx, (W - bw) / 2, 960, bw, 92, 46); ctx.fill();
    ctx.fillStyle = card.bandColor || "#E4572E";
    ctx.fillText(bandText, W / 2, 1024);

    ctx.fillStyle = "#fff";
    ctx.font = "600 56px Inter, 'Segoe UI', sans-serif";
    ctx.fillText(card.title || "", W / 2, 1150);
    ctx.font = "400 40px Inter, 'Segoe UI', sans-serif";
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillText(card.sub || "", W / 2, 1210);

    ctx.font = "400 34px Inter, 'Segoe UI', sans-serif";
    ctx.fillStyle = "rgba(255,255,255,0.8)";
    ctx.fillText("pharmeasy.in/fever-watch", W / 2, 1295);

    return loadImg(LOGO_SRC).then(function (img) {
      var lw = 400, lh = lw * (img.height / img.width || 0.2);
      ctx.drawImage(img, (W - lw) / 2, 150, lw, lh);
      return c;
    }).catch(function () { return c; });
  }

  function toBlob(canvas) {
    return new Promise(function (res) { canvas.toBlob(function (b) { res(b); }, "image/png"); });
  }

  function download(canvas, filename) {
    canvas.toBlob(function (b) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = filename || "fever-watch.png";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
    }, "image/png");
  }

  function whatsapp(text, url) {
    window.open("https://wa.me/?text=" + encodeURIComponent(text + " " + url), "_blank");
  }

  function copyLink(url) {
    if (navigator.clipboard) return navigator.clipboard.writeText(url);
    return Promise.resolve();
  }

  /* nativeShare: image + text via the OS share sheet when available (mobile),
     else download the image and open WhatsApp web (desktop). */
  function nativeShare(canvas, text, url, filename) {
    return toBlob(canvas).then(function (blob) {
      var file = new File([blob], filename || "fever-watch.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        return navigator.share({ files: [file], text: text, url: url });
      }
      download(canvas, filename);
      whatsapp(text, url);
      return null;
    });
  }

  return { renderCard: renderCard, toBlob: toBlob, download: download, whatsapp: whatsapp, copyLink: copyLink, nativeShare: nativeShare };
})();
