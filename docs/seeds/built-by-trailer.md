---
created: 2026-09-17
type: seed
status: open
summary: A build commit whose `Built-By` line git does not parse as a trailer is a build the version's derived list misses; the gate should refuse it at release.
value: 3
effort: S
version:
---

## Evidence

2026-09-17: of the 32 commits carrying a `Built-By` line, git parses 27. Four released in v0.7 and v0.8, cea0753, 5f7349f, 92191cc and 2a13022, and the first commit of v0.9 before it was amended, wrote a blank line between the trailers, so the trailer block git reads is the last paragraph alone and `git log --format='%(trailers:key=Built-By,valueonly)'`, the command AGENTS.md gives for the builds of a version, prints nothing for them. Nothing checked it; the attended agent found it by looking.

## Idea

The gate's release check lists the commits since the previous tag whose body holds `Built-By:` and refuses when git's own trailer parser does not return it for one of them, naming the commit; and the run each names, `run <stamp>`, must be a committed record. The four released commits stay as they are and AGENTS.md says so.
