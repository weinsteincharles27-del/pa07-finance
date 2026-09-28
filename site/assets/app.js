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
    /* Counted from the reader's own date, not the export's: the manifest's
       days_to_election is frozen when the figures last changed, which can be
       days ago, since an unchanged FEC read commits nothing. */
    var e = Date.parse(r.election + "T00:00:00Z"), n = new Date();
    var days = Math.round((e - Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())) / 86400000);
    var when = longDate(r.election);
    $("countdown").textContent =
      days > 1 ? days + " days to the election on " + when + "." :
      days === 1 ? "The election is tomorrow, " + when + "." :
      days === 0 ? "Election day, " + when + "." : "The election was on " + when + ".";
    $("built").textContent = "Data updated " + utc(man.generated_utc) +
      ". Candidate totals run through " + longDate(man.coverage_through) + ".";
  }

  function fail(err) {
    var box = $("boot");
    if (!box) return;
    box.className = "caveat";
    box.innerHTML = "<b>Could not load the data files.</b><p>" + String(err) + "</p>" +
      "<p>If you opened this file directly, the browser is blocking the fetch. Serve the " +
      "directory instead: <code>cd site &amp;&amp; python3 -m http.server 8000</code></p>";
  }

  function boot() {
    Promise.all([
      get("data/manifest.json"),
      get("data/candidates.json"),
      get("data/outside.json"),
      get("data/history.json"),
      get("data/detail.json").catch(function () { return { available: false, committees: [] }; }),
      /* The warnings travel with the numbers they qualify, inline, rather than
         in an appendix nobody scrolls to. */
      get("data/caveats.json").catch(function () { return { items: [] }; })
    ]).then(function (r) {
      State.data = { manifest: r[0], candidates: r[1], outside: r[2], history: r[3], detail: r[4],
                     caveats: r[5] };
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
