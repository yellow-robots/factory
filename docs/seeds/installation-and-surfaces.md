---
created: 2026-09-16
type: seed
status: open
summary: The factory runs from the main checkout of the repository it builds, at whatever commit that holds; the instance is a checkout of its own pinned at a released tag, with its key, its store and its credential beside it, so deploying a version is an act and a version is built by the one before it.
value: 5
effort: S
version:
---

## Evidence

Owner's item 5, 2026-09-16. Today's surface, by accident: a git worktree carrying `uv.lock` and `check.Dockerfile`, tests discoverable by unittest, Docker available to the user. A version must be deployable: the artefact and its changelog are the deliverable.

2026-09-17, the owner's direction, in conversation with the attended agent: the factory can be deployed now, with the capabilities it has, and build this repository as it would any project, not knowing it is itself; what is asked is that it works as an external deployment and not as a script the attended agent invokes, in a droplet of its own in time. Read on the day by the attended agent: builds are run from the main checkout of the repository being built, so the builder that builds a version is whatever that checkout holds that hour, and the record keeps a hash of `builder.py`'s text, `wrapper`, and no tag. The key's place, `~/.config/factory/deepseek.key`, and the records' place, `runs/` beside the program, are constants of `builder.py`. The second checkout the Idea of 2026-09-16 waited for is here by the owner's word, and it is this repository seen from outside: an export of v0.13 of fifteen files held all that `builder.py` and the suite need but one test that reads `cases/` (build-from-a-pushed-branch). The value was 2 and the effort L while it was undecided.

## Idea

The instance is a checkout of the factory's code apart from every project, pinned at a released tag, on this host at first and in a droplet later, which is operations and no new design; beside it its configuration, the key's place, the store of records-outside-the-project and the credential it pushes with, which pushes build branches and never main. Deploying a version is an act: after a release the instance is moved to the new tag, so a version is built by the one before it, as a compiler's stage builds the next, and the version a trailer names is a tag. What a project must carry is what build-from-a-pushed-branch refuses the lack of, written in README for whoever prepares a project; this repository is the first such project and no exception. README says how an instance is installed and moved to a tag, for the owner and the attended agent. It comes after the version that makes build-from-a-pushed-branch is released: the first instance is pinned at that tag, and the next version is the first it builds.
