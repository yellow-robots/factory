---
type: seed
status: spec
summary: The specs now live inside the world the builder reads; it must be able to read them and never write them.
value: 5
effort: S
goal: Add `docs/` to PROTECTED in builder.py so write and edit refuse any path under it with the protected error, while list and read still work there.
acceptance: test_builder.py PlaneTest, a write and an edit under docs/ refused, a read under docs/ allowed; written before the build.
version: v0.4
crossed_to:
created: 2026-09-16
---

## Evidence

Decision of 2026-09-16 to move the vault under the repository: a spec beside its tests, readable
by the builder as part of the world, so the goal on the command line can be a spec's path. The
same move makes the specs writable by the builder unless the plane says otherwise; today PROTECTED
covers tests and the toolchain only (`builder.py`, PROTECTED).

## Idea

One more entry in the tuple and two tests. The builder's report may cite the spec it read; the
gate later checks that a build's goal names a spec that exists.
