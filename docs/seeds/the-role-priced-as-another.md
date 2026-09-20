---
created: 2026-09-20
type: seed
status: building
summary: A role served elsewhere is priced with DeepSeek's table, so the reviewer on GLM is bounded five times too tightly and reads a fifth of what it was given.
value: 5
effort: S
version: v0.19
---

## Evidence

2026-09-20, run 20260920T103528Z, the first time any role ran on a model that is not the builder's. It answered in eighteen seconds and it was priced wrong.

`numbers.json` for that run reads `model=glm-5.3-flash` and `cost_source=table`. The table is `PRICE` in `builder.py`, which is DeepSeek's published peak rate for `deepseek-flash` and a statement about nothing else. Measured on that run's own tokens -- 2,427 input of which 1,088 were cache reads, 547 output:

| priced by | cost |
|---|---|
| the factory's table | $0.001065 |
| `genai_prices`, `zhipuai/GLM-5.3-Flash` | $0.000197 |

**The table overstates it by 5.41x.**

Why the library did not price it is the interesting half. `genai_prices` *can*: asked for `glm-5.3-flash` it answers `zhipuai/GLM-5.3-Flash` without hesitation. But `build_agent` reaches a role served elsewhere by giving `DeepSeekProvider` a `base_url`, so what the library has to look up is DeepSeek's provider with a Zhipu model name, which matches nothing; `usage.cost` comes back `None` and the factory's fallback answers instead. The fix in [[the-role-served-somewhere-else]] made the role reachable and left it mispriced, which that seed's Idea said in as many words and its Goal put out of scope.

**It is not a reporting error, it is a behavioural one.** v0.17 made what a run has spent the thing that bounds it. A pass is landed at `SOFT_SPEND`, and a pass whose spend is computed five times too high is landed after a fifth of the work it was given. Measured: a pass landed at $0.125 by the table has really spent about $0.0231. The reviewer on GLM reads a fifth of what it is budgeted for, and nothing in the record says so -- the number looks like $0.125 either way.

[[the-catch-rate-that-decides-the-role]] is what v0.19 exists for, and one of the questions it settles is whether the stronger model is the better reviewer. Asked today, it would compare a DeepSeek reviewer running to its full budget against a GLM reviewer cut off after a fifth of one, and it would answer confidently and wrongly. **That is why this comes first.**

### What the first build reached, 2026-09-20

Run 20260920T103528Z's mispricing is fixed and measured: commit 5c5d4ed, run 20260920T103952Z, green
at $0.1199 of a $0.125 ceiling. `price(usage, model)` takes the model with no default, the library
answers for `glm-5.3-flash` -- $0.000197 where the table said $0.001065 -- and a record made on it
now carries the library's number and says so.

The other two clauses it could not reach, and its report says why in as many words: the suite's own
fixtures configured roles on `a-model-of-its-own` and `a-reviewers-model`, names neither source can
price, and required those runs to proceed. The file asked for a refusal and forbade it at once, so
no code could satisfy both. **That was the attended agent's error, not the builder's** -- the third
time its `unsure` has been right about a blocker. The fixtures have been amended to a real model
that is not ours, which is what those tests were always about: that the model a run uses is the
role's and not the program's.

What the build did instead was add a second way to price a run, which answers with the table for any
model the library cannot price, and both programs call that one rather than `price`. So the defect
this seed exists to remove is still live on the path that matters, and a record made that way would
carry the table's arithmetic under the library's name.

## Goal

A run is priced by what it ran on, or it does not run.

**The library prices what it can, asked at the address the role is served at.** What `usage.cost` needs is a provider and a model it can look up together, and the model name is already right. Today `glm-5.3-flash` is asked of DeepSeek's provider and matches nothing.

The address is half the question and not a detail: **the same model name is served by more than one vendor at different rates.** Measured 2026-09-20 on the tokens of run 20260920T103528Z, `glm-5.3-flash` is $0.000196624 at `open.bigmodel.cn` and $0.000253495 at `api.z.ai`, and the bare name resolves to the first -- which is not the address this host's configuration names. Asked by name alone the library scans providers and answers with whichever it finds first, so a role is bounded by a rate that is not the one it is billed at. `base_url` is what the role is reached at and it is what the role is priced at; the name alone is the answer only when there is no address or the library does not know the one there is.

When the library answers, `cost_source` says `genai-prices` and that answer is the run's cost. `cost_source` names the source that answered and never the name that was configured.

**The table answers for the model it was written for, and for nothing else.** `PRICE` is DeepSeek's peak rate for `deepseek-flash`. It stays, it is still the source for that model, and it stops being the fallback for every other -- a wrong number is worse than no number when a wrong number is what bounds the run.

**A run the factory cannot price does not start.** Refused before a model is called and before a record is made, exit 2, naming the role and the model it could not price. That is the honest default and the reason is the sentence above: the spend ceilings are the only thing standing between a run and a runaway, and a ceiling derived from another model's rate is not a ceiling. A role whose price nobody knows is a role that cannot be bounded, and the factory does not run unbounded.

Both programs, because both reach their role the same way and both are bounded the same way.

What must not change: `deepseek-flash` keeps costing exactly what it costs today, by the same table, with `cost_source` still reading `table`, so every record ever written stays comparable with every record written after this.

**One function prices tokens, and it prices the whole run.** That is what `AGENTS.md` already
claims of this code, and the reason is the same reason as everything above: the number the tools
land a run on and the number its record carries are the same arithmetic, so they cannot drift. A
second way to price, with a laxer answer than the first, is a way for them to drift again. With the
refusal above in place nothing reaches a record that the one function cannot price, so there is
nothing for a second one to do.

The library's own running total is such a second way, and a quiet one. `RunUsage` adds a response's
cost only when the library gave one for that response and adds its tokens always, so a run in which
one answer could not be priced carries a total that is a sum of the others -- not `None`, so nothing
falls back, and not the run's price either. Measured 2026-09-20: a priced response of $0.001
followed by one of a million input and a hundred thousand output tokens that the library could not
price records $0.001, bounding the run about seventy times too loosely. A sum of some of a run's
responses is not the one function's answer, and what bounds the run and what its record carries are
that function's price for every token the run used.
