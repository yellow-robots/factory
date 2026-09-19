---
created: 2026-09-18
type: direction
---

## Thesis

The factory is a harness that, given an idea, builds the software that answers it. Its first project is itself: capabilities are grown, and a responsibility is transferred only once it can be measured. The end is weak recursive self-improvement — given a seed, the factory analyses it, sees how it fits, chooses how to build it, builds it, tests it and releases it. Closing that loop needs vision and taste, and we are far from it.

The product is what makes the journey sustainable, and it is a different claim. A coding harness and a cheap, capable model are commodity; anyone can have both. What is sold is the pipeline around them: a commission goes in, and a commit, a reviewer's verdict and a record of how both were reached come out. **It is priced per attempt and guarantees no output.** A service that guarantees an output invites commissions that cannot be satisfied, and spends its own money chasing problems with no known solution.

The commissioner chooses who attempts the work and who judges it — a builder, a reviewer, or several builders — or lets the factory route on the evidence of past runs. That is OpenRouter's shape applied to a pipeline rather than to inference: what you pick is not a model but a team.

**Top-quality code is not only the product, it is the foundation of the brand.** The reviewer leans harsh for that reason, and nothing about the verdict is negotiable per commissioner.

The two goals are one trajectory rather than two projects. Each stage below removes something the commissioner has to bring, and the capability that removes it is the same capability weak SRI needs next.

**What is not claimed.** Settlement is not provable today: a check the builder can read is not an independent oracle, and the published rates at which models satisfy a visible suite without doing the work are high enough that no contract should rest on one. Provable settlement is a property of a *task class*, not of a business — Diffblue has held it for years on coverage, where the unit is fungible and the oracle cannot be bent in the seller's favour. We may earn it for whatever class the records identify. We do not claim it for "any code change".

**What would show us wrong.** Any of these, and the thesis is rewritten rather than defended.
- A commission cannot be completed without a human reading the code at every step. Then this is a copilot, and the factory is a framing rather than a machine.
- Commissioners will not, or cannot, say what they want as tests that fail. Then the contract has no oracle and the product is a different product.
- The factory cannot write the failing tests for a version of itself, however far the instruments improve. Then the capability half stops at stage 1 and the ladder has no rungs above it.
- The records never separate a doable commission from an impossible one. Then routing is guesswork, there is never a provable tier, and the data is a log rather than an asset.
- A harsh reviewer's verdicts do not predict what commissioners accept. Then the verdict is noise sold as information.

## Roles

Four actors. Which programs they map to is derived from the repository; what each may do is not.

**The commissioner** brings the work, sets the terms — which models attempt it, how many, the ceiling — and disposes. The factory never writes to their branches; it proposes, and they advance their own.

**The factory** is the robot a commission is sent to. It instantiates one or more builders and a reviewer according to the task order, and chooses on the commissioner's behalf when asked to route. It does not pick the winner among competing proposals; the commissioner does. Routing without judging is not a conflict; routing *and* judging would be.

**The builder** writes code. It executes the commissioner's own code — their check, their tests — and is therefore the untrusted position in the system.

**The reviewer** reads. It cannot write, cannot fix what it finds, cannot push and cannot spend. A reviewer that could fix would become a builder and acquire an interest in finding less.

Three rules hold across the roles.

**Symmetry.** Whatever deterministic tool gatekeeps quality, the builder must pass it too. A standard the builder cannot run is one it will fail by accident, and every accidental failure is churn someone pays for. So the quality tools belong in the check, and the reviewer's work begins where they stop.

**Independence is a property of processes, not of hardware.** Separate programs and cold sessions give it. Separate machines are a commercial decision, taken when two services are marketed independently, not a pipeline optimisation.

**The bias has a direction, and the pricing sets it.** Paid per attempt, an in-house reviewer is biased toward rejecting, because rejection means more attempts. Paid per outcome it would be biased toward accepting. Harsh is by far the safer failure: it wastes the commissioner's money visibly rather than shipping bad code invisibly. The honest answer to "can I trust your reviewer" remains *commission a different one*.

## Coordination

The protocol is git, with one change to what the factory does today.

A commission allocates `refs/factory/proposed/<task>` at the base commit, which gives the task an identity before any work happens — needed for status, for metering, and for competing proposals to have names. A builder fast-forwards that ref to its commit; nothing is ever forced. The reviewer is commissioned against the ref and writes its verdict as a note on that commit. The commissioner fast-forwards their own branch to a proposal they accept, or leaves it.

**The factory never writes to the commissioner's branches.** That removes the branch-moved race, the never-force-push worry, and the question of who pays when a branch moves under a build. It costs the commissioner one command, which is the acceptance act that settles the contract — a contract that asks nothing of the buyer settles nothing.

