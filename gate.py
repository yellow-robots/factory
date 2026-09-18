#!/usr/bin/env python3
"""The gate: a deterministic check of the vault, its changelog and its tags.

    uv run gate.py check
    uv run gate.py render
    uv run gate.py release <version>

`check` validates `docs/` and the repository against it, `render` writes `CHANGELOG.md` from
the tags, and `release` refuses until everything derived agrees, then tags and renders. `check`
and `release` read the builds since the highest tag, every commit whose message carries a
`Built-By` line, and refuse when git's trailer parser does not read one or its value does not
name a run; the record the stamp names is the factory's, kept in its store outside the project,
so no stamp is looked up in the project. Each command prints one line per problem on stdout, starting with
the path relative to the root, and exits 1 if there is any; with nothing to report it prints
nothing and exits 0. Usage errors go to stderr and exit 2.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import builder

USAGE = "usage: gate.py check|render|release <version>"
STATUSES = ("open", "spec", "building", "done", "rejected")
SEED_FIELDS = {"type", "status", "summary", "value", "effort", "version", "created"}
REVIEW_FIELDS = {"type", "created", "runs", "reviewer"}
SEVERITIES = ("defect", "smell")
VERIFIEDS = ("yes", "no")
EFFORTS = {"S", "M", "L"}
BASE_LANGUAGE = {"this", "file", "formula", "true", "false", "null"}
BASE_MEMBER_ROOTS = {"this", "file", "formula"}
BASE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BASE_HEADER = re.compile(
    r"^(properties|order|sort|groupBy|filters|formulas|summaries):\s*(.*)$"
)
BASE_GROUP = re.compile(r"^(and|or|not)\s*:(.*)$")
BASE_PROPERTY = re.compile(r"property:\s*(.*)$")
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_NAME = re.compile(r"^v(\d+)\.(\d+)\.md$")
VERSION = re.compile(r"^v(\d+)\.(\d+)$")
WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
BUILT_BY = re.compile(r"^Built-By[ \t]*:", re.IGNORECASE | re.ASCII)
ASCII_WHITESPACE = " \t\n\r\x0b\x0c"
ASCII_RUN = re.compile(r"[^ \t\n\r\x0b\x0c]+")
# The builder names a record with a UTC stamp, and, when a second run shares its second, the
# stamp and a dash and that run's number: the shape the gate reads for a run is that one, digits
# in ASCII alone, so a dash with nothing after it, with something that is not a number or with a
# second dash names no run.
STAMP_SHAPE = re.compile(r"\d{8}T\d{6}Z(-\d+)?", re.ASCII)
# The build reads ask git for UTF-8 and for no signature whatever the repository's display
# settings say, so a message in another log encoding is not a build git cannot read and a
# signature is never counted as a trailer.
GIT_READ = ("-c", "i18n.logOutputEncoding=UTF-8", "-c", "log.showSignature=false")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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
            return fields, "\n".join(lines[i + 1:])
    return None, text


def _notes(docs: Path, root: Path, vault: set[str] | None) -> list[Path]:
    """Every `.md` under `docs/` that git does not ignore, the templates excepted."""
    templates = docs / "templates"
    return [
        p
        for p in sorted(docs.rglob("*.md"))
        if templates not in p.parents and _in_vault(p, root, vault)
    ]


def _git_out(root: Path, *args: str) -> tuple[int, str]:
    """git's exit status and stdout: status 1 and no output when git cannot run, and output in an
    encoding other than UTF-8 read with what cannot be decoded replaced, never a traceback."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, errors="replace"
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def _git(root: Path, *args: str) -> str:
    return _git_out(root, *args)[1]


def _git_bytes(root: Path, *args: str) -> tuple[int, bytes]:
    """git's exit status and stdout as bytes, status 1 and no output when git cannot run. Nothing
    git prints is turned into text before it is decoded, so a carriage return stays a carriage
    return."""
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return 1, b""
    return done.returncode, done.stdout


