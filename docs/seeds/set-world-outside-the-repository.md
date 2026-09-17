---
created: 2026-09-17
type: seed
status: open
summary: A run of the set works in a worktree of the whole repository, where the tools hide the answers but code the model has `check` run can read them; each run's world is built outside the repository from a pinned commit, with nothing of the set, its records or its notes in it.
value: 5
effort: M
version:
---

## Evidence

2026-09-17, from the research on eval practice asked by the owner, its claims about this repository checked by the attended agent. `Sandbox.run` mounts the whole checkout read-only at `/w` and returns the check's output to the model, and the model may edit the modules the tests import, so code it writes can print what the tools hide: a case run's worktree holds `cases/`, with 13 tracked pass words and held-out tests, and at 6cb9ab7 1,203 tracked files under `runs/`, among them `runs/20260917T113653Z/diff.patch`, the root fix of `symptom_not_root`. No run of the set did it. Through the tools themselves 29 of the 33 runs of v0.12's set read or searched the notes and 8 read a note naming their own case (notes-hidden-from-the-set). Practice removes the data rather than hiding it: Anthropic's "Demystifying evals for AI agents", 9 January 2026, asks for a clean environment per trial and reports Claude examining the git history of previous trials (https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); SWE-bench's maintainers opened an issue, 3 September 2025, on agents reading future commits through `git log --all`, the mitigation being to remove the future repository state (https://github.com/SWE-bench/SWE-bench/issues/465); the Agentic Benchmark Checklist asks that agents be isolated from ground truth and that the environment be frozen, T.5 and T.6 (https://arxiv.org/abs/2507.02825). All three read by the attended agent on the day. The cases act on HEAD, so their world changes with every version.

## Idea

Each run's world is a fresh repository of one commit outside this one, made from an export of a pinned commit with no `runs/`, no `cases/` and none of the notes that describe the set, `docs/`, `AGENTS.md`, `CLAUDE.md` and `CHANGELOG.md`, the case's goal, visible test and files added in that commit; nothing of this repository's history is in its `.git`. The pin is named in the harness and moved on purpose, so two set runs on one pin share a world. The held-out tests run on a fresh export with the run's diff applied, never in the world the model had. `README.md` stays for the two cases whose goals name it, its paragraph on the set moved to `cases/README.md`. The price: a run no longer sees what the factory's own builds see, the notes among it. It replaces notes-hidden-from-the-set.