Every state is read from git and none is written down: no ref is "never received"; a ref with no commit is building; a commit with no verdict note is under review; a commit with a verdict is answered; a branch at a proposed commit is accepted. A reviewer that dies mid-run leaves no note, and a missing verdict is honestly distinguishable from a negative one.

**Git carries actors** through signed commits, signed tags and signed pushes, with ref-scoped permissions enforced at the receiving end: the builder may write `refs/factory/proposed/*` and nothing else, the reviewer may write its notes and nothing else. What git does not carry, and what the protocol must supply, is the commission itself — repository, ref, seed, models, ceiling, deadline, what the parties agree the check is — along with liveness and settlement. The commission can be a signed object in git even though git has no vocabulary for it.

## Stages

Each stage names what the commissioner brings, what the factory supplies, and what must be true to say we are on it. Where we actually are is not written here: it is derived from the tags, the version notes and [[backlog.base]].

### Stage 1 — the commit

The commissioner brings a repository, a branch, a seed, tests that fail, and a way to run them. The factory supplies a proposed commit that makes them pass and a reviewer's verdict on it, or a note saying why not.

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

**Charging is not a stage.** The service is priced per attempt from the first paying commission; what the stages change is what a commission may ask for, not how it is paid for. A provable, fixed-price tier is added for a class of task when the records show that class is reliably doable — alongside pay-per-attempt, not replacing it.

## Decisions

### 2026-09-19 — priced per attempt, and no guaranteed output

The commissioner pays for the attempts they ordered, chooses which models make them, and carries the risk that the task is not solvable. Guaranteeing an output invites impossible commissions and makes the factory spend its own money on problems with no known solution.

This resolves three things at once. It **dissolves the gameable-oracle objection commercially**: if payment is not settled by the check, a check that can be satisfied without doing the work is bad information rather than a bad contract. It **answers adverse selection**, since an impossible task still pays for its attempts. And it turns the market research's strongest counter-evidence into precedent — `docs/scratchpad/market-2026-09-18.md` found that no coding vendor has held a per-task outcome price at scale and that Replit moved *to* effort-based pricing, charging for failed and looping runs as non-refundable compute.

The cost is a less differentiated claim. "Provable settlement" was sharp; "pay per attempt" is what everyone charges. The differentiation moves to the depth of the pipeline, to choosing a team rather than a model, and to the records.

### 2026-09-19 — the records are the second product

Success rate by task shape, by model, by cost is what routing needs in auto mode, and it is the only way a doable class of task will ever be identified for a provable tier. It is also **labelled outcome data** — task, attempt, verdict, accepted or not — which the market research could not find anywhere: all published pass/fail data is benchmark data, and benchmarks are contaminated. It is a by-product of running the pipeline honestly and nobody else is keeping it.

### 2026-09-19 — verification is a role of its own

The reviewer is its own program, its own cold session, its own run recorded in the store like any other; a role we cannot measure is a role we cannot transfer. It answers two questions a machine cannot: does the code do what the tests claim rather than merely satisfy them, and what else changed. Two machine preconditions run first because they are cheap — the tests pass, and the tests are the ones commissioned.

Its discipline is **reproduce before report**: a finding is not reported unless it has been demonstrated, and the verdict must be reproducible by the commissioner from what the commissioner holds. A finding only understandable by reading our record cannot settle anything.

### 2026-09-19 — lean harsh, one fixed claim, rich findings, no dial

Reviewer strictness is not a commissioner setting. A verdict whose meaning varies by commissioner is not comparable across commissions, and a corpus of incomparable verdicts cannot be routed on — which would cost us the decision above. The tolerance commissioners need already exists in the severity split: one fixed claim about whether the contract is met, and findings by severity that they dispose of themselves. A prototype ignores the smells; a payment system does not.

### 2026-09-19 — the record is a lead, never a ground

The reviewer may read the builder's record; a finding may not rest on it. If the wire shows the model noticing what a test asserts and special-casing it, that is worth chasing, and the defect must then be demonstrated in the code the commissioner holds. The risk of reading it is anchoring — verifying the builder's account rather than the artifact — which is empirical, so both arms are to be tried and compared on catch rate.

Whether the *commissioner* receives the record is a separate, commercial question. As proof that the work was done it is a differentiator nobody else offers.

### 2026-09-19 — the reviewer is stronger than the builder

GLM-5.3-Flash on API for the reviewer, `deepseek-flash` for the builder, with the model becoming a property of the role rather than a module constant. That the stronger model is the better reviewer is a hypothesis mutants can test rather than an assumption to carry.