def _utf8(data: bytes) -> str:
    """The bytes decoded as UTF-8 with what cannot be decoded replaced; never raises."""
    return data.decode("utf-8", "replace")


def _vault_paths(root: Path) -> set[str] | None:
    """The paths under `root` git does not ignore, relative to `root`, or `None` when git cannot
    answer (a directory that is no checkout, or a git that fails), so the vault is then read whole
    from the filesystem. `git ls-files` lists what is tracked and what is untracked and not
    ignored in one call; nothing is read from `.gitignore`."""
    code, out = _git_bytes(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if code != 0:
        return None
    return {path for path in _utf8(out).split("\0") if path}


def _in_vault(path: Path, root: Path, vault: set[str] | None) -> bool:
    """Whether `path` is part of the vault: git does not ignore it, or git could not answer."""
    if vault is None:
        return True
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return True
    return rel in vault


def _line_text(value: str) -> str:
    """A value with its control characters escaped, so a problem that quotes it stays one line and
    nothing but a control character changes."""
    out: list[str] = []
    for ch in value:
        if ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return "".join(out)


def _ascii_words(value: str) -> list[str]:
    """The value split at ASCII whitespace alone, so a no-break space stays part of a word."""
    return ASCII_RUN.findall(value)


def _tags(root: Path) -> set[str]:
    return {line.strip() for line in _git(root, "tag", "-l").splitlines() if line.strip()}


def _highest_tag(tags: set[str]) -> str | None:
    best, best_key = None, None
    for tag in tags:
        match = VERSION.match(tag)
        if not match:
            continue
        key = (int(match.group(1)), int(match.group(2)))
        if best_key is None or key > best_key:
            best, best_key = tag, key
    return best


def _resolve(target: str, docs: Path, root: Path, vault: set[str] | None) -> bool:
    """A note in `docs/` that git does not ignore, by path or by name, or a `.base` file."""
    target = target.strip()
    if not target:
        return False
    direct = docs / target
    if direct.is_file() and _in_vault(direct, root, vault):
        return True
    if direct.suffix == "":
        named = docs / (target + ".md")
        if named.is_file() and _in_vault(named, root, vault):
            return True
    name = target.rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".md") else name
    for found in docs.rglob("*"):
        if found.is_file() and _in_vault(found, root, vault) and (
            found.name == name or found.stem == stem
        ):
            return True
    return False


def _goal_problems(rel: str, body: str) -> list[str]:
    """The seed's `## Goal` as `builder.read_seed` reads it: the builder's `note_text` and
    `goal_section`, so the gate refuses exactly the notes the builder would. A `%%` comment left
    open is its own problem; a note with no heading outside a fence or a comment, or no text under
    it once the comments are out, has no Goal with text."""
    try:
        text = builder.note_text(body)
    except ValueError:
        return [f"{rel}: seed has a %% comment left open"]
    if not builder.goal_section(text):
        return [f"{rel}: seed has no ## Goal with text"]
    return []


def _test_docstrings(root: Path) -> list[str]:
    """The docstrings of every test method or class in a `test*.py` at the root."""
    found: list[str] = []
    for path in sorted(root.glob("test*.py")):
        if not path.is_file():
            continue
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test")
            ):
                doc = ast.get_docstring(node)
                if doc:
                    found.append(doc)
    return found


def _test_names(root: Path) -> set[str]:
    """The name of every test method or class in a `test*.py` at the root."""
    names: set[str] = set()
    for path in sorted(root.glob("test*.py")):
        if not path.is_file():
            continue
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test")
            ):
                names.add(node.name)
    return names


def _named_by_a_test(root: Path, stem: str, docstrings: list[str]) -> bool:
    pattern = re.compile(rf"seed:\s*{re.escape(stem)}(?![\w-])")
    return any(pattern.search(doc) for doc in docstrings)


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
    return text[i + 1:end]


def _expression_names(expression: str) -> list[str]:
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
        after = text[match.end():].lstrip()
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


def _plain_names(name: str) -> list[str]:
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


