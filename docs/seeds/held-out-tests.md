---
created: 2026-09-17
type: seed
status: open
summary: A case's only test is the one the model sees, so the set measures whether the builder built the tested thing; a second test it never sees, run after the build, measures whether it built the thing.
value: 4
effort: M
version:
---

## Evidence

The reviews of v0.7 and v0.9, 2026-09-16 and 2026-09-17: every file read whole by search, so a big file ended the run; `NaN` accepted by JSON aborting the table; line numbers off after a form feed. Each was green against the test the model saw and wrong against a test it did not. The owner's builder competencies of 2026-09-17, mechanics of the runtime, systemic thinking and debugging at the root, all ask the same question: did it build the thing, or the test. Nine cases, no way to ask it.

## Idea

A case may hold `held_out/` beside its test, with tests the model never sees: the harness copies them into the worktree after the build and runs the check once more in the same container, and the table gains `held_out`, the runs whose held-out check ended green; a case expecting green passes only when both did. First cases from the reviews: a search over a file too big to read whole, a record with `NaN`, a bug whose symptom test points away from its root. Depends on the case's expected outcome of pass-rate-error to define the pass.