**This breaks the key wall and the fix ships with it.** `leaked_file` scans a run for one key's value and `KEY_FILE` is one hardcoded path, so a reviewer run using the second key would have its record scanned only for the first. The scan becomes every key the instance holds, in the same version or the second model does not ship.

### 2026-09-19 — no long-lived key on the machine that runs commissioned code

Key custody is not a reason to split machines: the builder's machine already holds a provider key, so moving the second one elsewhere protects nothing. The coherent fix is a short-lived credential, or the model call proxied through something that holds the real key, which covers both keys and every future one.

### 2026-09-19 — the library at the agent layer, no orchestration engine

`pydantic-ai` earns its place where it already sits — one agent, one model, tools, typed output, usage limits — and a second provider is exactly what that layer is for. The build-check-review sequence is linear and short, and `build.py` already runs the part of it we have in plain code over subprocess and git. A graph engine buys branching, persistence and resumption; none of those are problems here, because nothing branches and resumption is re-running a commission, which is free while the request is durable in git. The reviewer's read-only tools are the right place to finally test `pydantic-ai-harness`'s `FileSystem(read_only=True)` against the two we hand-wrote, judged by the runs.

### 2026-09-18 — the product goes before the capability

Both goals are wanted; the order is now decided. The product's input is the commissioner's own failing tests, so the expensive capability — turning an idea into a specification — sits outside its scope and does not block it. And the differentiator is time-sensitive in a way weak SRI is not.

What this costs, recorded so it is not forgotten: v0.14's three reviews left 49 findings, each reproduced, verified and judged against known commits — a labelled corpus for measuring a transferred reviewer, and the rarest thing in evaluation work. It decays as the code moves away from those commits.

### 2026-09-18 — the thinnest end-to-end, and nothing more

The named risk is complexity: a factory that cannot be taken where it needs to go because of what was built into it on the way. So nothing enters that a first commission does not require. Everything designed on 18 September that no commission demands — escrow, parallel builds within one factory, per-project caches, a provisioner API, streamed evidence, metering beyond the record's own numbers — waits for a commission that demands it.

### 2026-09-18 — the check the factory re-runs is deferred

The commissioner runs their own tests against the delivered commit, and under per-attempt pricing nothing settles on the check at all. Machine-checking that the tests were not edited to pass is a different matter and is cheap: it is the crude half of the gaming problem and belongs with the reviewer's preconditions.

### 2026-09-18 — a machine per build

`check.Dockerfile` belongs to the commissioner, and `docker build` runs its `RUN` lines with network and without limits, on the host that holds the provider key. Isolation is therefore what makes an external commissioner possible at all, not a hardening measure to add afterwards. A machine destroyed after every build is also the whole answer to a hijacked one: there is no lasting state for a compromise to sit in, and the authority to destroy is outside the machine, since a captured one will not destroy itself.

The reviewer needs no such machine: it never executes commissioned code. It is exposed instead to prompt injection through the code, tests and seed it reads, and that risk is bounded by its own confinement — it cannot act, the dangerous direction is a false "meets" which the commissioner's own test run catches, and susceptibility is measurable by planting steering text alongside a known defect and seeing whether the verdict flips.

### 2026-09-18 — the records stay local for now

The host is imaged whole, so the single-copy risk is covered. It stops being covered when machines are disposable by design, because a machine destroyed on purpose takes its records with it. The remote is therefore part of the machine-per-build work rather than urgent on its own, and pushing each record to a ref of its own removes the contention a shared worktree has.

### 2026-09-18 — the v2 design draft is not a blueprint

`docs/scratchpad/factory-v2-design.md` is a source of proposals to argue with. Its architectural patterns and its code-quality checks are worth considering; its hypothesis sections — the sealed targets, the pre-registered thresholds, the horizon — are rejected and are not carried into anything.

### 2026-09-20 — a task's cost is not predicted before the work, and our own data cannot yet settle it

Research commissioned on whether a coding task's size or cost can be estimated before it is attempted came back against it, and the factory will not build a sizer. The published ceiling for predicting task difficulty from its description is a rank correlation near 0.4 within a benchmark and near 0.2 outside one, and a baseline of the description's word count reaches 0.086; measured on this factory's own builds, goal word count reaches 0.096 — the same baseline, independently reproduced, and nothing better. Every ex-ante feature in our records performs worse than predicting the mean, and the total a perfect oracle would have saved across the factory's whole history is $1.94.

