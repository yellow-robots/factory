---
created: 2026-09-16
type: seed
status: done
summary: The goal travels as a sentence on a command line and the report as five lists; the input should be a seed in the checkout and the output machine-readable for the next step.
value: 3
effort: M
version: v0.7
---

## Evidence

Owner's item 4, 2026-09-16. Every build so far took its goal from the shell, the attended agent copying the seed's Goal section into the command line by a script; the seed itself sits in the checkout the builder reads, at the commit the run is pinned to. `report.json` and `numbers.json` are already typed; the gate, `runs.py` and `evals.py` are their machine readers.

## Goal

`builder.py` takes as its goal argument either text or the path, relative to the checkout, of a seed note. The argument is a path when it is one word ending in `.md`, no whitespace in it; every other argument is text, the goal as it is, and `seed` is null: a sentence that ends in a file's name, or a goal of several lines, is text. The note is read from the checkout's commit, `git show HEAD:<path>`, not from the working tree, so the record's `head` names exactly the text the model was given; a path that is not in the commit, `..` and absolute paths among them, or a note without a `## Goal` with text under it, is a usage error, exit 2, before any run directory exists. The goal the model is given is `seed: <file name without .md>` on the first line and the section's text after it; `goal.txt` records exactly that, and `numbers.json` carries `seed`, the name, in the numbers line too. The `## Goal` section runs from its heading to the next heading of level one or two; a fenced code block inside it belongs to it whole, whatever its lines start with; `%%` comments, a line or a block between the marks, are not the note's text, so a `## Goal` inside one is not the heading and a comment inside the section is not the goal. `runs.py` and `evals.py` need nothing new: the goal column shows the first line. The tests in `test_builder.py` whose docstring names this seed define the behaviour.

After the build, by the attended agent: the builds of the next seeds are run with the seed's path, and `AGENTS.md` says so.
