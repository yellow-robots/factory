---
created: 2026-09-19
type: seed
status: open
summary: The leak scan searches a record for one key's value and the key's path is a constant of the program, so a run made on a second provider has its record searched for the wrong key; the instance holds keys, a role names the one it uses, and every one of them is scanned.
value: 5
effort: M
version:
---

## Evidence

2026-09-19, read in the code by the attended agent after the owner put a second key on the host at `~/.config/factory/glm.key` for the reviewer to use: `KEY_FILE` is one hardcoded path, `read_key()` returns one key, and `leaked_file(run_dir, key)` searches a record's files for one value. The wall that has held since v0.13 — no record is committed that holds the key — covers exactly one key, the one the run was given. A run made on the second provider would have its record searched for the first provider's key and committed clean, with the second key's value in it if the model or a tool ever echoed it. The wall does not fail loudly; it passes.

`MODEL` and the provider class are module constants of `builder.py`, so a second model is not expressible without editing the program, and a role cannot name the model it runs on.

The instance's configuration already names `records` and `work`, read by `instance.py`, which imports nothing of the builder's. It is where a key's place belongs too: the key's path has been a constant since v0.1, which installation-and-surfaces already reads as a fault of the surface rather than of the program.

## Idea

The instance's configuration names its keys, beside `records` and `work`, and `instance.py` reads them as it reads the rest. A role names the key it uses and the model it runs on, so the model and its provider stop being constants of the program and become properties of the run — which is what a reviewer stronger than the builder needs, and what a set run comparing two models needs after it.

The leak scan searches a record for **every key the instance holds**, not the key the run was given, so a record that carries any of them is refused by the same wall, named the same way, and the run that made it is the one that fails. A key file that cannot be read, or that holds nothing, is a usage error naming that key and refused before a model is called, as the one key already is.
