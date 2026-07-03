# Migrating — legacy docs onto the model

> **When to load this reference:** migrating an older doc (or a blob mixing many types) that predates
> the documentation model. For the model itself — types, lifecycle, frontmatter — see
> [`documentation-model.md`](documentation-model.md). For vault-safe write mechanics, see
> [`documentation-model.md`](documentation-model.md) — *Editing safely*.

---

## Steps

### 1. Enumerate and trace first

List every file, identify its `type`, and map every inbound and outbound link (vault-wide grep + the
Obsidian graph). Know which files are link-islands before moving anything.

**Gate:** hold here until the map is complete. Moving a file before the map is built = silent broken
links across the vault.

### 2. Find the iteration boundary

One coherent shipped change = one iteration. Later "open items" are a *future* iteration —
**shipping freezes the why** (see [`documentation-model.md`](documentation-model.md) — *Two principles*),
so they are never folded back into a shipped iteration.

**Judgment:** what is the single coherent change this doc records? If it records multiple changes, split
by iteration. If the boundary is ambiguous, prefer smaller iterations — the cheaper the why-record, the
clearer the history.

### 3. Split by type — "code is king"

| What the content is | Where it goes |
|---|---|
| Present-state facts (endpoints, IDs, schema, as-built state) | A **pointer** to the code / live system — a mirror only drifts |
| Rationale not recoverable from code (why this approach, trade-offs) | Kept verbatim, rehomed to `feature-rfc` |
| Frozen investigation / prior-art survey | A `research` doc |
| Standing ops | A `runbook` |

**Judgment:** "could I derive this from `git log` or the live system?" If yes, it is a pointer, not a
doc. If no, the why is worth keeping.

### 4. Retire the original

Two distinct cases — do not confuse them:

- **Migrated** (content re-homed, decision unchanged) → **delete it.** Its content now lives at the
  new path; the bytes survive in `.trash` / git. Do not tombstone — nothing superseded it. A
  `renameFile` already *is* this operation.
- **Superseded** (a newer design invalidates it) → retire **in place**: set `status: superseded` +
  `superseded_by` / `crossed_to`; the file stays for lineage. **Never `mv` a superseded file** — a
  filesystem rename silently breaks backlinks across the vault.

**Rule of thumb:** did a *decision change* (supersede) or did *content just move* (migrate)? `superseded`
requires a posterior invalidator — a later doc that changed the decision. Mislabelling a move as
`superseded` lies about history and leaves a drift-prone duplicate.

### 5. Gate the drafts

Stage edits in scratchpad. Run `check_links` (and `check_task` for any GitHub task) to green *before*
executing any app-mediated ops. See [`gates.md`](gates.md) for how to run the gates.

For vault-safe write mechanics — `obsidian:obsidian-cli` for link-safe renames, app-mediated edits,
folder creation — see [`documentation-model.md`](documentation-model.md) — *Editing safely*.
