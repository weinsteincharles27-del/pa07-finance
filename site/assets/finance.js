/* PA-07 finance: the sections.
 *
 * Reports what the FEC filed, by candidate and by committee. Colour identifies
 * party and nothing else: no figure is marked good or bad, no side is called
 * ahead, and support and oppose are words in a column rather than a red and a
 * green. The analytical sheets live in the workbook this page links to.
 */
(function () {
  "use strict";

  var P = window.PA07, elem = P.elem, C = window.Chart, fmt = C.fmt;

  function money(v) { return v === null || v === undefined ? "–" : "$" + Math.round(v).toLocaleString("en-US"); }
  function pct(v, dp) { return v === null || v === undefined ? "–" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%"; }
  function count(v) { return v === null || v === undefined ? "–" : v.toLocaleString("en-US"); }
  function party(p) { return p === "DEM" ? "D" : p === "REP" ? "R" : p === "IND" ? "Ind" : p === "UN" ? "Unaff." : p; }
  function last(name) { return name.split(" ").filter(function (t) { return !/^(Jr|Sr|II|III)\.?$/.test(t); }).pop(); }
  function nice(s) {
    /* FEC committee names arrive in capitals. Title-case them, keeping acronyms. */
    var keep = { PA: 1, PAC: 1, DLP: 1, FF: 1, SURJ: 1, LLC: 1, USA: 1, "SEED-PAC": 1, US: 1, LC: 1, DC: 1, NGP: 1, VAN: 1, SEIU: 1, USW: 1 };
    var small = { and: 1, for: 1, the: 1, of: 1, an: 1, a: 1, to: 1, in: 1, on: 1 };
    return s.split(" ").map(function (w, i) {
      var core = w.replace(/^[(]|[),.]+$/g, "");
      if (keep[core]) return w;
      if (i && small[core.toLowerCase()]) return w.toLowerCase();
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    }).join(" ");
  }

  function block(id, title, blurb) {
    var sec = elem("section", "block");
    sec.id = id;
    var h = elem("header");
    h.appendChild(elem("h2", null, title));
    if (blurb) h.appendChild(elem("p", null, blurb));
    sec.appendChild(h);
    return sec;
  }

  function figure(host, legendItems, caption) {
    var fig = elem("figure", "chart");
    if (legendItems) fig.appendChild(C.legend(legendItems));
    var plot = elem("div");
    fig.appendChild(plot);
    if (caption) fig.appendChild(elem("figcaption", null, caption));
    host.appendChild(fig);
    return plot;
  }

  function tile(k, v, sub) {
    var li = elem("li", "stat");
    li.appendChild(elem("div", "k", k));
    li.appendChild(elem("div", "v num", v));
    if (sub) li.appendChild(elem("div", "sub", sub));
    return li;
  }

  function table(host, head, rows, rowClass) {
    var wrap = elem("div", "scroll");
    var t = elem("table");
    var thead = elem("thead"), tr = elem("tr");
    head.forEach(function (h) { tr.appendChild(elem("th", h.num ? "num" : null, h.label || h)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tb = elem("tbody");
    rows.forEach(function (r, i) {
      var tr2 = elem("tr", rowClass ? rowClass(r, i) : null);
      r.cells.forEach(function (c, j) {
        var td = elem("td", head[j] && head[j].num ? "num" : (c === "–" ? "gap" : null), c);
        tr2.appendChild(td);
      });
      tb.appendChild(tr2);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    host.appendChild(wrap);
  }

  function note(host, text, cls) {
    var n = elem("div", cls || "note", text);
    host.appendChild(n);
    return n;
  }

  /* ------------------------------------------------------------- sections */

  function nominees(d) {
    return d.candidates.candidates.filter(function (c) { return c.status === "nominee"; })
      .sort(function (a, b) { return last(a.name) < last(b.name) ? -1 : 1; });
  }

  function standing(d) {
    var noms = nominees(d);
    var sec = block("standing", "Where the money stands",
      "Each nominee's campaign committee, cycle to date, from its latest quarterly report to the FEC. " +
      "Figures run through " + P.longDate(d.candidates.coverage_through) + ".");
    var grid = elem("div", "grid two");
    noms.forEach(function (c) {
      var col = elem("div");
      var h = elem("h3");
      h.appendChild(document.createTextNode(c.name + " "));
      h.appendChild(elem("span", c.party === "DEM" ? "dem" : "rep", "(" + party(c.party) + ")"));
      if (c.incumbent) h.appendChild(document.createTextNode(" · incumbent"));
      col.appendChild(h);
      var ul = elem("ul", "stats");
      ul.appendChild(tile("Raised", money(c.receipts), "all receipts this cycle"));
      ul.appendChild(tile("Spent", money(c.disbursements), "all disbursements this cycle"));
      ul.appendChild(tile("Cash on hand", money(c.cash_on_hand), "at " + P.longDate(c.coverage_end)));
      col.appendChild(ul);
      grid.appendChild(col);
    });
    sec.appendChild(grid);
    var plot = figure(sec, noms.map(function (c) {
      return { label: c.name + " (" + party(c.party) + ")", color: P.partyColour(c.party) };
    }), "Raised, spent and cash on hand, by nominee. Hover a bar for the exact figure.");
    C.groups(plot, {
      title: "Raised, spent and cash on hand",
      categories: ["Raised", "Spent", "Cash on hand"],
      series: noms.map(function (c) {
        return { label: c.name, color: P.partyColour(c.party),
                 values: [c.receipts, c.disbursements, c.cash_on_hand] };
      })
    });
    return sec;
  }

  var SOURCES = [
    { key: "individual_itemized", label: "Individual donors, over $200", color: "#1F4E79" },
    { key: "individual_unitemized", label: "Small donations, $200 or less", color: "#7EA6D9" },
    { key: "pac_contributions", label: "Political action committees", color: "#A8620B" },
    { key: "party_contributions", label: "Party committees", color: "#D9A441" },
    { key: "transfers_in", label: "Transfers from another authorized committee", color: "#6D4C9F" },
    { key: "self_funding", label: "Candidate's own money", color: "#4B5563" },
    { key: "other", label: "Other", color: "#C4C9D2" }
  ];

  function sources(d) {
    var noms = nominees(d);
    var sec = block("sources", "Where each nominee's money came from",
      "Every dollar of receipts, by source, as reported to the FEC. The bars add up to each " +
      "nominee's total raised.");
    var plot = figure(sec, SOURCES.map(function (s) { return { label: s.label, color: s.color, dot: true }; }),
      "Receipts by source. A transfer from another authorized committee is counted in receipts but was not raised from donors this cycle.");
    C.stacked(plot, {
      title: "Receipts by source",
      categories: noms.map(function (c) { return c.name + " (" + party(c.party) + ")"; }),
      series: SOURCES.map(function (s) {
        return { label: s.label, color: s.color, values: noms.map(function (c) { return c[s.key]; }) };
      })
    });
    var head = [{ label: "Source" }].concat(noms.map(function (c) { return { label: c.name, num: true }; }))
      .concat(noms.map(function (c) { return { label: last(c.name) + ", share", num: true }; }));
    var rows = SOURCES.map(function (s) {
      return { cells: [s.label].concat(noms.map(function (c) { return money(c[s.key]); }))
        .concat(noms.map(function (c) { return c.receipts ? pct(c[s.key] / c.receipts) : "–"; })) };
    });
    rows.push({ cells: ["Total raised"].concat(noms.map(function (c) { return money(c.receipts); }))
      .concat(noms.map(function () { return "100%"; })), total: true });
    table(sec, head, rows, function (r) { return r.total ? "total" : null; });
    return sec;
  }

  function everyone(d) {
    var cs = d.candidates.candidates;
    var sec = block("candidates", "Every declared candidate",
      "All " + cs.length + " candidates the FEC lists for this seat in " + d.candidates.cycle +
      ". Nominees are the two on the November ballot; primary candidates ran in May; a blank row " +
      "means the committee has never filed a periodic report.");
    var head = ["Candidate", "Party", "Status", { label: "Raised", num: true }, { label: "Spent", num: true },
                { label: "Cash on hand", num: true }, { label: "Small donations", num: true },
                { label: "From PACs", num: true }, "Reported through"];
    var rows = cs.map(function (c) {
      var st = c.status === "nominee" ? "Nominee" : c.status === "primary" ? "Primary candidate" : "Declared";
      if (c.incumbent) st += ", incumbent";
      return { party: c.party, cells: [c.name, party(c.party), st,
        c.filed ? money(c.receipts) : "–", c.filed ? money(c.disbursements) : "–",
        c.filed ? money(c.cash_on_hand) : "–", c.filed ? money(c.individual_unitemized) : "–",
        c.filed ? money(c.pac_contributions) : "–", c.filed ? P.longDate(c.coverage_end) : "no report filed"] };
    });
    table(sec, head, rows, function (r) { return r.party === "DEM" ? "d" : r.party === "REP" ? "r" : null; });
    return sec;
  }

  function outside(d) {
    var o = d.outside;
    var sec = block("outside", "Outside spending",
      "Money that groups spent on their own, without coordinating with any campaign, to support or " +
      "oppose one of the two nominees. Total: " + money(o.total) + ".");
    table(sec, ["Candidate the spending was about", { label: "Supporting", num: true },
                { label: "Opposing", num: true }, { label: "Committees", num: true }],
      o.by_target.map(function (t) {
        return { cells: [t.target, money(t.supports), money(t.opposes),
                         count(t.committees_supporting + t.committees_opposing)] };
      }));
    var top = o.rows.slice(0, 10);
    var byName = {};
    d.candidates.candidates.forEach(function (c) { byName[c.name] = c; });
    var plot = figure(sec, null, "The ten largest outside spenders. Bar colour is the party of the candidate the spending was about; the label says whether it supported or opposed them.");
    C.hbars(plot, {
      title: "Ten largest outside spenders",
      rows: top.map(function (r) {
        var c = byName[r.target] || {};
        return { label: nice(r.committee) + ", " + r.stance + " " + r.target,
                 short: (nice(r.committee).length > 26 ? nice(r.committee).slice(0, 24) + "…" : nice(r.committee)) +
                        " · " + r.stance + " " + last(r.target),
                 value: r.amount, color: P.partyColour(c.party) };
      })
    });
    var det = elem("details");
    det.appendChild(elem("summary", null, "Every committee, " + o.rows.length + " rows"));
    table(det, ["Committee", "About", "Stance", { label: "Amount", num: true }, { label: "Filings", num: true }],
      o.rows.map(function (r) {
        return { cells: [nice(r.committee), r.target, r.stance, money(r.amount), count(r.filings)] };
      }));
    sec.appendChild(det);
    if (o.by_category && o.by_category.length) {
      sec.appendChild(elem("h3", null, "What was bought"));
      var plot2 = figure(sec, null, "Itemized outside expenditures by what they paid for.");
      C.hbars(plot2, {
        title: "Outside spending by what was bought",
        rows: o.by_category.map(function (r) { return { label: r.category, value: r.amount, color: "#4B5563" }; })
      });
      var det2 = elem("details");
      det2.appendChild(elem("summary", null, "Every expenditure, " + o.itemized.length + " rows"));
      table(det2, ["Committee", "About", "Stance", "What", "Paid to", "Where", { label: "Amount", num: true }, "Date"],
        o.itemized.map(function (r) {
          return { cells: [nice(r.committee), r.target, r.stance, nice(r.what || ""), nice(r.payee || ""),
                           [nice(r.city || ""), r.state].filter(Boolean).join(", "), money(r.amount), r.date || ""] };
        }));
      sec.appendChild(det2);
    }
    return sec;
  }

  /* ------------------------------------------------- what the money bought */

  function bought(d) {
    var dt = d.detail;
    if (!dt || !dt.available || !dt.committees.length) return null;
    var sec = block("bought", "What the money bought",
      "Itemized campaign spending, each payment over $200, through " + P.longDate(dt.coverage_through) + ".");
    var grid = elem("div", "grid two");
    dt.committees.forEach(function (c) {
      var col = elem("div");
      var h = elem("h3");
      h.appendChild(document.createTextNode(c.candidate + " "));
      h.appendChild(elem("span", c.party === "DEM" ? "dem" : "rep", "(" + party(c.party) + ")"));
      col.appendChild(h);
      var plot = elem("div");
      col.appendChild(plot);
      C.hbars(plot, {
        title: "Spending by category, " + c.candidate,
        rows: c.spending.by_category.slice(0, 8).map(function (r) {
          return { label: r.category, value: r.amount, color: P.partyColour(c.party) };
        })
      });
      var ul = elem("ul", "stats");
      ul.appendChild(tile("Itemized spending", money(c.spending.itemized_total), count(c.spending.items) + " payments"));
      ul.appendChild(tile("Paid to Pennsylvania vendors", pct(c.spending.in_pa_share, 0), "share of itemized spending"));
      col.appendChild(ul);
      col.appendChild(elem("h3", null, "Largest payees"));
      table(col, ["Payee", "Where", { label: "Amount", num: true }],
        c.spending.top_vendors.map(function (v) {
          return { cells: [nice(v.vendor), [nice(v.city || ""), v.state].filter(Boolean).join(", "), money(v.amount)] };
        }));
      grid.appendChild(col);
    });
    sec.appendChild(grid);
    return sec;
  }

  /* --------------------------------------------- where the money came from */

  function from(d) {
    var dt = d.detail;
    if (!dt || !dt.available || !dt.committees.length) return null;
    var sec = block("from", "Where the donors are",
      "Itemized individual contributions, each over $200, by where the donor lives.");
    var grid = elem("div", "grid two");
    dt.committees.forEach(function (c) {
      var co = c.contributions;
      var col = elem("div");
      var h = elem("h3");
      h.appendChild(document.createTextNode(c.candidate + " "));
      h.appendChild(elem("span", c.party === "DEM" ? "dem" : "rep", "(" + party(c.party) + ")"));
      col.appendChild(h);
      var plot = elem("div");
      col.appendChild(plot);
      C.hbars(plot, {
        title: "Contributions by state, " + c.candidate,
        rows: co.by_state.map(function (r) { return { label: r.state, value: r.amount, color: P.partyColour(c.party) }; })
      });
      var big = co.by_size.filter(function (s) { return s.size >= 2000; })[0];
      var all = co.by_size.reduce(function (a, s) { return a + (s.amount || 0); }, 0);
      var ul = elem("ul", "stats");
      ul.appendChild(tile("From the district", pct(co.in_district_share, 0), "zip codes " + dt.in_district_zip_prefixes.join(", ") + "; approximate"));
      ul.appendChild(tile("Gifts of $2,000 and over", big ? pct(big.amount / all, 0) : "\u2013", "share of all individual money"));
      ul.appendChild(tile("Gifts of $200 or less", pct(co.by_size[0].amount / all, 0), "share of all individual money"));
      col.appendChild(ul);
      col.appendChild(elem("h3", null, "Top occupations, as donors reported them"));
      table(col, ["Occupation", { label: "Amount", num: true }, { label: "Gifts", num: true }],
        co.by_occupation.map(function (o) {
          return { cells: [nice(o.occupation || "(not stated)"), money(o.amount), count(o.count)] };
        }));
      grid.appendChild(col);
    });
    sec.appendChild(grid);
    return sec;
  }

  function history(d) {
    var h = d.history;
    var sec = block("history", "The last four elections",
      "Final full-cycle totals for the two nominees in each general election, with the certified " +
      "result. Outside spending here is the total that supported or opposed each candidate over the whole cycle.");
    var cycles = h.cycles.map(function (c) { return String(c.cycle); });
    var dem = h.cycles.map(function (c) { return c.candidates.filter(function (x) { return x.party === "DEM"; })[0]; });
    var rep = h.cycles.map(function (c) { return c.candidates.filter(function (x) { return x.party === "REP"; })[0]; });
    var plot = figure(sec, [{ label: "Democratic nominee", color: P.colours.D }, { label: "Republican nominee", color: P.colours.R }],
      "Money raised by each party's nominee, by election. Hover a bar for the exact figure.");
    C.groups(plot, {
      title: "Raised by each nominee, by election",
      categories: cycles,
      series: [{ label: "Democratic nominee", color: P.colours.D, values: dem.map(function (x) { return x.receipts; }) },
               { label: "Republican nominee", color: P.colours.R, values: rep.map(function (x) { return x.receipts; }) }]
    });
    var rows = [];
    h.cycles.forEach(function (c) {
      c.candidates.forEach(function (x) {
        rows.push({ party: x.party, cells: [String(c.cycle), x.name + (x.incumbent ? " (incumbent)" : ""), party(x.party),
          money(x.receipts), money(x.disbursements), money(x.ie_supporting), money(x.ie_opposing),
          count(x.general_votes), pct(x.two_party_share), x.winner ? "won" : "lost"] });
      });
    });
    table(sec, ["Election", "Candidate", "Party", { label: "Raised", num: true }, { label: "Spent", num: true },
                { label: "Outside, supporting", num: true }, { label: "Outside, opposing", num: true },
                { label: "Votes", num: true }, { label: "Two-party share", num: true }, "Result"],
      rows, function (r) { return r.party === "DEM" ? "d" : "r"; });
    var n = note(sec, "Two-party share is the candidate's votes divided by Democratic plus Republican votes, so the four elections compare on the same footing. " +
      "District lines changed between 2020 and 2022, so the electorate is not identical across all four. Certified results: ");
    h.cycles.forEach(function (c, i) {
      var a = elem("a", null, String(c.cycle));
      a.href = c.source_url;
      a.title = c.source;
      n.appendChild(a);
      n.appendChild(document.createTextNode(i < h.cycles.length - 1 ? ", " : "."));
    });
    return sec;
  }

  function download(d) {
    var wb = d.manifest.workbook;
    var sec = block("download", "Download",
      "The full workbook behind this page: every figure above, the source-of-funds reconciliation, " +
      "the four-election history, and a money-against-results analysis with its caveats. Native Excel " +
      "charts, no macros, rebuilt on every scheduled run.");
    if (wb && wb.available) {
      var p = elem("p");
      var a = elem("a", "button", "PA07_Campaign_Finance.xlsx");
      a.href = wb.href;
      a.setAttribute("download", "");
      p.appendChild(a);
      p.appendChild(document.createTextNode("  " + Math.round(wb.bytes / 1024) + " KB · nine sheets · thirteen charts"));
      sec.appendChild(p);
    } else {
      note(sec, "The workbook is not available in this build.", "caveat medium");
    }
    return sec;
  }

  document.addEventListener("data:ready", function (ev) {
    var d = ev.detail;
    var main = document.getElementById("main");
    [standing, sources, bought, from, everyone, outside, history, download].forEach(function (f) {
      var sec = f(d);
      if (sec) main.appendChild(sec);
    });
  });
})();
