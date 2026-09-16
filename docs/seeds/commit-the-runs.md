---
created: 2026-09-16
type: seed
status: done
summary: The run records are the baseline for every eval and live in an ignored folder on one machine; review them and commit them.
value: 4
effort: S
version: v0.4
---

## Evidence

Eight records as of 2026-09-16: three observer runs (v0.1, one of them the escape probe), three on pydantic-ai (v0.2, one contaminated by reading its own plan, one the escape probe), two builder runs (green, honest red). All were copied by hand out of worktrees before those were deleted; one careless removal loses the baseline.

## Goal

Attended git work, not a build. Review the eight records under `runs/` for anything that must not be committed (a key-like string, a secret in a path), remove `runs/` from `.gitignore`, commit the records. The tools keep hiding `runs`. The test naming this seed asserts that `.gitignore` no longer lists `runs/`. If the records grow past what a source repository should carry, a separate repository or a store is a later seed.
