# Debt rounds — the round-protocol canon

> **When to load this reference:** running or preparing a tech-debt round, reading a raise item (a
> `YR-DEBT-DUE` issue), or closing a debt epic (its body carries the `YR-ITERATION-KIND: tech-debt`
> line). For the epic-gate mechanics that raise and hold on these records, see `tools/epic_gate.py`.
> For the documentation types the round instantiates, see
> [`documentation-model.md`](documentation-model.md).

---

## The walls

A tech-debt round removes code under these walls — each a rule with the reason it exists, not a
formality.

1. **Census with a reachability ledger.** The round opens on a `research` doc (see
   [`documentation-model.md`](documentation-model.md) — *The document types*) enumerating every entry
   point and, from them, what's actually reachable. **Untested is not unused** — a census row with no
   passing exercise of the path is evidence of an untested path, not a dead one. **Nothing is deletable
   unless the ledger clears it**: the census is the only source of "this is unreachable," and a removal
   without a clearing row is a removal on vibes.
2. **By-name scope.** The round-spec is a `product-spec` (see
   [`documentation-model.md`](documentation-model.md) — *The document types*) naming the items in scope.
   **An item not named in the round-spec is not in the round** — a prune PR that reaches for one more
   thing "while it's in there" is scope creep on a pipeline built to fail closed on undeclared scope.
3. **Pin-then-prune.** The pin slice (tests that lock the ledger's kept behavior) is purely accretive
   and ordered **before** its prune slice under the epic. The sweep's own sub-issue serialization —
   promoting one open child at a time, in sub-issue order — enforces that order mechanically; no
   reviewer discipline is needed to keep a prune from landing ahead of its pin.
4. **Birth citation.** A removal cites the introducing commit or issue that its own census row already
   records — the census is the ledger of *why something exists*, so the citation is read off that row,
   never re-derived from `git blame` at prune time.
5. **One item = one revertible chain.** Each round item squash-merges as its own commit, so any single
   removal can be reverted without unwinding the whole round.
6. **The prune review bar.** A prune PR clears review only if it is **behavior-identical** (the pin
   slice's tests still pass, unchanged) and **net-negative** (it removes more than it adds) — a prune
   that grows the tree, or changes behavior, isn't a prune.

## Record grammars

Five grammars, each recognized only by its marker sitting on **its own whole stripped line** — a prose
mention, a quoted example, or a backticked reference never counts as the record. `tools/epic_gate.py`'s
own readers (`_is_debt_epic`, `_has_ledger_verdict`, `_is_due_raise`, the hold check) apply this same
line-anchor rule, so canon and code read the same bytes the same way.

**The kind record** — on the debt epic's own body, marking it a debt (not a feature) epic:

```
YR-ITERATION-KIND: tech-debt
```

**The ledger verdict** — a comment on the debt epic, posted at round close; seven fields, of which
`items` and `net-lines` are the machine-checked pair (both must be non-empty or the verdict doesn't
count):

```
YR-DEBT-LEDGER
items: 3
net-lines: -142
files-removed: 2
deps-removed: 1
pins-added: 1
suite-duration: 4m12s
incidents: none
```

**The due record** — the body of the raise issue the counter opens:

```
YR-DEBT-DUE
repo: yellow-robots/factory
anchor: #80
count: 10
counted: #81, #82, #83
```

**The hold marker** — a comment the epic-gate posts on a debt epic it will not self-close:

```
YR-DEBT-HOLD

This is a debt epic with no open children left, but no valid ledger verdict is on record.
```

**The net-lines PR-body record** — one per prune PR, in its own body; the round-close duties aggregate
these into the epic's single ledger verdict rather than hand-summing diffs:

```
YR-DEBT-NET-LINES
items: 1
net-lines: -18
```

All five are safe to show verbatim in a repo file: the counter and the hold marker only ever read
GitHub issue/comment surfaces, never this file.

## The counter

`tools/epic_gate.py`'s per-repo sweep counts, since the most recent closed debt epic (the **anchor**,
or "none" when there isn't one), every closed-as-completed `Feature` epic that does **not** itself carry
the kind record — the **countable** set. At `debt_round_every` countable epics it raises the need for a
round exactly once. The threshold defaults to **10**, is overridable per repo via the manifest key
`debt_round_every` in `.yr/factory.toml`, and is overridable process-wide via the `DEBT_ROUND_EVERY` env
var — precedence **env > manifest > default**; a missing or invalid manifest value falls back to the
default rather than erroring.

## The raise

The counter opens the due record as a `Type=Task`, `Backlog`-only issue, keyed on **(repo, anchor)** —
never re-keyed on the count, so the same anchor never raises twice. It is **deliberately not
DoR-complete**: a raise names the need, it does not scope the round — scoping is exactly the
round-spec's (a `product-spec`) job, by-name, per *The walls* above. The raise is **disposed of at
round close**, never promoted by the counter itself — promotion stays a human act.

## The close-hold and recovery

A debt epic with no open children left does **not** self-close the way a feature epic does: the
epic-gate holds it — posting the hold marker once and setting `Reason=Needs-info` — until a valid
ledger verdict comment is on record. **Recovery:** post the verdict (or close the epic attended), and
the next sweep either self-closes it or leaves it as the human who just closed it left it.

## Round-close duties

Closing a debt epic — attended, once the ledger verdict is ready — runs this list:

1. **Post the ledger verdict** (the seven-field record above) as a comment on the epic.
2. **Aggregate the net-lines records** from every prune PR in the round into the verdict's `items` and
   `net-lines` totals.
3. **Dispose of the round's raise issue** — close it now that its need is met; it is never left open
   past the round it named.
4. **Clear the held `Reason`** — the epic-gate's sweep posts the hold and sets `Needs-info`, but it
   never clears a Reason itself; clearing is the attended closer's act, the same fail-closed shape as
   every other epic-gate hold.
5. **Re-census per the census's own revisit trigger** — freshness for a `research` doc is event-driven,
   never clock-gated (see [`documentation-model.md`](documentation-model.md) — *Lifecycle*); the next
   round's census starts from the trigger the last one named, not from scratch.
