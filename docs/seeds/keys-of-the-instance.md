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

The instance's configuration describes the roles the instance runs. Beside `records` and `work` it holds a `roles` table, one entry per role, each naming the `model` that role runs on and the `key` file it reads; a role may also name a `base_url`, for a model served somewhere other than the provider the factory uses by default. A role is a name: `builder` is the one that exists, and a configuration may hold others.

`instance.py` reads the roles as it reads the rest, importing nothing of the builder's. It answers with a role's model, the path of its key and its base URL, and with the path of every key the configuration names, each once; it never reads a key file, because a key's value is the caller's to read and should live in as few places as it can.

A `roles` that is missing, is not a table, or holds an entry that is not a table, that has no `model` or no `key`, or whose `model` is not a string or whose `key` is not a string or not an absolute path, is a ValueError naming the configuration's file and which fault, in the shape `record_store` and `work_dir` already use. Asking for a role the configuration does not hold is the same kind of error, naming the configuration and the role.

Nothing of `builder.py` changes in this goal: the builder still reads its key from its own constant, and what searches a record still searches for one key. This goal is the configuration's reader alone.
