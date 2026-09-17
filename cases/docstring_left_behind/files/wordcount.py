"""Count the words of a text: a word is a run of characters between spaces, and a text with no
spaces is one word. `count(text)` returns the number."""


def count(text: str) -> int:
    """The number of words in `text`, split on spaces."""
    return len([word for word in text.split(" ") if word])
