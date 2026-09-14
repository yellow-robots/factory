# 0002. Build the thinnest loop first, in versions, with state derived rather than written

Date: 2026-09-14
Status: accepted

## Context

The v2 design runs to twenty sections. Asked for its confidence in building stage 1 as
written, the authoring model put it near one in two. The owner's response: stop defining, start
iterating from the most basic loop that closes a goal, and treat the design as an asset the
next iteration draws from.

The hardest problem is memory across sessions. A hand-written "next steps" file was tried in v1
and rejected here: it rots the moment nobody updates it, and nothing checks it. Software has
battle-tested patterns for exactly this, where state is derived from artifacts that something
else already keeps honest.

## Decision

Iterate in versions. A version is a declared goal with acceptance criteria, reached by one pass
of the loop, and it ends with a tag, a deployed artifact and a generated changelog entry.

Continuity is derived, never written. A session's first act is running, not reading: `make`
lists what can be done, `make next` prints the version of record (`git describe`), the next
declared version (the lowest `versions/<n>.toml` without a `v<n>` tag) and the red tests; `make
test` says how well things stand. Its last act is a red test and an issue, not a paragraph. The
instruments, each with its keeper:

- git tags and `git describe`: the version of record, kept by git.
- the failing test as position (Beck): a strict-xfail test marked `next`, kept by pytest,
  which fails the suite the moment it passes with the marker still on.
- the milestone and its issues: the steps, kept by the forge.
- the changelog: generated from conventional commits by git-cliff, never edited.
- decision records: append-only, superseded rather than changed, kept by review.
- the Makefile: the executable README, kept by use.

Manual first, then automate. v0.1 is the deterministic loop around an attended build: identify
the project, find what is next, provision if absent, build by hand, verify the goal on its
surface, check the metrics, deploy, publish the changelog. v0.2 automates the build step. Every
prompt the attended agent uses on the way is saved as a role file, so the automated step starts
from what was already exercised.

The first target is external. `yellow-robots/hello-robot-world` is the first project the
machinery runs on: v0.1 a static site, v0.2 an API, so the loop is exercised twice on one
project across two protocols. The factory conforms to the same project contract from its first
commit (this one) so that attended sessions on the factory use the same instruments, but the
factory does not build itself before stage 4. When it does, it does so as a compiler does: the
last released tag builds the candidate, the candidate builds itself, and the fixed point is the
check.

## Consequences

There is no state file to keep current, so there is nothing to forget. The cost is that every
instrument must be exercised or it rots: a version file with no tag discipline, a `next` marker
left on a passing test, a changelog edited by hand all show up as failures, which is the point.
The design document's twenty sections are not on the path; an idea from it enters only as the
goal of a version or the subject of a decision record.
