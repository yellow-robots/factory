#!/usr/bin/env python3
"""The vault's reader: its notes, the templates' fields and the text of a note.

A `Note` is read once, with its frontmatter and its body or the words of the `OSError` that kept
it from being read; `Vault` holds git's listing of the vault and answers what it holds. Nothing
here writes, runs a command or checks a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import builder
import repo

BASE_LANGUAGE = {"this", "file", "formula", "true", "false", "null"}
BASE_MEMBER_ROOTS = {"this", "file", "formula"}
BASE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BASE_HEADER = re.compile(r"^(properties|order|sort|groupBy|filters|formulas|summaries):\s*(.*)$")
BASE_GROUP = re.compile(r"^(and|or|not)\s*:(.*)$")
BASE_PROPERTY = re.compile(r"property:\s*(.*)$")


@dataclass(frozen=True)
class Note:
    """One note: its path, its path relative to the root, its frontmatter, its body, and the
    words of the `OSError` when it could not be read."""

    path: Path
    rel: str
    fm: dict[str, str] | None
    body: str
    error: str = ""

    @property
    def kind(self) -> str:
        """The frontmatter's `type`, or the empty string when there is none."""
        return self.fm.get("type", "") if self.fm else ""


class Vault:
    """The vault at a root: its `docs/`, git's listing of it, and the notes read once."""

    def __init__(self, root: Path, docs: Path, listing: repo.Listing | None = None) -> None:
        """Keep the root, its `docs/` and git's listing, with no note read yet."""
        self.root = root
        self.docs = docs
        self.listing = listing
        self._notes: list[Note] | None = None

    @classmethod
    def read(cls, root: Path) -> Vault:
        """The vault at `root`, asking `repo` once what `docs/` holds."""
        root = Path(root)
        docs = root / "docs"
        return cls(root, docs, repo.listing(root, docs))

    @property
    def whole(self) -> bool:
        """Whether git answered for nobody, so the vault is read whole from the filesystem."""
        return self.listing is None

    def _rel(self, path: Path) -> str | None:
        """`path` relative to the root, POSIX, or None when it is outside the root."""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return None

    def holds(self, path: Path) -> bool:
        """Whether `path` is a note the vault holds: git lists it, or git could not answer; False
        for a path outside the root."""
        rel = self._rel(path)
        if rel is None:
            return False
        return self.whole or rel in self.listing.listed

    def part(self, path: Path) -> bool:
        """Whether `path` is part of the vault wherever a note is read by it: git lists it and no
        ignore rule matches it, or git could not answer; False for a path outside the root."""
        rel = self._rel(path)
        if rel is None:
            return False
        return self.whole or (rel in self.listing.listed and rel not in self.listing.ignored)

    def notes(self) -> list[Note]:
        """Every note of the vault, read and parsed once, in path order."""
        if self._notes is None:
            templates = self.docs / "templates"
            self._notes = [
                _note(self.root, path)
                for path in sorted(self.docs.rglob("*.md"))
                if templates not in path.parents and self.holds(path)
            ]
        return self._notes

    def resolves(self, target: str) -> bool:
        """Whether `target` names a note in `docs/` git holds, by path or by name, or a `.base`
        file; a path git is told to ignore names nothing, tracked or not."""
        target = target.strip()
        if not target:
            return False
        direct = self.docs / target
        if direct.is_file() and self.part(direct):
            return True
        if direct.suffix == "":
            named = self.docs / (target + ".md")
            if named.is_file() and self.part(named):
                return True
        name = target.rsplit("/", 1)[-1]
        stem = name[:-3] if name.endswith(".md") else name
        for found in self.docs.rglob("*"):
            if found.is_file() and self.part(found) and (found.name == name or found.stem == stem):
                return True
        return False


def _note(root: Path, path: Path) -> Note:
    """The note at `path`: read once, its frontmatter and body, or the read error and nothing."""
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return Note(path, rel, None, "", str(e))
    fm, body = frontmatter(text)
    return Note(path, rel, fm, body, "")


def frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    """The `key: value` block between the leading `---` lines, and the body after it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fields: dict[str, str] = {}
            for line in lines[1:i]:
                key, sep, value = line.partition(":")
                if sep:
                    fields[key.strip()] = value.strip()
            return fields, "\n".join(lines[i + 1 :])
    return None, text


def title(body: str) -> str:
    """The body's first level-one heading, or the empty string when it has none."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def first_paragraph(body: str) -> str:
    """The body's first paragraph under its title, the embeds and the bullets passed over."""
    lines = body.splitlines()
    started = False
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not started:
            if stripped.startswith("# "):
                started = True
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("![[") or stripped.startswith("- "):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def changelog_bullets(body: str) -> list[str]:
    """The bullet lines under the body's `## Changelog`, the wikilinks among them excepted."""
    bullets: list[str] = []
    inside = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            inside = stripped == "## Changelog"
            continue
        if inside and stripped.startswith("- ") and not stripped.startswith("- [["):
            bullets.append(stripped)
    return bullets


def _fence_walk(text: str):
    """Walk `text`'s lines, yielding each with whether it lies inside a fenced code block."""
    fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        if fence is not None:
            yield line, True
            if builder.closing_fence(line, fence):
                fence = None
            continue
        opened = builder.opening_fence(line)
        if opened is not None:
            yield line, True
            fence = opened
            continue
        yield line, False


