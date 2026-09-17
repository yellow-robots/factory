---
created: 2026-09-17
type: seed
status: building
summary: A case's only test is the one the model sees, so the set measures whether the builder built the tested thing; a second test it never sees, run after the build, measures whether it built the thing.
value: 4
effort: M
version: v0.12
---

## Evidence

The reviews of v0.7 and v0.9, 2026-09-16 and 2026-09-17: every file read whole by search, so a big file ended the run; `NaN` accepted by JSON aborting the table; line numbers off after a form feed. Each was green against the test the model saw and wrong against a test it did not. The owner's builder competencies of 2026-09-17, mechanics of the runtime, systemic thinking and debugging at the root, all ask the same question: did it build the thing, or the test. Nine cases, no way to ask it.

## Idea

A case may hold `held_out/` beside its test, with tests the model never sees: the harness copies them into the worktree after the build and runs the check once more in the same container, and the table gains `held_out`, the runs whose held-out check ended green; a case expecting green passes only when both did. First cases from the reviews: a search over a file too big to read whole, a record with `NaN`, a bug whose symptom test points away from its root. Depends on the case's expected outcome of pass-rate-error to define the pass.

## Goal

A case may hold `held_out/` beside its test, with `test_*.py` files the model never sees: nothing of it is copied into the worktree before the build. After a run whose check ended green, when the case holds `held_out/`, the harness copies its files into the worktree's root and runs the check once more through the sandbox given to `main`, or the builder's own `Sandbox` when none, on the same worktree and record, numbered after the builder's checks, `checks` in the numbers plus one; the output goes to `held_out.log` in the record and the exit code to `held_out.json` in the record as `{"exit": <code>}`. A run whose check ended red, or that left no record, has no held-out check. A held-out check that raises is a failed run, its error on stderr like a build's, and the set goes on. `evals.py` prints in a column `held_out`, right after `green` in `COLUMNS`, the count of the case's runs whose held-out check ended green, exit 0; the cell is empty for a case without `held_out/`. A case whose word is `green` passes a run only when its check ended green and, when the case holds `held_out/`, the held-out check did too; `red` and `refused` are as they were. The module docstring of `evals.py` names `held_out/` and the column. The tests in `test_evals.py` whose docstring names this seed define the behaviour.
