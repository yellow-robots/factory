---
created: 2026-09-18
type: direction
---

## Thesis

The factory is a harness that, given an idea, builds the software that answers it. Its first project is itself: capabilities are grown, and a responsibility is transferred only once it can be measured. The end is weak recursive self-improvement — given a seed, the factory analyses it, sees how it fits, chooses how to build it, builds it, tests it and releases it. Closing that loop needs vision and taste, and we are far from it.

The product is what makes the journey sustainable, and it is a different claim. A coding harness and a cheap, capable model are commodity; anyone can have both. What is not commodity is the end-to-end: **a task priced before it starts and settled by a check the commissioner runs themselves.** The buyer never has to trust the seller's account of the quality, because the buyer's own tests decide. That inversion is the thing worth being early to.

The two are one trajectory rather than two projects. Each stage below removes something the commissioner has to bring, and the capability that removes it is the same capability weak SRI needs next.

**What would show us wrong.** Any of these, and the thesis is rewritten rather than defended.

- A commission cannot be completed without a human reading the code at every step. Then this is a copilot, and the factory is a framing rather than a machine.
- Commissioners will not, or cannot, say what they want as tests that fail. Then the contract has no oracle and the product is a different product.
- The factory cannot write the failing tests for a version of itself, however far the instruments improve. Then the capability half stops at stage 1 and the ladder has no rungs above it.

## Stages

Each stage names what the commissioner brings, what the factory supplies, and what must be true to say we are on it. Where we actually are is not written here: it is derived from the tags, the version notes and [[backlog.base]].

### Stage 1 — the commit

The commissioner brings a repository, a branch, a seed, tests that fail, and a way to run them. The factory supplies one commit on that branch that makes them pass, or a note on the head it was asked of saying why not.

**Reached when** a commissioner who is not the attended agent has had a commission answered end to end, on a machine of the factory's own, and has verified it by running their own tests against the delivered commit.

### Stage 2 — the tests

The commissioner brings a repository, a branch, and a description of what they want. The factory supplies the failing tests that define it, then the commit.

**Reached when** the factory writes the red tests for a seed of its own next version, and that version is built from them without the attended agent writing a test.

### Stage 3 — the fit

The commissioner brings a repository and an idea. The factory supplies where it belongs, how to build it, the tests, and the commit.

**Reached when** the factory carries a seed from open to done — placing it, specifying it, building it — with the attended agent reviewing rather than directing.

### Stage 4 — the deployment

The commissioner brings an idea. The factory supplies the deployed thing.

**Reached when** is not written. The stage is named so the direction is not mistaken for the destination, and because deploying may be a second robot with its own goals and its own tools rather than more of this one.

**Charging is not a stage.** The contract is legible from stage 1 onward: a ceiling quoted before the work, a check anyone can re-run after it. Automating the settlement is a rail, added when there is a commissioner who should pay — not when a stage is reached.

## Decisions

### 2026-09-18 — the product goes before the capability

Both goals are wanted; the order is now decided. The product's input is the commissioner's own failing tests, so the expensive capability — turning an idea into a specification — sits outside its scope and does not block it. And the differentiator is time-sensitive in a way weak SRI is not: a verifiable, task-priced contract is a small idea once stated, and its parts are off the shelf.

What this costs, recorded so it is not forgotten: v0.14's three reviews left 49 findings, each reproduced, verified and judged against known commits — a labelled corpus for measuring a transferred reviewer, and the rarest thing in evaluation work. It decays as the code moves away from those commits.

### 2026-09-18 — the thinnest end-to-end, and nothing more

The named risk is complexity: a factory that cannot be taken where it needs to go because of what was built into it on the way. So nothing enters that a first commission does not require. Everything designed on 18 September that no commission demands — escrow, parallel builds, per-project caches, a provisioner API, streamed evidence, metering beyond the record's own numbers — waits for a commission that demands it.

### 2026-09-18 — the check the factory re-runs is deferred

While the service is free, the commissioner is the oracle: they run their own tests against the delivered commit. The factory re-running them, and machine-checking that the tests were not edited to pass, become necessary when settlement is automatic and not before. Until then the commit's diff is readable and shows what changed.

### 2026-09-18 — a machine per build

`check.Dockerfile` belongs to the commissioner, and `docker build` runs its `RUN` lines with network and without limits, on the host that holds the provider key. Isolation is therefore what makes an external commissioner possible at all, not a hardening measure to add afterwards. A machine destroyed after every build is also the whole answer to a hijacked one: there is no lasting state for a compromise to sit in, and the authority to destroy is outside the machine, since a captured one will not destroy itself.

### 2026-09-18 — the records stay local for now

The host is imaged whole, so the single-copy risk is covered. It stops being covered when machines are disposable by design, because a machine destroyed on purpose takes its records with it. The remote is therefore part of the machine-per-build work rather than urgent on its own, and pushing each record to a ref of its own removes the contention a shared worktree has.

### 2026-09-18 — the v2 design draft is not a blueprint

`docs/scratchpad/factory-v2-design.md` is a source of proposals to argue with. Its architectural patterns and its code-quality checks are worth considering; its hypothesis sections — the sealed targets, the pre-registered thresholds, the horizon — are rejected and are not carried into anything.

## Open questions

- **Do commissioners arrive with failing tests?** The market is narrow for more reasons than the tests: a repository, a branch, a seed and a clear idea are all technical, so only technical people can appreciate the work. Answered by the first commissions — what they bring, and where they stop. If they will not bring tests, stage 2 stops being research and becomes the product's missing piece.
- **Who else sells a build settled by the buyer's own check, and why has it not worked?** Commissioned on 18 September, briefed to disconfirm rather than to confirm.
- **Can a model be trusted to write the failing tests for its own next version, and how would we know?** The instruments come first — [[set-world-outside-the-repository]], [[analyst-on-api-models]], [[paired-set-runs]], [[harder-capability-cases]] — and then stage 2's criterion answers it.
- **What is a forge for AI-driven development?** Deferred at v0.14 and still open. It decides where records, projects and commissions live once there is more than one of each.

## Out of scope

- **Continuous delivery as the factory's own responsibility.** Building and deploying may be two robots, with different goals and different tools. Stage 4 names the end; nothing here builds it.
- **Automated payment**, until there is a commissioner who should pay.
- **Parallel builds**, until one machine per build is shown to be insufficient. Three things block them today — the bench swept by name, the records committed through one shared index, and a spend cap that assumes one run at a time — and each is cheap once it is needed.
- **A status written anywhere.** What is done, what is in flight and what is next are derived from the seeds, the tags and the version notes. This document is amended when a decision changes, not when work happens.
