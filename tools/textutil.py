import re


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def truncate(text: str, n: int, suffix: str = "…") -> str:
    if len(text) <= n:
        return text
    return text[: n - len(suffix)] + suffix
