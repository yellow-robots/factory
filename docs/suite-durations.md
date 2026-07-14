# Suite-durations baseline — 2026-07-14

Attribution-only evidence for the debt census's "suite-speed is the single largest recurring
time cost of a factory self-build's check gate" finding (issue #171). This report measures and
states what was found; it optimizes nothing.

- **Measuring command:** `.venv/bin/python -m pytest tests/ -q --durations=25`
- **Git ref measured:** `fe17b43180e180551e6c22945f2b6dadd097a6b2` (this build's base commit,
  `origin/main` tip at measurement time)
- **Run date:** 2026-07-14 (run started 2026-07-14T09:05:10+02:00, finished
  2026-07-14T09:17:08+02:00)
- **Total test count:** 1186 passed
- **Total suite wall time:** 717.99s (0:11:57) — order of magnitude only, see run-conditions note
  below

## Durations tail (verbatim) and derived top-10 table

Verbatim tail of the measuring run — the `slowest 25 durations` section exactly as pytest
printed it, followed by the final summary line. All 25 rows this run happen to be `call`-phase
entries; no `setup`/`teardown` rows cleared the sub-0.005s display threshold this run.

```
============================= slowest 25 durations =============================
13.42s call     tests/test_dev_runner.py::test_shadow_first_failed_condition_is_earliest_in_order
6.55s call     tests/test_dev_runner_review_bundle.py::test_bundle_hash_reproducible_across_independent_runs_with_identical_inputs
5.82s call     tests/test_dev_runner.py::test_rerun_after_failure_not_wedged
5.62s call     tests/test_dev_runner.py::test_code_failure_clears_state_and_tears_down_no_resume
5.59s call     tests/test_dev_runner.py::test_hard_kill_bounds_residue_to_its_own_run_dir_and_a_later_run_is_unaffected
5.43s call     tests/test_dev_runner.py::test_pr_stage_relaunch_after_push_hold_resumes_at_pr_stage
5.14s call     tests/test_dev_runner.py::test_tmpdir_preserved_on_env_hold_and_a_relaunch_gets_its_own_fresh_one
5.12s call     tests/test_dev_runner.py::test_relaunch_resumes_under_the_repo_keyed_worktree_and_state_paths
5.04s call     tests/test_dev_runner.py::test_relaunch_resumes_at_first_incomplete_stage
4.72s call     tests/test_dev_runner.py::test_worktree_and_state_dirs_are_repo_keyed_for_same_numbered_tasks_across_repos
4.29s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[exact_approve]
4.28s call     tests/test_dev_runner_reevaluate.py::test_reevaluate_fresh_green_head_posts_would_merge_with_reeval_note
4.28s call     tests/test_shadow_review.py::test_shadow_usage_suffixed_and_never_collides_with_gating_review_usage
4.28s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[last_line_wins_blocks]
4.28s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_case_strict_rejects_lowercase
4.26s call     tests/test_dev_runner_reevaluate.py::test_reevaluate_makes_no_issue_comments_only_the_pr_record
4.25s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[quoted_mention_not_counted]
4.23s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[trailing_whitespace_tolerated]
4.19s call     tests/test_shadow_review.py::test_two_gating_rounds_suffix_both_shadow_artifacts_and_comments
4.15s call     tests/test_dev_runner_reevaluate.py::test_reevaluate_never_arms_or_merges_even_with_auto_merge_true
4.12s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[prose_mention_not_counted]
4.12s call     tests/test_verdict_grammar.py::test_terminal_approval_reread_pins_grammar[non_approve_blocks]
4.12s call     tests/test_dev_runner_reevaluate.py::test_reevaluate_stale_base_posts_would_block_freshness
4.11s call     tests/test_dev_runner.py::test_quota_signatures_overridable_via_env
4.07s call     tests/test_dev_runner.py::test_stage_charter_append_is_byte_exact_role_then_blank_line_then_charter
1186 passed, 2 warnings in 717.99s (0:11:57)
```

Derived: the ten slowest *distinct* tests by call-phase time (identical to the top 10 rows above,
since every row this run is already a distinct test's `call` phase):

| Rank | Call time | Test |
|---|---|---|
| 1 | 13.42s | `tests/test_dev_runner.py::test_shadow_first_failed_condition_is_earliest_in_order` |
| 2 | 6.55s | `tests/test_dev_runner_review_bundle.py::test_bundle_hash_reproducible_across_independent_runs_with_identical_inputs` |
| 3 | 5.82s | `tests/test_dev_runner.py::test_rerun_after_failure_not_wedged` |
| 4 | 5.62s | `tests/test_dev_runner.py::test_code_failure_clears_state_and_tears_down_no_resume` |
| 5 | 5.59s | `tests/test_dev_runner.py::test_hard_kill_bounds_residue_to_its_own_run_dir_and_a_later_run_is_unaffected` |
| 6 | 5.43s | `tests/test_dev_runner.py::test_pr_stage_relaunch_after_push_hold_resumes_at_pr_stage` |
| 7 | 5.14s | `tests/test_dev_runner.py::test_tmpdir_preserved_on_env_hold_and_a_relaunch_gets_its_own_fresh_one` |
| 8 | 5.12s | `tests/test_dev_runner.py::test_relaunch_resumes_under_the_repo_keyed_worktree_and_state_paths` |
| 9 | 5.04s | `tests/test_dev_runner.py::test_relaunch_resumes_at_first_incomplete_stage` |
| 10 | 4.72s | `tests/test_dev_runner.py::test_worktree_and_state_dirs_are_repo_keyed_for_same_numbered_tasks_across_repos` |

## Run conditions

Single run, on a shared host, with up to two concurrent factory builds possible at the same time.
Absolute times in this report are not to be read as clean measurements — read the wall time as
order-of-magnitude only, and read the durations table as relative attribution (which tests cost
the most relative to each other), not as precise, reproducible timings.

## Scope

This is a baseline; optimization, time budgets, or any gating posture are a later round's ruling,
out of this task's scope.
