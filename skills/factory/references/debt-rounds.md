# Debt rounds — the round-protocol canon

> **When to load this reference:** running or preparing a tech-debt round, reading a raise item (a
> `YR-DEBT-DUE` issue), or closing a debt epic (its body carries the `YR-ITERATION-KIND: tech-debt`
> line). For the epic-gate mechanics that raise and hold on these records, see `tools/epic_gate.py`.
> For the documentation types the round instantiates, see
> [`documentation-model.md`](documentation-model.md).

---

## The walls

A tech-debt round's home is broader than deletion: it is where code built with **partial
understanding** — the shape that was right for the first slice's knowledge, wrong once later slices
revealed more — gets refactored to match what's now known, not only where dead code gets removed. The
walls below still hold for either kind of item: a round removes or reshapes code under these walls —
each a rule with the reason it exists, not a formality.

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
7. **Swept surface, not clock.** A census declares its swept surface as three machine-readable fields —
   a baseline ref, an include rule, an exclude rule — in its own fenced block. The next round's surface
   is *(the tree today) − (files matching that declared surface unchanged since that baseline ref)*: a
   round's boundary is what changed, not how long since the last sweep. The exclude rule applies to
   **both terms** of that subtraction — the tree-today term and the unchanged-since term alike — so a
   path once excluded never re-enters the surface by falling back into either term in a later round.
8. **Per-arm exemption, declared.** Surface reduction applies per arm of the census, not census-wide: an
   arm whose findings depend on relationships no single change can exhibit is exempt from the
   subtraction and declares, in its own coverage line, that it read the whole tree — an undeclared
   "read the whole tree" claim is indistinguishable from a swept-surface claim wrongly scoped, so the
   declaration is the arm's own obligation, not an inference a reader makes.
9. **Generated evidence out, tests apart.** A census excludes generated evidence from its surface and
   names every such exclusion with its size — an untracked coverage report or build artifact is not
   evidence of reachability. And a census reports tests separately from production in its counts — a
   suite growing while production shrinks is progress, not noise netted against it.
10. **Inputs mined before swept.** A census reads four inputs, in this fixed order, before performing
    any sweep of its own: the declared surface, the nit clusters, the open backlog seeds, and the prior
    census's carry-forward. A finding already held by one of those inputs is cited to that input, never
    re-derived — a sweep that re-derives what a nit cluster or a backlog seed already found is spending
    effort on ground already covered.
