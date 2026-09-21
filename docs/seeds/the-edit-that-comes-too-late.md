---
created: 2026-09-20
type: seed
status: open
summary: A run that has not edited anything by its twentieth tool call caps four times as often as one that has, and the factory already records the fact it would need to say so.
value: 3
effort: S
reporter: research
kind: measurement
version:
---

## Evidence

2026-09-20, measured across every record holding messages by the attended agent, from research the owner commissioned into bounding a run.

Of 95 build runs, 91 edited something. The rank correlation between **when** the first edit happened and how many tool calls the run took in total is **+0.805**: a run that starts changing things early finishes early, and one that is still reading is still reading.

Taken as a rule at the twentieth tool call, over the 74 runs that got that far:

| at call 20 | runs | capped | median calls still to come |
|---|---|---|---|
| had edited | 34 | 2 (6%) | 4 |
| had not edited | 40 | **11 (28%)** | 36 |

The rule flags 40 runs and catches **11 of the 13 capped builds in the whole store**, at 28% precision against a base rate of 14% -- twice the base rate, and a recall of 0.85. That is not good enough to stop a run on. It is good enough to say something about one, and it costs nothing: the tool calls are already in `messages.json`, and the builder already counts them as `self.calls`.

What it is measuring is not difficulty. It is the exploration that [[caps-for-the-checkout-as-it-is]] found the budget being spent on -- a run that cannot find where to start does not stop trying, and the twentieth call is early enough that something could still be done about it.

2026-09-22, at 6f9ed57, by the attended agent from the review of run 20260921T230705Z (docs/reviews/20260921T230705Z.md). For the Goal that builds this, since it is the next to touch `runs.py`: the module's docstring at `runs.py:14` to `16` says `capped` reads a record's numbers, and since v0.22 the function is handed the numbers already read and reads the messages alone; given `None` it does not open them. A sentence to correct, no behaviour.

## Idea

The record says when the first edit came, beside the counts it already carries, so a version can read off its own table which of its runs went looking and never found. That is the whole of the cheap half and it needs no judgement.

What to do with the fact is the spec's and it is the part to be careful about. The signal is a warning and not a verdict: at 28% precision, stopping on it would kill three good runs for every bad one. Telling the model about it is a second question again, and the evidence there points away -- a model near what it believes is a limit has been measured wrapping up prematurely, which is why the run's budget is a threshold it meets rather than a counter it watches. Recording it costs nothing and settles nothing; acting on it should wait until there is more than thirteen capped runs to fit against.
