/* Fever Watch geolocation: resolve the visitor's nearest supported city.
 *
 * Resolution hierarchy (most accurate first):
 *   saved PharmEasy pincode/address  >  device GPS  >  IP geolocation  >  none
 * Detected lat/lon is snapped to the NEAREST supported city centroid. The
 * detected city is always a changeable default, never a hard lock.
 *
 * IP source: BigDataCloud reverse-geocode-client (keyless, client-side,
 * commercial-OK under its fair-use policy; client-side only), with freeipapi.com
 * as a no-key fallback. Both are HTTPS and CORS-enabled.
 */
window.FeverWatchGeo = (function () {
  "use strict";

  function haversineKm(lat1, lon1, lat2, lon2) {
    var R = 6371, toRad = Math.PI / 180;
    var dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function nearestCity(lat, lon, cities) {
    var best = null, bestD = Infinity;
    for (var i = 0; i < cities.length; i++) {
      var d = haversineKm(lat, lon, cities[i].lat, cities[i].lon);
      if (d < bestD) { bestD = d; best = cities[i]; }
    }
    return best ? { id: best.id, name: best.name, distanceKm: Math.round(bestD) } : null;
  }

  function gps(timeoutMs) {
    return new Promise(function (resolve) {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(
        function (p) { resolve({ lat: p.coords.latitude, lon: p.coords.longitude }); },
        function () { resolve(null); },
        { enableHighAccuracy: false, timeout: timeoutMs || 6000, maximumAge: 600000 }
      );
    });
  }

  function freeip() {
    return fetch("https://free.freeipapi.com/api/json/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.latitude != null && d.longitude != null) return { lat: +d.latitude, lon: +d.longitude, city: d.cityName };
        return null;
      })
      .catch(function () { return null; });
  }

  function ip() {
    // No coords -> BigDataCloud infers an approximate location from the caller's IP.
    return fetch("https://api.bigdatacloud.net/data/reverse-geocode-client?localityLanguage=en")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.latitude != null && d.longitude != null) return { lat: +d.latitude, lon: +d.longitude, city: d.city || d.locality };
        return freeip();
      })
      .catch(freeip);
  }

  /* resolve(cities, opts) -> Promise<{cityId, source, detectedName?} | null>
   *   opts.savedCityId / opts.savedLatLon : PharmEasy saved-address hook (top priority)
   *   opts.allowGPS : request device GPS (prompts the user). Default false = silent IP only.
   */
  function resolve(cities, opts) {
    opts = opts || {};
    if (opts.savedCityId) {
      var m = cities.filter(function (c) { return c.id === opts.savedCityId; })[0];
      if (m) return Promise.resolve({ cityId: m.id, source: "saved" });
    }
    if (opts.savedLatLon) {
      var n = nearestCity(opts.savedLatLon.lat, opts.savedLatLon.lon, cities);
      if (n) return Promise.resolve({ cityId: n.id, source: "saved" });
    }
    var chain = opts.allowGPS ? gps() : Promise.resolve(null);
    return chain.then(function (g) {
      if (g) { var ng = nearestCity(g.lat, g.lon, cities); if (ng) return { cityId: ng.id, source: "gps" }; }
      return ip().then(function (p) {
        if (p) { var ni = nearestCity(p.lat, p.lon, cities); if (ni) return { cityId: ni.id, source: "ip", detectedName: p.city }; }
        return null;
      });
    });
  }

  return { resolve: resolve, nearestCity: nearestCity, haversineKm: haversineKm };
})();
