# RFC 0005 — The upper pipeline (intent → spec → feature RFC → technical RFC → tasks)

**Status:** Accepted (2026-06-23) — v1 proven end-to-end (Feature A → PR #44 on yellow-robots); the Phase-1.5 crossing-link/task linters are built; board intake follows "Model E" (see `AGENTS.md`); refinements F2/F3/F5 landed. · **Decision-makers:** Jose + Claude · **Builds on:** [0001](0001-ticket-driven-dev-workflow.md), [0002](0002-dev-ai-runner.md), [0003](0003-task-state-model.md), [0004](0004-dispatch.md) · **Research basis:** [[upper-pipeline-prior-art]], [[prince-multi-agent-knowledge-engine]], and the internal corpus in `04 projects/factory/research/` (Obsidian).

> **Naming note.** The **factory is itself a product** — reusable across SW-dev projects (it builds any repo) — so a factory capability is designed through the *same* SDLC as any product feature. "RFC" then has two senses, split by **which side of the product↔engineering chasm** they sit on, not by subject: a **feature RFC** is the **product-side** design handover, authored in the Obsidian product brain (stage 2), for any product *including the factory itself*; a **technical RFC** is the **engineering-side** design on the repo — for a pipeline feature this is the stage-3 *technical RFC* the **amphibian** writes when the feature RFC crosses the chasm, while the factory's own *foundational* technical RFCs are **0001–0005** in `docs/rfcs/`. An engineering/technical RFC drafts in Obsidian and commits to the repo only once **accepted** — 0005 itself followed that path: drafted in Obsidian, accepted 2026-06-23, now committed here. When ambiguous this doc says *feature RFC*; "factory" means the **dev factory** (this repo), not the robot-manufacturing "factory" of the product vision.

---

## Context

The lower pipeline is built and proven: a **Ready** task becomes a reviewed PR through a staged, cold-`claude -p` runner with `builder ≠ verifier` and deterministic gates (RFCs 0001–0004). Everything *above* `Ready` — the path from a product idea down to a buildable task — is, in [0001](0001-ticket-driven-dev-workflow.md), a single arrow:

```
product/RFC discussion (Obsidian)  →  file a Task (= Definition of Ready)  →  Ready  →  [lower pipeline]
```

That arrow hides four acts — **product intent & spec → feature RFC → architectural assessment → task decomposition** — and today one operator performs all of them, in their head, for every feature. As feature complexity grows this is where control is lost and where an assisting agent can't help: there is no *staged role* for it to own, only a human wearing every hat in sequence.

We chose to climb: scaffold the upper pipeline so each act becomes a **focused stage** with its own artifact, gate, and loadable context — and automate a stage **only once it is proven robust** (the incremental, gated approach). Before designing we researched the field twice:

- **External prior art** ([[upper-pipeline-prior-art]]): GitHub **Spec-Kit**, Amazon **Kiro**, **BMAD-METHOD**, **Task Master**, **Aider** architect/editor, **Roo** Boomerang, **Cline** Plan/Act, and the **PRINCE** paper. Four file/git-native systems converge on the *same* staged, spec-driven funnel. Two things are **not** off-the-shelf and are ours to build: **architectural assessment against an existing codebase**, and a **per-stage evaluation harness**.
- **Internal corpus** (`04 projects/factory/research/`, 38 docs): a substantial, in places *more mature* prior design of the harness — a full dev-process design, a designed memory-consolidation layer, and pre-designs of both "missing" pieces above. **We reconcile with it; we do not re-derive it.**

---

## Decision

Build the upper pipeline as a **staged, spec-driven scaffold** that plugs into the proven lower pipeline at the `Ready` seam. **v1 is the groundwork** — templates, conventions, gates, the inter-stage handoff, and traceability — operated **human-driven-with-agent-assist**. Each stage's *automation* is a later, separately-earned rung.

### The stages (the workflow, in flow order)

| # | Stage (role) | The one thing it produces | Home | Human gate |
|---|---|---|---|---|
| 1 | **Product intent → spec** | a product spec: WHAT/WHY only, **EARS** acceptance criteria, no tech | Obsidian product brain | *spec ready* |
| 2 | **Feature RFC** | the design handover — approach, scope, decisions; cites the spec | Obsidian product brain | *approve RFC* |
| 3 | **Architectural assessment** | a **technical RFC**: which modules/patterns/integration-points/conventions the feature touches in the **existing** repo, + a per-task context slice | the **epic GitHub Issue** (+ optional Obsidian mirror); **slices → task Issues** | *review the technical RFC* |
| 4 | **Task decomposition** | one-PR-sized **DoR task-Issues**, each *self-contained* (carries its arch slice) | GitHub Issues | *promote to Ready* **(existing)** |
| 5 | **Build → PR** *(done)* | code | the factory (lower pipeline) | *merge* **(existing)** |

The two gates we already hold — *promote to Ready* and *merge* — are the **bottom of a ladder of gates**. v1 adds three lightweight "review the plan" gates above them (spec / feature RFC / technical RFC). We hold the gates; we do not auto-promote.

### Three load-bearing conventions

1. **Self-contained handoff (instruction-in / summary-out).** Each stage hands the next a *complete* artifact and nothing else — the downstream worker never reaches back into the upstream's context (Roo Boomerang) and never needs Obsidian (BMAD self-contained story files; the DoR form already mandates this for tasks: *"a dev should not need to roam Obsidian"*). The technical RFC exists precisely to make stage-4 tasks satisfy this for the **codebase-fit** half of the context.

2. **Traceability by citation (anti-drift).** Every artifact cites its source: spec → intent, feature RFC → spec, technical RFC → feature RFC + the exact repo modules, task → feature RFC + technical-RFC-slice, PR → task (`Closes #`). Obsidian artifacts use block-references; tasks use Issue links. This makes drift *detectable*. (PRINCE's in-text citations; the corpus's knowledge-graph-as-namespace is the v2 form.) v1 = the citation *convention*; the **crossing-link check** that enforces it (resolve every Obsidian↔GitHub reference, **fail loud** on a dangling one) is the first mechanization earned after the thin thread — see *Artifact homes* below. It is **scoped to pipeline-artifact crossing-links** (a spec / feature RFC / technical RFC's `source_*` refs), **not** the vault's ordinary wikilinks (the live vault already carries dozens of intentional unresolved links — `obsidian unresolved total` ≈ 53). The GitHub-side chain — task → epic-Issue technical RFC → feature RFC link, and PR → task via `Closes #` — resolves today.

3. **Gates are reviews of the plan, not the output.** Per PRINCE/Cline, the cheap, control-preserving checkpoint is approving the *outline before* the stage commits, not the artifact after. Each upper gate reviews a draft/outline.

### Artifact homes & the Obsidian↔GitHub boundary (decided)

The load-bearing decision (resolved at review, 2026-06-22): **keep the split.** Product intent, spec, and feature RFC live in the **Obsidian product brain**; the technical RFC + task slices + everything downstream live on the **GitHub surface**. The split is safe — and *only* safe — when governed by a **one-way airlock**:

1. **Dependencies flow one way, down the funnel.** Above the technical RFC: Obsidian. Below it: GitHub, repo-local. Nothing below the technical RFC reaches back up into the vault.
2. **The boundary is crossed exactly once**, at the **feature RFC → technical RFC** seam, by a **single role** — the *amphibian agent* (below). One crossing, not an N×M mesh.
3. **Fail-loud accessibility.** Product docs live *outside* the repo but must be *fully accessible*: every crossing-link is machine-resolved, or the workflow **stops, visibly and loudly**. "Accessible" is an enforced invariant, not a hope. (Scoped per convention 2 — crossing-links in pipeline artifacts, not the whole vault.)

**Loop-backs are manual, not automated.** The airlock bars *automated* back-edges, not human judgment. When a downstream discovery invalidates something upstream (a technical RFC reveals the spec was wrong), the pipeline **fails loud and stops** — a human revises the upstream spec/feature-RFC and re-runs forward. v1 has **no automated cycles**: we accept manual, visible loop-backs and don't build loop machinery now.

**The amphibian agent (handover without copying).** Stage 3 is run by the one role that touches both systems. It **reads** the feature RFC from the vault (the filesystem at `/srv/obsidian/vaults/obsidian/`, or the `obsidian` CLI's link-aware `read`) and **writes** the technical RFC + per-task slices onto the **epic GitHub Issue** and task Issues. The RFC is **cited, never copied** — the technical RFC is not a duplicate but a *projection* of the RFC onto the codebase (new, repo-grounded content with a resolvable backlink). Two disciplines it inherits: its credentials are **scoped** (vault-read + write-only-to-this-epic), and — because a spawned agent gets a minimal, constructed context (no skills catalogue), its **technical-RFC-authoring skill is inlined into its payload**. Every role *below* it is GitHub-only and repo-local, so the build never crosses the boundary at all.

### How v1 is operated

*Human-driven-with-agent-assist* means: the assisting agent **drafts** each artifact in-session against its template; the human reviews at the gate and **places** it in its home — product-brain artifacts (spec, feature RFC) in Obsidian (the human owns that surface; the agent does not autonomously write the vault as a pipeline step), the technical RFC on the **epic GitHub Issue** (drafted by the amphibian agent), and tasks via the Issue form. The lower-pipeline build agent reads **only** the task Issue (self-contained) and never any of the above — preserving *dev-AI never writes/needs Obsidian* ([0001](0001-ticket-driven-dev-workflow.md)). On **self-containment**: the runner's DoR gate checks only *Status=Ready + non-empty acceptance criteria*, so in v1 it is held by the human at the *promote-to-Ready* gate. This is a **falsifiable** gap, not a permanent one: its **necessary conditions are mechanizable** (the Phase-1.5 linter — cited repo paths exist at `base_ref`; no unresolved external pointer in a build-critical field; the slice is present → fail loud), leaving only **sufficiency** (is the inlined context *enough* to build?) as judgment, which the deferred eval-harness scores (v2). The human gate shrinks as those land; it never has to carry the whole guarantee.

### What we adopt, inherit, and defer

**Adopt from external prior art** (patterns, not whole tools):
- the staged **spec → design → tasks funnel** and the hard **WHAT/WHY-spec vs technical-design separation** (Spec-Kit, Kiro);
- **EARS** acceptance-criteria grammar — testable, 1:1 with tests, readable by product + eng (Kiro);
- **architecture-before-decomposition ordering** and the **self-contained context bundle** as the task shape (BMAD);
- the **instruction-in / summary-out** handoff (Roo) and the **reasoning/execution model split** (Aider — strong model assesses, cheap model builds).

**Inherit from the internal corpus** (reconcile, don't re-derive):
- the **source-verified, file:line, "hidden-contract" audit method** (the `oc-*` audits) as the *method* for stage 3 — this is exactly "assess an existing codebase → technical RFC," and it's the answer to the gap external prior art left open;
- the **self-contained context-bundle** discipline (independently designed as BMAD's, corroborating it);
- the **read-back rule** — *"a mutation is complete when readable, not when the call returned"* (`harness-adapter-pattern`) — as the verification primitive for gates;
- hard-won constraints that shape v1: **CC does not reliably follow its own spec** and **prompt-level rules ≠ enforcement** → gates must be as *structural* as cheaply possible, and the things we cannot yet enforce structurally stay human-gated; **"economy is good, starvation is not"** → do not over-compress per-stage context; **stale design tasks already pile up faster than throughput** (`cleanup-review`) → decomposition discipline and the (deferred) eval gate are real needs, not speculation.

**Defer (named on the map, not built in v1):**
- the **per-stage evaluation harness** (completeness/buildability scoring) — the corpus pre-designs it (`knowledge-corpus-architecture`: decay × criticality × verification-recipe, *diffs-not-booleans*); v1 uses human review at each gate;
- **automation of the upper stages** (an agent owns a stage end-to-end) and the **file→wake-agent detection** it needs (`network-inventory`, `acp-orchestration`) — v1 is human-driven;
- the **memory-consolidation layer** (`memory-inventory`, `changelog-design`) — first-class in the harness, but its own track;
- the **weighted vote-gate** (Product/Dev/Risk) and the generic **state-machine engine** (`dev-process-design`) — [0001](0001-ticket-driven-dev-workflow.md) already stages weighted voting to "Stage 2+"; v1 keeps the existing two gates + three lightweight review gates.
- **splitting the amphibian** for large/complex features — separate **architectural assessment** (reads the feature RFC → writes the technical RFC; *the* boundary crossing) from **task decomposition** (reads the technical RFC on GitHub → files task Issues; GitHub-only, never crosses), so neither overloads a single agent. Airlock-preserving (only assessment crosses) and matches the stage-3/stage-4 (BMAD architecture-then-decomposition) seam; v1 keeps them as one amphibian role.

### One constraint v1 designs around now

A spawned subagent gets a deliberately **constructed, minimal context** — it does **not** inherit the parent session's loaded skills or the full catalogue (`capabilities-inventory`). This is *by design* (focus + token economy), not an immovable wall; whether a subagent can load a skill itself depends on the tools it is granted. Either way we **inline** a stage's skill/doc into the spawn payload — a self-contained payload is robust to however spawning happens to be configured, the *same* self-containment principle we apply to tasks. v1 is human-driven so this doesn't bite yet, but the templates are written as **self-contained inlinable bundles** so automating a stage is a drop-in, not a redesign.

---

## v1 scope (explicit)

**In:** the four stage **templates** (`factory/templates/`), the conventions above (homes, citations, self-containment, the handoff contract), the three lightweight human gates, the reconciliation in this RFC, and an **end-to-end proof on `yellow-robots`** (one real feature walks all stages to a reviewed PR).

**Out (this version):** any stage *automation*; the eval harness; the memory layer; the weighted vote-gate; the state-machine engine; detection/dispatch for the upper stages; per-artifact JSON schemas + a validate gate for upper artifacts (the lower pipeline keeps its existing schema gate).

**Pilot:** `yellow-robots` — it has a real `check_cmd` (`pytest tests/ -q`), is wired into the lower pipeline, and is the product itself. The design stays repo-agnostic; `website` joins once it has a build system.

---

## Alternatives considered

- **Adopt a tool wholesale (run Spec-Kit's CLI).** Rejected: it imposes its own command/namespace/opinions and isn't anchored to our Obsidian↔Issues split. We lift its *patterns* into our structure instead — zero new runtime, and it composes with the existing factory.
- **Build the corpus's full state-machine engine + weighted vote-gate now.** Deferred: heavier, slower to a first end-to-end thread, and [0001](0001-ticket-driven-dev-workflow.md) already sequences voting to Stage 2+. The corpus design is the target the deferred rungs aim at, not v1.
- **Automate the upper stages immediately.** Rejected: it inverts the proven order (scaffold first, automate when robust) and would build the least-trodden piece (existing-code assessment) before its shape is validated by use.

---

## Open questions

1. **Artifact homes — RESOLVED (2026-06-22).** Jose accepted the **split** (intent/spec/feature-RFC in Obsidian; technical RFC + task slices on the GitHub surface), governed by the one-way airlock + fail-loud accessibility — see [§Artifact homes & the Obsidian↔GitHub boundary](#artifact-homes--the-obsidiangithub-boundary-decided) above. Revisit only if/when stage automation makes a single-system home pay for itself.
2. **Feature-RFC home, long-term** — stays in Obsidian, or moves into the product repo's `docs/` next to the code it designs (version-controlled with it)? Still open; deferred.

## Consequences

- The single [0001](0001-ticket-driven-dev-workflow.md) arrow becomes four reviewable stages with loadable context — which is what lets an assisting agent own a stage, and what keeps the operator in control via cheap plan-gates rather than by doing every act.
- The **technical RFC** becomes the artifact that makes a task self-contained for codebase-fit; it is also the seam where our first real differentiator (existing-code assessment) is built, deliberately, on proven ground.
- v1 adds **no new *stage* automation** (no agent owns a stage; every gate stays human-held) — so it cannot regress the lower pipeline. The Phase-1.5 linters are deterministic checks that *inform* a gate, not automation of it. The deferred rungs (eval harness, stage automation, memory layer) each get their own RFC when their turn comes.
- The templates are written as self-contained inlinable bundles, so later automation is additive.
