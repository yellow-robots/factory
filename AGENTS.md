# AGENTS.md — how the Yellow Robots dev factory works

This is the operating manual for the **Yellow Robots dev factory** — the autonomous machinery that takes a
Ready ticket to a reviewed PR. It is the map for any agent (AI or human) working **on** the factory, and it
documents how the factory builds **other** repos. The deep rationale lives in [`docs/rfcs/`](docs/rfcs/);
this file points there rather than repeating it.

If you are a `claude -p` stage spawned by the dev-runner, **this file is your context for the whole
system** — you only see one issue and one worktree, but the rules below govern what you may do.

---

## What this is

`yellow-robots/factory` is the **dev factory**: a dispatcher (`tools/dispatch.py`) plus a staged runner
(`tools/dev-runner.sh`) that build YR repos like software — branch → PR → CI gate → merge.

It is **infrastructure, separate from the product repos it builds.** The products are their own repos
(`yellow-robots` = robot artifacts; `website`), each self-contained: clone one and you have everything
to develop it by hand. A product repo declares *how* to build itself (a `.yr/factory.toml` manifest — see
Conventions); the factory provides *the machinery*. No product repo depends on another, and none contains
the factory.

Two homes, one rule each:
- **GitHub Issues + Projects** = the **system of record** for *work*. Tasks, state, history. Authoritative.
- **Obsidian vault** = the **product brain** — vision and strategy, and the *readable* mirror of the RFCs.
  Canonical RFCs live here in `docs/rfcs/`; the vault is for human reading.

A task must be **self-contained**: an implementer should never need to open Obsidian to do it.

---

## The operating model (ticket-driven SDLC)

```
product/RFC discussion (vault)  →  file a Task (Issue Form = Definition of Ready)
   →  human sets Status = Ready   ← human at design-active; epic children auto-promote
   →  n8n poll (every 5 min) finds Ready  →  POST host endpoint  →  dev-runner
   →  implement → test → check → review → PR  (all autonomous, see below)
   →  merge  ← factory-executed for an armed repo under fail-closed conditions; a human otherwise
   →  native close → Status = Done
```

The human **input** gate is exercised at the design artifacts, not at every `Ready` flip: a human decides
*what gets built* by setting a product-spec or feature-rfc `active`. Below that standing approval,
flipping a governed epic to Ready, promoting its next pre-approved slice, and closing a finished epic are
**mechanical** — enacted without a human touch, fail-closed back to the human on any doubt (a missing or
invalid approval record raises `Needs-info` rather than guessing). The cord-pull — un-Readying an epic —
remains the human's veto, always available. A standalone task with no governing design above it has no
standing approval to run on, so it keeps the original per-task human promotion. The **output** gate —
**merge the PR** — is **factory-executed for an armed repo under fail-closed conditions**: a repo whose
manifest sets `auto_merge = true`, that has completed the shadow phase, and whose host **sentinel** kill
switch is not thrown gets its green, fresh, approved, rank-holding PR **squash-merged by the factory
itself**, with a durable `YR-MERGE: MERGED` record; any failed condition posts `YR-MERGE: BLOCKED` and
stops for the human. Every **other** repo is **human-merged** exactly as before — the factory only
evaluates and records (shadow), never merges. Either way, implement → test → check → review → PR runs
without a human throughout, and no PR reaches `main` without passing the deterministic gates.

### Task lifecycle (state machine — RFC 0003)

