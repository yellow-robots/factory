---
created: 2026-09-16
type: seed
status: done
summary: Every read stays in the conversation; G1 spent 155k input tokens on three edits, and that curve decides how large a checkout the builder can work in.
value: 4
effort: S
version: v0.6
---

## Evidence

`20260915T160616Z`: input_tokens 155,449 for 12 requests and 1,016 lines read; `builder.py` alone is three reads of 300 lines. Cache hits covered 137k of it, so the money was small ($0.009), but the context grows with every call and the caps were set without knowing the curve. The rename of v0.5 (`20260916T154210Z`) reached 3.45M input tokens over 60 requests, 57k per request, before the cap.

## Goal

`runs.py` gains the column `input_per_request`, placed after `input_tokens`: `input_tokens` divided by `requests`, rounded to the nearest integer, an empty cell when either is missing, not a number, or `requests` is zero. Nothing else in the table changes. The test in `test_runs.py` whose docstring names this seed defines the behaviour.

The measure the seed asks for is then a reading of the table: the column across the factory's own builds and, once the evaluation set runs, its median per case in the table of `evals.py`. A `search` function or a map of the checkout are answers for when that column says the reads are the cost.
