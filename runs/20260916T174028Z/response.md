## Changed
- builder.py

## Did
- builder.py: renamed `checkout` to `tree` throughout the module docstring, including the `uv run builder.py <tree> "<goal>"` usage line and the `diff.patch (what the run left in the tree; absent when it left nothing)` sentence.
- builder.py: renamed `checkout` to `tree` in the class docstrings of BuildReport, Tools and Sandbox.
- builder.py: renamed `checkout` to `tree` in the method docstrings Tools.list, Tools.read, Tools.write, Tools.edit, Tools.check, Sandbox.image and Sandbox.run.
- builder.py: renamed `checkout` to `tree` in the git-helper docstrings git, head, dirty_paths and record_diff.
- builder.py: left `checkout` untouched in every comment, in the code (e.g. `outside the checkout`, the `checkout` numbers key) and in ROLE, as the goal requires.
- test_builder.py: attempted to update the sentence pinned at line 856 to `tree`, but the tool refused the path as protected, so no test was changed.

## Check
- red

## Failing
- test_builder.MainTest.test_the_record_leaves_no_patch_when_the_run_left_nothing_and_the_text_says_so

## Unsure
- The suite cannot go green as shipped: test_builder.py:856 asserts `'diff.patch (what the run left in the checkout; absent when it left nothing)' in builder.__doc__`, while test_rename_many asserts `'checkout' not in builder.__doc__`; a normal str cannot satisfy both, and my edit tool refuses `test*.py` as protected, so the only way to green would be to weaken a test.
- Whether BuildReport's class docstring is inside the goal's 'the classes'' scope: I changed it because the goal names class docstrings, but the added test does not check it (no test now covers it either way).
- Whether the intended resolution is for the attended agent (who may edit tests) to update test_builder.py:856 to the renamed wording; the builder's walls forbid it.
