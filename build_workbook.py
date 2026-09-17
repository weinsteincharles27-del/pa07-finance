#!/usr/bin/env python3
"""Build PA07_Campaign_Finance.xlsx from sources/.

One pass, nine sheets, thirteen native charts. Every displayed number that is
not a source value is a formula, so the workbook recalculates if a source cell
is edited. Conventions, each of which has caught a real bug in this project:

  - Candidate lookups are keyed by NAME with INDEX/MATCH, never by row, because
    the FEC returns candidates in no guaranteed order.
  - A candidate who never filed stays BLANK. SUM() ignores blanks; rendering $0
    would assert a figure the FEC does not report.
  - INDEX onto a blank cell returns 0. Every lookup that could hit one is
    guarded, and every subtraction checks ISNUMBER on both sides first.
  - Chart series titles come from the header row, one above the first data row.

    python3 build_workbook.py            # writes ./PA07_Campaign_Finance.xlsx
"""
import json
import os
import sys

import classify

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference, ScatterChart, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import Marker
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.trendline import Trendline
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as CL

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "sources")
OUT = os.environ.get("PA07_WORKBOOK", os.path.join(ROOT, "PA07_Campaign_Finance.xlsx"))

# ------------------------------------------------------------------ styling

NAVY, GREY = "1F3864", "595959"
DEM, REP = "2E5FA3", "C0392B"


def F(**k):
    return Font(name="Arial", size=10, **k)


TITLE = Font(name="Arial", size=15, bold=True, color=NAVY)
SUB = Font(name="Arial", size=9, italic=True, color=GREY)
SECT = Font(name="Arial", size=11, bold=True, color="FFFFFF")
HDR = Font(name="Arial", size=9, bold=True, color="FFFFFF")
BODY, BOLD = F(), F(bold=True)
INPUT = F(color="0000FF")
LINK = F(color="008000")
NOTE = Font(name="Arial", size=9, color=GREY)
WRAP = Alignment(wrap_text=True, vertical="top")
SECT_FILL = PatternFill("solid", fgColor=NAVY)
HDR_FILL = PatternFill("solid", fgColor="4472C4")
TOT_FILL = PatternFill("solid", fgColor="D9E2F3")
CALL_FILL = PatternFill("solid", fgColor="FFF2CC")
BLANK_FILL = PatternFill("solid", fgColor="F2F2F2")
WIN_FILL = PatternFill("solid", fgColor="EAF3EA")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = '$#,##0;($#,##0);"-"'
MONEY2 = '$#,##0.00;($#,##0.00);"-"'
PCT = '0.0%;(0.0%);"-"'
PCT2 = '0.00%;(0.00%);"-"'
NUM = '#,##0;(#,##0);"-"'
PP = '+0.00"pp";-0.00"pp";0.00"pp"'
SIG = '+0.0000;-0.0000;0.0000'


def section(ws, row, text, span=8):
    ws.cell(row, 1, text).font = SECT
    for c in range(1, span + 1):
        ws.cell(row, c).fill = SECT_FILL
    ws.row_dimensions[row].height = 18
    return row + 1


def headers(ws, row, cols, widths=None):
    """Write a header row. Returns the FIRST DATA ROW, so a stored anchor's
    header is always at anchor - 1."""
    for i, h in enumerate(cols, start=1):
        c = ws.cell(row, i, h)
        c.font, c.fill, c.border = HDR, HDR_FILL, BOX
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.row_dimensions[row].height = 32
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[CL(i)].width = w
    return row + 1


