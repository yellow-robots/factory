# RFC 0002 — The dev-AI runner

**Status:** Accepted (2026-06-17) · **Decision-makers:** Jose + Claude · **Builds on:** [0001-ticket-driven-dev-workflow](0001-ticket-driven-dev-workflow.md)

## Context

RFC 0001 defined the workflow: a *Ready* GitHub Issue is dispatched to a **dev-AI** that produces a PR. This RFC designs that dev-AI — what it is, how it's invoked, and how it enforces *builder ≠ verifier*. The constraint from 0001 stands: start simple, keep model/harness flexible, don't lock in a bet.

## Decision

**Treat the runner as a swappable black box behind a thin contract; start with headless Claude Code on Sonnet.**

### The contract

```
dev-runner(issue#, repo) → a PR that meets the Definition of Done
```

The dispatch layer only knows "a runner." It does not know or care what's inside. This is what makes the harness/model a measurement, not a commitment — you A/B runners on identical issues.

### v1 runner: headless Claude Code + Sonnet 4.6

- **Invocation:** one `claude -p` (headless, non-interactive) run per *Ready* issue, model `claude-sonnet-4-6`, `effort: high`.
- **Why Sonnet:** tasks are small and Ready-by-DoR (a complete, self-contained spec), which is exactly the regime where a cheaper model is the cost-efficient choice. Sonnet 4.6 is ~40% cheaper than Opus ($3/$15 vs $5/$25 per 1M tok), strong at coding. The Ready bar and the model choice reinforce each other.
- **Why CC:** simplest, most proven coding agent, already in use; CC orchestrates the builder≠verifier flow natively via subagents.

### builder ≠ verifier (the one quality rule locked from day one)

A single `claude -p` run **internally orchestrates distinct roles as subagents** — the fresh context is the independence (no role needs a different model, though we can point one at a stronger model if a task warrants):

1. **Implementer** subagent — reads the Issue, branches `task/<issue#>-slug`, implements against the *acceptance criteria*.
2. **Tester** subagent (independent) — writes/verifies tests derived from the Issue's acceptance criteria, **not** from the implementation.
3. **Reviewer** subagent (independent) — code-quality review (maintainability / simplicity / security).
4. Opens the PR (`Closes #N`), moves the Issue to *In Review*.

The implementer never signs off its own tests or quality. Tests come from the spec; review is independent.

### Model & harness are config knobs

The runner reads its model and (later) harness from config. "Test other models" = change one setting. This is how the **OC dogfood successor** lands: same contract, OC runs the agent with DeepSeek/etc., A/B'd against CC+Sonnet on identical issues. OC-as-runner is also maximally on-vision — *a "developer robot" building Yellow Robots on Yellow Robots*.

### Dispatch (from RFC 0001)

`issue labeled ready` → **n8n** dispatches a runner against that issue, **+ a scheduled poll-sweep** of the Ready queue as the fallback (a dropped event never loses a task). The dev-AI reads the **Issue** (self-contained per DoR); Obsidian is a read-only fallback for RFC links; it never writes Obsidian. The dev-agent is **separate from Joam** — Joam runs the product, dev-agents build it.

## Alternatives considered

- **OpenHands / OpenCode** — turnkey native issue→PR, model-agnostic, strong SWE-bench. Kept as A/B candidates behind the contract; not v1 because CC is simpler and already wired.
- **aider / mini-swe-agent** — leanest engines; we'd wrap git/PR ourselves. Fallback if we want a fully-owned minimal runner.
- **OC now** — the dogfood destination, but coding quality unproven; promote it once it measures up against the CC+Sonnet baseline.
- None ship a turnkey builder≠verifier — we orchestrate it ourselves regardless (above).

## Consequences

- The runner is built **directly** (bootstrap, like the skeleton) — it can't build itself.
- Start manual-trigger; wire n8n event+poll dispatch once the runner is proven on a few issues.
- The first live end-to-end run is worth watching — don't switch on autonomous dispatch before it's trusted.

## Open / deferred

- Exact subagent prompts (implementer/tester/reviewer) — in the implementation plan.
- How the runner moves Issue state (labels/Project status) and handles `needs-info` bounce-backs.
- OC-runner adapter — after CC+Sonnet v1 is the baseline.
