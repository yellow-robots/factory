---
created: 2026-09-17
type: seed
status: open
summary: Two set runs on two days differ in the builder, the harness, the cases, the notes and the day at once, so a change between them has no one cause; two builders run on one world, alternated in one sitting, have one.
value: 4
effort: M
version:
---

## Evidence

Asked by the owner on 2026-09-17, of the variation v0.7's set showed and v0.12's did not: which cause. The set at v0.7, 2026-09-16, 27 runs, and at v0.12, 2026-09-17, 33 runs, read from their records. The same in both: the model, `deepseek-flash`, every one of the 339 and 353 responses with the one `system_fingerprint`, aeb56401ca74e127821c4f9126dcb669; the library, pydantic-ai-slim 2.43.0; the role, hash 97196fd3f141c915. Different: `builder.py`, hash 26578ede7caf03bc against 5d7124422d698f2c, three commits between them, the harness's `hidden` and the tools run one at a time; `cases/`, readable at v0.7, whose runs read `cases/<name>/test_<name>.py` as the pass-rate-error seed found, and hidden at v0.12; the pass words and two new cases; the notes, 32 files under `docs/` at v0.7 and 51 at v0.12, read by 29 of v0.12's runs. The tempted test went from 2 of 3 to 3 of 3 and the rate from 0.963, standard error 0.056, to 1.000, 0.049: the difference is half its standard error, and one case's 2 of 3 against 3 of 3 is 1.3; at ten runs a side, 7 of 10 against 10 of 10 is 2.0 and 6 of 10 is 2.6. `builder.py` at v0.11 and at v0.12 differ by the six `sequential=True` and their comment, nothing else.

## Idea

A comparison is a run of its own. `evals.py`, given a second builder as a commit of this repository, makes each run of each case twice, once with the builder at HEAD and once with the builder at the commit, the order alternating round by round, both on worktrees cut from HEAD, so the cases, the notes, the harness and the hour are shared and the builder is what differs; the records of both land in this repository's `runs/`, and after the two tables one line gives each builder's rate and the difference with its standard error, the root of the sum of the two variances. The first comparison needs no variant written: the builder at v0.11 against HEAD is the barrier off against on, at ten runs a side on `tempt_the_test` and `rename_many`, 40 runs, about 40 cents and 40 minutes at v0.12's cent and minute a run. It comes after notes-hidden-from-the-set and cases-that-do-not-say-what-they-probe, or a builder that reads its answer passes under both and the comparison shows nothing. A builder older than v0.11 takes no `hidden`, so it sees `cases/` and whatever else the harness hides: a comparison that far back differs in what the model can read as well, and the spec says whether the harness refuses it. How the second builder runs, in a worktree of the commit through its own `main`, is the spec's too.
