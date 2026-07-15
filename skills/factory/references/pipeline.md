# Pipeline — the lower pipeline and dev-runner

> **When to load this reference:** running, debugging, or understanding the lower pipeline — from
> `Status=Ready` through `dispatch.py` → `dev-runner.sh` to the PR, and the terminal merge step. For
> the human gates and closing, see [`closing.md`](closing.md). For gate mechanics, see
> [`gates.md`](gates.md).

---

## How the lower pipeline runs

Once a task is `Status=Ready` (a human's flip, or the epic-gate under a standing approval), n8n polls
the board every few minutes, finds the Ready task, and POSTs it (with explicit `owner/repo`) to the
dispatch endpoint. A second n8n workflow POSTs `/sweep` on the same cadence — the org-wide epic-gate
pass (`tools/epic_gate.py`: promote the next pre-approved slice, raise stranded claims, close finished
epics), on its own lock so a sweep never blocks a build. The tick cadence is configuration, not
prose: the live number is whatever `deploy/n8n-dispatch.json` / `deploy/n8n-epic-sweep.json` say —
cite the file, never state a figure.

**Dispatch (`tools/dispatch.py`):** bearer-auth, detached fire-and-forget (it answers n8n before the
runner runs — a refused or dying runner is invisible to n8n), fail-closed — a request that cannot name
its `owner/repo` is refused and logged, never guessed. There is no default repo. Concurrency is
**per-repo locks + a global cap**, not one flock: each target repo gets its own non-blocking lock,
acquired outermost, so a repo already building never starts a second build for itself; inside that, the
build claims one of `DISPATCH_MAX_BUILDS` (default 2, operator-adjustable) capacity slots — the cap on
concurrent builds across every repo. A busy repo or a full cap exits politely, unclaimed, for the next
poll tick — never dropped, never queue-jumped (see `deploy/DISPATCH.md`). Ahead of concurrency, the
**admission wall** refuses a repo carrying no `.yr/factory.toml` at its base ref — never onboarded —
bouncing to `Backlog` + `Reason=Needs-info` naming onboarding, both at the epic-gate sweep (a child
about to be promoted) and as `dev-runner.sh`'s own read as the backstop (a standalone item already
Ready) — see [`onboarding.md`](onboarding.md) — *The bootstrap invariant*.

**`dev-runner.sh <issue#> --repo <owner/name>`** runs the staged pipeline; each LLM stage is a separate
cold `claude -p` process (builder ≠ verifier, structural). The **build role** runs implement / test /
repair; the **review role** runs the reviewer — two independently resolved models (see *Model roles*
below).

| Stage | What it does | On failure |
|---|---|---|
| **DoR gate** | Open + on board + `Status=Ready` + `Type=Task` + non-empty acceptance criteria + both model roles resolve from the registry with a non-inverted, same-provider ranked pair. No LLM call before this passes. | Refusal, no writes — or `Status=Backlog` + `Reason=Needs-info` for content/model bounces. |
| **Claim** | Sets `Status=In Progress` (single-flight lock — drops the task from the Ready poll). | — |
| **Worktree** | Fresh `git worktree` off `origin/main` of the target repo. Reads code *and* `.yr/factory.toml` from the base ref — never a mutable working tree. Resume-aware: an environmental hold from a prior run reuses its preserved worktree and completed-stage checkpoints instead of tearing them down. | — |
| **Implement** | Build-role model writes the minimal change against the acceptance criteria. `--permission-mode bypassPermissions` (the worktree + scoped creds are the walls). | `Blocked` |
| **Test** | Independent cold process derives tests from the **acceptance criteria** (not the implementation). Boundary guard: any change outside the legal test tree (below) → `Blocked`, offending diff saved, no auto-revert. | `Blocked` |
| **Check gate** | Runner (not LLM) runs `check_cmd` from `.yr/factory.toml`. One repair attempt on a code failure (at the registry's `check_repair` stage tier when set, else the build model); no repair on an environment failure (exit 126/127). | `Blocked` |
| **Review** | Independent cold process on the **review role's model**, fed the hashed **review bundle** (`tools/review_bundle.py`: base→head diff, acceptance criteria, check output, resolved role pair; each round's verdict appended). Emits `VERDICT: APPROVE` or `REQUEST_CHANGES`; one repair attempt; fail-closed — anything but a clean `APPROVE` blocks. | `Blocked` |
| **PR** | Commit, push `task/<id>-<slug>`, open PR, post the review. | — |
| **Merge evaluator** | Deterministic terminal step (no LLM): evaluates CI-green (bounded poll; zero configured checks fails fast) · freshness against `main`'s tip (decision-time re-fetch) · terminal clean `APPROVE` · rank gate (review >= build, one provider, both ranked, the reviewer is never weaker) — in order, in code, indeterminate = failed. **Armed repo** (manifest `auto_merge = true` read live from the base ref, shadow complete, host sentinel not thrown): all-pass → factory **squash-merges**, posts `YR-MERGE: MERGED`, native close → Done; any fail → `YR-MERGE: BLOCKED — <condition>` + `Reason=Blocked`. **Every other repo (shadow):** posts a loud `YR-MERGE-SHADOW: WOULD-MERGE / WOULD-BLOCK` record, sets `Status=In Review`, and stops for the human. | environmental → no record, resumable, never a hard block |

