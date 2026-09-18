---
created: 2026-09-16
type: seed
status: open
summary: A second role, read only, that answers whether a build's code does what its tests claim and what else it changed, with findings it has reproduced and a verdict, recorded like any other run.
value: 5
effort: M
version:
---

## Evidence

Every diff so far was read by the attended agent, a model in another harness. The independent reviews of v0.2 and v0.3 found real defects the builder and the attended agent had missed. Pinned by the owner on 2026-09-16 until the builder is validated.

2026-09-17, counted from the notes by the attended agent: the eight notes of `docs/reviews/` hold 60 findings, 15 defects and 45 smells, every one reproduced by the attended agent, all in builds whose check was green; every defect became a test, and of the smells 23 became tests, 2 seeds and 20 were judged `none`. Of the seven seeds the factory built from a seed's path, six had a green first build and five took a second red commit after a review, four of them after a green first build (analyst-on-api-models), and built-by-trailer took four reviews in v0.13, three of which said the tests did not pin the Goal. The builder builds what the tests ask and what they do not ask is found by review, so review is where the factory's quality is won today, and it is held outside the factory: the reviewers are Opus subagents of the attended agent's harness, prompted by hand, their findings typed into the note by the attended agent, no record of their runs kept.

2026-09-18, v0.14 released: its three reviews hold 49 findings, 14 defects and 35 smells, each reproduced by the attended agent before it was judged, against four commits that are tagged. That is a labelled corpus with ground truth, and it decays as the code moves away from those commits.

2026-09-19, the owner's direction, in conversation with the attended agent: the pin is lifted and this role is shaped first. Checks can be gamed, so a commissioner cannot be satisfied by running the checks alone — the checks are the contract, and verification inspects the code as well as running them. Verification is a commissioner's problem and the market already prices it; we are on both ends of it as the factory's first commissioners, so whatever we need in order to prove a task was done correctly is what a commissioner needs to run. The direction note of the same day records the decisions this Idea rests on.

## Idea

A second program of the factory's, beside `builder.py`: a cold model session over a delivered tree, read only, with a run recorded in the store like any other, because a role that cannot be measured cannot be given a responsibility.

**What it answers.** Two questions a machine cannot: does the code do what its tests claim, or does it satisfy them without doing it; and what else did it change. Two machine preconditions run first because they are cheap, and a failure of either needs no model: the tests pass, and the tests are the ones that were commissioned rather than the ones delivered.

**Its discipline.** A finding is not reported unless it has been reproduced, which is what the notes already record as `verified:`; and a finding must be reproducible from the artefact the commissioner holds — the diff, the tests, the check — because one that can only be understood by reading our record settles nothing. The builder's record may be read as a lead and never stand as a ground; whether reading it anchors the reviewer on the builder's account rather than on the artefact is measured rather than assumed, by running both ways.

**Its confinement.** It cannot write, cannot fix what it finds, cannot push and cannot spend: a reviewer that could fix would become a builder and acquire an interest in finding less. It executes nothing of the project's, so it needs no container; the risk it carries instead is the text it reads, since code, tests and a seed can all carry instructions aimed at a model. That risk is bounded by the same confinement — a compromised reviewer produces one wrong verdict, not a compromised machine — and the dangerous direction is a false pass, which the commissioner's own run of the tests catches.

**Its answer.** One fixed claim, whether the contract is met, and findings beside it with the severity the notes already use, defect and smell. The strictness is not a setting: a verdict whose meaning varies by commissioner is not comparable across runs, and the tolerance a commissioner needs is already in the severity split. It leans harsh, because quality is the product.

**Its model.** Stronger than the builder's, which needs a role to name the model and the key it runs on: keys-of-the-instance. That the stronger model is the better reviewer is a hypothesis, and mutants are how it is answered rather than assumed.

**Its instrument, and what waits.** Mutants: a known defect introduced into a green commit, and the catch rate over versions; steering text planted beside a defect measures how suggestible it is. The corpus of v0.14's 49 findings is a second instrument and a floor rather than a target, since it was produced by the harness this role replaces and so measures agreement rather than correctness. What waits for a later version: the stopping condition — how much it must look at before it may say the contract is met — which is under research; the deterministic quality tools it would judge by, which belong in the check first so the builder is held to them (quality-checks); and the verdict's place in the loop as a note beside a proposed commit, which is coordination and not this role.

Its read-only tools are where `pydantic-ai-harness`'s `FileSystem(read_only=True)` is finally worth trying against the two the factory hand-wrote, judged by the runs, as the v0.2 plan said it would be when a version first needed it.
