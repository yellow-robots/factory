#!/usr/bin/env python3
"""The repository's reader and writer: git, the listing, the tests and the suite.

The gate and the loop reach the repository through this module alone. One shape for a command's
answer, `Result`, and a reader that needs git to have answered raises `RepoError` naming the
command and git's own words rather than answering with nothing.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# The build reads ask git for UTF-8 and for no signature whatever the repository's display
# settings say, so a message in another log encoding is not a build git cannot read and a
# signature is never counted as a trailer.
GIT_READ = ("-c", "i18n.logOutputEncoding=UTF-8", "-c", "log.showSignature=false")
WHEEL_DIR = "dist"  # where the release's build puts the wheel; git ignores it
VERSION = re.compile(r"^v(\d+)\.(\d+)$")
TRAILERS_FORMAT = "%(trailers:key=Built-By,unfold,separator=%x00)"


@dataclass(frozen=True)
class Result:
    """One command's exit status, its standard output and its standard error."""

    code: int
    out: str
    err: str


class RepoError(Exception):
    """A git command, or a file, a reader needed and could not have answered."""

    def __init__(self, command: str, err: str) -> None:
        """Keep the command that failed and git's words, printing them as one line."""
        self.command = command
        self.err = err
        super().__init__(f"{command} failed: {err}")


@dataclass(frozen=True)
class Listing:
    """What git says of `docs/`: the paths it lists and the paths an ignore rule matches."""

    listed: set[str]
    ignored: set[str]


@dataclass(frozen=True)
class Test:
    """One test method or class of the root's `test*.py`: its unittest id, its name and its
    docstring."""

    id: str
    name: str
    doc: str


def _utf8(data: bytes) -> str:
    """The bytes decoded as UTF-8 with what cannot be decoded replaced; never raises."""
    return data.decode("utf-8", "replace")


