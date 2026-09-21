---
created: 2026-09-21
type: seed
status: open
summary: A cold build of this repository now spends the whole soft cap reading before its first write, so a seed whose red tests span the modules cannot be built in one run at all; two runs in a row read 20 and 32 requests, wrote nothing, and landed at $0.14 and $0.20.
value: 5
effort: M
version:
---

## Evidence

2026-09-21, building [[the-step-nobody-noticed]]'s third round on `v0.21`, fifteen tests red across `test_loop.py`, `test_repo.py`, `test_vault.py` and `test_host.py`, the product 2,277 lines in four modules. Run 20260921T121339Z: 32 requests, one check, no write and no edit, $0.198, 646 seconds; the report says every write of the final batch was refused by the cap. Run 20260921T122853Z, after the Goal was rewritten shorter and one spec: 20 requests, one check, no write and no edit, $0.140, 482 seconds. `SOFT_SPEND` is 0.125 and `HARD_SPEND` 0.25 in `builder.py`, chosen at v0.17 from a store where "a ceiling of 0.125 sits above every one of the 85 builds that answered"; every one of those builds was of a smaller repository.

The same seed's rounds that were built green cost $0.033 (five edits, one red test) and $0.010 (one edit, one red test): a run that finds one failing test and its cause early writes early. Two runs that took the whole product in first -- `gate.py` 782, `vault.py` 405, `repo.py` 334, `loop.py` 561, and the tests that name the seed -- spent it all before writing. Every read is 300 lines and one request, [[the-read-that-costs-a-request]]; every request carries the whole context again; and thinking is on, priced as output.

What the attended agent did instead, twice: took the red run's tree as the branch's base so the next run had less to do, and staged the red tests so a run sees a few. Both are work the cap forces on the person, and the second is a test file held back from the branch, which is the loop bent.

## Idea

Either the cap knows the checkout, or the reading gets cheaper, or a build is told where to look. The first: `SOFT_SPEND` scaled by what one pass over the tools' reach costs, as `the-work-a-capped-run-leaves` once scaled the calls -- a floor of today's number, since a small repository is bounded as it is. The second: [[the-read-that-costs-a-request]], larger reads for the same tokens and a third of the requests. The third: a Goal that names its files, and a builder that reads those first and the rest only when a test sends it there. Whichever, the change is in `builder.py` and reaches builds only when a version ships and its wheel is installed, so v0.21's builds are staged by hand and this is v0.22's first question.
