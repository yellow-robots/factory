# factory

`builder.py` runs a cold model session over a checkout until its tests pass, under walls the model cannot cross. Since v0.3 the factory writes its own code this way, from tests written before each build. `reviewer.py` is its second program: a read-only session over a delivered tree. What either can do is read off the records of its runs.

You are the attended agent, resuming cold. **This file tells you where to look, not what is true.** What holds is held by tests, by the tools, by the gate and by git; everything derivable is derived, and the only sentences here are ones no command can answer.

## Orient

```sh
uv run gate.py next                                              # the one next step of the loop, derived; take it, then run it again
uv run gate.py check                                             # vault vs templates and repo; silent when they agree
uv run python -m unittest -q                                     # the suite; no provider, no network, no docker
git log --oneline "tags/$(git describe --tags --abbrev=0)..HEAD" # what happened since the last version
git status --short                                               # uncommitted; a dirty docs/ is the owner's
ls docs/versions docs/seeds                                      # versions and backlog
git tag -l                                                       # released versions
uv run runs.py | tail -3                                         # the last records
```

The **version in flight** is the note in `docs/versions/` whose name is not a tag; there is at most one. Its seeds are the notes in `docs/seeds/` whose `version` names it.

## Where the answer is

Never answer these from memory or from this file. Run the command.

| question | where |
|---|---|
| what does a program do, refuse, exit | `README.md`. There is no `--help`: running one wrong prints one usage line and exits 2 |
| what are the walls | the constants at the top of `builder.py` |
| exactly how does it behave | its `test_<name>.py` at the root; `ls test_*.py` |
| what did a run do, cost, decide | its record in the store: `numbers.json` first, then `response.md`, `diff.patch`, `wire.jsonl.gz` |
| every run as one table | `uv run runs.py` |
| how good is the builder | `uv run evals.py` over `cases/` |
| how good is the reviewer | `uv run catch.py --score` — free, scores records already made. **It does not name the model**: the rate is whatever the records ran on, and the `reviewer` role here is configured for another. Read the record's `numbers.json` |
| what is a seed's stage | its `status`; `docs/templates/seed.md` says what each stage requires |
| what is ranked next | `docs/backlog.base` |
| what a review found and what became of it | `docs/reviews/<record stamp>.md` |
| which build made a commit | its `Built-By` trailer, which names the run |
| what this host is configured to run | `~/.config/factory/instance.toml` (or `$FACTORY_INSTANCE`) |
| why this exists, and what would show it wrong | `docs/direction.md` |

If a sentence in this file could be replaced by one of these, replace it.

## The loop

`uv run gate.py next` prints the one step that comes next, derived from git and the vault: the rows are `loop.RULES`, in their order, over one snapshot of facts, and `README.md` says what each reads. A session is one step long -- run it, take the step, run it again -- and nothing here is remembered across steps. What it cannot derive, it cannot say, so those are written here:

- **A review is a subagent of your own harness, to a written brief -- not `reviewer.py`**, the program under evaluation. Give it the Goal, the diff, the tests and a throwaway directory to probe in; forbid it the network, docker, running the model programs, and reading `~/.config/factory/`. Verify every finding yourself before it goes in `docs/reviews/<stamp>.md`, and judge it: `test <name>` when the factory's code was wrong, `case`/`seed <name>` when the model's behaviour was, `none:` with the reason.
- **A red build's tree may be taken as the branch's base** when the run wrote the work and landed at the cap: a plain commit naming the record, no `Built-By`, the record standing as red -- so the next build fixes lines rather than rewriting them.
- **Before a build, the branch must not be checked out where the build will push**: `next` says `detach first` when it is; `git switch <branch>` after. A commit made while detached leaves the branch behind.
- **`release` tags the HEAD of wherever it runs**, and its last line is the wheel it built; the changelog's commit, `main`, the mirror and the instance are the rows `next` reads after a tag.

## Rules

These are the ones nothing can hold, so they are written down.

- **Do not write code the factory could write.** Its ability to do it is what is being measured.
- **Do not touch a test to make a build pass.** Amending a spec and its tests *before* a build is allowed and must be stated in the commit message that carries the amendment, with the new red count.
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

