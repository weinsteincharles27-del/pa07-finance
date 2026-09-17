#!/usr/bin/env python3
"""Write the JSON the page reads into site/data/, and copy the workbook in.

The page shows what the FEC reports, by candidate and by committee, and nothing
else: no side-of-the-ledger aggregation, no model. The analytical sheets stay
in the workbook the page links to.

    python3 export_site.py
"""
import datetime
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(src, name):
    return json.load(open(os.path.join(src, name)))


def write(data_dir, name, obj):
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, name)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True)
    return os.path.getsize(path)


def status(c):
    if c["nominee"]:
        return "nominee"
    if c["party"] in ("DEM", "REP"):
        return "primary"
    return "declared"


def candidates_block(fec):
    keep = ["candidate_id", "name", "party", "incumbent", "nominee", "filed", "committee_name",
            "receipts", "disbursements", "cash_on_hand", "debts", "individual_contributions",
            "individual_itemized", "individual_unitemized", "pac_contributions", "party_contributions",
            "transfers_in", "self_funding", "coverage_end", "last_report"]
    out = []
    for c in fec["candidates"]:
        row = {k: c.get(k) for k in keep}
        row["status"] = status(c)
        # Residual, so the page can draw a composition that sums to receipts.
        if c["filed"]:
            row["other"] = round(c["receipts"] - (c["individual_contributions"] + c["pac_contributions"]
                                                  + c["party_contributions"] + c["transfers_in"] + c["self_funding"]), 2)
        else:
            row["other"] = None
        out.append(row)
    out.sort(key=lambda r: (r["status"] != "nominee", -(r["receipts"] or 0), r["name"]))
    return {"cycle": fec["cycle"], "coverage_through": fec["coverage_through"],
            "retrieved_utc": fec["retrieved_utc"], "candidates": out}


def outside_block(fec):
    rows = []
    for e in fec["independent_expenditures"]:
        rows.append({"committee": e["committee"], "committee_id": e["committee_id"],
                     "target": e["target_candidate"], "target_id": e["target_candidate_id"],
                     "stance": "supports" if e["support_oppose"] == "S" else "opposes",
                     "amount": e["amount"], "filings": e["filings"]})
    rows.sort(key=lambda r: -(r["amount"] or 0))
    by_target = {}
    for r in rows:
        k = by_target.setdefault(r["target"], {"target": r["target"], "supports": 0.0, "opposes": 0.0,
                                                "committees_supporting": 0, "committees_opposing": 0})
        k[r["stance"]] = round(k[r["stance"]] + r["amount"], 2)
        k["committees_" + ("supporting" if r["stance"] == "supports" else "opposing")] += 1
    items = []
    by_cat = {}
    for x in fec.get("outside_itemized") or []:
        items.append({"committee": x["committee"], "target": x["target_candidate"],
                      "stance": "supports" if x["support_oppose"] == "S" else "opposes",
                      "what": x["description"], "category": x["category"], "payee": x["payee"],
                      "city": x["payee_city"], "state": x["payee_state"], "amount": x["amount"], "date": x["date"]})
        by_cat[x["category"]] = round(by_cat.get(x["category"], 0.0) + (x["amount"] or 0), 2)
    return {"total": round(sum(r["amount"] for r in rows), 2), "rows": rows,
            "by_target": sorted(by_target.values(), key=lambda t: -(t["supports"] + t["opposes"])),
            "itemized": items,
            "by_category": sorted(({"category": k, "amount": v} for k, v in by_cat.items()), key=lambda r: -r["amount"]),
            "retrieved_utc": fec["retrieved_utc"]}


