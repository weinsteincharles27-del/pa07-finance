# PA-07 Campaign Finance

What the Federal Election Commission reports for the Pennsylvania 7th congressional
district race, by candidate and by committee. Bob Brooks (D) and Rep. Ryan Mackenzie (R),
general election 3 November 2026.

Live page: https://weinsteincharles27-del.github.io/pa07-finance/

The page shows money raised and spent by every declared candidate, where each nominee's
money came from, outside spending by committee with the candidate it was about and
whether it supported or opposed them, and the same figures for the last four elections
alongside the certified results. It reports what was filed and takes no position on any
candidate: colour identifies party, and support and oppose are words in a column.

The workbook behind the page, `PA07_Campaign_Finance.xlsx`, is linked from the page and
rebuilt on every scheduled run. Nine sheets, thirteen native Excel charts, no macros.
It carries everything on the page plus the source-of-funds reconciliation and a
money-against-results analysis with its caveats.

## How it works

```
collect_fec.py     OpenFEC API  ->  sources/fec.json, sources/fec_history.json, sources/fec_detail.json
classify.py        free-text FEC descriptions -> standard spending categories
build_workbook.py  sources/     ->  PA07_Campaign_Finance.xlsx
verify.py          the gate: every formula evaluated, every figure recomputed from sources/
export_site.py     sources/     ->  site/data/*.json, and the workbook copied into site/
```

Three kinds of FEC data are read. Committee totals and outside-spending aggregates, every
run. Every itemized outside expenditure (what each group bought and from whom), every run.
And the two nominees' itemized spending by category and payee, plus contributions by state,
size, zip and occupation, re-pulled weekly or whenever a new quarterly report lands. Memo
sub-itemizations and 48-hour notices are dropped, which is what makes the itemized sums
equal the FEC's own aggregates to the cent; `verify.py` checks that every run.

Two files in `sources/` are maintained by hand and never fetched:

- `race.json`: which two candidates are the nominees, the key dates, and the display
  names used on the page. The FEC API does not say who won a primary.
- `results.json`: certified vote totals for 2018 to 2024, with the source of each. These
  are historical facts and do not change.

`.github/workflows/refresh.yml` runs the four steps every five minutes, GitHub's cron
floor. A run makes 21 API calls (37 once a week, when the final 2018 to 2024 figures are
re-pulled); the key allows 60 a minute and 1,000 an hour. `changed.py` then compares the
result to what is committed with the timestamps removed: if nothing else moved, the run
leaves no commit and no deploy. The FEC processes filings in batches, so most runs find
nothing, and the "Data updated" date on the page means the figures last changed then, not
that the check last ran then. If `verify.py` fails, nothing is committed and the published
page keeps the last version that passed.

## Conventions that keep the numbers right

Every bug this project has had produced a valid, non-erroring, wrong number. The
conventions below each exist because one of those happened.

- **A candidate who never filed is blank, not $0.** "No report" and "raised nothing" are
  different claims. `SUM()` ignores blanks, so totals cover filers only.
- **Lookups are keyed by name, never by row.** The FEC returns candidates in no guaranteed
  order. `INDEX/MATCH` on the candidate name, always.
- **A blank cell reads as zero in arithmetic.** Every subtraction and ratio checks
  `ISNUMBER` on both sides first.
- **Outside spending is FEC's own deduplicated aggregate.** Summing raw Schedule E lines
  double-counts amendments and runs roughly twice as high. The aggregate can lag a 24-hour
  notice by weeks; that is a caveat on the page, not a hand patch.
- **The itemized schedules page by cursor, not page number.** Asking `schedule_b` for
  `page=2` returns page 1 again, silently. `keyset()` passes back `pagination.last_indexes`.
- **Categories come from the description, not the FEC's purpose field.** The FEC files more
  than half of this spending as OTHER. `classify.py` uses ordered keyword rules pinned by
  tests against the real descriptions; the gate fails if OTHER exceeds 2%.
- **Susan Wild's 2018 record is filed under district 15.** A query by district silently
  omits the 2018 winner. Candidates are fetched by ID.
- **The gate recomputes, it does not just evaluate.** `verify.py` runs every formula with
  the `formulas` engine, then rebuilds each displayed figure independently in Python from
  `sources/` and compares. `tests/test_verify.py` corrupts a build three different ways and
  asserts the gate catches each.

## Setup

The refresh job needs one repository secret, `FEC_API_KEY`. FEC's public `DEMO_KEY` allows
30 calls an hour and a run makes about 37, so there is no working fallback; without the
secret the job does nothing and exits green with a warning annotation, so a five-minute
schedule does not become a five-minute stream of failure emails. Request a key at
https://api.data.gov/signup/ (free, read-only against public data) and store it:

```bash
gh secret set FEC_API_KEY --repo weinsteincharles27-del/pa07-finance
```

Locally, put it in `fec_key.txt` (gitignored) or export `FEC_API_KEY`. `build_workbook.py`,
`verify.py`, `export_site.py` and the tests need no key; only the collector does.

GitHub Pages must be set to deploy from GitHub Actions (Settings, Pages, Source).

## Local development

```bash
python3 collect_fec.py          # fetch (needs network)
python3 build_workbook.py
python3 verify.py               # must print GREEN
python3 export_site.py
python3 tests/run_tests.py      # 44 passed, 0 failed
cd site && python3 -m http.server 8000
```

Dependencies: `openpyxl` and `formulas`. On this Mac use `/usr/bin/python3`, which has both.

## Files the refresh job owns

`sources/fec.json`, `sources/fec_history.json`, `sources/fec_detail.json`, `site/data/**` and `site/PA07_Campaign_Finance.xlsx`
are rewritten on `main` whenever the FEC figures change. CI refuses a pull request that edits them, so a branch
never conflicts with the bot. Page code lives in `site/assets`; data comes from the pipeline.
