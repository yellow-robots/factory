---
type: seed
status: open
summary:
value:
effort:
goal:
acceptance:
version:
crossed_to:
created: {{date}}
---
%%
One template, staged by status. Fill what the next stage requires; the gate refuses a transition
with an empty field.

- open: summary (one line, what and why), value, effort.
- spec: + goal (one imperative sentence the builder receives), acceptance (the tests by name, or
  the number that shows it done), version (the tag it is assigned to).
- building: the version's worktree exists and the red tests are committed in it.
- done: + crossed_to, a link to the version note. rejected or superseded: one line of why.

Value, 1 to 5: 5 unblocks a stage of autonomy or closes a hole in the walls; 4 gives a measure we
do not have; 3 improves the quality of an existing step; 2 saves cost or time; 1 convenience.
Effort: S one goal, one test file, within the builder's caps; M a version of two to four goals;
L more than one version, or research first.
Rank = value minus (S 0, M 0.5, L 1), computed by seeds.base, re-ranked at every release.

Body: evidence first (which run, which number, which failure), then the idea. Facts, dated.
%%

## Evidence

## Idea
