---
type: seed
status: open
summary: Every read stays in the conversation; G1 spent 155k input tokens on three edits, and that curve decides how large a checkout the builder can work in.
value: 4
effort: S
version:
---

## Evidence

`20260915T160616Z`: input_tokens 155,449 for 12 requests and 1,016 lines read; `builder.py` alone is three reads of 300 lines. Cache hits covered 137k of it, so the money was small ($0.009), but the context grows with every call and the caps were set without knowing the curve.

## Idea

Measure input tokens per request across the failure-mode set before adding anything. Likely answers when the curve bites: a `search` function so the model reads less, or a compact map of the checkout; both are also the owner's item 3, inspecting the codebase.