**Environmental vs code failure, everywhere:** a stage or step that *cannot run* — quota exhaustion on
an LLM stage, a broken toolchain (exit 126/127), a gh/network blip in the evaluator — is classified
**environmental**: `Blocked` with an ENVIRONMENTAL marker (or, in the evaluator, silently resumable),
never an LLM repair, never a shadow-streak reset, and the run's completed-stage checkpoints + worktree
are preserved under `DEV_RUNNER_HOME/state` so a relaunch **resumes from the last completed stage**
instead of re-paying it. A code failure gets its one repair; a machinery contradiction resets the
shadow streak.

## Stage conduct

Every stage prompt carries one confinement contract — the **stage charter** (`tools/dev-runner.sh:695`),
appended by `run_stage` to each stage's role prompt so a stage building a foreign repo gets it too, not
just the factory's own. It is the enforcing surface; this reference states its intent, not its text.
Three of its rules bear directly on how a stage's own behavior should be read against the rest of this
document:

- **Verification is scoped; the gate owns the suite.** A stage's own verification exercises only the
  change it just made. The repo's full check suite is the **check gate**'s job (above) — one clean pass,
  exactly one more per repair round, the armed merge path's freshness re-green (rebase, then one more
  gate pass, above) excepted — and past that, server CI's (`ci_green`, above). A stage re-running the
  whole suite as its own inner loop is doing the gate's job, not its own.
- **Foreground only.** A stage never polls, watches, or sleeps on state outside its own run; when it
  can't proceed, it stops rather than wait. A `Blocked` run is that stop's correct shape, not a failure
  to route around — see *environmental vs code failure*, above.
- **The task slice is the whole context.** A stage reasons from the acceptance criteria in front of it;
  standing documents — this reference included — inform the human and the pipeline's own code, never a
  stage's working context.

## The legal test tree

The tester's boundary guard is structural, not a prompt: the runner diffs the tester's stage against
the implementer's tree and computes offenders as that diff **minus** two exclusions —

1. anything under the repo-root `tests/` directory (path prefix `tests/`) — the tester's actual
   working tree, and
2. build artifacts anywhere in the tree — `__pycache__/` directories and `*.pyc` files, compiled from
   source the tester cannot itself change, so they can't smuggle an implementation change past
   builder ≠ verifier. A repo's `.gitignore` is the first line of defense against these showing up at
   all; the exclusion is the backstop for a repo that forgets it.

Anything left after both exclusions is a boundary violation: the stage fails `Blocked`, the offending
diff is saved (`boundary-violation.diff`) for diagnosis, and there is no auto-revert. This is why a
legitimate tester file under, say, `app/src/` or `app/tests/` (not the repo-root `tests/` tree) blocks
— the guard has no concept of "looks like a test file," only "is it under `tests/`."

## The ci_green model

The merge evaluator's `ci_green` condition requires **every configured check on the PR head to
conclude successfully** — not a check_cmd run in the worktree (that's the separate, in-build check
gate), but the PR's actual GitHub check rollup. The evaluation is a bounded poll with one extra wrinkle
for a rollup that reads empty:

