---
type: seed
status: open
summary: Expose the plane as an MCP server so a frontier model in a subscription harness works under the same walls, paid by subscription; two claims to verify first.
value: 5
effort: L
goal:
acceptance:
version:
crossed_to:
created: 2026-09-16
---

## Evidence

The roles that need a frontier model cannot run inside the pydantic-ai loop at API prices
(owner, 2026-09-16). v1 ran cold `claude -p` sessions under a subscription. The plane is five
functions with no dependency on the loop that calls them.

## Idea

The same plane, two loops: pydantic-ai for API models, a headless harness for frontier ones, both
recorded. Unverified and to check before any size is trusted: that a headless Claude Code session
can run with every built-in tool disabled and only our server allowed, and that a subscription
tolerates being driven that way at factory rates.
