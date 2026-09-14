# 0001. Direction is human, authoring is AI, and the factory earns autonomy in stages

Date: 2026-09-14
Status: accepted

## Context

Factory v1 (`yellow-robots/factory-v1`) turned Ready tickets into reviewed PRs on its own and
shipped products. Its findings report records why it was retired: an AI cannot own every
technical decision, because it pattern-fits without comprehending; drift from any written
convention is permanent; the codebase and the rule set both accrete. Reading the code to catch
this reduces AI to a copilot, which is not the goal.

The v2 design document in the vault (`04 projects/factory/factory-v2-design.md`) is the
reference asset for the ideas below. It is not a specification: whatever is defined up front will
not hold as the loop is built, so the document is consulted, not implemented.

## Decision

Direction is human; authoring is AI. Code is written machine-to-machine: the human reads
structure and outcomes and never judges composition.

The factory is built from four blocks: constraint as focus, a minimal set of tracked tools,
multi-angle review rounds, and work cut into scoped chunks. Products are organisms under
selection pressure: a loop of goal, action, feedback, measure, action, with two measures.
Degradation measures whether the thing is built the right way. Adaptation measures whether the
right thing is built. Both are measured; neither is inferred from reading code.

Autonomy is earned in stages, and a stage is entered only when the previous one is measured:

1. Built attended. A human-directed agent builds the loop and drives it by hand.
2. Automatic construction. Goals (intents) are set by the owner; solutions and metrics are
   supervised by the owner.
3. Automatic with intents only. The owner sets goals; the factory chooses solutions and reads
   its own metrics.
4. Self-improving. The factory is one of its own products.

There may be more stages or fewer. Failing to reach stage 1 is a possible outcome and would be
recorded as one.

## Consequences

Nothing in this repository is a rule written in prose for an AI to follow; rules are tests,
gates and tools. Every attended session is a prototype of what the machinery will do
deterministically, so the attended agent works the way the machinery will. The design document
stays in the vault and is mined, not maintained as a spec.
