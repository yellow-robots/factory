---
created: 2026-09-19
type: seed
status: open
summary: README names constants of builder.py by value; the gate never reads it, so a release can carry a page describing caps the program no longer has, and v0.16 did.
value: 3
effort: S
reporter: review
kind: integrity
version:
---

## Evidence

2026-09-19, found by the independent reviewer of runs 20260919T064941Z, 20260919T065440Z and 20260919T070052Z, reproduced by the attended agent. After the caps became a function of the checkout, `README.md` still read "80 tool calls, 60 provider requests in the library; a cap hit in the library ends the run with no report". All three clauses were false: the numbers, where they come from, and what happens when one is reached. `gate.py check` was silent, and `gate.py release` would have cut the tag.

The gate reads the vault against its templates and the repository, and the vault is `docs/`. README is neither a note nor code, so nothing derives it and nothing checks it. It is the page a reader outside the repository sees first.

## Idea

The gate reads README for the names it quotes: a constant of a program named there with a value beside it must have that value, and a constant it names that the program no longer has is a problem like any other the gate prints. What it cannot check is prose, and it should not try; what it can check is the numbers and the names, which are exactly what goes stale.
