---
name: factory
description: >-
  How an AI actually runs a change through the Yellow Robots dev factory — the operating manual, not
  orientation. Use when authoring or shipping any change on a YR repo: writing a product-spec / feature-rfc
  / technical-rfc / task, crossing the Obsidian→GitHub airlock, running the dev-runner, or invoking the
  gates (check_links, check_task, the repo check_cmd, the review verdict). Covers the iteration model,
  builder ≠ verifier, the deterministic gates, and the two human gates (promote-to-Ready, merge). Reach for
  it whenever the work is factory-driven development — even if the user doesn't say "factory".
---

# The Yellow Robots dev factory — operating manual

The factory builds a software product the way software should be built: in **iterations**, each from
*intent* to *shipped code*, with **builder ≠ verifier** and **deterministic gates** that a human can trust.
A probabilistic LLM proposes; the machine-checked gate disposes.

For workspace layout and the repos, use the **`yellow-robots`** skill first. This skill is the *how*: how to
take one iteration through the two pipelines. The full documentation model is the brain's **`conventions.md`**
(`04 projects/yellow-robots/factory/conventions/conventions.md`); the templates are in **`factory/templates/`**;
the deep rationale is **`factory/AGENTS.md`** + `factory/docs/rfcs/`.

## Two pipelines, one shape

```
UPPER (the design side — author + cross)            LOWER (the build side — automated)
  intent → product-spec → [feature-rfc →            Status=Ready → n8n poll → dispatch
    technical-rfc] → task            ──airlock──►      → dev-runner: implement → test → check
  (Obsidian brain)            (GitHub Issues)           → review → PR   (cold claude -p per stage)
```

Both are *author proposes, gate disposes*. **Upper** is **v1 human-driven-with-agent-assist**: you (or an
agent a human drives) fill each artifact, run the gates, and a human approves at each step — no stage is
automated yet. **Lower** is fully automated once a human promotes a task to Ready.

## The iteration spine (types)

`product-spec —1:N→ feature-rfc —1:1→ technical-rfc —1:N→ task`. **Floor = `product-spec → task(s)`** —
the two rfc layers are *earned*, added only when the change has a feature worth arguing or codebase-fit
that isn't obvious. Small iterations skip them. (Plus `research` / `note` / `runbook` as supporting docs.)
Homes: `product-spec` + `feature-rfc` live in **Obsidian**; `technical-rfc` (on the epic Issue) + `task` +
PR live on **GitHub**. The boundary is crossed **once**, and the downstream artifact **cites, never copies**.

## Run an iteration (the procedure)

1. **product-spec** — in the brain, from `templates/product-spec.md`. WHAT/WHY only, no tech; acceptance
   criteria in **EARS** (`WHEN <condition> THE SYSTEM SHALL <behavior>`). `type: product-spec`, a stable
   `id`, `status: active`. Gate: *spec ready* (human).
2. **feature-rfc** *(only if earned)* — the approach/decision/scope/non-goals; `source_spec:` the spec.
   Gate: *approve RFC* (human reviews the outline first).
3. **Cross the airlock → technical-rfc** — author it on the **epic GitHub Issue** from
   `templates/technical-rfc.md`. Name the **exact files/patterns/integration points** against the *current*
   tree, and write a **per-task context slice** (the minimal codebase-fit paragraph a dev needs, citing
   `repo/path.py:NN`). It carries `source_feature_rfc:` as a `[[wikilink]]`. **Run `check_links` on the draft
   before filing** (below); then file as **clean prose** — never raw frontmatter (GitHub shows it as noise).
   Gate: *review the technical RFC* (human).
4. **task** — one GitHub Issue via the Task DoR form, from `templates/task.md`: **Goal**, **Acceptance**
   (the EARS criteria as `- [ ]`), **Context & links** (paste the technical-RFC slice — self-contained),
   **Test expectations**, **Constraints**, **Size**. **Run `check_task`** (below). **One task = one PR**;
   bigger ⇒ split into sub-issues.
5. **Promote to Ready** — *a human sets Status → Ready*. **Never an agent.** This is the first human gate
   and the only dispatch signal.
6. **The lower pipeline builds it** — n8n poll → `dispatch.py` (fail-closed: it must name `owner/repo`) →
   `dev-runner.sh`: DoR gate → claim → fresh worktree off the base ref → implement → **independent** test
   (from the acceptance criteria) → `check_cmd` → **independent** review (`VERDICT: APPROVE`) → PR. Each
   stage is a separate cold `claude -p` (builder ≠ verifier, structurally). To run it by hand:
   `tools/dev-runner.sh <issue#> --repo <owner/name>`.
7. **Merge** — *a human reviews and merges* (the second human gate). Native close → Status = Done.

## The gates (deterministic — fail-closed)

| gate | checks | run it |
|---|---|---|
| `check_links` | an artifact's `source_*` crossing-links resolve (`[[wikilink]]`→vault FS; `#issue`/URL→format, `gh` when online). Scope = the artifact, not the vault. | `python3 tools/check_links.py <draft.md> [--no-gh]` — exit 1 = stop |
| `check_task` | the task is self-contained: Context slice present, **no `[[wikilink]]`/`obsidian://` in build-critical sections**, every backtick-cited repo path exists at the base ref | `python3 tools/check_task.py <task.md> --repo-root <repo> --base-ref origin/main` |
| `check_cmd` | the repo's own check (from `.yr/factory.toml`) — runs in the worktree with `.venv/bin` + `node_modules/.bin` on PATH | the runner runs it; one repair attempt on a code failure, **no** repair on an environment failure (exit 126/127) |
| review verdict | an independent reviewer emits `APPROVE` / `REQUEST_CHANGES` | the runner gates the PR on a clean `APPROVE` |

`check_links` / `check_task` are **advisory→blocking** today: they *inform* the human promote-to-Ready gate.
Run them yourself before promoting; don't claim CI enforcement that isn't wired.

## Invariants — never weaken

- **Builder ≠ verifier.** Implementer, tester, reviewer are independent cold processes — structural, not a prompt.
- **Confinement is the environment, not intent.** Fresh worktree + scoped creds + deterministic gates are the walls; that's why the implement stage can run `bypassPermissions`.
- **Build from git refs, never a mutable tree.** Code *and* `.yr/factory.toml` are read from the base ref.
- **Native primitives** (Issue Types, Projects fields, sub-issues, native close→Done) — not labels, not sidecars.
- **Repo-agnostic.** The factory holds no product knowledge; a product holds no copy of the factory. Each repo declares how to build itself in `.yr/factory.toml`.
- **Two human gates** — promote-to-Ready and merge. We hold them; no auto-promote, no auto-merge.
- **PRs only.** The pipeline produces PRs. Host/ops/deploy work is done directly and attended — never as a Ready ticket.
- **Auth is human work.** Orgs/repos/tokens/scopes are the human's, never an agent's.
- **Code is king; shipping freezes the why.** A shipped product-spec/rfc is an immutable record — a later change is a *new* iteration, not an edit of the old one.

## Onboard a new repo

Mechanical: clone it to `/opt/yellow-robots/<name>`; add **`.yr/factory.toml`** (`check_cmd`, `model`,
`base_ref`); ensure built deps exist (`.venv` / `node_modules`) so `check_cmd` runs in a worktree; make sure
the shared board can name `owner/<name>` (the dispatch routes by the issue's native repo, fail-closed). The
check gate is per-repo and grows with the repo.