def _base_named(text: str) -> list[tuple[str, str]]:
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


def _base_problems(docs: Path, root: Path, vault: set[str] | None) -> list[str]:
    """The properties `docs/backlog.base` names that are not seed template fields."""
    base = docs / "backlog.base"
    if not base.is_file() or not _in_vault(base, root, vault):
        return []
    fields_, _ = frontmatter(_read(docs / "templates" / "seed.md"))
    if fields_ is None:
        # The missing template is reported once, elsewhere.
        return []
    fields = set(fields_)
    problems: list[str] = []
    seen: set[str] = set()
    for kind, name in _base_named(_read(base)):
        identifiers = _plain_names(name) if kind == "name" else _expression_names(name)
        for identifier in identifiers:
            if identifier in seen:
                continue
            seen.add(identifier)
            if identifier not in fields:
                problems.append(
                    f"docs/backlog.base: {identifier} is not a field of docs/templates/seed.md"
                )
    return problems


def problems_check(root: Path) -> list[str]:
    root = Path(root)
    docs = root / "docs"
    if not docs.is_dir():
        return ["docs/: missing"]
    problems: list[str] = []
    vault = _vault_paths(root)
    tags = _tags(root)
    docstrings = _test_docstrings(root)
    test_names = _test_names(root)

    for path in docs.rglob("*"):
        if not path.is_file() or not _in_vault(path, root, vault):
            continue
        text = _read(path)
        if "[[" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        for match in WIKILINK.finditer(text):
            target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            if not _resolve(target, docs, root, vault):
                problems.append(f"{rel}: wikilink {target} does not resolve")

    version_notes: list[tuple[Path, str, dict[str, str], str]] = []
    for path in _notes(docs, root, vault):
        rel = path.relative_to(root).as_posix()
        fm, body = frontmatter(_read(path))
        if fm is None:
            problems.append(f"{rel}: no frontmatter")
            continue
        kind = fm.get("type", "")
        if not kind:
            problems.append(f"{rel}: frontmatter has no type")
            continue
        if not (docs / "templates" / f"{kind}.md").is_file():
            problems.append(f"{rel}: type {kind} has no template docs/templates/{kind}.md")
            continue
        if kind == "seed":
            problems.extend(_seed_problems(path, rel, fm, body, root, tags, docstrings, vault))
        elif kind == "version":
            version_notes.append((path, rel, fm, body))
        elif kind == "review":
            problems.extend(_review_problems(path, rel, fm, body, root, test_names))

    for path, rel, fm, body in version_notes:
        for field in sorted(set(fm) - {"type"}):
            problems.append(f"{rel}: version note has field {field}")
        if not VERSION_NAME.match(path.name):
            problems.append(f"{rel}: version note is not named v<major>.<minor>.md")
    untagged = [(path, rel) for path, rel, _, _ in version_notes if path.stem not in tags]
    if len(untagged) > 1:
        for _, rel in untagged:
            problems.append(f"{rel}: at most one version note may not be a tag ({len(untagged)} are)")
    problems.extend(_base_problems(docs, root, vault))
    in_flight = untagged[0][1] if len(untagged) == 1 else "docs/versions/"
    problems.extend(_build_problems(root, in_flight, _highest_tag(tags)))
    return problems


