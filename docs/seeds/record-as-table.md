---
type: seed
status: open
summary: Eight records and counting; one script that turns every numbers.json into rows is the outcomes panel with no new state anywhere.
value: 4
effort: S
version:
---

## Evidence

Reading a run today means opening `numbers.json` by hand; comparing two means opening both. The evals need every run of a case side by side, and no orientation page can name the last runs without narrating them.

## Idea

`runs.py`: one row per record, columns the numbers' keys, filters by goal, world commit and version; the same formula for rank and the same fields the Base uses, so the machine and the vault agree. Reads the committed records, writes nothing.
