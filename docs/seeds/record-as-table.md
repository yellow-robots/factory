---
type: seed
status: open
summary: Nine records and counting; one script that turns every numbers.json into rows is the outcomes panel with no new state anywhere.
value: 4
effort: S
goal:
acceptance:
version:
crossed_to:
created: 2026-09-16
---

## Evidence

Reading a run today means opening `numbers.json` by hand; comparing two means opening both. The
evals need every run of a case side by side, and the front door's Now section needs the last runs.

## Idea

`runs.py`: one row per record, columns the numbers' keys, filters by goal, world commit and
version; the same formula for rank and the same fields the Base uses, so the machine and the vault
agree. Reads the committed records, writes nothing.
