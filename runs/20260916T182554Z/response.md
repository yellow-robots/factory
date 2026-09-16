## Changed
- builder.py

## Did
- builder.py: added a second line to usage_error printing 'needs the DeepSeek key in ~/.config/factory/deepseek.key', so a first-time user invoking the builder incorrectly is told where the key lives; the literal tilde path is printed because the test asserts that exact string.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the usage error should also name docker or other prerequisites; the test only requires the key file path, so I named only that.