- A rollup that reads **zero total checks** is ambiguous the moment a PR opens — a real repo's checks
  can still be registering (GitHub Actions registers check runs asynchronously) rather than the repo
  having no CI at all — so an empty read gets its own short, bounded **registration grace**
  (`MERGE_CI_REG_POLL_INTERVAL` / `MERGE_CI_REG_GRACE`) before the evaluator concludes anything. If a
  check registers during the grace, evaluation falls through to the normal bounded wait below.
- If the rollup is **still empty when the grace expires**, the evaluator fails fast, without paying
  the (much longer) in-flight wait — a repo with genuinely no CI would otherwise stall every PR for
  the full `MERGE_CI_TIMEOUT`.
- Once a rollup carries checks (whether registered immediately or after the grace), the evaluator polls
  (`MERGE_CI_POLL_INTERVAL`) until nothing is in-flight, bounded by `MERGE_CI_TIMEOUT`.

The record's `check_rollup` field carries the terminal state as one of:

| `check_rollup` | Meaning |
|---|---|
| `success` | nothing in-flight, no failures — every configured check concluded successfully. |
| `failure` | nothing in-flight, at least one check failed. |
| `timed_out` | checks were still in-flight when the bounded wait (`MERGE_CI_TIMEOUT`) expired. |
| `empty` | a transient read, not a persisted value — zero total checks on a poll, the condition that starts the registration grace. Never itself the value recorded on a PR; superseded by whichever state the grace resolves to. |
| `empty_after_grace` | the rollup was still zero total checks when the registration grace expired — recorded as a `ci_green` failure. |

**A repo with no server CI configured at all cannot pass `ci_green`.** Every PR on such a repo reads a
zero-total rollup, pays the registration grace (nothing ever registers), and fails with
`empty_after_grace` — so every PR records `YR-MERGE-SHADOW: WOULD-BLOCK — ci_green` /
`YR-MERGE: BLOCKED — ci_green` with `check_rollup: empty_after_grace` and an empty `checks` list. That
record states a **fact about the repo** — it has no server CI wired up — not a CI run that failed.
Diagnosing it means adding server CI (a GitHub Actions workflow or equivalent) to the repo, not
debugging a broken check.

## To run by hand

```
tools/dev-runner.sh <issue#> --repo <owner/name>                       # full build
tools/dev-runner.sh <issue#> --repo <owner/name> --dry-run             # read-only: resolved plan or refusal reason
tools/dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>   # re-run the terminal decision only
```

Run from the factory root. The worktree is created and cleaned up by the runner (preserved only on an
environmental hold). `--dry-run` is the fastest way to see *why* a dispatch silently refuses.
`--re-evaluate` is the recovery path for a shadow record gone stale — see *Shadow merge choreography*
below.

## Model roles — the registry

Model choice is **operator-maintained data** (`models.toml` at the factory root; loader
`tools/registry.py`), never pipeline code. Two roles resolve independently:

- **build** (implement / test / repairs) and **review** (the reviewer) — per role, precedence is
  per-task body line (`model:` / `review_model:`, bare, case-insensitive) > per-repo manifest
  (`model` / `review_model`) > the registry's per-role default; the operator env override
  (`BUILD_MODEL` / `REVIEW_MODEL`) sits atop all three.
- Names must be registry entries — an unknown name from a body or manifest bounces `Needs-info`
  before any claim. The **only** non-registry escape is the env override with a raw model id: it runs
  unranked, loudly warned, and can never satisfy the merge rank gate (shadow-only by construction).
- **Rank gate, fail-closed twice:** at intake, an inverted or cross-provider ranked pair bounces
  `Needs-info`; at the merge evaluator, the bar is review-rank >= build-rank on one provider (the
  reviewer is never weaker) — an equal-rank pair that cleared intake also auto-merges cleanly.
- Optional per-stage repair tiers (`[roles.stage_tiers]`) let `check_repair` / `review_repair` run
  cheaper than the build role, never above it.

## Shadow merge choreography

Shadow completion (below) reads its window from prior PR **merge records**, mechanically — it has no
concept of "a build is currently running." That makes the human side of the choreography load-bearing:

