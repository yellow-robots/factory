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

The builder runs as the role `builder` when the instance's configuration holds one: the model it runs on and the file it reads its key from are that role's, read through `instance.py`, and the run's record names the model the role gave, where it already names a model. A configuration that holds no such role changes nothing yet — the constants of `builder.py` still answer — so every fixture of the suite that patches the key's place keeps working exactly as it does now. That fallback is the next goal's to remove.

A key file the role names that cannot be read, or that holds nothing once stripped, is a usage error naming that file, exit 2, refused before the model is called and before a record is made, exactly as the one key already is.

Only `builder.py` changes here. No test file's fixtures are touched, and `instance.py` is already what it needs to be.
