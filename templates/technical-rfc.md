---
type: technical-rfc
title: "<feature name>"
status: draft              # draft | in-review | approved | superseded
stage: 3
home: epic-issue           # canonical home = the epic GitHub Issue; this file is the draft/mirror; slices → task Issues
source_feature_rfc: "[[<feature-rfc note>]]"   # the feature RFC lives in Obsidian → wikilink; resolved by our tooling/CLI, not GitHub's renderer
target_repo: platform      # platform | website
base_ref: origin/main      # the tree this technical RFC was written against
created: "<YYYY-MM-DD>"
---

# Technical RFC — <feature name>

> The job of this technical RFC: make stage-4 tasks **self-contained for codebase-fit** — so a dev
> implements from the Issue alone, never opening Obsidian. Method: source-verified, name exact files, flag
> hidden contracts. **Read the tree; don't guess.** This is the stage external tools don't solve — it's ours.
>
> **This is the airlock.** Stage 3 is the *single* Obsidian→GitHub crossing: **read** the feature RFC from
> the vault, **write** this technical RFC on the epic Issue. Cite the feature RFC; never copy it. Nothing
> downstream of here reaches back into Obsidian.

## Outline (for the pre-gate)
<!-- The touched-files list + the 1-2 biggest risks, before the full technical RFC. Human approves the shape first. -->

## Touched modules / files
<!-- Exact paths in the CURRENT repo this feature will create or modify, one line each. -->
- `path/to/file` — <what changes>

## Existing patterns to follow
<!-- For each change, the in-repo example to imitate. Cite it. -->
- <pattern> — see `path/example:NN`

## Integration points
<!-- Callers/callees, schemas, CI, public interfaces this touches. -->

## Conventions
<!-- Naming, error handling, test layout — anything a newcomer would get wrong. -->

## Hidden contracts / anti-patterns to avoid
<!-- Things the code accepts but doesn't honour; foot-guns; "looks right but isn't". -->

## Per-task context slices
<!-- ONE self-contained paragraph per anticipated task. This text is pasted verbatim into the Issue's
     "Context & links". It must stand alone (cite exact files); no Obsidian needed. -->
### Slice A — <task title>
<!-- modules to touch · pattern to follow · integration point · the one gotcha — cite files -->

### Slice B — <task title>


---
## How to produce this technical RFC (checklist)
- [ ] **Read the feature RFC from the vault** (its `source_feature_rfc`); cite it, don't copy — this technical RFC is a *projection* of the feature RFC onto the code, not a duplicate.
- [ ] Enumerate touched files by **reading the tree**, not guessing.
- [ ] For each change, name the **existing pattern** to follow and cite an in-repo example.
- [ ] List **integration points** (callers, callees, schemas, CI).
- [ ] State the **conventions** a newcomer would miss.
- [ ] Flag **hidden contracts / anti-patterns**.
- [ ] Write one **self-contained slice per task**, citing exact files — re-read each as if you were the
      dev with no other context. If it needs Obsidian, it's not done.

*Next stage:* **task decomposition** (`task.md`) turns each slice into a Ready Issue.
Gate before then: **review the technical RFC** (human).
