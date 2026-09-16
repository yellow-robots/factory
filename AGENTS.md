# factory

The factory is `builder.py`: a program that runs a cold model session over a directory, the world, until the world's tests pass, under walls the model cannot cross. It is built one version at a time and its own repository is its first world. Since v0.3 the code is written by `builder.py` itself, from tests written before it runs; the first change it built is commit 48cbbe4. What it can do is read off the records of its runs. Nothing in this repository is written for a model to obey; what holds is held by tests, by the plane and by git.

You are the attended agent: a model in some harness, resuming this work cold, working with the owner. This file is for any such model. The state of the work is never narrated here; it is derived from git and the files, as below.

## Orient yourself

Run these before reading anything else, from the root of the checkout or worktree you are in:

```sh
uv run python -m unittest -q                                       # the factory's tests; no provider, no network, no docker
git tag -l --format='%(refname:strip=2) %(objectname:short)'       # the released versions
git log --oneline "tags/$(git describe --tags --abbrev=0)..HEAD"   # what happened since the last one
git status --short                                                 # what is not committed; see the last section
ls docs/versions docs/seeds                                        # the versions and the backlog
ls "$(git rev-parse --git-common-dir)/../runs" | tail -3           # the last run records; see the last section
```

Then derive:

- The version in flight is the note in `docs/versions/` whose name is not a tag. Its seeds are the notes in `docs/seeds/` whose `version` names it.
- A seed's stage is its `status`. `open`: evidence and an idea. `spec`: a `## Goal` the builder can be given, assigned to a version. `building`: at least one test names it, `seed: <name>` in the test's docstring, committed red. `done`: merged and green. `docs/templates/seed.md` states what each status requires; `docs/backlog.base` ranks the seeds.
- What the builder does and refuses is `README.md`; the walls are the constants at the top of `builder.py`; the exact behaviour is `test_builder.py`.
- A run is a directory under `runs/`: read `numbers.json` first (`stopped`, `check`, cost, counts), then `response.md`, `diff.patch` and `wire.jsonl`.

## How a version is made

The owner and the attended agent choose seeds from the backlog and promote them to specs: a version is assigned, the idea becomes a goal. For each spec the attended agent writes the tests that name the seed, commits them red on a branch in a git worktree, and runs `builder.py` on that worktree with the seed's goal. The factory writes the code. The attended agent reads the record and the diff, commits the diff as the factory's work, merges it, and tags the merge with the version; the version note holds the changelog. The attended agent does not write code the factory could write and does not touch a test to make a build pass, because the factory's ability to do it is what is being measured; the plane refuses the model the same. Tags are plain until seed `the-gate` lands; the gate cuts them annotated with the changelog and renders `CHANGELOG.md`.

## Commands

- `uv run python -m unittest -v`: the factory's own tests. Nothing external is needed.
- `uv run builder.py <world> "<goal>"`: one build. Needs the DeepSeek key in `~/.config/factory/deepseek.key` and docker, since the check runs in a container built once from the world's `uv.lock` and `check.Dockerfile`. Leaves `runs/<utc-stamp>/` beside the `builder.py` that ran, never in the world: run it from the main checkout and pass the worktree as the world. Exits 0 when the model returned a report, 1 on a cap or a provider error, 2 on a usage error. The cost and the time are in the record.
- `git worktree add <path> -b <branch>`: a world for a build. `.claude/worktrees/` is an ignored place for one.
- `git push origin main --tags`: the mirror is `git@github-joam:yellow-robots/factory.git`. `github-joam` is an SSH alias on this host that selects the owner's key; two GitHub identities share the machine.

## Not derivable from the repository

- `docs/` is an Obsidian vault the owner keeps open. Obsidian rewrites a file it shows: frontmatter reordered, a `{{...}}` in the frontmatter destroyed, a `.base` file reformatted. A dirty `docs/` may be the owner's content or Obsidian's rewrite; read the diff before committing or discarding it.
- A version exists only as a tag. Commit 48cbbe4 is titled `v0.4` and belongs to no version.
- Branches `bootstrap` and `v0.1` to `v0.4` are leftovers of past worktrees; `v0.1` to `v0.3` share their names with the tags, so git warns and prefers the tag. Write `tags/v0.3` where it matters.
- `runs/` and `plans/` are ignored. The records exist in the main checkout on this host only, until seed `commit-the-runs` lands. `plans/` is scratch for plan files; the plans of v0.2 and v0.3 are appended to their version notes.
- The model is DeepSeek `deepseek-flash`. pydantic-ai does not know the name, so `builder.py` carries a profile override; genai-prices has no row for it, so the price table in `builder.py` is the cost source. Thinking is on by default and ignores temperature. The key is never printed or committed.
- The history before this repository, v1 and the design that was abandoned for it, is in the owner's Obsidian vault at `/srv/obsidian/vaults/obsidian/03 archive/factory-v1/`. Reference, never a plan.
