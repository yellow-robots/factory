---
type: seed
status: spec
summary: Every document is an input or output of a loop step and drifts unless a deterministic gate checks it; one script validates the vault, renders what is derived, and cuts tags with changelogs.
value: 5
effort: M
goal: Add gate.py with three commands. `check` validates docs/ (every seed's frontmatter has the fields its status requires per templates/seed.md, wikilinks resolve, exactly one version note has no tag), `render` rewrites the Now section of docs/factory.md and the derived parts of each version note from git and the seeds, and `release <tag>` refuses unless check passes and every seed assigned to the version is done, then cuts an annotated tag whose message is the version note's changelog and regenerates CHANGELOG.md from all tags. Each command exits non-zero naming what is missing.
acceptance: test_gate.py, written before the build; every command exercised on a temporary vault and a temporary git repository.
version: v0.4
crossed_to:
created: 2026-09-16
---

## Evidence

v1 kept its documents honest only with templates, a deterministic gate and hooks; every
hand-maintained file without one rotted (findings report, 2026-09-12). v0.1 to v0.3 were specified
in plan files outside git and closed with commit messages; nothing checked that the front door,
the version notes and the tags agreed. The owner's items 2 (define and gate the specs) and 4
(formalise input and output), 2026-09-16.

## Idea

The gate is the hook: it runs as a cold session's first command and at release. Derived first,
hand-written last: the front door's Now section, the version notes' spec lists and changelogs, the
ranking, all come from git and frontmatter; the hand-written parts are the seed bodies, one goal
sentence, one closing paragraph per version, five sentences on the front door.
