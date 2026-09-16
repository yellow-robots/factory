---
created: 2026-09-16
type: seed
status: building
summary: The backlog's columns are consumers of the seed fields and nothing checks they still exist; the gate should.
value: 3
effort: S
version: v0.5
---

## Evidence

`gate.py` reads `.md` files only and knows `backlog.base` as a link target that must exist. A field renamed in the template leaves a column, a filter or the rank formula pointing at nothing until Obsidian is opened. Obsidian rewrites the base whenever the owner changes a view, a filter or an order (owner, 2026-09-16), so the check must read whatever shape Obsidian writes, not the shape a hand wrote.

## Goal

`check` reads `docs/backlog.base` and reports every property it names that is not a frontmatter field of `docs/templates/seed.md`, one problem per property, naming `docs/backlog.base` and the property. A property is named as a key under `properties:`, as an entry of an `order:` list, as the `property:` of a `sort` or `groupBy` entry, or as a bare identifier in a filter or formula expression once quoted strings are removed; there, an identifier followed by `(` is a function, one preceded by `.` is a member, and `this`, `file`, `formula`, `true`, `false` and `null` belong to the language, so `file.` properties and `formula.` references are never reported. The base is read as Obsidian writes it, with or without quotes around an expression. The tests in `test_gate.py` whose docstring names this seed define the behaviour.

From the review of the build: a nested filter group, `and:`, `or:` or `not:` as a list item with its own items or with an inline expression, names no property, its items do; `note.` is a prefix of a property, so the name after it is checked; in an expression a hyphen is the minus and not part of a name, while a name under `properties:`, in `order:`, after `property:` or under `summaries:` may carry one; a regex literal between slashes and a `#` comment outside quotes name nothing; `summaries:` keys name properties as `order:` entries do; when the seed template is missing or has no frontmatter the base reports nothing, since the template's absence is reported once elsewhere.
