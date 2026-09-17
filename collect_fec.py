#!/usr/bin/env python3
"""Pull PA-07 campaign finance from the OpenFEC API into sources/.

Writes two files:

  sources/fec.json          current cycle: every declared candidate's committee
                            totals, and independent expenditures by committee
  sources/fec_history.json  the last four general elections: the two nominees'
                            full-cycle totals and outside spending, joined to
                            the certified vote totals in sources/results.json

Which candidates are the current nominees, and what the certified results were,
are facts the API does not state; they come from sources/race.json and
sources/results.json, which are maintained by hand.

Conventions that matter for correctness:

  - A candidate who has never filed a report gets null, never 0. "No report" is
    not the same claim as "raised nothing", and the two must stay distinguishable.
  - Outside spending is OpenFEC's by_candidate aggregate, which is FEC's own
    deduplication of amendments and superseding filings. A naive sum of raw
    Schedule E lines double-counts and runs roughly twice as high. The aggregate
    can lag a 24-hour notice by several weeks; that is recorded as a caveat, not
    patched by hand.
  - Susan Wild's 2018 record is filed under district 15 (she also contested the
    old PA-15 special that day). Candidates are therefore always looked up by
    candidate_id, never by district.
  - The API key is read at the point of use and asserted absent from the output.

    FEC_API_KEY=... python3 collect_fec.py        # CI (repository secret)
    python3 collect_fec.py                        # local: reads fec_key.txt
    python3 collect_fec.py --history              # also refetch the 2018-2024 figures
"""
import datetime
import json
import re
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "sources")
BASE = "https://api.open.fec.gov/v1"


def api_key(required=True):
    """The OpenFEC key, from the environment or a local file. There is no public
    fallback: FEC's DEMO_KEY allows 30 calls an hour and this run makes about 37,
    so it fails partway through after minutes of retries. Better to stop now and
    say what to do."""
    k = os.environ.get("FEC_API_KEY", "").strip()
    if k:
        return k
    for p in (os.path.join(ROOT, "fec_key.txt"),
              os.path.expanduser("~/pa07-tracker/fec_key.txt")):
        if os.path.exists(p):
            return open(p).read().strip()
    if not required:
        return ""
    sys.exit("collect_fec.py: no FEC API key. Export FEC_API_KEY, or put the key in fec_key.txt.\n"
             "In GitHub Actions, add it as a repository secret:\n"
             "  gh secret set FEC_API_KEY --repo weinsteincharles27-del/pa07-finance\n"
             "Request a key at https://api.data.gov/signup/ (free, read-only, gates rate limits only).")


def fetch(path, **params):
    """One GET against OpenFEC with retry. The single seam the tests replace."""
    params["api_key"] = api_key()
    url = "%s%s?%s" % (BASE, path, urllib.parse.urlencode(params))
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:              # rate limited: wait it out
                time.sleep(15 * (attempt + 1))
                continue
            if 500 <= e.code < 600:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except Exception as e:             # network blip
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("OpenFEC %s failed after retries: %s" % (path, last))


def pages(path, **params):
    """Every result across pagination."""
    out, page = [], 1
    while True:
        d = fetch(path, page=page, per_page=100, **params)
        out.extend(d.get("results") or [])
        pg = d.get("pagination") or {}
        if page >= (pg.get("pages") or 1):
            return out
        page += 1


def money(v):
    return None if v is None else round(float(v), 2)


def day(iso):
    return (iso or "")[:10] or None


# ----------------------------------------------------------------- per candidate

def totals(candidate_id, cycle):
    """Full-cycle committee totals. Empty results means the candidate has never
    filed a periodic report: every field comes back None."""
    rs = fetch("/candidate/%s/totals/" % candidate_id, cycle=cycle, full_election="true").get("results") or []
    t = rs[0] if rs else {}
    return {
        "filed": bool(rs),
        "committee_id": t.get("committee_id"),
        "receipts": money(t.get("receipts")),
        "disbursements": money(t.get("disbursements")),
        "cash_on_hand": money(t.get("last_cash_on_hand_end_period")),
        "debts": money(t.get("last_debts_owed_by_committee")),
        "individual_contributions": money(t.get("individual_contributions")),
        "individual_itemized": money(t.get("individual_itemized_contributions")),
        "individual_unitemized": money(t.get("individual_unitemized_contributions")),
        "pac_contributions": money(t.get("other_political_committee_contributions")),
        "party_contributions": money(t.get("political_party_committee_contributions")),
        "transfers_in": money(t.get("transfers_from_other_authorized_committee")),
        "self_funding": money(t.get("candidate_contribution")),
        "coverage_start": day(t.get("coverage_start_date")),
        "coverage_end": day(t.get("coverage_end_date")),
        "last_report": t.get("last_report_type_full"),
    }


