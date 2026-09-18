---
created: 2026-09-18
type: seed
status: open
summary: A wikilink that names a path outside the vault resolves to nothing and the gate says nothing, so a link Obsidian cannot follow passes the check that exists to catch exactly that.
value: 2
effort: S
version:
---

## Evidence

2026-09-18, found by the third review of v0.14 and read in the code by the attended agent: `_resolve` joins a wikilink's target to `docs/` and asks whether the file exists, and `_in_part` answers true for any path that is not under the root, so `[[/etc/hostname]]` resolves and `check` is silent. The pass exists to catch a link that leads nowhere, and Obsidian cannot follow a link out of the vault. The same fail-open branch answers for a target reached by `..`. No note of this vault holds such a link: the check has been silent about none.

## Idea

A wikilink's target is a path inside the vault or it resolves to nothing: a target that leaves `docs/`, by an absolute path or by `..`, is the problem the pass already reports, named as the link it is. The reading of the vault is unchanged; what changes is that a path outside it is no answer.
