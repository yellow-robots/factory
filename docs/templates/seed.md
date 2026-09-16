---
type: seed
status: open
summary:
value:
effort:
version:
---
%%
One template, staged by status. Each status has facts the gate checks; a status whose facts are missing is refused.
open: summary (one line, what and why), value, effort; the body has Evidence and an Idea.
spec: version, the tag the seed is assigned to and the name of its note in versions/; the Idea becomes a Goal, the text the builder is given.
building: at least one test names the seed, `seed: <file name>` in the docstring of a test method or class, committed red in the version's worktree.
done: the build is merged and the tests naming the seed are green. rejected: one line of why in the body.
Value, 1 to 5: 5 unblocks a stage of autonomy or closes a hole in the walls; 4 gives a measure we do not have; 3 improves an existing step; 2 saves cost or time; 1 convenience.
Effort: S one goal within the builder's caps and one test file; M two to four goals; L more than one version, or research first.
Rank = value minus (S 0, M 0.5, L 1), computed by backlog.base.
Evidence: which run, which number, which failure. Facts, dated.
%%

## Evidence

## Idea
