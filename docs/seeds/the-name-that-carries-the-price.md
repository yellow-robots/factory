---
created: 2026-09-20
type: seed
status: open
summary: The factory calls its model deepseek-flash, the price table knows it as deepseek-v4-flash, and that one word is why every run has priced itself from a constant in the program instead of from the library.
value: 3
effort: S
version:
---

## Evidence

2026-09-20, checked in the installed packages by the attended agent after the owner pointed out that this is a choice the factory made rather than a gap in the library.

`genai_prices` holds `deepseek-v4-flash`, `deepseek-v4-flash-0731` and `deepseek-v4-flash-latest`, and nothing matching `deepseek-flash`. The factory runs as `deepseek-flash`, so `usage.cost` is `None` on every run, and `cost_source` reads `table` -- the constant in `builder.py` -- in **all 186 records that carry the field**. `UsageLimits.cost_limit`, which the library gained in v2.23.0, cannot bind for a run whose cost it cannot compute: it warns and does nothing.

DeepSeek accepts both names for the same model at the same price; `deepseek-v4-flash` is the retired label and `deepseek-flash` the current one, which is why the factory chose it. The v0.2 plan recorded the one hazard in going back: pydantic-ai's DeepSeek profile keys on the name and treats `deepseek-v4-*` as V4, which would have it force a tool choice while thinking is on, and DeepSeek answers that with a 400. The factory already carries the answer -- `PROFILE` sets `openai_supports_forced_tool_choice_with_thinking=False` and is passed to `OpenAIChatModel` explicitly, so it overrides whatever the name would imply.

Since v0.15 the model is named in the instance's configuration and not in the program, so this is a configuration change and a verification, not a code change.

## Idea

The instance names the model by a label the price table knows, so a run's cost is the library's and `cost_source` says so. The factory's own `PRICE` table stays as the fallback it was written to be, and what it is worth keeping for is that it answers when the library cannot -- a role on a model nobody has priced.

Three things to establish rather than assume, and the run records answer all three. That the 400 does not return, which one build settles. That the two sources agree on a price, by comparing the library's number against the table's on the same run -- they should, and a disagreement is worth more than the change is. And that a record's cost stays comparable across the switch, because `cost_source` changing mid-history is a change in what the column means, which every reading of the table afterwards has to know about.
