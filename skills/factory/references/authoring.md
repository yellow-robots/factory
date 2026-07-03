# Authoring — the upper pipeline

> **When to load this reference:** writing any upper-pipeline artifact — product-spec, feature-rfc,
> technical-rfc, or task. For doc types, the iteration model, and frontmatter rules, see
> [`documentation-model.md`](documentation-model.md). For vault editing safety (avoiding overwrites,
> working on the right file, saving discipline), see
> [`documentation-model.md` → *Editing-safely*](documentation-model.md#editing-safely). For gate
> mechanics, see [`gates.md`](gates.md). For closing (promote-to-Ready onwards), see
> [`closing.md`](closing.md).

---

## Steps

### 1. product-spec

Author in the brain (Obsidian), from `templates/product-spec.md`. WHAT/WHY only — no tech, no
implementation decisions.

**Content:** acceptance criteria in **EARS** (`WHEN … THE SYSTEM SHALL …`, or ubiquitous
`THE SYSTEM SHALL …` for static content). `type: product-spec`, `status: draft` (→ `active` at the gate).
Named `01-<slug>.md` in `<component>/iterations/<n>-<slug>/`.

**How to work:** open the `01` draft early and evolve WHAT/WHY *there* with the human, in Obsidian. Don't
brainstorm in the terminal and paste a finished spec — the doc is where the thinking lives. The spec must
be developed *in* the doc, not assembled from a finished outline.

**Judgment:** does the spec state WHAT and WHY in enough detail that a reviewer can judge whether a
proposed design is sound, without knowing how it will be built? If not, it is not ready.

**Gate: *spec-ready* (human).** A human reads the spec and decides it is complete enough to design against.
For the review discipline that feeds this gate, see [`reviewing.md`](reviewing.md).

---

### 2. feature-rfc *(only if earned)*

See [`documentation-model.md`](documentation-model.md) — *The document types* for the earned-test. If
the change is small or the approach obvious, go directly to step 3 (floor: product-spec → task(s)).

**Content:** the approach, decision, scope, non-goals. `source_spec:` the product-spec as a
`[[wikilink]]`. Author in Obsidian, from `templates/feature-rfc.md`.

**How to work:** send the outline to the human first — it is cheaper to redirect here than after full
authoring. Then draft in full.

**Judgment:** is the approach worth arguing, or is it routine? Would skipping this layer cost a reviewer
meaningful context about *why* this approach over alternatives?

**Gate: *approve-RFC* (human).** Human reviews the outline, then the draft. For the review discipline,
see [`reviewing.md`](reviewing.md).

---

### 3. Cross the airlock → technical-rfc

Author on the **epic GitHub Issue** from `templates/technical-rfc.md`. This is the Obsidian→GitHub
crossing: the artifact **cites, never copies** the feature-rfc — there is no mirror to drift. Carry
`source_feature_rfc:` as a `[[wikilink]]`. (On the **floor** there is no technical-rfc — the crossing
is product-spec → task, and the task cites `source_spec:`; skip to step 4.)

**Content required:**
- Name the **exact files / patterns / integration points** against the *current* tree.
- Write a **per-task context slice**: the minimal codebase-fit paragraph a dev needs, citing
  `repo/path.py:NN`. A task derived from this must be self-contained — an implementer must never need
  to open `AGENTS.md` to proceed.

**Before filing:** run `check_links` on the draft (see [`gates.md`](gates.md)). File as **clean prose**
— never raw frontmatter (GitHub renders frontmatter as noise).

**Gate: *review the technical-rfc* (human).** For the review discipline that feeds this gate, see
[`reviewing.md`](reviewing.md).

---

### 4. task

One GitHub Issue via the Task DoR form, from `templates/task.md`.

**Required sections:** Goal · Acceptance (EARS criteria as `- [ ]`) · Context & links (paste the
technical-RFC slice — self-contained) · Test expectations · Constraints / out of scope · Size.

**Run `check_task`** (see [`gates.md`](gates.md)) before promoting. **One task = one PR**; if a task
would need two PRs, split it into sub-issues.

**Judgment:** is the task self-contained? Can an implementer produce a correct PR from this Issue alone?
Is every acceptance criterion verifiable by an independent tester who has not seen the implementation?

For promote-to-Ready and onwards, see [`closing.md`](closing.md).
