---
created: 2026-09-16
type: seed
status: open
summary: A read-only role pointed at a diff with the goal "find defects", so a build is judged by a cold session before the attended agent reads it.
value: 4
effort: M
version:
---

## Evidence

Every diff so far was read by the attended agent, a model in another harness. The independent reviews of v0.2 and v0.3 found real defects the builder and the attended agent had missed. Pinned by the owner on 2026-09-16 until the builder is validated.

2026-09-17, counted from the notes by the attended agent: the eight notes of `docs/reviews/` hold 60 findings, 15 defects and 45 smells, every one reproduced by the attended agent, all in builds whose check was green; every defect became a test, and of the smells 23 became tests, 2 seeds and 20 were judged `none`. Of the seven seeds the factory built from a seed's path, six had a green first build and five took a second red commit after a review, four of them after a green first build (analyst-on-api-models), and built-by-trailer took four reviews in v0.13, three of which said the tests did not pin the Goal. The builder builds what the tests ask and what they do not ask is found by review, so review is where the factory's quality is won today, and it is held outside the factory: the reviewers are Opus subagents of the attended agent's harness, prompted by hand, their findings typed into the note by the attended agent, no record of their runs kept.

## Idea

The observer's tools plus a `diff()` function, a typed report of findings with severity, path and line, and a verdict. First eval case: its report on a known diff against the attended agent's. An eval before the role, as analyst-on-api-models has it, a replay over the notes: a candidate is given a build's commit, in a world exported at it, and the build's Goal, and its report is graded against the note on file, the defects it finds of those reproduced, and of its own findings those the attended agent reproduces, with two references beside it, the Opus review on file and a review that finds nothing. As a step of the loop its input is a range of commits on a pushed branch and its output a draft of the review note on that branch, not a reply in the attended agent's session (build-from-a-pushed-branch). A model of DeepSeek's class runs it in the builder's loop; if its grades are poor, tools-as-mcp is how a frontier model takes the role under the same walls, recorded. The owner's pin stands.
