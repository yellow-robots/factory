---
type: seed
status: building
summary: world and plane are the observer's words; the builder works on a checkout with tools, and the code, the role and the documents should say so.
value: 3
effort: S
version: v0.5
---

## Evidence

The owner, 2026-09-16: both terms are inherited from the observer iteration and should give way to specific ones. Every run so far had a git checkout as its world; the plain-directory path in `builder.py` exists for no run. `plans` sits in HIDDEN for a folder that no longer exists.

## Goal

`builder.py` works on a checkout with tools, and the words follow. `Plane` becomes `Tools`, and every `world` in names, parameters, keys, docstrings, comments, messages and the usage line becomes `checkout`: the usage line reads `builder.py <checkout> "<goal>"`, the numbers key `world` becomes `checkout`, `world_head` becomes `head` in the numbers and the function that computes it becomes `head()`. In the role text `a world` becomes `a checkout` and nothing else in it changes. The checkout must be a git checkout: a directory without `.git` is a usage error, exit 2, before any run directory exists, so the branches that record `not a git checkout` and a null head go, and `head` is always a commit. `plans` leaves `HIDDEN`. `test_builder.py` already uses the new names; the tests whose docstring names this seed define the behaviour and the rest of the suite must stay green.

The documents follow after the build, by the attended agent: `README.md`, `AGENTS.md`, the seed template and the seeds say checkout and tools; the notes of v0.1 to v0.4 keep their words as history, and one sentence in `AGENTS.md` maps the old words to the new.
