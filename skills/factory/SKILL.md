---
name: factory
description: >-
  How an AI actually runs a change through the Yellow Robots dev factory — the operating manual, not
  orientation. Use when authoring or shipping any change on a YR repo: writing a product-spec / feature-rfc
  / technical-rfc / task, crossing the Obsidian→GitHub airlock, running the dev-runner, or invoking the
  gates (check_links, check_task, the repo check_cmd, the review verdict). Covers the iteration model, the
  document types, builder ≠ verifier, the deterministic gates, and the human gates. Reach for it whenever
  the work is factory-driven development — even if the user doesn't say "factory".
---

# The Yellow Robots dev factory — operating manual

The factory builds a software product the way software should be built: in **iterations**, each from
*intent* to *shipped code*, with **builder ≠ verifier** and **deterministic gates** that a human can trust.
A probabilistic LLM proposes; the machine-checked gate disposes.

For workspace layout and the repos, see the workspace **`AGENTS.md`** (org orientation). This skill is the
*how*. The full documentation model is the brain's **`01-conventions`**
(`04 projects/yellow-robots/factory/iterations/3-upper-pipeline/01-conventions.md`); the templates are in the
**factory repo** at `templates/` — they **ship inside the installed plugin too** (a git-sourced plugin is
the whole repo), so from the YR workspace *or* the plugin they're always at hand, no external checkout; the
deep rationale is **`factory/AGENTS.md`** + `factory/docs/rfcs/`.

## The documentation model (summary — full in `01-conventions`)

Two principles: **docs exist to enable the next iteration** (they store the *why* — the decisions and the
arguments), and **code is king** (when docs and code disagree, code is the present truth; docs are history).
So **shipping freezes the why** — a shipped spec/rfc is immutable; a later change is a *new* iteration, never
an edit of the old one.

