#!/usr/bin/env python3
"""The gate: a deterministic check of the vault, its changelog and its tags.

    uv run gate.py check
    uv run gate.py render
    uv run gate.py release <version>

`check` validates `docs/` and the repository against it, `render` writes `CHANGELOG.md` from
the tags, and `release` refuses until everything derived agrees, then tags, builds the product
as a wheel at the clean tag and renders. `release` runs `uv build --wheel` into `dist/`, which
git ignores, once the tag is cut and before the changelog is rendered, because the version is
read from the tree and a dirty tree is marked as one; the wheel's path -- found in `dist/` as
the wheel this release built, never read off what `uv` prints -- is printed as the release's
last line. A build that fails is the release's failure, exit 1, naming what `uv build` said,
with the tag standing and the changelog unrendered: nothing has been pushed, and a tag is not a
deployment. `check` and `release` read the builds since the highest tag, every commit whose
message carries a `Built-By` line, and refuse when git's trailer parser does not read one or its
value does not name a run; the record the stamp names is the factory's, kept in its store
outside the project, so no stamp is looked up in the project. Each command prints one line per
problem on stdout, starting with the path relative to the root, and exits 1 if there is any;
with nothing to report it prints nothing and exits 0. Usage errors go to stderr and exit 2.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import builder
import repo
import vault
from vault import Note, Vault

USAGE = "usage: gate.py check|render|release <version>|next|numbers [<version>]"
STATUSES = ("open", "spec", "building", "done", "rejected")
SEVERITIES = ("defect", "smell")
VERIFIEDS = ("yes", "no")
EFFORTS = {"S", "M", "L"}
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_NAME = re.compile(r"^v(\d+)\.(\d+)\.md$")
WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
BUILT_BY = re.compile(r"^Built-By[ \t]*:", re.IGNORECASE | re.ASCII)
ASCII_WHITESPACE = " \t\n\r\x0b\x0c"
ASCII_RUN = re.compile(r"[^ \t\n\r\x0b\x0c]+")
# The builder names a record with a UTC stamp, and, when a second run shares its second, the
# stamp and a dash and that run's number: the shape the gate reads for a run is that one, digits
# in ASCII alone, so a dash with nothing after it, with something that is not a number or with a
# second dash names no run.
STAMP_SHAPE = re.compile(r"\d{8}T\d{6}Z(-\d+)?", re.ASCII)
# A full commit hash is forty lowercase hex digits: a problem abbreviates one where git names it,
# so a printed problem never names a commit by its full hash.
FULL_HASH = re.compile(r"\b[0-9a-f]{40}\b")


@dataclass(frozen=True)
class Problem:
    """One problem of the gate: the path it names and what is wrong with it."""

    path: str
    message: str

    def __str__(self) -> str:
        """The problem as one printed line, `path: message`."""
        return f"{self.path}: {self.message}"


class Unrenderable(Exception):
    """The problems that keep `render` from writing a changelog."""

    def __init__(self, problems: list[Problem]) -> None:
        """Keep `problems` as the reason no changelog was written."""
        self.problems = problems
        super().__init__("; ".join(str(problem) for problem in problems))


@dataclass(frozen=True)
class Fields:
    """The template fields each note's kind needs, each read once for a check."""

    seed: vault.Template
    review: vault.Template


def _line_text(value: str) -> str:
    """A value with its control characters escaped, so a problem that quotes it stays one line."""
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


def _repo_problem(path: str, error: repo.RepoError) -> Problem:
    """A `RepoError` as one problem: the thing being read, the command that failed and git's
    words, with any full commit hash abbreviated to seven characters."""
    said = f"{error.command} failed: {error.err}"
    return Problem(path, FULL_HASH.sub(lambda match: match.group()[:7], said))


