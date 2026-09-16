## Changed
- builder.py

## Did
- builder.py: added a lone-long-match is cut sentence (and the newline restriction in args) to Tools.search's docstring so `cut` and the caps are stated there.
- builder.py: refused a pattern containing a newline (or carriage return) in Tools.search with an error like the empty pattern.
- builder.py: gave Tools._files an `unlistable` counter that appends 1 when a directory cannot be listed, propagating through recursion.
- builder.py: added `skipped += len(unlistable)` in Tools.search so an unlistable directory counts once in `...	<n> files not searched`.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
