## Changed
- builder.py

## Did
- builder.py: the module docstring now lists `diff.patch (what the run left in the checkout; absent when it left nothing)`, as the test pins.
- builder.py: the comment above HIDDEN no longer says "planning" ("running and installing the program leave behind").
- builder.py: build_agent's docstring says "the five tools" instead of "the five functions of the tools".
- builder.py: git's docstring says "not one of the tools" instead of "Not a function of the tools".
- builder.py: record_diff's docstring says the patch is "absent when the run left nothing", since the code writes diff.patch only when the patch is non-empty.
- builder.py: record_diff joins the diff parts into `patch` once and writes that binding, instead of joining twice.
- builder.py: main refuses a directory whose `.git` is not git's (or missing) as `not a git checkout` by checking `git rev-parse --git-dir`, while a git checkout with no commit is still refused as `the checkout has no commit`; both exit 2 before any run directory.

## Check
- green

## Failing
- (none)

## Unsure
- A parallel batch of edits to builder.py partially applied and briefly left a stray `argv))` line and an out-of-sync line count; I re-applied each edit sequentially, confirmed the file ends cleanly at `sys.exit(main(sys.argv))`, and the suite passes.
- The documents (README.md, AGENTS.md, seeds, template) are described as the attended agent's work after the build; they appear already updated to checkout/tools, but I did not verify every seed note. docs/seeds/world-pinned-to-commit.md (a done v0.4 seed) still uses `world`/`world_head`, and I left it as-is since the documents are not the builder's to change.
