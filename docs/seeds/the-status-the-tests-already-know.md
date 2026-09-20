---
created: 2026-09-20
type: seed
status: open
summary: The gate checks that a building seed has tests and never that a seed with tests is building, so a seed can carry a status its own evidence contradicts for a whole version.
value: 3
effort: S
version:
---

## Evidence

2026-09-20. [[the-catch-rate-that-decides-the-role]] sat at `status: spec` with **23 tests naming it, all green, and 13 merged build commits**. The owner noticed reading the vault. `uv run gate.py check` had run after every one of those builds and said nothing.

The check is at `gate.py:624`:

```
if rank >= STATUSES.index("building") and not _named_by_a_test(root, path.stem, docstrings):
```

A seed at `building` or beyond must be named by a test. The converse is never asked, so a seed named by a test may sit at `open` or `spec` indefinitely and the gate agrees with it.

**It would not have shipped.** `gate.py release` refuses a version holding a seed that is not `done` or `rejected` (`gate.py:1022`), so the error would have surfaced at the release and been fixed then. What it cost instead is the whole working day carrying a status its own repository contradicted, in the vault the owner reads to know what is happening, at exactly the moment the seed's work was finishing and its state was worth knowing.

This one is worth writing down because of what the factory says about itself. `AGENTS.md`: *the state of the work is never narrated here; it is derived from git and the files.* A seed's `status` is the one place the factory does narrate, and the bargain is that the gate holds the narration against what is derivable. It holds it in one direction. A test docstring naming a seed is as derivable as anything in the repository, and it is the very fact the gate already reads for the other direction, so nothing needs to be discovered to close this -- only asked twice.

## Idea

A status the repository disagrees with is a problem the gate reports.

A seed named by a test in a `test*.py` at the root is at least `building`, and one whose tests are green with a build merged against it is `done`. The gate already reads both halves -- the docstrings for the first and the suite for the second -- so what is missing is the question, not the evidence.

Two edges decide how loud it should be. A test naming a seed is committed *red* before the build, so between that commit and the green build the seed is `building` and its tests fail, which is the normal state of a version in flight and must not be a problem. And a seed may be `rejected` with tests still naming it while they are removed, which is a legitimate few minutes and not a lie. The rule that survives both is the weak one: a seed named by a test is not `open` and not `spec`.

Whether `done` should also be derived is the interesting half and the answer is probably not. `done` means the attended agent has read the diff, taken the review and judged its findings, and no amount of green says that happened. Deriving it would make the gate agree with a seed the moment its tests passed, which is the one moment somebody should still be looking.