def note(ws, row, text, span=8, font=NOTE, h=None):
    ws.cell(row, 1, text).font = font
    ws.cell(row, 1).alignment = WRAP
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    ws.row_dimensions[row].height = h or max(13, 12 * (len(text) // (span * 13) + 1))
    return row + 1


def callout(ws, row, text, span=8, h=58):
    c = ws.cell(row, 1, text)
    c.font, c.alignment = F(), WRAP
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    for cc in range(1, span + 1):
        ws.cell(row, cc).fill = CALL_FILL
    ws.row_dimensions[row].height = h
    return row + 1


def box(ws, row, c0, c1, fill=None):
    for cc in range(c0, c1 + 1):
        ws.cell(row, cc).border = BOX
        if fill:
            ws.cell(row, cc).fill = fill


def money_cell(ws, row, col, value, font=INPUT, fmt=MONEY):
    c = ws.cell(row, col, value)
    c.font, c.number_format = font, fmt
    return c


def stance(so):
    return "Supports" if so == "S" else "Opposes"


def nice(name):
    """Title-case an all-caps FEC committee name without wrecking acronyms."""
    small = {"and", "for", "the", "of", "an", "a", "to", "in", "on"}
    upper = {"PA", "PAC", "DLP", "FF", "SURJ", "SEED-PAC", "US", "SEED", "LLC", "USA", "LC", "DC", "NGP", "VAN", "SEIU", "USW"}
    out = []
    for i, w in enumerate(name.split()):
        core = w.strip("(),.")
        if core.upper() in upper:
            out.append(w.replace(core, core.upper()))
        elif core.lower() in small and i > 0:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


def status_of(c):
    if c["nominee"]:
        return "Nominee"
    if c["party"] in ("DEM", "REP"):
        return "Primary candidate"
    return "Declared"


# ==================================================================== build

def build(fec, hist, race, out=OUT, det=None):
    wb = Workbook()
    A = {}                                   # row anchors, the ref-dict convention
    dem_name = next(c["name"] for c in fec["candidates"] if c["nominee"] == "DEM")
    rep_name = next(c["name"] for c in fec["candidates"] if c["nominee"] == "REP")
    NOMS = (dem_name, rep_name)
    cands = sorted(fec["candidates"], key=lambda c: (c["nominee"] is None, -(c["receipts"] or 0)))
    # Outside spending is shown for the two nominees only. Spending about primary
    # candidates who are not on the November ballot stays in sources/ but is not
    # displayed; the same filter is applied in export_site.py and verify.py.
    nominee_ids = {c["candidate_id"] for c in fec["candidates"] if c["nominee"]}
    nominees_only = [c for c in cands if c["nominee"]]

    # ---------------------------------------------------- Candidate Totals
    ct = wb.active
    ct.title = "Candidate Totals"
    ct["A1"] = "Candidate committee totals, PA-07, %d cycle" % fec["cycle"]
    ct["A1"].font = TITLE
    ct["A2"] = ("Cycle-to-date from each committee's latest periodic FEC report. Coverage through %s. "
                "Retrieved %s." % (fec["coverage_through"], fec["retrieved_utc"]))
    ct["A2"].font = SUB
    r = section(ct, 4, "THE TWO NOMINEES", 17)
    cols = ["Candidate", "Party", "Status", "Incumbent", "Filed?", "Coverage through", "Receipts",
            "Disbursements", "Cash on hand", "Debts", "Individual, total",
            "  of which unitemized ($200 or less)", "PAC contributions", "Party committee",
            "Transfers from other authorized committee", "Candidate self-funding",
            "Other / unclassified (derived)"]
    first = headers(ct, r, cols, [26, 7, 17, 10, 12, 13, 14, 14, 14, 11, 15, 16, 15, 13, 17, 15, 16])
    A["CT_FIRST"] = first
    for i, c in enumerate(nominees_only):
        rr = first + i
        ct.cell(rr, 1, c["name"]).font = BODY
        ct.cell(rr, 2, c["party"]).font = BODY
        ct.cell(rr, 3, status_of(c)).font = BODY
        ct.cell(rr, 4, "yes" if c["incumbent"] else "no").font = BODY
        ct.cell(rr, 5, "yes" if c["filed"] else "no report").font = BODY if c["filed"] else F(color="C00000", italic=True)
        ct.cell(rr, 6, c["coverage_end"] or "-").font = BODY
        if c["filed"]:
            for j, k in enumerate(["receipts", "disbursements", "cash_on_hand", "debts",
                                   "individual_contributions", "individual_unitemized",
                                   "pac_contributions", "party_contributions", "transfers_in",
                                   "self_funding"]):
                money_cell(ct, rr, 7 + j, c[k])
            ct.cell(rr, 17, '=IF(ISNUMBER(G{0}),G{0}-(K{0}+M{0}+N{0}+O{0}+P{0}),"")'.format(rr)).font = BODY
            ct.cell(rr, 17).number_format = MONEY
        box(ct, rr, 1, 17, None if c["filed"] else None)
        if not c["filed"]:
            for cc in range(7, 18):
                ct.cell(rr, cc).fill = BLANK_FILL
        if c["nominee"]:
            for cc in range(1, 7):
                ct.cell(rr, cc).font = F(bold=True)
    last = first + len(nominees_only) - 1
    A["CT_LAST"] = last
    tr = last + 1
    A["CT_TOTAL"] = tr
    ct.cell(tr, 1, "TOTAL, both nominees").font = BOLD
    for cc in range(7, 18):
        money_cell(ct, tr, cc, "=SUM({0}{1}:{0}{2})".format(CL(cc), first, last), BOLD)
    box(ct, tr, 1, 17, TOT_FILL)
    ct.cell(r, 12).comment = Comment("A subset of 'Individual, total', not an additional source. "
                                     "Do not add it to the other columns.", "pa07-finance", height=90, width=300)
    ct.cell(r, 17).comment = Comment("Receipts less the identified components: individual + PAC + party + "
                                     "transfers + self-funding. A formula, not a reported FEC field.",
                                     "pa07-finance", height=100, width=300)
    n = tr + 2
    n = note(ct, n, "HOW TO READ THIS TABLE", 17, font=F(bold=True, color=NAVY))
    for t in [
        "This workbook covers the two general-election nominees named in sources/race.json. The FEC lists other declared and primary candidates for the seat; they stay in sources/fec.json and are not shown.",
        "A candidate with no periodic report on file would show BLANK financial cells, not $0. The FEC reports nothing in that case, which is a different claim from 'raised nothing'.",
        "'of which unitemized' is a subset of 'Individual, total'. Adding it to the other source columns double-counts.",
        "Blue figures are values from the FEC API. Black figures are formulas.",
    ]:
        n = note(ct, n, t, 17)
    ct.freeze_panes = ct.cell(first, 2)

    # ------------------------------------------------------- Outside Money
    om = wb.create_sheet("Outside Money")
    om["A1"] = "Outside spending (independent expenditures), PA-07, %d" % fec["cycle"]
    om["A1"].font = TITLE
    om["A2"] = ("Money spent by outside groups on their own to support or oppose one of the two nominees, "
                "without coordinating with the campaign. FEC's deduplicated by_candidate aggregate. Largest first. "
                "Spending about primary candidates not on the November ballot is not shown.")
    om["A2"].font = SUB
    r = section(om, 4, "BY COMMITTEE", 7)
    f_ie = headers(om, r, ["Committee", "Target candidate", "Stance", "Amount", "Filings",
                           "Committee ID", "Share of all outside spending"],
                   [46, 24, 10, 15, 8, 12, 14])
    A["IE_FIRST"] = f_ie
    ies = sorted((e for e in fec["independent_expenditures"] if e["target_candidate_id"] in nominee_ids),
                 key=lambda x: -(x["amount"] or 0))
    for i, e in enumerate(ies):
        rr = f_ie + i
        om.cell(rr, 1, e["committee"]).font = BODY
        om.cell(rr, 2, e["target_candidate"]).font = BODY
        c = om.cell(rr, 3, stance(e["support_oppose"]))
        c.font, c.alignment = BODY, Alignment(horizontal="center")
        money_cell(om, rr, 4, e["amount"], fmt=MONEY2)
        om.cell(rr, 5, e["filings"]).font = BODY
        om.cell(rr, 6, e["committee_id"]).font = BODY
        box(om, rr, 1, 7)
    l_ie = f_ie + len(ies) - 1
    A["IE_LAST"] = l_ie
    t_ie = l_ie + 1
    A["IE_TOTAL"] = t_ie
    for i in range(len(ies)):
        c = om.cell(f_ie + i, 7, '=IFERROR(D{0}/$D${1},"")'.format(f_ie + i, t_ie))
        c.font, c.number_format = BODY, PCT
    om.cell(t_ie, 1, "TOTAL").font = BOLD
    money_cell(om, t_ie, 4, "=SUM(D{0}:D{1})".format(f_ie, l_ie), BOLD, MONEY2)
    c = om.cell(t_ie, 7, '=IFERROR(SUM(G{0}:G{1}),"")'.format(f_ie, l_ie))
    c.font, c.number_format = BOLD, PCT
    box(om, t_ie, 1, 7, TOT_FILL)

    r = section(om, t_ie + 2, "BY TARGET CANDIDATE AND STANCE", 7)
    f_st = headers(om, r, ["Target candidate", "Stance", "Amount", "Committees", "Share", "", ""])
    A["ST_FIRST"] = f_st
    targets = []
    for c in nominees_only:
        for so in ("S", "O"):
            targets.append((c["name"], so))
    for i, (nm, so) in enumerate(targets):
        rr = f_st + i
        om.cell(rr, 1, nm).font = BODY
        om.cell(rr, 2, stance(so)).font = BODY
        money_cell(om, rr, 3, '=SUMIFS($D${0}:$D${1},$B${0}:$B${1},A{2},$C${0}:$C${1},B{2})'
                   .format(f_ie, l_ie, rr), BODY)
        om.cell(rr, 4, '=COUNTIFS($B${0}:$B${1},A{2},$C${0}:$C${1},B{2})'.format(f_ie, l_ie, rr)).font = BODY
        c = om.cell(rr, 5, '=IFERROR(C{0}/$D${1},"")'.format(rr, t_ie))
        c.font, c.number_format = BODY, PCT
        box(om, rr, 1, 5)
    l_st = f_st + len(targets) - 1
    A["ST_LAST"] = l_st
    t_st = l_st + 1
    A["ST_TOTAL"] = t_st
    om.cell(t_st, 1, "TOTAL").font = BOLD
    money_cell(om, t_st, 3, "=SUM(C{0}:C{1})".format(f_st, l_st), BOLD)
    om.cell(t_st, 4, "=SUM(D{0}:D{1})".format(f_st, l_st)).font = BOLD
    box(om, t_st, 1, 5, TOT_FILL)
    n = t_st + 2
    n = note(om, n, "HOW TO READ OUTSIDE SPENDING", 7, font=F(bold=True, color=NAVY))
    for t in fec["notes"]:
        n = note(om, n, "- " + t, 7)
    om.freeze_panes = om.cell(f_ie, 1)

    # ------------------------------------------------- Spending Detail
    NOM_IDS = [c["committee_id"] for c in fec["candidates"] if c["nominee"] and c["committee_id"]]
    NOM_LABEL = {c["committee_id"]: "%s (%s)" % (c["name"], "D" if c["party"] == "DEM" else "R")
                 for c in fec["candidates"] if c["nominee"]}
    det_ok = bool(det) and bool(NOM_IDS) and all(cid in det["committees"] for cid in NOM_IDS)
    sd = wb.create_sheet("Spending Detail")
    sd["A1"] = "What each nominee's campaign spent its money on"
    sd["A1"].font = TITLE
    if det_ok:
        sd["A2"] = ("Itemized disbursements (each over $200), %d cycle, through %s. Categories assigned from the "
                    "description on each report. Retrieved %s." % (det["cycle"], det["coverage_through"], det["retrieved_utc"]))
        sd["A2"].font = SUB
        for i2, w2 in enumerate([30, 15, 9, 8, 15, 9, 8], start=1):
            sd.column_dimensions[CL(i2)].width = w2
        r = section(sd, 4, "SPENDING BY CATEGORY", 7)
        hdrs = ["Category"]
        for cid in NOM_IDS:
            hdrs += [NOM_LABEL[cid], "Share", "Items"]
        f_cat = headers(sd, r, hdrs)
        A["SD_CAT_FIRST"] = f_cat
        cat_amt = {cid: {x["category"]: x for x in det["committees"][cid]["spending"]["by_category"]} for cid in NOM_IDS}
        cats = [c for c in classify.SPENDING_ORDER if any(c in cat_amt[cid] for cid in NOM_IDS)]
        for i, cat in enumerate(cats):
            rr = f_cat + i
            sd.cell(rr, 1, cat).font = BODY
            for j, cid in enumerate(NOM_IDS):
                x = cat_amt[cid].get(cat)
                money_cell(sd, rr, 2 + 3 * j, x["amount"] if x else 0)
                sd.cell(rr, 4 + 3 * j, x["items"] if x else 0).font = INPUT
                sd.cell(rr, 4 + 3 * j).number_format = NUM
            box(sd, rr, 1, 1 + 3 * len(NOM_IDS))
        l_cat = f_cat + len(cats) - 1
        t_cat = l_cat + 1
        A["SD_CAT_LAST"], A["SD_CAT_TOTAL"] = l_cat, t_cat
        sd.cell(t_cat, 1, "TOTAL itemized").font = BOLD
        for j, cid in enumerate(NOM_IDS):
            col = CL(2 + 3 * j)
            money_cell(sd, t_cat, 2 + 3 * j, "=SUM({0}{1}:{0}{2})".format(col, f_cat, l_cat), BOLD)
            c2 = sd.cell(t_cat, 4 + 3 * j, "=SUM({0}{1}:{0}{2})".format(CL(4 + 3 * j), f_cat, l_cat))
            c2.font, c2.number_format = BOLD, NUM
            for i in range(len(cats) + 1):
                c3 = sd.cell(f_cat + i, 3 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                             .format(col, f_cat + i, t_cat))
                c3.font, c3.number_format = (BOLD if i == len(cats) else BODY), PCT
        box(sd, t_cat, 1, 1 + 3 * len(NOM_IDS), TOT_FILL)
        chk = t_cat + 1
        A["SD_CHECK"] = chk
        sd.cell(chk, 1, "Check: categories minus FEC itemized total (must be $0)").font = F(italic=True)
        for j, cid in enumerate(NOM_IDS):
            c2 = sd.cell(chk, 2 + 3 * j, "={0}{1}-{2}".format(CL(2 + 3 * j), t_cat, det["committees"][cid]["spending"]["itemized_total"]))
            c2.font, c2.number_format = F(italic=True), MONEY2
        r = chk + 2
        for j, cid in enumerate(NOM_IDS):
            r = section(sd, r, "LARGEST PAYEES, %s" % NOM_LABEL[cid].upper(), 7)
            f_v = headers(sd, r, ["Payee", "Amount", "Items", "City", "State", "Main category", ""])
            A["SD_VEND_%d" % j] = f_v
            vs = det["committees"][cid]["spending"]["top_vendors"]
            for i, v in enumerate(vs):
                rr = f_v + i
                sd.cell(rr, 1, nice(v["vendor"])).font = BODY
                money_cell(sd, rr, 2, v["amount"])
                sd.cell(rr, 3, v["items"]).font = INPUT
                sd.cell(rr, 4, nice(v["city"] or "")).font = BODY
                sd.cell(rr, 5, v["state"] or "").font = BODY
                sd.cell(rr, 6, v["category"]).font = BODY
                box(sd, rr, 1, 6)
            r = f_v + len(vs) + 1
        r = section(sd, r, "WHERE THE PAYEES ARE", 7)
        hdrs = ["Payee state"]
        for cid in NOM_IDS:
            hdrs += [NOM_LABEL[cid], "Share", ""]
        f_st = headers(sd, r, hdrs)
        A["SD_STATE_FIRST"] = f_st
        st_amt = {cid: {x["state"]: x["amount"] for x in det["committees"][cid]["spending"]["by_vendor_state"]} for cid in NOM_IDS}
        all_states = sorted(set().union(*[set(m) for m in st_amt.values()]),
                            key=lambda st: -sum(st_amt[cid].get(st, 0) for cid in NOM_IDS))
        top_states = all_states[:8]
        for i, st in enumerate(top_states + ["All other"]):
            rr = f_st + i
            sd.cell(rr, 1, st).font = BODY
            for j, cid in enumerate(NOM_IDS):
                if st == "All other":
                    v = sum(st_amt[cid].get(o, 0) for o in all_states[8:])
                else:
                    v = st_amt[cid].get(st, 0)
                money_cell(sd, rr, 2 + 3 * j, round(v, 2))
                c3 = sd.cell(rr, 3 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                             .format(CL(2 + 3 * j), rr, t_cat))
                c3.font, c3.number_format = BODY, PCT
            box(sd, rr, 1, 1 + 3 * len(NOM_IDS))
        A["SD_STATE_LAST"] = f_st + len(top_states)
        n = A["SD_STATE_LAST"] + 2
        for t in det["notes"][:2]:
            n = note(sd, n, "- " + t, 7)
    else:
        note(sd, 3, "sources/fec_detail.json is missing or does not cover both nominees; run collect_fec.py --detail.", 7)

    # ---------------------------------------------------- Donor Detail
    dd = wb.create_sheet("Donor Detail")
    dd["A1"] = "Where each nominee's contributions came from"
    dd["A1"].font = TITLE
    if det_ok:
        dd["A2"] = ("Itemized individual contributions (each over $200), %d cycle, through %s. FEC aggregates. Retrieved %s."
                    % (det["cycle"], det["coverage_through"], det["retrieved_utc"]))
        dd["A2"].font = SUB
        for i2, w2 in enumerate([30, 15, 9, 9, 15, 9, 9], start=1):
            dd.column_dimensions[CL(i2)].width = w2
        r = section(dd, 4, "BY STATE", 7)
        hdrs = ["State"]
        for cid in NOM_IDS:
            hdrs += [NOM_LABEL[cid], "Share", "Gifts"]
        f_s = headers(dd, r, hdrs)
        A["DD_STATE_FIRST"] = f_s
        con = {cid: det["committees"][cid]["contributions"] for cid in NOM_IDS}
        st_map = {cid: {x["state"]: x for x in con[cid]["by_state"]} for cid in NOM_IDS}
        states = sorted(set().union(*[set(m) for m in st_map.values()]),
                        key=lambda st: -sum((st_map[cid].get(st) or {}).get("amount", 0) for cid in NOM_IDS))
        top = states[:10]
        for i, st in enumerate(top + ["All other"]):
            rr = f_s + i
            dd.cell(rr, 1, st).font = BODY
            for j, cid in enumerate(NOM_IDS):
                if st == "All other":
                    amt = sum((st_map[cid].get(o) or {}).get("amount", 0) for o in states[10:])
                    cnt = sum((st_map[cid].get(o) or {}).get("count", 0) or 0 for o in states[10:])
                else:
                    x = st_map[cid].get(st) or {}
                    amt, cnt = x.get("amount", 0), x.get("count", 0)
                money_cell(dd, rr, 2 + 3 * j, round(amt, 2))
                c2 = dd.cell(rr, 4 + 3 * j, cnt)
                c2.font, c2.number_format = INPUT, NUM
            box(dd, rr, 1, 1 + 3 * len(NOM_IDS))
        l_s = f_s + len(top)
        t_s = l_s + 1
        A["DD_STATE_LAST"], A["DD_STATE_TOTAL"] = l_s, t_s
        dd.cell(t_s, 1, "TOTAL itemized").font = BOLD
        for j, cid in enumerate(NOM_IDS):
            col = CL(2 + 3 * j)
            money_cell(dd, t_s, 2 + 3 * j, "=SUM({0}{1}:{0}{2})".format(col, f_s, l_s), BOLD)
            c2 = dd.cell(t_s, 4 + 3 * j, "=SUM({0}{1}:{0}{2})".format(CL(4 + 3 * j), f_s, l_s))
            c2.font, c2.number_format = BOLD, NUM
            for i in range(len(top) + 2):
                c3 = dd.cell(f_s + i, 3 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                             .format(col, f_s + i, t_s))
                c3.font, c3.number_format = (BOLD if i == len(top) + 1 else BODY), PCT
        box(dd, t_s, 1, 1 + 3 * len(NOM_IDS), TOT_FILL)
        r = section(dd, t_s + 2, "BY SIZE OF GIFT", 7)
        hdrs = ["Size of gift"]
        for cid in NOM_IDS:
            hdrs += [NOM_LABEL[cid], "Share", "Gifts"]
        f_z = headers(dd, r, hdrs)
        A["DD_SIZE_FIRST"] = f_z
        sizes = con[NOM_IDS[0]]["by_size"]
        for i, sz in enumerate(sizes):
            rr = f_z + i
            dd.cell(rr, 1, sz["label"]).font = BODY
            for j, cid in enumerate(NOM_IDS):
                x = next((y for y in con[cid]["by_size"] if y["size"] == sz["size"]), None)
                money_cell(dd, rr, 2 + 3 * j, (x or {}).get("amount", 0))
                c2 = dd.cell(rr, 4 + 3 * j, (x or {}).get("count") if x and x.get("count") is not None else None)
                c2.font, c2.number_format = INPUT, NUM
            box(dd, rr, 1, 1 + 3 * len(NOM_IDS))
        l_z = f_z + len(sizes) - 1
        t_z = l_z + 1
        A["DD_SIZE_LAST"], A["DD_SIZE_TOTAL"] = l_z, t_z
        dd.cell(t_z, 1, "TOTAL, all gifts").font = BOLD
        for j, cid in enumerate(NOM_IDS):
            col = CL(2 + 3 * j)
            money_cell(dd, t_z, 2 + 3 * j, "=SUM({0}{1}:{0}{2})".format(col, f_z, l_z), BOLD)
            for i in range(len(sizes) + 1):
                c3 = dd.cell(f_z + i, 3 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                             .format(col, f_z + i, t_z))
                c3.font, c3.number_format = (BOLD if i == len(sizes) else BODY), PCT
        box(dd, t_z, 1, 1 + 3 * len(NOM_IDS), TOT_FILL)
        n = note(dd, t_z + 1, "Gifts of $200 or less are not itemized by donor, so their count is not reported. This table covers all receipts from individuals; the tables above and below cover itemized gifts only.", 7)
        r = section(dd, n + 1, "IN THE DISTRICT", 7)
        hdrs = [""]
        for cid in NOM_IDS:
            hdrs += [NOM_LABEL[cid], "Share", ""]
        f_d = headers(dd, r, hdrs)
        A["DD_DIST_FIRST"] = f_d
        dd.cell(f_d, 1, "From zip codes %s (Lehigh Valley and Poconos)" % ", ".join(p + "xx" for p in det["in_district_zip_prefixes"])).font = BODY
        dd.cell(f_d + 1, 1, "From everywhere else").font = BODY
        dd.cell(f_d + 2, 1, "TOTAL itemized, by zip").font = BOLD
        for j, cid in enumerate(NOM_IDS):
            col = CL(2 + 3 * j)
            money_cell(dd, f_d, 2 + 3 * j, con[cid]["in_district_amount"])
            money_cell(dd, f_d + 2, 2 + 3 * j, con[cid]["zip_total"])
            money_cell(dd, f_d + 1, 2 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2})),{0}{2}-{0}{1},"")'.format(col, f_d, f_d + 2), BODY)
            for i in range(3):
                c3 = dd.cell(f_d + i, 3 + 3 * j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                             .format(col, f_d + i, f_d + 2))
                c3.font, c3.number_format = (BOLD if i == 2 else BODY), PCT
        for i in range(3):
            box(dd, f_d + i, 1, 1 + 3 * len(NOM_IDS), TOT_FILL if i == 2 else None)
        n = note(dd, f_d + 3, "Approximate. The FEC records no district for a donor; zip prefix is the closest available proxy and these prefixes reach slightly beyond the district line.", 7)
        r = n + 1
        for j, cid in enumerate(NOM_IDS):
            r = section(dd, r, "TOP OCCUPATIONS, %s" % NOM_LABEL[cid].upper(), 7)
            f_o = headers(dd, r, ["Occupation, as reported by the donor", "Amount", "Gifts", "", "", "", ""])
            A["DD_OCC_%d" % j] = f_o
            occ = con[cid]["by_occupation"][:10]
            for i, o in enumerate(occ):
                rr = f_o + i
                dd.cell(rr, 1, nice(o["occupation"] or "(not stated)")).font = BODY
                money_cell(dd, rr, 2, o["amount"])
                c2 = dd.cell(rr, 3, o["count"])
                c2.font, c2.number_format = INPUT, NUM
                box(dd, rr, 1, 3)
            r = f_o + len(occ) + 1
        note(dd, r, det["notes"][2], 7)
    else:
        note(dd, 3, "sources/fec_detail.json is missing or does not cover both nominees; run collect_fec.py --detail.", 7)

    # -------------------------------------------------- Outside Detail
    od = wb.create_sheet("Outside Detail")
    od["A1"] = "What each outside group bought"
    od["A1"].font = TITLE
    od["A2"] = ("Every itemized independent expenditure about one of the two nominees, %d cycle. Notices and memo "
                "entries removed; the total equals FEC's by_candidate aggregate for the nominees. Largest first." % fec["cycle"])
    od["A2"].font = SUB
    oi = [x for x in (fec.get("outside_itemized") or []) if x["target_candidate_id"] in nominee_ids]
    for i2, w2 in enumerate([36, 18, 9, 22, 34, 18, 7, 13, 11, 10], start=1):
        od.column_dimensions[CL(i2)].width = w2
    if not oi:
        note(od, 4, "No itemized outside expenditures in sources/fec.json; run collect_fec.py.", 10)
    r = section(od, 4, "BY WHAT WAS BOUGHT", 10) if oi else None
    if oi:
        f_oc = headers(od, r, ["Category", "Amount", "Share", "Items", "", "", "", "", "", ""])
        A["OD_CAT_FIRST"] = f_oc
        ocats = [c for c in classify.OUTSIDE_ORDER if any(x["category"] == c for x in oi)]
        r = section(od, f_oc + len(ocats) + 3, "EVERY ITEMIZED EXPENDITURE", 10)
        f_oi = headers(od, r, ["Committee", "About", "Stance", "What was bought", "Paid to", "City", "State",
                               "Amount", "Category", "Date"])
        A["OI_FIRST"] = f_oi
        for i, x in enumerate(oi):
            rr = f_oi + i
            od.cell(rr, 1, nice(x["committee"] or "")).font = BODY
            od.cell(rr, 2, x["target_candidate"]).font = BODY
            c2 = od.cell(rr, 3, stance(x["support_oppose"]))
            c2.font, c2.alignment = BODY, Alignment(horizontal="center")
            od.cell(rr, 4, nice(x["description"] or "")).font = BODY
            od.cell(rr, 5, nice(x["payee"] or "")).font = BODY
            od.cell(rr, 6, nice(x["payee_city"] or "")).font = BODY
            od.cell(rr, 7, x["payee_state"] or "").font = BODY
            money_cell(od, rr, 8, x["amount"], fmt=MONEY2)
            od.cell(rr, 9, x["category"]).font = BODY
            od.cell(rr, 10, x["date"] or "").font = BODY
            box(od, rr, 1, 10)
        l_oi = f_oi + len(oi) - 1
        t_oi = l_oi + 1
        A["OI_LAST"], A["OI_TOTAL"] = l_oi, t_oi
        od.cell(t_oi, 1, "TOTAL").font = BOLD
        money_cell(od, t_oi, 8, "=SUM(H{0}:H{1})".format(f_oi, l_oi), BOLD, MONEY2)
        box(od, t_oi, 1, 10, TOT_FILL)
        chk = t_oi + 1
        A["OI_CHECK"] = chk
        od.cell(chk, 1, "Check: itemized total minus the by-candidate aggregate on Outside Money (must be $0)").font = F(italic=True)
        c2 = od.cell(chk, 8, "=H{0}-'Outside Money'!D{1}".format(t_oi, A["IE_TOTAL"]))
        c2.font, c2.number_format = F(italic=True), MONEY2
        for i, cat in enumerate(ocats):
            rr = f_oc + i
            od.cell(rr, 1, cat).font = BODY
            money_cell(od, rr, 2, '=SUMIFS($H${0}:$H${1},$I${0}:$I${1},A{2})'.format(f_oi, l_oi, rr), BODY)
            c3 = od.cell(rr, 3, '=IFERROR(B{0}/$H${1},"")'.format(rr, t_oi))
            c3.font, c3.number_format = BODY, PCT
            c4 = od.cell(rr, 4, '=COUNTIFS($I${0}:$I${1},A{2})'.format(f_oi, l_oi, rr))
            c4.font, c4.number_format = BODY, NUM
            box(od, rr, 1, 4)
        l_oc = f_oc + len(ocats) - 1
        t_oc = l_oc + 1
        A["OD_CAT_LAST"], A["OD_CAT_TOTAL"] = l_oc, t_oc
        od.cell(t_oc, 1, "TOTAL").font = BOLD
        money_cell(od, t_oc, 2, "=SUM(B{0}:B{1})".format(f_oc, l_oc), BOLD)
        c4 = od.cell(t_oc, 4, "=SUM(D{0}:D{1})".format(f_oc, l_oc))
        c4.font, c4.number_format = BOLD, NUM
        box(od, t_oc, 1, 4, TOT_FILL)
        od.freeze_panes = od.cell(f_oi, 1)

    # ------------------------------------------------------- Money Sources
    ms = wb.create_sheet("Money Sources")
    ms["A1"] = "Where each nominee's money came from"
    ms["A1"].font = TITLE
    ms["A2"] = "Composition of receipts, and what changes when committee transfers are set aside."
    ms["A2"].font = SUB
    CTF, CTL = A["CT_FIRST"], A["CT_LAST"]

    def idx(col, name):
        """Bare INDEX/MATCH expression into Candidate Totals, keyed by candidate name."""
        return ("INDEX('Candidate Totals'!${c}${f}:${c}${l},MATCH(\"{n}\",'Candidate Totals'!$A${f}:$A${l},0))"
                .format(c=col, f=CTF, l=CTL, n=name))

    def look(col, name, zero_ok=False):
        """The expression wrapped for display: blank on error, and blank on 0 unless
        zero is a legitimate reported value for that column."""
        return ('=IFERROR({0},"")' if zero_ok else '=IFERROR(IF({0}=0,"",{0}),"")').format(idx(col, name))

    r = section(ms, 4, "SOURCE OF FUNDS", 5)
    f_src = headers(ms, r, ["Source of funds", dem_name + " (D)", rep_name + " (R)",
                            "D, share of receipts", "R, share of receipts"], [44, 17, 17, 15, 15])
    A["MS_SRC_FIRST"] = f_src
    srcs = [("Individual, itemized (over $200)", "K", "L", True), ("Individual, unitemized ($200 or less)", "L", None, True),
            ("PAC contributions", "M", None, True), ("Party committee", "N", None, True),
            ("Transfers from another authorized committee", "O", None, True),
            ("Candidate self-funding", "P", None, False), ("Other / unclassified", "Q", None, True)]
    for i, (lab, col, minus, gz) in enumerate(srcs):
        rr = f_src + i
        ms.cell(rr, 1, lab).font = BODY
        for j, nm in enumerate(NOMS):
            if minus:   # itemized = individual total - unitemized
                f = '=IFERROR(IF({0}=0,"",{0}-{1}),"")'.format(idx(col, nm), idx(minus, nm))
            else:
                f = look(col, nm, zero_ok=not gz)
            money_cell(ms, rr, 2 + j, f, LINK)
        box(ms, rr, 1, 5)
    l_src = f_src + len(srcs) - 1
    t_src = l_src + 1
    A["MS_SRC_TOTAL"] = t_src
    ms.cell(t_src, 1, "TOTAL RECEIPTS").font = BOLD
    for j in range(2):
        money_cell(ms, t_src, 2 + j, "=SUM({0}{1}:{0}{2})".format(CL(2 + j), f_src, l_src), BOLD)
    for i in range(len(srcs)):
        for j in range(2):
            c = ms.cell(f_src + i, 4 + j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2})),{0}{1}/{0}{2},"")'
                        .format(CL(2 + j), f_src + i, t_src))
            c.font, c.number_format = BODY, PCT
    for j in range(2):
        c = ms.cell(t_src, 4 + j, '=IFERROR(SUM({0}{1}:{0}{2}),"")'.format(CL(4 + j), f_src, l_src))
        c.font, c.number_format = BOLD, PCT
    box(ms, t_src, 1, 5, TOT_FILL)
    chk = t_src + 1
    A["MS_CHECK"] = chk
    ms.cell(chk, 1, "Check: components minus reported receipts (must be $0)").font = F(italic=True)
    for j, nm in enumerate(NOMS):
        c = ms.cell(chk, 2 + j, '=IFERROR({0}{1}-{2},"")'.format(CL(2 + j), t_src, idx("G", nm)))
        c.font, c.number_format = F(italic=True), MONEY2

    r = section(ms, chk + 2, "THE HEADLINE GAP, AND WHAT IS IN IT", 5)
    f_adj = headers(ms, r, ["Measure", dem_name + " (D)", rep_name + " (R)", "R minus D", ""])
    A["MS_ADJ_FIRST"] = f_adj
    rows_adj = [("Receipts as reported", "G"), ("less: transfers from another authorized committee", "O")]
    for i, (lab, col) in enumerate(rows_adj):
        ms.cell(f_adj + i, 1, lab).font = BODY
        for j, nm in enumerate(NOMS):
            money_cell(ms, f_adj + i, 2 + j, look(col, nm), LINK)
    ex = f_adj + 2
    A["MS_ADJ_LAST"] = ex
    ms.cell(ex, 1, "Receipts excluding committee transfers").font = BOLD
    for j in range(2):
        col = CL(2 + j)
        money_cell(ms, ex, 2 + j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2})),{0}{1}-{0}{2},"")'
                   .format(col, f_adj, f_adj + 1), BOLD)
    for rr in range(f_adj, ex + 1):
        c = ms.cell(rr, 4, '=IF(AND(ISNUMBER(C{0}),ISNUMBER(B{0})),C{0}-B{0},"")'.format(rr))
        c.font, c.number_format = (BOLD if rr == ex else BODY), MONEY
        box(ms, rr, 1, 4, TOT_FILL if rr == ex else None)

    r = section(ms, ex + 2, "SMALL-DOLLAR SHARE", 5)
    f_sd = headers(ms, r, ["Measure", dem_name + " (D)", rep_name + " (R)", "", ""])
    A["MS_SD_FIRST"] = f_sd
    ms.cell(f_sd, 1, "Unitemized contributions ($200 or less)").font = BODY
    ms.cell(f_sd + 1, 1, "as a share of total receipts").font = BODY
    ms.cell(f_sd + 2, 1, "as a share of individual contributions").font = BODY
    for j, nm in enumerate(NOMS):
        col = CL(2 + j)
        money_cell(ms, f_sd, 2 + j, look("L", nm), LINK)
        for k, src in ((1, "G"), (2, "K")):
            c = ms.cell(f_sd + k, 2 + j, '=IFERROR({0}{1}/({2}),"")'.format(col, f_sd, idx(src, nm)))
            c.font, c.number_format = BODY, PCT
    for rr in range(f_sd, f_sd + 3):
        box(ms, rr, 1, 3)

    r = section(ms, f_sd + 4, "SPENDING PACE AND CASH", 5)
    f_sp = headers(ms, r, ["Measure", dem_name + " (D)", rep_name + " (R)", "R minus D", ""])
    A["MS_SP_FIRST"] = f_sp
    for i, lab in enumerate(["Receipts", "Disbursements", "Cash on hand", "Debts owed",
                             "Burn rate (disbursed / raised)", "Cash on hand / receipts"]):
        ms.cell(f_sp + i, 1, lab).font = BODY
    for j, nm in enumerate(NOMS):
        col = CL(2 + j)
        for i, src in enumerate("GHIJ"):
            money_cell(ms, f_sp + i, 2 + j, look(src, nm, zero_ok=(src == "J")), LINK)
        for k, num in ((4, f_sp + 1), (5, f_sp + 2)):
            c = ms.cell(f_sp + k, 2 + j, '=IF(AND(ISNUMBER({0}{1}),ISNUMBER({0}{2}),{0}{2}<>0),{0}{1}/{0}{2},"")'
                        .format(col, num, f_sp))
            c.font, c.number_format = BODY, PCT
    for i in range(6):
        rr = f_sp + i
        c = ms.cell(rr, 4, '=IF(AND(ISNUMBER(C{0}),ISNUMBER(B{0})),C{0}-B{0},"")'.format(rr))
        c.font, c.number_format = BODY, (MONEY if i < 4 else '0.0"pp";(0.0"pp");"-"')
        box(ms, rr, 1, 4)
    n = f_sp + 7
    n = note(ms, n, "Green figures link to Candidate Totals. Black figures are computed here. Debts are what the committee owes and are not netted out of cash on hand.", 5)

    # ------------------------------------------------------------- History
    hs = wb.create_sheet("History")
    hs["A1"] = "PA-07 general elections, %d to %d: finance and results" % (hist["cycles_covered"][0], hist["cycles_covered"][-1])
    hs["A1"].font = TITLE
    hs["A2"] = "Final full-cycle FEC totals and certified vote totals. One row per nominee per election. Retrieved %s." % hist["retrieved_utc"]
    hs["A2"].font = SUB
    r = section(hs, 4, "GENERAL-ELECTION NOMINEES", 19)
    cols = ["Cycle", "Election date", "District map", "Candidate", "Party", "Incumbent", "Receipts",
            "Disbursements", "Cash on hand at year end", "Individual contributions", "PAC contributions",
            "Outside spending supporting", "Outside spending opposing", "Candidate plus aligned outside money",
            "General votes", "Two-party vote share", "Result", "Receipts per vote", "Aligned money per vote"]
    f_h = headers(hs, r, cols, [7, 12, 30, 17, 7, 10, 14, 14, 14, 14, 14, 14, 14, 16, 12, 11, 8, 11, 12])
    A["H_FIRST"] = f_h
    i = 0
    for c in hist["cycles"]:
        for x in c["candidates"]:
            rr = f_h + i
            i += 1
            hs.cell(rr, 1, c["cycle"]).font = INPUT
            hs.cell(rr, 2, c["election_date"]).font = INPUT
            hs.cell(rr, 3, c["map_era"]).font = INPUT
            hs.cell(rr, 3).alignment = WRAP
            hs.cell(rr, 4, x["name"]).font = INPUT
            p = hs.cell(rr, 5, x["party"])
            p.font, p.alignment = F(bold=True, color=DEM if x["party"] == "DEM" else REP), Alignment(horizontal="center")
            hs.cell(rr, 6, "yes" if x["incumbent"] else "no").font = BODY
            for j, k in enumerate(["receipts", "disbursements", "cash_on_hand", "individual_contributions",
                                   "pac_contributions", "ie_supporting", "ie_opposing"]):
                money_cell(hs, rr, 7 + j, x[k])
            hs.cell(rr, 14, '=IF(ISNUMBER(G{r}),G{r}+L{r}+SUMIFS($M${f}:$M${l},$A${f}:$A${l},$A{r},$E${f}:$E${l},"<>"&$E{r}),"")'
                    .format(r=rr, f=f_h, l=f_h + 7)).font = BODY
            hs.cell(rr, 14).number_format = MONEY
            money_cell(hs, rr, 15, x["general_votes"], fmt=NUM)
            hs.cell(rr, 16, '=IF(AND(ISNUMBER(O{r}),SUMIFS($O${f}:$O${l},$A${f}:$A${l},$A{r})<>0),O{r}/SUMIFS($O${f}:$O${l},$A${f}:$A${l},$A{r}),"")'
                    .format(r=rr, f=f_h, l=f_h + 7)).font = BODY
            hs.cell(rr, 16).number_format = PCT2
            w = hs.cell(rr, 17, "won" if x["winner"] else "lost")
            w.font, w.alignment = (F(bold=True) if x["winner"] else F(color=GREY)), Alignment(horizontal="center")
            for col, src in ((18, "G"), (19, "N")):
                c2 = hs.cell(rr, col, '=IF(AND(ISNUMBER({s}{r}),ISNUMBER(O{r}),O{r}<>0),{s}{r}/O{r},"")'.format(s=src, r=rr))
                c2.font, c2.number_format = BODY, MONEY2
            box(hs, rr, 1, 19, WIN_FILL if x["winner"] else None)
    l_h = f_h + i - 1
    A["H_LAST"] = l_h
    hs.cell(r, 14).comment = Comment("This candidate's own receipts, plus outside spending supporting them, plus outside "
                                     "spending opposing their opponent. Money spent against the opponent works in this "
                                     "candidate's favour, so it sits on this side of the ledger.", "pa07-finance", height=120, width=320)
    hs.cell(r, 16).comment = Comment("Votes for this candidate divided by Democratic plus Republican votes. Third-party and "
                                     "write-in votes are excluded so the cycles stay comparable.", "pa07-finance", height=90, width=320)
    hs.freeze_panes = hs.cell(f_h, 4)

    n = l_h + 2
    n = note(hs, n, "TOTAL VOTES CAST, AND WHAT TWO-PARTY SHARE LEAVES OUT", 19, font=F(bold=True, color=NAVY))
    f_v = headers(hs, n, ["Cycle"] + [""] * 13 + ["Total votes cast", "Third-party and write-in", "Third-party share", "Reconciliation", ""])
    A["V_FIRST"] = f_v
    for j, c in enumerate(hist["cycles"]):
        rr = f_v + j
        hs.cell(rr, 1, c["cycle"]).font = INPUT
        hs.cell(rr, 4, "All candidates on the ballot").font = BODY
        money_cell(hs, rr, 15, c["district_total_votes"], fmt=NUM)
        money_cell(hs, rr, 16, c["other_votes"], fmt=NUM)
        c2 = hs.cell(rr, 17, '=IF(AND(ISNUMBER(O{r}),ISNUMBER(P{r}),O{r}<>0),P{r}/O{r},"")'.format(r=rr))
        c2.font, c2.number_format = BODY, PCT2
        c3 = hs.cell(rr, 18, '=IF(NOT(ISNUMBER(O{r})),"not reported",IF(ABS(SUMIF($A${f}:$A${l},$A{r},$O${f}:$O${l})+IF(ISNUMBER(P{r}),P{r},0)-O{r})<0.5,"ok","MISMATCH"))'
                     .format(r=rr, f=f_h, l=l_h))
        c3.font, c3.alignment = BODY, Alignment(horizontal="center")
        box(hs, rr, 1, 18)
        if not c["all_candidate_votes_reported"]:
            for cc in (15, 16, 17):
                hs.cell(rr, cc).fill = BLANK_FILL
    A["V_LAST"] = f_v + len(hist["cycles"]) - 1
    vc = A["V_LAST"] + 1
    A["V_CHECK"] = vc
    hs.cell(vc, 4, "Check: two-party plus third-party equals total, for every cycle that reports a total").font = F(italic=True)
    c = hs.cell(vc, 18, '=COUNTIF(R{0}:R{1},"MISMATCH")'.format(f_v, A["V_LAST"]))
    c.font, c.number_format, c.alignment = F(italic=True), '0" mismatched"', Alignment(horizontal="center")
    n = vc + 2
    n = note(hs, n, "HOW TO READ THIS SHEET", 19, font=F(bold=True, color=NAVY))
    for t in hist["notes"]:
        n = note(hs, n, "- " + t, 19)

    # ---------------------------------------------------- Money vs Results
    mv = wb.create_sheet("Money vs Results")
    for i2, w2 in enumerate([46, 16, 16, 16, 16, 16, 15, 15], start=1):
        mv.column_dimensions[CL(i2)].width = w2
    mv["A1"] = "Does money predict the result in PA-07?"
    mv["A1"].font = TITLE
    mv["A2"] = "Four elections. The Democratic side's share of money against its share of the two-party vote. Links to the History sheet."
    mv["A2"].font = SUB
    HF, HL = A["H_FIRST"], A["H_LAST"]

    def sif(col, cyc, party):
        return ("SUMIFS(History!${c}${f}:${c}${l},History!$A${f}:$A${l},{cy},History!$E${f}:$E${l},\"{p}\")"
                .format(c=col, f=HF, l=HL, cy=cyc, p=party))

    r = section(mv, 4, "CYCLE SUMMARY", 8)
    f_c = headers(mv, r, ["Election cycle", "D candidate receipts", "R candidate receipts", "D share of candidate receipts",
                          "D side, candidate plus aligned outside", "R side, candidate plus aligned outside",
                          "D share of all aligned money", "D two-party vote share"])
    A["MV_FIRST"] = f_c
    for j, c in enumerate(hist["cycles"]):
        rr = f_c + j
        mv.cell(rr, 1, c["cycle"]).font = BOLD
        money_cell(mv, rr, 2, "=" + sif("G", "$A%d" % rr, "DEM"), LINK)
        money_cell(mv, rr, 3, "=" + sif("G", "$A%d" % rr, "REP"), LINK)
        x = mv.cell(rr, 4, '=IF(B{r}+C{r}=0,"",B{r}/(B{r}+C{r}))'.format(r=rr)); x.font, x.number_format = BODY, PCT2
        money_cell(mv, rr, 5, "=" + sif("N", "$A%d" % rr, "DEM"), LINK)
        money_cell(mv, rr, 6, "=" + sif("N", "$A%d" % rr, "REP"), LINK)
        x = mv.cell(rr, 7, '=IF(E{r}+F{r}=0,"",E{r}/(E{r}+F{r}))'.format(r=rr)); x.font, x.number_format = BODY, PCT2
        x = mv.cell(rr, 8, "=" + sif("P", "$A%d" % rr, "DEM")); x.font, x.number_format = LINK, PCT2
        box(mv, rr, 1, 8)
    l_c = f_c + len(hist["cycles"]) - 1
    A["MV_LAST"] = l_c
    r = section(mv, l_c + 2, "CORRELATION AND LINEAR REGRESSION", 8)
    f_r = headers(mv, r, ["Statistic", "Model A: candidate receipts only", "Model B: candidate plus outside money", "", "", "", "", ""])
    A["REG_FIRST"] = f_r
    XA, XB, Y = "D{0}:D{1}".format(f_c, l_c), "G{0}:G{1}".format(f_c, l_c), "H{0}:H{1}".format(f_c, l_c)
    labs = ["Observations (n)", "Pearson correlation r", "R squared (variance explained)",
            "Slope (change in vote share per 1.0 of money share)", "Intercept", "Standard error of the slope",
            "t-statistic for the slope", "p-value (two-tailed)", "Degrees of freedom"]
    for j, lab in enumerate(labs):
        mv.cell(f_r + j, 1, lab).font = BODY
        box(mv, f_r + j, 1, 3)
    rn, rr_, rq, rs, ri, rse, rt, rp, rdf = [f_r + j for j in range(9)]
    for k, X in enumerate((XA, XB)):
        col = CL(2 + k)
        for row, f, fmt in [(rn, '=COUNT({y})', '0'), (rr_, '=IFERROR(CORREL({x},{y}),"")', SIG),
                            (rq, '=IFERROR(RSQ({y},{x}),"")', '0.0000'), (rs, '=IFERROR(SLOPE({y},{x}),"")', SIG),
                            (ri, '=IFERROR(INTERCEPT({y},{x}),"")', '0.0000'),
                            (rse, '=IFERROR(STEYX({y},{x})/SQRT(DEVSQ({x})),"")', '0.00000')]:
            c = mv.cell(row, 2 + k, f.format(x=X, y=Y)); c.font, c.number_format = BODY, fmt
        c = mv.cell(rt, 2 + k, '=IF(AND(ISNUMBER({c}{s}),ISNUMBER({c}{e}),{c}{e}<>0),{c}{s}/{c}{e},"")'.format(c=col, s=rs, e=rse)); c.font, c.number_format = BODY, SIG
        c = mv.cell(rp, 2 + k, '=IF(AND(ISNUMBER({c}{t}),{c}{d}>0),IFERROR(TDIST(ABS({c}{t}),{c}{d},2),""),"")'.format(c=col, t=rt, d=rdf)); c.font, c.number_format = BODY, '0.000'
        c = mv.cell(rdf, 2 + k, '=IF(ISNUMBER({c}{n}),{c}{n}-2,"")'.format(c=col, n=rn)); c.font, c.number_format = BODY, '0'
    A["REG_LAST"] = rdf
    vr = rdf + 1
    A["REG_VERDICT"] = vr
    mv.cell(vr, 1, "Statistically significant at p < 0.05?").font = BOLD
    for k in range(2):
        c = mv.cell(vr, 2 + k, '=IF(ISNUMBER({c}{p}),IF({c}{p}<0.05,"yes","no: cannot reject the null"),"")'.format(c=CL(2 + k), p=rp))
        c.font = F(bold=True, color="C00000")
    box(mv, vr, 1, 3)
    r = section(mv, vr + 2, "MODEL B: FITTED VALUES AND RESIDUALS", 8)
    f_f = headers(mv, r, ["Election cycle", "Actual D two-party vote share", "Predicted by Model B",
                          "Residual (actual minus predicted)", "D share of all aligned money", "", "", ""])
    A["FIT_FIRST"] = f_f
    for j in range(len(hist["cycles"])):
        rr, src = f_f + j, f_c + j
        mv.cell(rr, 1, "=A%d" % src).font = LINK
        x = mv.cell(rr, 2, "=H%d" % src); x.font, x.number_format = LINK, PCT2
        x = mv.cell(rr, 3, '=IF(AND(ISNUMBER($C${i}),ISNUMBER($C${s}),ISNUMBER(E{r})),$C${i}+$C${s}*E{r},"")'.format(i=ri, s=rs, r=rr)); x.font, x.number_format = BODY, PCT2
        x = mv.cell(rr, 4, '=IF(AND(ISNUMBER(B{r}),ISNUMBER(C{r})),B{r}-C{r},"")'.format(r=rr)); x.font, x.number_format = BODY, PP
        x = mv.cell(rr, 5, "=G%d" % src); x.font, x.number_format = LINK, PCT2
        box(mv, rr, 1, 5)
    A["FIT_LAST"] = f_f + len(hist["cycles"]) - 1
    n = A["FIT_LAST"] + 2
    n = section(mv, n, "WHAT THIS DOES AND DOES NOT ESTABLISH", 8)
    for t in [
        "n = 4. This cannot support a statistical claim. With four elections and two fitted parameters there are two degrees of freedom, and the confidence interval on the slope is wider than any effect it could detect. The regression is reported because it was asked for and because it disciplines the description, not because it licenses an inference. Treat every figure above as descriptive.",
        "Model A is the one that matters, and it finds nothing. The Democratic share of candidate fundraising has essentially no relationship to the Democratic share of the vote in this district (R squared near zero). 2024 is decisive on its own: Susan Wild raised 83% of all candidate money in the race and lost it.",
        "Model B does better because it counts the outside money. Once independent expenditures are added, including money spent attacking the opponent, the relationship turns positive. It is still not significant at n = 4, and the ordering is dominated by 2018, a Democratic wave year in which the Republican was barely funded.",
        "The causation runs both ways, and mostly backwards. Money flows toward races already expected to be close, and toward candidates already expected to win. A positive correlation is as consistent with 'donors can spot a winner' as with 'spending buys votes'. Nothing here separates the two.",
        "The omitted variable is the national environment. 2018 was a Democratic wave; 2024 was a Republican-leaning presidential year in a district trending right. Those two facts explain the vote-share series better than money does, and they are not in the model.",
    ]:
        n = callout(mv, n, t, 8, 56)

    # ------------------------------------------------------------- Summary
    su = wb.create_sheet("Summary", 0)
    for i2, w2 in enumerate([52, 17, 17, 17, 14, 14, 14, 14], start=1):
        su.column_dimensions[CL(i2)].width = w2
    su["A1"] = "PA-07 campaign finance: where the money is"
    su["A1"].font = TITLE
    su["A2"] = ("Pennsylvania's 7th congressional district. %s (D) and %s (R). General election %s. Source: FEC."
                % (dem_name, rep_name, race["election_date"]))
    su["A2"].font = SUB
    r = section(su, 4, "DATA VINTAGE, READ THIS FIRST", 8)
    su.cell(r, 1, "Candidate committee totals current through").font = BODY
    c = su.cell(r, 2, fec["coverage_through"]); c.font, c.alignment = F(bold=True, color="C00000"), Alignment(horizontal="left")
    su.cell(r, 3, "Latest periodic FEC report on file for the nominees").font = NOTE
    su.cell(r + 1, 1, "Outside spending").font = BODY
    c = su.cell(r + 1, 2, "continuous"); c.font, c.alignment = F(bold=True), Alignment(horizontal="left")
    su.cell(r + 1, 3, "Reported as it happens; fresher than the candidate totals").font = NOTE
    su.cell(r + 2, 1, "Data retrieved").font = BODY
    c = su.cell(r + 2, 2, fec["retrieved_utc"]); c.font, c.alignment = BODY, Alignment(horizontal="left")
    nxt = race.get("next_periodic_report") or {}
    su.cell(r + 2, 3, "Next candidate report: %s, due %s" % (nxt.get("name", "?"), nxt.get("due", "?"))).font = NOTE
    r = section(su, r + 4, "MONEY AT A GLANCE", 8)
    f_g = headers(su, r, ["", dem_name + " (D)", rep_name + " (R)", "R minus D", "", "", "", ""])
    SP, ADJ, ADJE = A["MS_SP_FIRST"], A["MS_ADJ_FIRST"], A["MS_ADJ_LAST"]
    grows = [("Total receipts", ADJ, MONEY), ("  less: transfers from another committee", ADJ + 1, MONEY),
             ("Receipts excluding transfers", ADJE, MONEY), ("Disbursements", SP + 1, MONEY),
             ("Cash on hand", SP + 2, MONEY), ("Debts owed", SP + 3, MONEY), ("Burn rate (disbursed / raised)", SP + 4, PCT)]
    for i, (lab, src, fmt) in enumerate(grows):
        rr = f_g + i
        su.cell(rr, 1, lab).font = BODY if lab.startswith("  ") else BOLD
        for j in range(2):
            x = su.cell(rr, 2 + j, "='Money Sources'!%s%d" % (CL(2 + j), src)); x.font, x.number_format = LINK, fmt
        d = su.cell(rr, 4, '=IF(AND(ISNUMBER(C{0}),ISNUMBER(B{0})),C{0}-B{0},"")'.format(rr))
        d.font, d.number_format = BOLD, (fmt if fmt == MONEY else '0.0"pp";(0.0"pp");"-"')
        box(su, rr, 1, 4, TOT_FILL if lab in ("Receipts excluding transfers", "Cash on hand") else None)
    l_g = f_g + len(grows) - 1
    r = section(su, l_g + 2, "OUTSIDE SPENDING", 8)
    f_o = headers(su, r, ["", "Amount", "Share of all outside spending", "Committees", "", "", "", ""])
    su.cell(f_o, 1, "All independent expenditures about the two nominees").font = BOLD
    money_cell(su, f_o, 2, "='Outside Money'!D%d" % A["IE_TOTAL"], LINK)
    su.cell(f_o, 4, "='Outside Money'!D%d" % A["ST_TOTAL"]).font = LINK
    box(su, f_o, 1, 4, TOT_FILL)
    orow = f_o + 1
    for c in nominees_only:
        for so in ("S", "O"):
            idx = targets.index((c["name"], so))
            su.cell(orow, 1, "%s, %s" % (c["name"], stance(so).lower())).font = BODY
            money_cell(su, orow, 2, "='Outside Money'!C%d" % (A["ST_FIRST"] + idx), LINK)
            x = su.cell(orow, 3, '=IFERROR(B{0}/$B${1},"")'.format(orow, f_o)); x.font, x.number_format = BODY, PCT
            su.cell(orow, 4, "='Outside Money'!D%d" % (A["ST_FIRST"] + idx)).font = LINK
            box(su, orow, 1, 4)
            orow += 1
    A["SU_OUT_LAST"] = orow - 1
    r = section(su, orow + 1, "THE LAST FOUR ELECTIONS", 8)
    su.cell(r, 1, "").font = HDR
    for i, c in enumerate(hist["cycles"]):
        x = su.cell(r, 2 + i, str(c["cycle"])); x.font, x.fill, x.border = HDR, HDR_FILL, BOX
        x.alignment = Alignment(horizontal="center")
    su.cell(r, 1).fill, su.cell(r, 1).border = HDR_FILL, BOX
    r += 1
    MF = A["MV_FIRST"]
    for lab, col in [("Democratic share of candidate receipts", "D"), ("Democratic share of all aligned money", "G"),
                     ("Democratic two-party vote share", "H")]:
        su.cell(r, 1, lab).font = BODY
        for i in range(len(hist["cycles"])):
            x = su.cell(r, 2 + i, "='Money vs Results'!%s%d" % (col, MF + i)); x.font, x.number_format = LINK, PCT2
        box(su, r, 1, 1 + len(hist["cycles"]))
        r += 1
    su.cell(r, 1, "Democratic result").font = BOLD
    for i, c in enumerate(hist["cycles"]):
        d = next(x for x in c["candidates"] if x["party"] == "DEM")
        x = su.cell(r, 2 + i, "won" if d["winner"] else "lost")
        x.font, x.alignment = F(bold=True), Alignment(horizontal="center")
    box(su, r, 1, 1 + len(hist["cycles"]))
    r += 2
    RF = A["REG_FIRST"]
    for lab, col in [("Correlation, candidate receipts share vs vote share (Model A)", "B"),
                     ("Correlation, all aligned money share vs vote share (Model B)", "C")]:
        su.cell(r, 1, lab).font = BODY
        x = su.cell(r, 2, "='Money vs Results'!%s%d" % (col, RF + 1)); x.font, x.number_format = F(bold=True, color=NAVY), '+0.0000;-0.0000'
        x = su.cell(r, 3, "='Money vs Results'!%s%d" % (col, RF + 7)); x.font, x.number_format = BODY, '"p = "0.000'
        box(su, r, 1, 3)
        r += 1
    r += 1
    r = section(su, r, "TWO FACTS THE MONEY MUST BE READ WITH", 8)
    r = callout(su, r, "1. The two halves are not as of the same date. Candidate totals stop at the latest periodic report and are usually months stale. Outside spending reports continuously. Do not compare a candidate figure and an outside-money figure as though they were measured on the same day.", 8, 50)
    r = callout(su, r, "2. Much of this money was not spent on the November race. The largest outside-spending committees were active in May 2026, inside the contested Democratic primary, and a large share of the Republican nominee's receipts is a transfer from a wound-down joint committee rather than new donor money. The naive reading of the headline totals is wrong in a way that changes the conclusion.", 8, 62)
    r = note(su, r + 1, "Green figures link to other sheets. Navy figures are computed here. Nothing on this sheet is typed in by hand.", 8)

    # ------------------------------------------------------------- Charts
    ch = wb.create_sheet("Charts", 1)
    ch["A1"] = "Where the money is: charts"
    ch["A1"].font = TITLE
    ch["A2"] = "Every series links to the data sheets. Chart source data sits in columns R onward."
    ch["A2"].font = SUB
    ch.column_dimensions["A"].width = 3
    for col in "RSTUVWXYZ":
        ch.column_dimensions[col].width = 22
    ch.sheet_view.showGridLines = False

    def blk(ws, row, label):
        ws.cell(row, 18, label).font = F(bold=True, color=NAVY)

    def hdr(ws, row, labels):
        for j, l in enumerate(labels):
            ws.cell(row, 18 + j, l).font = HDR

    def style(c, title, ytitle=None, xtitle=None, w=22, h=11):
        c.title, c.style, c.width, c.height = title, None, w, h
        if ytitle:
            c.y_axis.title = ytitle
        if xtitle:
            c.x_axis.title = xtitle
        if getattr(c.y_axis, "majorGridlines", None) is not None:
            c.y_axis.majorGridlines.spPr = GraphicalProperties(ln=None)
        c.x_axis.delete = c.y_axis.delete = False

    def paint(s, col):
        s.graphicalProperties.solidFill = col
        s.graphicalProperties.line.solidFill = col

    def points(s, cols):
        s.data_points = [DataPoint(idx=i, spPr=GraphicalProperties(solidFill=c)) for i, c in enumerate(cols)]

    blk(ch, 2, "CHART 1: receipts, spending and cash")
    hdr(ch, 3, ["Metric", dem_name + " (D)", rep_name + " (R)"])
    for i, (lab, off) in enumerate([("Receipts", 0), ("Disbursements", 1), ("Cash on hand", 2)]):
        ch.cell(4 + i, 18, lab).font = BODY
        for j in range(2):
            money_cell(ch, 4 + i, 19 + j, "='Money Sources'!%s%d" % (CL(2 + j), SP + off), LINK)
    blk(ch, 8, "CHART 2: receipts by source")
    src_labels = [s[0] for s in srcs]
    hdr(ch, 9, ["Candidate"] + src_labels)
    for i, nm in enumerate(NOMS):
        ch.cell(10 + i, 18, nm + (" (D)" if i == 0 else " (R)")).font = BODY
        for j in range(len(srcs)):
            money_cell(ch, 10 + i, 19 + j, "='Money Sources'!%s%d" % (CL(2 + i), A["MS_SRC_FIRST"] + j), LINK)
    blk(ch, 13, "CHART 3: headline receipts against receipts excluding transfers")
    hdr(ch, 14, ["Measure", dem_name + " (D)", rep_name + " (R)"])
    for i, (lab, row) in enumerate([("Receipts as reported", ADJ), ("Excluding committee transfers", ADJE)]):
        ch.cell(15 + i, 18, lab).font = BODY
        for j in range(2):
            money_cell(ch, 15 + i, 19 + j, "='Money Sources'!%s%d" % (CL(2 + j), row), LINK)
    blk(ch, 18, "CHART 4: ten largest outside spenders")
    hdr(ch, 19, ["Committee", "Independent expenditure"])
    top = ies[:10]
    for i, e in enumerate(top):
        ch.cell(20 + i, 18, "%s (%s %s)" % (nice(e["committee"]), stance(e["support_oppose"]).lower(), e["target_candidate"].split()[-1])).font = BODY
        money_cell(ch, 20 + i, 19, "='Outside Money'!D%d" % (A["IE_FIRST"] + i), LINK)
    blk(ch, 31, "CHART 5: outside spending by target and stance")
    hdr(ch, 32, ["Target and stance", "Amount"])
    nz = [(i, t) for i, t in enumerate(targets)]
    for k, (i, (nm, so)) in enumerate(nz):
        ch.cell(33 + k, 18, "%s, %s" % (nm.split()[-1], stance(so).lower())).font = BODY
        money_cell(ch, 33 + k, 19, "='Outside Money'!C%d" % (A["ST_FIRST"] + i), LINK)
    r5_last = 33 + len(nz) - 1
    c6_top = r5_last + 3
    blk(ch, c6_top - 1, "CHART 6: concentration of outside spending")
    hdr(ch, c6_top, ["Committee", "Outside spending"])
    NTOP = 6
    for i, e in enumerate(ies[:NTOP]):
        ch.cell(c6_top + 1 + i, 18, nice(e["committee"])).font = BODY
        money_cell(ch, c6_top + 1 + i, 19, "='Outside Money'!D%d" % (A["IE_FIRST"] + i), LINK)
    c6_other = c6_top + 1 + NTOP
    ch.cell(c6_other, 18, "All other (%d committees)" % (len(ies) - NTOP)).font = BODY
    money_cell(ch, c6_other, 19, "='Outside Money'!D{0}-SUM('Outside Money'!D{1}:D{2})".format(A["IE_TOTAL"], A["IE_FIRST"], A["IE_FIRST"] + NTOP - 1), LINK)

    c1 = BarChart(); c1.type, c1.grouping = "col", "clustered"
    c1.add_data(Reference(ch, min_col=19, max_col=20, min_row=3, max_row=6), titles_from_data=True)
    c1.set_categories(Reference(ch, min_col=18, min_row=4, max_row=6))
    style(c1, "1. Receipts, spending and cash on hand", "US dollars"); paint(c1.series[0], DEM); paint(c1.series[1], REP)
    c1.y_axis.numFmt = '$#,##0.0,,"M"'; ch.add_chart(c1, "A4")
    c2 = BarChart(); c2.type, c2.grouping, c2.overlap = "col", "stacked", 100
    c2.add_data(Reference(ch, min_col=19, max_col=18 + len(srcs), min_row=9, max_row=11), titles_from_data=True)
    c2.set_categories(Reference(ch, min_col=18, min_row=10, max_row=11))
    style(c2, "2. Where each nominee's receipts came from", "US dollars")
    for s, col in zip(c2.series, ["1F4E79", "2E75B6", "7EA6D9", "A9C6E8", "E8A33D", "7F7F7F", "D9D9D9"]):
        paint(s, col)
    c2.y_axis.numFmt = '$#,##0.0,,"M"'; ch.add_chart(c2, "A27")
    c3 = BarChart(); c3.type, c3.grouping = "col", "clustered"
    c3.add_data(Reference(ch, min_col=19, max_col=20, min_row=14, max_row=16), titles_from_data=True)
    c3.set_categories(Reference(ch, min_col=18, min_row=15, max_row=16))
    style(c3, "3. The headline gap is mostly one committee transfer", "US dollars"); paint(c3.series[0], DEM); paint(c3.series[1], REP)
    c3.y_axis.numFmt = '$#,##0.0,,"M"'; ch.add_chart(c3, "A50")
    c4 = BarChart(); c4.type = "bar"
    c4.add_data(Reference(ch, min_col=19, min_row=19, max_row=19 + len(top)), titles_from_data=True)
    c4.set_categories(Reference(ch, min_col=18, min_row=20, max_row=19 + len(top)))
    style(c4, "4. The ten largest outside spenders", "", "US dollars", w=24, h=13)
    paint(c4.series[0], "1F4E79"); c4.legend = None; c4.x_axis.numFmt = '$#,##0,"K"'; ch.add_chart(c4, "A73")
    c5 = BarChart(); c5.type = "col"
    c5.add_data(Reference(ch, min_col=19, min_row=32, max_row=r5_last), titles_from_data=True)
    c5.set_categories(Reference(ch, min_col=18, min_row=33, max_row=r5_last))
    style(c5, "5. Outside spending by target and stance", "US dollars", w=26, h=12)
    paint(c5.series[0], "1F4E79"); c5.legend = None; c5.y_axis.numFmt = '$#,##0.0,,"M"'; ch.add_chart(c5, "A99")
    c6 = PieChart()
    c6.add_data(Reference(ch, min_col=19, min_row=c6_top, max_row=c6_other), titles_from_data=True)
    c6.set_categories(Reference(ch, min_col=18, min_row=c6_top + 1, max_row=c6_other))
    c6.title, c6.width, c6.height = "6. Outside spending is concentrated", 20, 12
    c6.dataLabels = DataLabelList(); c6.dataLabels.showPercent = True
    points(c6.series[0], ["1F4E79", "C0392B", "2E75B6", "7EA6D9", "5B9BD5", "A9C6E8", "D9D9D9"])
    ch.add_chart(c6, "A124")

    # ---- detail charts (7 to 9), on the same sheet, source blocks below the others
    if det_ok:
        b7 = c6_other + 3
        blk(ch, b7 - 1, "CHART 7: spending by category")
        hdr(ch, b7, ["Category"] + [NOM_LABEL[cid] for cid in NOM_IDS])
        n7 = min(8, A["SD_CAT_LAST"] - A["SD_CAT_FIRST"] + 1)
        for i in range(n7):
            src = A["SD_CAT_FIRST"] + i
            ch.cell(b7 + 1 + i, 18, "='Spending Detail'!A%d" % src).font = LINK
            for j in range(len(NOM_IDS)):
                money_cell(ch, b7 + 1 + i, 19 + j, "='Spending Detail'!%s%d" % (CL(2 + 3 * j), src), LINK)
        c7 = BarChart(); c7.type, c7.grouping = "bar", "clustered"
        c7.add_data(Reference(ch, min_col=19, max_col=18 + len(NOM_IDS), min_row=b7, max_row=b7 + n7), titles_from_data=True)
        c7.set_categories(Reference(ch, min_col=18, min_row=b7 + 1, max_row=b7 + n7))
        style(c7, "7. What the campaigns spent on, largest categories", "", "US dollars", w=24, h=13)
        paint(c7.series[0], DEM); paint(c7.series[1], REP); c7.x_axis.numFmt = '$#,##0,"K"'
        ch.add_chart(c7, "A149")

        b8 = b7 + n7 + 3
        blk(ch, b8 - 1, "CHART 8: contributions by state")
        hdr(ch, b8, ["State"] + [NOM_LABEL[cid] for cid in NOM_IDS])
        n8 = min(8, A["DD_STATE_LAST"] - A["DD_STATE_FIRST"] + 1)
        for i in range(n8):
            src = A["DD_STATE_FIRST"] + i
            ch.cell(b8 + 1 + i, 18, "='Donor Detail'!A%d" % src).font = LINK
            for j in range(len(NOM_IDS)):
                money_cell(ch, b8 + 1 + i, 19 + j, "='Donor Detail'!%s%d" % (CL(2 + 3 * j), src), LINK)
        c8 = BarChart(); c8.type, c8.grouping = "col", "clustered"
        c8.add_data(Reference(ch, min_col=19, max_col=18 + len(NOM_IDS), min_row=b8, max_row=b8 + n8), titles_from_data=True)
        c8.set_categories(Reference(ch, min_col=18, min_row=b8 + 1, max_row=b8 + n8))
        style(c8, "8. Where the itemized contributions came from", "US dollars", "Donor state")
        paint(c8.series[0], DEM); paint(c8.series[1], REP); c8.y_axis.numFmt = '$#,##0,"K"'
        ch.add_chart(c8, "A174")

        b9 = b8 + n8 + 3
        blk(ch, b9 - 1, "CHART 9: what outside groups bought")
        hdr(ch, b9, ["Category", "Outside spending"])
        n9 = A["OD_CAT_LAST"] - A["OD_CAT_FIRST"] + 1
        for i in range(n9):
            src = A["OD_CAT_FIRST"] + i
            ch.cell(b9 + 1 + i, 18, "='Outside Detail'!A%d" % src).font = LINK
            money_cell(ch, b9 + 1 + i, 19, "='Outside Detail'!B%d" % src, LINK)
        c9 = BarChart(); c9.type = "bar"
        c9.add_data(Reference(ch, min_col=19, min_row=b9, max_row=b9 + n9), titles_from_data=True)
        c9.set_categories(Reference(ch, min_col=18, min_row=b9 + 1, max_row=b9 + n9))
        style(c9, "9. What the outside groups bought", "", "US dollars", w=22, h=11)
        paint(c9.series[0], "1F4E79"); c9.legend = None; c9.x_axis.numFmt = '$#,##0.0,,"M"'
        ch.add_chart(c9, "A199")
        A["N_CHARTS"] = 16
    else:
        A["N_CHARTS"] = 13

    # ----------------------------------------------------- History Charts
    hc = wb.create_sheet("History Charts")
    hc["A1"] = "Money and results, %d to %d" % (hist["cycles_covered"][0], hist["cycles_covered"][-1])
    hc["A1"].font = TITLE
    hc["A2"] = "Every series links to the History and Money vs Results sheets. Source data in columns R onward."
    hc["A2"].font = SUB
    hc.column_dimensions["A"].width = 3
    for col in "RSTUVW":
        hc.column_dimensions[col].width = 24
    hc.sheet_view.showGridLines = False
    CYC = [c["cycle"] for c in hist["cycles"]]
    MVS = "'Money vs Results'"
    blk(hc, 2, "CHART 1: all aligned money by cycle"); hdr(hc, 3, ["Cycle", "Democratic side", "Republican side"])
    blk(hc, 9, "CHART 2: candidate receipts by cycle"); hdr(hc, 10, ["Cycle", "Democratic nominee", "Republican nominee"])
    blk(hc, 16, "CHART 3: aligned money share vs vote share (Model B)"); hdr(hc, 17, ["Cycle", "D share of all aligned money", "D two-party vote share"])
    blk(hc, 23, "CHART 4: receipts share vs vote share (Model A)"); hdr(hc, 24, ["Cycle", "D share of candidate receipts", "D two-party vote share"])
    blk(hc, 30, "CHART 5: Democratic two-party vote share"); hdr(hc, 31, ["Cycle", "D two-party vote share", "50%"])
    blk(hc, 37, "CHART 6: candidate money vs outside money"); hdr(hc, 38, ["Cycle", "Candidate committees", "Outside spending"])
    for i, cy in enumerate(CYC):
        rr = MF + i
        for base in (4, 11, 18, 25, 32, 39):
            hc.cell(base + i, 18, cy).font = BODY
        money_cell(hc, 4 + i, 19, "=%s!E%d" % (MVS, rr), LINK); money_cell(hc, 4 + i, 20, "=%s!F%d" % (MVS, rr), LINK)
        money_cell(hc, 11 + i, 19, "=%s!B%d" % (MVS, rr), LINK); money_cell(hc, 11 + i, 20, "=%s!C%d" % (MVS, rr), LINK)
        for base, col in ((18, "G"), (25, "D")):
            x = hc.cell(base + i, 19, "=%s!%s%d" % (MVS, col, rr)); x.font, x.number_format = LINK, PCT2
            x = hc.cell(base + i, 20, "=%s!H%d" % (MVS, rr)); x.font, x.number_format = LINK, PCT2
        x = hc.cell(32 + i, 19, "=%s!H%d" % (MVS, rr)); x.font, x.number_format = LINK, PCT2
        x = hc.cell(32 + i, 20, 0.5); x.font, x.number_format = BODY, PCT2
        money_cell(hc, 39 + i, 19, "={m}!B{r}+{m}!C{r}".format(m=MVS, r=rr), LINK)
        money_cell(hc, 39 + i, 20, "=({m}!E{r}+{m}!F{r})-({m}!B{r}+{m}!C{r})".format(m=MVS, r=rr), LINK)
    blk(hc, 44, "CHART 7: receipts per vote received"); hdr(hc, 45, ["Candidate", "Receipts per vote"])
    i = 0; pv_cols = []
    for c in hist["cycles"]:
        for x in c["candidates"]:
            hc.cell(46 + i, 18, "%d %s (%s)" % (c["cycle"], x["name"].split()[-1], "D" if x["party"] == "DEM" else "R")).font = BODY
            money_cell(hc, 46 + i, 19, "=History!R%d" % (A["H_FIRST"] + i), LINK, MONEY2)
            pv_cols.append(DEM if x["party"] == "DEM" else REP); i += 1
    NPV = i
    n4 = 3 + len(CYC)
    h1 = BarChart(); h1.type, h1.grouping, h1.overlap = "col", "stacked", 100
    h1.add_data(Reference(hc, min_col=19, max_col=20, min_row=3, max_row=n4), titles_from_data=True)
    h1.set_categories(Reference(hc, min_col=18, min_row=4, max_row=n4))
    style(h1, "1. All aligned money in the race, by cycle", "US dollars", "Election cycle"); paint(h1.series[0], DEM); paint(h1.series[1], REP)
    h1.y_axis.numFmt = '$#,##0.0,,"M"'; hc.add_chart(h1, "A4")
    h2 = BarChart(); h2.type, h2.grouping = "col", "clustered"
    h2.add_data(Reference(hc, min_col=19, max_col=20, min_row=10, max_row=10 + len(CYC)), titles_from_data=True)
    h2.set_categories(Reference(hc, min_col=18, min_row=11, max_row=10 + len(CYC)))
    style(h2, "2. Candidate committee receipts, by cycle", "US dollars", "Election cycle"); paint(h2.series[0], DEM); paint(h2.series[1], REP)
    h2.y_axis.numFmt = '$#,##0.0,,"M"'; hc.add_chart(h2, "A27")
    for anchor, base, title, xt in (("A50", 18, "3. All aligned money vs result (Model B): positive, but n = 4", "Democratic share of all aligned money"),
                                    ("A75", 25, "4. Candidate fundraising vs result (Model A): no relationship", "Democratic share of candidate receipts")):
        sc = ScatterChart(); sc.title, sc.style, sc.width, sc.height = title, None, 22, 12
        sc.x_axis.title, sc.y_axis.title = xt, "Democratic two-party vote share"
        ser = Series(Reference(hc, min_col=20, min_row=base, max_row=base + len(CYC) - 1),
                     Reference(hc, min_col=19, min_row=base, max_row=base + len(CYC) - 1), title="Elections %d to %d" % (CYC[0], CYC[-1]))
        ser.marker = Marker(symbol="circle", size=9); ser.graphicalProperties.line.noFill = True
        ser.trendline = Trendline(trendlineType="linear", dispRSqr=True, dispEq=True)
        sc.series.append(ser); sc.x_axis.numFmt = sc.y_axis.numFmt = "0%"; sc.x_axis.delete = sc.y_axis.delete = False
        hc.add_chart(sc, anchor)
    h5 = LineChart()
    h5.add_data(Reference(hc, min_col=19, max_col=20, min_row=31, max_row=31 + len(CYC)), titles_from_data=True)
    h5.set_categories(Reference(hc, min_col=18, min_row=32, max_row=31 + len(CYC)))
    style(h5, "5. Democratic two-party vote share, by cycle", "Two-party vote share", "Election cycle")
    h5.series[0].graphicalProperties.line.solidFill = DEM; h5.series[0].graphicalProperties.line.width = 28000
    h5.series[0].marker = Marker(symbol="circle", size=8)
    h5.series[1].graphicalProperties.line.solidFill = "808080"; h5.series[1].graphicalProperties.line.dashStyle = "dash"
    h5.y_axis.numFmt = "0%"; hc.add_chart(h5, "A100")
    h6 = BarChart(); h6.type, h6.grouping, h6.overlap = "col", "stacked", 100
    h6.add_data(Reference(hc, min_col=19, max_col=20, min_row=38, max_row=38 + len(CYC)), titles_from_data=True)
    h6.set_categories(Reference(hc, min_col=18, min_row=39, max_row=38 + len(CYC)))
    style(h6, "6. Outside spending now exceeds the candidates' own", "US dollars", "Election cycle"); paint(h6.series[0], "1F4E79"); paint(h6.series[1], "E8A33D")
    h6.y_axis.numFmt = '$#,##0.0,,"M"'; hc.add_chart(h6, "A123")
    h7 = BarChart(); h7.type = "bar"
    h7.add_data(Reference(hc, min_col=19, min_row=45, max_row=45 + NPV), titles_from_data=True)
    h7.set_categories(Reference(hc, min_col=18, min_row=46, max_row=45 + NPV))
    style(h7, "7. Receipts per vote received", "", "US dollars per vote", w=22, h=13)
    paint(h7.series[0], "1F4E79"); points(h7.series[0], pv_cols); h7.legend = None; h7.x_axis.numFmt = "$#,##0"; hc.add_chart(h7, "A146")

    # ---------------------------------------------------- Notes & Sources
    ns = wb.create_sheet("Notes & Sources")
    ns.column_dimensions["A"].width = 150
    ns["A1"] = "Notes, sources and known limitations"; ns["A1"].font = TITLE
    r = section(ns, 3, "SOURCES", 1)
    for lab, val in [("Current cycle", "%s, %s, retrieved %s" % (fec["source"], fec["url"], fec["retrieved_utc"])),
                     ("History, finance", hist["source"] + ", retrieved " + hist["retrieved_utc"])]:
        r = note(ns, r, "%s: %s" % (lab, val), 1, font=BODY)
    for c in hist["cycles"]:
        r = note(ns, r, "History, %d results: %s (%s)" % (c["cycle"], c["source"], c["source_url"]), 1, font=BODY)
    r = section(ns, r + 1, "NOTES", 1)
    for t in fec["notes"] + hist["notes"] + ((det or {}).get("notes") or []):
        r = note(ns, r, "- " + t, 1)
    r = section(ns, r + 1, "METHOD", 1)
    for t in [
        "Candidate lookups use INDEX/MATCH keyed to the candidate name, never a row position; the FEC returns candidates in no guaranteed order.",
        "Candidates who have never filed are left blank rather than set to $0.",
        "Arithmetic that could read a blank cell as zero is guarded with ISNUMBER on both sides.",
        "'Other / unclassified' on Candidate Totals is a residual formula. The reconciliation row on Money Sources proves the components sum exactly to reported receipts.",
        "Independent expenditures are OpenFEC's deduplicated by_candidate aggregates.",
        "This workbook is rebuilt from sources/ on every scheduled run of the pa07-finance repository.",
    ]:
        r = note(ns, r, "- " + t, 1)

    A["_c6_top"], A["_c6_other"] = c6_top, c6_other
    order = ["Summary", "Charts", "Money Sources", "Candidate Totals", "Outside Money",
             "Spending Detail", "Donor Detail", "Outside Detail",
             "History", "History Charts", "Money vs Results", "Notes & Sources"]
    wb._sheets = [wb[s] for s in order]
    for s in wb.sheetnames:
        wb[s].sheet_properties.tabColor = NAVY
    wb.save(out)
    return A


def main():
    fec = json.load(open(os.path.join(SRC, "fec.json")))
    hist = json.load(open(os.path.join(SRC, "fec_history.json")))
    race = json.load(open(os.path.join(SRC, "race.json")))
    dpath = os.path.join(SRC, "fec_detail.json")
    det = json.load(open(dpath)) if os.path.exists(dpath) else None
    A = build(fec, hist, race, det=det)
    json.dump(A, open(os.path.join(ROOT, "_anchors.json"), "w"), indent=1)
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
