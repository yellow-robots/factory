---
created: 2026-09-20
type: seed
status: open
summary: A review reads the working tree while its prompt describes the committed diff, records nothing about the difference, and is indistinguishable from a build in the table of runs.
value: 3
effort: S
reporter: review
kind: integrity
version:
---

## Evidence

2026-09-20, from the independent review of run 20260920T000130Z, the first review of `reviewer.py`. Three findings that are not wrong and are less than the role claims of itself, kept together because all three are about what a record of a review fails to say.

**The tree it read is not the change it was shown.** `builder.main` refuses a checkout with uncommitted or untracked changes, so a build is reproducible from its record. `reviewer.py` refuses nothing of the kind. Its `list`, `read` and `search` serve the **working tree**; the diff in its prompt is `parent..head`, **committed**. The reviewer demonstrated them disagreeing: a file edited and not committed reads back to the model as `x = 999  # uncommitted` while the diff in the same prompt says `x = 2`. So a review can report on lines that are not in the change under review, or miss lines that are, and `numbers.json` gives a later reader no way to know it happened. The Goal did not ask for the refusal, which is why this is a smell; but *a role that cannot be measured cannot be given a responsibility* argues for at least recording the dirt. Goal D's harness will hold the tree clean by construction. `uv run reviewer.py` by hand will not, and that is how every review will be run until D exists.

**`WireModel` keys on the test seam, not on whether the model speaks HTTP.** `run_model = None if model is None else WireModel(model, wire)` decides "does this go over HTTP?" by "did a caller pass a model?", and `build_agent` discards `http_client` whenever one is given. Hand `main()` a real model -- which is exactly what `evals.py` and `build.py` both do, threading `model=` into `builder.main` -- and the record keeps one wire line with an empty url, a null status, no headers and no response, while `wire_attempts` reads 0. Production today is clean, which the attended agent confirmed separately: the unwrapped path records the genuine request, `tool_choice` is `auto`, the key is not in the wire, and the offered tool names match what the library sends. What is missing is the reviewer's equivalent of `test_the_request_the_library_sends_has_the_plan_shape`, which pins the builder's production request through the real model class over a mock transport.

**A review is indistinguishable from a build in `runs.py`.** The record lands in the same store, `COLUMNS` has no `role_name`, and `goal.txt` deliberately strips the `seed: <name>` line that would have marked the row. Evaluation records are told apart by their goal's `case: <name>` prefix; a review has no prefix at all. `AGENTS.md` calls `uv run runs.py` every record's numbers as one table, and from 2026-09-20 it is two kinds of run in one table with no column that separates them.

One more, smaller, from the same review: `call_budget` still adds `WRITE_CAP + CHECK_CAP`, 38 calls, as an allowance for tools the reviewer does not have -- 26% of its budget on this checkout and 48% on a small one. [[the-walk-that-bounds-nothing]] deletes that formula, so this resolves itself there rather than here.

## Idea

A review's record says what it read and what it is.

The tree's cleanliness is part of the record. Either a dirty checkout is refused as a build's is, which is the simple answer and costs a line, or the dirt is recorded and a reader can weigh the review knowing the tools and the diff disagreed. Refusing is better: the two halves of what the model was shown should describe the same tree, and a review of a tree nobody can reconstruct is not evidence.

The wire says what was sent, whoever sent it. The wrapper's condition becomes the thing it is actually about -- whether the model speaks HTTP -- rather than whether a caller passed one, and a request recorded by the wrapper is distinguishable in the record from one recorded off the wire, because they are not the same evidence and a later reader must not have to guess which they hold.

And a row of the table says which role made it. That is one column and it is the smallest of the three, but it is the one that decides whether `runs.py` keeps meaning what `AGENTS.md` says it means once more than one role writes records.
