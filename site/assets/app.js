/* PA-07 finance: page boot and the data layer.
 *
 * Static site, no build step: it fetches the JSON that export_site.py committed
 * and draws it. All paths are relative, so the page works served from a domain
 * root, from /pa07-finance/, or from a laptop with `python3 -m http.server`.
 */
(function () {
  "use strict";

  var D = "#2E5FA3", R = "#C0392B", OTHER = "#6B7280";

  var State = { data: {} };

  function $(id) { return document.getElementById(id); }

  function elem(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function get(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
      return r.json();
    });
  }

  function utc(iso) {
    if (!iso) return "";
    var t = Date.parse(iso);
    return isNaN(t) ? iso : new Date(t).toISOString().replace("T", " ").slice(0, 16) + " UTC";
  }

  function longDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T00:00:00Z");
    if (isNaN(d)) return iso;
    return d.getUTCDate() + " " + ["January", "February", "March", "April", "May", "June", "July",
      "August", "September", "October", "November", "December"][d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  function renderHeader(man) {
    var r = man.race;
    var h = $("title");
    h.innerHTML = "";
    h.appendChild(document.createTextNode(r.democrat + " "));
    h.appendChild(elem("span", "dem", "(D)"));
    h.appendChild(document.createTextNode(" and " + r.republican + " "));
    h.appendChild(elem("span", "rep", "(R)"));
    $("countdown").textContent =
      (r.days_to_election > 0 ? r.days_to_election + " days to the election" : "Election day has passed") +
      " · " + longDate(r.election);
    $("built").textContent = "Data updated " + utc(man.generated_utc) +
      " · candidate totals through " + longDate(man.coverage_through);
  }

  function fail(err) {
    var box = $("boot");
    if (!box) return;
    box.className = "caveat high";
    box.innerHTML = "<b>Could not load the data files.</b><p>" + String(err) + "</p>" +
      "<p>If you opened this file directly, the browser is blocking the fetch. Serve the " +
      "directory instead: <code>cd site &amp;&amp; python3 -m http.server 8000</code></p>";
  }

  function boot() {
    Promise.all([
      get("data/manifest.json"),
      get("data/candidates.json"),
      get("data/outside.json"),
      get("data/history.json")
    ]).then(function (r) {
      State.data = { manifest: r[0], candidates: r[1], outside: r[2], history: r[3] };
      renderHeader(State.data.manifest);
      var b = $("boot");
      if (b) b.remove();
      document.dispatchEvent(new CustomEvent("data:ready", { detail: State.data }));
    }).catch(fail);
  }

  window.PA07 = {
    state: State, get: get, elem: elem, utc: utc, longDate: longDate,
    colours: { D: D, R: R, OTHER: OTHER },
    partyColour: function (p) { return p === "DEM" ? D : p === "REP" ? R : OTHER; }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
