## Changed
- builder.py

## Did
- Changed the list docstring in builder.py (summary line and Args) from "relative to the checkout root" to "relative to the checkout's root".
- Changed the read docstring's path arg in builder.py to "relative to the checkout's root".
- Changed the write docstring's path arg in builder.py to "relative to the checkout's root".
- Changed the edit docstring's path arg in builder.py to "relative to the checkout's root", making the four tested tools uniformly use the possessive form.

## Check
- green

## Failing
- (none)

## Unsure
- The search tool's docstring (builder.py) still says "relative to the checkout root"; it is not one of the four tools the goal names and the test does not check it, so I left it unchanged.
