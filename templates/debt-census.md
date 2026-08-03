---
type: research
status: draft              # doc lifecycle: draft | active | rejected | superseded (NOT the board's Status)
supersedes: []             # optional: a round-N census supersedes round N-1's; targets are quoted
                            # "[[wikilinks]]"; empty is allowed (a first census has nothing to
                            # supersede) but must be justified in the body; stamped superseded at accept
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---

# Debt census — round <N>

> Filed as: a `research` doc opening a tech-debt round. The round's debt epic must carry the kind
> record line `YR-ITERATION-KIND: tech-debt` on its own body — verbatim blocks are safe in repo files;
> the counter and the close-hold read GitHub issue surfaces only, never this file. See
> [`debt-rounds.md`](../skills/factory/references/debt-rounds.md) for the round protocol this opens
> (*The walls* → *Census with a reachability ledger*).
>
> **Method discipline:** read-only — a census inspects, it does not change anything. **Untested is not
> unused** — a row with no passing exercise of the path is evidence of an untested path, not a dead
> one. **Deletion cites its birth** — every candidate-for-removal row records the commit or issue that
> introduced it, so a later prune reads the citation off this row instead of re-deriving it from `git
> blame`.

**Supersedes:** nothing — <one-line justification of the empty claim, or name the round N-1 census this replaces>
<!-- Keep this line, with a real justification, when the supersedes list above is empty. Once the
     list is non-empty, replace it with prose naming what's replaced, or drop it entirely. -->

## Swept surface
<!-- Machine-readable: this round's surface is (the tree today) minus (files in this declared surface
     unchanged since baseline). The exclude rule applies to both terms of that subtraction, so an
     excluded path never re-enters the surface in a later round — debt-rounds.md → The walls (the
     swept-surface wall). -->
```
YR-DEBT-SURFACE
baseline: <ref, e.g. the prior round's closing commit>
include: <rule, e.g. a path prefix or glob>
exclude: <rule, e.g. a path prefix or glob>
```

**Generated evidence excluded:**
<!-- Name every generated-evidence exclusion and its size — debt-rounds.md → The walls (the
     content-rules wall). -->
| Exclusion | Size |
|---|---|
| <path or glob> | <size> |

## Inputs mined
<!-- Read in this fixed order, before any sweep of this census's own: the declared surface above, the
     nit clusters, the open backlog seeds, the prior census's carry-forward. A finding already held by
     one of these is cited to it here, never re-derived — debt-rounds.md → The walls (the mined-inputs
     wall). -->
| Input | Already held | Cite |
|---|---|---|
| Declared surface | <finding, or "none"> | |
| Nit clusters | <finding, or "none"> | |
| Open backlog seeds | <finding, or "none"> | |
| Prior carry-forward | <finding, or "none"> | |

## Arm coverage
<!-- The axis set is closed at four — reachability, system shape, tests, performance. Tests and
     performance are standing arms: measured every round and gating nothing (tests is swept, not
     sampled once; performance records a protocol-tagged reading every round — see the Performance
     section below). Each arm reports whether it ran this round and, if not, what it carried forward
     unmeasured — an arm silently absent is a defect in the census, never a signal it found nothing. A
     candidate axis outside this set is excluded only by an argument recorded here; an axis not
     mentioned at all is not thereby excluded — debt-rounds.md → Census arms. -->
| Arm | Ran this round | Carried forward unmeasured |
|---|---|---|
| Reachability | <yes/no> | <what, or "n/a"> |
| System shape | <yes/no> | <what, or "n/a"> |
| Tests | <yes/no> | <what, or "n/a"> |
| Performance | <yes/no> | <what, or "n/a"> |

**Excluded candidate axes:** <none this round | name each excluded candidate with its argument — an
unmentioned axis is never treated as excluded>

## Baselines
<!-- The meters the next round's census diffs against. Tests are reported separately from production —
     debt-rounds.md → The walls (the content-rules wall). -->
- Tracked files (production): `<count>`
- Tracked files (tests): `<count>`
- Tracked lines (production): `<count>`
- Tracked lines (tests): `<count>`
- Suite count: `<count>` tests
- Suite duration: `<Nm NNs>`

## Reachability ledger
<!-- Nothing is deletable unless the ledger clears it: this is the only source of "this is
     unreachable," and a removal without a clearing row here is a removal on vibes. The call-graph walk
     yields three partitions, not two: reached by nothing (dead, below), reached only by tests
     (untested, below), and reached in production and exercised by no test (the third partition, listed
     by name beneath the table) — debt-rounds.md → Census arms. -->
**Coverage:** <swept surface, per the block above | whole tree — exempt per the per-arm exemption: name
why this arm's findings depend on relationships no single change can exhibit>

