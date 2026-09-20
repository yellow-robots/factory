# factory

`builder.py` runs a cold model session over a checkout until its tests pass, under walls the model cannot cross. Since v0.3 the factory writes its own code this way, from tests written before each build. `reviewer.py` is its second program: a read-only session over a delivered tree. What either can do is read off the records of its runs.

You are the attended agent, resuming cold. **This file tells you where to look, not what is true.** What holds is held by tests, by the tools, by the gate and by git; everything derivable is derived, and the only sentences here are ones no command can answer.

## Orient

```sh
uv run gate.py check                                             # vault vs templates and repo; silent when they agree
uv run python -m unittest -q                                     # the suite; no provider, no network, no docker
git log --oneline "tags/$(git describe --tags --abbrev=0)..HEAD" # what happened since the last version
git status --short                                               # uncommitted; a dirty docs/ is the owner's
ls docs/versions docs/seeds                                      # versions and backlog
uv run runs.py | tail -3                                         # the last records
```

The **version in flight** is the note in `docs/versions/` whose name is not a tag; there is at most one. Its seeds are the notes in `docs/seeds/` whose `version` names it.

## Where the answer is

Never answer these from memory or from this file. Run the command.

| question | where |
|---|---|
| what does a program do, refuse, exit | its `--help`, then `README.md`, then its `test_*.py` |
| what are the walls | the constants at the top of `builder.py` |
| exactly how does it behave | `test_builder.py`, `test_reviewer.py`, `test_gate.py`, `test_runs.py`, `test_evals.py`, `test_catch.py`, `test_keys.py`, `test_instance.py` |
| what did a run do, cost, decide | its record in the store: `numbers.json` first, then `response.md`, `diff.patch`, `wire.jsonl.gz` |
| every run as one table | `uv run runs.py` |
| how good is the builder | `uv run evals.py` over `cases/` |
| how good is the reviewer | `uv run catch.py --score` over `catches/` — free, scores records already made |
| what is a seed's stage | its `status`; `docs/templates/seed.md` says what each stage requires |
| what is ranked next | `docs/backlog.base` |
| what a review found and what became of it | `docs/reviews/<record stamp>.md` |
| which build made a commit | its `Built-By` trailer, which names the run |
| what this host is configured to run | `~/.config/factory/instance.toml` (or `$FACTORY_INSTANCE`) |

If a sentence in this file could be replaced by one of these, replace it.

## The loop

1. Owner and attended agent pick a seed and promote it: assign a version, turn the Idea into a `## Goal`.
2. The attended agent writes tests naming the seed (`seed: <name>` in the docstring) and commits them **red** on a branch.
3. Build it: `uv run build.py <repo> <branch> docs/seeds/<name>.md` (pushes the build back as one commit), or `uv run builder.py <worktree> docs/seeds/<name>.md` (builds in place; you commit it with the `Built-By` trailer).
4. Read the record and the diff. Hand the diff to an independent reviewer — a fresh session, given the Goal, the diff and the tests, probing in throwaway directories.
5. Write `docs/reviews/<stamp>.md` from its template. Verify each finding yourself and judge it: `test <name>` when the factory's code was wrong, `case`/`seed <name>` when the model's behaviour was, or `none:` with the reason.
6. When every seed is done: revise this file, write the version note's changelog, `uv run gate.py check`, fast-forward `main`, `uv run gate.py release <version>`.

## Rules

These are the ones nothing can hold, so they are written down.

- **Do not write code the factory could write.** Its ability to do it is what is being measured.
- **Do not touch a test to make a build pass.** Amending a spec and its tests *before* a build is allowed and must be stated.
- **When a Goal changes what a name means, find every place that encodes the old meaning** — not just the call sites that look like call sites. Fixtures naming a model, a `mock.patch.object` naming a function as a string, an expected value from another configuration, an arithmetic identity written longhand. This has cost more red builds than anything else.
- **Read the builder's `unsure` field carefully.** It has repeatedly been right about a blocker the attended agent was wrong about.
- **Never print or commit a key.** Reviewer prompts must forbid running `builder.py`, `build.py`, `reviewer.py`, `evals.py` or `catch.py` against a model or the network, forbid docker, and forbid reading anything under `~/.config/factory/`.
- **`main` takes ff-only merges. Never force-push.**
- **How the owner wants to be written to.** Headers, bullets and bold where they help the eye, not as decoration. Cut: preambles, flattery, repetition, restating the question, summarising what was just said, narrating steps taken or about to be taken, flourished prose. Keep: exact figures and paths, stated assumptions, and uncertainty that carries information — *~2x, fitted to one day's bill* rather than *2x*. Lead with the answer. State an error once, plainly, and move on.

