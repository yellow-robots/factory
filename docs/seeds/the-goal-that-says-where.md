---
created: 2026-09-20
type: seed
status: rejected
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

Rejected by the owner on 2026-09-20: drop what brings no clear benefit. The effect it chases is measured on human-written bug reports, which are underspecified in a way this factory's goals are not -- ours arrive deliberate, revised, and with their tests already committed and runnable -- and the one clean measurement the factory owns points the other way, since `ambiguous_goal` is deliberately under-specified and passes nine of nine with one of the lowest spreads in the set. What was left was a template: a document to maintain, a form to fill in, and a body of evidence saying structural changes alone can reduce solve rates without removing any content. The evidence for the shape was never there, and the measurement alone did not earn a seed.

What survives is in the evidence above and is worth keeping for whoever asks again: specification quality is the largest effect in the literature, length is measured to hurt, and this factory's own history cannot settle it because the goal text, the caps, the prompt and the repository all moved together.
