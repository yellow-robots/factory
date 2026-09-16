---
created: 2026-09-16
type: seed
status: open
summary: The gate and the builder read `## Goal` by different rules, so a seed can pass the gate and fail every build with a usage error.
value: 3
effort: S
version:
---

## Evidence

The third review of formal-input-output, 2026-09-16, ran both readers over the same notes. The gate's `_goal_text` says a Goal has text when its only text is a `%%` comment, when `## Goal` sits inside a `%%` block, and when the heading is indented four spaces; the builder's `read_seed` refuses all three as a usage error. A Goal whose text starts with `### Details` is the other way round: the gate reports `seed has no ## Goal with text`, the builder reads it. The gate's reader is a dozen lines from v0.4; the builder's, `note_text` and `goal_section`, is v0.7's, with fences, code spans and comments.

## Idea

The gate reads the section with the builder's reader, one definition of the Goal for both, so `seed has no ## Goal with text` means exactly that the builder would refuse the note.
