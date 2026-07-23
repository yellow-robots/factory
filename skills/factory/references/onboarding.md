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
check_cmd    = "<your check command>"  # REQUIRED — e.g. "pytest tests/ -q" or "python3 tools/check.py"
model        = "sonnet"                # build role — a models.toml registry entry name
review_model = "opus"                  # review role — must out-rank the build role (registry default)
base_ref     = "origin/main"
# auto_merge = true                    # OPT-IN, later: arms factory merges — only after the repo's
                                       # shadow phase completes; read live from the base ref.
# test_paths     = ["tests/"]          # OPT-IN — the tester stage's only legal write surface (default: repo-root tests/)
# artifact_globs = ["__pycache__/", "*.pyc"]  # OPT-IN — build-artifact forgiveness set for the boundary guard
# server_ci      = "required"          # OPT-IN — "required" (default) or "none": this repo's declared server-CI stance
```

The runner runs `check_cmd` with `.venv/bin` and `node_modules/.bin` on PATH — name tools plainly,
no venv prefix. Precedence: explicit env > manifest > built-in default. **`check_cmd` is required**
(issue #275): there is no built-in fallback command — a manifest with no `check_cmd` bounces the task
to `Backlog` + `Reason=Needs-info`, naming the missing key, before claim/worktree/any stage. This is
judged on the manifest alone: an environment `CHECK_CMD` overrides a *declared* `check_cmd` for the
session, but never substitutes for declaring one.

Three more keys let a repo **declare its own shape** instead of being expected to conform to the
factory's own repo's shape (issue #271 slices 2–4):

- **`test_paths`** (a TOML array of repo-relative path prefixes, default `["tests/"]`) — the tester
  stage's only legal write surface; a repo whose tests don't live under the repo-root `tests/` tree
  declares where they do live instead of the boundary guard blocking every tester stage. Each prefix is
  directory-anchored (normalized to a trailing slash before matching), so `src/tests` never matches
  `src/tests_extra/`. A declared value must be a non-empty array of non-empty, repo-relative strings:
  none absolute (no leading `/`), none containing a `..` path component — a value that fails this bounces
  `Needs-info` naming the rejected value, never a silent fallback to the default.
- **`artifact_globs`** (a TOML array of glob patterns, default `["__pycache__/", "*.pyc"]`) — the
  boundary guard's build-artifact forgiveness set: paths outside `test_paths` that are still allowed
  because they're compiled *from* source the tester cannot itself change. Same validation shape as
  `test_paths` (non-empty array, non-empty strings, none absolute, none containing `..`) and the same
  `Needs-info` bounce on a rejected value.
- **`server_ci`** (`"required"` or `"none"`, default `"required"`) — the repo's declared server-CI
  stance, read by the merge evaluator's `ci_green` condition at decision time. `"none"` passes `ci_green`
  by declaration (`not_required_declared`) instead of polling an empty check rollup — for a repo with no
  server CI wired up at all. Any other declared value bounces fail-closed at the merge evaluator, naming
  the rejected value. See [`pipeline.md`](pipeline.md#the-ci_green-model) for the full model.

Recommended, not required: also declare `lint_cmd`/`lint_fix_cmd` (a stack-appropriate linter — e.g.
`ruff` for Python, `eslint` for Node, or the repo's own tooling) and `lens_cmd` (the repo's own advisory
lens content). Like every other undeclared capability in this manifest, an undeclared key stays silently
absent — never a per-build warning — the same defaults-off precedent as `auto_merge`.

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

The seam-contract invariant (see `SKILL.md`) calls for every repo-shape assumption the pipeline makes to
be either an explicit `.yr/factory.toml` key with a fail-closed default, or a written invariant a repo
must meet. `check_cmd`, `test_paths`, `artifact_globs`, and `server_ci` (above) have made that crossing —
a repo declares its own shape on each, rather than being expected to conform to the factory's own repo's
shape. One assumption remains unwritten, still met today by convention rather than a checked key:

- **Built deps exist** (step 3) — `.venv` or `node_modules` present so `check_cmd` runs offline in a
  fresh worktree. Onboard a repo that skips this and expect the check gate to fail with a broken
  toolchain, not a legible bounce. Turning this into its own manifest key is a queued
  **seam-completion** design, not yet built: until it ships, this one assumption stays a convention, not
  a declaration.

## The written invariants

Four facts about how the pipeline runs are **written invariants** — not manifest keys, because they
describe the pipeline's own mechanics rather than a repo-specific shape, and every registered repo must
meet them as given:

- **Squash merges, single-commit PRs.** The factory always squash-merges an armed repo's PR
  (`--squash`, explicit, never a plain merge or rebase); the merge evaluator's freshness remediation
  assumes a single-commit PR (it resolves the PR head's parent to find the pre-rebase base).
- **Branch layout `task/<issue>-<slug>` on remote `origin`.** Every build pushes to `task/<issue#>-<slug>`
  on the `origin` remote — the runner never invents a different branch naming scheme or pushes elsewhere.
- **Checkout convention `$YR_WORKSPACE/<name>`.** The base checkout for a registered repo resolves as
  `$YR_WORKSPACE/<name>` (default `factory/../..`) — see *Clone to the workspace*, step 1, above.
- **The check child runs with no git identity.** `check_cmd` runs with `GIT_CONFIG_GLOBAL` /
  `GIT_CONFIG_SYSTEM` neutralized to `/dev/null`, so host-ambient git config never leaks into the check —
  a check that itself needs a git identity must set one up in its own fixtures, the same as it would
  under CI.

## Judgment points

- **Auth is human work** — creating GitHub orgs/repos, minting tokens/PATs, granting scopes. An agent
  never does this; flag it to the human and hold.
- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet. Set this in the runner's env if the new repo skips Issue Types.
- **Environment failure is a blocker:** if `check_cmd` exits 126 or 127 (toolchain can't execute), the
  runner reports `Blocked` without a repair attempt (see [`gates.md`](gates.md)). Fix the environment
  before filing any real tasks.
