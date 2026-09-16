## Changed
- gate.py

## Did
- Added `_wire_problems(root)` to gate.py: it globs `runs/*/wire.jsonl` and reports each path git tracks via `git ls-files`, naming the record and the expected `wire.jsonl.gz` form; untracked wires are ignored.
- Called `problems.extend(_wire_problems(root))` at the end of `problems_check` in gate.py so the check reports committed uncompressed wires.

## Check
- green

## Failing
- (none)

## Unsure
- No `runs/` directory exists in the world, so the goal's after-build step (compressing already-committed wires and naming the step in AGENTS.md) had nothing to act on and no test asserts it.
