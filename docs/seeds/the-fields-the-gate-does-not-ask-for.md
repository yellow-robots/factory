---
created: 2026-09-21
type: seed
status: open
summary: The template names reporter and kind and the gate asks for neither, so a seed can be filed without saying who saw it or what it moves, and 48 seeds at done and rejected say nothing yet.
value: 3
effort: S
reporter: owner
kind: integrity
version:
---

## Evidence

2026-09-21, at 5e44116, by the owner with the attended agent, from an audit of the 35 open seeds against HEAD. The template gained two fields that day, `reporter` -- owner, attended agent, review, reviewer, research -- and `kind` -- cost, quality, measurement, integrity, autonomy, scalability -- and the 35 open seeds carry them; the 48 at `done` and `rejected` do not. `gate.py:203` to `206` refuses a field the template does not list, and `gate.py:216` to `232` asks every seed for `summary`, `value`, `effort` and `created` by name, in code; nothing reads the template's comment, so a field the template names is not a field the gate asks for.

What the audit found the fields for. Of the 35 open seeds, 16 name a version in their Evidence, 7 a commit, 17 a run stamp, 7 none of the three; two name no reporter at all. Nine labels had drifted in four days, each on a line number, a count, a constant changed by hand, or a structure added or removed since the seed was born. One of the 35 was found by the factory's own reviewer, about a third by briefed reviews, the rest by the owner, the attended agent and commissioned research; that share is the dial that says how much of its own backlog the factory writes, and nothing counts it.

## Idea

The gate asks for `reporter` and `kind` from `open`, each from its set, on every seed as it asks for `value` and `effort`, and a seed missing either is one problem naming the field; the sets live in the gate as `STATUSES` and `EFFORTS` do. Before the build the attended agent writes both into the 48 seeds at `done` and `rejected`, from their Evidence, in the red commit, so the check is silent the moment the build lands. Whether the Evidence's pin is checked too -- a first paragraph naming a tag or a commit that resolves -- is the spec's to decide; a check that reads prose is what the gate avoids, and the birth commit is derivable from git without one.
