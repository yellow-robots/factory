import re


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def truncate(text: str, n: int, suffix: str = "…") -> str:
    if len(text) <= n:
        return text
    return text[: n - len(suffix)] + suffix


def _parse_value(raw: str):
    """Parse one frontmatter scalar/list value from the text after `key:`."""
    if raw == "":
        return ""
    if raw.startswith('"'):                       # double-quoted: keep contents verbatim (incl. '#')
        end = raw.find('"', 1)
        return raw[1:end] if end != -1 else raw[1:]
    if raw.startswith("["):                       # inline list [a, b, c]
        end = raw.find("]")
        if end != -1:
            inner = raw[1:end].strip()
            return [] if inner == "" else [item.strip() for item in inner.split(",")]
    hash_idx = raw.find(" #")                      # unquoted scalar: drop a trailing ' # comment'
    if hash_idx != -1:
        raw = raw[:hash_idx].rstrip()
    return raw


def split_frontmatter(text: str):
    """Split leading YAML-ish frontmatter from a markdown document → (meta, body).

    `meta` maps each frontmatter key to its value — a string, or a list for inline
    `[a, b]` syntax. Parses only the small subset our templates use (no external
    YAML dependency): `key: value` lines, double-quoted values, inline lists, and a
    trailing ` # comment` on unquoted values. Obsidian auto-adds `created`/`updated`
    keys — those are preserved like any other (we never reject unknown keys). Text
    that does not open with a `---` line and close with another `---` is treated as
    having no frontmatter, and returned unchanged as the body.
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
    for line in lines[1:close]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        meta[key.strip()] = _parse_value(raw.strip())
    return meta, "\n".join(lines[close + 1:])
