## Changed
- builder.py

## Did
- builder.py: usage_error now prints a second stderr line, 'needs the DeepSeek key in ~/.config/factory/deepseek.key', before the optional reason, so the no-argument usage error names the key a first-time user must provide; the test's literal tilde path is used, not str(KEY_FILE), since KEY_FILE is patched/HOME-dependent.

## Check
- green

## Failing
- (none)

## Unsure
- Whether the intent is for only the no-argument usage error or every usage error to name the key; I made it unconditional, and no other test rejects the extra line.
