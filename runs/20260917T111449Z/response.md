## Changed
- builder.py

## Did
- builder.py: usage_error now prints a second line, `needs the DeepSeek key in ~/.config/factory/deepseek.key and docker`, so a first-time user told the usage line alone also learns the key file they must provide.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the goal's 'the usage error' also intends the sibling usage errors in evals.py and runs.py; the only test, test_ambiguous_goal.py, drives builder.main, so I changed builder.py alone.
