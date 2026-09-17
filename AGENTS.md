# factory

The factory is `builder.py`: a program that runs a cold model session over a directory, the checkout, until the checkout's tests pass, under walls the model cannot cross. It is built one version at a time and its own repository is its first checkout: since v0.3 its code is written by `builder.py` itself, from tests written before each build, and v0.4 is the first version made that way. What it can do is read off the records of its runs. Nothing in this repository is written for a model to obey; what holds is held by tests, by the tools, by the gate and by git.

You are the attended agent: a model in some harness, resuming this work cold, working with the owner. This file is for any such model. The state of the work is never narrated here; it is derived from git and the files, as below.

## Orient yourself

Run these before reading anything else, from the root of the checkout or worktree you are in:

```sh
uv run gate.py check                                               # the vault against its templates and the repository; silent when they agree
uv run python -m unittest -q                                       # the factory's tests; no provider, no network, no docker
git tag -l --format='%(refname:strip=2) %(objectname:short)'       # the released versions
git log --oneline "tags/$(git describe --tags --abbrev=0)..HEAD"   # what happened since the last one
git status --short                                                 # what is not committed; see the last section
ls docs/versions docs/seeds                                        # the versions and the backlog
uv run runs.py | tail -3                                           # the last run records, as rows of the table
```

Then derive:

- The version in flight is the note in `docs/versions/` whose name is not a tag; there is at most one. Its seeds are the notes in `docs/seeds/` whose `version` names it.
- A seed's stage is its `status`. `open`: evidence and an idea. `spec`: a `## Goal` the builder can be given, read by the gate with the builder's own reader, assigned to a version. `building`: at least one test names it, `seed: <name>` in the test's docstring, committed red. `done`: merged and green. `rejected`: a way out at any stage. `docs/templates/seed.md` states what each status requires and the gate checks it; `docs/backlog.base` ranks the seeds.
- What the builder does and refuses is `README.md`; the walls are the constants at the top of `builder.py`; the exact behaviour is `test_builder.py`. The gate's is `test_gate.py`, the table's `test_runs.py`, the evaluation harness's `test_evals.py`. The model has six tools: list, read, search, write, edit, check.
- A run is a directory under `runs/`: read `numbers.json` first (`stopped`, `check`, `head`, cost, counts), then `response.md`, `diff.patch` and the wire, `wire.jsonl` fresh from a build and `wire.jsonl.gz` once committed. `uv run runs.py` is every record's numbers as one table. The commit that took the diff names the run in its `Built-By` trailer, so the builds of a version are `git log --format='%h %(trailers:key=Built-By,valueonly)' tags/<previous>..tags/<version>`, and the run's `head` is the red commit it started from.
- A review is a note in `docs/reviews/`, named after the record it reviewed, one per independent review: each finding with its severity, whether the attended agent reproduced it, and what it became, `test <name>`, `case <name>`, `seed <name>` or `none:` with the reason. The gate checks the note as it checks a seed, so a release cannot carry a verified finding nobody judged. Every verified defect is judged twice: a test when the factory's code was wrong, a case when the model's behaviour was.
- `cases/` is the evaluation set: one directory per case, a goal, a red test against this repository's own code and the word that says what a pass is, `pass.txt`, each probing a known way for the builder to fail; the harness hides `cases` from the builder's tools for the runs it starts, so the model never reads the word. `uv run evals.py` runs every case three times in throwaway worktrees and prints one table per case; its records are ordinary records whose goal begins `case: <name>`, so `runs.py` shows them beside the builds, and a case with `held_out/` adds `held_out.log` and `held_out.json` of the second check to its records.

## How a version is made

The owner and the attended agent choose seeds from the backlog and promote them to specs: a version is assigned, the idea becomes a goal. For each spec the attended agent writes the tests that name the seed, commits them red on a branch in a git worktree, and runs `builder.py` from the main checkout with that worktree as the checkout and the seed's path, `docs/seeds/<name>.md`, as the goal: the builder reads the seed's `## Goal` from the checkout's commit and records the seed's name. The factory writes the code. The attended agent reads the record and the diff, copies the record into the worktree, compresses its wire to `wire.jsonl.gz`, commits both as the factory's work, and hands the diff to an independent reviewer, a fresh session in this harness that reads the Goal, the diff and the tests and probes the change in throwaway directories; the review's findings go into a note in `docs/reviews/` from its template, each verified by the attended agent and judged, a test and a follow-up build on the same seed when the factory's code was wrong, a case or a seed when the model's behaviour was, or none with the reason. When every seed of the version is done, the attended agent revises this file, writes the version note's changelog, fast-forwards `main` and runs `uv run gate.py release <version>`: the gate refuses until everything derived agrees, then cuts the annotated tag and renders `CHANGELOG.md`. The attended agent does not write code the factory could write and does not touch a test to make a build pass, because the factory's ability to do it is what is being measured; the tools refuse the model the same.

