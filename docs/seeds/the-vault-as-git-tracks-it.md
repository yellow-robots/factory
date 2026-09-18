---
created: 2026-09-17
type: seed
status: building
summary: The gate reads every `.md` under `docs/` from the filesystem, so a note git ignores refuses `check` and with it every release; the gate reads the vault as git tracks it.
value: 3
effort: S
version: v0.14
---

## Evidence

2026-09-17, after 64623a8: the owner keeps a scratchpad in the vault, `docs/scratchpad/`, to read notes in Obsidian, the vault being `docs/`, and git ignores it so its contents bother no one. `uv run gate.py check` then exits 1 with `docs/scratchpad/eval-practices.md: no frontmatter`, and `release`, which runs the check first, refuses with it, so a note nobody tracks stops a release. `_notes` is every `*.md` under `docs/` but the templates', and the wikilink pass walks `docs.rglob("*")`, both from the filesystem; `_wire_problems` already asks git, `git ls-files`, for the records it checks. `docs/.obsidian/` has been ignored since v0.5 and passes only because none of its files holds `[[`.

## Idea

The gate reads the vault as git tracks it: a path git ignores is no note, for the notes, for the wikilink pass and for the base, and a directory that is not a git checkout is read whole as today. One reader answers it, `git check-ignore` or the list `git ls-files` gives of what is tracked and what is untracked and not ignored, beside `_wire_problems`, which already reads git. Then a scratchpad inside the vault bothers nothing, and a note git tracks is checked as it is now.

## Goal

The gate reads the vault as git tracks it. A path git ignores is no note and no part of the vault: `check` passes it over for its frontmatter, for its type, for its fields and for the wikilinks it holds, and a wikilink of a note's that names an ignored path resolves to nothing, which is the problem it already is. A path git tracks is read as it is now, and so is one nobody has committed yet, which git does not ignore: only what git is told to ignore is passed over.

What git ignores is asked of git once for the whole vault, beside `_wire_problems`'s own reading, and not by reading `.gitignore`: `git check-ignore` or the list `git ls-files` gives of what is tracked and what is untracked and not ignored answers for the notes, for the wikilink pass and for the base alike. A directory that is no git checkout, or a git that cannot answer, leaves the vault read whole as it is today, so a copy of the vault is checked and nothing is passed over for want of git.