State lives on **native GitHub primitives**, never labels:
- **Type** = Issue Type (`Task` / `Bug` / `Feature`; an `Epic` type exists but is reserved — the epic/technical-RFC node stays `Feature` until there's real value), set by the Issue Form.
- **Hierarchy** = native sub-issues (`gh issue create --parent`).
- **Status** = a Projects single-select field, and *is* the state machine:
  `Backlog → Ready → In Progress → In Review → Done`.
- **Reason** = a Projects single-select for off-track work: `Needs-info`, `Blocked`.

| Transition | Who | When |
|---|---|---|
| → Ready | **human** (standalone task) / **epic-gate** (child of a Ready epic) | standalone: meets Definition of Ready and a human wants it built. Epic child: the epic carries a standing-approval record — the epic-gate promotes the next slice automatically |
| Ready → In Progress | runner | claims the task (drops it from the Ready poll → single-flight) |
| → Backlog + Reason=Needs-info | runner | DoR content gate fails (empty acceptance criteria; a `model:`/`review_model:` or manifest model absent from the registry; an inverted or cross-provider ranked build/review pair) |
| → Reason=Blocked | runner | any stage fails, or the tester touches production code |
| In Progress → In Review | runner | PR opened (and left for the human, unless the factory merges it below) |
| → Done | **native automation** | PR merged → issue closes → Projects sets Done. The merge is **factory-executed** for an armed repo (squash-merge under fail-closed conditions) or **human** otherwise |

One shared board — **"Yellow Robots — Dev"** — spans every product repo; each item carries its repo, and
the runner builds against that repo. Lean backlog: we do **not** park no-foreseeable-start tasks. Drop them
(close as *not planned*); important ones resurface.

**Board intake — epics host their tasks ("Model E", validated 2026-06-23).** The filtered repo auto-add is
**off**; intake is hierarchy-driven. Add the **epic** (the technical-RFC Issue) to the board once
(`gh project item-add`, or the UI) and its **Task sub-issues auto-add at `Backlog`** — confirmed both
orderings: boarding an epic pulls in its *existing* children, and a child created under an *already-boarded*
epic flows in too (the *Auto-add sub-issues* → *item-added → Backlog* workflows). So the board holds **epics
*and* their tasks**, but `Status` is meaningful only for tasks; an epic just rests at `Backlog` until it's
closed → `Done`. This is safe because the runner builds **`Type=Task` only** (the DoR Type gate) — an epic
fat-fingered to `Ready` is refused, never built. Read the board via a **group-by-parent** view (roadmap)
and/or a `-type:Feature` filter (tasks only); epic progress (`n of m done`) is free from native sub-issues.
Gotcha: `gh project item-list` is eventually-consistent (can lag creation by ~a minute) — the issue-side
`projectItems` is the authoritative read.

---

## How a change is built (the dev-runner pipeline)

`tools/dev-runner.sh <issue#> --repo <owner/name>` runs one Ready ticket through, each stage a **separate
cold `claude -p` process** — independence by construction (builder ≠ verifier):

1. **DoR gate** — issue Open + on the board + Status=Ready + **Type=Task** + non-empty acceptance criteria.
   Refuses before any LLM call otherwise. No writes on refusal. (Type=Task stops an epic/Feature accidentally
   set Ready from being built — epics are sub-issue parents, not build units; `REQUIRE_ISSUE_TYPE=''` opts
   out for repos that don't use Issue Types.)
2. **Claim** — Status → In Progress (the single-flight lock: the task leaves the Ready poll).
3. **Worktree** — a fresh `git worktree` off `origin/main` of the **target repo**. The implement stage runs
   `--permission-mode bypassPermissions` because the *worktree + scoped creds are the walls*, not a prompt
   (the confinement principle).
4. **Implement** — writes the minimal change against the acceptance criteria. Runs the **build role**
   (implement/test/repair share it), resolved from the model registry (`models.toml` via
   `tools/registry.py`); the reviewer runs the separate **review role**. See Conventions → Models.
5. **Test (independent)** — a cold process derives tests from the **acceptance criteria (the spec)**, not
   from the implementation. **Boundary guard:** if the tester changes anything outside the repo's test
   tree, the run is **Blocked and raised** (no auto-revert) and the offending diff saved. Build artifacts
   (`__pycache__/`, `*.pyc`) are excluded — compiled from source the tester can't change, they can't
   smuggle an implementation change, so they never count as a violation.
6. **Check gate** — the *runner* (not an LLM) runs the repo's check command (its `.yr/factory.toml`
   `check_cmd`). One repair attempt on a **code** failure; an **environment** failure (the check can't
   execute — exit 126/127, e.g. a broken venv) is reported as Blocked *without* a repair, so a broken
   toolchain is never papered over.
7. **Review (independent)** — a cold process, running the **review role**, emits `VERDICT: APPROVE` or
   `REQUEST_CHANGES`. One repair attempt, then the verdict gates the PR (fail-closed: anything but a
   clean APPROVE blocks). The reviewer never runs below the review rank; a repair stage with a registry
   stage tier runs at that tier, else at the build role.
8. **PR** — commit, push `task/<id>-<slug>`, open the PR, Status → In Review, post the review.
9. **Terminal merge decision (deterministic, no LLM stage)** — evaluate the fail-closed merge conditions
   in order, in code (indeterminate = failed): CI green + fresh against `main`, a clean terminal
   `VERDICT: APPROVE`, and the strict review-rank > build-rank gate. A repo is **armed** when its manifest
   sets `auto_merge = true` (read at *decision time* from the base ref's current tip), the host
   **sentinel** kill switch is not thrown, and **shadow is complete** (computed mechanically from the
   repo's prior PR merge records + `main` history — a rolling window of clean, unreverted merges). An armed
   repo whose conditions all hold is **squash-merged into `main` by the factory** (rebasing + re-establishing
   green first if `main` moved; a rebase conflict blocks for the human), recorded as a durable
   `YR-MERGE: MERGED`, and left to native close→Done. Any failed condition for an armed repo posts
   `YR-MERGE: BLOCKED — <condition>` + `Reason=Blocked`. A repo that is **not** armed (or armed but
   shadow-incomplete) stays in **shadow**: a loud `YR-MERGE-SHADOW` record and the PR waits for a human.
   Environmental failures while evaluating/recording/merging are resumable — never a streak reset or a hard Block.

For a non-armed (or armed-but-blocked) PR, a **human reviews and merges**. Merge → native close → Done.

### Dispatch (RFC 0004)

An n8n workflow polls the board every 5 min for `Status=Ready & OPEN` and POSTs each issue **with its
explicit repo** to a host endpoint (`tools/dispatch.py`, bearer-auth), which `flock`-guards a single run and
invokes the runner. Dispatch is **fail-closed** (RFC 0006): there is no default repo — a request that can't
name its `owner/name` repo is refused and logged, never guessed, so a ticket can't be mis-routed into the
wrong repo. Polling (not webhooks) is deliberate — self-healing, no missed events. Deploy notes:
[`deploy/DISPATCH.md`](deploy/DISPATCH.md).

---

## Invariants — and why

- **Builder ≠ verifier.** Implementer, tester, and reviewer are independent cold processes. Enforced
  structurally (separate processes; the tester boundary guard), not by prompt.
- **Confinement is the environment, not intent.** Protection comes from what the system *permits* (fresh
  worktree, scoped creds, deterministic gates), not from what the model *plans*. That is why
  `bypassPermissions` is safe.
- **Native primitives over sidecars.** Issue Types, Projects fields, sub-issues, native close→Done — not
  labels, not custom backstops.
- **Deterministic gates dispose.** The LLM proposes; the machine-checked gate (CI / the repo's check
  command / the verdict gate) disposes. Nothing reaches `main` without passing a gate a human can trust.
- **The factory is repo-agnostic.** It builds any registered product repo via that repo's manifest. The
  factory holds *no* product knowledge; a product holds *no* copy of the factory.
- **The factory builds from git refs, never a mutable working tree.** The code *and* the `.yr/factory.toml`
  manifest are read from the base ref (`origin/main`), so a base checkout that's stale, dirty, or doubling
  as a live dev workspace can't affect a build. (Falls back to the working tree only for an un-pushed repo.)
- **One task = one PR.** If it can't be, it's too big — split into sub-issues.
- **Docs are consolidated, not accreted.** Update/merge/trim the canonical doc; don't pile a new one next
  to it. This file is that discipline applied to the repo.

---

## Repo map

| Path | What |
|---|---|
| `tools/dev-runner.sh` | the autonomous build pipeline (gate → implement → test → check → review → PR → terminal merge decision) |
| `tools/merge_shadow.py` | terminal merge-condition evaluator + `yr-merge-record` writer + mechanical shadow-completion (stdlib) |
| `tools/dispatch.py` | host endpoint n8n calls to fire a build (RFC 0004) |
| `tools/textutil.py` | small shared text helpers (slug/truncate) |
| `models.toml` + `tools/registry.py` | the model registry (build/review roles, ranks, stage tiers) + its stdlib loader/JSON CLI |
| `tests/` | pytest suite — `test_dev_runner.py` (stubbed, proves stage order + gates), `test_registry.py`, `test_dispatch.py`, `test_textutil.py` |
| `deploy/` | dispatch service unit, env example, n8n workflow + query, `DISPATCH.md` |
| `docs/rfcs/` | **canonical** RFCs — the *why* in depth |

---

## Conventions

- **Branches:** `task/<issue#>-<slug>`.
- **Workspace & per-repo config:** the factory finds its workspace relative to itself (`YR_WORKSPACE`,
  default `factory/../..`) and resolves each target repo's checkout as `$YR_WORKSPACE/<name>`. Build
  specifics live in the repo, not the factory — a `.yr/factory.toml` manifest declaring `check_cmd`
  (yellow-robots → `pytest tests/ -q`, website → `python3 tools/check.py`), a per-repo `model` and
  `review_model` (registry entry names — the build and review roles), `base_ref`, and `auto_merge` (a
  bool, default false — see the terminal merge decision). The runner runs the check in the ephemeral
  worktree with the repo's `.venv/bin` and `node_modules/.bin` on PATH, so `check_cmd` names tools plainly
  (no venv path). Precedence: explicit env > manifest > built-in default. `auto_merge` alone is read
  **not** with the rest but re-read from the base ref's *current tip at decision time* (a start-of-run
  value must never arm a merge).
- **The merge kill switch (sentinel):** a host-level file (`$DEV_RUNNER_HOME/merge-killswitch`, default
  `~/.cache/dev-runner/merge-killswitch`) read **live** at each merge decision. Present → the factory
  refuses that merge globally, without a git round-trip (a file, not an env var — a spawned runner carries
  its spawn-time environment). See [`deploy/DISPATCH.md`](deploy/DISPATCH.md).
- **The factory's own check command:** `.venv/bin/python -m pytest tests/ -q` (the venv is authoritative;
  no system pytest).
- **Commits** end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Models — the registry is the model surface.** Every selectable model lives in `models.toml` (data,
  not code; loader + JSON CLI in `tools/registry.py`), which also carries the **convention record** in its
  header — strategy/authoring on the strongest class, execution delegated down-tier. The runner resolves
  **two roles**: **build** (implementer, independent tester, repair stages) and **review** (the reviewer,
  every round). Per role, precedence is **per-task > per-repo > registry default**, with an **operator env
  override atop** (`BUILD_MODEL` / `REVIEW_MODEL` — these replace the retired `MODEL` / `HARD_MODEL`
  tiers). Task selectors are bare, case-insensitive lines in the issue body: `model:` (build) and
  `review_model:` (review); the manifest mirrors them (`model` / `review_model`). A name absent from the
  registry — from the task body or the manifest — bounces to Needs-info before claiming, as does a ranked
  build/review pair that is inverted (review weaker than build) or cross-provider; an **equal-rank** pair
  builds (the strict review>build bar is the later merge gate, not intake). The **one** place a raw,
  unregistered id may run is the operator env override — it runs **unranked with a loud warning** and is
  never bounced.
- **Auth is human work.** Creating GitHub orgs/repos, minting tokens/PATs, and granting scopes are done by
  a human, never by an agent.

---

## RFC index (the why, in depth)

`docs/rfcs/` holds the **implemented** technical RFCs. Unimplemented designs live in the Obsidian brain
(`04 projects/yellow-robots/factory/`) and cross into the repo only once built — no vault mirror of the RFCs.

- **[0001 — Ticket-driven development workflow](docs/rfcs/0001-ticket-driven-dev-workflow.md)** — Obsidian
  vs GitHub split; builder ≠ verifier; the SDLC.
- **[0002 — The dev-AI runner](docs/rfcs/0002-dev-ai-runner.md)** — cold `claude -p` staged runner; the
  stack-agnostic seam.
- **[0003 — Task state model](docs/rfcs/0003-task-state-model.md)** — native Status/Reason fields; the
  state machine above.
- **[0004 — Dispatch](docs/rfcs/0004-dispatch.md)** — n8n poll → host endpoint → runner; `build_task` core.
- **[0005 — The upper pipeline](docs/rfcs/0005-upper-pipeline.md)** — intent → spec → feature RFC →
  technical RFC → tasks; the airlock. *Being reworked in the brain into the upper-pipeline implementation spec.*

The brain organizes the *why* as **iterations** (`04 projects/yellow-robots/factory/iterations/`): `1-build-pipeline`,
`2-repo-agnostic`, `3-upper-pipeline`. Unimplemented designs (e.g. **autonomous merge**) and the full design
history live there; each crosses into `docs/rfcs/` only once built. The documentation model itself is
`skills/factory/references/documentation-model.md` (the factory skill).
