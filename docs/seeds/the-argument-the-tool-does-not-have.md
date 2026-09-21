---
created: 2026-09-21
type: seed
status: open
summary: A tool call whose arguments have the wrong shape is answered by the library, not the tools, and a second one ends the run with no report and no diff; twice the model has invented `limit` for `read`, been told, and done it again, and both runs died at about three cents.
value: 3
effort: S
reporter: attended agent
kind: quality
version:
---

## Evidence

2026-09-21, run 20260921T093954Z, the second build of [[installation-and-surfaces]]: `stopped: error`, 22 requests, 30 tool calls, no write, no edit, one check, $0.0282, 118 seconds, and the detail `Tool 'read' exceeded max retries count of 1`. The model called `read` with `{"path": "build.py", "start": 18, "limit": 30}`. `read` takes `path` and `start`; the library answered with a retry prompt, `extra_forbidden: Extra inputs are not permitted` at `limit`, and the model's next call carried `limit` again. `builder.py:810` gives tools one retry, so the second refusal is the run's end: no report, no diff, the branch left alone and a note on the head.

2026-09-17, run 20260917T215410Z, building [[records-outside-the-project]]: the same death, the same tool, the same invented argument, `{"path": "gate.py", "start": 296, "limit": 60}` and then `"limit": 60` again after the same correction. 32 requests, $0.0280, 138 seconds. Two of the store's 221 records end this way, both on `read`, both on `limit`.

The asymmetry is the harness's. Every failure a tool can name comes back to the model as an `error: ...` string, moves no counter but `calls`, and the run continues under the spend cap: a path outside the checkout, an anchor that is not unique, a wall. An argument the tool does not have never reaches the tool; the library validates the call's shape, answers in its own words, and counts. Since v0.17 what bounds a run is what it has spent; the retry limit is a second bound that predates it, fixed at one, and it ends a run for a mistake the model corrects on other tools every day.

## Idea

Two ideas, one each way. **The shape error becomes what every other error already is**: an `error: ...` string the model reads and moves on from, bounded by the spend and by nothing else -- the library's retry limit raised past what a run can afford, or the validation caught and answered by the tools in their own words, so a run dies only of what a run may die of. **Or the tool grows the argument the model keeps reaching for**: `read(path, start, limit)` with `limit` bounded at `READ_LINES_CAP`, which is what [[the-read-that-costs-a-request]] wants for another reason, and the lapse stops being one. The first fixes the class; the second fixes the instance. Whichever is chosen, the record should say which tool and which argument, as `cap` says which cap.
