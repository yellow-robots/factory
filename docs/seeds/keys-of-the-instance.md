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

There is one place a run's model and the place of its key come from, and it is the instance's configuration. The change is four small edits in `builder.py` and nothing else moves, in that file or any other. Each is quoted below as it stands now, so none of it has to be found.

**One.** These two lines, below the imports, are deleted:

```
KEY_FILE = Path.home() / ".config" / "factory" / "deepseek.key"
MODEL = "deepseek-flash"
```

The names stay gone rather than hidden. A module that keeps an attribute and refuses to answer for it is the same two places to look, told apart by a trick, and the point of the goal is that there is one place.

**Two.** In `build_agent`'s signature, `model_name` stops defaulting: the parameter is required, since every caller already passes one.

```
    tools: Tools, key: str = "", http_client: Any = None, model: Any = None, model_name: str = MODEL
```

**Three.** In `read_key`, these two lines go and the parameter becomes required, `path: Path`; its docstring says the file is the one the role names.

```
    if path is None:
        path = KEY_FILE
```

**Four.** In `main`, this block becomes a usage error instead of a fallback:

```
    try:
        builder_role = instance_role("builder")
    except (ValueError, OSError):
        builder_role = None
```

and with it the `else` branch below that used the constants:

```
    else:
        model_name, key = MODEL, ""
```

A configuration holding no `roles`, holding others but not `builder`, or holding a malformed one, is refused in the words `instance.py` already raises for it, naming the configuration's file and the role, before the model is called and before a record is made, in the shape a configuration a run cannot use is already refused. The comment above the block says what is now true.

Two tests are red, both in `test_keys.py`, which is a hundred and ninety lines and holds this seed's tests and nothing else. No test file changes and none may: `test*.py` is protected from write and edit, and what the tests ask for is not a build's to alter.
