## Changed
- gate.py

## Did
- gate.py: changed the stamp-shape test at line 879 from `STAMP_SHAPE.match(stamp)` to `STAMP_SHAPE.fullmatch(stamp)` so a value whose final word only *starts* with `\d{8}T\d{6}Z` (e.g. `20260917T000000Zx-g<hex>^{tree}`, or a stamp followed by a no-break space) is reported as naming no run instead of being looked up as a record.

## Check
- green

## Failing
- (none)

## Unsure
- (none)
