---
type: seed
status: spec
summary: A run is comparable and reproducible only if the world it ran on is a known commit; record it and refuse a dirty world.
value: 3
effort: S
version: v0.4
---

## Evidence

The two builder runs of 2026-09-15 ran on worktrees whose commit is known only from the shell history; `numbers.json` holds the world path, not the commit. The evals (`failure-mode-set`, `variance-runs`) need two runs of one case to be on the same world. The refusal is a wall for the attended agent, not for the model: it forces the tests to be committed before a build.

## Goal

`builder.py` records the world's `HEAD` commit as `world_head` in `numbers.json`. When the world is a git checkout with uncommitted or untracked changes, it exits 2 with a usage error naming the first dirty paths, before any run directory is created. A world that is not a git checkout records `world_head` as null and runs. Read-only git from the factory side, as `record_diff` already does. The tests in `test_builder.py` whose docstring names this seed define the behaviour.