def _seed_problems(
    path: Path,
    rel: str,
    fm: dict[str, str],
    body: str,
    root: Path,
    tags: set[str],
    docstrings: list[str],
    vault: set[str] | None,
) -> list[str]:
    docs = root / "docs"
    problems: list[str] = []
    for field in sorted(set(fm) - SEED_FIELDS):
        problems.append(f"{rel}: seed has field {field}")
    status = fm.get("status", "")
    if not status:
        return problems + [f"{rel}: seed has no status"]
    if status not in STATUSES:
        return problems + [
            f"{rel}: status {status} is not one of {', '.join(STATUSES)}"
        ]
    # rejected is a way out at any stage: it needs only what open needs, never a version,
    # a Goal or a test.
    rank = 0 if status == "rejected" else STATUSES.index(status)

    if not fm.get("summary", ""):
        problems.append(f"{rel}: seed has no summary")
    value = fm.get("value", "")
    try:
        number = int(value)
        if not 1 <= number <= 5:
            problems.append(f"{rel}: value {value} is not in 1 to 5")
    except ValueError:
        problems.append(f"{rel}: value {value!r} is not in 1 to 5")
    effort = fm.get("effort", "")
    if effort not in EFFORTS:
        problems.append(f"{rel}: effort {effort!r} is not S, M or L")
    created = fm.get("created", "")
    if not created:
        problems.append(f"{rel}: seed has no created")
    elif not CREATED.match(created):
        problems.append(f"{rel}: created {created!r} is not YYYY-MM-DD")

    version = fm.get("version", "")
    if rank >= STATUSES.index("spec"):
        note = docs / "versions" / f"{version}.md"
        if not version:
            problems.append(f"{rel}: seed has no version")
        elif not note.is_file() or not _in_vault(note, root, vault):
            problems.append(f"{rel}: version {version} has no note docs/versions/{version}.md")
        problems.extend(_goal_problems(rel, body))
    if version and version in tags and status not in ("done", "rejected"):
        problems.append(f"{rel}: version {version} is tagged but the seed is {status}")
    if rank >= STATUSES.index("building") and not _named_by_a_test(root, path.stem, docstrings):
        problems.append(f"{rel}: no test names it (seed: {path.stem})")
    return problems


def _segment(name: str) -> bool:
    """Whether `name` is one path segment: not empty, not `.` or `..`, with no `/` or `\\`, so it
    is never a path joined to a directory and looked up."""
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def _review_runs_problems(rel: str, path: Path, fm: dict[str, str]) -> list[str]:
    """The run stamps the review names: each one path segment, at least one, and the note named
    after one of them, `<stamp>.md`. The records themselves are the factory's, kept in its store
    outside the project, so no stamp needs a directory `runs/<stamp>` here."""
    stamps = fm.get("runs", "").split()
    if not stamps:
        return [f"{rel}: review has no runs"]
    problems: list[str] = []
    for stamp in stamps:
        if not _segment(stamp):
            problems.append(f"{rel}: run {stamp} is not one path segment")
    if path.stem not in stamps:
        problems.append(f"{rel}: review is not named after a run ({path.name})")
    return problems


def _review_findings(text: str) -> list[tuple[str, str]]:
    """The review's findings: each level-three heading of the body with its section's text, a
    fenced code block belonging whole."""
    findings: list[list] = []
    current: list | None = None
    fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        if fence is not None:
            if current is not None:
                current[1].append(line)
            if builder.closing_fence(line, fence):
                fence = None
            continue
        opened = builder.opening_fence(line)
        if opened is not None:
            if current is not None:
                current[1].append(line)
            fence = opened
            continue
        level, title = builder.heading(line)
        if level == 3:
            current = [title, []]
            findings.append(current)
        elif level in (1, 2):  # the next section of the note ends the finding
            current = None
        elif current is not None:
            current[1].append(line)
    return [(title, "\n".join(section)) for title, section in findings]


def _judged_problems(
    rel: str, title: str, judged: str, root: Path, test_names: set[str]
) -> list[str]:
    """Every `judged:` entry that does not name what exists, `none:` without a reason, or a line
    with nothing after it or an empty piece between commas."""
    if not judged.strip():
        return [f"{rel}: finding {title} has no judged"]
    if judged.startswith("none:"):
        if not judged[len("none:"):].strip():
            return [f"{rel}: finding {title} judged none: has no reason"]
        return []
    problems: list[str] = []
    for piece in judged.split(","):
        piece = piece.strip()
        if not piece:
            return [f"{rel}: finding {title} has no judged"]
        kind, _, name = piece.partition(" ")
        name = name.strip()
        if kind in ("test", "case", "seed") and not _segment(name):
            problems.append(
                f"{rel}: finding {title} judged {piece!r} names {name!r}, not one path segment"
            )
        elif kind == "test":
            if name not in test_names:
                problems.append(
                    f"{rel}: finding {title} is judged by test {name}, which no test*.py names"
                )
        elif kind == "case":
            if not (root / "cases" / name).is_dir():
                problems.append(
                    f"{rel}: finding {title} is judged by case {name}, which has no directory cases/{name}"
                )
        elif kind == "seed":
            if not (root / "docs" / "seeds" / f"{name}.md").is_file():
                problems.append(
                    f"{rel}: finding {title} is judged by seed {name}, which has no note docs/seeds/{name}.md"
                )
        else:
            problems.append(
                f"{rel}: finding {title} has judged {piece!r}, which is not test, case, seed or none:"
            )
    return problems


