---
created: 2026-09-19
type: seed
status: open
summary: The older records-only configuration is a path no instance takes any more; it is what keeps MODEL alive, and it is where the key wall still commits a record it has not searched.
value: 4
effort: S
reporter: attended agent
kind: integrity
version:
---

## Evidence

2026-09-19, read in `builder.py` at v0.16 by the attended agent, correcting what this seed said when it was filed on the 18th. It claimed `MODEL` and `KEY_FILE` were both present with nothing left that reads them. Half of that is true and half is not, and the half that is not is the interesting one.

`KEY_FILE` is dead as claimed: `read_key(path=None)` falls back to it, and both of the two callers in the program pass a path, so the default is never taken and no test patches it any more.

`MODEL` is not dead. It is `build_agent`'s default `model_name`, and it is what `main` runs on when `instance_role("builder")` raises and the configuration names neither `roles` nor `work` -- the older, records-only configuration, kept when the roles arrived at v0.15. On that path the key is the empty string.

That empty key is where the wall still fails open. [[the-search-that-answers-for-no-keys]] made a record searched for nothing refuse to commit, and had to exempt one case to stay green: a caller naming the empty string. The only caller that does is `main` on that path, and the only thing that runs it is one configuration inside `test_a_run_without_a_store_is_a_usage_error`, which writes `records = ...` and nothing else to prove where the configuration is found when the environment names none. The test is about where the file is, not about running with no roles.

So one leftover path keeps a constant alive, keeps an exemption in the key wall alive, and is exercised by a test that does not mean to exercise it.

2026-09-22, at c3baaad, by the attended agent from the review of run 20260921T215305Z (docs/reviews/20260921T215305Z.md). Two more facts for the Goal that builds this, since it is the next to touch `builder.py`'s main. First, `MODEL` has a second consumer now: `priced()` keys the price table on it at `builder.py:189`, and the comment above `PRICE` says the table "stays the source for `MODEL`", so removing the name means naming what keys the table. Second, four comments left behind by v0.22's `SpendModel`, which asks the spend at every request: `builder.py:128` says the hard ceiling is "raised from a tool"; `run`'s docstring at `builder.py:857` says the tools are what land a run on what it has spent; `builder.py:828` calls a `Tools` built without `spent` "a tool-less caller"; `README.md:59` says the spend is asked at every call. None is behaviour; all four lie to the next reader.

## Idea

The records-only path goes. `main` reads the `builder` role as it reads the store, and a configuration that cannot name one is the usage error it already is for a configuration that names `roles` or `work` badly -- there stops being a third case. `MODEL` and `KEY_FILE` go with it, and so does the empty-key exemption in `commit_record`, since nothing can then name an empty key. The test that proves where the configuration is found names a role in it, which is what every configuration of an instance has named since v0.15.
