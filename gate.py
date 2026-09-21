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
import vault as vaults

USAGE = "usage: gate.py check|render|release <version>"
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
TRAILERS_FORMAT = repo.TRAILERS_FORMAT


@dataclass(frozen=True)
class Problem:
    """One problem of the gate: the path it names and what is wrong with it."""

    path: str
    message: str

    def __str__(self) -> str:
        """The problem as one printed line, `path: message`."""
        return f"{self.path}: {self.message}"


def _read(path: Path) -> str:
    """The file's text with what cannot be decoded replaced, or the empty string when it cannot
    be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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
    words."""
    return Problem(path, f"{error.command} failed: {error.err}")


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


def _read_vault(root: Path, problems: list[Problem]) -> vaults.Vault:
    """The vault at `root`, with a listing git could not answer for one problem naming it."""
    try:
        return vaults.Vault.read(root)
    except repo.RepoError as e:
        problems.append(_repo_problem("docs/", e))
        return vaults.Vault(root, root / "docs", None)


def _field_sets(vault: vaults.Vault):
    """A reader of the templates' field sets, each kind read from its template once."""
    cache: dict[str, set[str] | None] = {}

    def fields(kind: str) -> set[str] | None:
        """The field names of `kind`'s template, read once, or None when it cannot be read."""
        if kind not in cache:
            cache[kind] = vaults.template_fields(vault.docs, kind)
        return cache[kind]

    return fields


def _wikilink_problems(vault: vaults.Vault) -> list[Problem]:
    """Every wikilink of a note the vault holds that does not resolve."""
    problems: list[Problem] = []
    for path in sorted(vault.docs.rglob("*"), key=lambda p: str(p)):
        if not path.is_file() or not vault.holds(path):
            continue
        rel = path.relative_to(vault.root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            problems.append(Problem(rel, "cannot be read"))
            continue
        if "[[" not in text:
            continue
        for match in WIKILINK.finditer(text):
            target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            if not vault.resolves(target):
                problems.append(Problem(rel, f"wikilink {target} does not resolve"))
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
    """Whether a test's docstring names the seed `stem`."""
    pattern = re.compile(rf"seed:\s*{re.escape(stem)}(?![\w-])")
    return any(pattern.search(test.doc) for test in tests)


def _seed_problems(
    note: vaults.Note,
    vault: vaults.Vault,
    tags: set[str] | None,
    tests: list[repo.Test] | None,
    fields,
) -> list[Problem]:
    """A seed note: the template's fields, its status and the fields that status needs."""
    rel, fm, body = note.rel, note.fm, note.body
    seed_fields = fields("seed")
    if seed_fields is None:
        return [Problem("docs/templates/seed.md", "cannot be read")]
    problems: list[Problem] = []
    for field in sorted(set(fm) - seed_fields):
        problems.append(Problem(rel, f"seed has field {field}"))
    status = fm.get("status", "")
    if not status:
        return problems + [Problem(rel, "seed has no status")]
    if status not in STATUSES:
        return problems + [
            Problem(rel, f"status {status} is not one of {', '.join(STATUSES)}")
        ]
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
        note_path = vault.docs / "versions" / f"{version}.md"
        if not version:
            problems.append(Problem(rel, "seed has no version"))
        elif not note_path.is_file() or not vault.part(note_path):
            problems.append(
                Problem(rel, f"version {version} has no note docs/versions/{version}.md")
            )
        problems.extend(_goal_problems(rel, body))
    if tags is not None and version and version in tags and status not in ("done", "rejected"):
        problems.append(Problem(rel, f"version {version} is tagged but the seed is {status}"))
    if rank >= STATUSES.index("building") and tests is not None:
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
    rel: str, heading_title: str, judged: str, root: Path, test_names: set[str] | None
) -> list[Problem]:
    """Every `judged:` entry that does not name what exists, `none:` without a reason, or a line
    with nothing after it or an empty piece between commas."""
    if not judged.strip():
        return [Problem(rel, f"finding {heading_title} has no judged")]
    if judged.startswith("none:"):
        if not judged[len("none:"):].strip():
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
            if test_names is not None and name not in test_names:
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
    rel: str, heading_title: str, section: str, root: Path, test_names: set[str] | None
) -> list[Problem]:
    """A finding's `severity:`, `verified:` and `judged:` lines, read anywhere in its prose."""
    lines: dict[str, str] = {}
    for line in vaults.prose_lines(section):
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
    note: vaults.Note,
    vault: vaults.Vault,
    tests: list[repo.Test] | None,
    fields,
) -> list[Problem]:
    """A review note: the template's fields, a reviewer, a created date, the runs it reviewed and
    one of them naming it, then its findings with comments out."""
    rel, fm, body = note.rel, note.fm, note.body
    review_fields = fields("review")
    if review_fields is None:
        return [Problem("docs/templates/review.md", "cannot be read")]
    test_names = {test.name for test in tests} if tests is not None else None
    problems: list[Problem] = []
    for field in sorted(set(fm) - review_fields):
        problems.append(Problem(rel, f"review has field {field}"))
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
    for heading_title, section in vaults.review_findings(text):
        problems.extend(_finding_problems(rel, heading_title, section, vault.root, test_names))
    return problems


