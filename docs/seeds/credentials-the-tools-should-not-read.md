---
created: 2026-09-19
type: seed
status: open
summary: The key wall guards the record, which is the second copy; a credential sitting in a customer's checkout is sent to the provider the moment the model reads it, and nothing stops the read.
value: 4
effort: M
reporter: research
kind: integrity
version:
---

## Evidence

2026-09-19, from the research the owner commissioned into secret detection, and checked against `builder.py` by the attended agent.

The wall that searches a record before it is committed protects the factory's own key in the factory's own artefact, and it does that well. It does nothing about a credential that belongs to whoever commissioned the build, and the reason is the ordering: the record is written after the run. By the time a customer's `.env` is in `messages.json`, it has already been sent to the provider. **The record is the second copy.**

Three channels carry it there, all read in `builder.py`. `Tools._resolve` blocks `HIDDEN` at the root and any `.git` component at any depth, and nothing else -- a `.env`, `.npmrc`, `id_rsa`, `kubeconfig` or `terraform.tfstate` anywhere in a checkout is a file the model may name and read. `check-<n>.log` is the container's stdout and stderr verbatim, so whatever the checkout's tests print is in the record. And `messages.json` and the wire carry every file the model read.

This was hypothetical while the factory built only itself. `build.py` clones an arbitrary repository and branch, so it stops being hypothetical with the first outside commission.

The research also settles what does not help. Of nine secret-detection tools benchmarked over 15,084 hand-labelled secrets, five score under 7% precision, and the one configuration that lifts precision to 90% is live credential verification -- sending candidates to a third party over the network, which is the thing this factory exists not to do. Across this store's 189 records, gitleaks found nothing and TruffleHog found two false positives. A scanner at the commit boundary would be cheap and would also be too late.

## Idea

The refusal belongs in `Tools.read`, beside the walls already there, and it is a wall rather than a search: a file whose name is a credential's by convention is not the model's to read, and the tool says so in the words the other refusals use. What that list holds is the spec's, and it should be short and named rather than clever -- the patterns that exist because a convention exists, not an attempt to recognise a secret by looking at it.

Two things follow that the spec must decide. A checkout may legitimately hold a `.env.example`, so the rule is about the name and the list must say which. And a refusal is visible to the model, which learns that a file it cannot read is there; that is the same trade the protected paths already make.

What this cannot reach is a credential printed by a test into `check-<n>.log`, because the container's output is the run's evidence and truncating it would cost more than it saves. That is worth stating in the Goal as out of scope rather than leaving it to be discovered.
