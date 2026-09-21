---
created: 2026-09-18
type: seed
status: done
summary: A wikilink that names a path outside the vault resolves to nothing and the gate says nothing, so a link Obsidian cannot follow passes the check that exists to catch exactly that.
value: 2
effort: S
version: v0.21
---

## Evidence

2026-09-18, found by the third review of v0.14 and read in the code by the attended agent: `_resolve` joins a wikilink's target to `docs/` and asks whether the file exists, and `_in_part` answers true for any path that is not under the root, so a wikilink to `/etc/hostname` resolves and `check` is silent. The pass exists to catch a link that leads nowhere, and Obsidian cannot follow a link out of the vault. The same fail-open branch answers for a target reached by `..`. No note of this vault holds such a link: the check has been silent about none.

2026-09-21. [[the-gate-in-three]] split the gate, and its `vault.holds` answers `False` for a path outside the root, held by a test of its own. `gate.py check` then reported, at once, the two notes of this vault that quoted the escaping link as an example -- this seed's Evidence above, and the review note it came from -- so the literal is now written as prose in both, and the sentence above saying no note holds such a link was true only of links meant as links. Measured on the split tree at 3d98c07 in this repository's own vault: `vault.resolves` answers `False` for `../AGENTS.md`, for `../AGENTS` and for `/etc/hostname`, and `True` for `seeds/../seeds/the-gate-in-three.md`. The hole is shut whole by the split's builds, runs 20260921T103518Z and 20260921T104653Z; the test named below pins it, green as written, and no build of this seed's own was needed.

## Goal

A wikilink's target is a path inside the vault, or it resolves to nothing.

`vault.resolves(target)` answers `True` only for a file under `docs/` that the vault holds -- reached by the target as a path under `docs/`, by the target with `.md` appended, or by its name anywhere under `docs/`, as today -- and `False` for a target that leaves `docs/` by an absolute path or by `..`, whatever file that path reaches, tracked or not. `check` then reports such a link as it reports any link that does not resolve, `<rel>: wikilink <target> does not resolve`, and nothing else about the reading of the vault changes.
