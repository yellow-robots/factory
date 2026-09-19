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

The search that keeps a key out of a record never fails open, and there is one place left where it does. `configured_keys` catches the error `key_paths()` raises for a configuration whose `roles` are missing or malformed and answers with an empty list; `leaked_file` then searches a record for nothing and the record is committed. A configuration that cannot say what a key is turns the wall off silently, which is the opposite of what every other case of this function does — a file it cannot read through, a truncated `.gz`, a link it will not walk into all refuse the commit.

```
    try:
        paths = key_paths()
    except (ValueError, OSError):
        return []
```

That error refuses the commit instead, as an unreadable key file already does: a `LeakedKey` carrying the words `instance.py` raised, which name the configuration's file and the fault, and never a key's value. An empty list of keys is refused the same way, whatever produced it, because a record searched for nothing has not been searched.

The docstring says what is now true. Its last sentence claims the empty list "falls back to the program's constants as the run does", which the code never did and which the run no longer does either.

Nothing else moves, in `builder.py` or any other file. One test is red, `test_a_configuration_that_names_no_key_refuses_the_commit`, in `test_keys.py`.
