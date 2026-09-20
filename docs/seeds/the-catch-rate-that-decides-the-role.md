---
created: 2026-09-20
type: seed
status: spec
summary: The reviewer is built and nobody knows whether it catches anything; the number that decides whether it is a gate or theatre is the one thing it has never been measured against.
value: 5
effort: M
version: v0.19
---

## Evidence

2026-09-20. [[reviewer-role]] is built: a read-only lens, five independent passes per dimension, four dimensions, agreement counted inside a dimension, a note rendered in the record and the record committed to the store key-scanned. What it has never had is a number.

The seed that built it said so from the start and the wording has not softened: *a reviewer that catches nine of ten is a gate; one that catches four is theatre, and no amount of good prose in its report changes that.* So this is not a nice-to-have measurement, it is the condition the role was specified under, and until it exists the reviewer is a program nobody should route a decision through.

**What it costs, measured rather than guessed.** Run 20260920T095556Z, the first review that completed, cost $0.5773 over five passes in 1221 seconds: **$0.1155 and 244 seconds a pass**. The passes run to the soft ceiling and are landed there, so a review's cost is not emergent, it is `dimensions x passes x SOFT_SPEND` and it is chosen. From that:

| what | passes | cost | wall clock |
|---|---|---|---|
| one review, one dimension | 5 | $0.58 | 20 min |
| one review, four dimensions | 20 | $2.31 | 81 min |
| twelve cases, one review each, one dimension | 60 | $27.71 | ~16 h |
| twelve cases, three runs, four dimensions | 720 | $83.13 | days |

The owner's direction of 2026-09-20 is the first line of that table and a little more: build the harness, prove it end to end over two or three cases within five to ten dollars, and bring the full run back as a decision rather than spending it. The number is worth having and it is not worth having by surprise.

### What the corpus actually is, checked 2026-09-20

This seed was written expecting `cases/` to serve: *twelve changes with seeded failures and held-out tests that know the right answer*. **It does not, and the difference matters enough to change the design.**

- `cases/` holds twelve cases, and **three** have a `held_out/` -- `docstring_left_behind`, `signature_not_the_raise`, `symptom_not_root`. The other nine have a goal, a red test and a word in `pass.txt`, which is what the *builder* is scored on, not a defect a reviewer could find.
- Ninety-one case runs are recorded. Six carry a held-out check and **all six passed**. So there is no recorded change that went green and was wrong, which is precisely the shape a review case needs.

What does exist, and is better, is the factory's own history. `docs/reviews/` holds fifteen notes, **138 findings, 128 of them verified by the attended agent** against a real diff at a named commit. Every one is a defect a strong independent reviewer found in a change this factory made, and the gate already refuses a release that carries a verified finding nobody judged. That is a ground-truthed answer key, written down before this seed existed and for another reason entirely.

**Two things follow, and both are limits on what the first number means.**

The key must hold only what a read-only pass could reach. Of the six verified findings on run 20260920T000130Z, four are of the form *this can be changed and the whole suite stays green* -- mutation findings, established by running a suite. `reviewer.py` is never offered `check` and builds no container. Scoring it against those would buy a low number for a reason that has nothing to do with reviewing.

And the key is a floor, never a ceiling. It holds what somebody found, so a pass that finds something real and new scores nothing for it. A catch rate measured this way cannot be read as a fraction of the defects that were there, only as a fraction of the defects we know were there.

### The first run, 2026-09-20

Run 20260920T124559Z, case `reviewer-role`, on `deepseek-flash` for comparability with the only
other review this factory has numbers for. Twenty passes over four dimensions, **$2.5787 and 6,837
seconds**, agreement 0.36, sixteen findings reported.

**The instrument works end to end.** The right commit, a throwaway worktree, the review run
unchanged, the record in the store with its goal beginning `case: reviewer-role`, the scoring done
and a rate printed with its error. That was the thing being proved and it is proved.

**The first number it printed was wrong, in the flattering direction.** It said two of two on both
counts. One of those is a real catch: `reviewer.py:134`, the role's key sent to the provider the
role did not name, inside the answer's span and unmistakably the same defect. The other was a
**span collision**: the answer's span was `[186, 193]` and the reviewer reported a finding at 192
that is a different defect entirely -- `goal.split("\n", 1)[1]` chopping the seed's name off the
goal, which is [[the-goal-a-review-does-not-record]] and was in nobody's key. Nothing in the run
reported the seed-path defect the answer was written for. **The honest score is one of two.** The
span is now `[186, 191]`, which is the seed-reading block and not the statement after it.

The scoring code did exactly what it was told. The answer key was too loose, and a key written by
hand against line numbers will go on being too loose unless each span is checked against what else
lives in it. That is a cost of crude-and-visible and it is payable; what is not payable is a number
that reads two when it is one.

