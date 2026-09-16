---
type: seed
status: spec
summary: The run records are the baseline for every eval and live in an ignored folder on one machine; review them and commit them.
value: 4
effort: S
goal: Review the nine records under runs/ for anything that must not be committed (a key-like string, a path that is a secret), remove runs/ from .gitignore, and commit the records; the builder's world keeps hiding runs regardless.
acceptance: git ls-files runs lists every record; a grep for key-like strings over runs/ finds nothing; test_builder.py still hides runs at the world root.
version: v0.4
crossed_to:
created: 2026-09-16
---

## Evidence

Nine records as of 2026-09-16: three observer runs (v0.1), three on pydantic-ai (v0.2, one of
them contaminated by reading its own plan), two builder runs (green, honest red), one adversarial
probe. All were copied by hand out of worktrees before those were deleted; one careless removal
loses the baseline.

## Idea

Attended git work, not a build. Once committed, `record-as-table` reads them from any checkout.
If the records grow past what a source repository should carry, a `factory-runs` repository or a
store is a later seed.
