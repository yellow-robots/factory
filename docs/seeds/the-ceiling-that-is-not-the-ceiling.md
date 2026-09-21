---
created: 2026-09-20
type: seed
status: open
summary: The catch harness refuses runs it could afford, matches a finding's path by exact string, and overwrites a record's numbers when it cannot read them.
value: 3
effort: S
reporter: review
kind: integrity
version:
---

## Evidence

2026-09-20, the independent review of `catch.py`, recorded in [[20260920T123852Z]]. Three smells in one program, none of them worth widening that build for and all of them real.

**The ceiling is about twice what a review can spend.** `catch.py` refuses a run when `cases x dimensions x passes x HARD_SPEND` exceeds the allowance, which is $5.00 a case. But `reviewer.py` stops *starting* passes once the review has spent `dimensions x passes x SOFT_SPEND`, so a review's true maximum is that $2.50 plus the one pass already running, which can reach $0.25: about **$2.75, not $5.00**. The guard errs in the safe direction and the cost of erring safe is a run refused that could have been afforded. It matters more than a rounding argument because it is the number the owner is asked to decide about: the twelve-case set reads $60.00 where it cannot exceed about $33, and $60 and $33 are different decisions. [[the-catch-rate-that-decides-the-role]] derived $5.00 as well, so the spec shares the overstatement and both are amended together.

**A finding's path is matched by exact string equality.** `./reviewer.py`, an absolute path inside the throwaway worktree, a capitalised name or a stray space all score zero against the answer `reviewer.py`. The reviewer's prompt asks only for the path *as the checkout names it*, which is a request and not a wall. The one real run returned clean relative paths, so this has never bitten; what it would look like if it did is a catch rate of 0.000 with nothing anywhere looking wrong, which is the failure mode this whole area exists to avoid.

**A record whose numbers cannot be read has them overwritten.** `_numbers` returns an empty mapping on any read or parse failure, and `_tag` then writes `{"goal": ...}` over `numbers.json` and commits that to the store. The harness's answer to *I cannot read this record's numbers* is to replace them with nothing. It needs an already-damaged record -- a partial write, a full disk, a hand edit -- so the attended agent did not reproduce it and the review did, on a record with deliberately invalid JSON. The store is the factory's memory and a program that writes to it must not be able to empty a record it merely failed to read.

## Idea

The harness refuses only what it cannot afford, matches a path the way a path is meant, and never writes over what it could not read.

The allowance is checked against what a review can really cost, which is the reviewer's own stopping rule plus the one pass that may already be running, and the seed's table is corrected with it. A reported path and an answer's path are compared after both are made relative to the checkout and stripped, so a model that says `./f.py` is understood rather than silently scored zero. And a record whose numbers will not parse is left alone and said so, because the alternative is a harness that destroys evidence while tidying.

All three are small and none of them is urgent. The first is the one with a date on it, because the decision about the full set is open and the number in front of it is wrong by about half.
