#!/usr/bin/env python3
"""The loop, derived: one snapshot of facts and one ordered table of rules.

    uv run gate.py next

`gather(root)` reads every fact once -- the vault through `vault`, git through `repo` and the
installed product through `host` -- and answers a frozen `Facts`, `None` and an `unknown` line
for every fact it could not read and never a guess. `RULES` is the loop's order: each row a
`Rule(name, applies, step)`, `applies` a predicate over `Facts` and `step` a function of `Facts`
returning the text to print. `next_step(facts)` is the first row that applies, read top to
bottom. Nothing in a rule reads a file or runs a command: the reading is here, at the edge, and
the rules are data over it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import gate
import host
import repo
import vault as vaults

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
    builds: tuple[Build, ...] | None
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


def _read_vault(root: Path) -> tuple[vaults.Vault, repo.RepoError | None]:
    """The vault `root` holds, and the listing error a checkout may hide: a failure inside a
    checkout is no checkout and the other facts are still read."""
    try:
        return vaults.Vault.read(root), None
    except repo.RepoError as e:
        return vaults.Vault(root, root / "docs", None), e


def _branch_and_attached(
    root: Path, head: str | None, unknown: list[str]
) -> tuple[str | None, bool | None]:
    """The branch at the head and whether it is attached, with a line when it cannot be told."""
    try:
        current = repo.branch(root)
    except repo.RepoError as e:
        unknown.append(f"branch: {e}")
        unknown.append(f"attached: {e}")
        return None, None
    if current is not None:
        return current, True
    if head is None:
        unknown.append("branch: the head is unknown")
        unknown.append("attached: the head is unknown")
        return None, None
    try:
        at = repo.branches_at(root, head)
    except repo.RepoError as e:
        unknown.append(f"branch: {e}")
        unknown.append(f"attached: {e}")
        return None, None
    if len(at) == 1:
        return at[0], False
    unknown.append(f"branch: {len(at)} branches at the head: {', '.join(at)}")
    return None, False


def _innermost_seed(
    test: repo.Test, by_id: dict[str, repo.Test], seed_names: list[str]
) -> str | None:
    """The name of the innermost docstring of `test` that names a seed, or None."""
    docs = [test.doc]
    parent = test.id.rsplit(".", 1)[0]
    while parent in by_id:
        docs.append(by_id[parent].doc)
        parent = parent.rsplit(".", 1)[0]
    for doc in docs:
        for name in seed_names:
            if vaults.names_seed(doc, name):
                return name
    return None


def _seed_test_ids(found: list[repo.Test], seed_names: list[str]) -> dict[str, list[str]]:
    """The ids of the tests of each seed: a test's seed is the innermost docstring that names
    one, a class id is never run whole, and a method naming its own seed is that seed's."""
    class_ids = {t.id for t in found if any(o.id.startswith(t.id + ".") for o in found)}
    by_id = {t.id: t for t in found}
    belonging: dict[str, list[str]] = {name: [] for name in seed_names}
    for test in found:
        if test.id in class_ids:
            continue
        name = _innermost_seed(test, by_id, seed_names)
        if name is not None:
            belonging[name].append(test.id)
    return belonging


def _run_stamp(entries: list[str]) -> str | None:
    """The run stamp a commit's `Built-By` trailer entries name, or None."""
    for entry in entries:
        stamp = repo.run_stamp(entry)
        if stamp is not None:
            return stamp
    return None


def _build_records(
    root: Path, highest: str | None
) -> tuple[list[tuple[str, str, str]], repo.RepoError | None]:
    """Every commit since `highest` as `(commit, subject, stamp)`, oldest first, or the error
    that kept the commits from being read at all."""
    try:
        commits = repo.builds(root, highest)
    except repo.RepoError as e:
        return [], e
    records: list[tuple[str, str, str]] = []
    try:
        for commit in reversed(commits):
            subject = repo.subject(root, commit)
            stamp = _run_stamp(repo.trailers(root, commit))
            if stamp is not None:
                records.append((commit, subject, stamp))
    except repo.RepoError as e:
        return [], e
    return records, None


