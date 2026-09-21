---
created: 2026-09-20
type: seed
status: open
summary: A seed's effort is a guess, its definition is circular, and it does not predict; the records hold what each seed actually cost and nothing writes it back.
value: 3
effort: S
reporter: research
kind: measurement
version:
---

## Evidence

2026-09-20, measured in the store by the attended agent from research the owner commissioned into whether a task's cost can be predicted before it is attempted.

The `effort` field is S, M or L, and `docs/templates/seed.md` defines S as "one goal within the builder's caps". That is circular: the caps are what the field is meant to help avoid. It is also uninformative. Across the 16 seeds the factory has built, the rank correlation between `effort` and the requests a seed's builds actually spent is +0.196, nowhere near significance, and **the two most expensive seeds are both labelled S**.

What does separate them is the mean, and it separates them cleanly. Of the 16 seeds, the nine whose builds averaged under 35 requests produced **zero** capped runs between them; the seven that averaged 35 or more produced **twelve**. Relative spread is roughly constant whatever the size of the task -- across the eleven evaluation cases the correlation between a case's mean cost and its spread is -0.064, flat -- so what changes the odds of a cap is not how variable a seed is but how expensive it is on average, because the cap is an absolute number and the spread is a ratio.

The wider research says an estimate made before the work is not worth building. The published ceiling for predicting a coding task's difficulty from its description is a rank correlation near 0.4 in-distribution and near 0.2 out of it (https://arxiv.org/abs/2608.05797), and thirty years of software effort estimation converged on the same number without beating a median predictor (https://arxiv.org/pdf/2101.05426). What has worked, in the one review that found models beating humans at all, is calibration to local historical data -- which is the only asset the factory holds and does not use.

The precedent for the retrospective form is Devin, which buckets a session XS to XL on its measured usage and flags L or XL as "the task scope was too broad for a single session". The number is computed after the run, not before it.

## Idea

`effort` keeps its prospective use for ranking a seed nobody has built, and gains a measured verdict for one that has been: the requests a seed's builds spent, read from the records, written back to the seed, with the threshold above which a seed should have been split named in the spec rather than guessed. A seed then carries both, and which of the two it is carrying is legible -- an estimate before there is evidence, a measurement after.

What the field is for changes with it. It stops being a prediction and becomes a fact that argues for splitting the next seed of its shape, which is reference-class forecasting on the factory's own history rather than estimation. `docs/backlog.base` reads the field to rank, so what an unmeasured seed ranks as is the spec's, and the template's circular definition goes.
