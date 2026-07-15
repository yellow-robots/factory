# Closing — promote, merge, freeze, and release

> **When to load this reference:** closing out an iteration — promoting a task to Ready, receiving a
> merged PR (→ Done), freezing Obsidian docs, judging the crossover test, and running a skill release.
> Promote-to-Ready is the **input gate**; merge → Done is the **output gate**. For authoring, see
> [`authoring.md`](authoring.md). For the lower pipeline, see [`pipeline.md`](pipeline.md).

---

## 1. Promote to Ready

**Who:** a human owns the input gate at the design artifacts — a human decides *what* gets built by
setting a product-spec or feature-rfc `active`; no agent ever sets `active`. Below that standing approval,
flipping a governed epic to Ready, promoting its next pre-approved slice, and closing a finished epic are
**mechanical**, fail-closed back to the human on any doubt. A standalone task with no governing design
above it has no standing approval to run on, so it keeps the original per-task human promotion — and its
**body inherits the design gates** (ruled 2026-07-13): governed work's WHAT was adversarially reviewed and
fit-checked upstream before anything crossed; a standalone task's body is that design, so the same cold
gates run on the body itself before the human promote. The pipeline verifies the code *against* the
acceptance criteria — unreviewed criteria make a flawed build pass green, which is why saving this gate
buys brittleness, not time (the org-level twin is `AGENTS.md`'s *hands-on is not unreviewed*: who authors
is orthogonal to whether it is independently verified).

**Checklist before promoting:**
- [ ] `check_links` is green on the technical-rfc (see [`gates.md`](gates.md)).
- [ ] `check_task` is green on the task (see [`gates.md`](gates.md)).
- [ ] **Standalone task only:** the body's design gates ran cold — an independent adversarial review and
  an architect fit check — and their verdicts are recorded on the issue trail (record-before-flip).
- [ ] The task is self-contained: an implementer can produce a correct PR from the Issue alone.
- [ ] Size is declared; if the task would need two PRs, it is already split into sub-issues.

**Gate disposes:** the DoR gate in the runner re-checks these structurally on claim — a task that passes
human promote but fails DoR is set `Needs-info`.

---

## 2. Merge → Done

**Who:** the **factory itself, for an armed repo** — otherwise a human. The runner's deterministic
merge evaluator (see [`pipeline.md`](pipeline.md)) checks CI-green, freshness against `main`'s tip, a
terminal clean `APPROVE`, and the review-rank >= build-rank gate (the reviewer is never weaker); an
**armed** repo (manifest
`auto_merge = true`, shadow phase complete, host sentinel not thrown) that passes them all is
squash-merged by the factory with a durable `YR-MERGE: MERGED` record. Every other repo stays in
**shadow**: a loud `YR-MERGE-SHADOW` would-merge/would-block record, then a human reviews and merges.
Native close → `Status=Done` either way.

- Merge ≠ ship. `main` is not production; deploy stays separate and attended.
- Shadow completion is mechanical (a rolling window of clean, unreverted merge records — see
  [`pipeline.md`](pipeline.md)); completion *permits* arming, and arming stays the human's manifest
  edit. Un-arm or throw the sentinel to return a repo to the human gate at any time.
  The **durable rule** is *a human decides what to build*, not *a human merges every PR*.

---

## 3. Doc-side freeze

When the PR merges, the iteration's Obsidian docs become immutable records:

- Set `status: active` on any doc still at `draft`; do not edit the body to match later reality.
- A later change gets its *own* later iteration. "Amend the spec to match what was actually built" is
  the wrong move — the drift is recorded by the *next* iteration, not by rewriting the frozen one.
- The technical-rfc on the epic Issue stays as the permanent record; the PR carries the link to the
  resulting code.
- Verify every doc that crossed carries its `crossed_to` stamp — set **at the crossing**, not here
  (see [`documentation-model.md`](documentation-model.md) — *Identity & navigation*). Stamp any doc
  found missing one: epics self-close, so this checklist is the backstop, not the act.
- Tombstones land at accept, not here (`status: superseded` + `superseded_by`, stamped in the same
  session — see [`documentation-model.md`](documentation-model.md) — *Lifecycle*). This checklist verifies every supersession pair the iteration's declarations created: run `check_supersession.py --sweep --scope <component>`
  and stamp only what's found missing — the accept session is the act, this checklist is the backstop,
  exactly like the `crossed_to` bullet above. If the shipped change instead **migrated** a doc (moved,
  decision unchanged), retire it by kind per [`migrating.md`](migrating.md) step 4.
- **Write at ship** (the maintenance-contract trigger, see [`documentation-model.md`](documentation-model.md)
  — *The maintenance contract*): walking the grounding list is the **architect's** ship-walk where that
  role is earned on the component, the **closing session's** otherwise.

This is **shipping freezes the why** from the documentation model; see
[`documentation-model.md`](documentation-model.md) — *Two principles*.

---

## 4. The crossover test

**Ruled 2026-07-06 — carried here whole, in the ruling's own wording.** At each close, the candidate set
includes product iterations: factory work must beat the product line on the three standing axes —
*quality control per iteration · incremental understanding · cost control* — the ruling's own order, kept
verbatim (the value-scoring line in [`documentation-model.md`](documentation-model.md) — *The
ideas-backlog* — deliberately words the same three axes in the front door's order; the two are not
harmonized). The factory is ready when no factory candidate wins. And a gap surfacing mid-product
re-enters the candidate set having just proven its value.

---

## Skill-release block

This block is **standalone** — run it for any skill release, including a hotfix re-release, without the
iteration ship/freeze steps above.

### When

After the iteration's PR merges (or on a hotfix) — and always **before** any consumer is repointed to
the new content or its previous home is demoted.

### Steps

1. **Version bump** — update `version` in `.claude-plugin/plugin.json` to the new semver. Keep
   `description` in plugin.json in sync with the `description` field in `skills/factory/SKILL.md` —
   they must agree exactly.

2. **Release scan** — verify all of the following are true before shipping:
   - No dangling router row in `SKILL.md`: every row in the Operations table links a file that exists
     under `references/`.
   - No orphan reference: every file under `references/` has a corresponding router entry.
   - `SKILL.md` is < 500 lines.
   - The `description` in `SKILL.md` frontmatter and in `plugin.json` agree exactly.
   - **The consumer scan is green:** nothing in the repo or org docs still cites a superseded content
     home as the *living* copy (`tools/check_model_refs.py`, fail-closed).

3. **Ship before demote** — the release (merge to `main`) ships the new content **before** any
   dependent consumer is repointed and before the superseded source is demoted: the living content must
   never exist nowhere authoritative. (Session note: bundled reference files hot-reload only via
   `/reload-plugins` or a fresh session — ship as one coherent version so router and references never
   split.)

### Gate

The release scan must be fully green. A dangling link, orphan reference, or description mismatch is a
blocker — do not ship until resolved.
