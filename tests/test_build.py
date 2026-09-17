"""build_workbook.py against the frozen sources."""
import openpyxl
import support


def test_candidate_totals_lists_the_two_nominees_only():
    with support.sandbox() as (src, work):
        out, A = support.built(src, work)
        fec = support.fixture("fec.json")
        ws = openpyxl.load_workbook(out)["Candidate Totals"]
        shown = {ws.cell(r, 1).value for r in range(A["CT_FIRST"], A["CT_LAST"] + 1)}
        assert shown == {c["name"] for c in fec["candidates"] if c["nominee"]}
        assert len(fec["candidates"]) > 2, "fixture should carry the other declared candidates"


def test_sheet_order_and_chart_count():
    with support.sandbox() as (src, work):
        out, _ = support.built(src, work)
        wb = openpyxl.load_workbook(out)
        assert wb.sheetnames == ["Summary", "Charts", "Money Sources", "Candidate Totals", "Outside Money",
                                 "Spending Detail", "Donor Detail", "Outside Detail",
                                 "History", "History Charts", "Money vs Results", "Notes & Sources"]
        assert sum(len(wb[s]._charts) for s in wb.sheetnames) == 16


def test_chart_series_titles_sit_one_row_above_their_data():
    with support.sandbox() as (src, work):
        out, _ = support.built(src, work)
        wb = openpyxl.load_workbook(out)
        for s in wb.sheetnames:
            for ch in wb[s]._charts:
                for ser in ch.series:
                    try:
                        tref = ser.tx.strRef.f
                    except AttributeError:
                        continue
                    vref = ser.val.numRef.f
                    trow = int(tref.split("!")[1].replace("$", "")[1:])
                    vrow = int(vref.split("!")[1].split(":")[0].replace("$", "")[1:])
                    assert trow == vrow - 1, (s, tref, vref)


def test_cash_lookups_are_keyed_by_name_not_row():
    with support.sandbox() as (src, work):
        out, A = support.built(src, work)
        ws = openpyxl.load_workbook(out)["Money Sources"]
        f = ws.cell(A["MS_SP_FIRST"] + 2, 2).value       # cash on hand, Democratic nominee
        assert "MATCH(" in f and "INDEX(" in f and "Bob Brooks" in f


def test_no_em_dashes_anywhere():
    with support.sandbox() as (src, work):
        out, _ = support.built(src, work)
        assert chr(0x2014).encode("utf-8") not in open(out, "rb").read()


def test_detail_sheets_reconcile_to_source():
    """Category rows sum to FEC's itemized total; itemized outside rows sum to the aggregate."""
    import json
    with support.sandbox() as (src, work):
        out, A = support.built(src, work)
        det = json.load(open(src + "/fec_detail.json"))
        fec = json.load(open(src + "/fec.json"))
        wb = openpyxl.load_workbook(out)
        sd = wb["Spending Detail"]
        for j, cid in enumerate(c["committee_id"] for c in fec["candidates"] if c["nominee"]):
            col = 2 + 3 * j
            total = sum(sd.cell(r, col).value or 0 for r in range(A["SD_CAT_FIRST"], A["SD_CAT_LAST"] + 1))
            assert abs(total - det["committees"][cid]["spending"]["itemized_total"]) < 0.02
        od = wb["Outside Detail"]
        nominees = {c["candidate_id"] for c in fec["candidates"] if c["nominee"]}
        total = sum(od.cell(r, 8).value or 0 for r in range(A["OI_FIRST"], A["OI_LAST"] + 1))
        assert abs(total - sum(x["amount"] for x in fec["independent_expenditures"]
                               if x["target_candidate_id"] in nominees)) < 0.01


def test_outside_spending_shows_nominees_only():
    """Spending about primary candidates not on the November ballot is in sources/ but not displayed."""
    import json
    with support.sandbox() as (src, work):
        out, A = support.built(src, work)
        fec = json.load(open(src + "/fec.json"))
        nominees = {c["name"] for c in fec["candidates"] if c["nominee"]}
        others = {c["name"] for c in fec["candidates"] if not c["nominee"]}
        assert any(e["target_candidate"] in others for e in fec["independent_expenditures"]), "fixture should carry some"
        wb = openpyxl.load_workbook(out)
        om = wb["Outside Money"]
        shown = {om.cell(r, 2).value for r in range(A["IE_FIRST"], A["IE_LAST"] + 1)}
        assert shown <= nominees and not (shown & others), shown
        od = wb["Outside Detail"]
        shown2 = {od.cell(r, 2).value for r in range(A["OI_FIRST"], A["OI_LAST"] + 1)}
        assert shown2 <= nominees and not (shown2 & others), shown2


def test_workbook_builds_without_detail_file():
    """The detail is optional: a missing fec_detail.json yields a placeholder, not a crash."""
    import json, os
    with support.sandbox() as (src, work):
        os.remove(os.path.join(src, "fec_detail.json"))
        out, A = support.built(src, work)
        wb = openpyxl.load_workbook(out)
        assert "Spending Detail" in wb.sheetnames
        assert A["N_CHARTS"] == 13 and sum(len(wb[s]._charts) for s in wb.sheetnames) == 13
