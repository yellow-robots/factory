## Changed
- evals.py

## Did
- evals.py: imported math so `_number` can reject non-finite floats.
- evals.py: `_number` now returns None for a non-finite float (JSON NaN/Infinity), so such a value is treated as a measure the run lacks by the median, spread and summed cost alike.
- evals.py: the module docstring now states the spread beside the `requests`, `cost_usd` and `seconds` medians is printed as `min-max`.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
