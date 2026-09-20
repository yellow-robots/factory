---
created: 2026-09-20
type: seed
status: open
summary: A review that did everything right exited 139, a segmentation fault at interpreter shutdown, after its record was safely committed.
value: 4
effort: S
version:
---

## Evidence

2026-09-20, run 20260920T095556Z, the second time `reviewer.py` was ever run against a real model and the first time it completed.

Everything about the run succeeded. All five passes ran, `stopped: answer`, `passes_ran: 5`, three findings reported of five seen at an agreement of 0.6, `review.json` and `review.md` written, the record committed to the store as `e546bf1`. Twenty minutes and $0.5773 of work, and none of it lost.

**The process then exited 139**, which is 128 + 11: a segmentation fault, raised after the record was on disk and after the numbers line was printed. The run's own code had finished; what crashed was the interpreter on its way out.

That the work survives is luck rather than design. A caller reads an exit code, and this one says the run died. `build.py` reads the builder's exit code to decide whether to push, and goal D's harness will read the reviewer's to decide whether a case counted -- a review that did its job and reports 139 is a review that harness will score as a failure. Exit codes are the only thing a program says to the thing that started it, and a program whose last word is wrong is worse than one that fails loudly.

The likely holder is not the reviewer's own code, which had returned. This run made 173 requests over 15.7M input tokens, the largest the factory has ever made by an order of magnitude, and it holds an `httpx2.AsyncClient` built by `Wire` that nothing closes; the event loop `run_sync` builds per pass is built and discarded five times. Both are native-backed and both are candidates. It is one observation, not a pattern: the first review, 20260920T091432Z, was killed by a ceiling and did not show it.

The same run is also evidence for [[the-tasks-the-suite-never-gives-back]], whose seed says `--pids-limit` counts threads and the suite accumulates them. An unclosed client and a discarded loop per pass are exactly the kind of thing that accumulates.

## Idea

The last thing a run says is true.

The measurement comes first and it is cheap: run the reviewer again at the same size and see whether 139 returns, then again with the wire's client closed and the loop's shutdown made explicit, and let the two answers say whether the fix is a fix. A single segmentation fault is a bug report, not a diagnosis, and guessing at a native crash from one sighting is how a morning disappears.

What must hold whatever the cause is that the exit code is the run's own verdict and not the interpreter's parting mood. If a crash on the way out cannot be prevented, it must at least not be mistaken for the run: the record is committed, the numbers are written, and what the program means to say is already known by then.

`Wire` is shared with the builder, so whatever is found here is the builder's too. No build has shown it, and the reason is probably size -- the largest build the factory has ever made moved 4.2M input tokens against this run's 15.7M -- which is a reason to expect it in builds later rather than a reason to think it is the reviewer's alone.
