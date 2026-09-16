---
type: front-door
reviewed: v0.3
---

# factory

You are the attended agent: a model in Claude Code, resuming this work cold. This page is for
you. Read it, then run; everything else is derived from what running shows.

The factory is a cold session that changes a world until its tests pass, under walls it cannot
cross (`builder.py`). The division: the attended agent writes the goal and the red tests; the
factory writes the code; the attended agent reviews the diff, commits it as the factory's, and
tags the version. Nothing in this repository is a rule written for a model to follow; rules are
tests, gates and the plane.

## Run first

```sh
cd /opt/yellow-robots/factory
uv run python -m unittest -q        # how well it stands; no provider, no docker
git log --oneline -6 && git tag -l  # what exists; the tag is the version of record
git status --short docs/            # owner edits in the vault; commit them before working
ls runs | tail -3                   # the last runs; numbers.json first, then response.md
```

## Where things are

- `builder.py` the factory; `test_builder.py` its acceptance tests, written before the code;
  `check.Dockerfile` the image the check runs in. `README.md` describes the current version.
- `docs/` this vault. `seeds/` is the backlog: a seed becomes a spec by filling the fields its
  next stage requires, see [[templates/seed]]; `versions/` holds one note per version, its specs
  and its changelog; [[seeds/seeds.base]] ranks and groups the seeds.
- `runs/` the record of every run: goal, wire, messages, checks, diff, numbers.
- History: `04 projects/factory-v1/` in the Obsidian vault at `/srv/obsidian/vaults/obsidian`,
  the v1 iterations and findings and the v2 design document. Reference, never a plan.

## The rule

The version in flight is the highest note in `versions/` whose tag does not exist. Its specs are
the seeds whose `version` names it. A version is complete when its tag exists with the changelog,
its seeds are `done`, and this page has been reviewed against the seeds it delivered.

## Now

%% hand-written until the gate renders this section; reviewed at every release %%

- Tags: `v0.1` the observer, `v0.2` the observer on pydantic-ai, `v0.3` the builder (on the
  README commit that followed the code). `main` is past `v0.3` by the G1 red test, the factory's
  change that made it green (commit 48cbbe4, titled `v0.4` before that number was given to the
  gate; it belongs to no version) and the docs commit.
- In flight: [[versions/v0.4]], the gate. Its specs are the seeds assigned to `v0.4`.
- Runs: eight in `runs/`. The builder's two are `20260915T160616Z` (green, 3 edits) and
  `20260915T160651Z` (the honesty probe: red, no edits, by design).
- The vault is edited live by the owner; `git status docs/` can change between two commands.
  Commit what is there when you start, and do not treat it as stable.
- Model: DeepSeek `deepseek-flash`, key in `~/.config/factory/deepseek.key`, never printed.
