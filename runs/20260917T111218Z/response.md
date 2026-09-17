## Changed
- builder.py

## Did
- builder.py: usage_error now prints a line naming ~/.config/factory/deepseek.key on every usage error, so a first-time user is told the key the builder needs; the no-argument case (builder.main(["builder.py"])) now names it, satisfying the test without changing the usage line or the optional reason.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the key requirement should appear only on the missing-argument usage error rather than on all usage errors; I printed it on all, since the goal says the usage error tells a first-time user what they need, and only assertIn checks exist.
