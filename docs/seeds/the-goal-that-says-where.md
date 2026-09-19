---
created: 2026-09-20
type: seed
status: open
summary: A goal that names where the work is costs a fraction of one that does not, and the factory has no shape for a goal and no measurement of whether the shape helps.
value: 4
effort: M
version:
---

## Evidence

2026-09-20, from research the owner commissioned into task sizing, whose clearest finding was not about sizing at all.

The largest single effect in the literature is specification quality. OpenAI's re-annotation of SWE-bench found **38.3% of samples flagged for underspecified problem statements**, and filtered out 68.3% of the benchmark on that and one other ground. What the evidence says helps is specific: naming where in the code the work is, stating the expected behaviour concretely, and giving executable tests. What it says hurts is length -- a study of what makes a good bug report for an agent finds longer reports associated with *lower* odds of resolution, and one of orienting context documents measured them at -0.5% on SWE-bench for +20% cost.

The factory's own history says the same thing and is easy to misread. The goal of `records-outside-the-project` grew from 211 words to 1611 across its builds while its cost fell from a capped 60 requests to 17. That is not "longer is better": within the six seeds whose goal text was revised between builds, the rank correlation between a goal's length and its cost averages -0.015, ranging from +0.60 to -0.50. What changed was precision, and the longer text was the more precise one.

Two things follow that the factory does not have. There is no stated shape for a `## Goal` -- the gate checks only that one exists and that the builder's own reader can read it -- so what makes one good is knowledge held by whoever writes it, which today is the attended agent and by hand. And there is no measurement: every claim above is from outside, or from a history where the goal text, the caps, the prompt and the repository all moved together, which [[caps-for-the-checkout-as-it-is]] and the sizing research both found confounds everything drawn from it.

The evaluation set already holds one half of the experiment. `ambiguous_goal` is a case whose goal is deliberately under-specified -- "The usage error tells a first-time user what they need" -- and it passes 9 of 9 with one of the lowest spreads in the set, which is itself a warning that the effect may be smaller than the literature suggests at this size of task.

## Idea

A goal has a stated shape, and the shape is the spec's: what changes, where it is -- named paths, since localization is the cue with the most evidence behind it -- what the behaviour must be afterwards, and what is out of scope. It is a shape and not a length, and the template says so, because the one thing measured to hurt is padding.

Whether the shape helps is measured rather than asserted, and the instrument is a pair. The same task under two goal texts, one to the shape and one not, run the way [[paired-set-runs]] runs two builders -- the cases, the harness and the hour shared, only the goal differing -- with `ambiguous_goal` and a precise counterpart of it as the first pair. What the spec must not do is assume the answer: the factory has been narrowing goals by hand all week and calling it a success, and this is the first chance to find out whether it was.
