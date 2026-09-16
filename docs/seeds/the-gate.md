---
type: seed
status: spec
summary: Every document is an input or output of a loop step and drifts unless a deterministic gate checks it; one script validates the vault, renders the changelog and cuts the tags.
value: 5
effort: M
version: v0.4
---

## Evidence

v1 kept its documents honest only with templates, a deterministic gate and hooks; every hand-maintained file without one rotted (findings report, 2026-09-12). v0.1 to v0.3 were specified in plan files outside git and closed with commit messages; nothing checked that the orientation page, the version notes and the tags agreed, and the page's first cold reader found three errors in it (commit 6cd3eca, 2026-09-16). The owner's items 2 (define and gate the specs) and 4 (formalise input and output), 2026-09-16.

## Goal

Add `gate.py`, run as `uv run gate.py <command>` from the repository root, with three commands. Each prints one line per problem naming the file and what is missing and exits 1 if there is any; with nothing to report it prints nothing and exits 0.

`check` validates `docs/` and the repository against it:

- every `.md` file under `docs/`, those under `docs/templates/` excepted, has frontmatter whose `type` names a file `docs/templates/<type>.md`;
- every wikilink in `docs/` resolves to a note or a `.base` file in `docs/`;
- a seed (`type: seed`) has `status` in open, spec, building, done, rejected; from `open` on it has `summary`, `value` in 1 to 5 and `effort` in S, M, L; from `spec` on, `version` names a file `docs/versions/<version>.md` and the body has a `## Goal` section with text under it; from `building` on, at least one test method or class in a `test*.py` file of the repository has a docstring containing `seed: <file name without .md>`;
- a version note (`type: version`) is named `v<major>.<minor>.md`; at most one version note is not a tag; every seed whose `version` is a tag is `done` or `rejected`.

`render` writes `CHANGELOG.md` from the tags, newest first: for each tag, a heading from the version note's first line, the tag's date from git, then the note's first paragraph and the bullets under its `## Changelog`.

`release <version>` refuses unless `check` passes, `docs/versions/<version>.md` exists and the tag does not, every seed carrying the version is `done` or `rejected`, `git status --porcelain` is empty, `AGENTS.md` has changed since the previous tag, and `python -m unittest` is green. It then creates an annotated tag `<version>` at `HEAD` whose message is the note's first paragraph and changelog bullets, and runs `render`.

The tests naming this seed live in `test_gate.py`, written before the build; every command is exercised on a temporary vault and a temporary git repository.
