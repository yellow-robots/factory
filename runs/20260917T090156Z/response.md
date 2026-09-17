## Changed
- gate.py

## Did
- Added `_segment` in gate.py and used it in `_review_runs_problems`, so a `runs:` stamp is refused unless it is one path segment (non-empty, not `.`/`..`, no `/` or `\`) before any `runs/<stamp>` lookup, instead of `/etc` resolving to the filesystem root.
- Rewrote the judged handling in `_judged_problems` in gate.py so a `judged:` with nothing after it or an empty comma-separated piece is reported as `has no judged`, and each `test`/`case`/`seed` name is refused unless it is one path segment before being looked up.
- Added `_prose_lines` in gate.py and made `_finding_problems` read `severity:`/`verified:`/`judged:` only from prose lines, skipping fenced code blocks (via `builder.opening_fence`/`closing_fence`) and indented code blocks (four spaces or a tab), so a line inside a code block never satisfies the finding's fields.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