**The path-only count says nothing on a single-file case.** This commit created `reviewer.py`, so
the whole diff is that file, and every reported finding matches every answer on the path alone. The
second count earns its place only where a case spans several files, which is worth saying before
anyone reads a path rate of 1.000 as a result.

**The allowance does not bound what a run can spend.** The projection is
`dimensions x passes x SOFT_SPEND`, $2.50 here, and it is checked against `--spend`. But a pass may
run to `HARD_SPEND`, so the real ceiling is `dimensions x passes x HARD_SPEND`, **$5.00**, and this
run was allowed $3.00. It came in at $2.5787 -- $0.1289 a pass against the $0.1155 measured before,
and 342 seconds a pass against 244 -- so nothing was overspent. It could have been, and the Goal's
sentence is that a run costing more than it was allowed does not start.

**Wall clock is the thing to plan around, not cost.** One case at four dimensions is under three
dollars and just under two hours. The twelve-case set is not principally an $83 decision, it is a
several-day one, and a model served at a lower rate spends its ceiling on more tokens and therefore
more minutes: correcting GLM's price this morning made a GLM pass roughly 3.6 times longer for the
same dollar.

## Goal

The harness runs the reviewer over cases whose answers are already known, and counts what it caught.

**A case is a commit and what that commit is known to hold.** It names a commit of this repository, the seed that commit was built from, and one entry per known finding: a path, and the line or the span in the file *at that commit*. The findings come from `docs/reviews/`, they are ones the attended agent verified, and they are only ones a pass that reads and cannot run could have reached. A case says which review note each answer came from, so every number in the output can be walked back to the note that justifies it.

**A case is reviewed the way anything is reviewed.** A throwaway worktree at that commit, the reviewer run over it as `reviewer.py` is run over any delivered tree, nothing about the review special-cased because it is being measured. Its record lands in the store like any other, key-scanned like any other, with a goal beginning `case: <name>` as an evaluation build's does, so `runs.py` shows what the measurement cost beside everything else it shows.

**A catch is crude and visible, and it is counted twice.** A reported finding catches a known one when it names that path and its line falls within that span. The same set is counted again on the path alone. Two numbers, because the difference between them is how much of the rate is the reviewer knowing *where* rather than *what*, and one number would hide it. Crude on purpose: the first rate should be honest about being crude rather than impressive and unreproducible.

**What it prints is a rate and its error.** One row per case: how many of the known findings were caught on each count, how many passes ran, what it cost and how long it took. Then the set: the rate on each count with its standard error under a uniform prior, as `evals.py` already gives the builder's. A single number with no error is the thing that makes a four look like a nine.

**It says what it will cost before it spends anything.** A review's cost is chosen and not emergent -- `dimensions x passes x SOFT_SPEND` for each case -- so the harness can say what the whole run comes to before the first pass starts, and does. A run that would cost more than it was told it may spend does not start: refused before a model is called and before a record is made, naming what it would have cost and what it was allowed. The full set is a decision somebody takes on purpose, not one they discover afterwards.

**A measurement is paid for once.** A review's record holds every finding it reported, and scoring is arithmetic over those findings and the case's answers. So the harness scores the records it already has as well as making new ones: no worktree, no pass, no model, nothing spent, and no allowance asked for because there is nothing to allow. A record says which case it was in its own goal, so it needs no telling.

The reason is the first run. It cost $2.5787, and the number it printed was wrong because an answer's span was too wide; correcting the span is a two-character edit and seeing the corrected number should not cost another $2.5787. An answer key written by hand will be corrected repeatedly, and a harness that charges a review for every correction is one that will be corrected less often than it should be.

**A case nobody measured is not a case the reviewer missed, wherever the measuring failed.** A case with no record, a case whose review could not be started or did not finish, and a case that knows no findings are all cases with nothing to score. None of them is a review that found nothing. Each is shown as unmeasured and none is in the rate -- and when nothing at all could be measured there is no rate to print and no arithmetic to attempt, which is not an error but an answer.

**A case nobody measured is not a case the reviewer missed.** A case with no record has no findings to score, which is not the same as a review that found nothing: it is shown as unmeasured and it is left out of the rate. Scoring the two cases of 2026-09-20 with one of them never run read 0.250 where the measured half read 0.500, which is the failure this whole seed exists to prevent, arriving from the other direction -- a number that makes a five look like a two and a half.

**What it may spend bounds what it can spend.** A pass may run to `HARD_SPEND`, above the ceiling the projection is counted in, so the allowance is checked against what the run could cost and not against what it is expected to cost. Both numbers are said, because the difference between them is the difference between a plan and a promise.

Exit 1 when a review was capped or errored, because a capped review is not a measurement; 2 for a usage error.

**What it must not do is be trusted before it is understood.** The first rate is one model, one phrasing, one depth, on a handful of cases, scored against an answer key that is a floor. It settles whether the reviewer is worth routing a decision through. It does not settle whether reviewing works.
