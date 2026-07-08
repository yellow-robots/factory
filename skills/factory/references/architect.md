# Architect — custodian of the map of the present

> **When to load this reference:** running any of the architect's three bound moments — the
> spec-ready grounding-and-disposition check, the crossing (authoring a technical-rfc and its
> slices), or the ship-walk (closing an iteration whose component has grown a living reference).
> For the cross-cutting layer and the living reference's load-bearing sections, see
> [`documentation-model.md`](documentation-model.md) — *The cross-cutting layer*. For the
> spec/RFC review discipline the architect runs alongside, see [`reviewing.md`](reviewing.md). For
> promote-to-Ready, merge, doc freeze, and skill release, see [`closing.md`](closing.md).

---

## Charter

The architect is the custodian of the **map of the present** — bound to three moments that already
exist in the pipeline, never a fourth stage added on top of it.

1. **Spec-ready.** Verify the grounding still holds: check the spec's citations against the current
   cross-cutting homes, and check its *forward* claims against the world, not only doc-vs-tree — a
   claim can be internally consistent with the docs and still be wrong about the tree. Produce and
   challenge the supersession disposition: a per-target ruling — **wholly replaced**, **partially
   affected**, or **unaffected** — each with evidence. A *partial* ruling routes to a living-map
   drift entry, never a tombstone. Tombstones (`status: superseded` + `superseded_by`) land only at
   accept, written only by the accepting session (see [`documentation-model.md`](documentation-model.md)
   — *Lifecycle*): the architect's output at this moment is the verified disposition, not the stamp.
2. **The crossing.** Author the technical-rfc on the epic Issue and its self-contained slices
   against the *current* tree, never the tree as the spec imagined it, and stamp `crossed_to` the
   moment the epic exists (see [`documentation-model.md`](documentation-model.md) — *Identity &
   navigation*). Run a final citation-drift pass against the tip at filing: the base can move
   mid-session, and a crossing that skips re-checking its own citations against that moved tip ships
   stale ones.
3. **The ship-walk.** Walk the grounding list: update the living reference in place, supersede
   replaced research (never edit it), verify the stamps — the crossing stamp and every declared
   pair — and record the pilot observables with the iteration.

The architect is also the **boundary custodian** — advisory only: when a spec or crossing moves a
component boundary (a new top-level home, a seam between repos, a component split or merge), it
names the boundary change explicitly as a WHAT-call on the for-the-human list — it never draws the
boundary itself, and no machinery gates on it.

## Independence and ordering

The architect runs as its **own independent cold session** — author ≠ fit-checker, the upper
pipeline's analogue of the lower pipeline's builder ≠ verifier. A single session that authors a
crossing and then fit-checks its own supersession disposition is grading its own homework.

Where a doc also earns the adversarial review (see [`reviewing.md`](reviewing.md)), the **review
runs first and folds in**; the architect runs **last**, against the final text. Reversing that order
— architect first, review second — lets one sympathetic frame carry through both passes; running
the architect last means it judges what actually shipped, not an intermediate draft.

## Fail-closed rules

- A replacement or fit question the session **cannot determine** goes on a **"for the human"** list
  in its report — never a guess, never a silent pass.
- A factual slip discovered in an **already-active** spec routes to the human, never a silent edit —
  an active spec is a frozen record (see [`documentation-model.md`](documentation-model.md) — *Two
  principles*); the architect flags what it found, it never rewrites history to match it.
- Open WHAT-calls live on the design side — the only side with a structural human gate: at spec-ready
  they land as callouts on the draft; at the crossing, an unresolved question pauses the crossing and
  goes back into the governing design doc — never onto the epic, which past the airlock executes
  mechanically with no human gate, by design. The epic's trail carries dispositions only — every item
  closed in or before the `YR-EPIC-APPROVAL` record.

## The earn-test

Decidable from the draft alone, no external state needed. The role runs when **any** arm holds:

1. a non-empty `supersedes` declaration;
2. an earned technical-rfc, read from the draft's own Next-stage statement;
3. changes touching the living reference's **load-bearing** sections (the reference cites
   [`documentation-model.md`](documentation-model.md) for the section set).

No arm holds ⇒ the role is **skipped**: the empty-declaration justification line plus the ordinary
human review suffice. The architect is earned work, not a tax on every change.

## Running a session — practice the pilot earned

Four sessions across it-9 (2026-07-07/08) settled the following; fold it into every run after:

- **Cite prior dispositions as precedent.** A settled ruling shortens the next one — the RFC-0005
  partial ruling settled the epic-gate-letter case in minutes once cited, instead of being
  re-argued from scratch.
- **Run the crossing's drift check at filing, always.** It is not optional even when the session
  feels fast: the pilot's second crossing was forced into exactly this repair when the base moved
  mid-session.
- **Ground the spec-ready check against the world, not only the docs.** A forward claim can pass
  every doc-vs-doc check and still be wrong about the tree; the spec-ready moment tests both.
- **Declare hand-executed gates.** Hand-running an approved-but-unshipped gate — a check whose
  tooling hasn't landed yet — is legitimate; declare it plainly in the report so a later reader can
  tell manual execution from automation.
- **Cite the counting rule, never re-derive a census informally.** A number that doesn't reproduce
  under a pinned counting rule isn't a finding, it's a guess with a decimal point.
- **The report ends in the moment's standard shape:**
  - **Fit check:** verdict → dispositions → deltas → census → for-the-human → observables.
  - **Crossing:** epic + ordered slices → EARS-landing map → gate outputs verbatim → choices with
    tradeoffs → for-the-human → observables.
  - **Ship-walk:** grounding walk → living-reference diff → sweep-vs-view agreement check → stamp
    verification → pilot observables.