def detail_block(fec, det):
    """Spending by category and payee, contributions by state, size, district and
    occupation, for the nominees. What was filed, nothing derived beyond shares."""
    if not det:
        return {"available": False}
    out = {"available": True, "coverage_through": det["coverage_through"], "retrieved_utc": det["retrieved_utc"],
           "in_district_zip_prefixes": det["in_district_zip_prefixes"], "committees": []}
    for c in fec["candidates"]:
        cid = c.get("committee_id")
        if not c["nominee"] or cid not in det["committees"]:
            continue
        d = det["committees"][cid]
        sp, co = d["spending"], d["contributions"]
        pa = next((x["amount"] for x in sp["by_vendor_state"] if x["state"] == "PA"), 0.0)
        states = co["by_state"]
        top_states = states[:8]
        other = round(sum(x["amount"] or 0 for x in states[8:]), 2)
        out["committees"].append({
            "candidate": c["name"], "party": c["party"], "committee_id": cid,
            "spending": {
                "itemized_total": sp["itemized_total"], "items": sp["items"],
                "by_category": sp["by_category"],
                "top_vendors": [{"vendor": v["vendor"], "city": v["city"], "state": v["state"],
                                 "amount": v["amount"], "category": v["category"]} for v in sp["top_vendors"][:8]],
                "in_pa_share": round(pa / sp["itemized_total"], 4) if sp["itemized_total"] else None,
            },
            "contributions": {
                "itemized_total": co["itemized_total"],
                "by_state": top_states + ([{"state": "All other", "amount": other, "count": None}] if other else []),
                "by_size": co["by_size"],
                "in_district_share": round(co["in_district_amount"] / co["zip_total"], 4) if co["zip_total"] else None,
                "in_district_amount": co["in_district_amount"],
                "by_occupation": co["by_occupation"][:6],
            },
        })
    return out


def history_block(hist):
    cycles = []
    for c in hist["cycles"]:
        two_party = sum(x["general_votes"] for x in c["candidates"])
        cands = []
        for x in c["candidates"]:
            cands.append({"name": x["name"], "party": x["party"], "incumbent": x["incumbent"],
                          "receipts": x["receipts"], "disbursements": x["disbursements"],
                          "cash_on_hand": x["cash_on_hand"], "ie_supporting": x["ie_supporting"],
                          "ie_opposing": x["ie_opposing"], "general_votes": x["general_votes"],
                          "two_party_share": x["general_votes"] / two_party if two_party else None,
                          "winner": x["winner"]})
        cycles.append({"cycle": c["cycle"], "election_date": c["election_date"], "map_era": c["map_era"],
                       "district_total_votes": c["district_total_votes"], "other_votes": c["other_votes"],
                       "all_candidate_votes_reported": c["all_candidate_votes_reported"],
                       "source": c["source"], "source_url": c["source_url"], "candidates": cands})
    return {"cycles": cycles, "retrieved_utc": hist["retrieved_utc"]}


