#!/usr/bin/env python3
"""What a version took, derived: the table `gate.py numbers` prints.

    uv run gate.py numbers

`gather(root)` reads git, the vault, the instance's store and the runs and answers a frozen
`Tally` of one `Row` per version -- each tag in version order oldest first and the version in
flight last -- and its `unknown` lines; `render(tally)` prints the table and then
`unknown: <field>: <why>` for each line, as `next` prints its unknowns. Every fact is read once
through `vault`, `repo`, `instance` and `runs` and through nothing else, and a fact that cannot be
read is None with its line and never a value that means something else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import instance
import repo
import runs
import vault

COLUMNS = (
    "version", "seeds", "builds", "green", "red", "capped", "unrecorded", "cost_usd", "requests",
    "reviews", "findings", "defects", "judged_test", "judged_seed", "judged_case", "judged_none",
    "commits", "by_hand",
)  # fmt: skip


@dataclass(frozen=True)
class Row:
    """One version's numbers: what git, the store and the vault hold for it, None where a fact
    could not be read."""

    version: str
    seeds: int
    builds: int
    green: int | None
    red: int | None
    capped: int | None
    unrecorded: int | None
    cost_usd: float | None
    requests: int | None
    reviews: int
    findings: int
    defects: int
    judged_test: int
    judged_seed: int
    judged_case: int
    judged_none: int
    commits: int
    by_hand: int


@dataclass(frozen=True)
class Tally:
    """One `Row` per version, oldest first, and the facts that could not be read."""

    rows: tuple[Row, ...]
    unknown: tuple[str, ...]


def _number(value: Any) -> float | None:
    """`value` as a number, or None when it is absent or not one; a bool is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _build_stamp(root: Path, commit: str) -> str | None:
    """The run stamp a commit's `Built-By` trailers name, or None when it names none."""
    for entry in repo.trailers(root, commit):
        stamp = repo.run_stamp(entry)
        if stamp is not None:
            return stamp
    return None


def _stamps(root: Path, commits: list[str]) -> tuple[list[str], int]:
    """The run stamps of the commits that are builds, oldest first, and the count of those that
    are not."""
    stamps: list[str] = []
    by_hand = 0
    for commit in commits:
        stamp = _build_stamp(root, commit)
        if stamp is None:
            by_hand += 1
        else:
            stamps.append(stamp)
    return stamps, by_hand


def _store(store: Path | None, stamps: list[str]) -> tuple[int, int, int, int, float, int] | None:
    """`(green, red, capped, unrecorded, cost_usd, requests)` for the builds' records, or None
    when the store's configuration names no store that can be read."""
    if store is None:
        return None
    green = red = capped = unrecorded = 0
    cost: float = 0.0
    requests = 0
    for stamp in stamps:
        record = store / stamp
        data = runs.numbers(record)
        if data is None:
            unrecorded += 1
            continue
        if data.get("check") == "green":
            green += 1
        elif data.get("check") == "red":
            red += 1
        if runs.capped(record):
            capped += 1
        cost += _number(data.get("cost_usd")) or 0.0
        requests += _number(data.get("requests")) or 0
    return green, red, capped, unrecorded, cost, requests


def _severity(section: str) -> str | None:
    """A finding's `severity:` line, read anywhere in its prose, or None when it has none."""
    for line in vault.prose_lines(section):
        key, sep, value = line.partition(":")
        if sep and key.strip() == "severity":
            return value.strip()
    return None


def _judged(section: str) -> str | None:
    """A finding's `judged:` line, read anywhere in its prose, or None when it has none."""
    for line in vault.prose_lines(section):
        key, sep, value = line.partition(":")
        if sep and key.strip() == "judged":
            return value.strip()
    return None


def _judgements(section: str) -> list[str]:
    """The first word of each comma-separated item of a finding's `judged:` line, its trailing
    colon removed."""
    judged = _judged(section)
    if judged is None:
        return []
    return [piece.strip().split(" ", 1)[0].rstrip(":") for piece in judged.split(",")]


