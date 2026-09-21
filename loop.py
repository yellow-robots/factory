#!/usr/bin/env python3
"""The loop, derived: one snapshot of facts and one ordered table of rules.

    uv run gate.py next

`gather(root)` reads every fact once -- the vault through `vault.Vault.read`, git through `repo`
and the gate's own problems through `gate.problems_check` -- and answers a frozen `Facts`, with an
`unknown` line for every fact it could not read and never a guess. `RULES` is the loop's order:
each row a `Rule(name, applies, step)`, `applies` a predicate over `Facts` and `step` a function
returning the text to print. `next_step(facts)` is the first row that applies. Nothing in a rule
reads a file or runs a command: the reading is here, at the edge, and the rules are data over it.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import builder
import gate
import repo
import vault as vaults

# A commit's `Built-By` value ends `run <stamp>`; the stamp is the builder's, a UTC second and,
# when a second run shares it, a dash and that run's number.
STAMP = re.compile(r"\d{8}T\d{6}Z(?:-\d+)?", re.ASCII)
SEED_IN_DOC = r"seed:\s*{}(?![\w-])"


@dataclass(frozen=True)
class Build:
    """One build of a seed: the commit and the run stamp its `Built-By` trailer names."""

    commit: str
    stamp: str


@dataclass(frozen=True)
class SeedFacts:
    """One seed of the version in flight, read once."""

    name: str
    status: str
    has_goal: bool
    tests: tuple[str, ...]
    colour: str
    builds: tuple[Build, ...]
    reviewed: bool | None


@dataclass(frozen=True)
class Facts:
    """The loop's one snapshot: every field read once by `gather`, `None` where it could not be."""

    root: Path
    problems: tuple[str, ...]
    tags: frozenset[str] | None
    highest: str | None
    head: str | None
    branch: str | None
    in_flight: str | None
    seeds: tuple[SeedFacts, ...]
    agents_changed: bool | None
    bullets: bool | None
    dirty: tuple[str, ...]
    after_tag: bool | None
    changelog_current: bool | None
    main_at_head: bool | None
    mirror_at_head: bool | None
    instance_version: str | None
    unknown: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    """The step a rule answers with: the rule's name and the text to print."""

    name: str
    text: str


@dataclass(frozen=True)
class Rule:
    """One row of the loop: its name, its predicate over `Facts` and the text it prints."""

    name: str
    applies: Callable[[Facts], bool]
    step: Callable[[Facts], str]


