## Changed
- runs.py
- evals.py

## Did
- runs.py: added the shared `tool_errors(record)` function that reads `messages.json`, counts tool-return contents starting `error:` but not with a wall-refusal prefix, and returns None when there are no messages to read.
- runs.py: added `tool_errors` to `COLUMNS` immediately after `checks`, defined the shared `REFUSED` prefixes, and made `_cell(record, numbers, column)` derive the per-record count (empty when None).
- runs.py: extended the module docstring to name `tool_errors` and the shared refusal set.
- evals.py: imported `runs`, added `tool_errors` after `checks` in both `COLUMNS` and `MEDIAN_COLUMNS`, and had `_metric` read the count through `runs.tool_errors` so both tables use one function.
- evals.py: made `_refused` use `runs.REFUSED` instead of a duplicate tuple, so refusal classification is single-sourced.
- evals.py: extended the module docstring to name `tool_errors` and its median/omission behaviour.

## Check
- green

## Failing
- (none)

## Unsure
- Could not verify a non-list but readable messages.json (e.g. a JSON object) beyond treating it as no messages to read; the tests do not cover it.
- The module-level `runs` import in evals.py is shadowed by local `runs` count variables in `_parse`/`main`; harmless since those scopes never touch the module, but noted.
