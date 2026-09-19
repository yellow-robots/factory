---
created: 2026-09-20
type: seed
status: building
summary: A final check that cannot run leaves the model's earlier verdict standing, and since this version that stale green is what decides whether a tree is pushed.
value: 5
effort: S
version: v0.17
---

## Evidence

2026-09-20, from the independent review of run 20260919T225154Z, reproduced by the attended agent in `builder.py` and in a throwaway repository before it was written here.

`check_final` runs the builder's own check on the tree the model left, and it swallows everything:

```python
try:
    self._check_once()
except Exception:  # a sandbox that cannot run must not lose the record
    pass
```

The comment is right about what it is protecting -- a record must survive a sandbox that cannot run -- and the record does survive. What does not survive is the meaning of `check`. When the final check cannot run, the field keeps whatever the model's own last check said, which is a verdict on an *earlier* tree, and nothing in the record says the final check was skipped: `checks` counts the model's checks, and there is no field for whether the last one covered the last tree.

Until this version that could not decide anything, because a capped run was refused whatever its check said and an answered run's report was read beside it. [[the-work-a-capped-run-leaves]] makes `check == "green"` the whole acceptance test, and capped runs are by construction the runs likeliest to have written since their own last check -- which is exactly the condition that makes `check_final` the only checker there is. So the same change that recovered seven builds' worth of work also made a swallowed exception sufficient to push a tree no check has seen.

The ways it happens are ordinary rather than exotic, and none of them is the model's doing: the docker daemon stops between the model's check and the builder's; the image is evicted and the rebuild fails, which `Sandbox.ensure_image` raises `RuntimeError` for; `docker build` passes `IMAGE_TIMEOUT` and `TimeoutExpired` comes out; the binary goes away and `docker run` raises `FileNotFoundError`. Each leaves a green from minutes earlier standing as the verdict on a tree that was written to afterwards.

The same hole has a second face, already guarded: a run whose check never ran at all leaves `check` at `none`, and `build.py` refusing that clause was pinned by nothing until the review found it.

## Goal

A record's `check` says what the check said about the tree the record is for, or it says nothing.

When the builder's own final check cannot run, the record must not carry a verdict that stands for a tree that check did not see. A green from the model's own earlier check is such a verdict once anything has been written since, and it is the one that matters, because `build.py` reads `check == "green"` as permission to push.

What must not change is what the swallow was written for. A sandbox that cannot run must still leave a record: the run is recorded, the wire is compressed, the store is offered the record as always, and the builder still exits the way it did. Losing the record to a failed final check would be a worse bug than the one being fixed.

Nothing about a check that *ran* changes. A red check stays red, a green check on the tree the model left stays green, and a run that wrote nothing since its own last check keeps that check's verdict, which is already a verdict on the final tree.

`build.py` needs no new rule: it already refuses every value of `check` that is not `green`, and the one guarding a check that never ran is now pinned by a test. What it needs is for `check` to stop lying.
