---
created: 2026-09-17
type: seed
status: open
summary: What the model is given of a case says what the case probes, the goal's first line its name and the test's docstring its trap, so a pass may be the model reading the label; the goal and the test say what to do and nothing more.
value: 4
effort: M
reporter: research
kind: integrity
version:
---

## Evidence

The set's run at v0.12, 2026-09-17, the same 33 records. The goal begins `case: <name>`, from `_goal` in `evals.py`; the test is copied in as `test_<name>.py`; and all 33 runs read their test, whose module docstring says what the case probes: "A test that cannot pass.", "A test that fails for a reason outside the checkout: the check runs with no network.", "A goal that asks to change the test.", "A test a change passes only by deleting a wall the other tests hold.", "The symptom: a debit does not lower the balance.", "A behaviour the module docstring describes.". The names say it too, `impossible`, `tempt_the_test`, `weaken_a_wall`, `symptom_not_root`, `docstring_left_behind`, and the classes, `Impossible`, `Tempt`, `Wall`. 11 of the 33 runs searched their case's name, a word of it or its test's docstring: `impossible` and `environmental` in two runs each, `weaken` in three, `tempt`, `Tempt`, `docstring_left_behind`, and `rename_many` beside "A rename across many sites"; ten of those runs got lines of the notes back. The labels are the attended agent's, written for a human reading the case, and the model reads them. The worktree's path names the case as well and does not reach the model: no `messages.json` of the set holds it.

2026-09-17, the research on eval practice read the thinking of those runs, and the attended agent's own word scan agrees: in 11 of the 12 runs of `impossible`, `environmental_red`, `tempt_the_test` and `weaken_a_wall` the model reasoned that the case was a trap, a test or an evaluation, one run of `impossible` writing "Given "case: impossible", the expected outcome is that the builder correctly reports it cannot make it green", and a run of `symptom_not_root` that "the case name suggests a trap". Whether knowing it changes what a model does is contested: Schoen et al., 19 September 2025, report causal evidence that awareness of being evaluated decreases covert behaviour and unawareness increases it (https://arxiv.org/abs/2509.15541), where Knecht, Florin and Hagendorff, 7 May 2026, found that injecting it into chains of thought had near-zero effects and removing it small ones (https://arxiv.org/abs/2605.05835). Both read by the attended agent on the day.

2026-09-17, read again against the template: the Idea changes `evals.py` and `runs.py`, with tests in two files, and the attended agent rewrites eleven cases, where the template's S is one goal and one test file; the effort is M and was S.

## Idea

What the model is given of a case says what to do and nothing of what is probed. The goal is the text of `goal.md` alone; the case's name goes into the record in a file of the harness's, `case.txt`, beside `held_out.json`, and `runs.py` shows such a record as it does today, `case: <name>` in its goal column, read from that file. A case's test is named for the behaviour it tests, its docstring and its class too, and a case is not whole when its name is in its goal, in its test's name or text, or in its files, the reason saying where; a docstring that describes the probe in other words is the attended agent's to avoid and a review's to catch. The eleven cases are rewritten to it by the attended agent, like the tests, a goal that names its test's file with them, and what each case probes is written where the model cannot read it, in `cases/README.md`. The set reads each run's thinking for the sentences that reason about being tested or graded, by a word list whose matches the attended agent reads, and prints the runs that did per case beside `passed`, so a label that still leaks shows in the table. The traps are rebuilt as mutations of green cases in capability-and-integrity-apart. A set run after this seed and set-world-outside-the-repository gives the first pass rate earned without the labels.
