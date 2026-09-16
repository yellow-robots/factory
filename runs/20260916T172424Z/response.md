## Changed
- builder.py

## Did
- builder.py: added a line to usage_error so the usage error names the provider key file ~/.config/factory/deepseek.key (with its format), telling a first-time user what they need; this is printed for every usage error and satisfies test_the_usage_error_names_the_key_file.

## Check
- green

## Failing
- (none)

## Unsure
- whether the maintainers prefer the key hint on every usage error versus only the missing-arguments case; the test only pins the no-args case and existing tests only assert substring presence, so printing it always was safe.
