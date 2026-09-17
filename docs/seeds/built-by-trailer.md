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

`release` refuses a version whose builds git cannot list. It reads the commits reachable from HEAD and not from the previous tag, the highest tag `v<major>.<minor>` as the rest of the release finds it, or every commit reachable from HEAD when there is no such tag. A build is a commit whose message has a line that begins `Built-By:`, and the line's value is what follows the colon, stripped; a commit may have more than one. For every value of every build, git's own trailer parser, `%(trailers:key=Built-By,valueonly)` in `git log`'s format, must return that value for the commit, or the release refuses with a problem that starts with `docs/versions/<version>.md:` and names the commit by its abbreviated hash, saying git does not read that `Built-By` as a trailer. Every value must end with a run, its last two words `run <stamp>` with the stamp one path segment, as a review's runs are, or the release refuses with a problem that starts with the note's path and names the commit, saying the `Built-By` names no run; and the run's record `runs/<stamp>` must be committed, in HEAD's tree, or the release refuses with a problem that starts with `runs/<stamp>:` and names the commit. A refusal is like the release's others: every problem printed, exit 1, no tag and nothing rendered. The commits before the previous tag are not read, so the four released build commits of v0.7 and v0.8 whose `Built-By` git does not read stay as AGENTS.md describes them. The module docstring of `gate.py` says that `release` reads the builds since the previous tag. From the review: every value is checked for its run and its record whether git reads it or not, and one release prints every problem of every build, each once. The message is split into lines at newlines alone; a `Built-By` line is one that begins with the key as git's trailer syntax matches it, `Built-By` in any case with any spaces before the colon, and its value is what follows the colon, stripped, an empty one included; the values git reads for the commit are those `%(trailers:key=Built-By,valueonly)` gives, kept apart with a separator so that an empty one counts, and a line is read when git reads a value equal to its own that no other line of the commit has matched. An empty value is one git reads, and it names no run. The record is a directory: `runs/<stamp>` must be a tree in HEAD's tree, not a file or a link. The commits are listed as revisions whatever paths the checkout holds, and a git command that fails while the builds are read is a problem under the note's path that names the command, never an empty list of builds; output git gives in an encoding other than UTF-8 is read with what cannot be decoded replaced, never a traceback. `check` reads the same builds, those since the highest tag, and reports the same problems, under the note of the version in flight or under `docs/versions/` when none is, so a build git cannot list is seen in the version's worktree before main moves; `release` prints each problem once. The problem for a line git does not read says `as a trailer`, the one for a value says `names no run`, and a commit is named by its abbreviated hash, never its full one. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
