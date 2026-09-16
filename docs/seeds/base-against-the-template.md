---
type: seed
status: open
summary: The backlog's columns are consumers of the seed fields and nothing checks they still exist; the gate should.
value: 3
effort: S
version:
---

## Evidence

`gate.py` reads `.md` files only and knows `backlog.base` as a link target that must exist. A field renamed in the template leaves a column, a filter or the rank formula pointing at nothing until Obsidian is opened. Obsidian rewrites the base whenever the owner changes a view, a filter or an order (owner, 2026-09-16), so the check must read whatever shape Obsidian writes, not the shape a hand wrote.

## Idea

`check` reports every property the base names in its filters, formulas, order, sort and groupBy that is not a field of the seed template, a `file.` property or a `formula.` reference. One test on a temporary vault with a base naming a field the template does not have.
