---
created: 2026-09-16
type: seed
status: done
summary: Every document is an input or output of a loop step and drifts unless a deterministic gate checks it; one script validates the vault, renders the changelog and cuts the tags.
value: 5
effort: M
version: v0.4
---

## Evidence

v1 kept its documents honest only with templates, a deterministic gate and hooks; every hand-maintained file without one rotted (findings report, 2026-09-12). v0.1 to v0.3 were specified in plan files outside git and closed with commit messages; nothing checked that the orientation page, the version notes and the tags agreed, and the page's first cold reader found three errors in it (commit 6cd3eca, 2026-09-16). The owner's items 2 (define and gate the specs) and 4 (formalise input and output), 2026-09-16.

## Goal

Add `gate.py` at the repository root, run as `uv run gate.py <command>`, with `main(argv, root=None)` shaped like `builder.main`: `argv[0]` is the program name, `root` defaults to the directory `gate.py` is in. Three commands. Each prints one line per problem on stdout, starting with the path relative to `root` and saying what is missing, and exits 1 if there is any; with nothing to report it prints nothing and exits 0. A missing or unknown command, or `release` without a version, prints usage on stderr and exits 2.

`check` validates `docs/` and the repository against it:

- every `.md` file under `docs/`, those under `docs/templates/` excepted, has frontmatter whose `type` names a file `docs/templates/<type>.md`;
- every wikilink in `docs/` (a double-bracket link, with or without an alias after `|` or a heading after `#`, embedded with a leading `!` or not) resolves to a note in `docs/`, by path or by name, or to a `.base` file;
- a seed (`type: seed`) has `status` in open, spec, building, done, rejected, and no frontmatter field beyond type, status, summary, value, effort, version; from `open` on it has `summary`, `value` in 1 to 5 and `effort` in S, M, L; from `spec` on, `version` names a file `docs/versions/<version>.md` and the body has a `## Goal` section with text under it; from `building` on, at least one test method or class in a `test*.py` file at the repository root has a docstring containing `seed: <file name without .md>`, a comment does not count; `rejected` is a way out at any stage and needs only what `open` needs;
- a version note (`type: version`) has no frontmatter field beyond `type` and is named `v<major>.<minor>.md`; at most one version note is not a tag; every seed whose `version` is a tag is `done` or `rejected`.

`render` writes `CHANGELOG.md` from the tags, newest first: for each tag, a heading from the version note's title line, the tag's date from git, then the note's first paragraph and the bullets under its `## Changelog`; embeds and the other sections stay out.

`release <version>` refuses unless `check` passes, `docs/versions/<version>.md` exists and the tag does not, every seed carrying the version is `done` or `rejected`, the note has at least one `## Changelog` bullet, `git status --porcelain` is empty, `AGENTS.md` has changed since the previous tag (the highest existing one; no constraint when there is none), and `python -m unittest` run at `root` is green. It then creates an annotated tag `<version>` at `HEAD` whose message is the note's first paragraph and changelog bullets, and runs `render`; a tag git cannot create is a problem like the others, reported, exit 1, nothing rendered.

The tests naming this seed are `test_gate.py`, written before the build; every command is exercised on a temporary vault and a temporary git repository.
