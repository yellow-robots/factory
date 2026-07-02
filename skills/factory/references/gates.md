# Gates — deterministic, fail-closed

> **When to load this reference:** running or interpreting any gate — `check_links`, `check_task`,
> `check_cmd`, or the review verdict. For authoring context, see [`authoring.md`](authoring.md). For how
> the runner runs these gates in sequence, see [`pipeline.md`](pipeline.md).

---

## Gate table

| Gate | Checks | How to run |
|---|---|---|
| `check_links` | An artifact's `source_*` crossing-links resolve: `[[wikilink]]` → vault FS; `#issue` / URL → format, `gh` when online. Scope = the artifact, not the vault. | `python3 tools/check_links.py <draft.md> [--no-gh]` — exit 1 = stop |
| `check_task` | Task is self-contained: context slice present; no `[[wikilink]]` / `obsidian://` in build-critical sections; every backtick-cited repo path exists at the base ref. | `python3 tools/check_task.py <task.md> --repo-root <repo> --base-ref origin/main` |
| `check_cmd` | The repo's own check (from `.yr/factory.toml`) — runs in the worktree with `.venv/bin` + `node_modules/.bin` on PATH. | The runner runs it. One repair attempt on a code failure; **no repair** on an environment failure (exit 126/127). |
| Review verdict | An independent reviewer emits `VERDICT: APPROVE` or `REQUEST_CHANGES`. | The runner gates the PR on a clean `APPROVE`. Fail-closed: anything but a clean `APPROVE` blocks. |

## Advisory vs. blocking

`check_links` and `check_task` are **advisory → blocking** today: they *inform* the human
promote-to-Ready gate. Run them yourself before promoting; don't claim CI enforcement that isn't wired.

`check_cmd` and the review verdict are **blocking**: the runner halts and sets `Status=Blocked` on
failure.

## Judgment points

- **Environment vs. code failure:** if `check_cmd` exits 126 or 127, the toolchain is broken — the
  runner reports `Blocked` without a repair attempt. Investigate the environment; don't paper over it
  with a repair.
- **One repair attempt:** on a code failure, the runner makes one repair attempt. If the second run
  still fails, the run is `Blocked`.
- **Review verdict is fail-closed:** anything other than a clean `APPROVE` blocks the PR. One repair
  attempt is made after a `REQUEST_CHANGES`; then the verdict gates.
- **Scope = the artifact:** `check_links` checks only the artifact you pass it, not the whole vault.
  Run it on each draft separately.
