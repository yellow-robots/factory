## Changed
- builder.py

## Did
- builder.py: added read_seed(checkout, arg), which returns text unchanged with seed None, or resolves a .md argument inside the checkout, reads the note, and returns `seed: <name without .md>` plus the stripped text of its ## Goal section, raising ValueError for a missing file, a note with no ## Goal, or an empty section.
- builder.py: in main, after the checkout checks, goal is set through read_seed and a ValueError/OSError becomes usage_error (exit 2) before any run directory is created.
- builder.py: added `seed` to the numbers dict so numbers.json and the numbers line carry the seed name or null.

## Check
- green

## Failing
- (none)

## Unsure
- AGENTS.md still says a build is run with the seed's goal; the seed's last line assigns that wording change to the attended agent after the build, so I left it, and no test checks it.