## Where to write what you learn

This file is not the place. It is the entry point and it stays short.

- A **defect or an idea** → a seed in `docs/seeds/`, from the template, with dated evidence.
- A **review's findings** → `docs/reviews/<stamp>.md`, each verified and judged.
- **What a version did and why** → its note in `docs/versions/`.
- A **behaviour that must hold** → a test. That is the only thing that makes it true.
- A **number** → nowhere. Derive it. A number written here is stale the next time it is measured.

Add to this file only a fact that no command can answer and no test can hold. If you are about to paste a measurement, a status, or a paragraph explaining what a program does, it belongs somewhere above.

## Traps

Not derivable, and each has cost real time.

- **The check's container and `PIDS_LIMIT`.** The suite accumulates tasks across modules: every module passes alone at 256, the suite together does not. A build red with `cannot fork()` is this, not the builder. Raising the number is the wrong answer twice — the deadlock has no way out from inside, because a build is judged by the check that is failing, and the check runs from the *instance's* `builder.py` at its pinned tag, so a fix in the checkout does not reach the thing judging it until a version ships. Seed: `the-tasks-the-suite-never-gives-back`.
- **Building the factory's own branch from a worktree.** `build.py` pushes the build back to the branch, and git refuses to update a branch that is checked out somewhere. So before the build: check `refs/heads/<branch>` equals HEAD and the tree is clean, then `git switch --detach`. After it: `git switch <branch>` to reattach. A commit made while detached leaves the branch behind and the next build is asked of the commit before it -- this happened three times before the check became a habit.
- **The instance is pinned.** `build.py` runs the *instance's* `builder.py`, not the checkout's. A fix reaches builds only when a version ships and the instance moves to it. On this host: store `/opt/yellow-robots/factory-records`, work `/opt/yellow-robots/factory-work`, instance `/opt/yellow-robots/factory-instance`.
- **The model is the role's, not the program's.** `~/.config/factory/instance.toml` names `records`, `work`, and a `roles` table; each role names a `model`, a `key` file and optionally a `base_url`. pydantic-ai does not know `deepseek-flash`, so `builder.py` carries a profile override keyed on it. Thinking is on by default and ignores temperature.
- **Pricing.** `PRICE` in `builder.py` is one model's table and a statement about nothing else; other models are priced by `genai_prices`, asked at the address the role is served at, because one model name can be served by several vendors at different rates. A role neither can price is refused before the run starts. What bounds a run is what it has spent, so a wrong price is a behavioural defect and not a reporting one. **The table is currently believed to be about twice DeepSeek's real rate** — seed `the-table-that-bills-twice`, open.
- **`docs/` is an open Obsidian vault.** `backlog.base` changes when the owner adjusts a view; frontmatter is re-serialised when a property is edited, and a value that is not valid YAML (a bare `{{date}}`) does not survive it. A dirty `docs/` is the owner's content: read the diff and commit it as theirs. The vault is `docs/` *as git tracks it* — an ignored path is no note, so `docs/scratchpad/` bothers nothing.
- **Old git shapes.** A version exists only as a tag; commit 48cbbe4 is titled `v0.4` but is one change released in it. Four build commits of v0.7–v0.8 (cea0753, 5f7349f, 92191cc, 2a13022) wrote `Built-By` with a blank line between trailers, which git's trailer parser misses; they stay as they are, and the gate never reads them. Branches `bootstrap` and `v0.1`–`v0.3` shadow the tags of those names — write `tags/v0.3`.
- **Old words.** Notes and records before v0.5 say *world* for the checkout and *plane* for the tools.
- **The mirror** is `git@github-joam:yellow-robots/factory.git`; `github-joam` is an SSH alias selecting the owner's key, because two GitHub identities share this machine.
- **Prior art.** v1 and the design abandoned for it: `/srv/obsidian/vaults/obsidian/03 archive/factory-v1/`. Reference, never a plan.
