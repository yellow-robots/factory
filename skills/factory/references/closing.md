# Closing — promote, merge, freeze, and release

> **When to load this reference:** closing out an iteration — promoting a task to Ready, receiving a
> merged PR (→ Done), freezing Obsidian docs, and running a skill release. Promote-to-Ready is the
> **input gate**; merge → Done is the **output gate**. For authoring, see [`authoring.md`](authoring.md).
> For the lower pipeline, see [`pipeline.md`](pipeline.md).

---

## 1. Promote to Ready

**Who:** a human — always. No agent may set `Status=Ready`. This is the input gate and the only dispatch
signal.

**Checklist before promoting:**
- [ ] `check_links` is green on the technical-rfc (see [`gates.md`](gates.md)).
- [ ] `check_task` is green on the task (see [`gates.md`](gates.md)).
- [ ] The task is self-contained: an implementer can produce a correct PR from the Issue alone.
- [ ] Size is declared; if the task would need two PRs, it is already split into sub-issues.

**Gate disposes:** the DoR gate in the runner re-checks these structurally on claim — a task that passes
human promote but fails DoR is set `Needs-info`.

---

## 2. Merge → Done

**Who:** a human reviews and merges the PR (v1). Native close → `Status=Done`.

- Merge ≠ ship. `main` is not production; deploy stays separate and attended.
- The autonomous-merge iteration (in the brain) is slated to retire this human gate — green
  deterministic gates + an independent reviewer stronger than the builder → the build merges itself.
  The **durable rule** is *a human decides what to build*, not *a human merges every PR*.

---

## 3. Doc-side freeze

When the PR merges, the iteration's Obsidian docs become immutable records:

- Set `status: active` on any doc still at `draft`; do not edit the body to match later reality.
- A later change gets its *own* later iteration. "Amend the spec to match what was actually built" is
  the wrong move — the drift is recorded by the *next* iteration, not by rewriting the frozen one.
- The technical-rfc on the epic Issue stays as the permanent record; the PR carries the link to the
  resulting code.

This is **shipping freezes the why** from the documentation model; see
[`documentation-model.md`](documentation-model.md) — *Two principles*.

---

## Skill-release block

This block is **standalone** — run it for any skill release, including a hotfix re-release, without the
iteration ship/freeze steps above.

### When

After the iteration's PR merges (or on a hotfix), before the skill is demoted from the active session.

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

3. **Ship before demote** — commit and push with the version bump *before* ending the session or
   reloading plugins. Bundled reference files require `/reload-plugins` or a fresh session to
   hot-reload; ship as one coherent version so the router and its references are always consistent.

### Gate

The release scan must be fully green. A dangling link, orphan reference, or description mismatch is a
blocker — do not ship until resolved.
