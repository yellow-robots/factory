## Changed
- gate.py

## Did
- gate.py: added BASE_LANGUAGE, BASE_IDENT, BASE_HEADER and BASE_PROPERTY constants for reading docs/backlog.base
- gate.py: added _unquoted, _expression_names and _base_named helpers that collect properties named as properties: keys, order: entries, sort/groupBy property:, and filter/formula expressions, dropping quoted strings, members (`.name`), functions (`name(`) and the language words this/file/formula/true/false/null
- gate.py: added _base_problems that reports each distinct named property absent from docs/templates/seed.md frontmatter as `docs/backlog.base: <property> is not a field of docs/templates/seed.md`
- gate.py: called _base_problems(docs) at the end of problems_check so check reports these problems

## Check
- green

## Failing
- (none)

## Unsure
- Whether Obsidian ever writes filters/formulas in shapes not covered by the line-based reader (e.g. folded multi-line scalars); the provided test and the repository's own docs/backlog.base only exercise block mappings, block sequences and single-line expressions
