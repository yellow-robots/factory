---
created: 2026-09-16
type: seed
status: done
summary: The gate and the builder read `## Goal` by different rules, so a seed can pass the gate and fail every build with a usage error.
value: 3
effort: S
version: v0.8
---

## Evidence

The third review of formal-input-output, 2026-09-16, ran both readers over the same notes. The gate's `_goal_text` says a Goal has text when its only text is a `%%` comment, when `## Goal` sits inside a `%%` block, and when the heading is indented four spaces; the builder's `read_seed` refuses all three as a usage error. A Goal whose text starts with `### Details` is the other way round: the gate reports `seed has no ## Goal with text`, the builder reads it. The gate's reader is a dozen lines from v0.4; the builder's, `note_text` and `goal_section`, is v0.7's, with fences, code spans and comments.

## Goal

`gate.py` reads a seed's `## Goal` with the builder's reader: `builder.note_text` and `builder.goal_section`, imported from `builder.py` beside it, replace `_goal_text`, so `seed has no ## Goal with text` is reported exactly when `builder.read_seed` would refuse the note for its Goal, no heading outside a fence or a comment, or no text under it once the comments are out; and a note with a `%%` comment left open is reported as `seed has a %% comment left open`, since the builder refuses it, the other checks going on. The gate stays deterministic and offline: importing `builder` touches neither the provider, nor the key, nor the network, and the gate's own vault passes silent. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
