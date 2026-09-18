---
created: 2026-09-19
type: seed
status: open
summary: `MODEL` and `KEY_FILE` are still in `builder.py` with nothing left that reads them, because the caps cut off every run that tried to take them out; two places still say where a key is, and one of them is dead.
value: 2
effort: S
version:
---

## Evidence

2026-09-19, v0.15. keys-of-the-instance moved the model and the key's place into the instance's configuration, and its last goal was to take the program's own constants out with the fallback that used them. Five runs tried. Two reached a green check with the whole change made and were cut off by the tool-call cap before they could report, so their work was discarded: 20260918T233211Z at 79 calls of 80 and 20260918T234138Z at 80, the second with the Goal quoting every line to be removed. Across the five, between fifty and fifty-five of every eighty calls were reads and searches, whatever the Goal said; naming the sites did not change it and quoting them did not either.

The attended agent then amended the spec, stated in the commit of 19 September: the usage error a configuration without a `builder` role raises is what a misconfigured instance needs and it stays; the assertion that the constants are absent was dropped, and this is where it went. What remains is dead code — nothing reads `KEY_FILE` once `read_key` is always given a path, and nothing reads `MODEL` once every caller passes a model name — and two places still say where a key is, which is the thing the seed set out to end.

## Idea

The two constants below the imports go, with `read_key`'s `path is None` branch and `build_agent`'s default for `model_name`, so the parameters are required and the configuration is the one place. The names stay gone rather than hidden: a module that keeps an attribute and refuses to answer for it, which is what run 20260918T224905Z did when it was boxed in, is the same two places to look told apart by a trick.

It is an S and it is blocked on nothing but the budget, so it goes in the first version built under caps that fit the checkout — which makes it a test of caps-for-the-checkout-as-it-is as much as a change of its own: if that seed works, this one builds in a single run.