def caveats_block(fec, hist, race):
    nxt = race.get("next_periodic_report") or {}
    return {"items": [
        {"id": "vintage", "severity": "high", "title": "The candidate totals are a snapshot, not live.",
         "text": "Campaigns report to the FEC quarterly. The figures here run through %s, the latest periodic "
                 "report on file. The next report, the %s, is due %s and will cover through %s." %
                 (fec["coverage_through"], nxt.get("name", "next quarterly"), nxt.get("due", "?"), nxt.get("covers_through", "?"))},
        {"id": "two-clocks", "severity": "medium", "title": "Outside spending is on a different clock.",
         "text": "Outside groups report as they spend, so that table is usually fresher than the candidate totals. "
                 "The two halves of this page are not as of the same date."},
        {"id": "primary", "severity": "medium", "title": "Much of the outside money went to the primary.",
         "text": "The largest outside-spending committees were active in May 2026, before the Democratic primary "
                 "on %s. Their spending is part of this race's record but was not aimed at the November contest." % race["primary_date"]},
        {"id": "transfer", "severity": "low", "title": "One line inside the receipts is not new donor money.",
         "text": "A transfer from another authorized committee counts as receipts. The source-of-funds section "
                 "shows it separately so it can be set aside when comparing what each campaign raised from donors."},
        {"id": "no-report", "severity": "low", "title": "Blank is not zero.",
         "text": "Candidates who have never filed a periodic report show blank fields. The FEC reports nothing for "
                 "them, which is not the same as a confirmed $0."},
        {"id": "lag", "severity": "low", "title": "The outside-spending totals can lag recent filings.",
         "text": "They come from the FEC's own deduplicated aggregate, which can take several weeks to absorb a "
                 "24-hour notice. Spending reported by notice in the last month may not appear yet."},
    ], "definitions": [
        {"term": "Raised (receipts)", "text": "All money the campaign committee took in this cycle, from any source."},
        {"term": "Spent (disbursements)", "text": "All money the campaign committee paid out this cycle."},
        {"term": "Cash on hand", "text": "What the committee had in the bank at the end of its latest report."},
        {"term": "Small donations", "text": "Individual contributions of $200 or less, which the FEC does not itemize by donor."},
        {"term": "PAC contributions", "text": "Money other political committees gave directly to the campaign. Different from outside spending, which never passes through the campaign."},
        {"term": "Outside spending (independent expenditures)", "text": "Money a group spends on its own to support or oppose a candidate, without coordinating with any campaign. The FEC records which candidate each expenditure was about and whether it supported or opposed them."},
        {"term": "Transfer from another authorized committee", "text": "Money moved in from a joint fundraising or earlier committee of the same candidate. It is counted in receipts but was not raised from donors this cycle."},
    ]}


def manifest(fec, hist, race, sizes, wb_bytes, wb_name):
    today = datetime.date.today()
    eday = datetime.date.fromisoformat(race["election_date"])
    return {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "race": {"district": race["district"], "office": race["office"], "cycle": race["cycle"],
                 "election": race["election_date"], "days_to_election": (eday - today).days,
                 "democrat": next(c["name"] for c in fec["candidates"] if c["nominee"] == "DEM"),
                 "republican": next(c["name"] for c in fec["candidates"] if c["nominee"] == "REP")},
        "coverage_through": fec["coverage_through"],
        "retrieved_utc": fec["retrieved_utc"],
        "history_cycles": hist["cycles_covered"],
        "source": {"name": "Federal Election Commission", "url": fec["url"]},
        "files": sizes,
        "workbook": {"href": wb_name, "bytes": wb_bytes, "available": wb_bytes > 0},
        "colours": {"D": "#2E5FA3", "R": "#C0392B"},
    }


def run(src, site, workbook):
    data = os.path.join(site, "data")
    fec, hist, race = load(src, "fec.json"), load(src, "fec_history.json"), load(src, "race.json")
    dpath = os.path.join(src, "fec_detail.json")
    det = json.load(open(dpath)) if os.path.exists(dpath) else None
    sizes = {
        "detail.json": write(data, "detail.json", detail_block(fec, det)),
        "candidates.json": write(data, "candidates.json", candidates_block(fec)),
        "outside.json": write(data, "outside.json", outside_block(fec)),
        "history.json": write(data, "history.json", history_block(hist)),
        "caveats.json": write(data, "caveats.json", caveats_block(fec, hist, race)),
    }
    wb_bytes = 0
    if workbook and os.path.exists(workbook):
        dest = os.path.join(site, os.path.basename(workbook))
        shutil.copyfile(workbook, dest)
        wb_bytes = os.path.getsize(dest)
    sizes["manifest.json"] = write(data, "manifest.json",
                                   manifest(fec, hist, race, sizes, wb_bytes, os.path.basename(workbook or "")))
    return sizes, wb_bytes


def main():
    workbook = os.environ.get("PA07_WORKBOOK", os.path.join(ROOT, "PA07_Campaign_Finance.xlsx"))
    sizes, wb_bytes = run(os.path.join(ROOT, "sources"), os.path.join(ROOT, "site"), workbook)
    for k, v in sorted(sizes.items()):
        print("  %-18s %7d bytes" % (k, v))
    print("  workbook           %7d bytes" % wb_bytes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
