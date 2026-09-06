# Operating the factory — the human's manual

This is the human operator's front door: what a human alone may do, what shape a piece of work takes,
what a trail record means when it shows up, and where the operations reference lives. It **cites**;
where a rule already has a home, this page names that home and points at it, it never re-tells the
rule. See [`AGENTS.md`](../AGENTS.md) for the SDLC in depth and
[`skills/factory/SKILL.md`](../skills/factory/SKILL.md) for the operating router this page's inventory
tracks.

## Verbs in force at 2026-09-06 — last changed by it-32

Eight acts only a human performs. Each line names the act and the home of its rule — read there for the
actor, the condition, and the consequence; this list is the index, not the rule.

- **Set a design `active`.** Rule's home: [`AGENTS.md`](../AGENTS.md) → *Conventions*, "Attended
  operator sessions."
- **Promote a standalone task to Ready.** Rule's home: [`AGENTS.md`](../AGENTS.md) → *Workflow types*
  ("the floor," "direct seed-to-task lane" rows).
- **Rule a WHAT-call.** Rule's home:
  [`skills/factory/references/attended-lane.md`](../skills/factory/references/attended-lane.md) →
  "The human's checkpoints" ("ruling the callouts on a draft spec").
- **Pull the cord** — un-Ready an epic, at any time. Rule's home:
  [`skills/factory/references/attended-lane.md`](../skills/factory/references/attended-lane.md) →
  "The human's checkpoints" ("the cord-pull veto").
- **Merge a PR the runner did not open** (an attended hand-merge, or the click on a repo not yet
  armed). Rule's home: [`AGENTS.md`](../AGENTS.md) → *Conventions*, "Attended operator sessions"
  ("Never: … or hand-merge a PR").
- **Arm a repo.** Rule's home:
  [`skills/factory/references/attended-lane.md`](../skills/factory/references/attended-lane.md) →
  "The output-gate model" ("Arming is decided exclusively by the human").
- **Release the skill.** Rule's home:
  [`skills/factory/references/closing.md`](../skills/factory/references/closing.md), the skill-release
  block.
- **Sanction gate evolution** — the merge click that closes an attended gate-evolution build. Rule's
  home: `records.toml`, the `YR-GATE-TOUCHING` row.

## The seven workflow types

Rendered by citation from [`AGENTS.md`](../AGENTS.md) → *Workflow types* — that table owns the actors,
the gates, and the machine-checked path for each; this is the index of names and shapes only.

- **full ladder (legacy)** — spec → feature-rfc → technical-rfc → task.
- **spec + technical-rfc (norm)** — spec → technical-rfc → task.
- **the floor** — spec → task(s).
- **direct seed-to-task lane** — seed → drafted task → independent adversarial review on the trail →
  architect fit check → file with the task-delivered stamp → human promote.
- **attended host and ops** — owner instruction → attended session → the runbook's executed record.
- **attended gate evolution** — `YR-GATE-TOUCHING` line → epic gate refuses promotion → attended
  build → independent review → owner's merge click.
- **the debt round** — census → debt-round spec → debt epic → prune guard → close-hold → round-close
  duties.

## Reading a trail

A trail record is a fact plus the rule that judged it. Each row below names both, cited by row name
from `records.toml` — never restated, and never a catalogue of cures.

- **`YR-MERGE`** — fact: an armed repo's terminal merge decision. Rule: the evaluator's four
  conditions, in order (CI-green, freshness, terminal `APPROVE`, review-rank), disposing `MERGED` on
  an all-pass or `BLOCKED` naming the failed one.
- **The six `YR-EPIC-GATE` raise-family sentinels** (`no-approval`, `not-a-task`, `not-onboarded`,
  `open-questions`, `gate-touching`, `stranded claim`) — fact: the epic-gate sweep found a specific
  bad state on an epic or its child. Rule: each sentinel names exactly the condition it caught; the
  fix is closing that condition, not reading past the marker.
- **`YR-CLOSE-HOLD`** — fact: a finished non-debt epic wants to self-close. Rule: held while a
  mandated close record is missing; the comment names each absent one.
- **`YR-DEBT-HOLD`** — fact: a debt round wants to self-close. Rule: the same close-arm shape as
  `YR-CLOSE-HOLD`, scoped to a debt epic.
- **`STAGE-BLOCKED`** — fact: an implement/test stage could not proceed within its rules. Rule: the
  stage's final reply's last non-empty line names the reason; the runner routes straight to `Blocked`.
- **`VERDICT`** — fact: the review stage's judgment on a PR. Rule: the gate reads the LAST verdict
  line only, and it must be exactly `VERDICT: APPROVE` to pass.
- **`YR-ESCALATION`** — fact: an attended agent routed a one-way-door decision to the human instead of
  deciding it. Rule: the severity valve — every escalation is counted at close, never silent.
- **The board's `Needs-info` and `Blocked` reasons** ([`AGENTS.md`](../AGENTS.md), the task-lifecycle
  state machine) — fact: the ticket's `Reason` field names why it stopped. Rule: fail-closed on any
  doubt — a missing or invalid record raises `Needs-info` rather than guessing.

## Operation inventory

Every row of [`skills/factory/SKILL.md`](../skills/factory/SKILL.md)'s Operations table, by name, each
pointing at its reference:

- **Authoring** → [`references/authoring.md`](../skills/factory/references/authoring.md)
- **Reviewing** → [`references/reviewing.md`](../skills/factory/references/reviewing.md)
- **Gates** → [`references/gates.md`](../skills/factory/references/gates.md)
- **Pipeline** → [`references/pipeline.md`](../skills/factory/references/pipeline.md)
- **Closing** → [`references/closing.md`](../skills/factory/references/closing.md)
- **Migrating** → [`references/migrating.md`](../skills/factory/references/migrating.md)
- **Onboarding** → [`references/onboarding.md`](../skills/factory/references/onboarding.md)
- **Documentation model** →
  [`references/documentation-model.md`](../skills/factory/references/documentation-model.md)
- **Architect** → [`references/architect.md`](../skills/factory/references/architect.md)
- **Attended lane** → [`references/attended-lane.md`](../skills/factory/references/attended-lane.md)
- **Debt rounds** → [`references/debt-rounds.md`](../skills/factory/references/debt-rounds.md)

## What keeps this page honest

This page is current by construction, not by memory: the release act's `manual_current` condition
(`tools/release.py`) refuses a skill release when the range since the previous tag changed
`skills/factory/SKILL.md` or `AGENTS.md` — the two surfaces above render by citation — without also
touching this file, unless the release is invoked with `--manual-unaffected "<reason>"`. The second
guard is `tests/test_manual_inventory.py`, which parses `skills/factory/SKILL.md`'s Operations table
and the eight-verb and workflow-type sources live above and fails if this page's inventory falls
behind the tree.
