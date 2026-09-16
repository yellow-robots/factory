## Changed
- builder.py

## Did
- builder.py Tools._resolve now refuses any path whose resolved relative parts (or raw path) contain a `.git` component at any depth with `not part of the checkout`, not only a hidden first component.
- builder.py Tools.list now filters `.git` from listings at any depth (not just the root) and reports each entry by basename, so listing `sub` omits `sub/.git` and names `b.txt` as the test requires.
- builder.py Tools._writable now raises `protected: <path> (not the builder's to change: the tests, the toolchain, the vault and git's own files)`.
- builder.py record_diff adds `--text` to the diff flags so a committed `.gitattributes` cannot turn the patch into a binary notice.
- builder.py git_env sets `LC_ALL=C` so git's refusals are read in English.
- builder.py adds git_refusal, and main now decides `not a git checkout` only from the first line of git's stderr after `fatal: `, so a path containing the phrase cannot flip it.
- builder.py numbers.json and the numbers line now carry `written` and `edited`, the ordered paths the tools wrote and edited.

## Check
- green

## Failing
- (none)

## Unsure
- I changed Tools.list to report basenames (required by the `names_in(self.tools.list("sub"))` assertions); I verified all 98 tests pass but did not inspect every other consumer of list output beyond test_builder.py.
- I assume git's invalid-gitfile message begins exactly with `invalid gitfile format`; the stray-.git test passes with that prefix.