def outside(candidate_id, cycle):
    """Independent expenditures about this candidate, one row per committee and
    stance, from FEC's deduplicated by_candidate aggregate."""
    rows = []
    for r in pages("/schedules/schedule_e/by_candidate/", candidate_id=candidate_id,
                   cycle=cycle, election_full="true"):
        so = r.get("support_oppose_indicator")
        if so not in ("S", "O"):
            continue
        rows.append({
            "committee_id": r.get("committee_id"),
            "committee": r.get("committee_name"),
            "target_candidate_id": candidate_id,
            "support_oppose": so,
            "amount": money(r.get("total")),
            "filings": r.get("count"),
        })
    return rows


# ------------------------------------------------------------------ current cycle

def current(race):
    cycle = race["cycle"]
    found = fetch("/candidates/search/", state="PA", district="07", office="H",
                  cycle=cycle, per_page=50).get("results") or []
    nominees = {v: k for k, v in race["nominees"].items()}
    cands, ies = [], []
    for r in sorted(found, key=lambda x: x["name"]):
        if cycle not in (r.get("election_years") or []):
            continue
        cid = r["candidate_id"]
        t = totals(cid, cycle)
        pcc = (r.get("principal_committees") or [{}])
        # One name per candidate, used for the candidate row AND as the target
        # label on their outside-spending rows, so the two always join.
        name = (race.get("display_names") or {}).get(cid) or display_name(r["name"])
        cands.append({
            "candidate_id": cid,
            "name": name,
            "fec_name": r["name"],
            "party": r.get("party"),
            "incumbent": r.get("incumbent_challenge") == "I",
            "nominee": nominees.get(cid),          # "DEM" / "REP" / None
            "has_raised_funds": bool(r.get("has_raised_funds")),
            "committee_name": (pcc[0].get("name") if pcc else None),
            **t,
        })
        for row in outside(cid, cycle):
            row["target_candidate"] = name
            ies.append(row)
    ies.sort(key=lambda x: -(x["amount"] or 0))
    return {
        "source": "FEC / OpenFEC API",
        "url": "https://www.fec.gov/data/elections/house/PA/07/%d/" % cycle,
        "retrieved_utc": now(),
        "cycle": cycle,
        "coverage_through": max((c["coverage_end"] for c in cands if c["coverage_end"]), default=None),
        "candidates": cands,
        "independent_expenditures": ies,
        "notes": [
            "Candidate totals are cycle-to-date from each committee's most recent periodic "
            "report (FEC Form 3). Independent expenditures report continuously and are usually "
            "fresher than the candidate totals; the two are not as of the same date.",
            "Independent expenditures come from OpenFEC's schedules/schedule_e/by_candidate "
            "aggregate, FEC's own deduplication of amended and superseded filings. Summing raw "
            "itemized Schedule E lines instead would roughly double the figure and would be wrong.",
            "That aggregate can lag a 24-hour notice by several weeks. Spending reported by "
            "notice in the last month may not yet appear here.",
            "Candidates with no periodic report on file show blank fields, not $0. The FEC "
            "reports no figures for them, which is not the same as a confirmed zero.",
            "'PAC contributions' is FEC's other_political_committee_contributions: money "
            "given directly to the campaign by other political committees. It is a different "
            "thing from independent expenditures, which are spent by outside groups on their "
            "own and never pass through the campaign.",
            "'Self-funding' is FEC's candidate_contribution: the candidate's own money given or "
            "loaned to the campaign this cycle.",
        ],
    }


# ---------------------------------------------------------------------- history

