---
created: 2026-09-20
type: seed
status: open
summary: The reviewer reviews the diff thoroughly and never asks what the diff made load-bearing elsewhere, so a defect the change lets through in code it does not touch is invisible to it.
value: 4
effort: M
version:
---

## Evidence

2026-09-20, run 20260920T150230Z, the second catch-rate case, `the-work-a-capped-run-leaves`. Twenty passes, $2.5421, agreement 0.60, and **none of the one defect the case knows about**.

The case was built to ask exactly this. The commit changes `build.py` alone. The defect it lets through is four lines of `builder.py` -- `check_final` swallowing every exception, so a final check that could not run leaves `check` reading a verdict on an earlier tree -- and the change is what makes that matter, because it makes `check == "green"` the whole acceptance test for a capped run. Finding it means noticing that the change made a clause load-bearing and then going to read the thing now carrying the load. The reviewer has `list`, `read` and `search` over the whole checkout and may do precisely that.

**It is not that it found nothing.** Nine findings, four of them defects, and they are good ones: `build.py:281` three times over, `build.py:163` twice, and two saying the seed's own Goal still describes the behaviour the change removed, which is a real thing to notice and one a reader of the diff alone would miss. Every finding is inside `build.py` or in that spec. Not one names `builder.py`.

So the reviewer reads what changed, carefully, and stops there. What it is never asked to do is the second question: *what did this change make load-bearing, and is that thing sound?* Both goals in `DIMENSIONS` that could invite it are phrased about the change under review, and `_review_diff` puts the diff in the prompt while the checkout is only reachable by a tool call the pass has to decide to make.

This matters more than one missed case. Every defect [[the-check-that-could-not-run]] and [[the-work-a-capped-run-leaves]] record was of this shape -- a change that is correct in itself and makes something else wrong -- and that shape is most of what an independent reviewer is for. A suite catches what a diff breaks; a reader is needed for what a diff loads.

## Idea

A dimension that asks what the change made load-bearing.

The cheapest version is words: one more entry in `DIMENSIONS` phrased at the thing the change now depends on rather than at the change, and the harness already exists to say whether it pays. That is the measurement this seed wants -- the same case, the same passes, one dimension added, and the catch on `builder.py` either appears or it does not. It is one case and about $2.75 to ask, which is cheap for an answer about what the role is for.

What it must not become is a reviewer told to read the whole checkout, which is a budget spent on reading rather than on thinking and is the failure `reviewer-role` bounded the passes to avoid. The question is whether one goal-phrased sentence moves a pass from the diff to its consequences, not whether a bigger context does.

Worth doing before any decision is routed through the reviewer, and worth doing before the full case set is run, because a dimension added afterwards invalidates the number that was paid for.
