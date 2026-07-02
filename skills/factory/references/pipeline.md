# Pipeline — the lower pipeline and dev-runner

> **When to load this reference:** running, debugging, or understanding the lower pipeline — from
> `Status=Ready` through `dispatch.py` → `dev-runner.sh` to the PR. For the human gates and closing,
> see [`closing.md`](closing.md). For gate mechanics, see [`gates.md`](gates.md).

---

## How the lower pipeline runs

Once a human sets `Status=Ready`, n8n polls the board every 5 minutes, finds the Ready task, and POSTs
it (with explicit `owner/repo`) to the dispatch endpoint.

**Dispatch (`tools/dispatch.py`):** bearer-auth, `flock`-guarded (single run), fail-closed — a request
that cannot name its `owner/repo` is refused and logged, never guessed. There is no default repo.

**`dev-runner.sh <issue#> --repo <owner/name>`** runs the staged pipeline; each stage is a separate cold
`claude -p` process (builder ≠ verifier, structural):

| Stage | What it does | On failure |
|---|---|---|
| **DoR gate** | Open + on board + `Status=Ready` + `Type=Task` + non-empty acceptance criteria. No LLM call before this passes. | Refusal, no writes, `Status=Needs-info`. |
| **Claim** | Sets `Status=In Progress` (single-flight lock — drops task from the Ready poll). | — |
| **Worktree** | Fresh `git worktree` off `origin/main` of the target repo. Reads code *and* `.yr/factory.toml` from the base ref — never a mutable working tree. | — |
| **Implement** | Writes the minimal change against the acceptance criteria. `--permission-mode bypassPermissions` (the worktree + scoped creds are the walls). | — |
| **Test** | Independent cold process derives tests from the **acceptance criteria** (not the implementation). Boundary guard: any change outside the repo's test tree → `Blocked`, offending diff saved, no auto-revert. Build artifacts (`__pycache__/`, `*.pyc`) are excluded — they can't smuggle an implementation change. | `Blocked` |
| **Check gate** | Runner (not LLM) runs `check_cmd` from `.yr/factory.toml`. One repair attempt on a code failure; no repair on an environment failure (exit 126/127). | `Blocked` |
| **Review** | Independent cold process emits `VERDICT: APPROVE` or `REQUEST_CHANGES`. One repair attempt; then gates the PR. Fail-closed: anything but clean `APPROVE` blocks. | `Blocked` |
| **PR** | Commit, push `task/<id>-<slug>`, open PR, `Status=In Review`, post review. | — |

## To run by hand

```
tools/dev-runner.sh <issue#> --repo <owner/name>
```

Run from the factory root. The worktree is created and cleaned up by the runner.

## Judgment points

- **`REQUIRE_ISSUE_TYPE=''`** in the runner environment opts out of the Type=Task check for repos that
  don't use Issue Types yet.
- The tester boundary guard is structural (the runner diffs the test tree), not a prompt — do not
  weaken it or paper over violations.
- **Model selection:** Sonnet is the default. `model: opus` in the issue body selects Opus (allowlisted
  values: `opus` / `sonnet`).
- **Status is the single-flight lock:** claiming sets `Status=In Progress`, which removes the task from
  the Ready poll. A task in flight cannot be double-dispatched.
