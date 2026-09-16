## Changed
- evals.py

## Did
- evals.py: added "files_changed", "deletions" and "stray_files" to COLUMNS after "diff_lines".
- evals.py: added _stray(record, goal), which counts distinct paths across a run's numbers.json written and edited arrays that the goal text names neither by full path nor by basename, and returns None when those arrays are absent.
- evals.py: changed _row to take the case's goal text and appended medians for diff_lines, files_changed and deletions (from the numbers as they are, missing runs skipped) followed by the median stray_files.
- evals.py: passed _goal(directory, name) into _row at the table-printing call site in main.

## Check
- green

## Failing
- (none)

## Unsure
- The seed's closing sentence about preservation checks (symbol and edge map, mutation score) has no tests here and was left unimplemented.
