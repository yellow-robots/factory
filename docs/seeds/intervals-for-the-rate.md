---
created: 2026-09-17
type: seed
status: open
summary: The line after the table prints a posterior standard deviation beside the observed rate and reads twice it as a change, which holds for these eleven cases only and cannot show one case falling from 3 of 3 to 0 of 3; each case gets its posterior interval, set runs are compared case by case, and the runs a question needs are counted before it is run.
value: 3
effort: M
version:
---

## Evidence

2026-09-17, from the research on eval practice, its arithmetic on this repository checked by the attended agent. Under the v0.12 line, one case of eleven falling from 3 of 3 to 0 of 3 moves the rate by 0.091, where twice the standard error of the difference is 0.139. The variance is the posterior's but the rate beside it is k/n, whose sampling variance at n=3 and p=0.5 is 0.083 against the posterior's 0.040. By the research's power computation, from Miller's Eq. 10 at a per-run rate near 0.9, the set detects a change of about 21 points at three runs a case and 11 at ten. Bowyer, Aitchison and Ivanova, ICML 2025, show that CLT intervals dramatically underestimate uncertainty on small benchmarks; they recommend Wilson score or Bayesian intervals, the Beta posterior's quantiles in closed form, find that only a Bayesian method on a clustered model reaches the right coverage across sample sizes, as runs within cases need, and recommend a paired Bayesian method to compare two models (https://arxiv.org/abs/2503.01747). Miller's "Adding Error Bars to Evals" gives formulas for measuring the difference between two models and for planning an evaluation (https://arxiv.org/abs/2411.00640). Both read by the attended agent on the day. standard-error-of-the-rate chose the uniform prior, which the first holds defensible; the construction around it is what fails.

2026-09-17, read again against the template after the owner restated the direction, that what is evaluated is the factory and not the model: the seed betters a measure the set has, the line after the table, and gives none it lacks, which the template calls 3; the value was 4. The comparison of two builders is paired-set-runs' and the grades of a replay analyst-on-api-models', and each takes its intervals from here when it is built.

## Idea

Each row carries its case's interval, the 2.5% and 97.5% quantiles of Beta(k+1, n-k+1), and the line after the table gives the set's rate with an interval, saying that it holds for these cases and not for the ways to fail they stand for. Two set runs are compared case by case, the differences paired, and a version that means to show a change says before its run how many runs a case needs to show it. Which estimator carries the set's interval, the hierarchical model or the paired case differences, is the spec's.
