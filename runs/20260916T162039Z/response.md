## Changed
- gate.py

## Did
- gate.py: split identifier handling, adding BASE_MEMBER_ROOTS, a hyphen-free BASE_IDENT, BASE_GROUP for and/or/not, and summaries in BASE_HEADER.
- gate.py: rewrote _expression_names to drop regex literals and # comments, treat name( as a function, skip language names and file./formula./this. members, and check the name after a note. prefix.
- gate.py: added _dot_root and _plain_names so properties/order/property:/summaries names keep hyphens and file./formula./this. names are not reported.
- gate.py: rewrote _base_named to tag names as plain or expression, so a nested and:/or:/not: group names no property while its items or inline expression do.
- gate.py: changed _base_problems to report nothing when the seed template is missing or has no frontmatter, and to dispatch plain names vs expressions.

## Check
- green

## Failing
- (none)

## Unsure
- Whether a dotted plain name with an unknown root (other than file./formula./this./note.) should be checked whole or after the dot; only the tested prefixes are exercised.
