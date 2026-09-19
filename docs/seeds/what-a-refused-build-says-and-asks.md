---
created: 2026-09-20
type: seed
status: open
summary: The refusal path of a build asks the store a weaker question than it means, asks it without a guard, and no longer says how the run ended.
value: 3
effort: S
version:
---

## Evidence

2026-09-20, from the independent review of run 20260919T225154Z, each of the three read in the code by the attended agent before it was written here. All three are the refusal path of `build.py` after [[the-work-a-capped-run-leaves]] reordered it, and none of them can push a build that should not be pushed -- they are what the path says and what it trusts.

**It asks whether the record is in the tree, not whether the store took it.** `_record_taken` runs `git cat-file -e HEAD:<stamp>` in the store. That answers "is a path named `<stamp>` in the store's HEAD tree", which is the same question only because `commit_record` commits with a pathspec -- `builder.py:1280`, `commit -q -m <name> -- <name>` -- so a refused record left staged by a best-effort `_unstage` cannot be swept into HEAD by the next build's commit. Drop the pathspec, or run `git commit -a` in the store by hand, and a record the store refused becomes a record `_record_taken` says yes to. The boundary holds today on an invariant two modules away that no test states.

**It asks without a guard.** `_record_taken` calls `_run` unguarded, on the path of every build including the green ones, while every other `_run` on that path is wrapped. `_run` passes `timeout=120`, so it raises `TimeoutExpired`, and raises `FileNotFoundError` if git goes away between the builder's last call and this one -- seconds apart, with one `commit_record` between them. The function's own docstring says a store that cannot answer for the record "answers no"; a git that cannot run does not answer no, it raises through `main`. Nothing is pushed, which is the safe direction, but the command prints the record's path and then a traceback: no single line, no `refs/notes/factory` note on the head it was asked of, and no exit through `refused()`, which is what every other failure gets and what `test_a_failed_build_says_one_line_and_the_note_names_the_record_by_its_stamp` pins for them.

**It no longer says how the run ended.** `refused(how)` prints the reason for the refusal and `_leave_note` writes that same line. Before the reordering a capped run was refused first, so the note said "the run was capped"; now it falls through and the note carries the substantive reason instead -- "the check is red", "the check did not run". AGENTS.md says the note is "one line naming the record and how it ended", so the part that is gone is the documented part. The record still names it, so nothing is lost, only put one hop away -- and asymmetrically, since the same change added `Stopped-By` to the *successful* build's commit for exactly this purpose, so that a reader of the branch need not hold the store.

## Idea

The refusal path says what it claims and asks what it means.

The note names how the run ended as well as why the build was refused, which is one line carrying both rather than one replacing the other, and restores what AGENTS.md already says of it. The guard around the store's answer is the one every other git call on that path already has, so a git that cannot run refuses the build through `refused()` like everything else rather than through a traceback. And the question put to the store either becomes the one that is meant -- did the store take this record -- or the invariant it leans on gets a test of its own, so that dropping the pathspec in `commit_record` breaks something loudly rather than quietly widening what counts as taken.

None of the three is urgent and none of them can push a bad build, which is why this is one small seed rather than three. What makes it worth building is that all three are on the path that exists to refuse, and a refusal path that is less careful than its own docstring is the wrong place to be relaxed.
