---
created: 2026-09-17
type: seed
status: open
summary: A review's findings live in the attended agent's session and are narrated in commit messages; whether each became a test, a case or nothing is not derivable, so the growth rule has no step to hold it.
value: 5
effort: M
version:
---

## Evidence

Six independent reviews so far, five in v0.7 and one in v0.9, each a fresh session in this harness; twelve defects and five smells. What each finding became is told in the red commits and the changelog bullets, by hand. The owner's rule of 2026-09-17: every verified defect is judged twice, a test when the factory's code was wrong, a case when the model's behaviour was. Nothing in the repository can say whether a version applied it.

## Idea

A template `docs/templates/review.md` and one note per review in `docs/reviews/`, named by the runs it covered: the reviewer, the runs, and each finding with severity, path, reproduction, `verified` by the attended agent, and `judged` as `test <name>`, `case <name>`, both, or `none` with one line why. The gate checks that a named test exists and names the seed, a named case directory exists, and refuses a release with a verified finding left unjudged; AGENTS.md's loop gains the step. The note's shape is the reviewer role's output when that role is built, so the role writes what the attended agent writes today.