def _prose_lines(section: str) -> list[str]:
    """A finding section's prose lines: a fenced code block, as `builder.note_text` reads one, and
    an indented code block (four spaces or more) belong whole and are no line of the prose."""
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in section.split("\n"):
        if fence is not None:
            if builder.closing_fence(line, fence):
                fence = None
            continue
        opened = builder.opening_fence(line)
        if opened is not None:
            fence = opened
            continue
        if line.startswith(("    ", "\t")):
            continue
        lines.append(line)
    return lines


def _finding_problems(
    rel: str, title: str, section: str, root: Path, test_names: set[str]
) -> list[str]:
    """A finding's `severity:`, `verified:` and `judged:` lines, read anywhere in its prose."""
    lines: dict[str, str] = {}
    for line in _prose_lines(section):
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and key in ("severity", "verified", "judged") and key not in lines:
            lines[key] = value.strip()
    problems: list[str] = []
    severity = lines.get("severity")
    if severity is None:
        problems.append(f"{rel}: finding {title} has no severity")
    elif severity not in SEVERITIES:
        problems.append(f"{rel}: finding {title} severity {severity} is not defect or smell")
    verified = lines.get("verified")
    if verified is None:
        problems.append(f"{rel}: finding {title} has no verified")
    elif verified not in VERIFIEDS:
        problems.append(f"{rel}: finding {title} verified {verified} is not yes or no")
    judged = lines.get("judged")
    if judged is None:
        if verified == "yes":
            problems.append(f"{rel}: finding {title} has no judged")
    else:
        problems.extend(_judged_problems(rel, title, judged, root, test_names))
    return problems


def _review_problems(
    path: Path,
    rel: str,
    fm: dict[str, str],
    body: str,
    root: Path,
    test_names: set[str],
) -> list[str]:
    """A review note: the template's fields and no other, a reviewer, a created date, the runs it
    reviewed and one of them naming it, then its findings with comments out."""
    problems: list[str] = []
    for field in sorted(set(fm) - REVIEW_FIELDS):
        problems.append(f"{rel}: review has field {field}")
    if not fm.get("reviewer", ""):
        problems.append(f"{rel}: review has no reviewer")
    created = fm.get("created", "")
    if not created:
        problems.append(f"{rel}: review has no created")
    elif not CREATED.match(created):
        problems.append(f"{rel}: created {created!r} is not YYYY-MM-DD")
    problems.extend(_review_runs_problems(rel, path, fm))
    try:
        text = builder.note_text(body)
    except ValueError:
        return problems + [f"{rel}: review has a %% comment left open"]
    for title, section in _review_findings(text):
        problems.extend(_finding_problems(rel, title, section, root, test_names))
    return problems


def _title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _first_paragraph(body: str) -> str:
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


def _changelog_bullets(body: str) -> list[str]:
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


def _tag_date(root: Path, tag: str) -> str:
    return _git(root, "log", "-1", "--format=%cs", tag).strip()


