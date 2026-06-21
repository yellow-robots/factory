# Yellow Robots — dev factory

The **build machinery** for Yellow Robots: it takes a *Ready* ticket to a *reviewed PR*, autonomously,
across any YR repo. The robot (a probabilistic LLM) proposes; deterministic gates dispose.

This is **infrastructure**, deliberately separate from the product repos it builds (`platform`, `mcp`,
`website`). Each product repo is self-contained and declares *how* to build itself; the factory supplies
*the pipeline*.

**New here?** Read **[AGENTS.md](AGENTS.md)** — how the factory works and the SDLC it runs. The *why*, in
depth, is in [`docs/rfcs/`](docs/rfcs/).

## What's here

| Path | What |
|---|---|
| `tools/dispatch.py` | the host endpoint n8n calls to fire a build (RFC 0004) |
| `tools/dev-runner.sh` | the staged pipeline: gate → implement → independent test → check → independent review → PR (RFC 0002) — builder ≠ verifier, by construction |
| `tools/textutil.py` | small shared text helpers |
| `deploy/` | the dispatch systemd service, the n8n workflow, and switch-on notes (`DISPATCH.md`) |
| `docs/rfcs/` | canonical RFCs — 0001 workflow, 0002 runner, 0003 task state, 0004 dispatch |
| `tests/` | pytest suite (stubbed: no live LLM, no network) |

## How it runs (one line)

A human sets a ticket **Status → Ready** → n8n polls and POSTs it to `dispatch.py` → `dev-runner.sh`
builds it into a PR → a human merges. Full lifecycle in [AGENTS.md](AGENTS.md); deployment in
[`deploy/DISPATCH.md`](deploy/DISPATCH.md).

## Where it lives

The factory is a sibling of the repos it builds, under one workspace root:

```
/opt/yellow-robots/
  factory/    ← this repo (the machinery)
  platform/   ← robot artifacts: schemas, robots, validate, promote
  mcp/        ← (to come)
  website/    ← (to come)
```

## Status

Bootstrapped by a faithful extraction from `platform` — 56 tests green. **Next (routing refactor):** make
the runner repo-agnostic — discover the workspace relative to itself and read a per-repo `.yr/factory.toml`
manifest (`check_cmd`, model, base ref) — so it builds *any* sibling, not just the repo it is run from.
Until then the runner still assumes it is run from within the target repo's checkout.
