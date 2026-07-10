---
type: technical-rfc
title: "<feature name>"
status: draft              # doc lifecycle: draft | active | rejected | superseded (NOT the board's Status)
stage: 3
home: epic-issue           # canonical home = the epic GitHub Issue; this file is the DRAFT (authoring only)
source_feature_rfc: "[[<feature-rfc note>]]"   # Obsidian wikilink — resolved by check_links/our CLI, NOT GitHub
target_repo: yellow-robots      # yellow-robots | website
base_ref: origin/main      # the tree this technical RFC was written against
created: "<YYYY-MM-DD>"
---

> **This is the airlock.** Stage 3 is the *single* Obsidian→GitHub crossing: **read** the feature RFC from
> the vault, **write** this technical RFC on the epic Issue. Cite the feature RFC; never copy it. Nothing
> downstream of here reaches back into Obsidian.
>
> **What gets filed:** the epic Issue takes the **feature name as its title** and **only the body between the
> `ISSUE BODY` markers** as its description — clean prose. The **frontmatter above** is authoring scaffold so
> `check_links` can resolve the crossing-link on this *draft*; the **checklist at the bottom** is an authoring
> aid. Neither goes on the Issue — GitHub doesn't render frontmatter, so raw YAML shows as noise. Run
> `check_links` on this draft *before* filing; the filed Issue carries provenance as the one **Source** line
> below, not as frontmatter.

# Technical RFC — <feature name>
<!-- ↑ the Issue TITLE (use the feature name). The filed body starts below the marker. -->

<!-- ═══════════════ ISSUE BODY · file from here ↓ ═══════════════ -->

**Source:** feature-RFC [[04 projects/yellow-robots/features/<slug>/feature-rfc]] (Obsidian product brain) · written against `origin/main`.
<!-- The ONE crossing-link — echoes the frontmatter's source_feature_rfc + base_ref. Link format follows the
     TARGET's home: the feature-RFC lives in Obsidian → a [[wikilink]] (our tooling resolves it; GitHub renders
     it as literal text, which is fine for provenance). A GitHub target would be a URL/#issue instead. Cite up
     to the feature-RFC only — no sibling links. -->

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
<!-- ONE self-contained paragraph per anticipated task. This text is pasted verbatim into each task Issue's
     "Context & links". It must stand alone (cite exact files); no Obsidian needed. -->
### Slice A — <task title>
<!-- modules to touch · pattern to follow · integration point · the one gotcha — cite files -->

### Slice B — <task title>

<!-- ═══════════════ ↑ END ISSUE BODY · file to here ═══════════════ -->

---
## Authoring scaffold — NOT filed on the Issue

**Pre-gate (shape first):** before writing the body, post the **touched-files list + the 1–2 biggest risks**
and get the shape approved (human). Then flesh out the body above. *Gates review the plan, not the output.*

**Checklist to produce the body:**
- [ ] **Read the feature RFC from the vault** (its `source_feature_rfc`); cite it, don't copy — this technical RFC is a *projection* of the feature RFC onto the code, not a duplicate.
- [ ] Enumerate touched files by **reading the tree**, not guessing.
- [ ] For each change, name the **existing pattern** to follow and cite an in-repo example.
- [ ] List **integration points** (callers, callees, schemas, CI).
- [ ] State the **conventions** a newcomer would miss.
- [ ] Flag **hidden contracts / anti-patterns**.
- [ ] Write one **self-contained slice per task**, citing exact files — re-read each as if you were the
      dev with no other context. If it needs Obsidian, it's not done.
- [ ] **Check-gate parity:** a slice that changes `check_cmd` or its prerequisites (toolchain,
      provisioning, new gate scripts) must list the server-CI workflow change among its deliverables —
      the in-build check gate and server CI are the same contract on two hosts.
- [ ] Run **`check_links`** on this draft (its `source_feature_rfc` must resolve) before filing.

*Next stage:* **task decomposition** (`task.md`) turns each slice into a Ready Issue.
Gate before then: **review the technical RFC** (human).
