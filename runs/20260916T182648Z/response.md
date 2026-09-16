## Changed
- builder.py

## Did
- builder.py: usage_error now prints a second line naming the key file (with the home directory written as `~`, derived from KEY_FILE) and docker, so a first-time user who runs the program with no arguments is told what the build needs; a patched or non-home KEY_FILE falls back to its absolute path, and any usage-error reason still follows on its own line.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the goal intended more than naming the key file; only the key path is asserted by the case test, so docker was mentioned to match README/AGENTS.md.
