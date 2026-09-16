---
type: seed
status: building
summary: The date a seed was born is a column the owner reads; it comes back at the top of the frontmatter, with the gate allowing it and checking its shape.
value: 2
effort: S
version: v0.5
---

## Evidence

On 2026-09-16 the owner moved `created` to the top of the seed template in Obsidian, which re-serialised the frontmatter; `{{date}}` is not valid YAML and came out as a mapping, and the field was then dropped for lack of a consumer. The owner wants it back: the Born column of the backlog and the order of equal ranks are its consumers.

## Goal

`gate.py` knows the seed field `created`: allowed beside type, status, summary, value, effort and version, required from `open` on, and shaped `YYYY-MM-DD`; a missing or misshaped `created` is a problem naming the file and the field. The templates stay exempt. Nothing else in `check` changes. The tests in `test_gate.py` whose docstring names this seed define the behaviour.

After the build, by the attended agent: `created` first in the seed template as the quoted string `"{{date}}"`, which YAML accepts and the Templates plugin fills; the backlog shows it as Born and breaks rank ties by it; every seed gets the date of the commit that created it.
