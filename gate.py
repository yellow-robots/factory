#!/usr/bin/env python3
"""The gate: a deterministic check of the vault, its changelog and its tags.

    uv run gate.py check
    uv run gate.py render
    uv run gate.py release <version>

`check` validates `docs/` and the repository against it, `render` writes `CHANGELOG.md` from
the tags, and `release` refuses until everything derived agrees, then tags and renders. Each
command prints one line per problem on stdout, starting with the path relative to the root,
and exits 1 if there is any; with nothing to report it prints nothing and exits 0. Usage errors
go to stderr and exit 2.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

USAGE = "usage: gate.py check|render|release <version>"
STATUSES = ("open", "spec", "building", "done", "rejected")
SEED_FIELDS = {"type", "status", "summary", "value", "effort", "version", "created"}
EFFORTS = {"S", "M", "L"}
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_NAME = re.compile(r"^v(\d+)\.(\d+)\.md$")
VERSION = re.compile(r"^v(\d+)\.(\d+)$")
WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")


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


def _notes(docs: Path) -> list[Path]:
    """Every `.md` under `docs/`, the templates excepted."""
    templates = docs / "templates"
    return [p for p in sorted(docs.rglob("*.md")) if templates not in p.parents]


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout


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


def _resolve(target: str, docs: Path) -> bool:
    """A note in `docs/`, by path or by name, or a `.base` file."""
    target = target.strip()
    if not target:
        return False
    direct = docs / target
    if direct.is_file():
        return True
    if direct.suffix == "" and (docs / (target + ".md")).is_file():
        return True
    name = target.rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".md") else name
    for found in docs.rglob("*"):
        if found.is_file() and (found.name == name or found.stem == stem):
            return True
    return False


def _goal_text(body: str) -> bool:
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "## Goal":
            continue
        for after in lines[i + 1:]:
            if after.strip().startswith("#"):
                break
            if after.strip():
                return True
        return False
    return False


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


def _named_by_a_test(root: Path, stem: str, docstrings: list[str]) -> bool:
    pattern = re.compile(rf"seed:\s*{re.escape(stem)}(?![\w-])")
    return any(pattern.search(doc) for doc in docstrings)


def problems_check(root: Path) -> list[str]:
    root = Path(root)
    docs = root / "docs"
    if not docs.is_dir():
        return ["docs/: missing"]
    problems: list[str] = []
    tags = _tags(root)
    docstrings = _test_docstrings(root)

    for path in docs.rglob("*"):
        if not path.is_file():
            continue
        text = _read(path)
        if "[[" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        for match in WIKILINK.finditer(text):
            target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            if not _resolve(target, docs):
                problems.append(f"{rel}: wikilink {target} does not resolve")

    version_notes: list[tuple[Path, str, dict[str, str], str]] = []
    for path in _notes(docs):
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
            problems.extend(_seed_problems(path, rel, fm, body, root, tags, docstrings))
        elif kind == "version":
            version_notes.append((path, rel, fm, body))

    for path, rel, fm, body in version_notes:
        for field in sorted(set(fm) - {"type"}):
            problems.append(f"{rel}: version note has field {field}")
        if not VERSION_NAME.match(path.name):
            problems.append(f"{rel}: version note is not named v<major>.<minor>.md")
    untagged = [(path, rel) for path, rel, _, _ in version_notes if path.stem not in tags]
    if len(untagged) > 1:
        for _, rel in untagged:
            problems.append(f"{rel}: at most one version note may not be a tag ({len(untagged)} are)")
    return problems


def _seed_problems(
    path: Path,
    rel: str,
    fm: dict[str, str],
    body: str,
    root: Path,
    tags: set[str],
    docstrings: list[str],
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
        if not version:
            problems.append(f"{rel}: seed has no version")
        elif not (docs / "versions" / f"{version}.md").is_file():
            problems.append(f"{rel}: version {version} has no note docs/versions/{version}.md")
        if not _goal_text(body):
            problems.append(f"{rel}: seed has no ## Goal with text")
    if version and version in tags and status not in ("done", "rejected"):
        problems.append(f"{rel}: version {version} is tagged but the seed is {status}")
    if rank >= STATUSES.index("building") and not _named_by_a_test(root, path.stem, docstrings):
        problems.append(f"{rel}: no test names it (seed: {path.stem})")
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

    for path in _notes(docs):
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
