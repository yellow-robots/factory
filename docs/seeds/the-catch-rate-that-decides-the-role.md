---
created: 2026-09-20
type: seed
status: open
summary: The reviewer is built and nobody knows whether it catches anything; the number that decides whether it is a gate or theatre is the one thing it has never been measured against.
value: 5
effort: M
version:
---

## Evidence

2026-09-20. [[reviewer-role]] is built: a read-only lens, five independent passes per dimension, four dimensions, agreement counted inside a dimension, a note rendered in the record and the record committed to the store key-scanned. What it has never had is a number.

The seed that built it said so from the start and the wording has not softened: *a reviewer that catches nine of ten is a gate; one that catches four is theatre, and no amount of good prose in its report changes that.* So this is not a nice-to-have measurement, it is the condition the role was specified under, and until it exists the reviewer is a program nobody should route a decision through.

The instrument is already built and has been since v0.12. `cases/` holds twelve changes with seeded failures and held-out tests that know the right answer: `ambiguous_goal`, `anchor_not_unique`, `docstring_left_behind`, `environmental_red`, `impossible`, `new_file`, `rename_many`, `signature_not_the_raise`, `symptom_not_root`, `tempt_the_test`, `two_files`, `weaken_a_wall`. Several were filed *because* a reviewer or an attended agent caught something a suite could not, which is what makes them the right corpus: the answers were found the way the reviewer is meant to find them.

**What it costs, measured rather than guessed.** Run 20260920T095556Z, the first review that completed, cost $0.5773 over five passes in 1221 seconds: **$0.1155 and 244 seconds a pass**. The passes run to the soft ceiling and are landed there, so a review's cost is not emergent, it is `dimensions x passes x SOFT_SPEND` and it is chosen. From that:

| what | passes | cost | wall clock |
|---|---|---|---|
| one review, one dimension | 5 | $0.58 | 20 min |
| one review, four dimensions | 20 | $2.31 | 81 min |
| twelve cases, one review each, one dimension | 60 | $27.71 | ~16 h |
| twelve cases, three runs, four dimensions | 720 | $83.13 | days |

The owner's direction of 2026-09-20 is the first line of that table and a little more: build the harness, prove it end to end over two or three cases within five to ten dollars, and bring the full run back as a decision rather than spending it. The number is worth having and it is not worth having by surprise.

**What else the same instrument settles**, which is why it is worth building rather than eyeballing: whether a dimension phrased as a goal beats one phrased as a question; whether more passes beat fewer, and where the marginal pass stops paying for itself; whether the stronger model is the better reviewer, which this host can now ask because the reviewer role reaches `glm-5.3-flash` and the builder's is `deepseek-flash`; and whether reading the builder's record anchors a pass or informs it. Every one of those is a pair of runs over the same cases, and none of them can be argued.

## Idea

The harness runs the reviewer over the cases and counts what it caught.

A case is a change with a seeded defect and a held-out test that knows it. The reviewer is given that change as any review is given one, and what it says is scored against what the case knows: a case is caught when a reported finding names the thing the case seeded. What "names the thing" means is the hard part and it should start crude and visible -- the path, and the line or the symbol the case's held-out test asserts on -- so that the first number is honest about being crude rather than impressive and unreproducible.

The record is the same record. A catch-rate run is a review with a goal that says which case it is, the way an evaluation build's goal begins `case: <name>`, so `runs.py` shows them beside everything else and the cost of the measurement is in the table with the rest.

What it prints is a rate and its error, as `evals.py` already does for the builder: caught of seeded, per case and over the set, with the spread across runs when there is more than one. A single number with no error is the thing that makes a four look like a nine.

**What it must not do is be trusted before it is understood.** The first rate this produces is one model, one phrasing, one depth, on twelve cases the factory wrote for itself, several of them from failures this very reviewer's ancestors found. That is a measurement of a corpus as much as of a role, and the seed it settles is whether the reviewer is worth routing a decision through -- not whether it is good.