def _note_problems(
    vault: vaults.Vault,
    tags: set[str] | None,
    tests: list[repo.Test] | None,
    fields,
) -> tuple[list[Problem], list[vaults.Note]]:
    """Every problem of one note, and the version notes kept for the check over all of them."""
    problems: list[Problem] = []
    version_notes: list[vaults.Note] = []
    for note in vault.notes():
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
        template = vault.docs / "templates" / f"{kind}.md"
        if not template.is_file() or not vault.part(template):
            problems.append(
                Problem(note.rel, f"type {kind} has no template docs/templates/{kind}.md")
            )
            continue
        if kind == "seed":
            problems.extend(_seed_problems(note, vault, tags, tests, fields))
        elif kind == "version":
            version_notes.append(note)
        elif kind == "review":
            problems.extend(_review_problems(note, vault, tests, fields))
    return problems, version_notes


def _version_problems(
    version_notes: list[vaults.Note], tags: set[str] | None
) -> tuple[list[Problem], list[vaults.Note]]:
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
                Problem(note.rel, f"at most one version note may not be a tag ({len(untagged)} are)")
            )
    return problems, untagged


def _base_problems(vault: vaults.Vault, fields) -> list[Problem]:
    """The properties `docs/backlog.base` names that are not seed template fields."""
    base = vault.docs / "backlog.base"
    if not base.is_file() or not vault.part(base):
        return []
    template = vault.docs / "templates" / "seed.md"
    if not template.is_file() or not vault.part(template):
        # The missing template is reported once, elsewhere.
        return []
    seed_fields = fields("seed")
    if seed_fields is None:
        return []
    try:
        text = base.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [Problem("docs/backlog.base", "cannot be read")]
    problems: list[Problem] = []
    seen: set[str] = set()
    for kind, name in vaults.base_named(text):
        identifiers = vaults.plain_names(name) if kind == "name" else vaults.expression_names(name)
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
    except repo.RepoError as e:
        return [_repo_problem(rel_note, e)]
    done = repo.git(root, "log", "-1", "--format=%B", commit, "--")
    if done.code != 0:
        return [Problem(rel_note, f"git log -1 --format=%B failed for {short}")]
    message = done.out
    lines = [
        line[match.end():].strip(ASCII_WHITESPACE)
        for line in message.split("\n")
        if (match := BUILT_BY.match(line))
    ]
    if not lines:
        return []
    try:
        entries = repo.trailers(root, commit)
    except repo.RepoError:
        return [Problem(rel_note, f"git log -1 --format={TRAILERS_FORMAT} failed for {short}")]
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
        words = _ascii_words(value)
        stamp = words[-1] if len(words) >= 2 and words[-2] == "run" else ""
        if not STAMP_SHAPE.fullmatch(stamp):
            problems.append(Problem(rel_note, f"{short}: `Built-By: {text}` names no run"))
    return problems


def _build_problems(root: Path, rel_note: str, previous: str | None) -> list[Problem]:
    """Every problem of every build since the previous tag, each once, under the version's note
    (or `docs/versions/` when no version is in flight); a git command that fails while the builds
    are read is one problem naming the command."""
    try:
        commits = repo.builds(root, previous)
    except repo.RepoError as e:
        return [_repo_problem(rel_note, e)]
    problems: list[Problem] = []
    seen: set[str] = set()
    for commit in commits:
        for problem in _commit_build_problems(root, rel_note, commit):
            key = f"{problem.path}\0{problem.message}"
            if key in seen:
                continue
            seen.add(key)
            problems.append(problem)
    return problems


