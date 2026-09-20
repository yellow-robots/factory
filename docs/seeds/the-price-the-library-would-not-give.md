---
created: 2026-09-20
type: seed
status: open
summary: The pricing call catches one of the two errors the library documents, so a provider's bad token counts become an uncaught crash that loses the record.
value: 2
effort: S
version:
---

## Evidence

2026-09-20, the independent review of [[the-role-priced-as-another]], recorded in [[20260920T103952Z]].

`genai_prices.calc_price` raises two things a caller is expected to handle. `LookupError` when it has no row, which `builder.price` catches and turns into `UnknownPrice`. And `ValueError` when it will not accept the usage at all -- `cache_read_tokens (N) cannot exceed input_tokens (M)` -- which nothing catches. pydantic-ai's own helper catches both; ours catches one.

Where it escapes to is the reason this is written down rather than shrugged at. `spent()` is called by `Tools._over_limit` on every tool call with nothing around it, and by the record's own pricing at the end of the run. The review reproduced both: the run dies mid-flight, and the record directory is left in the store half-made, never committed. A run that did real work loses all of it.

What it needs to happen is a provider reporting more cache reads than prompt tokens. Neither the review nor the attended agent found a path to that from DeepSeek or Zhipu, and `deepseek-flash` cannot reach it at all because the table answers first and `table_price` merely returns a negative number. So this is latent: a provider's bug becoming our lost record.

Two smaller things sit in the same call. `LookupError` covers `KeyError` and `IndexError`, so a data bug inside the library would be reported as *no price for model X*, which is fail-closed but says the wrong thing. And `require_price`'s docstring claims its answer *cannot disagree with the number the run would carry*, which is not true of this case: it prices zero tokens, and zero tokens never trip a usage the library rejects.

## Idea

A run does not lose its record because a number could not be computed.

The pricing call handles what the library documents it raises, and what it cannot price is `UnknownPrice` like anything else it cannot price -- which, after [[the-role-priced-as-another]], is already refused before the run starts, so the only way to meet it mid-run is a provider that lied about its own token counts. That is a thing to record and not a thing to die of: the record is the point of the run, and the last thing to give up.

Worth doing when something else is already open in that function. It is one `except` clause and a docstring that currently overclaims, and there is no evidence of it ever having fired.
