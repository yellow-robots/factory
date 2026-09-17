## Changed
- gate.py

## Did
- gate.py: added _git_out returning git's exit status plus stdout with errors="replace", and made _git use it, so a failing git is visible and non-UTF-8 output is decoded with replacements instead of raising.
- gate.py: added _line_text to escape a value's control characters so a problem that quotes it stays one line (needed for the form-feed value the test's splitlines would otherwise split).
- gate.py: rewrote _builds to run `git rev-list <rev> --` and return the failing command when git exits non-zero, so paths like a file named `v0.1..HEAD` never hide the builds.
- gate.py: rewrote _build_trailers to keep git's `%(trailers:key=Built-By,valueonly)` output split at newlines with an empty value counted, and to return None when the command fails.
- gate.py: added _commit_build_problems that matches lines beginning `Built-By` in any case with spaces before the colon, checks every value for being read by git, for ending in `run <stamp>` with a one-segment stamp, and for `runs/<stamp>` being a tree (not a file or link) in HEAD's tree, naming the abbreviated hash.
- gate.py: rewrote _build_problems to report every build problem once, or one problem naming the failing git command.
- gate.py: made problems_check read the builds since the highest tag and report them under the in-flight version note (or `docs/versions/` when none), so check sees an unread build before main moves.
- gate.py: updated the _release_problems call to the new _build_problems note-path signature.

## Check
- green

## Failing
- (none)

## Unsure
- I could not run git directly; I relied on the review note that valueonly prints a blank line for an empty value and assumed git's trailer separator is the newline it terminates the atom with.
- The no-tag branch (_builds with previous=None reading every commit) is unpinned by tests and only exercised by code inspection.