def problems_check(root: Path, vault: vaults.Vault | None = None) -> list[Problem]:
    """Every problem of the vault and the repository against it, each once."""
    root = Path(root)
    docs = root / "docs"
    if not docs.is_dir():
        return [Problem("docs/", "missing")]
    problems: list[Problem] = []
    if vault is None:
        vault = _read_vault(root, problems)
    try:
        tests = repo.tests(root)
    except repo.RepoError as e:
        problems.append(_repo_problem(e.command, e))
        tests = None
    try:
        tags = repo.tags(root)
    except repo.RepoError as e:
        problems.append(_repo_problem("docs/versions/", e))
        tags = None
    fields = _field_sets(vault)
    problems.extend(_wikilink_problems(vault))
    note_problems, version_notes = _note_problems(vault, tags, tests, fields)
    problems.extend(note_problems)
    version_problems, untagged = _version_problems(version_notes, tags)
    problems.extend(version_problems)
    in_flight = untagged[0].rel if len(untagged) == 1 else "docs/versions/"
    problems.extend(_base_problems(vault, fields))
    previous = repo.highest(tags) if tags is not None else None
    problems.extend(_build_problems(root, in_flight, previous))
    return _dedup(problems)


def _release_problems(root: Path, version: str, vault: vaults.Vault) -> list[Problem]:
    """Every problem a release of `version` has that check does not already report."""
    root = Path(root)
    docs = root / "docs"
    problems: list[Problem] = []
    rel_note = f"docs/versions/{version}.md"
    note = docs / "versions" / f"{version}.md"
    try:
        tags = repo.tags(root)
    except repo.RepoError as e:
        problems.append(_repo_problem("docs/versions/", e))
        tags = set()

    if not note.is_file():
        problems.append(Problem(rel_note, "no such version note"))
    if version in tags:
        problems.append(Problem(rel_note, f"{version} is already tagged"))

    for item in vault.notes():
        fm = item.fm
        if not fm or fm.get("type") != "seed" or fm.get("version") != version:
            continue
        if fm.get("status") not in ("done", "rejected"):
            problems.append(
                Problem(item.rel, f"seed of {version} is {fm.get('status') or 'unset'}")
            )

    body = vaults.frontmatter(_read(note))[1] if note.is_file() else ""
    if not vaults.changelog_bullets(body):
        problems.append(Problem(rel_note, "no ## Changelog bullets"))

    status = repo.git(root, "status", "--porcelain")
    for line in status.out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip() if len(line) > 3 else line.strip()
        # `dist/` is the release's own output only where git ignores it, as this repository does;
        # `git status` leaves an ignored path out already, so a path there in a repository that
        # does not ignore it is an uncommitted change like any other and the tree is not clean.
        problems.append(Problem(path, "uncommitted change"))

    previous = repo.highest(tags)
    if previous is not None:
        changed = repo.git(root, "diff", "--name-only", previous, "HEAD", "--", "AGENTS.md")
        if not changed.out.strip():
            problems.append(Problem("AGENTS.md", f"unchanged since {previous}"))

    result = repo.suite(root)
    if result == "red":
        problems.append(Problem("test", "the unittest suite is red"))
    elif result == "timed out":
        problems.append(Problem("test", "the unittest suite timed out"))
    elif result == "could not run":
        problems.append(Problem("test", "the unittest suite could not run"))
    return _dedup(problems)


def render(root: Path) -> str:
    """The changelog's text from the tags, newest version first, and writes nothing."""
    root = Path(root)
    docs = root / "docs"
    tags = repo.tags(root)
    ordered = sorted(tags, key=repo.version_key, reverse=True)
    out = ["# Changelog", ""]
    for tag in ordered:
        note = docs / "versions" / f"{tag}.md"
        if not note.is_file():
            continue
        body = vaults.frontmatter(_read(note))[1]
        out.append(f"## {vaults.title(body)}")
        out.append("")
        date = repo.tag_date(root, tag)
        if date:
            out.append(date)
            out.append("")
        paragraph = vaults.first_paragraph(body)
        if paragraph:
            out.append(paragraph)
            out.append("")
        bullets = vaults.changelog_bullets(body)
        out.extend(bullets)
        if bullets:
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _tag_message(note: Path) -> str:
    """The note's first paragraph and changelog bullets, as the tag's annotated message."""
    body = vaults.frontmatter(_read(note))[1]
    paragraph = vaults.first_paragraph(body)
    bullets = vaults.changelog_bullets(body)
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
    if command == "render":
        try:
            text = render(root)
        except repo.RepoError as e:
            return _emit([_repo_problem("docs/versions/", e)])
        (root / "CHANGELOG.md").write_text(text, encoding="utf-8")
        return 0
    if command == "release":
        if len(args) < 3 or not args[2].strip():
            return _usage()
        version = args[2].strip()
        problems: list[Problem] = []
        vault = _read_vault(root, problems)
        problems.extend(problems_check(root, vault))
        if not problems:
            problems = _release_problems(root, version, vault)
        if problems:
            return _emit(problems)
        note = root / "docs" / "versions" / f"{version}.md"
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
        (root / "CHANGELOG.md").write_text(render(root), encoding="utf-8")
        print(wheel)
        return 0
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
