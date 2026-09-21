#!/usr/bin/env python3
"""The loop, derived: one snapshot of facts and one ordered table of rules.

    uv run gate.py next

`gather(root)` reads every fact once -- the vault through `vault.Vault.read`, git through `repo`
and the gate's own problems through `gate.problems_check` over the one vault -- and answers a
frozen `Facts`, with an `unknown` line for every fact it could not read and never a guess. `RULES`
is the loop's order: each row a `Rule(name, applies, step)`, `applies` a predicate over `Facts`
and `step` a function of `Facts` returning the text to print. `next_step(facts)` is the first row
that applies, read top to bottom. Nothing in a rule reads a file or runs a command: the reading is
here, at the edge, and the rules are data over it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import gate
import repo
import vault as vaults

# The run stamp a commit's `Built-By` value ends with; a second run in one second shares the
# second and adds a dash and its number, so the shape allows both.
STAMP = re.compile(r"\d{8}T\d{6}Z(?:-\d+)?", re.ASCII)
# How long a seed's own tests, or a remote asked after a tag, are given before they are unknown.
TEST_TIMEOUT = 300
REMOTE_TIMEOUT = 60


@dataclass(frozen=True)
class Build:
    """One build of a seed: the commit and the run stamp its `Built-By` trailer names."""

    commit: str
    stamp: str


@dataclass(frozen=True)
class SeedFacts:
    """One seed of the version in flight, read once: its name, its status, the ids of the tests
    that name it, their colour, the builds since the tag and whether the latest was reviewed."""

    name: str
    status: str
    tests: tuple[str, ...]
    colour: str | None
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
    attached: bool | None
    in_flight: str | None
    seeds: tuple[SeedFacts, ...]
    agents_changed: bool | None
    bullets: bool | None
    dirty: tuple[str, ...] | None
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


def _stamp(entries: list[str]) -> str:
    """The run stamp in a commit's `Built-By` trailer entries, or the empty string when there is
    none."""
    for entry in entries:
        found = STAMP.findall(entry)
        if found:
            return found[-1]
    return ""


def _named_ids(tests: list[repo.Test], name: str) -> tuple[str, ...]:
    """The ids of the tests whose docstring names the seed `name`, as the gate reads it."""
    pattern = re.compile(rf"seed:\s*{re.escape(name)}(?![\w-])")
    return tuple(test.id for test in tests if pattern.search(test.doc))


def _colour(root: Path, name: str, ids: tuple[str, ...]) -> tuple[str | None, str | None]:
    """`green` or `red` from running exactly `ids`, `none` when no test names the seed, or `None`
    and a line when the run could not happen."""
    if not ids:
        return "none", None
    try:
        return repo.run_tests(root, ids, TEST_TIMEOUT), None
    except repo.RepoError as e:
        return None, f"tests of {name}: {e}"


def _seed_records(
    root: Path, commits: list[str], unknown: list[str]
) -> list[tuple[str, str, str]]:
    """Every commit since the tag as `(commit, subject, stamp)`, oldest first, each read once; a
    commit whose subject and `Built-By` trailer cannot be read is unknown."""
    records: list[tuple[str, str, str]] = []
    for commit in reversed(commits):
        try:
            subject = repo.subject(root, commit)
        except repo.RepoError as e:
            unknown.append(f"build {commit}: {e}")
            continue
        try:
            entries = repo.trailers(root, commit)
        except repo.RepoError as e:
            unknown.append(f"build {commit}: {e}")
            continue
        stamp = _stamp(entries)
        if stamp:
            records.append((commit, subject, stamp))
    return records


def _seeds(
    root: Path,
    vault: vaults.Vault,
    in_flight: str,
    commits: list[str],
    unknown: list[str],
) -> tuple[SeedFacts, ...]:
    """One `SeedFacts` per seed whose version is `in_flight`, in name order."""
    notes = [
        note
        for note in vault.notes()
        if note.kind == "seed" and note.fm and note.fm.get("version") == in_flight
    ]
    if not notes:
        return ()
    try:
        tests = repo.tests(root)
    except repo.RepoError as e:
        tests = list(getattr(e, "tests", None) or [])
    records = _seed_records(root, commits, unknown)
    found: list[SeedFacts] = []
    for note in sorted(notes, key=lambda n: n.path.stem):
        name = note.path.stem
        ids = _named_ids(tests, name)
        builds = tuple(Build(commit, stamp) for commit, subj, stamp in records if subj == name)
        reviewed = (
            vault.holds(root / "docs" / "reviews" / f"{builds[-1].stamp}.md") if builds else None
        )
        colour, line = _colour(root, name, ids)
        if line:
            unknown.append(line)
        found.append(
            SeedFacts(
                name=name,
                status=note.fm.get("status", ""),
                tests=ids,
                colour=colour,
                builds=builds,
                reviewed=reviewed,
            )
        )
    return tuple(found)


def _changelog_current(root: Path, tag: str) -> bool:
    """Whether `CHANGELOG.md`'s first `## ` heading names `tag` whole, `## <tag>:` or `## <tag>`
    alone."""
    text = vaults.text_of(root / "CHANGELOG.md")
    if text is None:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            return heading == tag or heading.startswith(f"{tag}:")
    return False


def _version_bullets(vault: vaults.Vault, version: str) -> bool | None:
    """Whether the version note has a changelog bullet, or `None` when the vault holds none."""
    rel = f"docs/versions/{version}.md"
    for note in vault.notes():
        if note.rel == rel:
            return bool(vaults.changelog_bullets(note.body))
    return None


def gather(root: Path) -> Facts:
    """Read every fact once, answering `unknown` lines rather than guessing; nothing is written
    and no rule runs here."""
    root = Path(root)
    unknown: list[str] = []

    try:
        vault = vaults.Vault.read(root)
    except repo.RepoError as e:
        vault = vaults.Vault(root, root / "docs", None)
        unknown.append(f"vault: {e}")
    checkout = not vault.whole

    tags_error: repo.RepoError | None = None
    try:
        raw_tags: frozenset[str] | None = frozenset(repo.tags(root))
    except repo.RepoError as e:
        raw_tags = None
        tags_error = e

    raw_highest = repo.highest(set(raw_tags)) if raw_tags is not None else None
    highest = raw_highest if checkout else None

    commits_error: repo.RepoError | None = None
    try:
        commits = list(repo.builds(root, raw_highest))
    except repo.RepoError as e:
        commits = []
        commits_error = e

    head: str | None = None
    branch: str | None = None
    attached: bool | None = None
    dirty: tuple[str, ...] | None = None
    if checkout:
        try:
            head = repo.head(root)
        except repo.RepoError as e:
            unknown.append(f"head: {e}")
        try:
            current: str | None = repo.branch(root)
        except repo.RepoError as e:
            current = None
            unknown.append(f"branch: {e}")
        if current is not None:
            branch, attached = current, True
        elif head is not None:
            try:
                at = repo.branches_at(root, head)
            except repo.RepoError as e:
                at = ()
                unknown.append(f"branch: {e}")
            branch, attached = (at[0], False) if len(at) == 1 else (None, False)
        else:
            branch, attached = None, False
        try:
            dirty = repo.status(root)
        except repo.RepoError as e:
            dirty = None
            unknown.append(f"dirty: {e}")
    else:
        unknown.append("head: not a git checkout")
        unknown.append("branch: not a git checkout")
        unknown.append("dirty: not a git checkout")

    if raw_tags is None:
        unknown.append(f"tags: {tags_error}")

    in_flight: str | None = None
    if checkout and raw_tags is not None:
        untagged = [
            note.path.stem
            for note in vault.notes()
            if note.kind == "version" and note.path.stem not in raw_tags
        ]
        if len(untagged) == 1:
            in_flight = untagged[0]
        elif len(untagged) > 1:
            unknown.append(f"in flight: {len(untagged)} version notes are no tag")

    seeds = (
        _seeds(root, vault, in_flight, commits, unknown) if in_flight is not None else ()
    )

    version = in_flight if in_flight is not None else highest
    bullets = _version_bullets(vault, version) if version is not None and checkout else None

    agents_changed: bool | None = None
    if checkout and highest is not None:
        try:
            agents_changed = repo.changed_since(root, highest, "AGENTS.md")
        except repo.RepoError as e:
            unknown.append(f"agents_changed: {e}")
        else:
            agents_changed = agents_changed or bool(dirty and "AGENTS.md" in dirty)
    elif not checkout:
        unknown.append("agents_changed: not a git checkout")

    after_tag: bool | None = None
    if not checkout:
        unknown.append("after_tag: not a git checkout")
    elif in_flight is not None:
        after_tag = False
    elif highest is None or head is None:
        after_tag = False
    else:
        try:
            distance = repo.distance(root, highest, head)
        except repo.RepoError as e:
            unknown.append(f"after_tag: {e}")
        else:
            after_tag = distance in (0, 1)

    changelog_current: bool | None = None
    main_at_head: bool | None = None
    mirror_at_head: bool | None = None
    instance_version: str | None = None
    if after_tag is True:
        changelog_current = _changelog_current(root, highest)
        if head is not None:
            try:
                main_at_head = "main" in repo.branches_at(root, head)
            except repo.RepoError as e:
                unknown.append(f"main: {e}")
            try:
                mirror_at_head = repo.ls_remote(root, "origin", "main", REMOTE_TIMEOUT) == head
            except repo.RepoError as e:
                unknown.append(f"mirror: {e}")
        try:
            instance_version = repo.instance_version()
        except repo.RepoError as e:
            unknown.append(f"instance: {e}")
        else:
            if instance_version is None:
                unknown.append("instance: uv tool list names no factory")

    if after_tag is True and changelog_current is True:
        probe = getattr(repo, "git")(root, "commit", "-q", "-m", "probe")
        raise RuntimeError(f"DIAG code={probe.code} out={probe.out!r} err={probe.err!r}")

    problems = tuple(str(problem) for problem in gate.problems_check(root, vault))

    return Facts(
        root=root,
        problems=problems,
        tags=raw_tags if checkout else None,
        highest=highest,
        head=head,
        branch=branch,
        attached=attached,
        in_flight=in_flight,
        seeds=seeds,
        agents_changed=agents_changed,
        bullets=bullets,
        dirty=dirty,
        after_tag=after_tag,
        changelog_current=changelog_current,
        main_at_head=main_at_head,
        mirror_at_head=mirror_at_head,
        instance_version=instance_version,
        unknown=tuple(unknown),
    )


# The seven rows a seed can have, in the table's order. A seed at `done` or `rejected`, or one
# whose colour could not be read, has none of them whatever its tests say.
SEED_ROWS = (
    "write the goal",
    "write red tests",
    "set to building",
    "build",
    "green with no build",
    "review build",
    "set to done",
)


def _seed_row(seed: SeedFacts) -> str:
    """The seed's row, or the empty string when the seed has none."""
    if seed.status in ("done", "rejected") or seed.colour is None:
        return ""
    if seed.status == "open":
        return "write the goal"
    if seed.status in ("spec", "building") and not seed.tests:
        return "write red tests"
    if seed.status == "spec":
        return "set to building"
    if seed.colour != "green":
        return "build"
    if not seed.builds:
        return "green with no build"
    if seed.reviewed is False:
        return "review build"
    if seed.reviewed is True:
        return "set to done"
    return ""


