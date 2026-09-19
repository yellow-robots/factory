---
created: 2026-09-20
type: seed
status: rejected
summary: The factory calls its model deepseek-flash and the price table knows only deepseek-v4-flash; measured, that table's row is a different model's numbers, so the label stays and the factory's own price is the source rather than the fallback.
value: 3
effort: S
version:
---

Rejected 2026-09-20: the premise was that the two price sources agree and that the library's is the better one, and both halves are false -- `genai_prices`' `deepseek-v4-flash` row prices the same run at 0.73x or 1.45x the factory's table depending on the hour, and DeepSeek's own page gives `deepseek-flash` numbers that are neither. Switching the label would replace a correct price with a wrong one. What was true in it -- that the table is this model's source and not a fallback, and that it prices every run at peak -- survives in [[the-budget-that-counts-files]], which is the one thing that reads the number to make a decision.

## Evidence

2026-09-20, checked in the installed packages and against DeepSeek's published pricing by the attended agent, after the owner pointed out that the label is a choice the factory made rather than a gap in the library.

`genai_prices` holds `deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-chat`, `deepseek-reasoner` and three `v3` rows, and nothing matching `deepseek-flash`. The factory runs as `deepseek-flash`, so `usage.cost` is `None` on every run and `cost_source` reads `table` -- the constant in `builder.py` -- in **all 190 records that carry the field**. `UsageLimits.cost_limit`, which the library gained in v2.23.0, cannot bind for a run whose cost it cannot compute: it warns and does nothing.

So far the seed was right. Then the two sources were compared on one real run, 20260919T225154Z, 1,557,544 input tokens of which 1,489,152 were cache reads, and 19,130 output:

| source | price | vs the table |
|---|---|---|
| `builder.py`'s `PRICE` | $0.05241 | -- |
| `genai_prices`, run at 22:00 UTC | $0.03810 | 0.73x |
| `genai_prices`, run at 07:00 UTC | $0.07619 | 1.45x |

The library's row carries a time-of-day constraint, so the same tokens cost twice as much between 01:00-04:00 and 06:00-10:00 UTC. That much is real -- DeepSeek does charge by the hour. The numbers are not. api-docs.deepseek.com/quick_start/pricing, read 2026-09-20, gives **`deepseek-flash`** at $0.006 cache hit, $0.3 cache miss and $1.2 output per 1M tokens at peak, half that off peak. `genai_prices`' `deepseek-v4-flash` gives $0.014, $0.44 and $1.32 at peak: not DeepSeek's `deepseek-flash` at either rate, and not a constant multiple of it either (0.43x, 0.68x, 0.91x). The row is a different model's.

The factory's table is exactly DeepSeek's peak column for `deepseek-flash`, which is what its comment has said since v0.2 and what it still is.

The one hazard in going back was recorded in the v0.2 plan and does not arise: pydantic-ai's DeepSeek profile keys on the name and treats `deepseek-v4-*` as V4, which would force a tool choice while thinking is on. `PROFILE` sets `openai_supports_forced_tool_choice_with_thinking=False` and is passed to `OpenAIChatModel` explicitly, so the name implies nothing. The hazard was never the reason to stay; the price is.

## Idea

None. The label is correct and the library's row is wrong for the model behind it. `cost_source` reading `table` on every record is not a gap to close.
