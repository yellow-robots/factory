---
created: 2026-09-16
type: seed
status: open
summary: Two runs are a demonstration; a dozen goals on the factory's own code, each probing a known way to fail, each run three times, make the builder measurable.
value: 5
effort: M
version:
---

## Evidence

G1 (`20260915T160616Z`, green in 3 edits) and G2 (`20260915T160651Z`, honest red) are the whole record of the builder. v1's incidents (findings report) name the ways a builder fails: works around the test, invents what the spec left open, changes what it did not need to, gives up, or declares green on red.

## Idea

Cases, each with its red test: a change across two files; a new file; an edit whose anchor is not unique in a 600-line file; an ambiguous goal; a test that fails for an environmental reason; a goal a lazy solution satisfies by deleting behaviour; a goal that needs more than 8 checks. Measures per case: green rate, honest-red rate, edits, checks, cost, protected-path attempts, diff size against the minimal patch. Three runs each (see `variance-runs`). The set is what lets a second model be tried at all.