- **Merge only while no build is in flight.** A human-merge click races the next dispatch's worktree cut
  the moment `main` moves: a branch cut *just before* the merge lands is stale the instant it's checked,
  even though every reviewed condition (CI, approval, rank) is clean. The runner honestly records
  `YR-MERGE-SHADOW: WOULD-BLOCK — freshness` on an otherwise-mergeable PR — this is the race from issue
  #67/PR #69, not a bug. Merging serially (never mid-build) avoids it entirely.
- **A merged-over `WOULD-BLOCK` is a rolling-window RESET, with no reason carve-out.**
  `tools/merge_shadow.py classify_event` does not distinguish *why* a blocked PR was blocked — a
  freshness-stale WOULD-BLOCK that a human merges anyway resets the shadow streak exactly like an
  overridden CI failure would. There is no exception for "it was only stale." If the PR is otherwise
  clean, don't merge over the block — recover the record instead (next point) so the eventual merge
  posts a true `WOULD-MERGE` and counts as a success, not a reset.
- **Recovery for a freshness-stale PR: a content-identical rebase, then `--re-evaluate`.** Rebase the
  branch onto the moved tip by hand (attended — the runner never rebases outside its own armed-merge
  remediation) so the diff is unchanged and the existing review verdict still applies; then run
  `tools/dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>`. This re-runs *only* the four
  terminal conditions (`ci_green` / `freshness` / `terminal_approval` / `rank_gate`) against the PR's
  *current* head — no DoR gate, no claim, no worktree, no LLM stage — reusing the originating run's
  review verdict, bundle hash, and resolved build/review roles/ranks from
  `$DEV_RUNNER_HOME/runs/<issue>-<id>/` (located via the `run_id` on the PR's last merge record). It
  posts a fresh shadow record whose note names the record it supersedes, so history reads truthfully;
  it never merges, rebases, claims, or writes board state, even on an armed repo with shadow already
  complete — the posted record is the only write. A closed/merged PR, a PR that doesn't belong to the
  named issue, or an originating run whose artifacts are missing all refuse fail-closed, before any
  write.

## The shadow review seat

A second, non-gating verdict on the same review bundle every gating round produces (issue #165) — not
to be confused with *shadow merge choreography* above, which is about the merge evaluator's WOULD-MERGE
record for a non-armed repo. Dark by default: both `YR_SHADOW_MODEL` and `YR_SHADOW_BASE_URL`
(`tools/dev-runner.sh:46-51`) must be set, or the feature is a pure no-op — no shadow subprocess, no
shadow artifact, no shadow comment, byte-identical to a build without it. When lit, a shadow round runs
the same review prompt against the same review bundle as the gating round, on its own model/base-URL
pair (`shadow_review_round()`, `tools/dev-runner.sh:927`), and is never wired into the review gate,
`terminal_approval`, or the merge evaluator — a shadow stage failure is logged and the build proceeds
unchanged.

Every shadow artifact is inert by construction — a record that can never be mistaken for the gating
grammar:

- `YR-SHADOW-REVIEW: <token>` (`shadow_verdict_token()` / the posting loop, `tools/dev-runner.sh:1079`)
  states the shadow round's own verdict, but blockquotes the transcript beneath it so no line can match
  the line-anchored gating grammar `^VERDICT:` (`verdict_line()`, same file).
- `YR-VERDICT-DIFF: agree|disagree` (`tools/verdict_diff.py`'s `render_comment` / `build_records`) pairs
  a gating round with its own same-index shadow round into one `yr-verdict-diff/1` record
  (`{schema, round, gating, shadow, agree}`) — a round with no shadow record gets no diff, never a
  synthesized disagreement.

Both grammars are defined in the modules cited above — read them there, not restated here.

## The ledger

The cross-build usage meter (epic yellow-robots/factory#204) — `tools/ledger.py`, stdlib-only like
`tools/registry.py`. Home: `$DEV_RUNNER_HOME/ledger/rows.jsonl`, an append-only JSONL file of
`yr-ledger-row/1` rows, one per runner invocation, landed under a blocking flock at whichever terminal
branch the run reaches (Needs-info bounce, `Blocked`, env-hold, or the success terminus). Each row carries
census-weighted usage per stage (`tools/stage_usage.py`'s weights, unchanged), a per-stage `price`
snapshot (`tools/registry.py`'s `input_price_per_mtok` for that stage's model, null when unregistered —
never skips the row), `totals.shadow_cost_usd` (weighted-total × price, summed over the row's non-shadow,
priced stages), outcome, repairs, wall-clock, and identity. The ledger **informs, never gates**: nothing
here touches the review gate, the rank gate, or the merge evaluator.

`per-model`/`report` are read-only aggregations over the rows, answering four standing reads: (1) the
close-time cost line — total and per-merged-task weighted cost for a repo/window; (2) the crossover cost
axis — factory-repo vs product-repo cost per merged task, same window; (3) a trial's before/after —
`per-model`'s aggregates (runs, merged tasks, weighted-cost-per-merged-task, repair rate, verdict
outcomes) across two windows; (4) the concurrency headroom — weighted tokens per day across repos. All
four are computable from the rows alone.

## The bench

The attended benchmark tool (epic yellow-robots/factory#161) that replays a candidate's solution to a
past task against sealed, held-out tests, grades it deterministically, and reports the result — never
contending with the live dispatch line: attended host CLI only, no dispatch coupling, no `/build` path,
no capacity-slot claims (`tools/bench_replay.py`'s module docstring).

Pipeline: **corpus → sealed replay → deterministic grading → report.**

- **Corpus** (`tools/bench_corpus.py extract`): derives one `yr-bench-corpus/1` record per eligible
  merged `task/*` PR — the DoR prompt, the pre-solution ref, and the held-out test files' paths and
  contents — under `bench/corpus/`.
- **Sealed replay** (`tools/bench_replay.py`'s `grade()` / `run_candidate()`): seals a fresh workdir at
  the record's `pre_solution_ref` via a depth-1 fetch of exactly that one commit. **The seal rule:** the
  seal is verified *before any grading* — no configured remote, exactly one commit reachable from HEAD
  and it IS `pre_solution_ref`, and the GitHub credential env vars absent from the child process's
  environment; any failure is `invalid-seal`, loud, never graded. The seal must survive its own
  verification.
- **Deterministic grading**: no LLM judge. The held-out tests are patched back onto the candidate's tree
  from the record itself (never from git), then the repo's own `check_cmd` runs: exit 0 is `pass`, else
  `fail`; a check harness that couldn't even execute is `ungraded-environmental`, never a graded fail.
  `run_candidate()` appends one `yr-bench-result/1` row per run to `bench/results/`.
- **Report** (`tools/bench_report.py`): `report` aggregates `yr-bench-result/1` rows into a dated
  `bench/reports/*.md` (pass rate, weighted cost, N, per-repo composition, the grading caveat below);
  `sweep-diffs` aggregates posted `YR-VERDICT-DIFF` comments into `bench/diffs/`, backfilling each PR's
  merge outcome.

**The grading caveat** — quoted verbatim by `tools/bench_report.py`'s `load_grading_caveat()` from
`bench/corpus/README.md`'s own `## Grading caveat` section, never re-worded in the report or here: a
`pass` proves only that a candidate's change makes the *same PR's own* anchored test artifacts green
under the repo's own check command — not independent proof of correctness, and not graded against the
original PR's approach.

## Judgment points

- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet.
- The tester boundary guard is structural (the runner diffs the test tree), not a prompt — do not
  weaken it or paper over violations.
- **Status is the per-task lock; the fleet's concurrency is per-repo locks + a cap, not one flock:**
  claiming sets `Status=In Progress`, which removes the task from the Ready poll — a task in flight
  cannot be double-dispatched. Cross-epic and standalone Ready items interleave unprioritized, in board
  order; dispatch serializes only within a repo (its own non-blocking lock) and across the fleet (the
  `DISPATCH_MAX_BUILDS` cap) — see *per-repo locks + a global cap*, above, and the admission wall that
  refuses an un-onboarded repo ahead of either.
- **Shadow completion is mechanical:** a rolling window over the repo's last 5 merge-record-bearing
  PRs — complete iff ≥ 3 landed unreverted successes and zero resets (an overridden `WOULD-BLOCK`, a
  reverted merge, a malformed record, or a machinery error resets). Completion only *permits* arming;
  the human arms a repo by setting `auto_merge = true` in its manifest, and the host **sentinel** file
  is the always-available kill switch.
- **Merge ≠ ship:** the factory merges only to the repo's integration branch; deploy stays separate
  and attended.