def _colour(
    root: Path, name: str, ids: tuple[str, ...], status: str, unknown: list[str]
) -> str | None:
    """`green` or `red` from running exactly `ids`, `none` when no test names the seed, `None`
    with a line when the run could not happen, and no run at all for a terminal seed."""
    if status in ("done", "rejected"):
        return None
    if not ids:
        return "none"
    try:
        return repo.run_tests(root, ids, TEST_TIMEOUT)
    except repo.RepoError as e:
        unknown.append(f"tests of {name}: {e}")
        return None


def _seeds(
    root: Path, store: vaults.Vault, in_flight: str, highest: str | None, unknown: list[str]
) -> tuple[SeedFacts, ...]:
    """One `SeedFacts` per seed whose version is `in_flight`, in name order."""
    notes = [
        note
        for note in store.notes()
        if note.kind == "seed" and note.fm and note.fm.get("version") == in_flight
    ]
    if not notes:
        return ()
    try:
        found = list(repo.tests(root).found)
    except repo.RepoError as e:
        found = []
        unknown.append(f"tests: {e}")
    seed_names = [note.path.stem for note in store.notes() if note.kind == "seed"]
    belonging = _seed_test_ids(found, seed_names)
    records, builds_error = _build_records(root, highest)
    seeds: list[SeedFacts] = []
    for note in sorted(notes, key=lambda note: note.path.stem):
        name = note.path.stem
        ids = tuple(belonging.get(name, ()))
        if builds_error is not None:
            builds: tuple[Build, ...] | None = None
            unknown.append(f"builds of {name}: {builds_error}")
        else:
            builds = tuple(
                Build(commit, stamp) for commit, subject, stamp in records if subject == name
            )
        reviewed = (
            store.holds(root / "docs" / "reviews" / f"{builds[-1].stamp}.md") if builds else None
        )
        status = note.fm.get("status", "") if note.fm else ""
        colour = _colour(root, name, ids, status, unknown)
        seeds.append(SeedFacts(name, status, ids, colour, builds, reviewed))
    return tuple(seeds)


def _changelog_current(root: Path, tag: str) -> bool | None:
    """Whether `CHANGELOG.md`'s first `## ` heading names `tag` whole, False when the file is
    missing, None when it cannot be read."""
    path = root / "CHANGELOG.md"
    text = vaults.text_of(path)
    if text is None:
        return False if not path.is_file() else None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            return heading == tag or heading.startswith(f"{tag}:")
    return False


def _version_bullets(store: vaults.Vault, version: str) -> bool | None:
    """Whether the version note has a changelog bullet, or None when there is none to read."""
    rel = f"docs/versions/{version}.md"
    for note in store.notes():
        if note.rel == rel:
            return None if note.error else bool(vaults.changelog_bullets(note.body))
    return None


