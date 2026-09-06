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
product-spec (or a legacy feature-rfc) `active`. Below that standing approval, flipping a governed epic to Ready,
promoting its next slice, and closing a finished epic are **mechanical**, fail-closed to the human on any
doubt (an invalid or missing record raises `Needs-info` rather than guessing). The cord-pull —
un-Readying an epic — remains the human's veto; a standalone task with no governing design keeps the
original per-task human promotion. The **output** gate — **merge the PR** — is **factory-executed for an
armed repo under fail-closed conditions** (`auto_merge = true`, sentinel clear): squash-merged with a
durable `YR-MERGE: MERGED` record, else `YR-MERGE: BLOCKED` and a stop for the human. The gate model as
ruled (it-30): the human's technical judgment sits at the technical-RFC decision surface, not at the PR;
the shadow phase is pre-arming qualification (once armed, no shadow merges); an attended hand-merge is
categorically refused; a repo **not yet armed** keeps the human click as a named transitional exception —
low-value by ruling, never the design. Arming is the norm for factory-built repos.

### Task lifecycle (state machine — RFC 0003)

State lives on native GitHub primitives, never labels: `Backlog → Ready → In Progress → In Review → Done`,
`Reason` = `Needs-info` / `Blocked`.

| Transition | Who | When |
|---|---|---|
| → Ready | **human** (standalone) / **epic-gate** (epic child) | standalone: DoR met, human decides; epic child: standing approval auto-promotes the next slice |
| → Done | native automation | PR merged (factory-executed for an armed repo, human otherwise) |

Remaining transitions and the board are RFC 0003's detail.

### Workflow types — who decides, and what each walks

*The type of a piece of work is decided at the moment its first artifact is created — the mining
session for a seed, the drafting session on the direct lane, the owner for attended work and debt
rounds; the session proposes the type on that artifact, and the deciding actor is the PM once it-36
ships, the owner until then.*

The seven types below name their machinery; they do not restate it. Each *machine-checked* cell names
only `id`s of `process.toml` transition rows, or — where the check is a gate's refusal rather than a
transition — the refusal's `records.toml` row name; the *prose* cell names the residue no machine
disposes.

