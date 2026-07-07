# AGENTS.md — how the Yellow Robots dev factory works

The **Yellow Robots dev factory**: [`tools/dispatch.py`](tools/dispatch.py) +
[`tools/dev-runner.sh`](tools/dev-runner.sh) take a Ready ticket to a reviewed PR for any registered,
self-contained repo (declares *how* to build itself via `.yr/factory.toml`); deep rationale in
[`docs/rfcs/`](docs/rfcs/). GitHub Issues + Projects is the system of record for work; the Obsidian vault
is the product brain and RFC mirror — tasks are self-contained, no Obsidian needed to implement one.

---

## The operating model (ticket-driven SDLC)

```
product/RFC discussion (vault)  →  file a Task (Issue Form = Definition of Ready)
   →  human sets Status = Ready   ← human at design-active; epic children auto-promote
   →  n8n poll (every few minutes) finds Ready  →  POST host endpoint  →  dev-runner
   →  implement → test → check → review → PR  (all autonomous, see below)
   →  merge  ← factory-executed for an armed repo under fail-closed conditions; a human otherwise
   →  native close → Status = Done
```

The human **input** gate sits at the design artifacts: a human decides *what gets built* by setting a
product-spec or feature-rfc `active`. Below that standing approval, flipping a governed epic to Ready,
promoting its next slice, and closing a finished epic are **mechanical**, fail-closed to the human on any
doubt (an invalid or missing record raises `Needs-info` rather than guessing). The cord-pull —
un-Readying an epic — remains the human's veto; a standalone task with no governing design keeps the
original per-task human promotion. The **output** gate — **merge the PR** — is **factory-executed for an
armed repo under fail-closed conditions** (`auto_merge = true`, sentinel clear): squash-merged with a
durable `YR-MERGE: MERGED` record, else `YR-MERGE: BLOCKED` and a stop for the human. Every **other** repo
stays **human-merged**.

### Task lifecycle (state machine — RFC 0003)

State lives on native GitHub primitives, never labels: `Backlog → Ready → In Progress → In Review → Done`,
`Reason` = `Needs-info` / `Blocked`.

| Transition | Who | When |
|---|---|---|
| → Ready | **human** (standalone) / **epic-gate** (epic child) | standalone: DoR met, human decides; epic child: standing approval auto-promotes the next slice |
| → Done | native automation | PR merged (factory-executed for an armed repo, human otherwise) |

Remaining transitions and the board are RFC 0003's detail.

---

## How a change is built

`tools/dev-runner.sh <issue#> --repo <owner/name>` stages DoR → implement → test → check → review → PR →
merge decision. Depth: `skills/factory/references/pipeline.md` / `gates.md`, RFC 0002/0004,
[`deploy/DISPATCH.md`](deploy/DISPATCH.md).

---

## Invariants — and why

- **Builder ≠ verifier.** Implementer, tester, reviewer run as independent cold processes — structural,
  not a prompt.
- **Confinement is the environment, not intent.** The system's *permits* (worktree, scoped creds,
  deterministic gates) protect, not the model's *plans* — why `bypassPermissions` is safe.
- **Native primitives over sidecars.** Issue Types, Projects fields, sub-issues, native close→Done, never
  labels.
- **Deterministic gates dispose.** The LLM proposes; the machine-checked gate (CI / `check_cmd` / the
  verdict) disposes — nothing reaches `main` unchecked.
- **Repo-agnostic.** Builds any registered repo via its manifest; the factory holds no product knowledge,
  no product holds a copy of the factory.
- **Builds from git refs, not a mutable working tree.** Code and `.yr/factory.toml` read from
  `origin/main`, so a stale/dirty/live-dev checkout can't affect a build (falls back to the working tree
  only when unpushed).
- **One task = one PR.** Too big? Split into sub-issues.
- **Docs are consolidated, not accreted.** Update/merge/trim the canonical doc, don't pile on a new one —
  this file is that discipline applied to itself.

---

## Repo map

| Path | What |
|---|---|
| `tools/dev-runner.sh` | the staged build pipeline |
| `tools/merge_shadow.py` | merge-decision evaluator + shadow-completion |
| `tools/dispatch.py` | n8n's build-trigger endpoint (RFC 0004) |
| `tools/stage_usage.py`, `tools/textutil.py` | PR usage-summary comment; shared text helpers |
| `models.toml` + `tools/registry.py` | the model registry + loader/CLI |
| `tests/` | the pytest suite |
| `deploy/` | dispatch service unit, env example, n8n workflow, `DISPATCH.md` |
| `docs/rfcs/` | canonical RFCs |

---

## Conventions

- **Branches:** `task/<issue#>-<slug>`. **Check command:** `.venv/bin/python -m pytest tests/ -q` (venv
  authoritative).
- **Workspace & manifest:** checkout is `$YR_WORKSPACE/<name>` (default `factory/../..`); per-repo
  `.yr/factory.toml` sets `check_cmd`, `model`/`review_model`, `base_ref`, `auto_merge` (default false),
  precedence env > manifest > default. `auto_merge` re-reads the base ref's tip at decision time, never a
  start value. The **sentinel** kill switch (host file) blocks any merge if present — see
  [`deploy/DISPATCH.md`](deploy/DISPATCH.md).
- **Commits** credit the authoring model, never a hardcoded name: the runner stamps the body
  (`dev-runner, <model-id>`); an attended commit ends with
  `Co-Authored-By: <authoring model> <noreply@anthropic.com>`.
- **Models — the registry is the model surface.** `models.toml` holds the **convention record** (strategy
  on the strongest class, execution down-tier), two roles — **build** (implement/test/repair) and
  **review** — precedence per-task > per-repo > registry default, plus an operator override
  (`BUILD_MODEL`/`REVIEW_MODEL`, replacing retired `MODEL`/`HARD_MODEL`). Selectors `model:` /
  `review_model:` live in the issue body/manifest; an unregistered or wrongly-ranked pair bounces to
  Needs-info, and only the override runs unranked, warned.
- **Auth is human work** — orgs/repos/tokens/scopes, never an agent.

---

## RFC index

`docs/rfcs/` holds the **implemented** RFCs (0001–0005). Unimplemented designs live in the Obsidian brain,
crossing over once built. The documentation model itself is
`skills/factory/references/documentation-model.md`.
