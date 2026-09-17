## Changed
- ledger.py

## Did
- In ledger.py parse(), set sign to -1 when the line starts with '-': the sign variable was hardcoded to 1, so a debit line was treated as a credit and did not lower the balance.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