## Commands

- `uv run gate.py check`, `uv run gate.py render`, `uv run gate.py release <version>`: the gate. Problems go to stdout, one per line, starting with the path; exit 1 when there is any, 2 for a usage error, silence and 0 otherwise. `render` writes `CHANGELOG.md`. `release` also needs a clean tree, `AGENTS.md` changed since the previous tag, a green suite and at least one changelog bullet in the version note.
- `uv run python -m unittest -v`: the factory's own tests. Nothing external is needed.
- `uv run runs.py`: the records as a tab-separated table, one row per record, a header first; nothing is written. Any argument is a usage error.
- `uv run evals.py [--runs N] [case ...]`: the evaluation set, every case N times (three by default) in throwaway worktrees of this repository at `HEAD`, the case's files and test committed there first; one tab-separated table per case of counts (green, held out, honest, refused, passed by the case's word, a green case only when its held-out check passed too), medians (tool errors among them, the model's `error:` returns that no wall gave) and, beside the medians of requests, cost and seconds, their spread over the runs as `min-max`; after the table the set's pass rate and its standard error under a uniform prior. A case may hold `held_out/`, tests the model never sees, run after a green build. Needs the key and docker like a build; the records land in `runs/` like a build's. Exit 1 when any run was capped or errored, 2 for a usage error.
- `uv run builder.py <checkout> "<goal>"`: one build, the goal text or the path of a seed, `docs/seeds/<name>.md`, whose `## Goal` is then the goal. Needs the DeepSeek key in `~/.config/factory/deepseek.key` and docker, since the check runs in a container built once from the checkout's `uv.lock` and `check.Dockerfile`. Refuses a directory that is not a git checkout, and a checkout with uncommitted or untracked changes, exit 2. Leaves `runs/<utc-stamp>/` beside the `builder.py` that ran, never in the checkout. Exits 0 when the model returned a report, 1 on a cap or a provider error. The cost and the time are in the record.
- `git worktree add <path> -b <branch>`: a checkout for a build. `.claude/worktrees/` is an ignored place for one.
- `git push origin main --tags`: the mirror is `git@github-joam:yellow-robots/factory.git`. `github-joam` is an SSH alias on this host that selects the owner's key; two GitHub identities share the machine.

## Not derivable from the repository

- `docs/` is an Obsidian vault the owner keeps open. `backlog.base` changes whenever the owner adjusts a view, a filter or an order there, and a note's frontmatter is re-serialised when a property is edited there, in Obsidian's own shape; a frontmatter value that is not valid YAML, such as a bare `{{date}}`, does not survive that. A dirty `docs/` is the owner's content: read the diff and commit it as theirs.
- Four build commits of v0.7 and v0.8, cea0753, 5f7349f, 92191cc and 2a13022, wrote `Built-By` with a blank line between the trailers, which git's trailer parser does not read: `git log --format='%h %b' | grep '^Built-By:'` finds every build, `%(trailers:key=Built-By)` misses those four.
- A version exists only as a tag. Commit 48cbbe4 is titled `v0.4`; it is one change released in v0.4, not the version.
- The notes of v0.1 to v0.4, their changelog and the records before v0.5 say world for the checkout and plane for the tools; those were the observer's words.
- Branches `bootstrap` and `v0.1` to `v0.3` are leftovers of past worktrees and share their names with the tags, so git warns and prefers the tag. Write `tags/v0.3` where it matters.
- The model is DeepSeek `deepseek-flash`. pydantic-ai does not know the name, so `builder.py` carries a profile override; genai-prices has no row for it, so the price table in `builder.py` is the cost source. Thinking is on by default and ignores temperature. The key is never printed or committed.
- The history before this repository, v1 and the design that was abandoned for it, is in the owner's Obsidian vault at `/srv/obsidian/vaults/obsidian/03 archive/factory-v1/`. Reference, never a plan.