def _dedup(problems: list[Problem]) -> list[Problem]:
    """`problems` in order, each path and message once."""
    seen: set[tuple[str, str]] = set()
    unique: list[Problem] = []
    for problem in problems:
        key = (problem.path, problem.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(problem)
    return unique


def _vault(root: Path) -> tuple[Vault, list[Problem]]:
    """The vault at `root`, read once, and the problem when git cannot list `docs/`."""
    root = Path(root)
    try:
        return Vault.read(root), []
    except repo.RepoError as error:
        return Vault(root, root / "docs", None), [_repo_problem("docs/", error)]


def _fields(store: Vault) -> tuple[Fields, list[Problem]]:
    """The seed's and review's field sets, read once from the Vault, and the problem of a template
    that is part of the vault but cannot be read or has no frontmatter."""
    kinds: dict[str, vault.Template] = {}
    problems: list[Problem] = []
    for kind in ("seed", "review"):
        path = store.docs / "templates" / f"{kind}.md"
        if not path.is_file() or not store.part(path):
            kinds[kind] = vault.Template(None, "")
            continue
        found = store.template(kind)
        if found.error:
            problems.append(Problem(f"docs/templates/{kind}.md", found.error))
        kinds[kind] = found
    return Fields(kinds["seed"], kinds["review"]), problems


def _read_tests(root: Path) -> tuple[list[repo.Test], list[Problem]]:
    """Every test of the root and, when a test file cannot be read or parsed, one problem naming
    it."""
    try:
        found = repo.tests(root)
    except repo.RepoError as error:
        return [], [_repo_problem("test*.py", error)]
    return list(found.found), [Problem(rel, why) for rel, why in found.unparseable]


def _wikilink_problems(store: Vault) -> list[Problem]:
    """Every wikilink of any file the vault holds, whole, that does not resolve."""
    problems: list[Problem] = []
    for held in store.files():
        if held.error or "[[" not in held.text:
            continue
        for match in WIKILINK.finditer(held.text):
            target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            if not store.resolves(target):
                problems.append(Problem(held.rel, f"wikilink {target} does not resolve"))
    return problems


def _goal_problems(rel: str, body: str) -> list[Problem]:
    """The seed's `## Goal` as `builder.read_seed` reads it: the builder's `note_text` and
    `goal_section`, so the gate refuses exactly the notes the builder would."""
    try:
        text = builder.note_text(body)
    except ValueError:
        return [Problem(rel, "seed has a %% comment left open")]
    if not builder.goal_section(text):
        return [Problem(rel, "seed has no ## Goal with text")]
    return []


def _named_by_a_test(stem: str, tests: list[repo.Test]) -> bool:
    """Whether a test's docstring names the seed `stem`, as `vault.names_seed` reads it."""
    return any(vault.names_seed(test.doc, stem) for test in tests)


def _seed_problems(
    note: Note,
    store: Vault,
    tags: set[str] | None,
    tests: list[repo.Test],
    fields: Fields,
) -> list[Problem]:
    """A seed note: the template's fields, its status and the fields that status needs."""
    rel, fm, body = note.rel, note.fm, note.body
    problems: list[Problem] = []
    seed_fields = set(fields.seed.fields) if fields.seed.fields is not None else None
    if seed_fields is not None:
        for field in sorted(set(fm) - seed_fields):
            problems.append(Problem(rel, f"seed has field {field}"))
    status = fm.get("status", "")
    if not status:
        return problems + [Problem(rel, "seed has no status")]
    if status not in STATUSES:
        return problems + [Problem(rel, f"status {status} is not one of {', '.join(STATUSES)}")]
    # rejected is a way out at any stage: it needs only what open needs, never a version,
    # a Goal or a test.
    rank = 0 if status == "rejected" else STATUSES.index(status)

    if not fm.get("summary", ""):
        problems.append(Problem(rel, "seed has no summary"))
    value = fm.get("value", "")
    try:
        number = int(value)
        if not 1 <= number <= 5:
            problems.append(Problem(rel, f"value {value} is not in 1 to 5"))
    except ValueError:
        problems.append(Problem(rel, f"value {value!r} is not in 1 to 5"))
    effort = fm.get("effort", "")
    if effort not in EFFORTS:
        problems.append(Problem(rel, f"effort {effort!r} is not S, M or L"))
    created = fm.get("created", "")
    if not created:
        problems.append(Problem(rel, "seed has no created"))
    elif not CREATED.match(created):
        problems.append(Problem(rel, f"created {created!r} is not YYYY-MM-DD"))

    version = fm.get("version", "")
    if rank >= STATUSES.index("spec"):
        note_path = store.docs / "versions" / f"{version}.md"
        if not version:
            problems.append(Problem(rel, "seed has no version"))
        elif not note_path.is_file() or not store.part(note_path):
            problems.append(
                Problem(rel, f"version {version} has no note docs/versions/{version}.md")
            )
        problems.extend(_goal_problems(rel, body))
    if tags is not None and version and version in tags and status not in ("done", "rejected"):
        problems.append(Problem(rel, f"version {version} is tagged but the seed is {status}"))
    if rank >= STATUSES.index("building"):
        if not _named_by_a_test(note.path.stem, tests):
            problems.append(Problem(rel, f"no test names it (seed: {note.path.stem})"))
    return problems


def _segment(name: str) -> bool:
    """Whether `name` is one path segment: not empty, not `.` or `..`, with no `/` or `\\`."""
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def _review_runs_problems(rel: str, path: Path, fm: dict[str, str]) -> list[Problem]:
    """The run stamps the review names: each one path segment, at least one, and the note named
    after one of them, `<stamp>.md`."""
    stamps = fm.get("runs", "").split()
    if not stamps:
        return [Problem(rel, "review has no runs")]
    problems: list[Problem] = []
    for stamp in stamps:
        if not _segment(stamp):
            problems.append(Problem(rel, f"run {stamp} is not one path segment"))
    if path.stem not in stamps:
        problems.append(Problem(rel, f"review is not named after a run ({path.name})"))
    return problems


def _judged_problems(
    rel: str, heading_title: str, judged: str, root: Path, test_names: set[str]
) -> list[Problem]:
    """Every `judged:` entry that does not name what exists, `none:` without a reason, or a line
    with nothing after it or an empty piece between commas."""
    if not judged.strip():
        return [Problem(rel, f"finding {heading_title} has no judged")]
    if judged.startswith("none:"):
        if not judged[len("none:") :].strip():
            return [Problem(rel, f"finding {heading_title} judged none: has no reason")]
        return []
    problems: list[Problem] = []
    for piece in judged.split(","):
        piece = piece.strip()
        if not piece:
            return [Problem(rel, f"finding {heading_title} has no judged")]
        kind, _, name = piece.partition(" ")
        name = name.strip()
        if kind in ("test", "case", "seed") and not _segment(name):
            problems.append(
                Problem(
                    rel,
                    f"finding {heading_title} judged {piece!r} names {name!r}, "
                    "not one path segment",
                )
            )
        elif kind == "test":
            if name not in test_names:
                problems.append(
                    Problem(
                        rel,
                        f"finding {heading_title} is judged by test {name}, "
                        "which no test*.py names",
                    )
                )
        elif kind == "case":
            if not (root / "cases" / name).is_dir():
                problems.append(
                    Problem(
                        rel,
                        f"finding {heading_title} is judged by case {name}, "
                        f"which has no directory cases/{name}",
                    )
                )
        elif kind == "seed":
            if not (root / "docs" / "seeds" / f"{name}.md").is_file():
                problems.append(
                    Problem(
                        rel,
                        f"finding {heading_title} is judged by seed {name}, "
                        f"which has no note docs/seeds/{name}.md",
                    )
                )
        else:
            problems.append(
                Problem(
                    rel,
                    f"finding {heading_title} has judged {piece!r}, "
                    "which is not test, case, seed or none:",
                )
            )
    return problems


def _finding_problems(
    rel: str, heading_title: str, section: str, root: Path, test_names: set[str]
) -> list[Problem]:
    """A finding's `severity:`, `verified:` and `judged:` lines, read anywhere in its prose."""
    lines: dict[str, str] = {}
    for line in vault.prose_lines(section):
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and key in ("severity", "verified", "judged") and key not in lines:
            lines[key] = value.strip()
    problems: list[Problem] = []
    severity = lines.get("severity")
    if severity is None:
        problems.append(Problem(rel, f"finding {heading_title} has no severity"))
    elif severity not in SEVERITIES:
        problems.append(
            Problem(rel, f"finding {heading_title} severity {severity} is not defect or smell")
        )
    verified = lines.get("verified")
    if verified is None:
        problems.append(Problem(rel, f"finding {heading_title} has no verified"))
    elif verified not in VERIFIEDS:
        problems.append(
            Problem(rel, f"finding {heading_title} verified {verified} is not yes or no")
        )
    judged = lines.get("judged")
    if judged is None:
        if verified == "yes":
            problems.append(Problem(rel, f"finding {heading_title} has no judged"))
    else:
        problems.extend(_judged_problems(rel, heading_title, judged, root, test_names))
    return problems


def _review_problems(
    note: Note,
    store: Vault,
    tests: list[repo.Test],
    fields: Fields,
) -> list[Problem]:
    """A review note: the template's fields, a reviewer, a created date, the runs it reviewed and
    one of them naming it, then its findings with comments out."""
    rel, fm, body = note.rel, note.fm, note.body
    problems: list[Problem] = []
    if fields.review.fields is not None:
        for field in sorted(set(fm) - set(fields.review.fields)):
            problems.append(Problem(rel, f"review has field {field}"))
    test_names = {test.name for test in tests}
    if not fm.get("reviewer", ""):
        problems.append(Problem(rel, "review has no reviewer"))
    created = fm.get("created", "")
    if not created:
        problems.append(Problem(rel, "review has no created"))
    elif not CREATED.match(created):
        problems.append(Problem(rel, f"created {created!r} is not YYYY-MM-DD"))
    problems.extend(_review_runs_problems(rel, note.path, fm))
    try:
        text = builder.note_text(body)
    except ValueError:
        return problems + [Problem(rel, "review has a %% comment left open")]
    for heading_title, section in vault.review_findings(text):
        problems.extend(_finding_problems(rel, heading_title, section, store.root, test_names))
    return problems


def _note_problems(
    store: Vault,
    tags: set[str] | None,
    tests: list[repo.Test],
    fields: Fields,
) -> tuple[list[Problem], list[Note]]:
    """Every problem of one note, and the version notes kept for the check over all of them."""
    problems: list[Problem] = []
    version_notes: list[Note] = []
    for note in store.notes():
        if note.error:
            problems.append(Problem(note.rel, "cannot be read"))
            continue
        if note.fm is None:
            problems.append(Problem(note.rel, "no frontmatter"))
            continue
        kind = note.kind
        if not kind:
            problems.append(Problem(note.rel, "frontmatter has no type"))
            continue
        template = store.docs / "templates" / f"{kind}.md"
        if not template.is_file() or not store.part(template):
            problems.append(
                Problem(note.rel, f"type {kind} has no template docs/templates/{kind}.md")
            )
            continue
        if kind == "seed":
            problems.extend(_seed_problems(note, store, tags, tests, fields))
        elif kind == "version":
            version_notes.append(note)
        elif kind == "review":
            problems.extend(_review_problems(note, store, tests, fields))
    return problems, version_notes


def _version_problems(
    version_notes: list[Note], tags: set[str] | None
) -> tuple[list[Problem], list[Note]]:
    """Every problem of the version notes together, and the ones that are not a tag."""
    problems: list[Problem] = []
    for note in version_notes:
        for field in sorted(set(note.fm) - {"type"}):
            problems.append(Problem(note.rel, f"version note has field {field}"))
        if not VERSION_NAME.match(note.path.name):
            problems.append(Problem(note.rel, "version note is not named v<major>.<minor>.md"))
    if tags is None:
        return problems, []
    untagged = [note for note in version_notes if note.path.stem not in tags]
    if len(untagged) > 1:
        for note in untagged:
            problems.append(
                Problem(
                    note.rel, f"at most one version note may not be a tag ({len(untagged)} are)"
                )
            )
    return problems, untagged


def _base_problems(store: Vault, fields: Fields) -> list[Problem]:
    """The properties `docs/backlog.base` names that are not seed template fields."""
    base = store.docs / "backlog.base"
    if not base.is_file() or not store.part(base):
        return []
    seed_fields = set(fields.seed.fields) if fields.seed.fields is not None else None
    if seed_fields is None:
        return []
    text = store.text(base)
    if text is None:
        return [Problem("docs/backlog.base", "cannot be read")]
    problems: list[Problem] = []
    seen: set[str] = set()
    for kind, name in vault.base_named(text):
        identifiers = vault.plain_names(name) if kind == "name" else vault.expression_names(name)
        for identifier in identifiers:
            if identifier in seen:
                continue
            seen.add(identifier)
            if identifier not in seed_fields:
                problems.append(
                    Problem(
                        "docs/backlog.base",
                        f"{identifier} is not a field of docs/templates/seed.md",
                    )
                )
    return problems


def _entry_value(entry: str) -> str:
    """An entry's value: what follows its first colon, stripped of ASCII whitespace alone."""
    return entry.partition(":")[2].strip(ASCII_WHITESPACE)


def _commit_build_problems(root: Path, rel_note: str, commit: str) -> list[Problem]:
    """Every problem of one build, each once: how many `Built-By` lines git's trailer parser does
    not read as a trailer, or a value that does not end `run <stamp>` with the whole stamp in the
    builder's shape."""
    try:
        short = repo.short_hash(root, commit)
    except repo.RepoError as error:
        return [_repo_problem(rel_note, error)]
    try:
        message = repo.message(root, commit)
    except repo.RepoError as error:
        return [_repo_problem(rel_note, error)]
    lines = [
        line[match.end() :].strip(ASCII_WHITESPACE)
        for line in message.split("\n")
        if (match := BUILT_BY.match(line))
    ]
    if not lines:
        return []
    try:
        entries = repo.trailers(root, commit)
    except repo.RepoError as error:
        return [_repo_problem(rel_note, error)]
    values = [*lines, *(_entry_value(entry) for entry in entries)]
    problems: list[Problem] = []
    unread = len(lines) - len(entries)
    if unread > 0:
        problems.append(
            Problem(
                rel_note,
                f"{short}: git does not read {unread} of {len(lines)} "
                "`Built-By` lines as a trailer",
            )
        )
    for value in values:
        text = _line_text(value)
        if repo.run_stamp(value) is None:
            problems.append(Problem(rel_note, f"{short}: `Built-By: {text}` names no run"))
    return problems


def _build_problems(root: Path, rel_note: str, previous: str | None) -> list[Problem]:
    """Every problem of every build since the previous tag, each once, under the version's note
    (or `docs/versions/` when no version is in flight); a git command that fails while the builds
    are read is one problem naming the command."""
    try:
        commits = repo.builds(root, previous)
    except repo.RepoError as error:
        return [_repo_problem(rel_note, error)]
    problems: list[Problem] = []
    for commit in commits:
        problems.extend(_commit_build_problems(root, rel_note, commit))
    return _dedup(problems)


def problems_check(root: Path, store: Vault | None = None) -> list[Problem]:
    """Every problem of the vault and the repository against it, each once."""
    root = Path(root)
    docs = root / "docs"
    if not docs.is_dir():
        return [Problem("docs/", "missing")]
    problems: list[Problem] = []
    if store is None:
        store, errors = _vault(root)
        problems.extend(errors)
    tests, test_problems = _read_tests(root)
    problems.extend(test_problems)
    try:
        tags = repo.tags(root)
    except repo.RepoError as error:
        problems.append(_repo_problem("docs/versions/", error))
        tags = None
    fields, field_problems = _fields(store)
    problems.extend(field_problems)
    problems.extend(_wikilink_problems(store))
    note_problems, version_notes = _note_problems(store, tags, tests, fields)
    problems.extend(note_problems)
    version_problems, untagged = _version_problems(version_notes, tags)
    problems.extend(version_problems)
    in_flight = untagged[0].rel if len(untagged) == 1 else "docs/versions/"
    problems.extend(_base_problems(store, fields))
    previous = repo.highest(tags) if tags is not None else None
    problems.extend(_build_problems(root, in_flight, previous))
    return _dedup(problems)


def _release_problems(root: Path, version: str, store: Vault) -> list[Problem]:
    """Every problem a release of `version` has that check does not already report."""
    root = Path(root)
    docs = root / "docs"
    problems: list[Problem] = []
    rel_note = f"docs/versions/{version}.md"
    note = docs / "versions" / f"{version}.md"
    try:
        tags = repo.tags(root)
    except repo.RepoError as error:
        problems.append(_repo_problem("docs/versions/", error))
        tags = set()

    if not note.is_file():
        problems.append(Problem(rel_note, "no such version note"))
    if version in tags:
        problems.append(Problem(rel_note, f"{version} is already tagged"))

    for item in store.notes():
        fm = item.fm
        if not fm or fm.get("type") != "seed" or fm.get("version") != version:
            continue
        if fm.get("status") not in ("done", "rejected"):
            problems.append(
                Problem(item.rel, f"seed of {version} is {fm.get('status') or 'unset'}")
            )

    version_note = _version_note(store, version)
    if version_note is None or version_note.error:
        problems.append(Problem(rel_note, "cannot be read"))
    elif not vault.changelog_bullets(version_note.body):
        problems.append(Problem(rel_note, "no ## Changelog bullets"))

    try:
        dirty = repo.status(root)
    except repo.RepoError as error:
        problems.append(_repo_problem(rel_note, error))
    else:
        for path in dirty:
            # `dist/` is the release's own output only where git ignores it, as this repository
            # does; `git status` leaves an ignored path out already, so a path there in a
            # repository that does not ignore it is an uncommitted change like any other and the
            # tree is not clean.
            problems.append(Problem(path, "uncommitted change"))

    previous = repo.highest(tags)
    if previous is not None:
        try:
            changed = repo.changed_since(root, previous, "AGENTS.md")
        except repo.RepoError as error:
            problems.append(_repo_problem(rel_note, error))
        else:
            if not changed:
                problems.append(Problem("AGENTS.md", f"unchanged since {previous}"))

    result = repo.suite(root)
    if result == "red":
        problems.append(Problem("test", "the unittest suite is red"))
    elif result == "timed out":
        problems.append(Problem("test", "the unittest suite timed out"))
    elif result == "could not run":
        problems.append(Problem("test", "the unittest suite could not run"))
    return _dedup(problems)


def _version_note(store: Vault, version: str) -> Note | None:
    """The version note `docs/versions/<version>.md` the vault holds, or None when it holds
    none."""
    rel = f"docs/versions/{version}.md"
    for note in store.notes():
        if note.rel == rel:
            return note
    return None


def render(root: Path, store: Vault | None = None) -> str:
    """The changelog's text from the tags, newest version first; raises `Unrenderable` when a
    version note cannot be read."""
    root = Path(root)
    problems: list[Problem] = []
    if store is None:
        store, errors = _vault(root)
        problems.extend(errors)
    try:
        tags = repo.tags(root)
    except repo.RepoError as error:
        problems.append(_repo_problem("docs/versions/", error))
        raise Unrenderable(_dedup(problems)) from error
    notes = {note.rel: note for note in store.notes()}
    ordered = sorted(tags, key=repo.version_key, reverse=True)
    out = ["# Changelog", ""]
    for tag in ordered:
        note = notes.get(f"docs/versions/{tag}.md")
        if note is None:
            continue
        if note.error:
            problems.append(Problem(note.rel, "cannot be read"))
            continue
        body = note.body
        out.append(f"## {vault.title(body)}")
        out.append("")
        try:
            date = repo.tag_date(root, tag)
        except repo.RepoError as error:
            problems.append(_repo_problem("docs/versions/", error))
            date = ""
        if date:
            out.append(date)
            out.append("")
        paragraph = vault.first_paragraph(body)
        if paragraph:
            out.append(paragraph)
            out.append("")
        bullets = vault.changelog_bullets(body)
        out.extend(bullets)
        if bullets:
            out.append("")
    if problems:
        raise Unrenderable(_dedup(problems))
    return "\n".join(out).rstrip("\n") + "\n"


def _tag_message(note: Note) -> str:
    """The note's first paragraph and changelog bullets, as the tag's annotated message."""
    body = note.body
    paragraph = vault.first_paragraph(body)
    bullets = vault.changelog_bullets(body)
    message = paragraph
    if bullets:
        message = (paragraph + "\n" if paragraph else "") + "\n".join(bullets)
    return message


def _emit(problems: list[Problem]) -> int:
    """Print one line per problem and return 1 when there is any, 0 when there is none."""
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def _usage() -> int:
    """Print the usage line on stderr and return 2."""
    print(USAGE, file=sys.stderr)
    return 2


def main(argv: list[str], root: Path | str | None = None) -> int:
    """Run `check`, `render` or `release <version>` and return the exit code."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    args = list(argv)
    if len(args) < 2 or not args[1].strip():
        return _usage()
    command = args[1].strip()
    if command == "check":
        return _emit(problems_check(root))
    if command == "next":
        if len(args) != 2:
            return _usage()
        import loop  # the gate's readers do not import their reader's reader

        sys.stdout.write(loop.render(loop.gather(root)))
        return 0
    if command == "numbers":
        import tally  # the numbers are their own reader, off the gate's path to a build

        found = tally.gather(root)
        if len(args) == 2:
            sys.stdout.write(tally.render(found))
            return 0
        if len(args) == 3 and args[2].strip():
            row = next((r for r in found.rows if r.version == args[2].strip()), None)
            if row is None:
                return _usage()
            sys.stdout.write(tally.render(tally.Tally(rows=(row,), unknown=())))
            return 0
        return _usage()
    if command == "render":
        try:
            text = render(root)
        except Unrenderable as error:
            return _emit(error.problems)
        (root / "CHANGELOG.md").write_text(text, encoding="utf-8")
        return 0
    if command == "release":
        if len(args) < 3 or not args[2].strip():
            return _usage()
        version = args[2].strip()
        store, errors = _vault(root)
        problems: list[Problem] = list(errors)
        problems.extend(problems_check(root, store))
        if not problems:
            problems = _release_problems(root, version, store)
        if problems:
            return _emit(problems)
        note = _version_note(store, version)
        done = repo.tag(root, version, _tag_message(note))
        if done.code != 0:
            return _emit(
                [Problem(f"docs/versions/{version}.md", f"git tag -a {version} failed: {done.err}")]
            )
        wheel, said = repo.build_wheel(root)
        if not wheel:  # the tag stands and nothing is rendered: a tag is not a deployment
            return _emit(
                [Problem(f"docs/versions/{version}.md", f"uv build --wheel failed: {said}")]
            )
        try:
            text = render(root, store)
        except Unrenderable as error:  # the tag stands, as after a failed wheel
            return _emit(error.problems)
        (root / "CHANGELOG.md").write_text(text, encoding="utf-8")
        print(wheel)
        return 0
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
