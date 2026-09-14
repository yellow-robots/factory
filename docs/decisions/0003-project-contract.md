# 0003. A project is the four ways the factory can talk to it

Date: 2026-09-14
Status: accepted

## Context

The factory holds no product knowledge, so everything it needs from a project must come from
the project itself, in a form a machine can act on. The v1 manifest (`.yr/factory.toml`) mixed
build settings, model choices and arming state, and the pipeline read the rest from prose.

## Decision

The factory works only on projects with a fixed structure, and that structure is exactly the
four ways of talking to a project:

| Way of talking | What the project provides | Executable form |
|---|---|---|
| Work on this project | where the code and its docs live | the repository; decision records in `docs/decisions/` |
| How to deploy | how infra is provisioned and the project deployed | idempotent `provision` and `deploy` targets, no prose |
| What to do next | the goal of the next version | `versions/<n>.toml`: one goal, criteria each naming a `surface` |
| How well is it doing | deterministic quality metrics | `make test` and `make check`, plus the metrics the run records |

The factory repository conforms to this contract itself, so that an attended session on the
factory and a machinery run on a product read the same instruments.

## Consequences

Anything the factory needs that is not one of the four is a smell to be argued about in a new
record, not added quietly. A project that lacks one of the four is refused at the identify step,
not worked around. The exact shape of each executable form will change as the loop is built;
this record fixes the four questions, not their file formats.