def history(results):
    cycles = []
    for c in results["cycles"]:
        cy = c["cycle"]
        cands = []
        for n in c["nominees"]:
            t = totals(n["candidate_id"], cy)
            ie = outside(n["candidate_id"], cy)
            cands.append({
                "candidate_id": n["candidate_id"], "name": n["name"], "party": n["party"],
                "incumbent": n["incumbent"], **t,
                "ie_supporting": round(sum(x["amount"] for x in ie if x["support_oppose"] == "S"), 2),
                "ie_opposing": round(sum(x["amount"] for x in ie if x["support_oppose"] == "O"), 2),
                "ie_committees_supporting": sum(1 for x in ie if x["support_oppose"] == "S"),
                "ie_committees_opposing": sum(1 for x in ie if x["support_oppose"] == "O"),
                "general_votes": n["general_votes"],
                "winner": n["winner"],
            })
        cycles.append({k: c[k] for k in ("cycle", "election_date", "map_era",
                                          "all_candidate_votes_reported", "district_total_votes",
                                          "other_votes", "source", "source_url")}
                      | {"two_party_votes": sum(x["general_votes"] for x in cands),
                         "candidates": cands})
    return {
        "source": "OpenFEC API (finance); certified results from sources/results.json",
        "retrieved_utc": now(),
        "district": results["district"],
        "cycles_covered": [c["cycle"] for c in cycles],
        "cycles": cycles,
        "notes": results.get("notes", []) + [
            "Finance figures are full-cycle totals through 31 December of the election year "
            "and are final, unlike the current-cycle figures, which are mid-cycle.",
            "In 2018 Susan Wild's single committee financed two concurrent races (the PA-07 "
            "full term and the PA-15 unexpired term), so her 2018 receipts are not a clean "
            "PA-07 figure. The vote total used is the full-term race.",
        ],
    }


# ----------------------------------------------------------------------- helpers

def display_name(fec_name):
    """'BROOKS, BOB' -> 'Bob Brooks'; 'GRANADOS, MICHAEL RAMON MR. JR.' -> 'Michael Ramon Granados Jr.'"""
    last, _, rest = fec_name.partition(",")
    toks = [t for t in rest.split() if t.strip(".").upper() not in ("MR", "MRS", "MS", "DR")]
    suffix = [t for t in toks if t.strip(".").upper() in ("JR", "SR", "II", "III")]
    first = [t for t in toks if t not in suffix]
    def cap(t):
        """Capitalise one token, keeping the second cap in Mc-/Mac- names and after a hyphen."""
        if not t:
            return t
        out = "-".join(w[:1].upper() + w[1:].lower() for w in t.split("-"))
        return re.sub(r"^(Mc|Mac)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    name = " ".join(cap(t) for t in first) + " " + " ".join(cap(p) for p in last.strip().split())
    if suffix:
        name += " " + suffix[0].strip(".").title() + "."
    return name.strip()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(path, obj):
    key = api_key(required=False)
    text = json.dumps(obj, indent=2)
    assert not key or key not in text, "API key leaked into %s" % path
    with open(path, "w") as f:
        f.write(text + "\n")


HISTORY_MAX_AGE_DAYS = 7


def history_is_fresh(path, now_utc=None):
    """The 2018-2024 figures are final. Re-pulling them on every run would spend
    16 of a run's 37 calls confirming numbers that cannot change, so they are
    refreshed weekly; --history forces it."""
    if not os.path.exists(path):
        return False
    try:
        stamp = json.load(open(path)).get("retrieved_utc") or ""
        then = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    return (now_utc - then).days < HISTORY_MAX_AGE_DAYS


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    race = json.load(open(os.path.join(SRC, "race.json")))
    results = json.load(open(os.path.join(SRC, "results.json")))
    cur = current(race)
    write(os.path.join(SRC, "fec.json"), cur)
    n_filed = sum(1 for c in cur["candidates"] if c["filed"])
    print("fec.json: %d candidates (%d filed), %d outside-spending rows, coverage through %s"
          % (len(cur["candidates"]), n_filed, len(cur["independent_expenditures"]), cur["coverage_through"]))
    hpath = os.path.join(SRC, "fec_history.json")
    if "--history" in argv or not history_is_fresh(hpath):
        hist = history(results)
        write(hpath, hist)
        print("fec_history.json: %d cycles refreshed" % len(hist["cycles"]))
    else:
        print("fec_history.json: fresh (under %d days old), not refetched" % HISTORY_MAX_AGE_DAYS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
