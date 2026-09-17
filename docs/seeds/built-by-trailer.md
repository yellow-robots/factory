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

`check` and `release` refuse builds git cannot list, reading them from git alone.

The builds read are the commits reachable from HEAD and not from the highest tag `v<major>.<minor>`, or every commit reachable from HEAD when there is no such tag, listed, and each of them read, with the revisions ended by `--` whatever paths the checkout holds. Everything git prints for them is read as bytes, git asked for UTF-8 and for no signature whatever the repository's settings say, and decoded as UTF-8 with what cannot be decoded replaced, never as text that turns a carriage return into a newline; nothing of it raises.

A `Built-By` line is a line of a commit's message, the message split at `\n` alone, that begins with the letters `Built-By` in ASCII of any case, then any spaces or tabs, then a colon; its value is what follows that colon. A build is a commit with at least one `Built-By` line. What git reads for the commit are the entries of `git log -1 --format=%(trailers:key=Built-By,unfold,separator=%x00)`: its output without the one newline the format ends with, split at NUL, each entry `<key>: <value>` and never empty, so no output is no entry and an empty value is an entry; an entry's value is what follows its first colon. Every value, of a line or of an entry, is stripped of ASCII whitespace alone.

For each build every problem is reported, each once. When git reads fewer entries than the commit has `Built-By` lines, a problem under the note's path says how many of its `Built-By` lines git does not read `as a trailer`. Every value, of every line and of every entry, must end with the words `run <stamp>`, the value split at ASCII whitespace and the stamp in the shape the builder names every record with, eight digits, `T`, six digits and `Z`, or a problem under the note's path quotes the value and says it `names no run`. Every stamp so named must be a tree `runs/<stamp>` in HEAD's tree, a directory and not a file, a link or a submodule, or a problem under `runs/<stamp>:` says the run has no committed record, once for the commit however many of its values name the stamp.

A problem names its commit by git's unique abbreviation of the hash, at least seven characters whatever `core.abbrev` says, or by the hash's first seven characters when git cannot abbreviate it, never the full hash, and quotes a value with its control characters escaped and nothing else changed. A git command that fails while the builds are listed or read, the abbreviation apart, is a problem under the note's path naming the command and the commit it was reading, never an empty list of builds.

The note's path is that of the version in flight, the one version note that is not a tag, or `docs/versions/` when none is or more than one is. `check` reports these problems, so a build git cannot list is seen in the version's worktree, where it can still be amended, before main moves; `release` runs `check` first and stops on its problems, and does not read the builds again. A refusal is like the release's others: every problem printed, exit 1, no tag and nothing rendered. The commits before the highest tag are not read, so the four released build commits of v0.7 and v0.8 whose `Built-By` git does not read stay as AGENTS.md describes them. The module docstring of `gate.py` says that `check` and `release` read the builds since the highest tag. The tests in `test_gate.py` whose docstring names this seed define the behaviour.
