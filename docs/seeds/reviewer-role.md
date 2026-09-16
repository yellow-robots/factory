---
type: seed
status: open
summary: A read-only role pointed at a diff with the goal "find defects", so a build is judged by a cold session before the attended agent reads it.
value: 4
effort: M
version:
---

## Evidence

Every diff so far was read by the attended agent, a model in another harness. The independent reviews of v0.2 and v0.3 found real defects the builder and the attended agent had missed. Pinned by the owner on 2026-09-16 until the builder is validated.

## Idea

The observer's tools plus a `diff()` function, a typed report of findings with severity, path and line, and a verdict. First eval case: its report on a known diff against the attended agent's.
