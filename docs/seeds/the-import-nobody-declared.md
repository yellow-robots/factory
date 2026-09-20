---
created: 2026-09-20
type: seed
status: open
summary: Two libraries the factory imports by name are declared by nothing; they resolve because something else happens to depend on them.
value: 2
effort: S
version:
---

## Evidence

2026-09-20, the independent review of [[the-role-priced-as-another]], recorded in [[20260920T103952Z]].

`builder.py` imports `genai_prices` at module scope, as of that build, and has imported `httpx2` that way since v0.2. `pyproject.toml` declares one dependency: `pydantic-ai-slim[openai]==2.43.0`. Neither name appears in it.

They resolve because the library depends on both, and `uv.lock` pins the versions that got pulled in -- `genai_prices` at `uv.lock:411`. So nothing is broken today and nothing has ever been broken by it.

What it costs is that `import builder` stops working the day the library drops either, and `import builder` is the first line of `gate.py`, `runs.py`, `build.py` and `reviewer.py`. The whole factory would fail to start over a transitive dependency someone else decided not to ship, and the error would name a module rather than a version.

It is also a claim about what we pin. `uv.lock` pins what was resolved; `pyproject.toml` says what we asked for. A library we import by name is one we asked for, and the lock file is not the place that records the asking.

## Idea

What the factory imports, the factory declares.

`pyproject.toml` names every library imported at the top of a program the factory runs, at the versions the lock already holds, so the lock keeps pinning what it pins and nothing about any run changes. The measure that it worked is that nothing moves: same lock, same versions, same records.

`pyproject.toml` and `uv.lock` are both PROTECTED, so this is the attended agent's to do and not a build. It is small, and the reason to do it is the day it stops being small.
