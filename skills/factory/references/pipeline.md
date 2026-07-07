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
epics), on its own lock so a sweep never blocks a build.

**Dispatch (`tools/dispatch.py`):** bearer-auth, `flock`-guarded (single build in flight), detached
fire-and-forget (it answers n8n before the runner runs — a refused or dying runner is invisible to
n8n), fail-closed — a request that cannot name its `owner/repo` is refused and logged, never guessed.
There is no default repo.

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
| **Test** | Independent cold process derives tests from the **acceptance criteria** (not the implementation). Boundary guard: any change outside the repo's test tree → `Blocked`, offending diff saved, no auto-revert. Build artifacts (`__pycache__/`, `*.pyc`) are excluded — they can't smuggle an implementation change. | `Blocked` |
| **Check gate** | Runner (not LLM) runs `check_cmd` from `.yr/factory.toml`. One repair attempt on a code failure (at the registry's `check_repair` stage tier when set, else the build model); no repair on an environment failure (exit 126/127). | `Blocked` |
| **Review** | Independent cold process on the **review role's model**, fed the hashed **review bundle** (`tools/review_bundle.py`: base→head diff, acceptance criteria, check output, resolved role pair; each round's verdict appended). Emits `VERDICT: APPROVE` or `REQUEST_CHANGES`; one repair attempt; fail-closed — anything but a clean `APPROVE` blocks. | `Blocked` |
| **PR** | Commit, push `task/<id>-<slug>`, open PR, post the review. | — |
| **Merge evaluator** | Deterministic terminal step (no LLM): evaluates CI-green (bounded poll; zero configured checks fails fast) · freshness against `main`'s tip (decision-time re-fetch) · terminal clean `APPROVE` · strict rank gate (review > build, one provider, both ranked) — in order, in code, indeterminate = failed. **Armed repo** (manifest `auto_merge = true` read live from the base ref, shadow complete, host sentinel not thrown): all-pass → factory **squash-merges**, posts `YR-MERGE: MERGED`, native close → Done; any fail → `YR-MERGE: BLOCKED — <condition>` + `Reason=Blocked`. **Every other repo (shadow):** posts a loud `YR-MERGE-SHADOW: WOULD-MERGE / WOULD-BLOCK` record, sets `Status=In Review`, and stops for the human. | environmental → no record, resumable, never a hard block |

**Environmental vs code failure, everywhere:** a stage or step that *cannot run* — quota exhaustion on
an LLM stage, a broken toolchain (exit 126/127), a gh/network blip in the evaluator — is classified
**environmental**: `Blocked` with an ENVIRONMENTAL marker (or, in the evaluator, silently resumable),
never an LLM repair, never a shadow-streak reset, and the run's completed-stage checkpoints + worktree
are preserved under `DEV_RUNNER_HOME/state` so a relaunch **resumes from the last completed stage**
instead of re-paying it. A code failure gets its one repair; a machinery contradiction resets the
shadow streak.

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
  `Needs-info`; at the merge evaluator, the bar is *strict* review-rank > build-rank on one provider —
  an equal-rank pair that cleared intake still never auto-merges.
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

## Judgment points

- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet.
- The tester boundary guard is structural (the runner diffs the test tree), not a prompt — do not
  weaken it or paper over violations.
- **Status is the single-flight lock:** claiming sets `Status=In Progress`, which removes the task from
  the Ready poll. A task in flight cannot be double-dispatched. Cross-epic and standalone Ready items
  interleave unprioritized, in board order — the dispatch `flock` serializes them.
- **Shadow completion is mechanical:** a rolling window over the repo's last 5 merge-record-bearing
  PRs — complete iff ≥ 3 landed unreverted successes and zero resets (an overridden `WOULD-BLOCK`, a
  reverted merge, a malformed record, or a machinery error resets). Completion only *permits* arming;
  the human arms a repo by setting `auto_merge = true` in its manifest, and the host **sentinel** file
  is the always-available kill switch.
- **Merge ≠ ship:** the factory merges only to the repo's integration branch; deploy stays separate
  and attended.
