## Changed
- builder.py

## Did
- In builder.py, changed the list docstring's summary line to say 'relative to the checkout's root'.
- In builder.py, changed the list method's `path` arg docstring to say 'relative to the checkout's root'.
- In builder.py, changed the read method's `path` arg docstring to say 'relative to the checkout's root'.
- In builder.py, changed the write method's `path` arg docstring to say 'relative to the checkout's root'.
- In builder.py, changed the edit method's `path` arg docstring to say 'relative to the checkout's root'.

## Check
- green

## Failing
- (none)

## Unsure
- The search tool's docstring (builder.py line 278) still says 'relative to the checkout root', but the goal names only the four tools list, read, write and edit, and the test only asserts on those four, so it was left unchanged.
