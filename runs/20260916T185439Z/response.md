## Changed
- builder.py

## Did
- builder.py: rewrote read_seed so an argument is a seed path only when it ends in .md and contains no whitespace, otherwise it is text with seed null; path args that are absolute or contain a .. component, or that git show HEAD:<path> cannot read, raise ValueError (usage error, exit 2, before any run directory).
- builder.py: read_seed now takes the note text from the checkout's commit via git show HEAD:<path> instead of the working tree.
- builder.py: added strip_comments, which removes everything between %% marks (inline or across lines) so a ## Goal inside a comment is not a heading and a comment inside the section is not the goal.
- builder.py: added fence and heading_level helpers plus goal_section, which finds the ## Goal heading outside fenced code blocks and reads from it to the next level-one or level-two heading, keeping fenced blocks whole whatever their lines start with.
- builder.py: widened the main() except around read_seed to also catch subprocess errors, since read_seed now runs git, and updated main()'s comment to describe commit-based reading.

## Check
- green

## Failing
- (none)

## Unsure
- AGENTS.md already states the attended agent runs builder.py with the seed's path (docs/seeds/<name>.md), so no change was needed there.
- No test covers %% comments inside a fenced code block; strip_comments removes them globally before fence parsing.
