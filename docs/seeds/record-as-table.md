---
created: 2026-09-16
type: seed
status: building
summary: Twelve records and counting; one script that turns every numbers.json into a row is the outcomes panel with no new state anywhere.
value: 4
effort: S
version: v0.5
---

## Evidence

Reading a run today means opening `numbers.json` by hand; comparing two means opening both. The evals need every run of a case side by side, and no orientation page can name the last runs without narrating them. Twelve records on 2026-09-16, in three shapes: the observer's, the builder's before `world_head`, and the builder's with it.

## Goal

Add `runs.py` at the repository root, run as `uv run runs.py`, with `main(argv, runs=None)` shaped like the others: `argv[0]` is the program name, `runs` the records directory, by default `runs/` beside `runs.py`. It prints the records as one table, tab-separated, a header line then one row per record in the order of their stamps, and exits 0; any argument is a usage error on stderr, exit 2. The columns, in this order: stamp, head, stopped, check, requests, tool_calls, lists, reads, writes, edits, checks, input_tokens, cache_read_tokens, output_tokens, reasoning_tokens, cost_usd, seconds, files_changed, insertions, deletions, goal. Each value comes from the record's `numbers.json` as it is there; `goal` is the first line of `goal.txt` with tabs as spaces; a key the record does not have is an empty cell; `head` reads `head` and, in records written before v0.5, `world_head`; a record without `numbers.json` is a row with its stamp and goal only. Nothing is written. The tests in `test_runs.py` whose docstring names this seed define the behaviour.