The brain is organized as **iterations** — numbered folders in ship order inside a component's
**`iterations/`** folder (`<component>/iterations/1-…/`, `2-…/`). *Everything inside `iterations/` is an
iteration*, research included — absolute because it's scoped: **free-form brain** (business, legal,
marketing, brand assets, an ideas-backlog, and an optional **AGENTS.md-style orientation note**) lives
*alongside* `iterations/`, ungoverned. The orientation note is the design-brain's **working context**
(purpose/north-star, conventions, what's deliberately not built, open threads) — **context only, never an
index of iterations** (that's `ls` + each `01`, and it rots); hand-authored, optional, and it cites the
repo's `AGENTS.md`, never duplicates it.
Each doc is `NN-slug.md`: the **filename ordinal is its id** (product-spec = `01`), stable and order-visible
— no `id` property, no hub notes; the `01` product-spec is the iteration's front door.

**Frontmatter is a closed vocabulary** — every doc carries only `type · status · created · updated`, plus
`source_*` / `crossed_to` / `superseded_by` / `retired_reason` where they apply. **Never invent keys** (that's
how an AI grows hundreds of junk properties); anything else goes in the body. `title` is the H1, `stage`/`home`
are the `type`, the component/iteration are the folder — none are frontmatter.

**Spine** (in order): `product-spec —1:N→ feature-rfc —1:1→ technical-rfc —1:N→ task`.
**Floor = `product-spec → task(s)`** — the two rfc layers are *earned*, added only when a feature is worth
arguing or codebase-fit isn't obvious. The earned-test is the *default*, not a veto: if a human explicitly
asks for a layer it would skip, produce it marked *on request — not earned*, or push back recommending the
floor. **Supporting** types (in an iteration, off the spine): `research`
(a frozen investigation), `note` (the wildcard — marketing / legal / distilled how-X), `runbook` (ops).
Homes: `product-spec` + `feature-rfc` in **Obsidian**; `technical-rfc` (on the epic Issue) + `task` + PR on
**GitHub**. The boundary is crossed **once** — at feature-rfc→technical-rfc, or on the **floor** at
product-spec→task (the task cites its parent spec via `source_spec`) — and the downstream artifact
**cites, never copies**.

## Working with the vault (load these skills first)

The brain is an Obsidian vault — **load the obsidian skills before you touch it**:

- **`obsidian:obsidian-cli`** — read / search / create notes, set properties, list backlinks, and do
  **link-safe renames**. A rename must go through Obsidian so every backlink follows:
  `obsidian eval code="app.fileManager.renameFile(app.vault.getAbstractFileByPath('old/path.md'),'new/path.md')"`.
  **Never `mv` a vault file** — a filesystem rename silently breaks links across the whole vault (the archive included).
- **`obsidian:obsidian-markdown`** — wikilinks, callouts, frontmatter, embeds.
- **`obsidian:obsidian-bases`** — the `.base` views that filter/group the brain by `type`/`status`.

Writes are app-mediated (the `obsidian` CLI, or the Local REST API) — never a blind filesystem overwrite of a
file the app may hold open. Create new files freely. To **edit a doc's body** (e.g. trim a section), rewrite
the whole file *through the app* — `obsidian create path=… content=… overwrite`, or a REST `PUT` — which is
safe where a shell redirect is not; for a surgical change, GET-modify-PUT so untouched text stays
byte-identical. **Folders don't auto-create:** `create path=…` / `renameFile` need the parent to exist first
(`obsidian eval code="app.vault.createFolder('<component>/iterations/<n>-<slug>')"`).

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

## Run an iteration (the procedure)

1. **product-spec** — in the brain, from `templates/product-spec.md`. WHAT/WHY only, no tech; acceptance
   criteria in **EARS** (`WHEN … THE SYSTEM SHALL …`, or ubiquitous `THE SYSTEM SHALL …` for static
   content). `type: product-spec`, `status: draft` (→ `active` at the gate), named `01-<slug>.md` in
   `<component>/iterations/<n>-<slug>/`. **Develop the design *in* this doc** — open the `01` draft early and
   evolve WHAT/WHY there with the human, in Obsidian; don't brainstorm in the terminal and paste in a finished
   spec (the doc is where the thinking lives). Gate: *spec ready* (human).
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
5. **Promote to Ready** — *a human sets Status → Ready*. **Never an agent.** This is the input gate and the
   only dispatch signal.
6. **The lower pipeline builds it** — n8n poll → `dispatch.py` (fail-closed: it must name `owner/repo`) →
   `dev-runner.sh`: DoR gate → claim → fresh worktree off the base ref → implement → **independent** test
   (from the acceptance criteria) → `check_cmd` → **independent** review (`VERDICT: APPROVE`) → PR. Each
   stage is a separate cold `claude -p` (builder ≠ verifier, structurally). To run it by hand:
   `tools/dev-runner.sh <issue#> --repo <owner/name>`.
7. **Merge** — in v1, *a human reviews and merges*; native close → Status = Done. **This output gate is
   slated to retire next iteration** (see the **autonomous-merge** iteration in the brain): green deterministic gates
   **+** an independent reviewer stronger than the builder → the build merges itself. Merge ≠ ship — `main`
   is not production; deploy stays separate and attended.

## Migrating a legacy doc onto the model

An older doc that predates the model (or a blob mixing many types) is *migrated*, not rewritten:

1. **Enumerate & trace first** — every file, its `type`, every inbound/outbound link (vault-wide grep + the
   graph). Know what's a link-island before moving anything.
2. **Find the iteration boundary** — one coherent shipped change = one iteration; later "open items" are a
   *future* iteration (shipping freezes the why), never folded back.
3. **Split by type by "code is king"** — **present-state facts** (endpoints, IDs, schema, as-built) → a
   **pointer** to the code/live system (a mirror only drifts); **rationale not recoverable from code** (why
   this approach, trade-offs) → **kept verbatim**, rehomed to the feature-rfc; an audit → a frozen `research`;
   standing ops → a `runbook`.
4. **Retire the original — by which kind.** *Migrated* (content re-homed, decision unchanged) → **delete** it:
   its content now lives at the new path, the bytes survive in `.trash`/git; don't tombstone — nothing
   superseded it (a `renameFile` already *is* this). *Superseded* (a newer design invalidates it) → retire
   **in place**: `status: superseded` + `superseded_by`/`crossed_to`, the file stays for lineage; never `mv`.
   Rule of thumb: did a *decision change* (supersede) or did *content just move* (migrate)? — `superseded`
   needs a posterior invalidator.
5. **Gate the drafts** — stage in scratchpad, run `check_links` (and `check_task` for any GitHub task) to
   green, *then* execute the app-mediated ops.

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
- **The human owns the *input* gate.** Promote-to-Ready — deciding *what* gets built — is human, always; no auto-promote. The *output* gate (merge) is human in v1 but is being automated next iteration (autonomous-merge). The durable rule is *a human decides what to build*, not *a human merges every PR*.
- **PRs only.** The pipeline produces PRs. Host/ops/deploy work is done directly and attended — never as a Ready ticket.
- **Auth is human work.** Orgs/repos/tokens/scopes are the human's, never an agent's.
- **Code is king; shipping freezes the why.** A shipped product-spec/rfc is an immutable record — a later change is a *new* iteration, not an edit of the old.

## Onboard a new repo

Mechanical: clone it to `/opt/yellow-robots/<name>`; add **`.yr/factory.toml`** (`check_cmd`, `model`,
`base_ref`); ensure built deps exist (`.venv` / `node_modules`) so `check_cmd` runs in a worktree; make sure
the shared board can name `owner/<name>` (the dispatch routes by the issue's native repo, fail-closed). The
check gate is per-repo and grows with the repo.
