# Bench corpus

Records here are produced by `tools/bench_corpus.py extract` from a repo's merged `task/*` PRs (epic
yellow-robots/factory#161). Each `<owner>--<name>/<issue>-pr<pr>.json` is a `yr-bench-corpus/1` record:
the DoR prompt, the pre-solution ref, and the held-out test files (path + content) a sealed replay
patches back onto a candidate's tree. `exclusions.jsonl` names every merged PR that didn't qualify, and
why.

## Grading caveat

Bench grading is entirely mechanical, never an LLM judge: `tools/bench_replay.py`'s `grade()` /
`run_candidate()` seal the repo at the task's pre-solution ref, patch the held-out tests back onto the
candidate's tree from the corpus record's own stored contents — the *same PR's own* test additions,
authored by whichever AI landed the original solution, not independent ground truth — and run the target
repo's own `check_cmd`: exit 0 is `pass`, any other exit is `fail`, and an exit that means the check
harness itself couldn't even run (a missing/broken toolchain) is `ungraded-environmental`, never counted
as a graded fail.

A `pass` therefore proves only that a candidate's change makes those specific, already-anchored test
artifacts green under that repo's own check command — it is not independent proof of correctness, and it
is not graded against the original PR's approach. A candidate that solves the same task by a genuinely
correct but different path can still fail if the anchored tests happen to assert on the original
implementation's specific shape; conversely, a wrong solution that happens to satisfy the anchored
assertions would still grade `pass`. Anchored-test artifacts and a wrong-but-passing solution must stay
distinguishable at adjudication — this caveat exists so every report reader sees that distinction stated
plainly, not discovered later.
