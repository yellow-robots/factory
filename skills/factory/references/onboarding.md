# Onboarding — adding a new repo to the factory

> **When to load this reference:** adding a new repo to the Yellow Robots factory. For workspace layout
> and context, see the workspace `AGENTS.md`. Auth (GitHub orgs / tokens / scopes) is human work — see
> *Invariants* in `SKILL.md`.

---

## The bootstrap invariant

The pipeline reads a repo's build contract — `.yr/factory.toml` — from the **base ref**, at the worktree
stage, before any LLM call runs. A repo with nothing there has nothing to read: **onboarding cannot ride
a build.** The manifest and the runnable scaffold it depends on (built deps present, `check_cmd` green in
a fresh worktree) are **attended prerequisites on the design side** — set by a human before the repo ever
reaches the board — **never a slice** the factory produces or promotes for itself. The **admission wall**
(`tools/epic_gate.py`'s sweep, and `dev-runner.sh`'s own read as the backstop) is the mechanical check
that catches a repo that skipped this: it bounces the work to `Backlog` + `Reason=Needs-info`, naming
onboarding, rather than sailing an un-onboarded repo into a doomed build.

The **non-delegable acts** — **auth · onboarding · arming** — are attended, human work, stated once,
plainly: no agent ever creates an org/repo/token, writes a repo's first manifest, or sets
`auto_merge = true`.

## Steps

### 1. Clone to the workspace

Clone the repo to `/opt/yellow-robots/<name>`. The factory resolves repos as `$YR_WORKSPACE/<name>`
(default `factory/../..`), so this path is the expected checkout location.

### 2. Add `.yr/factory.toml`

At the repo root:

```toml
check_cmd    = "<your check command>"  # e.g. "pytest tests/ -q" or "python3 tools/check.py"
model        = "sonnet"                # build role — a models.toml registry entry name
review_model = "opus"                  # review role — must out-rank the build role (registry default)
base_ref     = "origin/main"
# auto_merge = true                    # OPT-IN, later: arms factory merges — only after the repo's
                                       # shadow phase completes; read live from the base ref.
```

The runner runs `check_cmd` with `.venv/bin` and `node_modules/.bin` on PATH — name tools plainly,
no venv prefix. Precedence: explicit env > manifest > built-in default.

### 3. Ensure built deps exist

`.venv` (Python) or `node_modules` (JS) must be present in the **base checkout** so `check_cmd` runs
offline in a fresh worktree without internet access. The worktree itself is ephemeral and carries
neither (both are gitignored) — the runner puts the base checkout's `.venv/bin` / `node_modules/.bin`
on `PATH` for the check-command child (step 2).

### 4. Register on the board

The dispatch endpoint routes by the Issue's native repo (fail-closed: it must name `owner/<name>`).
Ensure the shared board ("Yellow Robots — Dev") can see the repo, and that new Issues filed in the repo
can be added to it via the board's auto-add or manual intake rules.

### 5. Verify end-to-end

File a minimal test task (DoR form), set `Status=Ready`, and confirm the runner:
1. Picks it up (dispatch routes correctly).
2. Passes the DoR gate.
3. Builds without error.
4. Opens a PR.
5. Records a merge-evaluator verdict on the PR (see [`pipeline.md`](pipeline.md#the-ci_green-model) for
   the full model). On a repo whose CI is wired up and green, expect `YR-MERGE-SHADOW: WOULD-MERGE` (or
   `YR-MERGE: MERGED` if the repo is already armed). On a repo with **no server CI configured yet**,
   expect `YR-MERGE-SHADOW: WOULD-BLOCK — ci_green` with `check_rollup: empty_after_grace` — that record
   states the fact that the repo has no server CI wired up, not that a check failed. Either record is a
   correct, expected result of the smoke test, not a bug to chase.

Check that `check_cmd` passes in the worktree — this is the gate that will block every future build if
it's broken.

## Gate

The check gate is per-repo and grows with the repo. Adding a new check to `check_cmd` is a normal PR on
that repo. The gate must be green in the worktree before considering a build passing.

## Current assumptions

The factory currently **assumes**, rather than declares, several things about a registered repo — met
today by convention, not by a manifest key the runner checks:

- **Built deps exist** (step 3) — `.venv` or `node_modules` present so `check_cmd` runs offline in a
  fresh worktree.
- **`check_cmd` is defined** (step 2) — the in-build check gate the runner actually runs.
- **Server CI is configured** — the merge evaluator's `ci_green` condition polls the PR's GitHub check
  rollup, not `check_cmd`; a repo with no server CI wired up (no workflow at all) cannot pass it, ever
  — see [`pipeline.md`](pipeline.md#the-ci_green-model).
- **Tests live under the repo-root `tests/` tree** — the tester stage's boundary guard treats
  `tests/**` as the only legal place for tester changes; a repo whose test suite lives elsewhere (e.g.
  `app/tests/`) will see every tester stage blocked as a boundary violation — see
  [`pipeline.md`](pipeline.md#the-legal-test-tree).

These are today's unstated shape assumptions, not a repo-declared contract — the seam-contract
invariant (see `SKILL.md`) calls for turning each into an explicit `.yr/factory.toml` key with a
fail-closed default. That work is a queued seam-completion design, not yet built: onboard a repo that
doesn't meet these assumptions today and expect the corresponding stage to block until the design ships
or the repo's shape changes to match.

## Judgment points

- **Auth is human work** — creating GitHub orgs/repos, minting tokens/PATs, granting scopes. An agent
  never does this; flag it to the human and hold.
- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet. Set this in the runner's env if the new repo skips Issue Types.
- **Environment failure is a blocker:** if `check_cmd` exits 126 or 127 (toolchain can't execute), the
  runner reports `Blocked` without a repair attempt (see [`gates.md`](gates.md)). Fix the environment
  before filing any real tasks.
