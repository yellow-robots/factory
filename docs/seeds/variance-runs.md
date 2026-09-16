---
type: seed
status: open
summary: Thinking mode ignores temperature, so no run repeats; every eval case needs three runs and its numbers are distributions.
value: 4
effort: S
goal:
acceptance:
version:
crossed_to:
created: 2026-09-16
---

## Evidence

DeepSeek's documentation: in thinking mode, temperature "will not trigger an error but will also
have no effect" (read 2026-09-15). v0.1 and v0.2 reported temperature 0 and were never at zero.
The parity runs of v0.2 differed in call order between attempts.

## Idea

Run each case three times; report medians and spreads, not single numbers. The role text and the
thinking effort are the two knobs to vary on purpose, one at a time, once a baseline exists.
