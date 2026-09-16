## Changed
- builder.py

## Did
- builder.py: replaced `checkout` with `tree` throughout the module docstring (including `uv run builder.py <tree> "<goal>"` and the `diff.patch (what the run left in the tree; ...)` sentence).
- builder.py: replaced it in the `BuildReport`, `Tools` and `Sandbox` class docstrings.
- builder.py: replaced it in the `Tools.list`, `Tools.read`, `Tools.write`, `Tools.edit`, `Tools.check`, `Sandbox.image` and `Sandbox.run` method docstrings.
- builder.py: replaced it in the `git`, `head`, `dirty_paths` and `record_diff` helper docstrings.
- builder.py: left `checkout` untouched in all code (identifiers, parameters, string literals, numbers keys), all comments, and the `ROLE` text, which still reads `a goal and a checkout`.

## Check
- red

## Failing
- test_builder.MainTest.test_the_record_leaves_no_patch_when_the_run_left_nothing_and_the_text_says_so

## Unsure
- The goal and test_rename_many.py require `checkout` to be absent from builder.__doc__, but test_builder.py line 856 asserts the exact sentence "diff.patch (what the run left in the checkout; absent when it left nothing)" is present in builder.__doc__; the two cannot both hold for the module docstring, and test_builder.py is protected (write/edit return `error: protected: test_builder.py`), so `check` cannot be made green without changing what a test asserts.
