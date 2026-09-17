## Changed
- ledger.py

## Did
- In ledger.py, set sign = -1 when a line starts with '-', so a debit parses as negative instead of having its sign stripped and ignored (previously sign stayed 1, making balance(['+5','-3']) = 8 rather than 2).

## Check
- green

## Failing
- (none)

## Unsure
- Whether 'symptom_not_root' implies a deeper root cause elsewhere, but the full suite (160 tests) passes and no other code touches ledger's sign handling.
