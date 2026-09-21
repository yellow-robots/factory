---
created: 2026-09-20
type: seed
status: open
summary: Every test module of the factory passes alone inside the check's container and the suite together does not, because tasks accumulate across it until git cannot fork.
value: 4
effort: M
reporter: attended agent
kind: integrity
version:
---

## Evidence

2026-09-20, measured by the attended agent in the check's own container after it stopped two builds of v0.17 and cost $0.185.

The check runs the suite in a container with `--pids-limit 256`. On 2026-09-20 the suite crossed it, and every build after that point was refused: `build.py` will not take a build whose check is red, and the check was red for a reason that had nothing to do with what the builder wrote. Both refused runs diagnosed it correctly and said so in `unsure`; the second one is worth quoting, because it is the factory reporting a wall of its own: "the same 33 failures + 2 errors appear before the change, so it is a sandbox process limit, not the change."

The failures are all one shape. `evals.py` calls `git worktree add`, and git answers `error: cannot fork() for reset: Resource temporarily unavailable`.

It is accumulation and not a peak, which four runs of the same image over the same tree settle:

| what ran | `--pids-limit` | failed forks | result |
|---|---|---|---|
| `test_evals` alone | 256 | 0 | 42 tests, OK |
| `test_builder` alone | 256 | 0 | 103 tests, OK |
| `test_build` alone | 256 | 0 | 22 tests, 1 failure, the seed's own red test |
| the whole suite | 256 | 75 | 256 tests, 33 failures and 2 errors |
| the whole suite | 1024 | 0 | 256 tests, 1 failure, the same red test |
| the whole suite | unlimited | 0 | 256 tests, 1 failure, the same red test |

No module needs 256 tasks. The suite does, and only because it has run the earlier ones first. `--pids-limit` counts threads as well as processes, so what accumulates need not be a process: an event loop or a thread pool that is never shut down counts the same as a zombie, and the suite runs `agent.run_sync` more than a hundred times.

The crossing is datable to four tests. The build at 0b4669d ran 251 tests and its check was green; the guards committed at be91a96 took it to 255, and the next two builds were refused. Two of those four run a whole `build.py` build each, and one of them runs two.

**The shape of the wall is the finding, not the number.** The factory could not build the fix for this. Any candidate build is judged by a check that fails for this reason, and the check is run by the *instance's* `builder.py`, pinned at a released tag, so a fix in the checkout does not reach the thing doing the judging until a version ships with it. That is a deadlock the attended agent had to break by hand, which is recorded in v0.17's note as the one change of that version the factory did not write.

## Idea

Find what the suite holds and give it back.

The measurement comes first and it is cheap: run the suite in the container and watch `/sys/fs/cgroup/pids.current`, or sample the task count between modules, and the curve says whether it climbs monotonically -- a leak -- or steps up and stays, which is a pool that is never closed. Both are fixable and they are fixed differently, so guessing between them is the one thing not to do.

The likely holders are known and few. `agent.run_sync` builds and tears down an event loop each time it is called, and anyio's worker threads are not always reaped with it. `Wire` holds an `httpx2.AsyncClient` whose connection pool has its own tasks. `evals.py` and `test_build.py` shell out to git many times per test. Each is checkable against the curve rather than by argument.

What the fix must not do is raise the ceiling again. `PIDS_LIMIT` is headroom bought to unblock the factory, not an answer: a suite that leaks tasks will cross any number eventually, and the next crossing will land exactly where this one did, in the middle of a version, wearing the costume of somebody else's bug. A test that pins what the suite holds at once is the thing that stops it happening a third time.
