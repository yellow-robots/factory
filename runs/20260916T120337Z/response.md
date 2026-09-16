## Changed
- builder.py

## Did
- builder.py: added `world_head(world)` returning the world's `git rev-parse --verify -q HEAD` commit, or null when the world is not a git checkout or has no commit, using the existing read-only `git` helper
- builder.py: added `dirty_paths(world)` parsing `git status --porcelain -z --untracked-files=all` into the changed paths, skipping the extra NUL field of renames
- builder.py: main now refuses a git world with any dirty paths via `usage_error`, naming the first five paths, before the run directory is created or the key is read
- builder.py: main records `world_head` in `numbers.json` from the head captured at start, without evaluating git for a plain directory (null)

## Check
- green

## Failing
- (none)

## Unsure
- Whether git status --porcelain -z ordering guarantees f.py before stray.txt, though both are named and included among the first five paths regardless
