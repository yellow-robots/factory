---
type: seed
status: done
summary: The seeds now live inside the world the builder reads; it must be able to read them and never write them.
value: 5
effort: S
version: v0.4
---

## Evidence

Decision of 2026-09-16 to move the vault under the repository: a seed beside its tests, readable by the builder as part of the world, so the goal on the command line can become a seed's path. The same move makes the seeds writable by the builder unless the plane says otherwise; today `PROTECTED` in `builder.py` covers the tests and the toolchain only.

## Goal

Add `docs/` to `PROTECTED` in `builder.py`: `write` and `edit` refuse any path under `docs/` with the protected error, and `list` and `read` still work there. The tests in `test_builder.py` whose docstring names this seed define the behaviour.
