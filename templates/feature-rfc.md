---
type: feature-rfc
status: draft              # doc lifecycle: draft | active | rejected | superseded (NOT the board's Status)
source_spec: "[[<product-spec note>]]"   # the spec this cites — resolvable wikilink, checked by check_links
supersedes: []             # active designs this doc replaces; targets are quoted "[[wikilinks]]"; empty
                            # is allowed but must be justified in the body; stamped superseded at accept
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---

# Feature RFC — <feature name>

> This is a **feature RFC** — the product-side design (stage 2) that spawns the stage-3 **technical RFC**
> and then task-Issues. Distinct from the factory's own *foundational* technical RFCs (0001–0005 in
> `yellow-robots/factory/docs/rfcs/`), which design the factory itself. Gate: review the **outline** of this
> feature RFC before it's fully written — the cheap checkpoint.

**Supersedes:** nothing — <one-line justification of the empty claim>
<!-- Keep this line, with a real justification, when the supersedes list above is empty. Once the
     list is non-empty, replace it with prose naming what's replaced, or drop it entirely. -->

## Outline (for the pre-gate)
<!-- 3-5 bullets: the approach in brief. The human approves THIS before you write the full RFC. -->

## Context
<!-- Summarise the spec in 2-3 lines and cite it. What problem; what's already true. -->

## Decision
<!-- The chosen approach, stated plainly. One paragraph. -->

## Details
<!-- How the approach works — enough for the technical RFC to map it onto the codebase.
     Design-level, not file-level (file names are the technical RFC's job). -->

## Scope / non-goals
<!-- What's in this RFC; what's deliberately out (becomes future RFCs). -->

## Alternatives considered
<!-- Options weighed + why rejected. Keep honest. -->

## Open questions
<!-- Anything unresolved the technical RFC or decomposition must settle. -->

## Consequences
<!-- What changes downstream; any new constraint this introduces. -->

---
*Next stage:* a **technical RFC** (`technical-rfc.md`) maps this onto the existing repo.
Gate before then: **approve RFC** (human).
*Review output:* fold findings into this RFC + the technical-RFC / task acceptance; a heavyweight, standalone-worthy review lives as its own `research`/`note` doc, cited here — never a frozen appendix (see `documentation-model.md` → *Reviewing a doc*).
