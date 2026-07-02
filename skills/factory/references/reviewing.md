# Reviewing — spec and RFC review

> **When to load this reference:** reviewing a product-spec or feature-rfc (adversarial steelman →
> completeness → ranked findings → human gate). For the fold-in vs. standalone decision, see
> [`documentation-model.md`](documentation-model.md) — *Reviewing a doc*. For technical-rfc and
> lower-pipeline review, the dev-runner handles that natively (see [`pipeline.md`](pipeline.md)).

---

## Steps

### 1. Adversarial steelman

Before identifying flaws, restate the strongest version of the argument the doc makes. This forces
genuine understanding of the intent before any critique, and surfaces the assumptions the doc relies on.

**Judgment:** can you construct the steelman? If not, the doc is underspecified — return that as a
finding before any other critique. "I cannot steelman this" is a blocker, not a note.

### 2. Completeness — within the stated scope

Check that every claim and criterion in the doc is complete, internally consistent, and achievable
**within the scope the doc itself declares.** Do **not** introduce new scope: if the doc does not claim
to cover X, completeness for X is not a finding here. New scope is a separate proposal for the human
to decide, never a finding within the current review.

**Judgment:**
- Is there missing detail that would block an implementer or make acceptance criteria unverifiable?
- Are acceptance criteria in EARS form (`WHEN … THE SYSTEM SHALL …`) and testable by an independent party?
- Are non-goals explicit enough to prevent scope creep downstream?

### 3. Rank findings

Group findings by severity — state blockers first, unambiguously:

- **Blockers** — the doc cannot gate forward without addressing these. Examples: missing acceptance
  criteria, undefined behavior in a required path, self-contradiction, a decision whose rationale is
  absent and cannot be inferred.
- **Improvements** — addressable before gating but not blockers. Examples: clarity, completeness within
  stated scope, naming that will confuse the implementer.
- **Notes** — low-stakes observations for the human to decide (nice-to-haves, future considerations).

Do not bury a blocker in a long list. A reviewer who must scan the whole list for blockers is a review
that will miss them.

### 4. Fold-in or standalone?

Apply the rule from [`documentation-model.md`](documentation-model.md) — *Reviewing a doc*: **light
findings fold in; heavy findings earn a standalone doc.** When unsure, fold in — standalone is earned,
not the default.

- **Fold in (default):** durable findings go into the reviewed doc's sections (Open questions,
  Alternatives, Consequences) or, for build-level points, into the technical-rfc and task acceptance
  criteria. The `status` transition (`draft → active`) is the record that review happened.
- **Standalone:** when the critique itself carries durable why the folded-in doc won't show — an
  adversarial, verified, multi-finding assessment — freeze it as a supporting `research` or `note` in
  the iteration. Give it its own `NN-slug.md` ordinal, name the reviewer/date/method in the body, state
  what it reviewed, and cite it in prose (`[[wikilink]]`) from the reviewed doc. Never via `source_*`
  (those are spine crossing-links only).

### 5. Feed the human gate

State clearly which gate this review is feeding:

- **product-spec review → *spec-ready* gate:** the human reads the review and decides the spec is
  complete enough to design against (proceeds to feature-rfc or technical-rfc).
- **feature-rfc review → *approve-RFC* gate:** the human reads the review and decides the RFC is
  approved to build against (proceeds to technical-rfc).

If the review contains a blocker, say so explicitly at the top — do not make the human dig through
findings to discover that the gate cannot open.

**Invariant:** a review must not create scope. New capabilities, new doc types, new requirements found
during review are proposals to the human for a future iteration, not findings within the current scope.
A review that adds scope has failed its own completeness constraint.
