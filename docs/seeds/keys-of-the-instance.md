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

There is one place a run's model and the place of its key come from, and it is the instance's configuration. The change is small and every part of it is named below; nothing else in `builder.py` and nothing at all in any other file needs to move, so there is nothing to go looking for.

- The two module constants `KEY_FILE` and `MODEL`, just below the imports, are deleted. The names stay gone rather than hidden: a module that keeps an attribute and refuses to answer for it is the same two places to look, told apart by a trick, and the point of the goal is that there is one place.
- `read_key` takes the path of the key file and no longer defaults it: the parameter is required, the branch that falls back when it is None goes, and the docstring says the file is the role's.
- `build_agent`'s `model_name` no longer defaults to the constant: it is required, and every caller already passes one.
- In `main`, the block that reads `instance_role("builder")` inside a `try` and falls back when it is missing or malformed becomes a usage error: a configuration holding no `roles`, holding others but not `builder`, or holding a malformed one, is refused in the words `instance.py` already raises, naming the configuration's file and the role, before the model is called and before a record is made. The `else` branch that used the constants goes with it, and the comment above the block says what is now true.

The suite's fixtures already name a role, so no test file changes, and none may: `test*.py` is protected from write and edit, and what the tests ask for is not a build's to alter. Two tests are red, both in `test_keys.py`, which is two hundred lines and holds this seed's tests and nothing else.
