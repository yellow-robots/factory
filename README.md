# Yellow Robots — dev factory

The **build machinery** for Yellow Robots: it takes a *Ready* ticket to a *reviewed PR*, autonomously,
across any YR repo. The robot (a probabilistic LLM) proposes; deterministic gates dispose.

This is **infrastructure**, deliberately separate from the product repos it builds (`yellow-robots`,
`website`, `gilda`). Each product repo is self-contained and declares *how* to build itself; the factory
supplies *the pipeline*.

**New here?** Read **[AGENTS.md](AGENTS.md)** — how the factory works and the SDLC it runs. A human
operator running the factory day to day should read **[docs/manual.md](docs/manual.md)** instead — the
verbs, the workflow types, and the trail records, each by citation. The *why*, in depth, is in
[`docs/rfcs/`](docs/rfcs/).

## What's here

| Path | What |
|---|---|
| `tools/dispatch.py` | the host endpoint n8n calls to fire a build (RFC 0004) |
| `tools/provenance.py` | the one self-locate helper: every declared runtime surface's `commit: <sha>` version statement runs through here |
| `tools/drift.py` | the one drift alarm, two moments (attended session start, each sweep): names every readable surface trailing `origin/main` and every surface it cannot read from that host — advisory, never a gate |
| `tools/deploy.sh` | the scripted attended deploy act: quiescence probe, `git pull --ff-only`, conditional `dispatch` restart, post-deploy checks, one `YR-DEPLOY` record — no automatic trigger |
| `tools/dev-runner.sh` | the staged pipeline: gate → implement → independent test → check → independent review → PR (RFC 0002) — builder ≠ verifier, by construction |
| `tools/stage_lib.sh` | the `claude -p` stage harness, sourced by `dev-runner.sh` |
| `tools/bg_scan.py` | scans an archived stage transcript for an unresolved background-task conversion |
| `tools/merge_shadow.py` | the merge-decision evaluator + shadow-completion |
| `tools/board_plumbing.py` | the one home for the board's identifiers, its single field write, and its single per-issue project-item read + selection rule |
| `models.toml` + `tools/registry.py` | the model registry (data) + its stdlib loader/CLI |
| `records.toml` + `tools/records.py` | the record registry: every machine-parsed trail grammar in one home (data) + its stdlib loader/CLI |
| `tools/check_trail.py` | the trail-shape detector: are a lane's mandated records present and well-formed, content-blind |
| `tools/compile_slice.py` + `hooks/` | the attended lane's delivered slice (compiled from the canon tables) + the session-start delivery hook |
| `process.toml`, `tools/process.py` + `build/` | the process model (machines · transitions · guards · stores · bindings; stance and enforcement derived, never authored), its engine, and the compiled surfaces |
| `tools/predicates.py`, `tools/sources.py`, `tools/acts.py` | the engine's three seams: pure tri-state predicates, the one I/O home, the act normalizer + typed matchers |
| `tools/wall.py` | the attended lane's walls: a loop over the model's compiled rows — the hook shim over `process.decide`, refusals that name the rule, the close report, the journal |
| `tools/ledger.py` | the usage ledger: transcript archive, per-invocation row, per-model/report reads, fail-soft refusal rows + the typed crossover verdict |
| `tools/stage_usage.py`, `tools/textutil.py` | the PR usage-summary comment; small shared text helpers |
| `tools/bench_corpus.py`, `tools/bench_replay.py`, `tools/bench_report.py` | the bench corpus, candidate replay, and report aggregation |
| `tools/rank.py`, `tools/strategy.py` | the Bases rank reader over the ideas folder; the strategy doc's fenced `yr-strategy` TOML block reader |
| `tools/gh-app`, `tools/design_gate.py`, `tools/design-runner.sh` | the App-token wrapper behind `GH_BIN`; the design sweep (triage packs, `YR-TRIAGE` licensing, reversal/withdrawal stop, idle-loudly, spawn); the PM's product/adversarial/fold stage runner |
| `tools/design-review-runner.sh`, `tools/vault_api.py` | the PM's own review-stage runner (fit, arch, activate) spawned once drafting exits; the machinery's one client of the vault's REST interface, every write read back through the file |
| `tools/cross.py`, `tools/cross-runner.sh` | the crossing's deterministic gates + filing act (`check_links`/`check_task`, the architecture review's verdict, the epic and sub-issues filed by tool with their types, `YR-EPIC-APPROVAL`, `crossed_to` through the vault client); its own stage runner (cross-draft, the cold technical-rfc review, the architecture review) |
| `tools/round_record.py`, `tools/close-runner.sh` | the close stage's own records module (`YR-ROUND-RECORD`'s four counts + per-surface `deployed`, `YR-CROSSOVER` from PR usage vs. the strategy theme budget — honest when not every linked PR priced, the close-walk's living-reference edit applied through the vault client, `YR-SHIP-WALK`, idempotent); its own stage runner (an idempotence check, `close-walk`, a supersession sweep, then `ship-walk`/`round-record`/`crossover` in order) — spawned by `design_gate.py`'s close sweep when an epic carries `YR-CLOSE-HOLD`, its own repo's `component-root`/`strategy-doc` threaded on argv |
| `tools/changelog.py`, `tools/notify.py` | what shipped is published (it-36 slice I, #474): the changelog-fragment + technical-rfc + round-record compiler (`CHANGELOG.md` + a fenced `yr-changelog` release-body block) and the per-stakeholder delivery tool (`[[stakeholders]]`'s telegram/webhook/issue-comment/github-release channels, signed, then `YR-CHANGELOG`) |
| `deploy/` | the dispatch systemd service, the n8n workflows (including `n8n-changelog-telegram.json`), and switch-on notes (`DISPATCH.md`) |
| `docs/rfcs/` | implemented technical RFCs — 0001 workflow, 0002 runner, 0003 task state, 0004 dispatch, 0005 upper-pipeline. Unimplemented designs live in the Obsidian brain. |
| `tests/` | pytest suite (stubbed: no live LLM, no network) |
| `qa/` | consumer quality content — the advisory lens (`qa/lens.py`) and the blocking cardinality guards (`qa/cardinality.py` + its rule set `qa/cardinality.toml`); distinct from the platform machinery in `tools/` |
| `tools/epic_gate.py`, `tools/design_resolver.py`, `tools/review_bundle.py`, `tools/check_task.py`, `tools/check_links.py`, `tools/check_model_refs.py`, `tools/check_supersession.py` | the standing-approval sweep; the governing-design resolver; the hashed review bundle; the DoR, crossing-link, stale-reference, and supersession gates |
| `tools/release.py` | the validation-gated, git-native skill release act: annotated `skill/vX.Y.Z` tag + GitHub Release carrying the typed record, refusing on failing validation; beside it, the `it/<n>` iteration-release family (it-36 slice I) |
| `tools/nit_harvest.py` | the census's nit-harvest arm: recurrence-ranked duplication clusters from the PR comment trail |
| `tools/promote.sh`, `tools/watch_build.sh`, `tools/board.sh` | operator commands: promote to Ready, watch a build to terminal state, dump the board |
| `skills/`, `skills/factory/templates/` | the factory skill (router + references); the upper-pipeline stage templates |

Full map in [AGENTS.md](AGENTS.md) → *Repo map*.

## How it runs (one line)

A human sets a ticket **Status → Ready** → n8n polls and POSTs it to `dispatch.py` → `dev-runner.sh`
builds it into a PR → merge is **factory-executed for an armed repo** under fail-closed conditions,
**human-merged** otherwise. Full lifecycle in [AGENTS.md](AGENTS.md); deployment in
[`deploy/DISPATCH.md`](deploy/DISPATCH.md).

## Where it lives

The factory is a sibling of the repos it builds, under one workspace root:

```
/opt/yellow-robots/
  factory/    ← this repo (the machinery)
  yellow-robots/ ← robot artifacts: schemas, robots, validate, promote
  website/    ← the website (landing + capture; onboarding)
  gilda/      ← a registered product repo
```

## License

[MIT](LICENSE). This repo is the machinery, not a running service — what's here to read is the pipeline's
design and record: [AGENTS.md](AGENTS.md), [`docs/rfcs/`](docs/rfcs/), and the factory skill
(`skills/factory/`). What actually executes builds — `tools/dispatch.py`, the n8n workflow it's paired
with, and `tools/dev-runner.sh` — runs **host-side only**, against this org's own tickets and credentials;
none of it is a service this repo serves to the outside.

## Status

Extracted from `yellow-robots` and made **repo-agnostic**: the runner discovers its workspace relative to
itself (`YR_WORKSPACE`, default `factory/../..`), resolves each target repo as `$YR_WORKSPACE/<name>`, and
reads that repo's build config from a per-repo `.yr/factory.toml` — every key `tools/dev-runner.sh` reads
from that manifest is documented in [AGENTS.md](AGENTS.md) → *Conventions*, the runner's own read sites
being the count, never a list here; explicit env overrides it.