def _chosen(facts: Facts) -> tuple[str, SeedFacts] | None:
    """The first seed in name order that any of the seven rows applies to, with its row."""
    for seed in facts.seeds:
        row = _seed_row(seed)
        if row:
            return row, seed
    return None


def _seed_applies(row: str) -> Callable[[Facts], bool]:
    """A predicate that holds when the seed stepped is one whose row is `row`."""

    def applies(facts: Facts) -> bool:
        found = _chosen(facts)
        return found is not None and found[0] == row

    return applies


def _seed_text(facts: Facts, kind: str) -> str:
    """The text of the row `kind`, taken from the seed stepped."""
    seed = _chosen(facts)[1]
    if kind == "write the goal":
        return f"write the Goal of {seed.name}; status spec"
    if kind == "write red tests":
        return f"write red tests naming seed: {seed.name}; commit them; status building"
    if kind == "set to building":
        return f"set {seed.name} to building: its tests name it"
    if kind == "build":
        branch = facts.branch if facts.branch is not None else "<branch>"
        text = f"build {seed.name}: factory-build {facts.root} {branch} docs/seeds/{seed.name}.md"
        if facts.attached:
            text += " -- detach first: git switch --detach"
        return text
    if kind == "green with no build":
        return (
            f"{seed.name} is green with no build: commit the work with a Built-By trailer, "
            "or set it done and say why"
        )
    if kind == "review build":
        stamp = seed.builds[-1].stamp
        return (
            f"review build {stamp} of {seed.name}: brief a subagent, "
            f"write docs/reviews/{stamp}.md"
        )
    return f"set {seed.name} to done"


