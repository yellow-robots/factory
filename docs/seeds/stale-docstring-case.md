---
created: 2026-09-17
type: seed
status: building
summary: Twice this week a build changed a behaviour a module docstring describes and left the docstring as it was; the reviews caught it, the set has no quality case at all. The first one.
value: 4
effort: S
version: v0.12
---

## Evidence

v0.7's first search build left the module docstring counting five tools, as its own report noted; v0.9's first build left `evals.py` saying medians alone while README and AGENTS.md said the spread. Both green, both caught by a review, both fixed by a follow-up build. Quality, building the right way, is the category with no case, 2026-09-17.

2026-09-17, v0.11: the build 20260917T095623Z rewrote the enumeration of the counts in the docstring of `evals.py`, which a test named, and left the sentence beside it saying the tool errors are "not a wall's refusal" after the build before it, 20260917T095221Z, had added the caps to the walls; `runs.py` says the same. Two docstrings stale in one version, both a sentence away from a line the model did rewrite.

## Idea

A case whose goal changes a behaviour the module docstring describes, the visible test on the behaviour, a held-out test on the docstring. Pass is both green. Needs held-out-tests first; until then the case can exist with its held-out test unread, its `held_out` column empty.

## Goal

A case `docstring_left_behind`: `wordcount.py`, whose module and function docstrings say words are split on spaces, a goal that makes any whitespace split them, the visible test on the behaviour, the held-out test on the two docstrings; pass is green. With it the second held-out case the reviews asked for, `symptom_not_root`: `ledger.py`, whose `parse` drops a debit's sign, a goal that says a debit lowers the balance, the visible test on the balance, the held-out test on `parse`. Both are the attended agent's, like the tests, and need no build; the test in `test_evals.py` whose docstring names this seed holds the repository's cases whole and the two with `held_out/` named.
