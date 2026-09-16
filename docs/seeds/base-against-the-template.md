---
created: 2026-09-16
type: seed
status: spec
summary: The backlog's columns are consumers of the seed fields and nothing checks they still exist; the gate should.
value: 3
effort: S
version: v0.5
---

## Evidence

`gate.py` reads `.md` files only and knows `backlog.base` as a link target that must exist. A field renamed in the template leaves a column, a filter or the rank formula pointing at nothing until Obsidian is opened. Obsidian rewrites the base whenever the owner changes a view, a filter or an order (owner, 2026-09-16), so the check must read whatever shape Obsidian writes, not the shape a hand wrote.

## Goal

`check` reads `docs/backlog.base` and reports every property it names that is not a frontmatter field of `docs/templates/seed.md`, one problem per property, naming `docs/backlog.base` and the property. A property is named as a key under `properties:`, as an entry of an `order:` list, as the `property:` of a `sort` or `groupBy` entry, or as a bare identifier in a filter or formula expression once quoted strings are removed; there, an identifier followed by `(` is a function, one preceded by `.` is a member, and `this`, `file`, `formula`, `true`, `false` and `null` belong to the language, so `file.` properties and `formula.` references are never reported. The base is read as Obsidian writes it, with or without quotes around an expression. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
