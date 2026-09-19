---
created: 2026-09-19
type: seed
status: spec
summary: Seven capped builds left a tree the builder's own check passed, and all seven were discarded for want of a report: 90 cents, seventeen per cent of everything this factory has ever spent on builds.
value: 5
effort: S
version: v0.17
---

## Evidence

2026-09-19, from research the owner commissioned into how a run should be bounded, and verified in the store by the attended agent before it was written here.

Of 98 build runs, 13 were capped. **Seven of those 13 left a tree whose check was green**, and every one was thrown away. They cost $0.896 -- **17.1% of the $5.23 this factory has ever spent on builds** -- and each carried a complete change:

| stamp | requests | edits | files | diff | cost |
|---|---|---|---|---|---|
| 20260916T154210Z | 60 | 19 | 1 | +107/-111 | $0.1146 |
| 20260917T220443Z | 60 | 12 | 3 | +175/-23 | $0.1075 |
| 20260918T074122Z | 60 | 8 | 2 | +39/-11 | $0.0844 |
| 20260918T224905Z | 59 | 13 | 1 | +48/-27 | $0.1554 |
| 20260918T233211Z | 48 | 7 | 1 | +24/-29 | $0.1235 |
| 20260918T234138Z | 40 | 7 | 1 | +23/-28 | $0.1613 |
| 20260919T000504Z | 59 | 6 | 1 | +21/-16 | $0.1494 |

The `check` those records carry is not the model's claim. `main` calls `check_final()` after `run()` returns, whatever ended it, and the field is the last check run -- so for a run that wrote after its own last check, it is the builder's independent verdict on the tree the run left, and for one that wrote nothing since, it is a verdict on that same tree. These are not seven runs that said they were done. They are seven runs whose tree **passed the suite under the builder's own check**.

[[caps-for-the-checkout-as-it-is]] states the opposite and is wrong: "A capped run reported nothing, so its work is not taken and `build.py` refuses it; the rule is sound and the cap is what is wrong." The rule is not sound. The factory already refuses a report claiming green when the check is red, which is to say the check already outranks the report as evidence. A green check with no report is therefore *more* evidence than a red check with a confident one, and only the latter is refused. What the report adds is the `did` and `unsure` lists, which are narration for whoever reads the record -- useful, and not the acceptance criterion.

The precedent is published. SWE-agent's harness, on exceeding its cost limit, calls `handle_error_with_autosubmission()`: it stages the working tree, extracts the diff and submits it anyway, recording the trajectory as `exit_cost` (https://github.com/SWE-agent/SWE-agent, `sweagent/agent/agents.py`). They salvage an unvalidated patch. The factory holds something they do not -- a check that already ran on the tree being salvaged.

The same paper (https://arxiv.org/html/2405.15793v3) reports that "93.0% of resolved instances are submitted before exhausting their cost budget, compared to 69.0% of instances overall" and concludes that "increasing the maximum budget or token limit are unlikely to substantially increase performance". Their successes finish at a median $1.21 and 12 steps against failures at a mean $2.52 and 21 steps. The same shape holds here: answered builds run a median of 20 requests at $0.032, capped builds a median of 60 at $0.125, and the most expensive build that ever answered, $0.1239, sits just below the median capped one. That is the argument that this seed, and not a larger budget, is where the money is.

## Goal

A build is taken when the tree it left passes the check, whatever ended the run.

`build.py` stops treating a cap as a reason to refuse. What it asks of a run is what it already asks: that the check on the final tree is green, and that something changed. A run that was capped and left a green tree with a diff is pushed as any other build is, one commit, never forced, with its trailer as it is now.

What still refuses, and must: a red check; a check that never ran; a green check that changed nothing; a branch that moved while the build was in flight; and **a record the store would not take**. That last one needs care, because the ordering it relied on is gone. Today a capped run is refused before the exit code is read, so `code != 0` can be taken to mean the store refused the record; once a cap is no longer a refusal, a capped run reaches that line with the same non-zero code as a leaked key. The two must be told apart by something other than the exit code, and the safe direction is unambiguous: a record whose commit the store refused may hold a key, so a build must not be pushed on any reading that cannot rule it out.

The commit says what it came from. A build taken from a run that never reported is not the same artefact as one taken from a run that did, and a reader of the branch should not have to hold the store to know which they have. Where that goes is the spec's, with one constraint: `gate.py` reads `Built-By` as a trailer and refuses a release whose value does not end `run <stamp>` in the builder's shape, so whatever is added must leave that reading intact.

The record already carries everything needed to decide: `stopped`, and `check`, which `check_final` writes from the builder's own run of the suite on the tree the model left, whatever ended the run.
