---
type: task
title: "<one-line title>"
stage: 4
home: github-issue         # canonical = the GitHub Issue (the Task DoR form fields ARE the schema)
# Provenance — keep the ONE naming your direct parent; DELETE the rest (an empty or `<placeholder>`
# source_* fails check_links by design). Floor task → source_spec. Under the rfc layers → source_technical_rfc.
source_spec: "[[<product-spec note>]]"         # floor task: the product-spec is the parent (Obsidian → wikilink)
source_feature_rfc: "[[<feature-rfc note>]]"   # feature RFC lives in Obsidian → wikilink
source_technical_rfc: "<epic Issue # or URL>"  # technical RFC lives on GitHub → URL/#issue
size: "S — one PR"         # exact form options: "S — one PR" | "M — one PR, careful" | "Too big — split into sub-issues"
model: sonnet              # sonnet (default) | opus — for opus, also put `model: opus` in the Context body (the runner scans the body)
target_repo: yellow-robots
---

# Task — <one-line title>

**Filed as:** a GitHub Issue via the **Task** form on the target repo (the fields below ARE the
Definition of Ready) · **Source:** the technical-RFC slice — or, on a floor iteration, the product-spec.

> Filed via `.github/ISSUE_TEMPLATE/task.yml`. This template is the authoring aid — fill it, then create
> the Issue. **One task = one PR. Self-contained: a dev implements from this Issue alone.** Required (the
> form rejects empties): Goal, Acceptance criteria, Context & links, Test expectations, Size. For a hard
> build, add `model: opus` on its own line inside Context — the runner reads the override from the body.

## Goal
<!-- One sentence — what is true when this is done. -->

## Acceptance criteria
<!-- The checklist the implementation must satisfy. Tests derive from THIS, not the code.
     Lift the relevant EARS criteria from the product spec. -->
- [ ] <criterion>
- [ ] <criterion>

## Context & links
<!-- SELF-CONTAINED. Paste the technical RFC's per-task slice here (modules to touch, pattern to
     follow, integration point, the gotcha; exact file paths). On a floor iteration there is no
     technical RFC — author the slice directly from the product-spec. A dev should NOT need to open
     Obsidian. If a cited path is this task's own not-yet-built output, name it on a `Deliverable:`
     line (e.g. `Deliverable: \`tools/x.py\` — the new script`) — check_task exempts it from the
     cited-path-exists gate; plain references still resolve. -->

## Test expectations
<!-- How this is verified. The independent tester writes tests against the acceptance criteria above. -->

## Constraints / out of scope
<!-- Optional. Boundaries; things explicitly not to touch. -->

## Size
<!-- Pick one, exact form options: "S — one PR" · "M — one PR, careful" · "Too big — split into sub-issues" -->

---
*Next stage:* the **factory** builds it (implement → independent test → check → independent review → PR).
Gate before then: **promote to Ready** (human, sets Status → Ready). Final gate: **merge** — factory-executed
for an armed repo under fail-closed conditions, human otherwise.
