## Changed
- evals.py

## Did
- evals.py: added `requests_spread`, `cost_usd_spread` and `seconds_spread` to COLUMNS right after their medians, matching the test's COLUMNS.
- evals.py: added SPREAD_COLUMNS naming the three measures that decide a comparison.
- evals.py: extracted `_number_text` from `_median_text` and added `_spread_text`, which renders the lowest and highest values as `min-max` using the same number formatting and returns empty for no values.
- evals.py: in `_row`, the metric values for each median column are collected once and, for a SPREAD_COLUMNS column, the spread cell is appended right after the median cell, so a missing measure is left out of both.

## Check
- green

## Failing
- (none)

## Unsure
- Docs (README.md, AGENTS.md, docs/versions) already describe the spread column, so no doc change was needed; I did not verify any other consumers of COLUMNS outside the tests.
