## Changed
- builder.py

## Did
- builder.py: in note_text, a line indented four spaces or more (or by a tab) is now kept whole as an indented code block, so `%%` on it is text and not a comment mark.
- builder.py: goal_section now trims only blank lines from both ends of the section instead of str.strip(), so the section's first line keeps its indentation and an indented `## Changelog` is not a heading.
- builder.py: read_seed now wraps both committed_file and `git show HEAD:<path>` in one GitError handler, so a git failure (a checkout without a commit, or `:!f.md` pathspec magic) becomes a ValueError/usage error instead of a traceback.
- builder.py: read_seed's docstring now names every refusal (outside path, entry that is no file such as a symbolic link or directory, missing note, missing or empty Goal, and a `%%` comment left open), satisfying the docstring assertions.

## Check
- green

## Failing
- (none)

## Unsure
- AGENTS.md already states the next seeds' builds run with the seed's path (lines about `docs/seeds/<name>.md`), so no change was made there; I verified only that the test suite is green, not the gate's content checks beyond it.
