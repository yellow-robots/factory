---
created: 2026-09-16
type: seed
status: building
summary: The record of a run must be complete and git's answers must be read exactly; the review of v0.5's last build found four ways they are not yet.
value: 5
effort: S
version: v0.6
---

## Evidence

The independent review of v0.5's last build, 2026-09-16, verified in throwaway repositories: a path with a `.git` component below the root, `sub/.git/x`, is written by the tools and never listed by git, so it is absent from `diff.patch` and from the numbers, and three such writes forge a nested repository that hides a whole subtree from the record; a committed `.gitattributes` with `* -diff` turns the patch into a binary notice; the not-a-checkout test is a substring match over all of git's stderr, so a path containing the phrase, or a git speaking another language, flips it; the refusal the model reads for `.gitignore` names the tests and the toolchain, which it is neither.

## Goal

In `builder.py`: any path with a `.git` component at any depth is not part of the checkout, refused by every tool as `not part of the checkout` and left out of listings, as `.git` at the root already is. `numbers.json` carries `written` and `edited`, the paths the tools wrote and edited in order, so the record names every file the run touched whatever git lists, and the numbers line carries them too. The diffs of `record_diff` run with `--text` as well, so an attribute cannot turn the patch into a binary notice. `git_env()` sets `LC_ALL` to `C`, so git answers in English, and the not-a-checkout test reads the first line of git's stderr after `fatal: ` and nothing else. The refusal the model reads for a protected path says `protected: <path> (not the builder's to change: the tests, the toolchain, the vault and git's own files)`. The tests in `test_builder.py` whose docstring names this seed define the behaviour; `check.Dockerfile`'s comments say checkout, by the attended agent.
