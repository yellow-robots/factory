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
     unreachable," and a removal without a clearing row here is a removal on vibes. -->
**Coverage:** <swept surface, per the block above | whole tree — exempt per the per-arm exemption: name
why this arm's findings depend on relationships no single change can exhibit>

| Item | Class | Evidence | Birth | Candidate disposition |
|---|---|---|---|---|
| <item> | <live / untested / dead> | <what was inspected> | <introducing commit or issue> | <keep / pin-then-prune / needs more evidence> |

## Duplication / consolidation sets
<!-- Groups of items that overlap or duplicate each other — candidates for merging rather than a
     straight removal. One set per group, naming its members and the consolidation target. -->
**Coverage:** <swept surface, per the block above | whole tree — exempt per the per-arm exemption: name
why this arm's findings depend on relationships no single change can exhibit>

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