def _review_row(notes: list[vault.Note], stamps: set[str]) -> tuple[int, int, int, int, int, int, int]:
    """`(reviews, findings, defects, judged_test, judged_seed, judged_case, judged_none)` over the
    review notes that name one of `stamps`."""
    reviews = findings = defects = 0
    judged = {"test": 0, "seed": 0, "case": 0, "none": 0}
    for note in notes:
        if note.kind != "review" or note.fm is None:
            continue
        if not (set(note.fm.get("runs", "").split()) & stamps):
            continue
        reviews += 1
        for _, section in vault.review_findings(note.body):
            findings += 1
            if _severity(section) == "defect":
                defects += 1
            for word in _judgements(section):
                if word in judged:
                    judged[word] += 1
    return (reviews, findings, defects, judged["test"], judged["seed"], judged["case"], judged["none"])


def _seed_count(notes: list[vault.Note], version: str) -> int:
    """The seed notes whose `version` names `version`."""
    return sum(
        1
        for note in notes
        if note.kind == "seed" and note.fm is not None and note.fm.get("version") == version
    )


def gather(root: Path) -> Tally:
    """Read git, the vault, the store and the runs once and answer every version's row and the
    lines of what could not be read; nothing is written."""
    root = Path(root)
    unknown: list[str] = []

    store: Path | None
    try:
        store = instance.record_store()
    except (ValueError, OSError) as e:
        unknown.append(f"store: {e}")
        store = None
    else:
        if not store.is_dir():
            unknown.append(f"store: {store} is not a directory")
            store = None

    try:
        held = vault.Vault.read(root)
    except repo.RepoError as e:
        held = vault.Vault(root, root / "docs", None)
        unknown.append(f"docs: {e}")
    notes = list(held.notes())

    tags: set[str] | None
    try:
        tags = repo.tags(root)
    except repo.RepoError as e:
        unknown.append(f"tags: {e}")
        tags = None

    ordered = (
        sorted((tag for tag in tags if repo.version_key(tag) != (-1, -1)), key=repo.version_key)
        if tags is not None
        else []
    )
    untagged = [
        note.path.stem
        for note in notes
        if note.kind == "version" and tags is not None and note.path.stem not in tags
    ]
    in_flight = untagged[0] if len(untagged) == 1 else None

    versions: list[tuple[str, str | None, str]] = []
    for index, tag in enumerate(ordered):
        versions.append((tag, ordered[index - 1] if index else None, tag))
    if in_flight is not None:
        versions.append((in_flight, ordered[-1] if ordered else None, "HEAD"))

    rows: list[Row] = []
    for version, since, to in versions:
        try:
            commits = repo.commits(root, since, to)
        except repo.RepoError as e:
            unknown.append(f"commits of {version}: {e}")
            commits = []
        try:
            stamps, by_hand = _stamps(root, commits)
        except repo.RepoError as e:
            unknown.append(f"builds of {version}: {e}")
            stamps, by_hand = [], 0
        numbers = _store(store, stamps)
        reviews = _review_row(notes, set(stamps))
        seeds = _seed_count(notes, version)
        if numbers is None:
            green = red = capped = unrecorded = None
            cost = requests = None
        else:
            green, red, capped, unrecorded, cost, requests = numbers
        rows.append(
            Row(
                version=version,
                seeds=seeds,
                builds=len(stamps),
                green=green,
                red=red,
                capped=capped,
                unrecorded=unrecorded,
                cost_usd=cost,
                requests=requests,
                reviews=reviews[0],
                findings=reviews[1],
                defects=reviews[2],
                judged_test=reviews[3],
                judged_seed=reviews[4],
                judged_case=reviews[5],
                judged_none=reviews[6],
                commits=len(commits),
                by_hand=by_hand,
            )
        )

    return Tally(tuple(rows), tuple(unknown))


def _cell(value: Any, column: str) -> str:
    """One cell: an int as it is, money to four decimals as `runs.py` prints it, None empty."""
    if value is None:
        return ""
    if column == "cost_usd":
        return f"{value:.4f}"
    return str(value)


def render(found: Tally) -> str:
    """The table, a header and one row per version, then one `unknown: <line>` per fact that could
    not be read."""
    lines = ["\t".join(COLUMNS)]
    for row in found.rows:
        lines.append("\t".join(_cell(getattr(row, column), column) for column in COLUMNS))
    lines.extend(f"unknown: {line}" for line in found.unknown)
    return "\n".join(lines) + "\n"
