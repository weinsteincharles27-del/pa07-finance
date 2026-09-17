"""collect_fec.py: the parsing, with the network faked."""
import json
import os

import support

RACE = {"cycle": 2026, "district": "PA-07", "nominees": {"DEM": "H1", "REP": "H2"},
        "display_names": {"H2": "Pat Short"}}
SEARCH = {"results": [
    {"candidate_id": "H1", "name": "DOE, JANE", "party": "DEM", "incumbent_challenge": "C",
     "election_years": [2026], "has_raised_funds": True, "principal_committees": [{"name": "JANE FOR PA"}]},
    {"candidate_id": "H2", "name": "SHORT, PATRICK LEE MR.", "party": "REP", "incumbent_challenge": "I",
     "election_years": [2026], "has_raised_funds": True, "principal_committees": [{"name": "SHORT CMTE"}]},
    {"candidate_id": "H3", "name": "MCCLURE, SAM", "party": "IND", "incumbent_challenge": "C",
     "election_years": [2026], "has_raised_funds": False, "principal_committees": []},
    {"candidate_id": "H9", "name": "OLD, CANDIDATE", "party": "DEM", "incumbent_challenge": "C",
     "election_years": [2022], "has_raised_funds": True, "principal_committees": []},
]}
TOTALS_H1 = {"results": [{"committee_id": "C1", "receipts": 1000.0, "disbursements": 400.0,
                          "last_cash_on_hand_end_period": 600.0, "last_debts_owed_by_committee": 0.0,
                          "individual_contributions": 800.0, "individual_itemized_contributions": 500.0,
                          "individual_unitemized_contributions": 300.0,
                          "other_political_committee_contributions": 150.0,
                          "political_party_committee_contributions": 25.0,
                          "transfers_from_other_authorized_committee": 20.0, "candidate_contribution": 5.0,
                          "coverage_start_date": "2025-01-01T00:00:00", "coverage_end_date": "2026-06-30T00:00:00",
                          "last_report_type_full": "JULY QUARTERLY"}]}
IE_H1 = {"results": [{"committee_id": "C90", "committee_name": "BIG PAC", "support_oppose_indicator": "S", "total": 250.0, "count": 3},
                     {"committee_id": "C91", "committee_name": "OTHER PAC", "support_oppose_indicator": "O", "total": 40.0, "count": 1},
                     {"committee_id": "C92", "committee_name": "WEIRD", "support_oppose_indicator": "X", "total": 9.0, "count": 1}],
         "pagination": {"pages": 1}}


def responses():
    return [
        (("/candidates/search/", {}), SEARCH),
        (("/candidate/H1/totals/", {}), TOTALS_H1),
        (("/candidate/H2/totals/", {}), TOTALS_H1),
        (("/schedules/schedule_e/by_candidate/", {"candidate_id": "H1"}), IE_H1),
    ]


def test_never_filed_candidate_gets_nulls_not_zeros():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
    sam = next(c for c in cur["candidates"] if c["candidate_id"] == "H3")
    assert sam["filed"] is False
    for k in ("receipts", "disbursements", "cash_on_hand", "individual_unitemized", "pac_contributions"):
        assert sam[k] is None, k


def test_candidates_from_other_cycles_are_dropped():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
    assert "H9" not in [c["candidate_id"] for c in cur["candidates"]]


def test_outside_target_label_equals_candidate_name_so_they_join():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
    names = {c["candidate_id"]: c["name"] for c in cur["candidates"]}
    for row in cur["independent_expenditures"]:
        assert row["target_candidate"] == names[row["target_candidate_id"]]


def test_display_name_override_and_title_casing():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
        dn = ff.mod.display_name
    by = {c["candidate_id"]: c["name"] for c in cur["candidates"]}
    assert by["H2"] == "Pat Short"            # race.json override wins
    assert by["H1"] == "Jane Doe"
    assert by["H3"] == "Sam McClure"          # Mc- keeps its second capital
    assert dn("OBANDO-DERSTINE, CAROL") == "Carol Obando-Derstine"
    assert dn("GRANADOS, MICHAEL RAMON MR. JR.") == "Michael Ramon Granados Jr."


def test_unknown_stance_rows_are_ignored():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
    assert sorted(r["support_oppose"] for r in cur["independent_expenditures"]) == ["O", "S"]


def test_nominee_flag_comes_from_race_json():
    with support.fake_fetch(responses()) as ff:
        cur = ff.mod.current(RACE)
    by = {c["candidate_id"]: c["nominee"] for c in cur["candidates"]}
    assert by == {"H1": "DEM", "H2": "REP", "H3": None}


def test_api_key_never_reaches_the_output(tmp=None):
    mod = support.load("collect_fec")
    os.environ["FEC_API_KEY"] = "sekrit-key-123"
    try:
        with support.fake_fetch(responses()) as ff:
            cur = ff.mod.current(RACE)
        assert "sekrit-key-123" not in json.dumps(cur)
        # and write() refuses to write it if it ever did
        import tempfile
        d = tempfile.mkdtemp()
        try:
            mod.write(os.path.join(d, "x.json"), cur)
            try:
                mod.write(os.path.join(d, "y.json"), {"oops": "sekrit-key-123"})
                assert False, "write() should refuse a leaked key"
            except AssertionError as e:
                assert "leaked" in str(e).lower()
        finally:
            import shutil
            shutil.rmtree(d)
    finally:
        del os.environ["FEC_API_KEY"]
