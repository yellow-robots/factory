---
name: factory
description: >-
  How an AI actually runs a change through the Yellow Robots dev factory — the operating manual, not
  orientation. Use when authoring (product-spec · feature-rfc · technical-rfc · task), reviewing a spec or
  RFC, running the lower pipeline or its gates (check_links / check_task / check_cmd / review verdict),
  closing an iteration (promote-to-Ready · merge → Done · doc freeze · skill release), migrating a legacy
  doc, or onboarding a new repo. Covers builder ≠ verifier, deterministic gates, and the human gates.
  Routes each operation to the right reference on demand. Reach for it whenever the work is factory-driven
  development — even if the user doesn't say "factory".
---

# The Yellow Robots dev factory — operating manual

The factory builds a software product the way software should be built: in **iterations**, each from
*intent* to *shipped code*, with **builder ≠ verifier** and **deterministic gates** that a human can trust.
A probabilistic LLM proposes; the machine-checked gate disposes.

For workspace layout and the repos, see the workspace **`AGENTS.md`** (org orientation). This skill is the
*how*; the deep rationale is **`factory/AGENTS.md`** + `factory/docs/rfcs/`. The templates are in the
**factory repo** at `templates/` — they ship inside the installed plugin (a git-sourced plugin is the whole
repo), always at hand without an external checkout. The documentation model lives authoritatively at
[`references/documentation-model.md`](references/documentation-model.md).

## Two pipelines, one shape

```
UPPER (the design side — author + cross)            LOWER (the build side — automated)
  product-spec → [feature-rfc →                     Status=Ready → n8n poll → dispatch
    technical-rfc] → task            ──airlock──►      → dev-runner: implement → test → check
  (Obsidian brain)            (GitHub Issues)           → review → PR   (cold claude -p per stage)
```

**Intent/vision sits _outside_ the pipeline** — a human brain doc (the vault's vision & strategy), not a
spine artifact. The **product-spec is the root**: it captures the intent as its own WHAT/WHY and carries no
upstream `source_*`. Reference the vision in prose if useful, never as a gated crossing-link.

Both are *author proposes, gate disposes*. **Upper** is **v1 human-driven-with-agent-assist**: you (or an
agent a human drives) fill each artifact, run the gates, and a human approves at each step. **Lower** is
fully automated once a human promotes a task to Ready.

## Operations — load on demand

Each factory operation maps to one reference. Load the reference for the phase you are performing; route
chained work (author → review → close) phase-by-phase — routing the chain is normal. An ask that maps to
**no** operation is reported as a `ROUTING GAP:` (see *Invariants*).

| Operation | When | Reference |
|---|---|---|
| **Authoring** | Writing a product-spec, feature-rfc, technical-rfc, or task | [`references/authoring.md`](references/authoring.md) |
| **Reviewing** | Reviewing a spec or RFC (adversarial steelman → ranked findings → human gate) | [`references/reviewing.md`](references/reviewing.md) |
| **Gates** | Running check_links / check_task / check_cmd / review verdict | [`references/gates.md`](references/gates.md) |
| **Pipeline** | Running or debugging the lower pipeline / dev-runner | [`references/pipeline.md`](references/pipeline.md) |
| **Closing** | Promote-to-Ready · merge → Done · doc freeze · skill release | [`references/closing.md`](references/closing.md) |
| **Migrating** | Migrating a legacy doc onto the model | [`references/migrating.md`](references/migrating.md) |
| **Onboarding** | Adding a new repo to the factory | [`references/onboarding.md`](references/onboarding.md) |
| **Documentation model** | Any question about doc types, lifecycle, frontmatter, or the iteration model | [`references/documentation-model.md`](references/documentation-model.md) |
| **Architect** | Spec-ready grounding + supersession disposition, authoring the crossing's technical-rfc, or the close's ship-walk | [`references/architect.md`](references/architect.md) |
| **Debt rounds** | Running a tech-debt round, acting on a debt raise, or closing a debt epic | [`references/debt-rounds.md`](references/debt-rounds.md) |

## Invariants — never weaken

- **Builder ≠ verifier.** Implementer, tester, reviewer are independent cold processes — structural, not a prompt.
- **Confinement is the environment, not intent.** Fresh worktree + scoped creds + deterministic gates are the walls; that's why the implement stage can run `bypassPermissions`.
- **Build from git refs, never a mutable tree.** Code *and* `.yr/factory.toml` are read from the base ref.
- **Native primitives** (Issue Types, Projects fields, sub-issues, native close→Done) — not labels, not sidecars.
- **Repo-agnostic.** The factory holds no product knowledge; a product holds no copy of the factory. Each repo declares how to build itself in `.yr/factory.toml`.
- **The human owns the *input* gate.** The input gate is exercised at the design artifacts — a human decides *what* gets built by setting a product-spec or feature-rfc `active`; no agent ever sets `active`. Below that standing approval, flipping an epic Ready, promoting its next pre-approved slice, and closing a finished epic are mechanical, fail-closed back to the human on any doubt; a standalone task with no governing design keeps per-task human promotion. The *output* gate (merge) is **factory-executed for an armed repo** under fail-closed conditions (shadow first; arming is the human's manifest edit; the sentinel is the kill switch) and human for every other repo. The durable rule is *a human decides what to build*, not *a human merges every PR*.
- **PRs only.** The pipeline produces PRs. Host/ops/deploy work is done directly and attended — never as a Ready ticket.
- **Auth is human work.** Orgs/repos/tokens/scopes are the human's, never an agent's.
- **Code is king; shipping freezes the why.** A shipped product-spec/rfc is an immutable record — a later change is a *new* iteration, not an edit of the old.
- **Fail-loud routing.** Chained work is routed phase-by-phase to exactly one operation each; routing a chain (author → review → close) is normal — route each phase. When a request maps to **no** operation, surface it on its own line beginning exactly `ROUTING GAP: ` followed by the unmappable ask; never force it to the nearest fit.
