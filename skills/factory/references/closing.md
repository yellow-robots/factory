# Closing — promote, merge, freeze, and release

> **When to load this reference:** closing out an iteration — promoting a task to Ready, receiving a
> merged PR (→ Done), freezing Obsidian docs, judging the crossover test, and running a skill release.
> Promote-to-Ready is the **input gate**; merge → Done is the **output gate**. For authoring, see
> [`authoring.md`](authoring.md). For the lower pipeline, see [`pipeline.md`](pipeline.md).

---

## 1. Promote to Ready

**Who:** a human owns the input gate, and it is a **triage record** — nothing activates outside it. A
human disposes each ranked seed `go` / `park` / `reject` on the component's triage surface, and only a
`go` licenses a design artifact (a product-spec or feature-rfc) toward `active`, whether a human sets it
directly or the PM's machinery does under that same license (it-36); no agent ever sets `active` outside
a triage record. Below that standing approval, flipping a governed epic to Ready, promoting its next
pre-approved slice, and closing a finished epic are **mechanical**, fail-closed back to the human on any
doubt. A standalone task with no governing design
above it has no standing approval to run on, so it keeps the original per-task human promotion — and its
**body inherits the design gates** (ruled 2026-07-13): governed work's WHAT was adversarially reviewed and
fit-checked upstream before anything crossed; a standalone task's body is that design, so the same cold
gates run on the body itself before the human promote — and since it-30 the promote act itself is walled
(`tools/promote.sh` demands the gates record before its own promotion record), and standalone-shipped
work earns a defined, recorded close: a standalone task is a round of one, emitting the ship-walk trace
and round-record counts for its scope (the step set, the walled-act map, and the record vocabulary live
in [`attended-lane.md`](attended-lane.md) and `records.toml` — cited, never restated here). The pipeline verifies the code *against* the
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

- Merge ≠ ship. `main` is not production; deploy stays separate and attended — the build-host checkout
  it refreshes is one of the factory's eight runtime surfaces (`AGENTS.md`'s git-refs invariant carve-out).
- Shadow completion is mechanical (a rolling window of clean, unreverted merge records — see
  [`pipeline.md`](pipeline.md)); completion *permits* arming, and arming stays the human's manifest
  edit. Un-arm or throw the sentinel to return a repo to the human gate at any time.
  The **durable rule** is *a human decides what to build*, not *a human merges every PR*.

---

## 3. Doc-side freeze

When the PR merges, the iteration's Obsidian docs become immutable records:

- Set `status: active` on any doc still at `draft`; do not edit the body to match later reality. A
  **functional defect** (a dead link or unresolvable anchor) is the one exception and *is* repaired
  here, under the closed rules in [`documentation-model.md`](documentation-model.md) — *Two
  principles*: the close is the moment a session handles every doc in the iteration, so it is where
  such a defect is most cheaply caught. Record the repair in the walk entry.
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

## 5. The round's close is machinery (it-36)

For a PM-governed epic, §§1–4 above run as machinery, not as a closing session: `tools/design_gate.py`'s
`sweep_close` finds an epic carrying `YR-CLOSE-HOLD` whose mandated close records are still missing and
spawns `tools/close-runner.sh` once per epic. That runner runs one `close-walk` stage (the ship-walk
over the grounding list) and then `tools/round_record.py`'s `ship-walk` / `round-record` / `crossover`
subcommands in order — a failed walk stops short of the rest, so no partial close ever posts. Every
write lands through `tools/vault_api.py`, the machinery's own client of the vault's REST interface (see
[`documentation-model.md`](documentation-model.md) — *Editing safely*), under the App's identity, and is
read back to confirm. `tools/epic_gate.py`'s close-hold arm itself — deciding *when* an epic wants to
self-close and what it demands before it may — is untouched; this section names only what now *satisfies*
the hold, not what raises it.

**What shipped is published (it-36).** The merge evaluator's `fragment_present` condition (issue #474)
demands a changelog fragment under the manifest's `changelog_dir` on every merging PR — the runner's own
implement stage writes one; an attended PR's own duty to add one is *AGENTS.md* → *Conventions*. At an
iteration's close, `tools/changelog.py` compiles those fragments (or a merged PR's own title, named as
such, when its fragment is missing) into `CHANGELOG.md` and a release body carrying a fenced
`yr-changelog` block; `tools/release.py` gains the `it/<n>` iteration-release family beside the existing
skill family (`skill/vX.Y.Z`) to ship it; `tools/notify.py` delivers that release to the manifest's
`[[stakeholders]]` table — telegram, webhook (signed), issue-comment, or the GitHub Release itself — then
posts one `YR-CHANGELOG` naming the delivered set. Both tools are **attended-invoked today**: no sweep
wires either one in yet (a board item tracks that), and until item P (the owner's Telegram credential and
webhook secret) exists, no `[[stakeholders]]` entry can name a real address regardless. Depth:
[`pipeline.md`](pipeline.md) → *The changelog and stakeholder notification*.

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
   - **The manual is current** (`manual_current`, it-32): the range since the previous tag did not
     change `skills/factory/SKILL.md` or `AGENTS.md` without touching `docs/manual.md` — the manual
     renders both by citation — or the act records the manual unaffected
     (`tools/release.py … --manual-unaffected "<reason>"`); the `YR-RELEASE` record carries `manual:`
     either way.

3. **Ship before demote** — the release (merge to `main`) ships the new content **before** any
   dependent consumer is repointed and before the superseded source is demoted: the living content must
   never exist nowhere authoritative. (Session note: bundled reference files hot-reload only via
   `/reload-plugins` or a fresh session — ship as one coherent version so router and references never
   split.)

4. **Run the act.** The release is the human's own — no agent may execute it — so its commands live
   here rather than in a session's memory. Run them from the repo root of a checkout **current with
   `main`**: a stale checkout's `release.py` rejects flags it predates, naming them as unrecognized
   arguments rather than as staleness.

   ```bash
   tools/release.py validate --version <X.Y.Z> --commit <sha>    # judge only — writes nothing
   tools/release.py ship --version <X.Y.Z>                       # release origin/main's tip
   tools/release.py backfill --version <X.Y.Z> --commit <sha>    # type a version shipped before the act
   ```

   `--test-mode` on `ship`/`backfill` runs the full validation and writes nothing — no tag, no
   Release, no trail. `--manual-unaffected "<reason>"` answers step 2's manual condition by
   declaration, and the reason lands verbatim in the record's `manual:` field. `--who @login` names
   the shipper in the record; absent, the act reads the authenticated `gh` user, and `@unknown` on a
   failed read.

   **A failing condition and a failing write are different states, and only one of them is a
   no-op.** Any *validation* failure writes nothing at all and prints the condition's token as
   stdout's first line. Past validation the act writes in order — annotated tag, tag pushed to
   `origin`, GitHub Release carrying the `YR-RELEASE` record — so a failure *there* leaves work
   behind: `tag_push_failed` leaves the tag local, and `release_create_failed` leaves it **on
   origin**, where a retry of that same version refuses as `tag_exists`, since a version is released
   once. Read the token, then read `git ls-remote origin refs/tags/skill/vX.Y.Z` before retrying —
   a pushed tag with no Release is finished by creating the Release for the existing tag, never by
   re-running the act.

### Gate

The release scan must be fully green. A dangling link, orphan reference, or description mismatch is a
blocker — do not ship until resolved.
