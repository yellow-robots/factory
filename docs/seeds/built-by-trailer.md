---
created: 2026-09-17
type: seed
status: building
summary: A build commit whose `Built-By` line git does not parse as a trailer is a build the version's derived list misses; the gate should refuse it at release.
value: 3
effort: S
version: v0.13
---

## Evidence

2026-09-17: of the 32 commits carrying a `Built-By` line, git parses 27. Four released in v0.7 and v0.8, cea0753, 5f7349f, 92191cc and 2a13022, and the first commit of v0.9 before it was amended, wrote a blank line between the trailers, so the trailer block git reads is the last paragraph alone and `git log --format='%(trailers:key=Built-By,valueonly)'`, the command AGENTS.md gives for the builds of a version, prints nothing for them. Nothing checked it; the attended agent found it by looking.

2026-09-17, at e1cdf67, after v0.12: 44 commits carry a `Built-By` line and git parses 40, the same four missing; every value ends `run <stamp>`.

## Idea

The gate's release check lists the commits since the previous tag whose body holds `Built-By:` and refuses when git's own trailer parser does not return it for one of them, naming the commit; and the run each names, `run <stamp>`, must be a committed record. The four released commits stay as they are and AGENTS.md says so.

## Goal

`release` refuses a version whose builds git cannot list. It reads the commits reachable from HEAD and not from the previous tag, the highest tag `v<major>.<minor>` as the rest of the release finds it, or every commit reachable from HEAD when there is no such tag. A build is a commit whose message has a line that begins `Built-By:`, and the line's value is what follows the colon, stripped; a commit may have more than one. For every value of every build, git's own trailer parser, `%(trailers:key=Built-By,valueonly)` in `git log`'s format, must return that value for the commit, or the release refuses with a problem that starts with `docs/versions/<version>.md:` and names the commit by its abbreviated hash, saying git does not read that `Built-By` as a trailer. Every value must end with a run, its last two words `run <stamp>` with the stamp one path segment, as a review's runs are, or the release refuses with a problem that starts with the note's path and names the commit, saying the `Built-By` names no run; and the run's record `runs/<stamp>` must be committed, in HEAD's tree, or the release refuses with a problem that starts with `runs/<stamp>:` and names the commit. A refusal is like the release's others: every problem printed, exit 1, no tag and nothing rendered. The commits before the previous tag are not read, so the four released build commits of v0.7 and v0.8 whose `Built-By` git does not read stay as AGENTS.md describes them; `check` is unchanged. The module docstring of `gate.py` says that `release` reads the builds since the previous tag. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
