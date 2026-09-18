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

A configuration that cannot say which key a run uses is refused, rather than quietly answering with the program's own. In `main`, this block stops falling back:

```
    try:
        builder_role = instance_role("builder")
    except (ValueError, OSError):
        builder_role = None
```

A configuration holding no `roles`, holding others but not `builder`, or holding a malformed one, is refused in the words `instance.py` already raises for it, naming the configuration's file and the role, before the model is called and before a record is made, in the shape a configuration a run cannot use is already refused. The `else` branch below that used the constants becomes unreachable and goes with it; the comment above the block says what is now true.

Nothing else moves, in `builder.py` or in any other file. `KEY_FILE` and `MODEL` stay where they are for now, with nothing left that reads them; taking them out is its own seed, since five runs were cut off by the caps trying to do it here.

One test is red, `test_a_configuration_that_does_not_hold_the_builder_s_role_is_a_usage_error`, in `test_keys.py`, which is a hundred and eighty lines and holds this seed's tests and nothing else. No test file changes and none may: `test*.py` is protected from write and edit.
