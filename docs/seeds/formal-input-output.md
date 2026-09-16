---
created: 2026-09-16
type: seed
status: building
summary: The goal travels as a sentence on a command line and the report as five lists; the input should be a seed in the checkout and the output machine-readable for the next step.
value: 3
effort: M
version: v0.7
---

## Evidence

Owner's item 4, 2026-09-16. Every build so far took its goal from the shell, the attended agent copying the seed's Goal section into the command line by a script; the seed itself sits in the checkout the builder reads, at the commit the run is pinned to. `report.json` and `numbers.json` are already typed; the gate, `runs.py` and `evals.py` are their machine readers.

## Goal

`builder.py` takes as its goal argument either text or the path, relative to the checkout, of a seed note. When the argument ends in `.md` and names a file in the checkout whose body has a `## Goal` section with text under it, the goal the model is given is `seed: <file name without .md>` on the first line and the section's text after it; `goal.txt` records exactly that, and `numbers.json` carries `seed`, the name, in the numbers line too. The note is read from the checkout as it is. A path ending in `.md` that names no file in the checkout, or a note without a `## Goal` with text under it, is a usage error, exit 2, before any run directory exists. Text stays text, and `seed` is null. `runs.py` and `evals.py` need nothing new: the goal column shows the first line. The tests in `test_builder.py` whose docstring names this seed define the behaviour.

After the build, by the attended agent: the builds of the next seeds are run with the seed's path, and `AGENTS.md` says so.
