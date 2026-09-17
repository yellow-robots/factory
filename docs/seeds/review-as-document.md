---
created: 2026-09-17
type: seed
status: done
summary: A review's findings live in the attended agent's session and are narrated in commit messages; whether each became a test, a case or nothing is not derivable, so the growth rule has no step to hold it.
value: 5
effort: M
version: v0.10
---

## Evidence

Six independent reviews so far, five in v0.7 and one in v0.9, each a fresh session in this harness; twelve defects and five smells. What each finding became is told in the red commits and the changelog bullets, by hand. The owner's rule of 2026-09-17: every verified defect is judged twice, a test when the factory's code was wrong, a case when the model's behaviour was. Nothing in the repository can say whether a version applied it.

## Idea

A template `docs/templates/review.md` and one note per review in `docs/reviews/`, named by the runs it covered: the reviewer, the runs, and each finding with severity, path, reproduction, `verified` by the attended agent, and `judged` as `test <name>`, `case <name>`, both, or `none` with one line why. The gate checks that a named test exists and names the seed, a named case directory exists, and refuses a release with a verified finding left unjudged; AGENTS.md's loop gains the step. The note's shape is the reviewer role's output when that role is built, so the role writes what the attended agent writes today.

## Goal

A note of type `review`, one per review, made from `docs/templates/review.md`, is checked by `gate.py check` as a seed is, so `release`, which runs check first, refuses a version whose reviews are not whole. Its frontmatter holds the template's fields and no other: `created`, `type`, `runs`, `reviewer`. `runs` names the records reviewed, their stamps separated by spaces, each a directory `runs/<stamp>` of the repository, and the note is named after one of them, `<stamp>.md`; `reviewer` is not empty; `created` is `YYYY-MM-DD`. The body is read as the builder reads a note, `builder.note_text`, comments out, a comment left open a problem of its own. Its findings are the level-three headings of the body, one finding each, titled by the heading, and a finding's problem names it by that title; anywhere in a finding's section the lines `severity:`, `verified:` and `judged:` are read: `severity` is `defect` or `smell`; `verified` is `yes` or `no`; `judged` is `test <name>`, `case <name>` or `seed <name>`, several of them separated by commas, or `none:` followed by a reason, and a finding verified `yes` must have one, while a finding verified `no` may leave the line out. A test named is a test method or class of that name in a `test*.py` at the root; a case named is a directory `cases/<name>`; a seed named is `docs/seeds/<name>.md`. Every problem is one line starting with the note's path, as a seed's is. From the review: a stamp in `runs` and the name after `test`, `case` or `seed` are one path segment, not empty, not `.` or `..`, with no `/` or `\`, and any other is a problem naming it, never a path joined and looked up; the `severity:`, `verified:` and `judged:` lines are lines of the finding's prose, so a line inside a fenced or an indented code block is never read as one, the fence rules the builder's `note_text` follows; and a `judged:` with nothing after it, or with an empty piece between commas, is reported as `has no judged`. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
