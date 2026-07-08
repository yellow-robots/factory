import re


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def truncate(text: str, n: int, suffix: str = "…") -> str:
    if len(text) <= n:
        return text
    return text[: n - len(suffix)] + suffix


def _unquote(item: str):
    """Strip a wrapping pair of double quotes from one scalar/list-item token, verbatim inside."""
    if item.startswith('"'):
        end = item.find('"', 1)
        return item[1:end] if end != -1 else item[1:]
    return item


def _parse_value(raw: str):
    """Parse one frontmatter scalar/list value from the text after `key:`."""
    if raw == "":
        return ""
    if raw.startswith('"'):                       # double-quoted: keep contents verbatim (incl. '#')
        return _unquote(raw)
    if raw.startswith("["):                       # inline list [a, b, c]
        end = raw.find("]")
        if end != -1:
            inner = raw[1:end].strip()
            return [] if inner == "" else [_unquote(item.strip()) for item in inner.split(",")]
    hash_idx = raw.find(" #")                      # unquoted scalar: drop a trailing ' # comment'
    if hash_idx != -1:
        raw = raw[:hash_idx].rstrip()
    return raw


def split_frontmatter(text: str):
    """Split leading YAML-ish frontmatter from a markdown document → (meta, body).

    `meta` maps each frontmatter key to its value — a string, or a list for inline
    `[a, b]` syntax or a block style (a bare `key:` line followed by indented `- item`
    lines — the form Obsidian's property editor writes for a non-empty list). Parses
    only the small subset our templates use (no external YAML dependency): `key: value`
    lines, double-quoted values (list items too), inline/block lists, and a trailing
    ` # comment` on unquoted values. Obsidian auto-adds `created`/`updated` keys — those
    are preserved like any other (we never reject unknown keys). Text that does not open
    with a `---` line and close with another `---` is treated as having no frontmatter,
    and returned unchanged as the body.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.split("\n")
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:                             # no closing fence → not frontmatter
        return {}, text
    meta = {}
    i = 1
    while i < close:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            i += 1
            continue
        key, _, raw = line.partition(":")
        raw = raw.strip()
        if raw == "":                              # maybe a block-style list follows
            items = []
            j = i + 1
            while j < close:
                item_line = lines[j]
                item_stripped = item_line.strip()
                if item_line[:1] in (" ", "\t") and (item_stripped == "-" or item_stripped.startswith("- ")):
                    items.append(_unquote(item_stripped[1:].strip()))
                    j += 1
                else:
                    break
            if items:
                meta[key.strip()] = items
                i = j
                continue
        meta[key.strip()] = _parse_value(raw)
        i += 1
    return meta, "\n".join(lines[close + 1:])
