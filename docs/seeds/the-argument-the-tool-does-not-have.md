---
created: 2026-09-21
type: seed
status: building
summary: A tool call whose arguments have the wrong shape is answered by the library, not the tools, and a second one ends the run with no report and no diff; twice the model has invented `limit` for `read`, been told, and done it again, and both runs died at about three cents.
value: 3
effort: S
reporter: attended agent
kind: quality
version: v0.22
---

## Evidence

2026-09-21, run 20260921T093954Z, the second build of [[installation-and-surfaces]]: `stopped: error`, 22 requests, 30 tool calls, no write, no edit, one check, $0.0282, 118 seconds, and the detail `Tool 'read' exceeded max retries count of 1`. The model called `read` with `{"path": "build.py", "start": 18, "limit": 30}`. `read` takes `path` and `start`; the library answered with a retry prompt, `extra_forbidden: Extra inputs are not permitted` at `limit`, and the model's next call carried `limit` again. `builder.py:810` gives tools one retry, so the second refusal is the run's end: no report, no diff, the branch left alone and a note on the head.

2026-09-17, run 20260917T215410Z, building [[records-outside-the-project]]: the same death, the same tool, the same invented argument, `{"path": "gate.py", "start": 296, "limit": 60}` and then `"limit": 60` again after the same correction. 32 requests, $0.0280, 138 seconds. Two of the store's 221 records end this way, both on `read`, both on `limit`.

The asymmetry is the harness's. Every failure a tool can name comes back to the model as an `error: ...` string, moves no counter but `calls`, and the run continues under the spend cap: a path outside the checkout, an anchor that is not unique, a wall. An argument the tool does not have never reaches the tool; the library validates the call's shape, answers in its own words, and counts. Since v0.17 what bounds a run is what it has spent; the retry limit is a second bound that predates it, fixed at one, and it ends a run for a mistake the model corrects on other tools every day.

## Idea

Two ideas, one each way. **The shape error becomes what every other error already is**: an `error: ...` string the model reads and moves on from, bounded by the spend and by nothing else -- the library's retry limit raised past what a run can afford, or the validation caught and answered by the tools in their own words, so a run dies only of what a run may die of. **Or the tool grows the argument the model keeps reaching for**: `read(path, start, limit)` with `limit` bounded at `READ_LINES_CAP`, which is what [[the-read-that-costs-a-request]] wants for another reason, and the lapse stops being one. The first fixes the class; the second fixes the instance. Whichever is chosen, the record should say which tool and which argument, as `cap` says which cap.

## Goal

A read is as large as the model asks for, and a mistake in a call's shape costs a request and never the run.

**`read(path, start, limit)`.** `Tools.read` takes a third argument, `limit`, the most lines to return: a read answers from `start` with at most `limit` lines, at most `READ_LINES_CAP` lines and at most `READ_BYTES_CAP` bytes, whichever is met first, and a read cut short by any of the three ends with the truncation line naming where to continue, as it does now. `limit` omitted or above the line cap is the line cap; below one is one. `READ_LINES_CAP` becomes 1000 and `READ_BYTES_CAP` 64000. The docstring names the three arguments and both numbers, as `test_the_docstrings_state_the_caps` reads them. Nothing else about a read moves: numbered lines, one line at least however long, a line cut at the byte cap, and every error the tool answers today.

**A call of the wrong shape is answered, not fatal.** A tool called with an argument it does not have, or without one it needs, is answered by the library's validation with words the model reads and moves on from, as `error: ...` is for every other mistake; the run goes on under the spend, the calls and the requests, and ends of nothing else. Today `build_agent` gives tools one retry -- `retries={"tools": 1, "output": 2}` -- so the second wrong call ends the run with `stopped: error` and `Tool 'read' exceeded max retries count of 1`; two of the store's 221 builds died so, both on `read`, both on `limit`. The retries for tools go above what a run can afford, the output retries stay as they are.

**What the record says.** `numbers.json` gains `bytes_read`, the bytes every read returned over the run, beside `lines_read`; and `retries`, a mapping from a tool's name to how many times the library answered a call of that tool for its shape, counted from the run's messages -- each retry prompt part, by the tool it names -- `{"read": 2}`, and `{}` when it never did. `runs.py` and its table do not change. The reviewer reads through the same `Tools` and gains the larger read with it; its record does not change.

**README.** The sentence on the tools names `read(path, start, limit)` and the two numbers as they now are.

**Held by tests.** `test_builder.py`, naming this seed or [[the-read-that-costs-a-request]]: a read with `limit` returns that many lines and a truncation line naming the next; a `limit` above the cap reads the cap; a file longer than the cap truncates at the cap and continues from the line after; `bytes_read` is the bytes returned; the docstring names the caps. A scripted model that calls `read` twice with an argument it does not have, then reads correctly, then reports: `stopped: answer`, the report returned, `retries` `{"read": 2}`. `test_reviewer.py` as it is.

**What must not change.** The five other tools, the walls, the caps on writes, checks and spend, the search caps, and every field the record has now and its meaning.
