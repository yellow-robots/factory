---
created: 2026-09-17
type: seed
status: done
summary: The tool calls the model issues in one response overlap in the library; two edits of one file raced, one was lost and both reported success, so a record can say a change happened that never did.
value: 5
effort: S
version: v0.12
---

## Evidence

2026-09-17, build 20260917T103739Z on the standard-error seed. Response 13 carried three `edit` calls; the first, on the module docstring of `evals.py`, returned `edited evals.py (429 -> 429 lines)`, and `check-1.log` failed the docstring test. The model read the file, found the old text still there, repeated the identical call in response 21, and it landed. The builder said it in its unsure list, an edit call reported success but did not change the file, and could not explain it. pydantic-ai 2.43.0 runs a response's tool calls overlapping unless a tool is registered `sequential=True`, a barrier that runs alone; `build_agent` registers the six without it. `edit` reads the file, replaces and writes with no lock, so two edits of one file in one response can both read the same text and the later write drops the earlier change; a `check` overlapping an `edit` tests a half-edited checkout, and a `read` overlapping a `write` reads a half-written file. The set's records show the model issuing several calls per response since v0.6; how many edits were lost before this one is not knowable from the records, since the return said edited.

## Idea

Every tool runs alone, one call at a time in the order the model gave them: `sequential=True` on the six in `build_agent`. A test with a slow edit, two of one file in one response, asserts the second starts after the first ends and both changes are in the file; a third in the same response, on the text the first wrote, finds it.

## Goal

Every tool of the builder runs alone: the six are registered in `build_agent` as sequential, so the calls of one response run one at a time in the order the model gave them, a call started only after the one before it returned, and a call sees what the calls before it wrote. Nothing else changes: the returns, the counters and the record are as they were. The test in `test_builder.py` whose docstring names this seed defines the behaviour.
