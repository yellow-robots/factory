---
type: seed
status: open
summary: The builder explores a world file by file; a larger world needs search and a map, once the cost curve says so.
value: 3
effort: M
version:
---

## Evidence

Owner's item 3, 2026-09-16. G1 read the whole of `builder.py` in three calls to change nine lines of it; the escape probes read everything they could reach.

## Idea

A `search(pattern)` function first, a compact structural map of the world second; each one gated by what `cost-of-context` measures.
