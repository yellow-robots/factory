# Upper-pipeline templates

The stage artifacts for the factory's **upper pipeline** (product intent → buildable task), per
**RFC 0005** (the upper-pipeline design — in the Obsidian factory project while in-flight; commits to
`docs/rfcs/` once accepted). v1 is
**human-driven-with-agent-assist**: a human (or an agent the human drives) fills each template; a human
reviews at each gate. Automation of a stage is earned later, once it's proven.

## The workflow

| Stage | Template | Produces | Home | Gate |
|---|---|---|---|---|
| 1 product intent → spec | `product-spec.md` | spec (EARS, WHAT/WHY only) | Obsidian product brain | *spec ready* |
| 2 feature RFC | `feature-rfc.md` | the design handover | Obsidian product brain | *approve RFC* |
| 3 architectural assessment | `architecture-brief.md` | codebase-fit brief + per-task slices | epic Issue (the amphibian crossing); slices → Issues | *review the brief* |
| 4 task decomposition | `task.md` | Ready DoR task-Issues | GitHub Issues | *promote to Ready* |
| 5 build → PR | *(the factory)* | code | the lower pipeline | *merge* |

The two existing gates (*promote to Ready*, *merge*) are the bottom of the ladder; stages 1–3 each add
one lightweight "review the plan" gate above them.

## Conventions

- **Self-contained handoff** — each stage hands the next a *complete* artifact; the downstream worker
  never reaches back into the upstream's context. The architecture brief's slice is what makes a task
  self-contained for codebase-fit (a dev never opens Obsidian — the DoR form mandates this).
- **Traceability by citation** — every artifact cites its source: spec→intent, RFC→spec, brief→RFC+exact
  files, task→RFC+slice, PR→task (`Closes #`). Obsidian artifacts use block-refs; tasks use Issue links.
  Drift becomes detectable.
- **One-way airlock (Obsidian↔GitHub)** — the boundary is crossed *once*, at the RFC→brief seam, by the
  **amphibian agent** (reads the RFC from the vault, writes the brief on the epic Issue; cites, never
  copies). Above it Obsidian; below it GitHub, repo-local. Crossing-links are **fail-loud** — an
  unresolved `source_*` ref stops the workflow (scoped to pipeline artifacts, not the whole vault).
- **Typed frontmatter** — each artifact's properties live in YAML frontmatter (Obsidian-typed:
  text/list/number/date), enabling validation now and promotion to GitHub fields later (`status`,
  `stage`, `source_*`, `target_repo`, `size`, `model`). A `source_*` link's **format follows its
  target's home**: a `[[wikilink]]` when the target is in Obsidian, a URL/`#issue` when it's on GitHub.
  `check_links.py` resolves both via our tooling (not the platform's renderer), so a wikilink is correct
  even inside a GitHub-homed artifact.
- **Gates review the plan, not the output** — approve the outline before a stage commits; cheap control.
- **Self-contained = inlinable** — templates are written so a stage's content can later be inlined into a
  spawned agent's payload (spawned/minimal-mode contexts drop the skills catalogue), so automating a
  stage is a drop-in, not a redesign.

## A note on names

A **feature RFC** (these templates) is a product-feature design that spawns task-Issues — distinct from
the factory's own **technical RFCs** (0001–0005) in `docs/rfcs/`. And "factory" here means the **dev factory** (this repo),
not the robot-manufacturing "factory" of the product vision.
