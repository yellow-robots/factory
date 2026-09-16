## Changed
- runs.py

## Did
- runs.py: read numbers.json as utf-8-sig so a leading byte order mark no longer hides the numbers.
- runs.py: added _field to render each cell as one field, keeping strings as-is but replacing tab/newline with a space and printing non-strings (true, [1, 2], {"x": 1}) as json.dumps does.
- runs.py: rewrote _cell to treat a JSON null as an empty cell and to fall back from a null head to world_head.
- runs.py: applied _field to the stamp (record name) and goal cells so a tab or newline in a name becomes a space.

## Check
- green

## Failing
- (none)

## Unsure
- runs.py already existed with most of the table implemented; I changed only the cells the review named and did not re-verify untested details such as a byte order mark in goal.txt.