def problems_render(root: Path) -> list[str]:
    root = Path(root)
    docs = root / "docs"
    tags = _tags(root)
    ordered = sorted(tags, key=lambda tag: _version_key(tag), reverse=True)
    out = ["# Changelog", ""]
    for tag in ordered:
        note = docs / "versions" / f"{tag}.md"
        if not note.is_file():
            continue
        body = frontmatter(_read(note))[1]
        out.append(f"## {_title(body)}")
        out.append("")
        date = _tag_date(root, tag)
        if date:
            out.append(date)
            out.append("")
        paragraph = _first_paragraph(body)
        if paragraph:
            out.append(paragraph)
            out.append("")
        bullets = _changelog_bullets(body)
        out.extend(bullets)
        if bullets:
            out.append("")
    (root / "CHANGELOG.md").write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    return []


def _version_key(tag: str) -> tuple[int, int]:
    match = VERSION.match(tag)
    if not match:
        return (-1, -1)
    return (int(match.group(1)), int(match.group(2)))


def _suite_green(root: Path) -> bool:
    try:
        done = subprocess.run(
            [sys.executable, "-m", "unittest", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _short_hash(root: Path, commit: str) -> str:
    """git's unique abbreviation of `commit`, at least seven characters whatever `core.abbrev`
    says, never the full hash; the first seven characters of the hash when git cannot say."""
    code, out = _git_bytes(root, "rev-parse", "--short=7", commit)
    if code == 0:
        short = _utf8(out).strip()
        if short:
            return short
    return commit[:7]


def _builds(root: Path, previous: str | None) -> tuple[list[str], str | None]:
    """The full hashes of the commits reachable from HEAD and not from `previous`, or every commit
    reachable from HEAD when there is no previous tag. They are listed as revisions, `--` ending
    the revisions so a path named like the range is never read as one; a git that fails is the
    command that failed, never an empty list of builds."""
    revision = f"{previous}..HEAD" if previous is not None else "HEAD"
    command = f"git rev-list {revision} --"
    code, out = _git_bytes(root, *GIT_READ, "rev-list", revision, "--")
    if code != 0:
        return [], command
    return _utf8(out).split(), None


TRAILERS_FORMAT = "%(trailers:key=Built-By,unfold,separator=%x00)"


def _build_trailers(root: Path, commit: str) -> list[str] | None:
    """The entries git's own trailer parser reads as `Built-By` for `commit`, each `<key>:
    <value>` and never empty, the format's one final newline removed and the rest split at NUL;
    `None` when the git command fails."""
    code, out = _git_bytes(root, *GIT_READ, "log", "-1", f"--format={TRAILERS_FORMAT}", commit, "--")
    if code != 0:
        return None
    text = _utf8(out)
    if text.endswith("\n"):
        text = text[:-1]
    if not text:
        return []
    return text.split("\x00")


def _entry_value(entry: str) -> str:
    """An entry's value: what follows its first colon, stripped of ASCII whitespace alone."""
    return entry.partition(":")[2].strip(ASCII_WHITESPACE)


def _commit_build_problems(root: Path, rel_note: str, commit: str) -> list[str]:
    """Every problem of one build, each once: how many `Built-By` lines git's trailer parser does
    not read as a trailer, or a value that does not end `run <stamp>` with the whole stamp in the
    builder's shape. The record the stamp names is the factory's, kept in its store outside the
    project, so no stamp is looked up here. Every value, of a line and of an entry, is checked
    whether git reads it or not; every problem names the commit's abbreviated hash."""
    short = _short_hash(root, commit)
    code, message_bytes = _git_bytes(root, *GIT_READ, "log", "-1", "--format=%B", commit, "--")
    if code != 0:
        return [f"{rel_note}: git log -1 --format=%B failed for {short}"]
    message = _utf8(message_bytes)
    lines = [
        line[match.end():].strip(ASCII_WHITESPACE)
        for line in message.split("\n")
        if (match := BUILT_BY.match(line))
    ]
    if not lines:
        return []
    entries = _build_trailers(root, commit)
    if entries is None:
        return [f"{rel_note}: git log -1 --format={TRAILERS_FORMAT} failed for {short}"]
    values = [*lines, *(_entry_value(entry) for entry in entries)]
    problems: list[str] = []
    unread = len(lines) - len(entries)
    if unread > 0:
        problems.append(
            f"{rel_note}: {short}: git does not read {unread} of {len(lines)} "
            f"`Built-By` lines as a trailer"
        )
    for value in values:
        text = _line_text(value)
        words = _ascii_words(value)
        stamp = words[-1] if len(words) >= 2 and words[-2] == "run" else ""
        if not STAMP_SHAPE.fullmatch(stamp):
            problems.append(f"{rel_note}: {short}: `Built-By: {text}` names no run")
    return problems


def _build_problems(root: Path, rel_note: str, previous: str | None) -> list[str]:
    """Every problem of every build since the previous tag, each once, under the version's note (or
    `docs/versions/` when no version is in flight); a git command that fails while the builds are
    read is one problem naming the command."""
    commits, failed = _builds(root, previous)
    if failed is not None:
        return [f"{rel_note}: {failed} failed"]
    problems: list[str] = []
    seen: set[str] = set()
    for commit in commits:
        for problem in _commit_build_problems(root, rel_note, commit):
            if problem not in seen:
                seen.add(problem)
                problems.append(problem)
    return problems


def _release_problems(root: Path, version: str) -> list[str]:
    root = Path(root)
    docs = root / "docs"
    problems: list[str] = []
    rel_note = f"docs/versions/{version}.md"
    note = docs / "versions" / f"{version}.md"
    tags = _tags(root)

    if not note.is_file():
        problems.append(f"{rel_note}: no such version note")
    if version in tags:
        problems.append(f"{rel_note}: {version} is already tagged")

    for path in _notes(docs, root, _vault_paths(root)):
        fm, _ = frontmatter(_read(path))
        if not fm or fm.get("type") != "seed" or fm.get("version") != version:
            continue
        if fm.get("status") not in ("done", "rejected"):
            rel = path.relative_to(root).as_posix()
            problems.append(f"{rel}: seed of {version} is {fm.get('status') or 'unset'}")

    bullets = _changelog_bullets(frontmatter(_read(note))[1]) if note.is_file() else []
    if not bullets:
        problems.append(f"{rel_note}: no ## Changelog bullets")

    for line in _git(root, "status", "--porcelain").splitlines():
        if line.strip():
            path = line[3:].strip() if len(line) > 3 else line.strip()
            problems.append(f"{path}: uncommitted change")

    previous = _highest_tag(tags)
    if previous is not None:
        changed = _git(root, "diff", "--name-only", previous, "HEAD", "--", "AGENTS.md").strip()
        if not changed:
            problems.append(f"AGENTS.md: unchanged since {previous}")

    if not _suite_green(root):
        problems.append("test: the unittest suite is red")
    return problems


def _annotate(root: Path, version: str, note: Path) -> bool:
    body = frontmatter(_read(note))[1]
    paragraph = _first_paragraph(body)
    bullets = _changelog_bullets(body)
    message = paragraph
    if bullets:
        message = (paragraph + "\n" if paragraph else "") + "\n".join(bullets)
    try:
        done = subprocess.run(
            ["git", "tag", "-a", version, "-m", message, "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _emit(problems: list[str]) -> int:
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def _usage() -> int:
    print(USAGE, file=sys.stderr)
    return 2


def main(argv: list[str], root: Path | str | None = None) -> int:
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    args = list(argv)
    if len(args) < 2 or not args[1].strip():
        return _usage()
    command = args[1].strip()
    if command == "check":
        return _emit(problems_check(root))
    if command == "render":
        return _emit(problems_render(root))
    if command == "release":
        if len(args) < 3 or not args[2].strip():
            return _usage()
        version = args[2].strip()
        problems = problems_check(root)
        if not problems:
            problems = _release_problems(root, version)
        if problems:
            return _emit(problems)
        note = root / "docs" / "versions" / f"{version}.md"
        if not _annotate(root, version, note):
            return _emit([f"docs/versions/{version}.md: git could not create tag {version}"])
        problems_render(root)
        return 0
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
