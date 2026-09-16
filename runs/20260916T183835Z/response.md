## Changed
- builder.py

## Did
- builder.py: replaced `checkout` with `tree` in Tools.__doc__ and the docstrings of Tools.list, read, _files, search, write, edit and check.
- builder.py: replaced `checkout` with `tree` in Sandbox.__doc__ and the docstrings of Sandbox.image and Sandbox.run.
- builder.py: replaced `checkout` with `tree` in the git-helper docstrings of git, head, dirty_paths and record_diff.
- Left `checkout` untouched in the module docstring, the ROLE text, code identifiers/comments and non-git-helper function docstrings (e.g. read_seed), as the goal specifies.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
