# Onboarding — adding a new repo to the factory

> **When to load this reference:** adding a new repo to the Yellow Robots factory. For workspace layout
> and context, see the workspace `AGENTS.md`. Auth (GitHub orgs / tokens / scopes) is human work — see
> *Invariants* in `SKILL.md`.

---

## Steps

### 1. Clone to the workspace

Clone the repo to `/opt/yellow-robots/<name>`. The factory resolves repos as `$YR_WORKSPACE/<name>`
(default `factory/../..`), so this path is the expected checkout location.

### 2. Add `.yr/factory.toml`

At the repo root:

```toml
check_cmd = "<your check command>"   # e.g. "pytest tests/ -q" or "python3 tools/check.py"
model     = "sonnet"                  # "sonnet" or "opus"
base_ref  = "origin/main"
```

The runner runs `check_cmd` with `.venv/bin` and `node_modules/.bin` on PATH — name tools plainly,
no venv prefix. Precedence: explicit env > manifest > built-in default.

### 3. Ensure built deps exist

`.venv` (Python) or `node_modules` (JS) must be present in the repo so `check_cmd` runs in a fresh
worktree without internet access. The worktree shares the repo's built deps via the normal Git worktree
mechanism.

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

Check that `check_cmd` passes in the worktree — this is the gate that will block every future build if
it's broken.

## Gate

The check gate is per-repo and grows with the repo. Adding a new check to `check_cmd` is a normal PR on
that repo. The gate must be green in the worktree before considering a build passing.

## Judgment points

- **Auth is human work** — creating GitHub orgs/repos, minting tokens/PATs, granting scopes. An agent
  never does this; flag it to the human and hold.
- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet. Set this in the runner's env if the new repo skips Issue Types.
- **Environment failure is a blocker:** if `check_cmd` exits 126 or 127 (toolchain can't execute), the
  runner reports `Blocked` without a repair attempt (see [`gates.md`](gates.md)). Fix the environment
  before filing any real tasks.