- **The check's container and `PIDS_LIMIT`.** The suite accumulates tasks across modules: it passed module by module at the limit of the day and not all together, which is how this was found. A build red with `cannot fork()` is this, not the builder. Raising the number is the wrong answer twice — the deadlock has no way out from inside, because a build is judged by the check that is failing, and the check runs from the *installed* product at the version last released, so a fix in the checkout does not reach the thing judging it until a version ships. What unblocks a build today is raising the limit by hand *and shipping a version*, because the check runs from the instance. Read `docs/seeds/the-tasks-the-suite-never-gives-back.md` before doing either.
- **Building the factory's own branch from a worktree.** `build.py` pushes the build back to the branch, and git refuses to update a branch that is checked out somewhere. So before the build: check `refs/heads/<branch>` equals HEAD and the tree is clean, then `git switch --detach`. After it: `git switch <branch>` to reattach. A commit made while detached leaves the branch behind and the next build is asked of the commit before it -- this happened three times before the check became a habit, and a fourth on the day the loop was built, so `next` says `detach first` and nothing yet says `reattach`.
- **The instance is pinned.** `factory-build` runs the *installed* product's `build.py`, not the checkout's; `uv tool list` names its version. A fix reaches builds only when a version ships and its wheel is installed. On this host: store `/opt/yellow-robots/factory-records`, work `/opt/yellow-robots/factory-work`; the instance is `uv tool`'s install of `factory`, and the clone at `/opt/yellow-robots/factory-instance` was v0.19's, retired when v0.20's wheel was installed.
- **The model is the role's, not the program's.** `~/.config/factory/instance.toml` names `records`, `work`, and a `roles` table; each role names a `model`, a `key` file and optionally a `base_url`. pydantic-ai does not know `deepseek-flash`, so `builder.py` carries a profile override keyed on it. Thinking is on by default and ignores temperature.
- **Pricing.** `PRICE` in `builder.py` is one model's table and a statement about nothing else; other models are priced by `genai_prices`, asked at the address the role is served at, because one model name can be served by several vendors at different rates. A role neither can price is refused before the run starts. What bounds a run is what it has spent, so a wrong price is a behavioural defect and not a reporting one. A record's cost is the work at one flat rate; DeepSeek bills half that off peak, which includes **entire weekends, Chinese public holidays and adjusted working days**, so a bill can be half a record and the record is still right. Quote a projection as a range, not a number.
- **`docs/` is an open Obsidian vault.** `backlog.base` changes when the owner adjusts a view; frontmatter is re-serialised when a property is edited, and a value that is not valid YAML (a bare `{{date}}`) does not survive it. A dirty `docs/` is the owner's content: read the diff and commit it as theirs. The vault is `docs/` *as git tracks it* — an ignored path is no note, so `docs/scratchpad/` bothers nothing.
- **Old git shapes.** A version exists only as a tag; commit 48cbbe4 is titled `v0.4` but is one change released in it. Four build commits of v0.7–v0.8 (cea0753, 5f7349f, 92191cc, 2a13022) wrote `Built-By` with a blank line between trailers, which git's trailer parser misses; they stay as they are, and the gate never reads them.
- **A version's branch and its tag share a name** — `bootstrap`, `v0.1`–`v0.3`, and every version branch from `v0.15` on. A bare name resolves to the tag, past a one-line warning: on the day v0.19 shipped, `git merge --ff-only v0.19` fast-forwarded `main` to the tag and stopped one commit short of the branch. Write `heads/v0.19` for the branch and `tags/v0.19` for the tag.
- **Old words.** Notes and records before v0.5 say *world* for the checkout and *plane* for the tools.
- **The mirror** is `git@github-joam:yellow-robots/factory.git`; `github-joam` is an SSH alias selecting the owner's key, because two GitHub identities share this machine.
- **Prior art.** v1 and the design abandoned for it: `/srv/obsidian/vaults/obsidian/03 archive/factory-v1/`. Reference, never a plan.
