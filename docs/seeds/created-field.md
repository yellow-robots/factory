---
type: seed
status: open
summary: The date a seed was born is a column the owner reads; it comes back at the top of the frontmatter, with the gate allowing it and checking its shape.
value: 2
effort: S
version:
---

## Evidence

On 2026-09-16 the owner moved `created` to the top of the seed template in Obsidian, which re-serialised the frontmatter; `{{date}}` is not valid YAML and came out as a mapping, and the field was then dropped for lack of a consumer. The owner wants it back: the Born column of the backlog and the order of equal ranks are its consumers.

## Idea

`created` first in the template, as the quoted string `"{{date}}"` that the Templates plugin fills and YAML accepts; from `open` on a seed carries a date `YYYY-MM-DD` and the gate checks the field is present and shaped so; the backlog shows it as Born and breaks rank ties by it; the sixteen seeds get their date back from the commit that created them.
