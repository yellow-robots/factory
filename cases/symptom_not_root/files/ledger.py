"""A ledger of signed amounts, one per line: `+5`, `-3`, `12`, a bare number being a credit.
`parse(line)` gives one line's amount as an int, `balance(lines)` their sum."""


def parse(line: str) -> int:
    """The amount of one line: an optional sign, then digits."""
    text = line.strip()
    sign = 1
    if text[:1] in "+-":
        text = text[1:]
    return sign * int(text)


def balance(lines) -> int:
    """The sum of the lines' amounts."""
    return sum(parse(line) for line in lines)