11. **Every prune slice ships a guard.** A prune slice ships a guard — an ordinary test, no instrument
    named — that fails when its own finding recurs; a prune with no guard is a fix that can silently
    regress. Where a finding admits no deterministic predicate, the slice records **why** no guard is
    expressible and **what would have to be true** for one to exist — a recorded impossibility is a
    finding, silence is not. Where the guard protects an enumerable set, the expected set is **derived
    from the tree**, never enumerated as a list of offenders — a hardcoded list is legitimate only as a
    **tombstone for a named removal**, not as the check's ongoing shape. Where the guard asserts against
    a document, it names the **surface it reads** — the specific section or table, not the containing
    file — so a match found outside that surface can't satisfy it. The difference across these guards is
    shape, not tier: `tests/harness/test_gh_fake_migration.py`'s
    `test_no_full_gh_fake_reimplementation_anywhere_in_tests` walks the tree and holds completely;
    the raw-VERDICT-pipeline cap is a cardinality guard that held — written
    as an ordinary pytest test at #151 and, in the factory's own repo since #365, carried as the
    declared rule `verdict-extraction-pipeline` in `qa/cardinality.toml` instead;
    `tests/test_docs_drift_correction.py`'s `assert int(match.group(1)) > 63` was a floor, still green
    while the claim it floored drifted — the exhibit reads as the fail-open floor *retired by debt
    round 2* (issue #383), once the drifted claim was removed rather than corrected a third time: the
    species lesson kept, the live citation not. That middle exhibit states the rule better than the
    prose can: it changed tier without changing one thing it asserts. Which tier a repo reaches for is
    the repo's own call — the wall constrains the shape and never the instrument.

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

## Census arms

The census's axis set is **closed at four** — no fifth without an argued canon change to this section.
Every census reports, on each arm's own coverage line, whether that arm ran this round and, when it
didn't, what it carried forward unmeasured; an arm silently absent from a census reads as a defect in
the census, never as a signal that the arm found nothing.

1. **Reachability.** Walls the call graph from every entry point (wall 1) and partitions what it finds
   into three sets, not two: reached by nothing (the deletion ledger), reached only by tests (untested
   is not unused), and — the third partition — **reached in production and exercised by no test**. The
   third falls out of the same call-graph walk the other two already use and is reported as a list of
   names, never collapsed into a ratio.
2. **System shape.** A declared arm of every census, run as the round's macro view: its scope is the
   system rather than any single change, and it is the arm wall 8 exempts from surface reduction,
   because its findings are relationships no single change can exhibit. It reports shapes only a
   system-wide pass surfaces — a contract's consumer count, a grammar's forked conventions, a
   duplicated home — and for each one it **rules the intended shape**, not only enumerates the
   instances found: a row listing five consumers with no ruling on whether five is right hasn't done
   this arm's job — the ruling is what a later guard checks against, so the decision survives the round
   that made it. The concern behind it is the same kind of judgment [`architect.md`](architect.md)
   names, but that reference binds the architect role to four named moments in the pipeline it already
   touches (spec-ready, the architecture review, the crossing, the ship-walk) — none of them this arm
   — so the name stays the arm's own, never that role's.
3. **Tests.** A standing arm: `tests/` is the largest surface in the repo, so it is swept every round
   rather than once. Reported apart from production (wall 9). It gates nothing — the sweep is a meter,
   not a check.
4. **Performance.** A standing arm: measured every round, and it gates nothing. Each census records
   per-test runtime attribution together with the protocol that produced it — host, load state,
   extraction method — because three runs of the same tree at the same ref spread ~10% while a meter
   exists to detect a 23% trend. A reading without a protocol does not enter the series. Successive
   readings compare **shares before seconds**; where two readings were produced under different
   protocols, the comparison is of shares only, never of absolute durations.

A candidate axis outside this set is excluded only when this section records the exclusion with its
argument — never by silence. An axis this document has not mentioned is not thereby excluded; it is
simply unaddressed, and adding a fifth axis is a change to this canon, not a census's own call.

### The nit harvest

`tools/nit_harvest.py` is the tool behind the **nit clusters** input (wall 10) — it is **not a fifth
axis**: the axis set stays closed at four, and the harvest feeds the census rather than expanding it. It
reads the repo's merged-PR comment trail (`gh api repos/{owner}/{name}/issues/comments --paginate`) and
ranks paths by **recurrence across independent reviews** — a file named by findings in **two or more
separate PRs** that **still resolves in the tree** today. Its output lands in the census's *Duplication /
consolidation sets* section, feeding that arm the same way a backlog seed feeds another; a recurrence of
one is not a cluster, and a path that no longer resolves is dropped.

Two finding sources, **one label per row**. A **record** row is a line beginning `YR-NIT:` at column 0 —
`line.startswith("YR-NIT:")` on the raw line, no `.strip()` and no `\s*` tolerance, the same line-anchor
rule the record grammars above and `tools/epic_gate.py` share. The grammar is defined once, in
`tools/nit_harvest.py`'s module docstring — `YR-NIT: tag=<blocker|nit> path=<repo-relative path>
[line=<n>] — <one sentence>` — and cited, never re-defined, from anywhere else. Column-0 anchoring is
what keeps a **quoted transcript's** nits out of the harvest: a quoted review transcript (e.g. a bench
replay's own candidate transcript, reproduced verbatim wherever it is read back) blockquotes its whole
body, so a quoted nit arrives indented behind `> ` and never sits at column 0. When a
finding carries **no** record, a **heuristic** row is recovered from prose and labelled as such — a path
that **degrades precision, never a run**: the absent-record path never raises and never fails a build. A
stored `line` is **provenance only** — a pointer back to the comment, never an actionable line: the
harvest clusters on **two** keys and returns both — a **symbol** (a backticked identifier that
still resolves in the tree) and a **path** — because a contract's consumers share a name rather than a
file, and path clustering alone ranks the most-edited files to the top by construction. Each arm uses
the same recurrence rule; a stored line number is consulted by neither.

The harvest **never files a nit as an issue.** `tools/epic_gate.py`'s intake sweep adds every open issue
in a registered repo to the shared board, so a harvested-nit issue would flood the state machine the
census feeds; the harvest's output is a census row, not a ticket.

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
3. **Report the round's six close-time meters:** recurrence (findings that reappeared despite a prior
   wall-11 guard); coverage over the four declared axes (the census's own arm-coverage table);
   guard yield (how many of this round's prune slices shipped the wall-11 guard); per-test cost with its
   protocol (the performance arm's reading, per *Census arms*); cluster conversion **within the round
   that found them** (how many of this round's duplication/consolidation sets converted to a prune item
   in the same round they were found in); and the **detection locus** — two counts kept separate,
   duplication findings raised at build time by the iteration's reviewer and consolidation shapes found
   by the system-shape arm, reported as **two counts and never as a ratio** — a build-time catch is one
   PR wide, a shape is many, so the two counts never collapse into one unit.
4. **Dispose of the round's raise issue** — close it now that its need is met; it is never left open
   past the round it named.
5. **Clear the held `Reason`** — the epic-gate's sweep posts the hold and sets `Needs-info`, but it
   never clears a Reason itself; clearing is the attended closer's act, the same fail-closed shape as
   every other epic-gate hold.
6. **Re-census per the census's own revisit trigger** — freshness for a `research` doc is event-driven,
   never clock-gated (see [`documentation-model.md`](documentation-model.md) — *Lifecycle*); the next
   round's census starts from the trigger the last one named, not from scratch.
