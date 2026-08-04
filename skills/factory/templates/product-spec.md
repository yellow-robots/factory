---
type: product-spec
status: draft              # doc lifecycle: draft | active | rejected | superseded (NOT the board's Status)
supersedes: []             # active designs this doc replaces; targets are quoted "[[wikilinks]]"; empty
                            # is allowed but must be justified in the body; stamped superseded at accept
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---

# Product spec — <feature name>

> Spec discipline: **WHAT and WHY only — no tech stack, no file names, no "how".** Naming a module
> belongs in the technical RFC, not here. Every acceptance criterion must be expressible as a test.

**Supersedes:** nothing — <one-line justification of the empty claim>
<!-- Keep this line, with a real justification, when the supersedes list above is empty. Once the
     list is non-empty, replace it with prose naming what's replaced, or drop it entirely. -->

## Why
<!-- The product reason this exists. One short paragraph: who is helped and how. -->

## What
<!-- The observable behaviour from the user's / product's point of view. No implementation. -->

## Acceptance criteria (EARS)
<!-- Easy Approach to Requirements Syntax — each line testable, 1:1 with a future test. Pick the
     simplest form that fits:
       Ubiquitous (static content/config — no trigger):  THE SYSTEM SHALL <always-true behaviour>.
       Event-driven:                                      WHEN <trigger> THE SYSTEM SHALL <behaviour>.
     (Also available: WHILE <state> …, WHERE <feature> …, IF <unwanted condition> THEN ….) -->
- THE SYSTEM SHALL <observable behaviour>.
- WHEN <condition / event> THE SYSTEM SHALL <observable behaviour>.

## Out of scope
<!-- What this explicitly does NOT do — bounds the RFC. -->

---
*Next stage:* a **feature RFC** (`feature-rfc.md`) cites this spec and chooses the approach.
Gate before then: **spec ready** (human). A criterion that can't become a test isn't done.
*Review output:* fold findings in — or, if heavyweight, a standalone `research`/`note` cited here; never a frozen appendix (see `documentation-model.md` → *Reviewing a doc*).
