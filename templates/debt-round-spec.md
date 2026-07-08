---
type: product-spec
status: draft              # doc lifecycle: draft | active | rejected | superseded (NOT the board's Status)
supersedes: []             # active designs this doc replaces; targets are quoted "[[wikilinks]]"; empty
                            # is allowed but must be justified in the body; stamped superseded at accept
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---

# Debt-round spec — round <N>

> Filed as: a `product-spec` scoping one tech-debt round under its debt epic. The epic's own body must
> carry the kind record line `YR-ITERATION-KIND: tech-debt` — verbatim blocks are safe in repo files;
> the counter and the close-hold read GitHub issue surfaces only, never this file. Spec discipline: **WHAT and
> WHY only** — every item named below traces to a census row; see
> [`debt-rounds.md`](../skills/factory/references/debt-rounds.md) for the round protocol this
> instantiates (*The walls*, *Record grammars*, *Round-close duties*).

**Supersedes:** nothing — <one-line justification of the empty claim>
<!-- Keep this line, with a real justification, when the supersedes list above is empty. Once the
     list is non-empty, replace it with prose naming what's replaced, or drop it entirely. -->

## Why
<!-- The mandate for this round: the raise (`YR-DEBT-DUE`) that called it, and why now. -->

## Scope — by name
<!-- An item not named here is not in the round. A prune PR reaching for one more thing "while it's in
     there" is scope creep on a pipeline built to fail closed on undeclared scope. One row per item. -->
| Item | Census row | Pin slice | Prune slice |
|---|---|---|---|
| <item> | <census doc row / anchor> | <slice / Issue> | <slice / Issue> |

## Pin-then-prune ordering
<!-- Every behavior-touching item is an ordered pin-then-prune pair under the epic — the pin slice
     (tests that lock the ledger's kept behavior) is purely accretive and lands before its prune slice.
     Sub-issue order is the enforcement: the epic's own sub-issue serialization — promoting one open
     child at a time, in sub-issue order — enforces that ordering mechanically; no reviewer discipline
     is needed to keep a prune from landing ahead of its pin. -->

## Acceptance criteria (EARS)
<!-- Easy Approach to Requirements Syntax — each line testable, 1:1 with a future test. Pick the
     simplest form that fits:
       Ubiquitous (static content/config — no trigger):  THE SYSTEM SHALL <always-true behaviour>.
       Event-driven:                                      WHEN <trigger> THE SYSTEM SHALL <behaviour>.
     (Also available: WHILE <state> …, WHERE <feature> …, IF <unwanted condition> THEN ….) -->
- THE SYSTEM SHALL <observable behaviour>.
- WHEN <condition / event> THE SYSTEM SHALL <observable behaviour>.

### Per-prune acceptance scaffold
<!-- Copy this block into each prune slice's own acceptance criteria; fill the fields, don't rename them. -->
- [ ] Pins green — the pin slice's tests still pass, unchanged (behavior-identical).
- [ ] The PR body carries the net-lines record, aggregated into the round's ledger verdict at close:
  ```
  YR-DEBT-NET-LINES
  net-lines: <int>
  scope: <the named item(s) from Scope — by name above>
  birth: <the introducing commit or issue, read off the item's census row — never re-derived>
  ```
- [ ] Every removal cites its `birth:` — the census row already records it; no re-derivation from
      `git blame` at prune time.
- [ ] No new dependencies.

### Suite-duration canary
<!-- Recorded, never gated: the full-suite duration at this slice's close, carried into the round's
     ledger verdict `suite-duration` field. A slow suite is signal, not a failing gate. -->
- Suite duration: `<Nm NNs>` (recorded, never gated)

## Out of scope
<!-- What this explicitly does NOT do — bounds the round. -->

## Round close
<!-- Run once, attended, when every pin-then-prune pair in Scope — by name above has landed. -->
1. **Post the ledger verdict** as a comment on the debt epic — the `YR-DEBT-LEDGER` grammar, all seven
   fields:
   ```
   YR-DEBT-LEDGER
   items: <int>
   net-lines: <int>
   files-removed: <int>
   deps-removed: <int>
   pins-added: <int>
   suite-duration: <Nm NNs>
   incidents: <none | description>
   ```
2. **Aggregate the per-slice net-lines records** — every `YR-DEBT-NET-LINES` record posted by a prune
   PR in this round — into the verdict's `items` and `net-lines` totals.
3. **Close the raise item** (the `YR-DEBT-DUE` issue) that called this round.
4. **Clear the epic's held `Reason`** — the epic-gate's sweep posts the hold and sets `Needs-info`, but
   it never clears a Reason itself; clearing is this attended act.
5. **Re-census** — start the next round's census from this round's revisit trigger, not from scratch.

---
*Next stage:* the round's items decompose into pin-then-prune task-Issue pairs under the debt epic.
Gate before then: **spec ready** (human). A criterion that can't become a test isn't done.
*Review output:* fold findings in — or, if heavyweight, a standalone `research`/`note` cited here; never a frozen appendix (see `documentation-model.md` → *Reviewing a doc*).
