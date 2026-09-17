"""export_site.py: the payload the page reads."""
import json
import os

import support

DATA_FILES = ["manifest.json", "candidates.json", "outside.json", "history.json", "caveats.json", "detail.json"]


def exported():
    with support.sandbox() as (src, work):
        out, _ = support.built(src, work)
        site = os.path.join(work, "site")
        e = support.load("export_site")
        e.run(src, site, out)
        return {f: json.load(open(os.path.join(site, "data", f))) for f in DATA_FILES}, os.listdir(site)


def test_every_file_the_page_fetches_is_written():
    d, listing = exported()
    assert set(d) == set(DATA_FILES)
    assert "PA07_Campaign_Finance.xlsx" in listing
    assert d["manifest.json"]["workbook"]["available"] is True


def test_nominees_first_then_by_receipts():
    d, _ = exported()
    cs = d["candidates.json"]["candidates"]
    st = [c["status"] for c in cs]
    assert st[:2] == ["nominee", "nominee"] and "nominee" not in st[2:]
    filed = [c["receipts"] for c in cs[2:] if c["filed"]]
    assert filed == sorted(filed, reverse=True)


def test_outside_by_target_sums_to_total_and_rows_are_ranked():
    d, _ = exported()
    o = d["outside.json"]
    assert abs(sum(t["supports"] + t["opposes"] for t in o["by_target"]) - o["total"]) < 0.01
    amts = [r["amount"] for r in o["rows"]]
    assert amts == sorted(amts, reverse=True)
    assert set(r["stance"] for r in o["rows"]) <= {"supports", "opposes"}


def test_payload_carries_no_side_of_ledger_aggregation():
    """The page shows what was filed. The aligned-money construct stays in the workbook."""
    d, _ = exported()
    text = json.dumps(d).lower()
    for banned in ("aligned", "pro_d", "pro_r", "advantage", "regression", "slope"):
        assert banned not in text, banned


def test_composition_sums_to_receipts():
    d, _ = exported()
    for c in d["candidates.json"]["candidates"]:
        if not c["filed"]:
            assert c["other"] is None
            continue
        parts = c["individual_itemized"] + c["individual_unitemized"] + c["pac_contributions"] + \
            c["party_contributions"] + c["transfers_in"] + c["self_funding"] + c["other"]
        assert abs(parts - c["receipts"]) < 0.02, c["name"]


def test_history_two_party_share_sums_to_one_per_cycle():
    d, _ = exported()
    for c in d["history.json"]["cycles"]:
        assert abs(sum(x["two_party_share"] for x in c["candidates"]) - 1.0) < 1e-9
        assert sum(1 for x in c["candidates"] if x["winner"]) == 1


def test_no_em_dashes_in_payload():
    d, _ = exported()
    assert chr(0x2014) not in json.dumps(d)


def test_detail_payload_shape_and_shares():
    d, _ = exported()
    dt = d["detail.json"]
    assert dt["available"] and len(dt["committees"]) == 2
    for c in dt["committees"]:
        sp, co = c["spending"], c["contributions"]
        assert abs(sum(x["amount"] for x in sp["by_category"]) - sp["itemized_total"]) < 0.02
        assert 0 < sp["in_pa_share"] < 1 and 0 < co["in_district_share"] < 1
        assert len(sp["top_vendors"]) <= 8 and len(co["by_occupation"]) <= 6
        assert co["by_state"][-1]["state"] == "All other"


def test_outside_itemized_matches_aggregate_and_is_categorised():
    d, _ = exported()
    o = d["outside.json"]
    assert abs(sum(x["amount"] for x in o["itemized"]) - o["total"]) < 0.01
    assert abs(sum(x["amount"] for x in o["by_category"]) - o["total"]) < 0.01
    assert all(x["category"] for x in o["itemized"])


def test_outside_payload_is_nominees_only():
    d, _ = exported()
    fec = support.fixture("fec.json")
    nominees = {c["name"] for c in fec["candidates"] if c["nominee"]}
    o = d["outside.json"]
    assert {t["target"] for t in o["by_target"]} <= nominees
    assert {r["target"] for r in o["rows"]} <= nominees
    assert {r["target"] for r in o["itemized"]} <= nominees
    assert abs(o["total"] - sum(e["amount"] for e in fec["independent_expenditures"]
                                if e["target_candidate"] in nominees)) < 0.01