def git(root: Path, *args: str) -> Result:
    """Run git at `root` with the same `-c` options everywhere; a git that cannot start is a
    non-zero `Result` with the exception's words in `err`, never a raise, and `err` is git's words
    on one line, runs of whitespace collapsed to one space."""
    try:
        done = subprocess.run(["git", *GIT_READ, *args], cwd=str(root), capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        return Result(1, "", " ".join(str(e).split()))
    return Result(done.returncode, _utf8(done.stdout), " ".join(_utf8(done.stderr).split()))


def tags(root: Path) -> set[str]:
    """Every tag git lists, or `RepoError` when git cannot answer."""
    done = git(root, "tag", "-l")
    if done.code != 0:
        raise RepoError("git tag -l", done.err)
    return {line.strip() for line in done.out.splitlines() if line.strip()}


def version_key(tag: str) -> tuple[int, int]:
    """A `v<major>.<minor>` tag's numbers, or (-1, -1) for a tag that is not one."""
    match = VERSION.match(tag)
    if not match:
        return (-1, -1)
    return (int(match.group(1)), int(match.group(2)))


def highest(tags: set[str]) -> str | None:
    """The highest `v<major>.<minor>` tag by number, or None when there is none."""
    best: str | None = None
    for tag in tags:
        if VERSION.match(tag) and (best is None or version_key(tag) > version_key(best)):
            best = tag
    return best


def listing(root: Path, docs: Path) -> Listing | None:
    """What git lists and ignores under `docs/`, or None when git answers for nobody -- a
    directory that is no checkout, or a git whose top level is not `root` itself; `RepoError`
    when git is in a checkout but a call fails."""
    top = git(root, "rev-parse", "--show-toplevel")
    if top.code != 0:
        return None
    if not top.out.strip() or Path(top.out.strip()).resolve() != Path(root).resolve():
        return None
    files = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if files.code != 0:
        raise RepoError("git ls-files --cached --others --exclude-standard -z", files.err)
    listed = {path for path in files.out.split("\0") if path}
    return Listing(listed, _ignored(root, docs))


def _ignored(root: Path, docs: Path) -> set[str]:
    """The paths under `docs/` git is told to ignore, relative to `root`, asked of git once;
    `RepoError` when git cannot answer."""
    rels: list[str] = []
    for path in docs.rglob("*"):
        try:
            if path.is_file():
                rels.append(path.relative_to(root).as_posix())
        except (OSError, ValueError):
            continue
    if not rels:
        return set()
    command = "git check-ignore --no-index -z --stdin"
    try:
        done = subprocess.run(
            ["git", *GIT_READ, "check-ignore", "--no-index", "-z", "--stdin"],
            cwd=str(root),
            input="\0".join(rels).encode("utf-8", "surrogateescape"),
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise RepoError(command, " ".join(str(e).split())) from e
    if done.returncode not in (0, 1):
        raise RepoError(command, " ".join(_utf8(done.stderr).split()))
    return {path for path in _utf8(done.stdout).split("\0") if path}


def builds(root: Path, previous: str | None) -> list[str]:
    """The full hashes reachable from HEAD and not from `previous`, or every commit reachable
    from HEAD when there is none; `RepoError` when git cannot list them."""
    revision = f"{previous}..HEAD" if previous is not None else "HEAD"
    command = f"git rev-list {revision} --"
    done = git(root, "rev-list", revision, "--")
    if done.code != 0:
        raise RepoError(command, done.err)
    return done.out.split()


def trailers(root: Path, commit: str) -> list[str]:
    """The entries git's own trailer parser reads as `Built-By` for `commit`, each `<key>:
    <value>` and never empty, or `RepoError` when git cannot answer."""
    command = f"git log -1 --format={TRAILERS_FORMAT}"
    done = git(root, "log", "-1", f"--format={TRAILERS_FORMAT}", commit, "--")
    if done.code != 0:
        raise RepoError(command, done.err)
    text = done.out
    if text.endswith("\n"):
        text = text[:-1]
    if not text:
        return []
    return text.split("\x00")


def tag_date(root: Path, tag: str) -> str:
    """The commit date of `tag`, `YYYY-MM-DD`, or `RepoError` when git cannot answer."""
    done = git(root, "log", "-1", "--format=%cs", tag)
    if done.code != 0:
        raise RepoError("git log -1 --format=%cs", done.err)
    return done.out.strip()


def short_hash(root: Path, commit: str) -> str:
    """git's unique abbreviation of `commit`, at least seven characters whatever `core.abbrev`
    says, or `RepoError` when git cannot answer."""
    done = git(root, "rev-parse", "--short=7", commit)
    short = done.out.strip()
    if done.code != 0 or not short:
        raise RepoError("git rev-parse --short=7", done.err)
    return short


def status(root: Path) -> tuple[str, ...]:
    """The uncommitted paths `git status --porcelain` names, or `RepoError` when git cannot
    answer."""
    done = git(root, "status", "--porcelain")
    if done.code != 0:
        raise RepoError("git status --porcelain", done.err)
    paths: list[str] = []
    for line in done.out.splitlines():
        if not line.strip():
            continue
        paths.append(line[3:].strip() if len(line) > 3 else line.strip())
    return tuple(paths)


def changed_since(root: Path, tag: str, path: str) -> bool:
    """Whether `path` differs between `tag` and the head, or `RepoError` when git cannot
    answer."""
    command = f"git diff --name-only {tag} HEAD -- {path}"
    done = git(root, "diff", "--name-only", tag, "HEAD", "--", path)
    if done.code != 0:
        raise RepoError(command, done.err)
    return bool(done.out.strip())


def message(root: Path, commit: str) -> str:
    """`commit`'s whole message, or `RepoError` when git cannot answer."""
    done = git(root, "log", "-1", "--format=%B", commit, "--")
    if done.code != 0:
        raise RepoError("git log -1 --format=%B", done.err)
    # git follows the body with one newline of its own; the message is what the commit holds.
    return done.out[:-1] if done.out.endswith("\n") else done.out


def tests(root: Path) -> list[Test]:
    """Every test method or class of each `test*.py` at the root, read once, with its unittest id,
    its name and its docstring; a file that cannot be read or does not parse raises `RepoError`
    naming it, carrying the tests of the other files."""
    found: list[Test] = []
    reasons: list[tuple[str, str]] = []
    for path in sorted(root.glob("test*.py")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            reasons.append((rel, "cannot be read"))
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            reasons.append((rel, "does not parse"))
            continue
        found.extend(_module_tests(tree, path.stem))
    if reasons:
        error = RepoError("parse test files", f"{reasons[0][0]}: {reasons[0][1]}")
        error.tests = found
        error.reasons = reasons
        raise error
    return found


def _module_tests(tree: ast.Module, module: str) -> list[Test]:
    """Every test method and class one parsed `module` holds, with its unittest id."""
    found: list[Test] = []

    def walk(body: list[ast.stmt], classes: list[str]) -> None:
        """Record the test methods and classes in `body`, inside `classes`."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                name = ".".join([*classes, node.name])
                found.append(Test(f"{module}.{name}", node.name, ast.get_docstring(node) or ""))
                walk(node.body, [*classes, node.name])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test"
            ):
                name = ".".join([*classes, node.name])
                found.append(Test(f"{module}.{name}", node.name, ast.get_docstring(node) or ""))

    walk(tree.body, [])
    return found


def suite(root: Path) -> str:
    """How the unittest suite at `root` ran: `green`, `red`, `timed out` or `could not run`."""
    try:
        done = subprocess.run(
            [sys.executable, "-m", "unittest", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "timed out"
    except (OSError, subprocess.SubprocessError):
        return "could not run"
    return "green" if done.returncode == 0 else "red"


def tag(root: Path, version: str, message: str) -> Result:
    """Cut an annotated tag `version` at HEAD with `message`; git's own `Result`."""
    return git(root, "tag", "-a", version, "-m", message, "HEAD")


def wheels(dist: Path) -> set[str]:
    """The wheel filenames `dist/` holds; a missing directory is no wheel and one that cannot be
    read raises `RepoError`."""
    if not dist.is_dir():
        return set()
    try:
        return {p.name for p in dist.iterdir() if p.is_file() and p.name.endswith(".whl")}
    except OSError as e:
        raise RepoError(f"read {dist}", str(e)) from e


def build_wheel(root: Path) -> tuple[str, str]:
    """`uv build --wheel` at the root; the wheel's path relative to the root, found in `dist/` as
    the wheel this build put there, or the empty string with uv's own words when it failed."""
    dist = root / WHEEL_DIR
    try:
        before = wheels(dist)
    except RepoError:
        before = set()
    try:
        done = subprocess.run(
            ["uv", "build", "--wheel"],
            cwd=str(root),
            capture_output=True,
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as e:
        return "", " ".join(str(e).split())
    if done.returncode != 0:
        return "", " ".join((done.stderr.strip() or done.stdout.strip()).split())
    try:
        made = sorted(wheels(dist) - before)
    except RepoError as e:
        return "", str(e)
    if not made:
        return "", "uv build named no wheel"
    return f"{WHEEL_DIR}/{made[-1]}", ""