def _read(path: Path) -> str:
    """The file's text with what cannot be decoded replaced, or the empty string when unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _named_tests(root: Path) -> list[tuple[str, str]]:
    """Every test method or class of each `test*.py` at the root as `(id, docstring)`, the id
    `module.Class.method` or `module.Class`; a file that cannot be read or does not parse is left
    for the gate's own problem and answers nothing here."""
    found: list[tuple[str, str]] = []
    for path in sorted(root.glob("test*.py")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        _walk_tests(tree, path.stem, [], found)
    return found


def _walk_tests(node, module: str, classes: list[str], found: list[tuple[str, str]]) -> None:
    """Walk one node's children, qualifying each test class and method with its module and class."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            doc = ast.get_docstring(child)
            if doc:
                found.append((".".join([module, *classes, child.name]), doc))
            _walk_tests(child, module, [*classes, child.name], found)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith(
            "test"
        ):
            doc = ast.get_docstring(child)
            if doc:
                found.append((".".join([module, *classes, child.name]), doc))
            _walk_tests(child, module, classes, found)


def _names_seed(doc: str, name: str) -> bool:
    """Whether a docstring names the seed `name`, as the gate reads it."""
    return bool(re.compile(SEED_IN_DOC.format(re.escape(name))).search(doc))


def _colour(root: Path, ids: tuple[str, ...]) -> str:
    """`green`, `red` or `none`: the seed's own tests run in the root, alone, or none naming it."""
    if not ids:
        return "none"
    try:
        done = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", *ids],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return "none"
    return "green" if done.returncode == 0 else "red"


def _has_goal(body: str) -> bool:
    """Whether the seed's `## Goal` has text, read as the builder reads it."""
    try:
        text = builder.goal_section(builder.note_text(body))
    except ValueError:
        return False
    return bool(text)


def _stamp(entries: list[str]) -> str:
    """The run stamp in a commit's `Built-By` trailer entries, or the empty string when there is
    none."""
    for entry in entries:
        found = STAMP.findall(entry)
        if found:
            return found[-1]
    return ""


def gather(root: Path) -> Facts:
    """Read every fact once through the gate's readers, answering `unknown` lines rather than
    guessing. Nothing is written and no rule runs here."""
    root = Path(root)
    unknown: list[str] = []

    problems = tuple(str(problem) for problem in gate.problems_check(root))

    try:
        tags: frozenset[str] | None = frozenset(repo.tags(root))
    except repo.RepoError as e:
        tags = None
        unknown.append(f"tags: {e}")
    highest = repo.highest(set(tags)) if tags is not None else None

    done = repo.git(root, "rev-parse", "HEAD")
    if done.code == 0 and done.out.strip():
        head: str | None = done.out.strip()
    else:
        head = None
        unknown.append(f"head: git rev-parse HEAD failed: {' '.join(done.err.split())}")

    done = repo.git(root, "branch", "--show-current")
    branch: str | None = done.out.strip() if done.code == 0 else None

    try:
        vault = vaults.Vault.read(root)
    except repo.RepoError as e:
        vault = None
        unknown.append(f"vault: {e}")

    in_flight: str | None = None
    if vault is not None:
        untagged = [
            note.path.stem
            for note in vault.notes()
            if note.kind == "version" and (tags is None or note.path.stem not in tags)
        ]
        if len(untagged) == 1:
            in_flight = untagged[0]
        elif len(untagged) > 1:
            unknown.append(f"in flight: {len(untagged)} version notes are no tag")

    seeds: list[SeedFacts] = []
    if vault is not None and in_flight is not None:
        tests = _named_tests(root)
        for note in vault.notes():
            if note.kind != "seed" or not note.fm or note.fm.get("version") != in_flight:
                continue
            name = note.path.stem
            ids = tuple(qual for qual, doc in tests if _names_seed(doc, name))
            builds = _seed_builds(root, highest, name, unknown)
            reviewed = None
            if builds:
                reviewed = (root / "docs" / "reviews" / f"{builds[-1].stamp}.md").is_file()
            seeds.append(
                SeedFacts(
                    name=name,
                    status=note.fm.get("status", ""),
                    has_goal=_has_goal(note.body),
                    tests=ids,
                    colour=_colour(root, ids),
                    builds=builds,
                    reviewed=reviewed,
                )
            )

    if highest is not None:
        done = repo.git(root, "diff", "--name-only", highest, "--", "AGENTS.md")
        agents_changed: bool | None = bool(done.out.strip()) if done.code == 0 else None
    else:
        agents_changed = None

    bullets: bool | None = None
    version = in_flight if in_flight is not None else highest
    if version is not None:
        body = vaults.frontmatter(_read(root / "docs" / "versions" / f"{version}.md"))[1]
        bullets = bool(vaults.changelog_bullets(body))

    dirty: list[str] = []
    done = repo.git(root, "status", "--porcelain")
    if done.code == 0:
        for line in done.out.splitlines():
            if not line.strip():
                continue
            dirty.append(line[3:].strip() if len(line) > 3 else line.strip())

    after_tag = False
    if in_flight is None and highest is not None and head is not None:
        tagged = repo.git(root, "rev-parse", f"{highest}^{{commit}}")
        if tagged.code == 0 and tagged.out.strip():
            commit = tagged.out.strip()
            if commit == head:
                after_tag = True
            else:
                parent = repo.git(root, "rev-parse", "HEAD~1")
                after_tag = parent.code == 0 and parent.out.strip() == commit

    changelog_current: bool | None = None
    if highest is not None:
        changelog_current = False
        for line in _read(root / "CHANGELOG.md").splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                changelog_current = highest in stripped
                break

    main_at_head: bool | None = None
    if head is not None:
        done = repo.git(root, "rev-parse", "--verify", "refs/heads/main")
        main_at_head = done.code == 0 and done.out.strip() == head

    done = repo.git(root, "ls-remote", "origin", "main")
    if done.code != 0:
        mirror_at_head: bool | None = None
        unknown.append(f"mirror: git ls-remote origin main failed: {' '.join(done.err.split())}")
    else:
        mirror_at_head = bool(head) and any(
            line.split()[0] == head for line in done.out.splitlines() if line.split()
        )

    instance_version = _instance(unknown)

    return Facts(
        root=root,
        problems=problems,
        tags=tags,
        highest=highest,
        head=head,
        branch=branch,
        in_flight=in_flight,
        seeds=tuple(seeds),
        agents_changed=agents_changed,
        bullets=bullets,
        dirty=tuple(dirty),
        after_tag=after_tag,
        changelog_current=changelog_current,
        main_at_head=main_at_head,
        mirror_at_head=mirror_at_head,
        instance_version=instance_version,
        unknown=tuple(unknown),
    )


def _seed_builds(
    root: Path, highest: str | None, name: str, unknown: list[str]
) -> tuple[Build, ...]:
    """One `Build` per commit since the highest tag whose message's first line is the seed's name,
    the stamp from its `Built-By` trailer, oldest first."""
    try:
        commits = repo.builds(root, highest)
    except repo.RepoError as e:
        unknown.append(f"builds of {name}: {e}")
        return ()
    builds: list[Build] = []
    for commit in reversed(commits):
        done = repo.git(root, "log", "-1", "--format=%s", commit, "--")
        if done.code != 0 or done.out.strip() != name:
            continue
        try:
            entries = repo.trailers(root, commit)
        except repo.RepoError as e:
            unknown.append(f"build {commit}: {e}")
            continue
        builds.append(Build(commit, _stamp(entries)))
    return tuple(builds)


def _instance(unknown: list[str]) -> str | None:
    """The product's version from `uv tool list`, `v` stripped, or an unknown line."""
    try:
        done = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        unknown.append(f"instance: uv tool list failed: {' '.join(str(e).split())}")
        return None
    if done.returncode != 0:
        said = done.stderr.strip() or done.stdout.strip()
        unknown.append(f"instance: uv tool list failed: {' '.join(said.split())}")
        return None
    for line in done.stdout.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "factory":
            return words[1].removeprefix("v")
    unknown.append("instance: uv tool list names no factory")
    return None


def _pick(seeds: tuple[SeedFacts, ...], ok) -> SeedFacts | None:
    """The first seed, in name order, the predicate holds of, or None."""
    for seed in seeds:
        if ok(seed):
            return seed
    return None


def _at_open(seed: SeedFacts) -> bool:
    return seed.status == "open"


def _spec_untested(seed: SeedFacts) -> bool:
    return seed.status == "spec" and not seed.tests


def _named_not_building(seed: SeedFacts) -> bool:
    return bool(seed.tests) and seed.status not in ("building", "done")


def _red(seed: SeedFacts) -> bool:
    return seed.colour == "red"


def _green_unbuilt(seed: SeedFacts) -> bool:
    return (
        seed.colour == "green"
        and not seed.builds
        and seed.status not in ("done", "rejected")
    )


def _green_unreviewed(seed: SeedFacts) -> bool:
    return (
        seed.colour == "green"
        and bool(seed.builds)
        and seed.reviewed is False
        and seed.status not in ("done", "rejected")
    )


def _green_reviewed(seed: SeedFacts) -> bool:
    return (
        seed.colour == "green"
        and bool(seed.builds)
        and seed.reviewed is True
        and seed.status not in ("done", "rejected")
    )


def _settled(facts: Facts) -> bool:
    return bool(facts.seeds) and all(s.status in ("done", "rejected") for s in facts.seeds)


def _number(facts: Facts) -> str:
    return (facts.highest or "").removeprefix("v")


def _after_ok(facts: Facts) -> bool:
    return (
        facts.after_tag is True
        and facts.changelog_current is True
        and facts.main_at_head is True
        and facts.mirror_at_head is not False
    )


def _install(facts: Facts) -> bool:
    return (
        _after_ok(facts)
        and facts.instance_version is not None
        and facts.instance_version != _number(facts)
    )


def _out(facts: Facts) -> bool:
    return (
        _after_ok(facts)
        and facts.instance_version is not None
        and facts.instance_version == _number(facts)
    )


RULES: tuple[Rule, ...] = (
    Rule(
        "fix",
        lambda f: bool(f.problems) and f.after_tag is not True,
        lambda f: f"fix: {f.problems[0]}",
    ),
    Rule(
        "commit changelog",
        lambda f: f.after_tag is True and f.changelog_current is False,
        lambda f: "commit CHANGELOG.md",
    ),
    Rule(
        "fast-forward main",
        lambda f: f.after_tag is True
        and f.changelog_current is True
        and f.main_at_head is False,
        lambda f: f"fast-forward main: git merge --ff-only heads/{f.highest}",
    ),
    Rule(
        "push",
        lambda f: f.after_tag is True
        and f.changelog_current is True
        and f.main_at_head is True
        and f.mirror_at_head is False,
        lambda f: "push: git push origin main --tags",
    ),
    Rule(
        "install",
        _install,
        lambda f: f"install: uv tool install --reinstall "
        f"dist/factory-{_number(f)}-py3-none-any.whl",
    ),
    Rule("out", _out, lambda f: f"{f.highest} is out: open the next version"),
    Rule(
        "open a version",
        lambda f: f.in_flight is None and f.after_tag is not True,
        lambda f: "open a version: write docs/versions/vX.md and set version: vX on a seed",
    ),
    Rule(
        "promote a seed",
        lambda f: f.in_flight is not None and not f.seeds,
        lambda f: f"promote a seed to {f.in_flight}",
    ),
    Rule(
        "write the goal",
        lambda f: _pick(f.seeds, _at_open) is not None,
        lambda f: f"write the Goal of {_pick(f.seeds, _at_open).name}; status spec",
    ),
    Rule(
        "write red tests",
        lambda f: _pick(f.seeds, _spec_untested) is not None,
        lambda f: f"write red tests naming seed: {_pick(f.seeds, _spec_untested).name}; "
        "commit them; status building",
    ),
    Rule(
        "set to building",
        lambda f: _pick(f.seeds, _named_not_building) is not None,
        lambda f: f"set {_pick(f.seeds, _named_not_building).name} to building: its tests name it",
    ),
    Rule(
        "build",
        lambda f: _pick(f.seeds, _red) is not None,
        lambda f: _build_text(f, _pick(f.seeds, _red)),
    ),
    Rule(
        "green with no build",
        lambda f: _pick(f.seeds, _green_unbuilt) is not None,
        lambda f: f"{_pick(f.seeds, _green_unbuilt).name} is green with no build: commit the work "
        "with a Built-By trailer, or set it done and say why",
    ),
    Rule(
        "review build",
        lambda f: _pick(f.seeds, _green_unreviewed) is not None,
        lambda f: _review_text(f, _pick(f.seeds, _green_unreviewed)),
    ),
    Rule(
        "set to done",
        lambda f: _pick(f.seeds, _green_reviewed) is not None,
        lambda f: f"set {_pick(f.seeds, _green_reviewed).name} to done",
    ),
    Rule(
        "revise AGENTS.md",
        lambda f: _settled(f) and f.agents_changed is False,
        lambda f: f"revise AGENTS.md: unchanged since {f.highest}",
    ),
    Rule(
        "changelog bullet",
        lambda f: _settled(f) and f.bullets is False,
        lambda f: f"write a ## Changelog bullet in docs/versions/{f.in_flight}.md",
    ),
    Rule(
        "commit",
        lambda f: _settled(f) and bool(f.dirty),
        lambda f: f"commit: {' '.join(f.dirty)}",
    ),
    Rule(
        "release",
        _settled,
        lambda f: f"release: uv run gate.py release {f.in_flight}",
    ),
    Rule("wait", lambda f: True, lambda f: "wait: some fact could not be read; read the unknowns"),
)


def _build_text(facts: Facts, seed: SeedFacts) -> str:
    """The build step for a red seed, with the detach when the branch is checked out."""
    text = (
        f"build {seed.name}: factory-build {facts.root} {facts.in_flight} "
        f"docs/seeds/{seed.name}.md"
    )
    if facts.branch is not None:
        text += " -- detach first: git switch --detach"
    return text


def _review_text(facts: Facts, seed: SeedFacts) -> str:
    """The review step for a green, built, unreviewed seed: the latest build's stamp."""
    stamp = seed.builds[-1].stamp
    return f"review build {stamp} of {seed.name}: brief a subagent, write docs/reviews/{stamp}.md"


def next_step(facts: Facts) -> Step:
    """The first rule that applies, read top to bottom: the loop's next step."""
    for rule in RULES:
        if rule.applies(facts):
            return Step(rule.name, rule.step(facts))
    return Step("wait", "wait: no step applies")


def render(facts: Facts) -> str:
    """The step as `next: <text>`, then one `unknown: <line>` per fact that could not be read."""
    lines = [f"next: {next_step(facts).text}"]
    lines.extend(f"unknown: {line}" for line in facts.unknown)
    return "\n".join(lines) + "\n"
