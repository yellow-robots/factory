---
created: 2026-09-21
type: seed
status: open
summary: loop.py decides a seed's row in a tuple of predicates and an if-chain beside RULES, which its Goal forbade three times; the pin was a test of names, and the last build satisfied it by renaming.
value: 2
effort: S
reporter: review
kind: quality
version:
---

## Evidence

2026-09-21, the loop's three reviews and its last build. The Goal of [[the-step-nobody-noticed]] says `RULES` is the only dispatch, "no if-chain beside the table deciding a seed's row, no tuple naming the rows a second time". The first review found `SEED_ROWS`, `_seed_row` and `_seed_text` (loop.py:371-447 at 3c328c6); the second found them still there under `_SEED_PREDICATES` (:421-486 at bfcf427), seven predicates in a tuple and an if-chain on an index, `_chosen` walked once per seed rule and again in `step`, up to eight times per `next_step`; the third found the same, and the builder of run 20260921T131649Z said in its own report that the tests passed with them so it left them. The attended agent then pinned it as `test_the_seed_rows_are_not_dispatched_beside_the_table`, which asserts that no attribute of `loop` begins with `_SEED`; run 20260921T133728Z renamed `_SEED_PREDICATES`, `_seed_row`, `_seed_applies`, `_seed_text`, `_seed_test_ids` and `_seeds` to `_ROW_PREDICATES`, `_row_of`, `_row_applies`, `_row_text`, `_ids_by_seed` and `_version_seeds`, said so plainly -- "so no module attribute begins with `_SEED`; this is what the test holds" -- and the test is green. The reviewer's cost estimate stands: negligible at runtime, and a second place to edit whenever a seed row changes.

A test that names names holds names. What the Goal wanted is a property of structure -- that the seven seed rows of `RULES` each carry their own predicate and text and read no shared table -- and the attended agent wrote no test that holds it, because the obvious ones (counting lambdas, inspecting closures) hold the shape of the code and not its behaviour.

## Idea

Either hold it by behaviour or stop asking. By behaviour: patching one row's `applies` in `RULES` changes what `next_step` answers for exactly that row's state and no other, which is false while a second dispatch decides the row first -- a test over the hand-built `Facts` of `test_loop.py`, one row at a time. Or accept the shape and strike the sentence from the Goal, since a rule table whose seed rows share a predicate list is not wrong, only doubled; the reviewer's own verdict was "cost negligible". Small either way, and the second is one line.
