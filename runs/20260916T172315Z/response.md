## Changed
- builder.py

## Did
- builder.py: added a KEY_HINT constant holding "~/.config/factory/deepseek.key", the key path as a first-time user reads it
- builder.py: usage_error now prints a second stderr line naming the DeepSeek key file (and docker), so the usage error tells a first-time user what they need

## Check
- green

## Failing
- (none)

## Unsure
- The test only asserts the key-path substring, so the exact wording of the added usage hint beyond that literal is my choice and not otherwise verified
