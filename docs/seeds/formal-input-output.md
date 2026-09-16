---
type: seed
status: open
summary: The goal travels as a sentence on a command line and the report as five lists; the input should be a seed in the checkout and the output machine-readable for the next step.
value: 3
effort: M
version:
---

## Evidence

Owner's item 4, 2026-09-16. Both builder runs took their goal from the shell; the spec that justified it lived in a plan file the checkout could not see. `report.json` and `numbers.json` are already typed; the gate and `record-as-table` are their first machine readers.

## Idea

The goal argument becomes the path of a seed at status spec; the builder reads the seed as part of the checkout, its `## Goal` is what it is asked; the run's numbers name the seed. Output stays as it is until a consumer needs more.
