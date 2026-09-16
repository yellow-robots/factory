---
type: seed
status: spec
summary: A record's wire carries the whole context of every request and is the bulk of runs/; compress it once the build is reviewed and committed.
value: 2
effort: S
version: v0.5
---

## Evidence

Twelve records, 8.8 MB on disk on 2026-09-16; `wire.jsonl` repeats the conversation in every request it records, so a build of 23 requests over 800k input tokens is most of it. The owner, 2026-09-16: everything in the run folder is valuable and size is not a problem; compress the wire when the work is done and reviewed. Git compresses its objects, so the gain is in checkouts, clones and the eye that lists a record.

## Goal

`check` reports every record whose wire is committed uncompressed: a path `runs/<stamp>/wire.jsonl` that git tracks is a problem naming the record, `runs/<stamp>/wire.jsonl.gz` being the expected form. A `wire.jsonl` that git does not track is a build not yet reviewed and is not a problem. Nothing in `builder.py` changes: it writes `wire.jsonl`, and the attended agent compresses it at the factory's commit. The tests in `test_gate.py` whose docstring names this seed define the behaviour.

After the build, by the attended agent: the wires of the records already committed are compressed, and `AGENTS.md` names the step.