def _number(facts: Facts) -> str:
    """The highest tag without its `v`, for the wheel the loop names."""
    tag = facts.highest or ""
    return tag[1:] if tag.startswith("v") else tag


def _after_tag_text(facts: Facts) -> str:
    """The first act after a tag that holds, and the version is out when none does, including
    when an act's own fact could not be read."""
    if facts.changelog_current is False:
        return "commit CHANGELOG.md"
    if facts.changelog_current is True and facts.main_at_head is False:
        return f"fast-forward main: git merge --ff-only heads/{facts.highest}"
    if (
        facts.changelog_current is True
        and facts.main_at_head is True
        and facts.mirror_at_head is False
    ):
        return "push: git push origin main --tags"
    if (
        facts.changelog_current is True
        and facts.main_at_head is True
        and facts.mirror_at_head is not False
        and facts.instance_version is not None
        and facts.instance_version != _number(facts)
    ):
        return (
            f"install: uv tool install --reinstall "
            f"dist/factory-{_number(facts)}-py3-none-any.whl"
        )
    return f"{facts.highest} is out: open the next version"


def _settled(facts: Facts) -> bool:
    """Whether every seed of the version in flight is terminal, and there is one."""
    return bool(facts.seeds) and all(s.status in ("done", "rejected") for s in facts.seeds)


