---
type: seed
status: spec
summary: A run is comparable and reproducible only if the world it ran on is a known commit; record it and refuse a dirty world.
value: 3
effort: S
goal: builder.py records the world's HEAD commit as `world_head` in numbers.json and, when the world is a git checkout with uncommitted or untracked changes, exits 2 with a usage error naming the first few dirty paths before any run directory is created; a world that is not a git checkout records `world_head` as null and runs.
acceptance: test_builder.py MainTest, a dirty git world refused with no run directory, a clean one recording the commit, a plain directory recording null; written before the build.
version: v0.4
crossed_to:
created: 2026-09-16
---

## Evidence

The two builder runs of 2026-09-15 ran on worktrees whose commit is known only from the shell
history; numbers.json holds the world path, not the commit. The evals (failure-mode set, variance)
need two runs of one case to be on the same world.

## Idea

Read-only git from the factory side, as `record_diff` already does. The refusal is a wall for the
attended agent, not the model: it forces the red tests to be committed before a build.
