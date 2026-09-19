---
created: 2026-09-19
type: seed
status: open
summary: A configuration that cannot say what a key is makes the record's search answer with an empty list, so the record is committed having been searched for nothing; every other case of that function refuses the commit.
value: 4
effort: S
version:
---

## Evidence

2026-09-19, built by goal c of keys-of-the-instance in run 20260918T230414Z and read by the attended agent the same night. `configured_keys` catches the ValueError `key_paths()` raises for a configuration whose `roles` are missing or malformed, and answers with an empty list; `leaked_file` then searches a record for nothing, finds nothing, and the record is committed. A configuration that cannot say what a key is turns the wall off silently — the opposite of every other case in the same function, where a file it cannot read through, a `.gz` that ends before its stream does, and a link it will not walk into all refuse the commit. Its docstring says the empty list "falls back to the program's constants as the run does", which the code never did and which the run stopped doing at goal b2.

Latent, not live: since goal b2 `main` refuses such a configuration before a record exists, so only a caller that builds a record without going through `main` can reach it, which the suite does. The wall has held since v0.13 and this is the first hole in it.

One run was spent on the fix, 20260919T000504Z, and capped at 80 tool calls with the check green: 27 reads and 29 searches for six edits, on a goal that is one small function. It is the sixth cap of eleven runs and the third to be cut off with the work done. The test below was written and taken back out of the tree so the version's suite is green; it goes back in with the build.

## Idea

The error `key_paths()` raises refuses the commit rather than being swallowed: a `LeakedKey` carrying the words `instance.py` raised, which name the configuration's file and the fault and never a key's value, as an unreadable key file already does. An empty list of keys is refused the same way whatever produced it, because a record searched for nothing has not been searched. The docstring says what is then true.

The test, as written on the night and ready to go back:

```python
def test_a_configuration_that_names_no_key_refuses_the_commit(self):
    """seed: the-search-that-answers-for-no-keys. The search never fails open, and this was the one
    case where it did: a configuration whose roles are missing or malformed names no key, the list
    came back empty, and the record was committed having been searched for nothing. A record that
    cannot be searched is not committed; the refusal names the configuration, as the others name the
    file they could not read through, and never a value."""
    self.configure(roles="")
    record = self.runs / "20260919T000000Z"
    record.mkdir(parents=True)
    (record / "numbers.json").write_text("{}\n")
    with self.assertRaises(builder.LeakedKey) as refused:
        builder.commit_record(self.runs, record)
    self.assertIn(str(self.instance), str(refused.exception))
    self.assertNotIn("builders-own-key", str(refused.exception))
    log = subprocess.run(["git", "-C", str(self.runs), "log", "--oneline"],
                         capture_output=True, encoding="utf-8", env=builder.store_env())
    self.assertEqual(log.stdout, "", "nothing of the record is committed")
```

It belongs in `EveryKeyTest` of `test_keys.py`, whose fixtures it uses as written.
