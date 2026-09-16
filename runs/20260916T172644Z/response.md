## Changed
- builder.py

## Did
- In builder.py, changed the list docstring and its Args path line from 'relative to the checkout root' to 'relative to the checkout's root'.
- In builder.py, changed the read docstring's path line to 'relative to the checkout's root'.
- In builder.py, changed the write docstring's path line to 'relative to the checkout's root'.
- In builder.py, changed the edit docstring's path line to 'relative to the checkout's root'.

## Check
- green

## Failing
- (none)

## Unsure
- Parallel edits to the same file appear to have interfered (one reported edited but did not stick, one reported not found), so I re-applied the read and write edits serially and confirmed the final state.
