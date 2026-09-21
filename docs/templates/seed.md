---
created: "{{date}}"
type: seed
status: open
summary:
value:
effort:
reporter:
kind:
version:
---
%%
One template, staged by status. Each status has facts the gate checks; a status whose facts are missing is refused.
open: created (the date the seed was born, YYYY-MM-DD, filled by the template), summary (one line, what and why), value, effort, reporter, kind; the body has Evidence and an Idea.
spec: version, the tag the seed is assigned to and the name of its note in versions/; the Idea becomes a Goal, the text the builder is given.
building: at least one test names the seed, `seed: <file name>` in the docstring of a test method or class, committed red in the version's worktree.
done: the build is merged and the tests naming the seed are green. rejected: one line of why in the body.
Value, 1 to 5: 5 unblocks a stage of autonomy or closes a hole in the walls; 4 gives a measure we do not have; 3 improves an existing step; 2 saves cost or time; 1 convenience. Value is the owner's call on what nothing counts; where the store or git can count what the seed moves, the Evidence names that quantity in words a reader can re-derive.
Effort: S one goal within the builder's caps and one test file; M two to four goals; L more than one version, or research first.
Reporter, who saw it and through what: owner; attended agent, from its own reading of a run or the code; review, a briefed subagent's finding the attended agent reproduced; reviewer, the factory's own reviewer.py, with the run; research, a study the owner commissioned.
Kind, what the seed moves, one word: cost, quality, measurement, integrity, autonomy, scalability. The value says how much; this says of what.
Rank = value minus (S 0, M 0.5, L 1), computed by backlog.base; equal ranks are ordered by created, oldest first.
Evidence: which run, which number, which failure. Each paragraph opens with its date and the commit or tag it was read at, then who read it and from what -- `2026-09-19, at v0.15, by the attended agent from run 20260918T224905Z`; its line references are to that commit. A count names what it counts, `11 of the 12 cases`, so a later reader sees it move.
%%

## Evidence

## Idea