| type | path | actors in order | steps (mandatory / optional) | gates and holders | machine-checked | prose |
|---|---|---|---|---|---|---|
| **full ladder (legacy)** | spec → feature-rfc → technical-rfc → task | owner (frame) · authoring session · cold reviewer · architect · owner (`active`) · crossing session · cold reviewer · epic gate · runner stages · evaluator · closing session | mandatory: cold review, fit check, `active`, technical-rfc review, DoR, the four cold stages, ship-walk / optional: feature-rfc (legacy) | spec-ready (owner), approve-RFC (owner, legacy), Ready (epic gate), merge (evaluator, or owner for an unarmed repo) | `design-doc.draft->active`, `task.backlog->ready.epic-flip`, `task.backlog->ready.epic-child`, `task.ready->in-progress.claim`, `task.in-progress->in-review.pr-open`, `pr.approved->merged.evaluator`, `task.in-review->done.native`, `task.ready->done.epic-close` | the type choice, the reviews' content, the ship-walk |
| **spec + technical-rfc (norm)** | spec → technical-rfc → task | owner (frame) · authoring session · cold reviewer · architect · owner (`active`) · crossing session · cold reviewer · epic gate · runner stages · evaluator · closing session | mandatory: cold review, fit check, `active`, technical-rfc review, DoR, the four cold stages, ship-walk / optional: none | spec-ready (owner), Ready (epic gate), merge (evaluator, or owner for an unarmed repo) | `design-doc.draft->active`, `task.backlog->ready.epic-flip`, `task.backlog->ready.epic-child`, `task.ready->in-progress.claim`, `task.in-progress->in-review.pr-open`, `pr.approved->merged.evaluator`, `task.in-review->done.native`, `task.ready->done.epic-close` | the type choice, the reviews' content, the ship-walk |
| **the floor** | spec → task(s) | owner · authoring session · cold reviewer · architect · owner · filing session · owner (promote) · runner · evaluator | mandatory: cold review, fit check, `active`, DoR, the four cold stages, ship-walk / optional: technical-rfc (when a task earns it) | spec-ready (owner), Ready (owner, per-task promote), merge (evaluator, or owner for an unarmed repo) | `design-doc.draft->active`, `task.backlog->ready.standalone`, `task.ready->in-progress.claim`, `task.in-progress->in-review.pr-open`, `pr.approved->merged.evaluator`, `task.in-review->done.native` | the type choice |
| **direct seed-to-task lane** | seed → drafted task → independent adversarial review on the trail → architect fit check → file with the task-delivered stamp → human promote | drafting session · independent reviewer · architect · owner (promote) · runner · evaluator | mandatory: adversarial review, fit check, task-delivered stamp, DoR, the four cold stages, ship-walk / optional: none | Ready (owner, per-task promote), merge (evaluator, or owner for an unarmed repo) | `task.backlog->ready.standalone` (its guard demands the gates record) | the review's and fit check's content, the type choice |
| **attended host and ops** | owner instruction → attended session → the runbook's executed record | owner · attended session | mandatory: the runbook's executed record / optional: none — no ticket, no PR | none — owner instruction is the authority; no ticket, no PR | `sentinel.clear->thrown.throw`, `sentinel.thrown->clear.clear`, `arming.disarmed->armed.arm`, `arming.armed->disarmed.unarm`, `shared-ref.push.instructed` where they apply | everything else |
| **attended gate evolution** | `YR-GATE-TOUCHING` line → epic gate refuses promotion → attended build → independent review → owner's merge click | owner · epic gate (refusal) · attended session · independent reviewer · owner (merge click) | mandatory: `YR-GATE-TOUCHING` line, attended build, independent review, owner's merge click / optional: none | epic gate (refuses a gate-touching child's promotion), merge (owner's click) | no transition — the gate's refusal is a record, `YR-EPIC-GATE: gate-touching` (`records.toml:171`), which fires for a Task-typed child carrying the line (`tools/epic_gate.py:1109`); an untyped child draws `not-a-task` first (`:1090`) | the build, the review, the click |
| **the debt round** | census → debt-round spec → debt epic → prune guard → close-hold → round-close duties, per `skills/factory/references/debt-rounds.md` | owner (census) · authoring session · owner (`active`) · epic gate · runner stages · evaluator · closing session | mandatory: census, debt-round spec, prune guard, close-hold, round-close duties / optional: none | spec-ready (owner), Ready (epic gate), close-hold (epic gate), merge (evaluator, or owner for an unarmed repo) | `design-doc.draft->active`, `task.backlog->ready.epic-flip`, `task.ready->done.epic-close` | the census's judgment |

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
  only when unpushed). The runtime carve-out — eight runtime surfaces, refreshed by, may lawfully execute
  from a mutable working tree, declared (`tools/provenance.py`'s `SURFACES`) vs named:

  | # | Surface | Refreshed by | Mutable working tree | Declared / named |
  |---|---|---|---|---|
  | 1 | Build-host checkout (runs `dev-runner`, `epic-gate`) | Deploy act | Lawful | Declared |
  | 2 | Resident `dispatch` process | Unit restart | Holds its import closure — a pull is not a deploy for it | Declared |
  | 3 | Attended workspace checkout (`attended-session`) | Attended fast-forward | Lawful | Declared |
  | 4 | Plugin/skill cache (`attended-session`, cache half) | Plugin install act | Immutable between installs | Declared |
  | 5 | Org-docs clone | Attended pull | N/A — docs, not code | Named |
  | 6 | Scheduler's imported workflow definitions | Attended re-import | N/A — config, not code | Named |
  | 7 | Installed unit file and its environment | Attended edit | N/A — config, not code | Named |
  | 8 | Build environment | Attended provision | N/A — config, not code | Named |

  Long-lived-process semantics: a resident process (row 2) holds its import closure for its whole
  process life, so a pull under it changes nothing it states — only a restart is a deploy for it.
- **One task = one PR.** Too big? Split into sub-issues.
- **Docs are consolidated, not accreted.** Update/merge/trim the canonical doc, don't pile on a new one —
  this file is that discipline applied to itself.

---

## Repo map

| Path | What |
|---|---|
| `tools/dev-runner.sh` | the staged build pipeline |
| `tools/stage_lib.sh` | the `claude -p` stage harness (`run_stage`, quota hold/pool credential selection, transcript archive + usage capture, refusal/blocked-reason classification, `verdict_line`, `resolve_role`), sourced by `dev-runner.sh` after `SELF_DIR` — one library, byte-identical behaviour (it-36 slice C) |
| `tools/board_plumbing.py` | the one home for the board's plumbing: its project/field/option identifiers, its single field write, and its single per-issue project-item read + selection rule (consumed by the runner, the epic gate and the three operator scripts) |
| `tools/merge_shadow.py` | merge-decision evaluator + shadow-completion |
| `tools/dispatch.py` | n8n's build-trigger endpoint (RFC 0004) |
| `tools/provenance.py` | the one self-locate helper: `SURFACES`, `factory_commit(root)`, `statement(root)` (the `commit: <sha>` form), `plugin_cache_root()`, `dispatch_statement_path()` — every declared runtime surface's version statement runs through here, no emission site shells out to `git` on its own (it-33 slice 2) |
| `tools/drift.py` | the one drift alarm: two moments (attended session start via `compile_slice.py:position()`, each sweep via `epic_gate.py:main()`), per-host population of `provenance.SURFACES` — names every readable surface trailing `origin/main` and every surface it cannot read from that host; advisory, loud, never a gate (it-33 slice 4); slice 6 adds `deploy_record_findings`, the sweep-only comparison of the deploy trail's latest `YR-DEPLOY` record against each named build-host surface's own live statement |
| `tools/deploy.sh` | the scripted attended act (it-33 slice 6): quiescence probe (refuses on a held build/sweep lock or a live run dir) -> `git pull --ff-only` -> `systemctl --user restart dispatch` iff the pull touched the dispatcher's own import closure -> the runbook's post-deploy checks -> one `YR-DEPLOY` record on yellow-robots/factory#464. No automatic trigger; `--dry-run` probes and reports only |
| `tools/epic_gate.py` | the standing-approval sweep: promotes/self-closes epics, flags stranded claims; the close arm holds a finished non-debt epic until its mandated close records exist (`YR-CLOSE-HOLD`, it-31 slice 9) |
| `tools/design_resolver.py` | the governing-design resolver (it-31 slice 4): parses an epic body's Source line, reads the design's status through the vault — the epic-flip guard's evaluator, one seam |
| `tools/release.py` | the validation-gated, git-native skill release act (it-31 slice 7, ruling 6): refuses unless the declared version's tree is unchanged since its bump commit (it-33 slice 5), the human's manual is current with the surfaces it renders or recorded unaffected (it-32 slice 5), the model loads at the commit, server CI is green there (the squash-source PR's tree-equal head), and build/ carries no drift — then annotated tag `skill/vX.Y.Z` + GitHub Release carrying `YR-RELEASE`; backfill mode types the pre-tool pair; `--test-mode` writes nothing |
| `tools/review_bundle.py` | the canonical, hashed per-run review bundle |
| `tools/check_task.py` | the DoR self-containedness gate for a Ready task |
| `tools/check_links.py` | the crossing-link (`source_*`) resolver/gate |
| `tools/check_model_refs.py` | the stale vault-doc-reference guard |
| `tools/check_supersession.py` | the supersession declaration/pair guard |
| `tools/nit_harvest.py` | the census's nit-harvest arm: recurrence-ranked duplication clusters from the PR comment trail |
| `tools/promote.sh` | operator: promote a standalone task to Ready; an epic-flip's machinery arm (it-36 slice G) beside the attended one — under `YR_MACHINERY` AND the App identity (`YR_GH_APP_SLUG`), never `YR_MACHINERY` alone — flips through the `epic-flip.machinery` transition (the owner's own `YR-TRIAGE` `go` disposition licenses it), `WHO` from the App slug, never `gh api user` |
| `tools/watch_build.sh` | operator: poll a build to a terminal state |
| `tools/board.sh` | operator: one-shot org-wide board TSV |
| `tools/stage_usage.py`, `tools/textutil.py` | PR usage-summary comment; shared text helpers |
| `models.toml` + `tools/registry.py` | the model registry + loader/CLI |
| `records.toml` + `tools/records.py` | the record registry: every machine-parsed trail grammar in one home — emitter, the typed `emitted_by` actor classes, readers, surfaces, grammar mode, the `YR-` marker as one named constant — + loader/CLI; lane mandates COMPILE from the process model, never from registry data (it-30) |
| `process.toml` + `tools/process.py` | the process model and its engine: machines/transitions/guards/stores/bindings with `stance` and `enforcement` DERIVED (no field to author), the loader's fail-closed rule set (the load-time tier gates via the suite, per ruling 1), the four compiled surfaces under `build/`, the decision path the walls run, the journal, and the close report (it-30) |
| `tools/predicates.py`, `tools/sources.py`, `tools/acts.py` | the engine's three seams: the closed predicate vocabulary (pure, tri-state, no `__bool__`), the ONLY I/O home (every fetch bounded, stubbed in tests), and the act normalizer + typed matcher vocabulary (no substring, no regex) (it-30) |
| `build/` | the compiled surfaces — walled-act map, lane mandates (with the version table row), static slice, conformance vectors — `GENERATED from process.toml`, committed so a model diff shows its consequences; freshness is `process.py check --drift`, advisory-loud by ruling |
| `tools/check_trail.py` | the trail-shape detector: presence + grammar of a lane's mandated records, model-compiled mandates + must-not-carry, surface-dispatched, content-blind, version-scoped via `--scope-created` — walk/census tooling, advisory-tier (it-30) |
| `tools/compile_slice.py` + `hooks/` | the attended lane's delivery: the bounded slice compiled from the canon tables (never hand-edited) + the plugin's SessionStart hook composing the runtime position at delivery, loud-non-blocking (it-30) |
| `tools/wall.py` | the attended lane's walls, rebuilt as a loop over the process model's compiled rows: the PreToolUse/Stop hook shim over `process.decide`, a non-loading model answered LOUD and non-blocking, the promote wall delegating to the engine's transition-check, and the journal view the round record reads (it-30) |
| `tools/ledger.py` | the usage ledger: transcript archive, per-invocation row, per-model/report reads; fail-soft refusal rows from `gate()` and the `crossover` emitter for `YR-CROSSOVER` (it-31 slice 9) |
| `tools/bg_scan.py` | scans an archived stage transcript for an unresolved background-task conversion |
| `tools/bench_corpus.py` | derives the replayable bench corpus from a repo's merged task PRs |
| `tools/bench_replay.py` | sealed-checkout replay harness + deterministic grading, plus the live candidate replay driver |
| `tools/bench_report.py` | bench evidence report |
| `tools/rank.py` | the Bases rank reader over the ideas folder: `rank list` / `rank top --n N`, reproducing `ideas-backlog.base`'s `formulas.rank` verbatim in meaning over `status == "open"` seeds read through `textutil.split_frontmatter`, descending; a seed missing `value` or `effort` has no rank and is listed as such; an `out_of_subset` finding is listed, never dropped (it-36 slice B) |
| `tools/strategy.py` | the strategy doc's fenced block reader: parses a `note`'s fenced `yr-strategy` TOML block into themes, constraints, kpi_targets, loop_budget_usd_per_week and factory_cap, via `tomllib`; a missing or malformed block is a loud finding (it-36 slice B) |
| `tools/gh-app` | the on-demand GitHub App installation-token wrapper behind `GH_BIN` (it-36 slice E): mints a JWT (RS256 via `openssl dgst -sha256 -sign`, the stdlib-only convention's one named carve-out), mints/caches/re-mints the installation token (under five minutes to expiry), then execs the real `gh` under it — the PM acts on every native surface under the App's own identity, never the owner's |
| `tools/design_gate.py` | the design sweep (it-36 slice E): posts one `YR-TRIAGE-PACK` comment per decision-ready seed to a repo's triage issue (rank from `tools/rank.py`, cost from `tools/sources.py:pr_usage` × the seed's S/M/L effort factor, theme from `tools/strategy.py`); trusts a `YR-TRIAGE` disposition only from `YR_OWNER_LOGIN`, last record per seed wins; a reversal or a withdrawn governing epic kills the in-flight design; idles loudly (no theme, loop budget exhausted -> `YR-ESCALATION`, or the vault interface down) rather than substitute factory work; spawns `tools/design-runner.sh` for the next licensed `go`, one design in flight per repository |
| `tools/design-runner.sh` | the PM's own stage runner (it-36 slice E), sourcing `tools/stage_lib.sh`: `product` (drafts a spec from the seed + strategy doc + `skills/factory/templates/product-spec.md`), `adversarial` (`skills/factory/references/reviewing.md`'s cold-review standard, `VERDICT:`), `fold` — each leaving its own `kind: design` row in the PM instance's ledger; drafts only, never a vault write (a later slice's own duty) |
| `tools/design-review-runner.sh` | the PM's own review-stage runner (it-36 slice F), a separate invocation from `design-runner.sh` spawned once drafting has exited: `fit` (the architect's spec-ready moment, typed as `YR-DESIGN-FIT`, alongside the already-decided `YR-DESIGN-REVIEW`), `arch` (the architect's own mandate — abstraction/pattern/libraries/language/boundaries, >=1 argued alternative, a `fit`/`refit`/`block` verdict and an ADR; a `block` earns exactly one fold-and-re-review before the draft returns to the triage issue, unactivated), `activate` (asks the engine's `transition-check design-doc.draft->active`, writing only on exit 0 through `tools/vault_api.py`) |
| `tools/vault_api.py` | the machinery's one client of the vault's REST interface (it-36 slice F): read, whole-body write and a frontmatter-key patch over `127.0.0.1:27123`, keyed by the non-empty `YR_VAULT_API_KEY`, every write read back through the file; `VaultUnreachable` is the one loud-stop failure — a refusal, an unreachable app, or a read-back mismatch, never a retry into a filesystem write |
| `tools/cross.py` | the crossing's deterministic gates + filing act (it-36 slice G): `check_links` on the technical-rfc draft, `check_task` (`--base-ref origin/main`) on every RUNNER-BUILT slice only, the architecture review's verdict gating filing itself (a `block` refuses; `fit`/`refit` renders human-facing verdict/alternative prose onto the technical-rfc body — never the raw transcript — and, given `architecture_home`/`adr_slug`/`adr_title`, writes the real ADR through the vault client and appends `YR-ARCH-REVIEW` to the design doc's own text, the vault-doc surface, never the issue trail); only then the epic (`gh issue create` + `updateIssue` to Type=Feature + `gh project item-add`), one sub-issue per slice (`addSubIssue`, Type=Task on runner-built, non-escalated slices only), the tool-emitted `YR-EPIC-APPROVAL` (`who` = the App slug), `crossed_to` through the vault client, and the filed epic number + the crossing's own seed written back onto the PM config (`design_gate.update_pm_config_entry`) so a later `promote.sh` machinery flip can resolve it; a slice declaring `Declares: external dependency <name>` / `Declares: data migration` files UNTYPED (the epic-gate's own `not-a-task` hold) and carries a `YR-ESCALATION` comment — nothing else waits on it; a mid-filing exception is caught and reported as a partial `filed` result, never a traceback |
| `tools/cross-runner.sh` | the crossing's own stage runner (it-36 slice G), sourcing `tools/stage_lib.sh`: `cross-draft` (the technical-rfc + one task body per anticipated slice, split by `tools/cross.py split-draft`), the cold technical-rfc review (`VERDICT: APPROVE`/`REQUEST CHANGES`, one fold-and-re-review), `arch` (one fold-and-re-review on `block`, design-review-runner.sh's own pattern) — then `git fetch origin` on the target repo's own shared-clone checkout and `tools/cross.py file` |
| `tests/` | the pytest suite |
| `qa/` | consumer quality content — the advisory lens (`qa/lens.py`) and the blocking cardinality guards (`qa/cardinality.py` + its rule set `qa/cardinality.toml`); distinct from the platform machinery in `tools/` |
| `deploy/` | dispatch service unit, env example, n8n workflow, `DISPATCH.md` |
| `docs/rfcs/` | canonical RFCs |
| `skills/` | the factory skill (router + references) |
| `skills/factory/templates/` | upper-pipeline stage templates (spec, feature-rfc, technical-rfc, task, debt-census) |

---

## Conventions

- **Branches:** `task/<issue#>-<slug>`. **Check command (attended workspace checkout):**
  `.venv/bin/python -m pytest tests/ -q` — the checkout's own venv. A cut build worktree carries no
  `.venv`: the build gate runs the manifest's `check_cmd` (bare `pytest tests/ -q`), and build stages
  use `python3 -m pytest` / bare `pytest` (the manifest's `stage_conduct` says so where it counts).
  **An attended session on the workspace host runs targeted suites only** (the files its change
  touches); the full suite is server CI's to certify on the PR head — a full local run is too costly
  for the workspace VPS and duplicates the certification CI performs anyway (owner ruling
  2026-08-09, on the #428 round; two full runs that day died of host contention at 35%).
- **Workspace & manifest:** checkout is `$YR_WORKSPACE/<name>` (default `factory/../..`); per-repo
  `.yr/factory.toml` sets `check_cmd`, `model`/`review_model`, `base_ref`, `auto_merge` (default false),
  `merge_ci_timeout` (the merge evaluator's bounded in-flight CI wait in seconds; `MERGE_CI_TIMEOUT` env
  override, default 1200), precedence env > manifest > default. `auto_merge`/`merge_ci_timeout` both
  re-read the base ref's tip at decision time, never a start value; a `merge_ci_timeout` present but not
  a positive integer blocks fail-closed (`timeout_invalid`) rather than silently falling back to the
  default. `server_ci` (`required` | `none`, default `required`; issue #274) declares the repo's
  server-CI stance, also re-read at decision time: `none` passes the evaluator's `ci_green` condition by
  declaration (`not_required_declared`, never a bare empty rollup), but `server_ci = none` on an armed
  repo (`auto_merge = true`) is a conflicting pair — no independent CI to gate an autonomous merge on —
  and refuses fail-closed (`server_ci_none_armed`) naming both declarations; any other declared value
  blocks fail-closed naming the rejected value. `check_cmd` is **required** (no built-in fallback; issue
  #275): required-ness is judged on the manifest alone — an undeclared key refuses the work before
  claim/worktree/any stage, naming the missing key, regardless of any environment `CHECK_CMD`; where the
  manifest DOES declare `check_cmd`, an environment `CHECK_CMD` still overrides it for the session, and
  the run's log names the effective source. `check_timeout` (the local gate's bounded window in seconds,
  default 1200; `CHECK_TIMEOUT` env override; issue #308) is resolved once, at this same start-of-run
  point, precedence env > manifest > default, and a manifest value present but not a positive integer
  bounces `Needs-info` naming the rejected value before any claim, never silently defaulting. A gate is
  judged by LIVENESS, not the absolute clock (issue #314): `check_idle_timeout` (default 300s;
  `CHECK_IDLE_TIMEOUT` env override) shares `check_timeout`'s resolution point, precedence, and
  malformed-value bounce discipline — it is the window a check/lint/lens invocation's log (including the
  armed re-green) may sit at zero byte growth before the wrapper kills its process group, an OBSERVED
  expiry (never inferred from the exit code alone) disposing as a code failure whose tail names the idle
  duration, total elapsed, and both windows, through that site's existing repair/Block path, the lens
  folding it into its advisory note instead. `check_timeout` expiring while output is STILL flowing no
  longer kills anything: it is a one-time loud advisory — a run-log line plus one issue-trail comment
  naming the process group, elapsed time, both windows, and that output is flowing — and the run
  continues; the advisory only informs, it never gates (owner ruling 2026-07-29: a chatty live loop holds
  its slot until a human looks). `test_paths` / `artifact_globs` (issue #273)
  let a repo declare its own shape rather than conform to the factory's own: `test_paths` (default `["tests/"]`) is
  the tester stage's only legal write surface, `artifact_globs` (default `["__pycache__/", "*.pyc"]`) is
  the boundary guard's build-artifact forgiveness set — both TOML arrays of non-empty, repo-relative
  strings (none absolute, none containing `..`), a rejected declared value blocking fail-closed naming
  the value, never silently falling back to the default. `stage_conduct` (issue #312) is a TOML array of
  non-empty strings — a repo's own per-command conduct numbers (real durations, this repo's timeout
  values; the generic conduct rules already live in the stage charter, post-#307, and are never
  restated) — delivered to every `claude -p` stage appended to the task prompt on stdin, under a
  one-line header naming the source manifest, never on argv (issue #121's channel contract); a declared
  line containing one of the shared test harness's four routed stub literals
  (`tests/harness/contract.md`: `TESTER`, `REVIEWER`, `tests FAIL`, `REQUESTED CHANGES`) is rejected at
  parse time, fail-closed, naming the offending line; absent key, byte-identical stage prompts to today
  (pinned). The **sentinel** kill switch (host file) blocks any merge if present — see
  [`deploy/DISPATCH.md`](deploy/DISPATCH.md).
- **Lint and lens keys.** `lint_cmd`/`lint_fix_cmd` (issue #213) and `lens_cmd` (issue #214) are
  manifest keys the runner reads the same way as `check_cmd` above; what each runs, when, and how a
  lint failure repairs is [`skills/factory/references/gates.md`](skills/factory/references/gates.md)
  → the gate table and *Judgment points* (`:17-63`), not restated here.
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
  exactly the Claude API price ratios, so (weighted-total × the model's input $/Mtok) / 1,000,000 = the
  build's shadow cost in true dollars at API rates (issue #313 — the un-divided product is µ$, not $).
  Builds run on the host's Claude subscription — no per-token invoice exists; the shadow price is the
  decision metric (model choice, capacity headroom, cross-provider comparison).
- **The usage ledger informs, never gates** (epic yellow-robots/factory#204). `tools/ledger.py` appends
  one `yr-ledger-row/1` row per runner invocation to `$DEV_RUNNER_HOME/ledger/rows.jsonl` and archives
  each stage's session transcript into the run dir under a runner-owned retention cap — both fail-soft,
  never blocking, failing, or gating a run. A new row carries `cost_unit: "usd"` (true dollars); a reader
  treats an absent `cost_unit` as the pre-#313 µ$ era and re-derives the true cost from that row's own
  stage inputs, read-time, never a file rewrite — a mixed-era `rows.jsonl` stays correct forever.
  `tools/dev-runner.sh` also writes a run-dir `gate-durations.json` (one entry per check/lint/lens
  invocation: site, elapsed seconds, disposition), which `append` folds into the row as a top-level
  `gates` list. `per-model`/`report` are read-only aggregations over those rows (depth:
  `skills/factory/references/pipeline.md` → "The ledger").
- **Attended operator sessions** run under the human's standing grants (settled 2026-07-03, dogfooded
  through it-6→10): cold design reviews with per-finding dispositions; the crossing's technical-rfc and
  decomposition review as its gate; epic Ready flips under a design's standing approval and standalone
  flips on explicit instruction — always record-before-flip on the trail. Never: set a design `active`,
  arm a repo, or hand-merge a PR (an armed repo merges via the evaluator; everything else is the
  human's click). Grants are per-agent and the human's to extend.
- **Auth is human work** — orgs/repos/tokens/scopes, never an agent.
- **Bench evidence** (epic yellow-robots/factory#161; depth:
  [`skills/factory/references/pipeline.md`](skills/factory/references/pipeline.md) → "The bench"). Two
  record schemas: `yr-bench-corpus/1` (`tools/bench_corpus.py`) and `yr-bench-result/1`
  (`tools/bench_replay.py`).

---

## RFC index

`docs/rfcs/` holds the **implemented** RFCs (0001–0005). Unimplemented designs live in the Obsidian brain,
crossing over once built. The documentation model itself is
`skills/factory/references/documentation-model.md`.