What the dataset cannot do is more important than what it says, because it is fixable. Repository size and calendar date are the same variable in it, at a rank correlation of 1.000 — this repository only grows — so nothing about repository size is identifiable from our history at all; the one feature that appeared to predict well turned out to be counting files the model cannot see. The role prompt changed seven times across 61 seeded builds, the caps changed inside the window, and goal texts were revised between builds of the same seed, so the label moves too. Four confounds, all moving with time. `paired-set-runs` is the instrument that separates them, by holding everything but one variable fixed across a pair, and it is what a revisit would need first.

Two things follow that are worth doing. A seed's effort stops being a guess and becomes a measurement written back from its builds, which is reference-class forecasting on our own history rather than estimation. And the lever is the mean rather than the spread: relative spread is roughly constant whatever the size of the task, while the cap is an absolute number, so a seed's average cost is what decides whether it caps — nine seeds averaging under 35 requests produced no caps between them, and seven averaging more produced twelve.

### 2026-09-20 — the factory prices its own runs, at one flat rate, on purpose

`builder.py`'s `PRICE` table is the source of every cost the records carry and is not a fallback waiting to be replaced. `genai_prices` has no row for `deepseek-flash`, and the row for the adjacent name, `deepseek-v4-flash`, is a different model's numbers: 0.43x our cache-hit rate, 0.68x our input and 0.91x our output, which is no discount of anything. Checked against api-docs.deepseek.com/quick_start/pricing on 2026-09-20, our three constants are exactly DeepSeek's published peak rate for the model we run. Naming the model so the library can price it would have replaced a correct number with a wrong one, and the seed that proposed it is rejected.

The rate is flat where DeepSeek's is not. DeepSeek charges half outside 01:00-04:00 and 06:00-10:00 UTC on weekdays; 85% of the store's 190 runs started outside those windows, so the recorded spend overstates the money by 1.61x, $6.53 against $4.07. That is the right trade and it stays. What a bound on a run must measure is the work, and a number that halves because the clock passed 10:00 measures the hour instead — the same tokens would buy twice the work at midnight. So the column is what a run consumed at one constant rate, it is comparable across every record ever written, and no threshold derived from it is a claim about a bill. What the factory actually pays is a separate question that only arises when someone is billed for it.

## Open questions

- **How deep does the reviewer look before saying "meets"?** The builder's stopping condition is a green check; the reviewer's is a judgement about sufficiency and we have no principled one. Probably the hardest part of the role. Research commissioned 19 September into inspection-rate evidence, mutation score as an adequacy criterion, capture-recapture estimation of what two reviewers missed, and the economics of marginal detection.
- **Does the reviewer read the builder's record?** Both arms to be run and compared on catch rate against mutants.
- **Is the stronger model actually the better reviewer?** Mutants answer it cheaply, across versions.
- **Can task analysis separate a doable commission from an impossible one?** Everything about routing and about a provable tier depends on it, and the records are the only source of the answer.
- **Do commissioners arrive with failing tests?** The market is narrow for more reasons than the tests: a repository, a branch, a seed and a clear idea are all technical. Answered by the first commissions — what they bring, and where they stop. The research found no survey, no pricing experiment and no behavioural data on whether anyone will pay per task for code, and named it the cheapest hole for us to close ourselves.
- **Who pays for the losing attempts when several factories compete on one commission?** Settled in principle — the commissioner, who orders the attempts — but the bounty literature is a graveyard of markets where most work went unpaid, so the shape of the order matters.
- **Can a model be trusted to write the failing tests for its own next version, and how would we know?** The instruments come first — [[set-world-outside-the-repository]], [[analyst-on-api-models]], [[paired-set-runs]], [[harder-capability-cases]] — and then stage 2's criterion answers it.
- **What is a forge for AI-driven development?** Deferred at v0.14 and still open. It decides where records, projects and commissions live once there is more than one of each.

## Out of scope

- **Continuous delivery as the factory's own responsibility.** Building and deploying may be two robots, with different goals and different tools. Stage 4 names the end; nothing here builds it.
- **Settlement by the check**, until a class of task is identified from the records whose oracle cannot be bent in the seller's favour.
- **A workflow or orchestration engine.** The sequence is linear, nothing branches, and resumption is re-running a commission. The dependency would arrive without the problem.
- **A reviewer strictness setting.** The severity split gives the commissioner their tolerance without making the verdict negotiable.
- **Parallel builds inside one factory**, until one machine per build is shown to be insufficient. Three things block them today — the bench swept by name, the records committed through one shared index, and a spend cap that assumes one run at a time — and each is cheap once it is needed. Competing factories on one commission are a different question and an open one.
- **A status written anywhere.** What is done, what is in flight and what is next are derived from the seeds, the tags and the version notes. This document is amended when a decision changes, not when work happens.