| Item | Class | Evidence | Birth | Candidate disposition |
|---|---|---|---|---|
| <item> | <live / untested / dead> | <what was inspected> | <introducing commit or issue> | <keep / pin-then-prune / needs more evidence> |

**Reached in production, exercised by no test:**
<!-- The third partition — distinct from "reached by nothing" (dead, above) and "reached only by
     tests" (untested, above). A list of names, never a ratio — debt-rounds.md → Census arms. -->
| Symbol |
|---|
| <name, or "none this round"> |

## System shape
<!-- The round's macro view — scope is the system, not any single change; exempt from surface
     reduction per the per-arm exemption (debt-rounds.md → The walls, wall 8). Reports shapes no
     single change can reveal, and rules the intended shape for each rather than only enumerating its
     instances — debt-rounds.md → Census arms. -->
**Coverage:** whole tree — exempt per the per-arm exemption: <name why this arm's findings depend on
relationships no single change can exhibit>

| Shape | Instances found | Ruling: intended shape | Rationale |
|---|---|---|---|
| <e.g. a contract's consumer count> | <instances found> | <the ruled intended shape> | <why> |
| <e.g. a grammar's forked conventions> | <instances found> | <the ruled intended shape> | <why> |
| <e.g. a duplicated home> | <instances found> | <the ruled intended shape> | <why> |

## Performance
<!-- A standing arm: measured every round, gates nothing — debt-rounds.md → Census arms. Each census
     records per-test runtime attribution together with the protocol that produced it — host, load
     state, extraction method — because three runs of the same tree at the same ref spread ~10% while a
     meter exists to detect a 23% trend. A reading with no protocol recorded does not enter the series.
     Successive readings compare shares before seconds; where two readings were produced under
     different protocols, compare shares only, never absolute durations. -->
**Protocol:** host: `<e.g. named CI runner class, or the attended operator's machine>` · load state:
`<idle | contended, and how that was known>` · extraction method: `<e.g. pytest --durations=N, a timer
wrapper>`

| Test | Runtime | Share of suite duration | Prior share (same protocol only) |
|---|---|---|---|
| <slowest test, or "none this round"> | <duration> | <% of suite duration> | <prior round's share, or "n/a — no prior reading under a comparable protocol"> |

## Duplication / consolidation sets
<!-- Groups of items that overlap or duplicate each other — candidates for merging rather than a
     straight removal. One set per group, naming its members and the consolidation target. These
     consolidation-shape rows are one half of the round-close detection-locus meter: reported at round
     close as a count, kept separate from — never a ratio against — the duplication findings the
     iteration's reviewer raised at build time (debt-rounds.md → Round-close duties). -->
**Coverage:** <swept surface, per the block above | whole tree — exempt per the per-arm exemption: name
why this arm's findings depend on relationships no single change can exhibit>

**Nit harvest** — `tools/nit_harvest.py` reads the merged-PR comment trail and ranks paths named by
findings in two or more *separate* reviews that still resolve in the tree (debt-rounds.md → Census arms,
*the nit harvest*). A stored `line` is provenance only; a row's `source` is `record` (a column-0
`YR-NIT:` line) or `heuristic` (recovered from prose). A recurrence of 1 is not a cluster.

**By symbol** — the arm that answers whether a contract has acquired consumers. Read this table
first: a symbol named by two independent reviews is the consolidation signal, where a much-edited
file is only churn.

| Symbol | Recurrence (distinct PRs) | Source(s) | Provenance | Consolidation target |
|---|---|---|---|---|
| <symbol> | <n PRs, e.g. #a, #b> | <record / heuristic> | <PR + line, if any — a pointer to the comment, never an actionable line> | <the merge target, or "none this round"> |

**By path.**

| Path | Recurrence (distinct PRs) | Source(s) | Provenance | Consolidation target |
|---|---|---|---|---|
| <path> | <n PRs, e.g. #a, #b> | <record / heuristic> | <PR + line, if any — a pointer to the comment, never an actionable line> | <the merge target, or "none this round"> |

## Unknowns
<!-- What the census could not determine — explicit, not silently dropped. Each unknown either becomes
     a round item once resolved, or stays unresolved and is carried into the next census. -->

## Revisit trigger
<!-- When these numbers go stale: at the first prune merge of this round. Re-census per round, never
     on a clock — the next round's census starts fresh. -->

---
*Next stage:* the round-spec (`debt-round-spec.md`) scopes the round by name from this ledger's
cleared rows.
*Review output:* fold findings in — or, if heavyweight, a standalone `research`/`note` cited here; never a frozen appendix (see `documentation-model.md` → *Reviewing a doc*).
