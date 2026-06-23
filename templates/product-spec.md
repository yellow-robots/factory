---
type: product-spec
title: "<feature name>"
status: draft              # draft | in-review | ready | superseded
stage: 1
home: obsidian
source_intent: "[[<one-line intent note>]]"   # resolvable wikilink — the crossing-link checker asserts it exists
target_repo: yellow-robots      # yellow-robots | website
created: "<YYYY-MM-DD>"
---

# Product spec — <feature name>

> Spec discipline: **WHAT and WHY only — no tech stack, no file names, no "how".** Naming a module
> belongs in the technical RFC, not here. Every acceptance criterion must be expressible as a test.

## Why
<!-- The product reason this exists. One short paragraph: who is helped and how. -->

## What
<!-- The observable behaviour from the user's / product's point of view. No implementation. -->

## Acceptance criteria (EARS)
<!-- Easy Approach to Requirements Syntax — each line testable, 1:1 with a future test. -->
- WHEN <condition / event> THE SYSTEM SHALL <observable behaviour>.
- WHEN <…> THE SYSTEM SHALL <…>.

## Out of scope
<!-- What this explicitly does NOT do — bounds the RFC. -->

---
*Next stage:* a **feature RFC** (`feature-rfc.md`) cites this spec and chooses the approach.
Gate before then: **spec ready** (human). A criterion that can't become a test isn't done.
