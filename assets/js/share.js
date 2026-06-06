/* Fever Watch shareable-card export + deep links.
 *
 * Renders the city's risk card to a PNG (portrait 1080x1350, WhatsApp / Instagram
 * Stories friendly) on a canvas, matching the OG card in src/build_og.py: dark
 * textured teal background, co-branded PharmEasy + Fever Watch lockup, the OVERALL
 * city score as the hero, a band pill, and a frosted glass card with Location and
 * the Top-concern disease. The PharmEasy mark is a rasterized PNG (not an SVG) so
 * it draws reliably on every Android WebView.
 *
 * nativeShare() uses the OS share sheet (mobile); desktop falls back to a
 * WhatsApp-web link + image download.
 */
window.FeverWatchShare = (function () {
  "use strict";
  var base = (window.FW && window.FW.base) || "";
  var LOGO_SRC = base + "assets/img/pe_logo-white.png";
  var BG_TOP = "#0F6059", BG_BOT = "#062F2C", ACCENT = "#4AC9BE", SOFT = "#CBE6E3";
  var _logo = null;

  function loadImg(src) {
    return new Promise(function (res, rej) {
      var i = new Image();
      i.onload = function () { res(i); };
      i.onerror = rej;
      i.src = src;
    });
  }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function paintBackground(ctx, W, H) {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, BG_TOP); g.addColorStop(1, BG_BOT);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // soft top glow
    var glow = ctx.createRadialGradient(W / 2, H * 0.02, 0, W / 2, H * 0.08, W * 0.7);
    glow.addColorStop(0, "rgba(64,176,166,0.30)"); glow.addColorStop(1, "rgba(64,176,166,0)");
    ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);
    // darker pools at the bottom corners
    [[W * 0.08, H * 1.02], [W * 0.92, H * 1.02]].forEach(function (p) {
      var d = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], W * 0.5);
      d.addColorStop(0, "rgba(0,18,17,0.55)"); d.addColorStop(1, "rgba(0,18,17,0)");
      ctx.fillStyle = d; ctx.fillRect(0, 0, W, H);
    });
    // rain streaks
    ctx.strokeStyle = "rgba(255,255,255,0.06)"; ctx.lineWidth = 2;
    var n = Math.round(W * H / 9000);
    for (var i = 0; i < n; i++) {
      var x = Math.random() * W, y = Math.random() * H * 0.95, ln = H * (0.018 + Math.random() * 0.022);
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - ln * 0.45, y + ln); ctx.stroke();
    }
  }

  function drawLockup(ctx, cx, yMid, logoH) {
    var gap = logoH * 0.55;
    var lw = _logo ? logoH * (_logo.width / _logo.height) : 0;
    ctx.font = "600 " + Math.round(logoH * 0.92) + "px Inter, 'Segoe UI', sans-serif";
    var fw = "Fever Watch", fwW = ctx.measureText(fw).width;
    var total = lw + gap + 2 + gap + fwW;
    var x = cx - total / 2;
    if (_logo) { ctx.drawImage(_logo, x, yMid - logoH / 2, lw, logoH); x += lw + gap; }
    ctx.strokeStyle = "rgba(255,255,255,0.5)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, yMid - logoH * 0.62); ctx.lineTo(x, yMid + logoH * 0.62); ctx.stroke();
    x += 2 + gap;
    ctx.fillStyle = "#fff"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(fw, x, yMid);
    ctx.textAlign = "center";
  }

  function drawPill(ctx, cx, yMid, text, color, fsize, h) {
    ctx.font = "800 " + fsize + "px Inter, 'Segoe UI', sans-serif";
    var w = ctx.measureText(text).width + 108;
    var x0 = cx - w / 2;
    ctx.save();
    ctx.shadowColor = "rgba(255,255,255,0.55)"; ctx.shadowBlur = 26;
    ctx.fillStyle = "#fff"; rr(ctx, x0, yMid - h / 2, w, h, h / 2); ctx.fill();
    ctx.restore();
    ctx.fillStyle = color; ctx.textBaseline = "middle";
    ctx.fillText(text, cx, yMid + 2);
  }

  function drawPin(ctx, cx, cy, size) {
    var r = size * 0.34, ty = cy - size * 0.16;
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(cx, ty, r, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.84, ty + r * 0.42); ctx.lineTo(cx + r * 0.84, ty + r * 0.42);
    ctx.lineTo(cx, cy + size * 0.5); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#0a3430"; ctx.beginPath(); ctx.arc(cx, ty, r * 0.42, 0, Math.PI * 2); ctx.fill();
  }

  function drawGlobe(ctx, cx, cy, r) {
    ctx.strokeStyle = ACCENT; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.ellipse(cx, cy, r * 0.5, r, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx - r, cy); ctx.lineTo(cx + r, cy); ctx.stroke();
  }

  function badge(ctx, cx, cy, r) {
    ctx.fillStyle = "rgba(4,34,32,0.62)";
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  }

  function wrap(ctx, text, maxW) {
    if (ctx.measureText(text).width <= maxW) return [text];
    if (text.indexOf(", ") >= 0) { var p = text.split(", "); return [p[0] + ",", p.slice(1).join(", ")]; }
    return [text];
  }

  /* card = {score, band, bandColor, city, state, driverLabel, driverEmoji, date} */
  function renderCard(card) {
    var W = 1080, H = 1350;
    var c = document.createElement("canvas");
    c.width = W; c.height = H;
    var ctx = c.getContext("2d");

    function paint() {
      paintBackground(ctx, W, H);
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      drawLockup(ctx, W / 2, 120, 54);

      ctx.font = "150px 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif";
      ctx.fillText(card.driverEmoji || "🦟", W / 2, 300);

      ctx.fillStyle = SOFT; ctx.font = "600 42px Inter, 'Segoe UI', sans-serif";
      ctx.fillText("Monsoon Fever Risk Score", W / 2, 440);

      ctx.fillStyle = "#fff"; ctx.font = "800 250px Inter, 'Segoe UI', sans-serif";
      var s = String(card.score), sw = ctx.measureText(s).width;
      ctx.textAlign = "left";
      ctx.fillText(s, W / 2 - sw / 2 - 56, 600);
      ctx.fillStyle = ACCENT; ctx.font = "800 70px Inter, 'Segoe UI', sans-serif";
      ctx.fillText("/100", W / 2 - sw / 2 - 56 + sw + 26, 632);
      ctx.textAlign = "center";

      drawPill(ctx, W / 2, 792, (card.band || "") + " RISK", card.bandColor || "#E4572E", 58, 100);

      // glass info card
      var bx = 120, by = 905, bw = 840, bh = 250;
      ctx.fillStyle = "rgba(255,255,255,0.06)"; ctx.strokeStyle = "rgba(255,255,255,0.20)"; ctx.lineWidth = 2;
      rr(ctx, bx, by, bw, bh, 30); ctx.fill(); ctx.stroke();
      var rows = [
        { icon: "pin", label: "Location", lines: wrapValue(ctx, (card.city + (card.state ? ", " + card.state : "")), bw - 260) },
        { icon: card.driverEmoji || "🦟", label: "Top concern", lines: [card.driverLabel || ""] }
      ];
      var seg = bh / rows.length, badgeR = 58, padL = 34;
      rows.forEach(function (row, i) {
        var cy = by + seg * (i + 0.5);
        var cbx = bx + padL + badgeR, tx = cbx + badgeR + 24;
        badge(ctx, cbx, cy, badgeR);
        if (row.icon === "pin") { drawPin(ctx, cbx, cy, badgeR * 1.15); }
        else { ctx.font = (badgeR * 1.2) + "px 'Segoe UI Emoji', sans-serif"; ctx.textAlign = "center"; ctx.fillText(row.icon, cbx, cy + 2); }
        ctx.textAlign = "left";
        var lh = 52, blockH = 30 + 10 + lh * row.lines.length, ty = cy - blockH / 2;
        ctx.fillStyle = ACCENT; ctx.font = "600 30px Inter, 'Segoe UI', sans-serif"; ctx.textBaseline = "top";
        ctx.fillText(row.label, tx, ty);
        ctx.fillStyle = "#fff"; ctx.font = "800 46px Inter, 'Segoe UI', sans-serif";
        var vy = ty + 40;
        row.lines.forEach(function (ln) { ctx.fillText(ln, tx, vy); vy += lh; });
        if (i < rows.length - 1) {
          ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = 2; ctx.setLineDash([10, 8]);
          ctx.beginPath(); ctx.moveTo(tx, by + seg); ctx.lineTo(bx + bw - padL, by + seg); ctx.stroke();
          ctx.setLineDash([]);
        }
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
      });

      // date
      ctx.font = "600 36px Inter, 'Segoe UI', sans-serif"; ctx.fillStyle = SOFT;
      ctx.fillText("📅  " + (card.date || ""), W / 2, 1212);

      // footer
      ctx.fillStyle = "rgba(255,255,255,0.05)"; ctx.fillRect(0, 1262, W, H - 1262);
      ctx.strokeStyle = "rgba(255,255,255,0.16)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, 1262); ctx.lineTo(W, 1262); ctx.stroke();
      var fy = 1306, pre = "Check your city at ", url = "pharmeasy.in/fever-watch";
      ctx.font = "600 34px Inter, 'Segoe UI', sans-serif"; var preW = ctx.measureText(pre).width;
      ctx.font = "800 34px Inter, 'Segoe UI', sans-serif"; var urlW = ctx.measureText(url).width;
      var x = (W - (44 + 16 + preW + urlW)) / 2;
      drawGlobe(ctx, x + 22, fy, 22);
      x += 44 + 16;
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#fff"; ctx.font = "600 34px Inter, 'Segoe UI', sans-serif"; ctx.fillText(pre, x, fy); x += preW;
      ctx.fillStyle = ACCENT; ctx.font = "800 34px Inter, 'Segoe UI', sans-serif"; ctx.fillText(url, x, fy);
      ctx.textAlign = "center";
      return c;
    }

    if (_logo) return Promise.resolve(paint());
    return loadImg(LOGO_SRC).then(function (img) { _logo = img; return paint(); }).catch(function () { return paint(); });
  }

  function wrapValue(ctx, text, maxW) {
    ctx.font = "800 46px Inter, 'Segoe UI', sans-serif";
    return wrap(ctx, text, maxW);
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
    window.open("https://wa.me/?text=" + encodeURIComponent(url ? text + " " + url : text), "_blank");
  }

  function copyLink(url) {
    if (navigator.clipboard) return navigator.clipboard.writeText(url);
    return Promise.resolve();
  }

  function nativeShare(canvas, text, url, filename) {
    return toBlob(canvas).then(function (blob) {
      var file = new File([blob], filename || "fever-watch.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        // Some Android targets (notably WhatsApp) attach only the image and drop the caption when a
        // file is present - the receiving app decides. Best-effort: copy the message so it can be pasted.
        try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url ? text + " " + url : text); } catch (e) {}
        var payload = { files: [file], text: text };
        if (url) payload.url = url;
        return navigator.share(payload);
      }
      download(canvas, filename);
      whatsapp(text, url);
      return null;
    });
  }

  return { renderCard: renderCard, toBlob: toBlob, download: download, whatsapp: whatsapp, copyLink: copyLink, nativeShare: nativeShare };
})();
