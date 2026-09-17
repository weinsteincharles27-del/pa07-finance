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
collect_fec.py     OpenFEC API  ->  sources/fec.json, sources/fec_history.json
build_workbook.py  sources/     ->  PA07_Campaign_Finance.xlsx
verify.py          the gate: every formula evaluated, every figure recomputed from sources/
export_site.py     sources/     ->  site/data/*.json, and the workbook copied into site/
```

Two files in `sources/` are maintained by hand and never fetched:

- `race.json`: which two candidates are the nominees, the key dates, and the display
  names used on the page. The FEC API does not say who won a primary.
- `results.json`: certified vote totals for 2018 to 2024, with the source of each. These
  are historical facts and do not change.

`.github/workflows/refresh.yml` runs the four steps daily at 12:23 UTC, commits the
refreshed payload to `main`, and publishes `site/`. If `verify.py` fails, nothing is
committed and the published page keeps the last version that passed.

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
- **Susan Wild's 2018 record is filed under district 15.** A query by district silently
  omits the 2018 winner. Candidates are fetched by ID.
- **The gate recomputes, it does not just evaluate.** `verify.py` runs every formula with
  the `formulas` engine, then rebuilds each displayed figure independently in Python from
  `sources/` and compares. `tests/test_verify.py` corrupts a build three different ways and
  asserts the gate catches each.

## Setup

The repository works with no secrets: the collector falls back to FEC's public `DEMO_KEY`.
An API key raises the rate limit and is worth adding. Request one at
https://api.data.gov/signup/ and store it:

```bash
gh secret set FEC_API_KEY --repo weinsteincharles27-del/pa07-finance
```

Locally, put it in `fec_key.txt` (gitignored) or export `FEC_API_KEY`.

GitHub Pages must be set to deploy from GitHub Actions (Settings, Pages, Source).

## Local development

```bash
python3 collect_fec.py          # fetch (needs network)
python3 build_workbook.py
python3 verify.py               # must print GREEN
python3 export_site.py
python3 tests/run_tests.py      # 28 passed, 0 failed
cd site && python3 -m http.server 8000
```

Dependencies: `openpyxl` and `formulas`. On this Mac use `/usr/bin/python3`, which has both.

## Files the refresh job owns

`sources/fec.json`, `sources/fec_history.json`, `site/data/**` and `site/PA07_Campaign_Finance.xlsx`
are rewritten on `main` daily. CI refuses a pull request that edits them, so a branch
never conflicts with the bot. Page code lives in `site/assets`; data comes from the pipeline.
