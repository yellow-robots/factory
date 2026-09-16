# factory — Claude Code sessions

Start with `docs/factory.md`: it says what to run before reading anything else. The `docs/`
folder is an Obsidian vault the owner edits; commit their edits first (`git status --short docs/`)
and never mix docs and code in one commit. Work in a git worktree, never in this checkout. The
factory (`builder.py`) builds versions from a goal and red tests written by the attended agent;
the attended agent never writes the code the factory could build, and never edits the tests to
make a build pass. The DeepSeek key lives in `~/.config/factory/deepseek.key`; never print it.
