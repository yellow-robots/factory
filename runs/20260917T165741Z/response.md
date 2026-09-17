## Changed
- gate.py

## Did
- gate.py: read every build's git output as bytes with a new `_git_bytes`/`_utf8` pair instead of text mode, so a bare carriage return stays part of a value and no output raises.
- gate.py: changed `_build_trailers` to read `%(trailers:key=Built-By,unfold,separator=%x00)`, strip the format's one final newline and split at NUL, returning `<key>: <value>` entries, with empty text as no entry and an empty value as a real entry.
- gate.py: rewrote `_commit_build_problems` to compare the count of `Built-By` message lines against the entries git reads and report how many lines git does not read `as a trailer`, and to check every line value and every entry value for `run <stamp>` and a committed `runs/<stamp>` tree, deduplicating the per-stamp run problem once per commit.
- gate.py: added `_short_hash`, which uses `git rev-parse --short=7` so a commit is named by at least seven unique characters whatever `core.abbrev` says and never the full hash.
- gate.py: made `_line_text` escape only control characters, so non-ASCII text such as `café` and backslashes are quoted unchanged.
- gate.py: added ASCII-whitespace-only strip and split helpers (`ASCII_WHITESPACE`, `_ascii_words`) so a no-break space is kept as git keeps it and stays inside the stamp segment.
- gate.py: matched the `Built-By` line key with `re.ASCII | re.IGNORECASE` so a dotless-i lookalike is not a key.
- gate.py: updated the module docstring to say `check` and `release` read the builds since the highest tag.

## Check
- green

## Failing
- (none)

## Unsure
- The Goal's line '`release` … does not read the builds again' is not visible to any test; `_release_problems` still calls `_build_problems`, so a release re-reads the builds through `check` and again afterwards. The review note judged this none, and every test is green either way, so it was left unchanged.
- `git log --format=%(trailers:key=Built-By,unfold,separator=%x00)` requires a git new enough to support `unfold`; the suite exercises it and passes, so the installed git supports it.
