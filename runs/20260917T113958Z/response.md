## Changed
- gate.py
- runs.py

## Did
- gate.py: changed USAGE to "usage: uv run gate.py check|render|release <version>" so the usage line names how the program is run, matching the test's startswith assertion.
- runs.py: changed usage_error's stderr line to "usage: uv run runs.py" so the usage error prints the uv run invocation the test looks for.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
