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
- **Legible failure, derivable recovery.** A failure surface (a merge record, a `Blocked` comment, a
  bounce) states the observed fact and the rule that judged it — never step-by-step cures. Recovery is
  not enumerated: failure modes are unbounded, and a cure catalogue dwarfs the docs while still missing
  the unforeseen. The docs teach the *model* — each gate's meaning, its record vocabulary, its design
  intent — so any agent, human or AI, derives recovery from the message plus the shipped docs alone: no
  session memory, no source archaeology.
- **Repo-agnostic.** Builds any registered repo via its manifest; the factory holds no product knowledge,
  no product holds a copy of the factory.
- **The seam is a contract, not a calibration.** Every repo-shape assumption the pipeline makes is a
  declared `.yr/factory.toml` key with a fail-closed default, or a written invariant a repo must meet —
  never an unstated inheritance from the factory's own repo shape.
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
| `tools/epic_gate.py` | the standing-approval sweep: promotes/self-closes epics, flags stranded claims |
| `tools/review_bundle.py` | the canonical, hashed per-run review bundle |
| `tools/check_task.py` | the DoR self-containedness gate for a Ready task |
| `tools/check_links.py` | the crossing-link (`source_*`) resolver/gate |
| `tools/check_model_refs.py` | the stale vault-doc-reference guard |
| `tools/check_supersession.py` | the supersession declaration/pair guard |
| `tools/promote.sh` | operator: promote a standalone task to Ready |
| `tools/watch_build.sh` | operator: poll a build to a terminal state |
| `tools/board.sh` | operator: one-shot org-wide board TSV |
| `tools/stage_usage.py`, `tools/textutil.py` | PR usage-summary comment; shared text helpers |
| `models.toml` + `tools/registry.py` | the model registry + loader/CLI |
| `tools/ledger.py` | the usage ledger: transcript archive, per-invocation row, per-model/report reads |
| `tests/` | the pytest suite |
| `qa/` | consumer quality content (e.g. `qa/lens.py`) — distinct from the platform machinery in `tools/` |
| `deploy/` | dispatch service unit, env example, n8n workflow, `DISPATCH.md` |
| `docs/rfcs/` | canonical RFCs |
| `skills/` | the factory skill (router + references) |
| `templates/` | upper-pipeline stage templates (spec, feature-rfc, technical-rfc, task, debt-census) |

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
- **Usage artifacts price in fresh-input equivalents.** Each stage files `usage-<stage>.json`; the census
  weights (`stage_usage.py`, epic #47 — input 1 · output 5 · cache-write 1.25 · cache-read 0.1) are
  exactly the Claude API price ratios, so weighted-total × the model's input $/Mtok = the build's shadow
  cost at API rates. Builds run on the host's Claude subscription — no per-token invoice exists; the
  shadow price is the decision metric (model choice, capacity headroom, cross-provider comparison).
- **The usage ledger informs, never gates** (epic yellow-robots/factory#204). `tools/ledger.py` appends
  one `yr-ledger-row/1` row per runner invocation to `$DEV_RUNNER_HOME/ledger/rows.jsonl` and archives
  each stage's session transcript into the run dir under a runner-owned retention cap — both fail-soft,
  never blocking, failing, or gating a run. `per-model`/`report` are read-only aggregations over those
  rows (depth: `skills/factory/references/pipeline.md` → "The ledger").
- **Attended operator sessions** run under the human's standing grants (settled 2026-07-03, dogfooded
  through it-6→10): cold design reviews with per-finding dispositions; the crossing's technical-rfc and
  decomposition review as its gate; epic Ready flips under a design's standing approval and standalone
  flips on explicit instruction — always record-before-flip on the trail. Never: set a design `active`,
  arm a repo, or hand-merge a PR (an armed repo merges via the evaluator; everything else is the
  human's click). Grants are per-agent and the human's to extend.
- **Auth is human work** — orgs/repos/tokens/scopes, never an agent.
- **Bench evidence and the shadow review seat** (epic yellow-robots/factory#161; depth:
  [`skills/factory/references/pipeline.md`](skills/factory/references/pipeline.md) → "The shadow review
  seat" / "The bench"). Three record schemas: `yr-bench-corpus/1` (`tools/bench_corpus.py`),
  `yr-bench-result/1` (`tools/bench_replay.py`), and `yr-verdict-diff/1` (`tools/verdict_diff.py`,
  pairing a gating review round with its own shadow round). The shadow review seat is dark by default
  behind two env keys, `YR_SHADOW_MODEL` / `YR_SHADOW_BASE_URL` (`tools/dev-runner.sh:46-51`) — both or
  neither, never gating. No shadow- or bench-derived PR trail comment ever carries a line-anchored
  `VERDICT:` itself (only the gating review's own comment does): a shadow or verdict-diff comment always
  blockquotes its transcript, so it can never be mistaken for the gating grammar.

---

## RFC index

`docs/rfcs/` holds the **implemented** RFCs (0001–0005). Unimplemented designs live in the Obsidian brain,
crossing over once built. The documentation model itself is
`skills/factory/references/documentation-model.md`.
