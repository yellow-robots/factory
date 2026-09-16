---
type: seed
status: open
summary: The goal travels as a sentence on a command line and the report as five lists; the input should be a spec in the world and the output machine-readable for the next step.
value: 3
effort: M
goal:
acceptance:
version:
crossed_to:
created: 2026-09-16
---

## Evidence

Owner's item 4, 2026-09-16. Both builder runs took their goal from the shell; the spec that
justified it lived in a plan file the world could not see. `report.json` and `numbers.json` are
already typed; the gate and `record-as-table` are their first machine readers.

## Idea

The goal argument becomes a path to a seed at status spec; the builder reads it as part of the
world; the run's numbers name the spec. Output stays as it is until a consumer needs more.
