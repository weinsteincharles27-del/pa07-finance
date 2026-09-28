/* PA-07 finance: the sections, read top to bottom as one column.
 *
 * Reports what the FEC filed, by candidate and by committee. Colour identifies
 * party and nothing else: no figure is marked good or bad, no side is called
 * ahead, and support and oppose are words rather than a red and a green. A
 * category of money is a row with one bar per nominee on one shared scale,
 * never a hue of its own, so blue always means the Democrat and red the
 * Republican. Sentences state both nominees' figures and let the reader
 * compare. Each caveat from caveats.json sits beside the figures it
 * qualifies. The analytical sheets live in the workbook this page links to.
 */
(function () {
  "use strict";

  var P = window.PA07, elem = P.elem, C = window.Chart, fmt = C.fmt;

  function has(v) { return v !== null && v !== undefined; }
  function money(v) { return has(v) ? "$" + Math.round(v).toLocaleString("en-US") : "–"; }
  function pct(v, dp) { return has(v) ? (v * 100).toFixed(dp === undefined ? 1 : dp) + "%" : "–"; }
  function count(v) { return has(v) ? v.toLocaleString("en-US") : "–"; }
  function party(p) { return p === "DEM" ? "D" : p === "REP" ? "R" : p === "IND" ? "Ind" : p === "UN" ? "Unaff." : p; }
  function last(name) { return name.split(" ").filter(function (t) { return !/^(Jr|Sr|II|III)\.?$/.test(t); }).pop(); }
  function poss(name) { return name + "’s"; }
  function text(host, s) { host.appendChild(document.createTextNode(s)); }

  /* Money in a sentence: millions to two places, thousands rounded. */
  function said(v) {
    if (!has(v)) return "no figure";
    var a = Math.abs(v);
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + " million";
    if (a >= 1e3) return "$" + Math.round(v / 1e3).toLocaleString("en-US") + ",000";
    return "$" + Math.round(v);
  }

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
  function place(city, state) { return [nice(city || ""), state].filter(Boolean).join(", "); }

  /* Sections go into the page before they are drawn into, so each chart
     measures its real width on the first pass instead of redrawing. */
  function section(id, title) {
    var s = elem("section"), h = elem("h2", null, title);
    s.id = id; h.id = id + "-h";
    s.setAttribute("aria-labelledby", h.id);
    s.appendChild(h);
    document.getElementById("main").appendChild(s);
    return s;
  }

  function figure(host, legendItems, caption) {
    var fig = elem("figure", "chart"), plot = elem("div");
    if (legendItems) fig.appendChild(C.legend(legendItems));
    fig.appendChild(plot);
    if (caption) fig.appendChild(elem("figcaption", null, caption));
    host.appendChild(fig);
    return plot;
  }

  function para(host, cls, s) { var p = elem("p", cls, s); host.appendChild(p); return p; }

  function table(host, head, rows, rowClass) {
    var wrap = elem("div", "scroll"), t = elem("table"), thead = elem("thead"), tr = elem("tr");
    head.forEach(function (h) { tr.appendChild(elem("th", h.num ? "num" : null, h.label || h)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tb = elem("tbody");
    rows.forEach(function (r, i) {
      var row = elem("tr", rowClass ? rowClass(r, i) : null);
      r.cells.forEach(function (c, j) {
        var td = elem("td", head[j] && head[j].num ? "num" : null);
        if (c && c.nodeType) td.appendChild(c); else td.textContent = c;
        row.appendChild(td);
      });
      tb.appendChild(row);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    host.appendChild(wrap);
  }

  function details(host, summary) {
    var d = elem("details");
    d.appendChild(elem("summary", null, summary));
    host.appendChild(d);
    return d;
  }

  /* A caveat from caveats.json, inline. Its ISO dates are read out as dates. */
  function flag(host, d, id) {
    var c = ((d.caveats || {}).items || []).filter(function (x) { return x.id === id; })[0];
    if (!c) return;
    var p = elem("p", "flag");
    p.appendChild(elem("b", null, c.title));
    text(p, " " + c.text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, function (_, iso) { return P.longDate(iso); }));
    host.appendChild(p);
  }

  /* A payee or occupation cell: the name, with its place under it. */
  function named(name, where) {
    var s = elem("span", null, name);
    if (where) s.appendChild(elem("span", "place", where));
    return s;
  }

  function nameWithParty(host, name, p, extra) {
    text(host, name + " ");
    host.appendChild(elem("span", p === "DEM" ? "dem" : "rep", "(" + party(p) + ")"));
    if (extra) text(host, extra);
  }

  function nominees(d) {
    return d.candidates.candidates.filter(function (c) { return c.status === "nominee"; })
      .sort(function (a, b) { return last(a.name) < last(b.name) ? -1 : 1; });
  }

  function committees(d) {
    var dt = d.detail;
    if (!dt || !dt.available || !dt.committees.length) return null;
    return dt.committees.slice().sort(function (a, b) { return last(a.candidate) < last(b.candidate) ? -1 : 1; });
  }

  function key(noms) {
    return noms.map(function (c) {
      return { label: c.name + " (" + party(c.party) + ")" + (c.incumbent ? ", incumbent" : ""),
               color: P.partyColour(c.party), dot: true };
    });
  }

  function both(noms, pick) {
    return noms.map(function (c) { return { label: c.name, color: P.partyColour(c.party), values: pick(c) }; });
  }

  /* ------------------------------------------------------------- the lead */

  function lead(d) {
    var noms = nominees(d), through = P.longDate(d.candidates.coverage_through);
    var s = elem("section", "lead");
    s.id = "standing";
    s.setAttribute("aria-label", "Where the money stands");
    document.getElementById("main").appendChild(s);

    var lede = elem("p", "lede");
    text(lede, "By " + through.replace(/ \d{4}$/, "") + ", ");
    noms.forEach(function (c, i) {
      if (i) text(lede, i === noms.length - 1 ? " and " : ", ");
      text(lede, last(c.name) + (i ? " " : " had raised "));
      lede.appendChild(elem("b", null, said(c.receipts)));
    });
    text(lede, ".");
    s.appendChild(lede);

    para(s, "since", noms.map(function (c) {
      return poss(last(c.name)) + " campaign had spent " + said(c.disbursements) + " and had " +
             said(c.cash_on_hand) + " in the bank";
    }).join("; ") + ". Each figure is cycle to date, from the campaign’s latest quarterly report to the FEC.");

    var plot = figure(s, key(noms), null);
    plot.parentNode.style.marginTop = "1.5rem";
    C.pairs(plot, {
      title: "Raised, spent and cash on hand, by nominee",
      rows: [{ label: "Raised" }, { label: "Spent" }, { label: "Cash on hand" }],
      series: both(noms, function (c) { return [c.receipts, c.disbursements, c.cash_on_hand]; })
    });
    flag(s, d, "vintage");
  }

  /* ------------------------------------------------ where the money came from */

  var SOURCES = [
    { key: "individual_itemized", label: "Donors giving over $200", full: "Individual donors, over $200" },
    { key: "individual_unitemized", label: "Donors giving $200 or less", full: "Small donations, $200 or less" },
    { key: "pac_contributions", label: "Political action committees" },
    { key: "party_contributions", label: "Party committees" },
    { key: "transfers_in", label: "Transfers from own committees", full: "Transfers from another authorized committee" },
    { key: "self_funding", label: "Candidate’s own money" },
    { key: "other", label: "Other" }
  ];

  function sources(d) {
    var noms = nominees(d);
    var sec = section("sources", "Where the money came from");
    var plot = figure(sec, key(noms),
      "Every dollar of receipts by source, as each campaign reported it, with each source’s share of " +
      "that campaign’s total. Each nominee’s bars add up to their total raised.");
    C.pairs(plot, {
      title: "Receipts by source, by nominee",
      rows: SOURCES.map(function (s) { return { label: s.label }; }),
      series: both(noms, function (c) { return SOURCES.map(function (s) { return c[s.key]; }); }),
      valueRoom: 92,
      valueLabel: function (v, i, j) {
        var total = noms[j].receipts, share = total ? v / total : null;
        /* A real $5,000 is not "0%". */
        return fmt.money(v) + (share === null ? "" : " · " + (share > 0 && share < 0.005 ? "<1%" : pct(share, 0)));
      }
    });
    flag(sec, d, "transfer");

    var det = details(sec, "Exact figures");
    var head = [{ label: "Source" }].concat(noms.map(function (c) { return { label: c.name, num: true }; }))
      .concat(noms.map(function (c) { return { label: last(c.name) + ", share", num: true }; }));
    var rows = SOURCES.map(function (s) {
      return { cells: [s.full || s.label].concat(noms.map(function (c) { return money(c[s.key]); }))
        .concat(noms.map(function (c) { return c.receipts ? pct(c[s.key] / c.receipts) : "–"; })) };
    });
    rows.push({ cells: ["Total raised"].concat(noms.map(function (c) { return money(c.receipts); }))
      .concat(noms.map(function () { return "100%"; })), total: true });
    table(det, head, rows, function (r) { return r.total ? "total" : null; });
  }

  /* ------------------------------------------------- what the money bought */

  /* The same rows in the same order for both nominees, so a zero is a zero. */
  var SPEND_ROWS = ["Television advertising", "Digital advertising", "Print and radio advertising",
                    "Mail and printing", "Fundraising", "Staff and payroll", "Consulting",
                    "Polling and research", "Field, phones and texting", "Office and administrative"];

  function bought(d) {
    var cs = committees(d);
    if (!cs) return;
    var sec = section("bought", "What the money bought");
    para(sec, "prose", "Campaigns itemize every payment over $200. Through " +
      P.longDate(d.detail.coverage_through) + ", " + cs.map(function (c, i) {
        return (i ? last(c.candidate) + "’s" : poss(last(c.candidate)) + " campaign") + " itemized " +
               said(c.spending.itemized_total) + " in " + count(c.spending.items) + " payments, " +
               pct(c.spending.in_pa_share, 0) + " of it to Pennsylvania vendors";
      }).join("; ") + ".");

    var rows = SPEND_ROWS.concat(["Everything else"]).map(function (k) { return { label: k }; });
    var plot = figure(sec, cs.map(function (c) {
      return { label: c.candidate + " (" + party(c.party) + ")", color: P.partyColour(c.party), dot: true };
    }), "Itemized spending by what it paid for. “Everything else” is itemized spending outside these ten categories.");
    C.pairs(plot, {
      title: "Itemized spending by category, by nominee",
      rows: rows,
      series: cs.map(function (c) {
        var have = {}, shown = 0;
        c.spending.by_category.forEach(function (r) { have[r.category] = r.amount; });
        var vals = SPEND_ROWS.map(function (k) { shown += have[k] || 0; return have[k] || 0; });
        vals.push(Math.max(0, c.spending.itemized_total - shown));
        return { label: c.candidate, color: P.partyColour(c.party), values: vals };
      })
    });

    var cols = elem("div", "cols");
    cs.forEach(function (c) {
      var col = elem("div"), h = elem("h3");
      text(h, "Largest payees, ");
      nameWithParty(h, c.candidate, c.party);
      col.appendChild(h);
      table(col, ["Payee", { label: "Amount", num: true }], c.spending.top_vendors.map(function (v) {
        return { cells: [named(nice(v.vendor), place(v.city, v.state)), money(v.amount)] };
      }));
      cols.appendChild(col);
    });
    sec.appendChild(cols);
  }

  /* --------------------------------------------------- where the donors are */

  function from(d) {
    var cs = committees(d);
    if (!cs) return;
    var sec = section("from", "Where the donors are");
    var zips = d.detail.in_district_zip_prefixes.join(", ");
    var prose = elem("div", "prose");
    para(prose, null, "Itemized individual contributions, each over $200, by where the donor lives. The " +
      "district share is approximate: it counts zip codes beginning " + zips + ".");
    cs.forEach(function (c) {
      var co = c.contributions, all = co.by_size.reduce(function (a, s) { return a + (s.amount || 0); }, 0);
      var big = co.by_size.filter(function (s) { return s.size >= 2000; })[0];
      para(prose, null, pct(co.in_district_share, 0) + " of " + poss(last(c.candidate)) +
        " itemized individual money came from inside the district. Of all individual money " +
        last(c.candidate) + " reported, " + (big && all ? pct(big.amount / all, 0) : "no share") +
        " came in gifts of $2,000 and over, and " + (all ? pct(co.by_size[0].amount / all, 0) : "no share") +
        " in gifts of $200 or less.");
    });
    sec.appendChild(prose);

    /* One scale for both, or a state that gave $300K to one campaign draws as
       long as a state that gave $700K to the other. */
    var hi = 0;
    cs.forEach(function (c) { c.contributions.by_state.forEach(function (r) { hi = Math.max(hi, r.amount || 0); }); });
    var cols = elem("div", "cols");
    sec.appendChild(cols);
    cs.forEach(function (c) {
      var col = elem("div"), h = elem("h3");
      nameWithParty(h, c.candidate, c.party);
      col.appendChild(h);
      cols.appendChild(col);
      var plot = figure(col, null, null);
      C.hbars(plot, {
        title: "Itemized contributions by state, " + c.candidate, xMax: hi,
        rows: c.contributions.by_state.map(function (r) {
          return { label: r.state, value: r.amount, color: P.partyColour(c.party) };
        })
      });
      col.appendChild(elem("h3", null, "Top occupations, as donors reported them"));
      table(col, ["Occupation", { label: "Amount", num: true }, { label: "Gifts", num: true }],
        c.contributions.by_occupation.map(function (o) {
          return { cells: [nice(o.occupation || "(not stated)"), money(o.amount), count(o.count)] };
        }));
    });
  }

  /* --------------------------------------------------------- outside money */

  function outside(d) {
    var o = d.outside, byName = {};
    d.candidates.candidates.forEach(function (c) { byName[c.name] = c; });
    var sec = section("outside", "Money from outside groups");
    para(sec, "prose", "Groups that spend on their own, without coordinating with any campaign, reported " +
      said(o.total) + " about the two nominees: " + o.by_target.map(function (t) {
        return said(t.supports) + " supporting " + last(t.target) + " and " + said(t.opposes) + " opposing " +
               last(t.target) + ", from " + count(t.committees_supporting + t.committees_opposing) + " committees";
      }).join("; ") + ".");
    flag(sec, d, "primary");
    flag(sec, d, "two-clocks");

    sec.appendChild(elem("h3", null, "The ten largest outside spenders"));
    var plot = figure(sec, null, "Bar colour is the party of the candidate the spending was about; the label says whether it supported or opposed them.");
    C.hbars(plot, {
      title: "Ten largest outside spenders",
      rows: o.rows.slice(0, 10).map(function (r) {
        var c = byName[r.target] || {}, n = nice(r.committee);
        return { label: n + ", " + r.stance + " " + r.target,
                 short: (n.length > 26 ? n.slice(0, 24) + "…" : n) + " · " + r.stance + " " + last(r.target),
                 value: r.amount, color: P.partyColour(c.party) };
      })
    });
    table(details(sec, "Every committee, " + o.rows.length + " rows"),
      ["Committee", "About", "Stance", { label: "Amount", num: true }, { label: "Filings", num: true }],
      o.rows.map(function (r) { return { cells: [nice(r.committee), r.target, r.stance, money(r.amount), count(r.filings)] }; }));

    if (o.by_category && o.by_category.length) {
      sec.appendChild(elem("h3", null, "What outside groups bought"));
      var plot2 = figure(sec, null, "Itemized outside expenditures by what they paid for.");
      C.hbars(plot2, {
        title: "Outside spending by what was bought",
        rows: o.by_category.map(function (r) { return { label: r.category, value: r.amount, color: "#4B5563" }; })
      });
      table(details(sec, "Every expenditure, " + o.itemized.length + " rows"),
        ["Committee", "About", "Stance", "What", "Paid to", { label: "Amount", num: true }, "Date"],
        o.itemized.map(function (r) {
          return { cells: [nice(r.committee), r.target, r.stance, nice(r.what || ""),
                           named(nice(r.payee || ""), place(r.city, r.state)), money(r.amount),
                           r.date ? P.longDate(r.date) : ""] };
        }));
    }
  }

  /* -------------------------------------------------------------- history */

  function history(d) {
    var h = d.history;
    var sec = section("history", "The last four elections");
    var cycles = h.cycles.map(function (c) { return String(c.cycle); });
    function nominee(c, p) { return c.candidates.filter(function (x) { return x.party === p; })[0] || {}; }
    var plot = figure(sec, [{ label: "Democratic nominee", color: P.colours.D, dot: true },
                            { label: "Republican nominee", color: P.colours.R, dot: true }],
      "Money raised by each party’s nominee over the whole cycle, by election. Hover a bar for the exact figure.");
    C.groups(plot, {
      title: "Raised by each nominee, by election",
      categories: cycles,
      series: [{ label: "Democratic nominee", color: P.colours.D, values: h.cycles.map(function (c) { return nominee(c, "DEM").receipts; }) },
               { label: "Republican nominee", color: P.colours.R, values: h.cycles.map(function (c) { return nominee(c, "REP").receipts; }) }]
    });
    var rows = [];
    h.cycles.forEach(function (c) {
      c.candidates.forEach(function (x) {
        rows.push({ cells: [String(c.cycle), x.name + (x.incumbent ? " (incumbent)" : ""),
          elem("span", x.party === "DEM" ? "dem" : x.party === "REP" ? "rep" : null, party(x.party)),
          money(x.receipts), money(x.disbursements), money(x.ie_supporting), money(x.ie_opposing),
          count(x.general_votes), pct(x.two_party_share), x.winner ? "won" : "lost"] });
      });
    });
    table(sec, ["Election", "Candidate", "Party", { label: "Raised", num: true }, { label: "Spent", num: true },
                { label: "Outside, supporting", num: true }, { label: "Outside, opposing", num: true },
                { label: "Votes", num: true }, { label: "Two-party share", num: true }, "Result"], rows);
    var n = para(sec, "flag", "Two-party share is the candidate’s votes divided by Democratic plus Republican votes, so the four elections compare on the same footing. " +
      "District lines changed between 2020 and 2022, so the electorate is not identical across all four. Certified results: ");
    h.cycles.forEach(function (c, i) {
      var a = elem("a", null, String(c.cycle));
      a.href = c.source_url;
      a.title = c.source;
      n.appendChild(a);
      text(n, i < h.cycles.length - 1 ? ", " : ".");
    });
  }

  /* ------------------------------------------------------------ downloads */

  function downloads(d) {
    var wb = d.manifest.workbook, p = document.getElementById("downloads");
    if (!p || !wb || !wb.available) return;
    var a = elem("a", null, "The Excel workbook");
    a.href = wb.href;
    a.setAttribute("download", "");
    p.appendChild(a);
    text(p, " (" + Math.round(wb.bytes / 1024) + " KB) has every figure above, the source-of-funds " +
      "reconciliation, the four-election history, and a money-against-results analysis with its caveats. " +
      "Native Excel charts, no macros.");
  }

  document.addEventListener("data:ready", function (ev) {
    var d = ev.detail;
    [lead, sources, bought, from, outside, history, downloads].forEach(function (fn) {
      try { fn(d); }
      catch (e) { console.error(fn.name, e); }
    });
  });
})();
