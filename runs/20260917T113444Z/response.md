## Changed
- ledger.py

## Did
- In ledger.py, parse() detected a leading '-' but never set the sign to -1, so debits were added instead of subtracted; I set sign = -1 when the first character is '-' so balance(["+5","-3"]) is 2.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
