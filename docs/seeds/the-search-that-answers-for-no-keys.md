---
created: 2026-09-19
type: seed
status: building
summary: A configuration that cannot say what a key is makes the record's search answer with an empty list, so the record is committed having been searched for nothing; every other case of that function refuses the commit.
value: 4
effort: S
version: v0.16
---

## Evidence

2026-09-19, built by goal c of keys-of-the-instance in run 20260918T230414Z and read by the attended agent the same night. `configured_keys` catches the ValueError `key_paths()` raises for a configuration whose `roles` are missing or malformed, and answers with an empty list; `leaked_file` then searches a record for nothing, finds nothing, and the record is committed. A configuration that cannot say what a key is turns the wall off silently — the opposite of every other case in the same function, where a file it cannot read through, a `.gz` that ends before its stream does, and a link it will not walk into all refuse the commit. Its docstring says the empty list "falls back to the program's constants as the run does", which the code never did and which the run stopped doing at goal b2.

Latent, not live: since goal b2 `main` refuses such a configuration before a record exists, so only a caller that builds a record without going through `main` can reach it, which the suite does. The wall has held since v0.13 and this is the first hole in it.

One run was spent on the fix, 20260919T000504Z, and capped at 80 tool calls with the check green: 27 reads and 29 searches for six edits, on a goal that is one small function. It is the sixth cap of eleven runs and the third to be cut off with the work done. The test below was written and taken back out of the tree so the version's suite is green; it goes back in with the build.

## Goal

The search that keeps a key out of a record never fails open, and `configured_keys` was the one place it did.

The error `key_paths()` raises is no longer swallowed. A configuration whose `roles` are missing or malformed names no key the search can use, and that refuses the commit: a `LeakedKey` carrying the words `instance.py` raised, which name the configuration's file and which fault and never a key's value, exactly as a key file that cannot be read already does.

An empty list of keys refuses the commit whatever produced it, so a `roles` table holding no role is refused too, because a record searched for nothing has not been searched. A caller that names one key itself is unaffected: it has said what to search for, and the configuration is not consulted.

The docstring says what is then true. Its sentence that the empty list "falls back to the program's constants as the run does" describes a fallback the code never had, and that the run stopped having at v0.15 when the builder began running as a role.
