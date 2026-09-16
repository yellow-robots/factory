---
created: 2026-09-16
type: seed
status: spec
summary: Thinking mode ignores temperature, so no run repeats; every eval case needs three runs and its numbers are distributions.
value: 4
effort: S
version: v0.6
---

## Evidence

DeepSeek's documentation: in thinking mode, temperature "will not trigger an error but will also have no effect" (read 2026-09-15). v0.1 and v0.2 reported temperature 0 and were never at zero. The parity runs of v0.2 differed in call order between attempts. The two follow-ups of one v0.5 seed, both small, took 25 and 29 requests where the first build of another took 10.

## Goal

`evals.py` runs every case N times, three unless `--runs N` says otherwise, and its table reports medians, so a case's numbers are distributions and not single numbers. The tests in `test_evals.py` whose docstring names this seed define the behaviour: at the default, one case yields three records and its medians are the middle values of three; `--runs 1` yields one record and each median is that run's value; `--runs 2` yields the mean of the two.

After the build, by the attended agent: the evaluation set's first run at the default, so every case has its spread on record. The role text and the thinking effort are the two knobs to vary on purpose, one at a time, once that baseline exists.
