## Changed
- builder.py

## Did
- builder.py: removed ` Factory v0.3.` from the module docstring and changed `reachable only through five functions` to `reachable only through five tools`, satisfying the review and the docstring test.
- builder.py: added `GIT_ENV_UNSET` and `git_env()` and passed `env=git_env()` to the read-only `git()` subprocess, so git runs without the environment's own `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES`.
- builder.py: replaced the `.git`-exists / `--git-dir` guard in `main` with a `git rev-parse --show-toplevel` check that must name the checkout, refusing a subdirectory of a repository, a stray `.git` file or directory, and an environment-pointed directory as `not a git checkout`, while accepting a worktree whose `.git` is a file.
- builder.py: wrapped that guard in `except FileNotFoundError` and `except (OSError, subprocess.SubprocessError)` so a git that cannot run is a usage error naming git (never a traceback), and wrote a comment above the guard explaining both its halves.

## Check
- green

## Failing
- (none)

## Unsure
- The goal mentions README.md, AGENTS.md, the seed template and the seeds as document changes that follow after the build by the attended agent; I left those untouched as builder.py and the tests are the build's scope.
- The toplevel guard compares `Path(top).resolve()` to the already-resolved checkout; the test's symlink-free temp paths pass, but an exotic symlink layout was not separately exercised.
