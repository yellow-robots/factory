---
created: 2026-09-17
type: seed
status: done
summary: The line after the table prints the spread of one round's pass rate and calls it the standard error; the set's rate is the mean over n rounds, whose standard error is that spread over the square root of n, so a real rise between two set runs reads as noise.
value: 4
effort: S
version: v0.12
---

## Evidence

Found by the owner's question of 2026-09-17, is it worth increasing the number of attempts. The estimator the owner gave, the sum over the cases of p(1-p) over the square of the case count, is the variance of one round's pass rate, one pass over the nine cases; v0.11 prints its root, with the n/(n-1) correction, as `standard error`. The rate on the same line is the mean over n rounds, and the standard error of a mean over n is the round's spread over the square root of n. Over the two set runs on file: v0.6, rate 0.778, printed 0.091, standard error of the rate 0.052; v0.7, rate 0.963, printed 0.064, standard error of the rate 0.037. The difference, 0.185, is 2.9 standard errors of the difference, 0.064, where the printed numbers made it 1.7 and the v0.11 note says the rise is not shown; it is. The attended agent wrote the spec without the root of n and read the comparison by it.

The estimator has a second weakness the same question raised: a case at 0 of n or n of n contributes nothing to the spread, so the seven cases of v0.7 at 3 of 3 are read as certain, while a case that fails one run in five shows 3 of 3 about half the time, 0.8 to the third being 0.51. A full set at three runs costs 25 to 34 minutes and $0.31 to $0.51, the two runs on file; the spread shrinks with the root of n and the cost grows with n.

## Idea

The line prints the standard error of the rate it prints, the round's spread over the square root of the runs, so twice the standard error of the difference between two set runs is the threshold the seed pass-rate-error meant. In the variance term each case's proportion is smoothed so a perfect score with few runs is not read as certain; the rule, Laplace's passed plus one over runs plus two or another, is chosen when the seed becomes a spec, and the version note says what the two set runs on file give under it. Attempts stay at three by default; a case that varies is run at ten alone, `--runs 10 <case>`, and a full set at ten when a version changes what the model sees.

## Goal

The line after the table prints the standard error of the rate it prints. Each case's rate has a variance under a uniform prior, Laplace's: (k+1)(n-k+1) over (n+2) squared times (n+3), k the case's runs that passed and n its runs; the standard error is the square root of the sum of those variances over the cases, divided by the case count. It is never zero, a case at 0 or at n of n included, and it is defined at one run, so the line carries it whatever the run count: `pass rate <rate> standard error <error>`, both to three decimals, and the rate stays the mean over the cases of k over n. The n/(n-1) correction and the division by the root of n are replaced by this, since the posterior variance holds both the honesty at few runs and the count of runs. The module docstring of `evals.py` says the error is under a uniform prior. The tests in `test_evals.py` whose docstring names this seed define the behaviour.
