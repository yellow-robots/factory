---
created: 2026-09-19
type: seed
status: building
summary: The leak scan searches a record for one key's value and the key's path is a constant of the program, so a run made on a second provider has its record searched for the wrong key; the instance's configuration describes the roles it runs, each with its model and its key, and every key it names is searched for.
value: 5
effort: M
version: v0.15
---

## Evidence

2026-09-19, read in the code by the attended agent after the owner put a second key on the host at `~/.config/factory/glm.key` for the reviewer to use: `KEY_FILE` is one hardcoded path, `read_key()` returns one key, and `leaked_file(run_dir, key)` searches a record's files for one value. The wall that has held since v0.13 — no record is committed that holds the key — covers exactly one key, the one the run was given. A run made on the second provider would have its record searched for the first provider's key and committed clean, with the second key's value in it if the model or a tool ever echoed it. The wall does not fail loudly; it passes.

`MODEL` and the provider class are module constants of `builder.py`, so a second model is not expressible without editing the program, and a role cannot name the model it runs on.

The instance's configuration already names `records` and `work`, read by `instance.py`, which imports nothing of the builder's. It is where a key's place belongs too: the key's path has been a constant since v0.1, which installation-and-surfaces already reads as a fault of the surface rather than of the program.

## Goal

There is one place a run's model and the place of its key come from, and it is the instance's configuration. `MODEL` and `KEY_FILE` are gone from `builder.py`, and with them the fallback the previous goal left: a configuration that holds no `roles` at all, or holds others but not `builder`, is a usage error naming the configuration's file and the role, refused before the model is called and before a record is made, in the shape a configuration a run cannot use is already refused.

The suite's own fixtures follow, and this is the bulk of the goal: every place that patched `builder.KEY_FILE` writes a configuration holding a `[roles.builder]` table instead, naming a model and that same key file, in `test_builder.py`, `test_build.py` and `test_evals.py` alike. `search` finds them faster than reading the files whole.

Nothing else changes: what searches a record still searches for the one key the run was given.
