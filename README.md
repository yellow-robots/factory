# Yellow Robots — dev factory

The **build machinery** for Yellow Robots: it takes a *Ready* ticket to a *reviewed PR*, autonomously,
across any YR repo. The robot (a probabilistic LLM) proposes; deterministic gates dispose.

This is **infrastructure**, deliberately separate from the product repos it builds (`yellow-robots`,
`website`, `gilda`). Each product repo is self-contained and declares *how* to build itself; the factory
supplies *the pipeline*.

**New here?** Read **[AGENTS.md](AGENTS.md)** — how the factory works and the SDLC it runs. The *why*, in
depth, is in [`docs/rfcs/`](docs/rfcs/).

## What's here

| Path | What |
|---|---|
| `tools/dispatch.py` | the host endpoint n8n calls to fire a build (RFC 0004) |
| `tools/dev-runner.sh` | the staged pipeline: gate → implement → independent test → check → independent review → PR (RFC 0002) — builder ≠ verifier, by construction |
| `tools/merge_shadow.py` | the merge-decision evaluator + shadow-completion |
| `models.toml` + `tools/registry.py` | the model registry (data) + its stdlib loader/CLI |
| `tools/ledger.py` | the usage ledger: transcript archive, per-invocation row, per-model/report reads |
| `tools/stage_usage.py`, `tools/textutil.py` | the PR usage-summary comment; small shared text helpers |
| `tools/bench_corpus.py`, `tools/bench_replay.py`, `tools/bench_report.py`, `tools/verdict_diff.py` | the bench corpus, candidate replay, report aggregation, and gating-vs-shadow verdict diff |
| `deploy/` | the dispatch systemd service, the n8n workflow, and switch-on notes (`DISPATCH.md`) |
| `docs/rfcs/` | implemented technical RFCs — 0001 workflow, 0002 runner, 0003 task state, 0004 dispatch, 0005 upper-pipeline. Unimplemented designs live in the Obsidian brain. |
| `tests/` | pytest suite (stubbed: no live LLM, no network) |
| `qa/` | consumer quality content (e.g. `qa/lens.py`) — distinct from the platform machinery in `tools/` |
| `tools/epic_gate.py`, `tools/review_bundle.py`, `tools/check_task.py`, `tools/check_links.py`, `tools/check_model_refs.py`, `tools/check_supersession.py` | the standing-approval sweep; the hashed review bundle; the DoR, crossing-link, stale-reference, and supersession gates |
| `tools/promote.sh`, `tools/watch_build.sh`, `tools/board.sh` | operator commands: promote to Ready, watch a build to terminal state, dump the board |
| `skills/`, `templates/` | the factory skill (router + references); the upper-pipeline stage templates |

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
reads that repo's build config from a per-repo `.yr/factory.toml` (`check_cmd` / `model` / `base_ref`;
explicit env overrides it). 1129 tests green.