def review_findings(text: str) -> list[tuple[str, str]]:
    """The review's findings: each level-three heading of the body with its section's text, a
    fenced code block belonging whole."""
    findings: list[list] = []
    current: list | None = None
    for line, fenced in _fence_walk(text):
        if fenced:
            if current is not None:
                current[1].append(line)
            continue
        level, heading_title = builder.heading(line)
        if level == 3:
            current = [heading_title, []]
            findings.append(current)
        elif level in (1, 2):  # the next section of the note ends the finding
            current = None
        elif current is not None:
            current[1].append(line)
    return [(heading_title, "\n".join(section)) for heading_title, section in findings]


def prose_lines(section: str) -> list[str]:
    """A finding section's prose lines: a fenced code block and an indented code block belong
    whole and are no line of the prose."""
    return [
        line
        for line, fenced in _fence_walk(section)
        if not fenced and not line.startswith(("    ", "\t"))
    ]


@dataclass(frozen=True)
class Template:
    """A template's frontmatter fields and why they could not be read, `""` when they were."""

    fields: dict[str, str] | None
    error: str


def template(docs: Path, kind: str) -> Template:
    """The fields of `docs/templates/<kind>.md`, or `cannot be read` or `no frontmatter`."""
    path = docs / "templates" / f"{kind}.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Template(None, "cannot be read")
    fm, _ = frontmatter(text)
    if fm is None:
        return Template(None, "no frontmatter")
    return Template(fm, "")


def template_fields(docs: Path, kind: str) -> set[str] | None:
    """The field names of `docs/templates/<kind>.md`'s frontmatter, or None when it cannot be
    read."""
    found = template(docs, kind)
    return set(found.fields) if found.fields is not None else None


def text_of(path: Path) -> str | None:
    """The whole text of `path`, or None when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _unquoted(text: str) -> str:
    """An expression with one layer of Obsidian's YAML quotes, around it, removed."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        quote, text = text[0], text[1:-1]
        if quote == '"':
            text = text.replace('\\"', '"').replace("\\\\", "\\")
        else:
            text = text.replace("''", "'")
    return text


def _dot_root(text: str, dot: int) -> str:
    """The identifier immediately before the `.` at `dot`, if there is one."""
    i = dot - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    end = i + 1
    while i >= 0 and (text[i].isalnum() or text[i] == "_"):
        i -= 1
    return text[i + 1 : end]


def expression_names(expression: str) -> list[str]:
    """The bare identifiers an Obsidian expression names: quoted strings, regex literals,
    `#` comments, members of `file.`/`formula.`/`this.`, functions (`name(`), and the language
    names `this`, `file`, `formula`, `true`, `false` and `null` removed. A `note.` prefix is a
    property's, so the name after it is checked."""
    text = _unquoted(expression)
    text = re.sub(r'"[^"]*"', " ", text)
    text = re.sub(r"'[^']*'", " ", text)
    text = re.sub(r"#[^\n]*", " ", text)
    text = re.sub(r"/[^/\n]*/", " ", text)
    names: list[str] = []
    for match in BASE_IDENT.finditer(text):
        name = match.group()
        after = text[match.end() :].lstrip()
        if after.startswith("("):
            continue
        if match.start() and text[match.start() - 1] == ".":
            if _dot_root(text, match.start() - 1) != "note":
                continue
            names.append(name)
            continue
        if name in BASE_LANGUAGE:
            continue
        if after.startswith("."):
            continue
        names.append(name)
    return names


def plain_names(name: str) -> list[str]:
    """A property named under `properties:`, `order:`, `property:` or `summaries:`, where a
    hyphen is part of the name; a `file.`, `formula.` or `this.` prefix is never reported, while
    the name after a `note.` prefix is checked."""
    name = _unquoted(name).strip()
    if not name:
        return []
    root, _, rest = name.partition(".")
    if root in BASE_MEMBER_ROOTS:
        return []
    if root == "note" and rest:
        return [rest]
    return [name]


def base_named(text: str) -> list[tuple[str, str]]:
    """Every property `text` names, tagged as a plain name or an expression: keys under
    `properties:` and `summaries:`, entries of `order:`, the `property:` of a `sort` or
    `groupBy`, and filter and formula expressions. A nested `and:`/`or:`/`not:` group names no
    property; its items, or its inline expression, do."""
    named: list[tuple[str, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        i += 1
        if not stripped or stripped.startswith("#"):
            continue
        header = BASE_HEADER.match(stripped)
        if not header:
            continue
        key, rest = header.group(1), header.group(2).strip()
        if key == "order" and rest.startswith("["):
            for entry in rest.strip("[]").split(","):
                named.append(("name", entry.strip()))
            continue
        block: list[tuple[int, str]] = []
        while i < len(lines):
            line = lines[i]
            content = line.strip()
            if content and not content.startswith("#"):
                if len(line) - len(line.lstrip()) <= indent:
                    break
                block.append((len(line) - len(line.lstrip()), content))
            i += 1
        if key in ("properties", "summaries"):
            child = min((depth for depth, _ in block), default=indent)
            for depth, content in block:
                if depth == child and ":" in content and not content.startswith("-"):
                    named.append(("name", content.split(":", 1)[0].strip()))
        elif key == "order":
            for _, content in block:
                if content.startswith("- "):
                    named.append(("name", content[2:].strip()))
        elif key in ("sort", "groupBy"):
            for _, content in block:
                match = BASE_PROPERTY.search(content)
                if match:
                    named.append(("name", match.group(1).strip()))
        else:
            if rest:
                named.append(("expr", rest))
            for _, content in block:
                if content.startswith("- "):
                    item = content[2:].strip()
                    group = BASE_GROUP.match(item)
                    if group is None:
                        named.append(("expr", item))
                    elif group.group(2).strip():
                        named.append(("expr", group.group(2).strip()))
                elif ":" in content:
                    value = content.split(":", 1)[1].strip()
                    if value:
                        named.append(("expr", value))
    return named