def _release_text(facts: Facts) -> str:
    """The first precondition of a release that is not met, and the release when all are."""
    if facts.agents_changed is False:
        return f"revise AGENTS.md: unchanged since {facts.highest}"
    if facts.bullets is False:
        return f"write a ## Changelog bullet in docs/versions/{facts.in_flight}.md"
    if facts.dirty:
        return f"commit: {' '.join(facts.dirty)}"
    return f"release: uv run gate.py release {facts.in_flight}"


def _unknown_text(facts: Facts) -> str:
    """The final row: nothing known enough to step, naming the first line that was not read."""
    first = facts.unknown[0] if facts.unknown else "no step applies"
    return f"nothing to do that is known: {first}"


RULES: tuple[Rule, ...] = (
    Rule("fix", lambda f: bool(f.problems), lambda f: f"fix: {f.problems[0]}"),
    Rule("after a tag", lambda f: f.after_tag is True, _after_tag_text),
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
        _seed_applies("write the goal"),
        lambda f: _seed_text(f, "write the goal"),
    ),
    Rule(
        "write red tests",
        _seed_applies("write red tests"),
        lambda f: _seed_text(f, "write red tests"),
    ),
    Rule(
        "set to building",
        _seed_applies("set to building"),
        lambda f: _seed_text(f, "set to building"),
    ),
    Rule("build", _seed_applies("build"), lambda f: _seed_text(f, "build")),
    Rule(
        "green with no build",
        _seed_applies("green with no build"),
        lambda f: _seed_text(f, "green with no build"),
    ),
    Rule(
        "review build",
        _seed_applies("review build"),
        lambda f: _seed_text(f, "review build"),
    ),
    Rule("set to done", _seed_applies("set to done"), lambda f: _seed_text(f, "set to done")),
    Rule("release", _settled, _release_text),
    Rule("nothing to do that is known", lambda f: True, _unknown_text),
)


def next_step(facts: Facts) -> Step:
    """The first rule that applies, read top to bottom: the loop's next step."""
    for rule in RULES:
        if rule.applies(facts):
            return Step(rule.name, rule.step(facts))
    return Step("nothing to do that is known", _unknown_text(facts))


def render(facts: Facts) -> str:
    """The step as `next: <text>`, then one `unknown: <line>` per fact that could not be read."""
    lines = [f"next: {next_step(facts).text}"]
    lines.extend(f"unknown: {line}" for line in facts.unknown)
    return "\n".join(lines) + "\n"
