<!-- GENERATED from process.toml v1.0.0 sha256:7bee83ab0dab72ae — never hand-edit -->

# The attended lane — the delivered slice (static half)

## The machines — where each state physically lives

**task** — one GitHub issue of Type Task or Epic, as it sits on the shared Dev board
- status (store `board.status`, board-single-select): `backlog`='Backlog' · `ready`='Ready' · `in-progress`='In Progress' · `in-review`='In Review' · `done`='Done'
- reason (store `board.reason`, board-single-select): `none`='' · `needs-info`='Needs-info' · `blocked`='Blocked'

**pr** — one pull request of a factory build
- state (store `pr.status`, pr-attribute): `open`='open' · `approved`='approved' · `merged`='merged'

**design-doc** — one vault design document (spec / feature-rfc / supporting doc)
- status (store `doc.frontmatter.status`, frontmatter-key): `draft`='draft' · `active`='active' · `superseded`='superseded' · `rejected`='rejected'

## The transitions — who may move what, under which conditions
- **task.backlog->ready.standalone** [human/attended-agent; door one-way; partial; chokepoint: none — client-side hook coverage only] — the standalone lane's review + fit gate; YR-PROMOTED never satisfies it. the standalone lane's human input gate: no governing design carries the approval, and promotion starts an autonomous build that opens a PR
  - open: board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.blocked->ready.unblock** [human/attended-agent; door reversible; partial; chokepoint: none — client-side hook coverage only] — this is the unblock; a clean In Progress -> Ready is a different row; record-before-flip, typed. unblocking is the same board write as promotion and a DIFFERENT rule: the Reason that justified the block must not survive the unblock
  - open: board.reason.web-ui: the Projects UI (detected by YR-BOARD-FLIP); board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.backlog->ready.epic-child** [machinery; door reversible; partial; chokepoint: none — client-side hook coverage only] — the standing approval on the epic's trail licenses every child promotion beneath it; the airlock rule: an open question on the epic blocks mechanical promotion. the epic gate's mechanical promotion under a standing approval; the cord-pull (un-Readying) is the human's veto, so the door is reversible
  - open: board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.ready->in-progress.claim** [machinery; door reversible; partial; chokepoint: none — client-side hook coverage only] — no guards. the runner's claim: the dispatched build takes the task
  - open: board.reason.web-ui: the Projects UI (detected by YR-BOARD-FLIP); board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.in-progress->in-review.pr-open** [machinery; door reversible; partial; chokepoint: none — client-side hook coverage only] — no guards. the runner opened the PR; the build reached its terminal stage
  - open: board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.in-review->done.native** [external-service; door one-way; partial; chokepoint: none — client-side hook coverage only] — native close->Done follows the merge, never precedes it. we do not gate GitHub; the native close->Done board move is detected, never prevented
  - open: board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **task.ready->done.epic-close** [external-service; door one-way; partial; chokepoint: none — client-side hook coverage only] — the round's ship-walk trace on the epic's trail before the epic reaches Done; the round record (refusals · records-demanded · detector-findings · escalations) lands at close. the epic's self-close: the board move is GitHub's, and the close duties ride as guards so a close without its records is a detector finding — gap 15's fix, detection-tier
  - open: board.status.web-ui: a human moving the card, or GitHub's native close->Done automation (detected by YR-BOARD-FLIP)
- **pr.approved->merged.evaluator** [machinery; door one-way; partial; chokepoint: none — client-side hook coverage only] — an unarmed repo keeps the human's click (the named transitional exception); the host kill switch is not thrown; every merge condition holds, in the evaluator's own order with its own fail-closed semantics. the armed output gate; an attended hand-merge is refused because no actor class an attended session belongs to may perform this transition — no special 'categorical' concept is needed
  - open: pr.merged.web-ui: the merge button (detected by YR-MERGE)
- **design-doc.draft->active** [human/attended-agent; door one-way; partial; chokepoint: none — client-side hook coverage only] — the cold adversarial review, typed into the doc; the architect's fit verdict at the spec-ready moment; the airlock rule: an open question blocks the activation. the human input gate — what gets built; the standing approval under which the epic gate promotes slices mechanically
  - open: doc.frontmatter.status.cli: the `obsidian` CLI or REST API from a shell (detected by YR-ACCEPT)

## Honesty block
- caller_trust = `declared` — the caller class is declared, not proven; the journal and the detector find the shape afterwards.
- guards check existence and grammar only — genuineness stays with independent review and the bench.
- an act matching no binding is OBSERVED, never silently permitted as lawful — silence is absence of coverage, not permission.
- conduct: an attended commit credits the authoring model (an editor-driven commit (the body is not visible pre-execution), git commit --amend of a body written earlier, combined short flags beyond -am (-sam, -anm, ...), any porcelain wrapper are not covered).
