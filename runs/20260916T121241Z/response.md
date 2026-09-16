## Changed
- gate.py

## Did
- Added gate.py at the repository root with main(argv, root=None) that defaults root to the script's directory and dispatches check, render and release, printing usage to stderr and returning 2 for a missing/unknown command or release without a version.
- Implemented problems_check in gate.py: frontmatter type must name docs/templates/<type>.md for every .md under docs/ except templates/, plus wikilink resolution by path/name or .base.
- Implemented seed validation in gate.py: allowed fields, status in the five values, summary/value 1-5/effort S-M-L from open on, version note plus ## Goal from spec on, and a test method/class docstring containing seed: <stem> from building on (parsed with ast so comments do not count).
- Implemented version-note validation in gate.py: only the type field, v<major>.<minor>.md names, at most one untagged note, and tagged versions having only done/rejected seeds.
- Implemented problems_render in gate.py to write CHANGELOG.md newest-first from git tags, using each version note's title line, git commit date, first paragraph and ## Changelog bullets while dropping embeds and other sections.
- Implemented release in gate.py to run check, then refuse on a missing/already-tagged version, non-done seeds, no changelog bullets, a dirty git status, unchanged AGENTS.md since the highest tag, or a red unittest suite; otherwise it creates an annotated tag with the note's paragraph and bullets and renders the changelog.

## Check
- green

## Failing
- (none)

## Unsure
- Whether 'from building on' should require a naming test docstring for rejected seeds; I included rejected since it follows building in the listed status order, and the tests do not distinguish this.
- Whether render's 'newest first' should order by version number or by git tag date; I sort by parsed v<major>.<minor>, which matches the test's ordering.
- Whether check passes on the factory's own docs/ (tests run on temporary vaults only); I did not verify the real vault.
