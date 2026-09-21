---
created: 2026-09-19
type: seed
status: open
summary: The record says which cap ended a run by matching English in the library's exception message, so a library that rewords it turns every later record's answer to the empty string and nothing in the suite fails.
value: 3
effort: S
reporter: review
kind: integrity
version:
---

## Evidence

2026-09-19, found by the independent reviewer of runs 20260919T064941Z, 20260919T065440Z and 20260919T070052Z, reproduced by the attended agent. `which_cap` answers `calls` or `requests` by looking for the substrings `tool_calls_limit` and `request_limit` in the text of the `UsageLimitExceeded` the library raised. It matches the installed pydantic-ai exactly, and every branch is right today. But the record's `cap` is then a substring match on an exception message: pydantic-ai is pinned, so nothing breaks now, and the first bump that rewords either sentence degrades every record written afterwards to the empty string, silently, with the suite green.

The same fact is available without reading English. The run has `usage.tool_calls` and `usage.requests`, and `limits(budget)` has `tool_calls_limit` and `request_limit`; the one that was reached is the one that bound.

## Idea

`which_cap` is told the usage and the limits rather than the message, and answers by comparing numbers. The detail stays in the record as it is, because it is the library's own account of what happened; what the table reads is derived from counts. A run that was capped and matches neither limit is worth seeing, so it answers with neither rather than guessing, as it does now.
