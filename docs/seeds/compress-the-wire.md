---
type: seed
status: open
summary: A record's wire carries the whole context of every request and is the bulk of runs/; compress it once the build is reviewed and committed.
value: 2
effort: S
version:
---

## Evidence

Twelve records, 8.8 MB on disk on 2026-09-16; `wire.jsonl` repeats the conversation in every request it records, so a build of 23 requests over 800k input tokens is most of it. The owner, 2026-09-16: everything in the run folder is valuable and size is not a problem; compress the wire when the work is done and reviewed. Git compresses its objects, so the gain is in checkouts, clones and the eye that lists a record.

## Idea

Done and reviewed is the factory's commit: the attended agent compresses `wire.jsonl` to `wire.jsonl.gz` before committing the record, and the gate's `check` reports a committed record whose wire is not compressed, so a forgotten one cannot reach a release. Readers use `gzip -d` or `zcat`; nothing else in the record changes.
