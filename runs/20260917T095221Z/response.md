## Changed
- runs.py
- evals.py

## Did
- runs.py: added a WALLS tuple for the non-refusal wall returns, `error: cap reached` and `error: no sandbox`, and excluded them in tool_errors, so only the model's own `error:` returns are counted.
- evals.py: rewrote the comment over MEDIAN_COLUMNS to say tool-errors is read from runs.py, where the one count is computed, rather than computed in evals.py.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the docstring wording in runs.tool_errors ('not a wall's refusal') should also be broadened to 'wall's return'; it is not asserted by any test and behaviour is correct.
