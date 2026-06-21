# RFC 0001 — Ticket-driven development workflow

**Status:** Accepted (2026-06-17) · **Amended 2026-06-18:** the state model is superseded by [0003-task-state-model](0003-task-state-model.md) — every facet is a **native** primitive (Issue Types, Projects Status/Reason fields, sub-issues), not labels · **Decision-makers:** Jose + Claude

## Context

We need a workflow connecting the *product* side (where humans + frontier models discuss everything from vision to task definition) and the *development* side (implementation, testing, deployment) — without losing or missing tasks in the back-and-forth, and **without inventing our own process**. Developers will be mainly AIs.

## Decision

Adopt a standard **ticket-driven SDLC**:

- **Obsidian = product brain.** Vision, strategy, and **RFCs** (design decisions). Holds **no task state**.
- **GitHub Issues + Projects = tasks, and the single system of record.** This is what prevents lost tasks: a task changes *state* in one place; it never physically shuttles between systems.
- **git = execution.** Branch → PR → CI → review → merge.

**Flow:** RFC or direct Issue → **Ready** → branch/PR → CI + independent test & review → merge (closes the Issue) → archived.

## Details

- **Origin (two paths):** small/clear work → an Issue directly; large/uncertain/architectural work → an **RFC** (here, in Obsidian) that *spawns* task-Issues.
- **State — _amended → [0003-task-state-model](0003-task-state-model.md)_:** status lives **on the Issue**, not on a board. One `status:*` label per open issue (`backlog → ready → in-progress → in-review`, plus `needs-info` / `blocked`); `done` / `cancelled` = native close. *Ready* = the available pull queue. A board, if any, is a *projection* of the labels (recommended retired for now). The original `Backlog→…→Done` here described a board column — which is board-resident in GitHub and drifted from the task, prompting RFC 0003.
- **Definition of Ready:** an AI could implement it without asking — goal, acceptance criteria, context/RFC links, constraints, test expectations, sized to one PR. (Encoded as the Issue Form.)
- **Definition of Done:** acceptance criteria met + tests written & green + CI passing + reviewed + merged. (Encoded as the PR template.)
- **Sizing:** one task = one PR. Bigger = an epic (parent Issue/RFC) → sub-issues.
- **Quality — `builder ≠ verifier` (locked now; the rest deferred):** tests derive from the Issue's *acceptance criteria* and are authored/verified by a **different agent** than the builder; an **independent code-review** agent on every PR (maintainability/simplicity/security), separate from "tests green." These are the dev + risk lenses; product-gate / weighted voting wait for Stage 2+.
- **Dispatch:** event (`issue labeled status:ready` → **n8n** → dispatch a dev-AI) **+ a scheduled poll-sweep** of the ready queue as the fallback (a dropped event never loses a task). Status-label transitions follow git events (PR opened → `status:in-review`, merged → native `done`); judgment moves (→ `ready` / `needs-info`, or `cancelled` via close) are human/runner per [0003-task-state-model](0003-task-state-model.md).
- **Dev-AI:** a headless Claude Code / OpenClaw run on the repo, **separate from Joam** (Joam *runs* the product; dev-agents *build* it). It reads the **Issue** (self-contained per DoR); Obsidian is read-only fallback for RFC links; it never writes Obsidian.

## Alternatives considered

- **Obsidian-as-tracker** (markdown task files + our own state machine): rejected — it reinvents an issue tracker and creates a *second* system of record, which is exactly how tasks get lost. GitHub Issues gives native issue↔branch↔PR↔commit linkage for free.

## Consequences

- Retires the old vault task-system; the `task-v1` schema becomes a GitHub **Issue Form** template (its `status` field → `status:*` labels per [0003-task-state-model](0003-task-state-model.md)).
- Reshapes It2: Obsidian holds strategy + RFCs (not `design/`/`plans/` folders); tasks move to Issues/Projects.
- Lightweight, sturdy, and reusable beyond this project — which was the goal.