def gather(root: Path) -> Facts:
    """Read every fact once, answering `unknown` lines rather than guessing; nothing is written
    and no rule runs here."""
    root = Path(root)
    unknown: list[str] = []
    problems: list[str] = []

    store, vault_error = _read_vault(root)
    if vault_error is not None:
        problems.append(f"docs/: {vault_error}")

    checkout = repo.toplevel(root) is not None

    tags: frozenset[str] | None = None
    highest: str | None = None
    if checkout:
        try:
            tags = frozenset(repo.tags(root))
        except repo.RepoError as e:
            unknown.append(f"tags: {e}")
        else:
            highest = repo.highest(set(tags))
    else:
        unknown.append("tags: not a git checkout")
    if tags is None:
        unknown.append("highest: not a git checkout" if not checkout else "highest: tags unknown")

    head: str | None = None
    branch: str | None = None
    attached: bool | None = None
    dirty: tuple[str, ...] | None = None
    if checkout:
        try:
            head = repo.head(root)
        except repo.RepoError as e:
            unknown.append(f"head: {e}")
        branch, attached = _branch_and_attached(root, head, unknown)
        try:
            dirty = repo.status(root)
        except repo.RepoError as e:
            unknown.append(f"dirty: {e}")
    else:
        unknown.append("head: not a git checkout")
        unknown.append("branch: not a git checkout")
        unknown.append("attached: not a git checkout")
        unknown.append("dirty: not a git checkout")

    in_flight: str | None = None
    if not checkout:
        unknown.append("in_flight: not a git checkout")
    elif tags is None:
        unknown.append("in_flight: tags unknown")
    else:
        untagged = [
            note.path.stem
            for note in store.notes()
            if note.kind == "version" and note.path.stem not in tags
        ]
        if len(untagged) == 1:
            in_flight = untagged[0]
        elif len(untagged) > 1:
            unknown.append(f"in_flight: {len(untagged)} version notes are no tag")

    seeds = _seeds(root, store, in_flight, highest, unknown) if in_flight is not None else ()

    agents_changed: bool | None = None
    if not checkout:
        unknown.append("agents_changed: not a git checkout")
    elif highest is None:
        agents_changed = True
    else:
        try:
            agents_changed = repo.changed_since(root, highest, "AGENTS.md")
        except repo.RepoError as e:
            unknown.append(f"agents_changed: {e}")
        else:
            if not agents_changed and dirty and "AGENTS.md" in dirty:
                agents_changed = True

    version = in_flight if in_flight is not None else highest
    bullets: bool | None = None
    if version is not None:
        bullets = _version_bullets(store, version)
        if bullets is None:
            unknown.append(f"bullets: cannot read docs/versions/{version}.md")

    after_tag: bool | None = None
    if not checkout:
        unknown.append("after_tag: not a git checkout")
    elif tags is None:
        unknown.append("after_tag: highest unknown")
    elif highest is None:
        after_tag = False
    elif head is None:
        unknown.append("after_tag: the head is unknown")
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
        if changelog_current is None:
            unknown.append("changelog: cannot be read")
        if head is not None:
            try:
                main_at_head = "main" in repo.branches_at(root, head)
            except repo.RepoError as e:
                unknown.append(f"main: {e}")
            try:
                mirror_at_head = repo.ls_remote(root, "origin", "main", REMOTE_TIMEOUT) == head
            except repo.RepoError as e:
                unknown.append(f"mirror: {e}")
        installed = host.instance()
        instance_version = installed.version
        if instance_version is None:
            unknown.append(f"instance: {installed.error}")

    problems.extend(str(problem) for problem in gate.problems_check(root, store))

    return Facts(
        root=root,
        problems=tuple(problems),
        tags=tags,
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


# The seven rows a seed can have, in the table's order, each a predicate over one seed. A seed
# at `done` or `rejected`, or one whose colour or builds could not be read, has none of them.
_SEED_PREDICATES: tuple[Callable[[SeedFacts], bool], ...] = (
    lambda seed: seed.status == "open",
    lambda seed: seed.status in ("spec", "building") and not seed.tests,
    lambda seed: seed.status == "spec",
    lambda seed: seed.colour != "green",
    lambda seed: seed.colour == "green" and not seed.builds,
    lambda seed: seed.colour == "green" and bool(seed.builds) and seed.reviewed is False,
    lambda seed: seed.colour == "green" and bool(seed.builds) and seed.reviewed is True,
)


def _seed_row(seed: SeedFacts) -> int | None:
    """The index of the seed's row among the seven, or None when the seed has none."""
    if seed.status in ("done", "rejected") or seed.colour is None or seed.builds is None:
        return None
    for index, predicate in enumerate(_SEED_PREDICATES):
        if predicate(seed):
            return index
    return None


def _chosen(facts: Facts) -> tuple[int, SeedFacts] | None:
    """The first seed in name order that any of the seven rows applies to, with its row index."""
    for seed in facts.seeds:
        index = _seed_row(seed)
        if index is not None:
            return index, seed
    return None


def _seed_applies(index: int) -> Callable[[Facts], bool]:
    """A predicate that holds when the seed stepped is one whose row is `index`."""

    def applies(facts: Facts) -> bool:
        found = _chosen(facts)
        return found is not None and found[0] == index

    return applies


def _seed_text(facts: Facts, index: int) -> str:
    """The text of the row `index`, taken from the seed stepped."""
    seed = _chosen(facts)[1]
    if index == 0:
        return f"write the Goal of {seed.name}; status spec"
    if index == 1:
        return f"write red tests naming seed: {seed.name}; commit them; status building"
    if index == 2:
        return f"set {seed.name} to building: its tests name it"
    if index == 3:
        branch = facts.branch if facts.branch is not None else "<branch>"
        text = f"build {seed.name}: factory-build {facts.root} {branch} docs/seeds/{seed.name}.md"
        if facts.attached:
            text += " -- detach first: git switch --detach"
        return text
    if index == 4:
        return (
            f"{seed.name} is green with no build: commit the work with a Built-By trailer, "
            "or set it done and say why"
        )
    if index == 5:
        stamp = seed.builds[-1].stamp
        return (
            f"review build {stamp} of {seed.name}: brief a subagent, write docs/reviews/{stamp}.md"
        )
    return f"set {seed.name} to done"


def _number(facts: Facts) -> str:
    """The highest tag without its `v`, for the wheel the loop names."""
    tag = facts.highest or ""
    return tag[1:] if tag.startswith("v") else tag


def _after_tag_text(facts: Facts) -> str:
    """The first act after a tag that holds; an act whose fact is unknown is skipped and the
    next act considered, and the version is out when none holds."""
    if facts.changelog_current is False:
        return "commit CHANGELOG.md"
    if facts.main_at_head is False:
        return f"fast-forward main: git merge --ff-only heads/{facts.highest}"
    if facts.mirror_at_head is False:
        return "push: git push origin main --tags"
    if facts.instance_version is not None and facts.instance_version != _number(facts):
        return (
            f"install: uv tool install --reinstall dist/factory-{_number(facts)}-py3-none-any.whl"
        )
    return f"{facts.highest} is out: open the next version"


def _settled(facts: Facts) -> bool:
    """Whether every seed of the version in flight is terminal, and there is one."""
    return bool(facts.seeds) and all(seed.status in ("done", "rejected") for seed in facts.seeds)


def _release_applies(facts: Facts) -> bool:
    """The release row holds once every seed is terminal and the three acts it weighs are known."""
    return (
        _settled(facts)
        and facts.agents_changed is not None
        and facts.bullets is not None
        and facts.dirty is not None
    )


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
        lambda f: f.in_flight is None and f.tags is not None and f.after_tag is not True,
        lambda f: "open a version: write docs/versions/vX.md and set version: vX on a seed",
    ),
    Rule(
        "promote a seed",
        lambda f: f.in_flight is not None and not f.seeds,
        lambda f: f"promote a seed to {f.in_flight}",
    ),
    Rule("write the goal", _seed_applies(0), lambda f: _seed_text(f, 0)),
    Rule("write red tests", _seed_applies(1), lambda f: _seed_text(f, 1)),
    Rule("set to building", _seed_applies(2), lambda f: _seed_text(f, 2)),
    Rule("build", _seed_applies(3), lambda f: _seed_text(f, 3)),
    Rule("green with no build", _seed_applies(4), lambda f: _seed_text(f, 4)),
    Rule("review build", _seed_applies(5), lambda f: _seed_text(f, 5)),
    Rule("set to done", _seed_applies(6), lambda f: _seed_text(f, 6)),
    Rule("release", _release_applies, _release_text),
    Rule("unknown", lambda f: True, _unknown_text),
)


def next_step(facts: Facts) -> Step:
    """The first rule that applies, read top to bottom: the loop's next step. There is no other
    dispatch and no fallback beside the table."""
    rule = next(rule for rule in RULES if rule.applies(facts))
    return Step(rule.name, rule.step(facts))


def render(facts: Facts) -> str:
    """The step as `next: <text>`, then one `unknown: <line>` per fact that could not be read."""
    lines = [f"next: {next_step(facts).text}"]
    lines.extend(f"unknown: {line}" for line in facts.unknown)
    return "\n".join(lines) + "\n"
