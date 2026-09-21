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
    "version", "seeds", "runs", "builds", "green", "red", "capped", "unrecorded", "cost_usd",
    "requests", "reviews", "findings", "defects", "judged_test", "judged_seed", "judged_case",
    "judged_none", "commits", "by_hand",
)  # fmt: skip


@dataclass(frozen=True)
class Row:
    """One version's numbers: what git, the store and the vault hold for it, None where a fact
    could not be read."""

    version: str
    seeds: int
    runs: int | None
    builds: int | None
    green: int | None
    red: int | None
    capped: int | None
    unrecorded: int | None
    cost_usd: float | None
    requests: int | None
    reviews: int | None
    findings: int | None
    defects: int | None
    judged_test: int | None
    judged_seed: int | None
    judged_case: int | None
    judged_none: int | None
    commits: int | None
    by_hand: int | None


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
    are not; `RepoError` when a commit's trailers cannot be read."""
    stamps: list[str] = []
    by_hand = 0
    for commit in commits:
        stamp = _build_stamp(root, commit)
        if stamp is None:
            by_hand += 1
        else:
            stamps.append(stamp)
    return stamps, by_hand


def _store_records(
    store: Path,
) -> tuple[dict[str, list[tuple[str, dict[str, Any], Path]]], set[str]]:
    """Every readable record of `store`, by the seed it names, and the stamps that have a readable
    record. A record whose numbers cannot be read names no seed and is no run; a record whose
    `seed` is not a name belongs to no seed; a record whose numbers are readable is recorded even
    when it names no seed, so a build whose stamp it holds is not unrecorded."""
    by_seed: dict[str, list[tuple[str, dict[str, Any], Path]]] = {}
    recorded: set[str] = set()
    for record in runs.records(store):
        data = runs.numbers(record)
        if data is None:
            continue
        recorded.add(record.name)
        seed = data.get("seed")
        if isinstance(seed, str) and seed:
            by_seed.setdefault(seed, []).append((record.name, data, record))
    return by_seed, recorded


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


def _review_row(
    notes: list[vault.Note], stamps: set[str]
) -> tuple[int, int, int, int, int, int, int]:
    """`(reviews, findings, defects, judged_test, judged_seed, judged_case, judged_none)` over the
    review notes that name one of `stamps`; a finding counts once under each kind its `judged:`
    line names, however many items of that kind it names."""
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
            for word in dict.fromkeys(_judgements(section)):
                if word in judged:
                    judged[word] += 1
    return (reviews, findings, defects, judged["test"], judged["seed"], judged["case"], judged["none"])


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
    by_seed: dict[str, list[tuple[str, dict[str, Any], Path]]] = {}
    recorded: set[str] = set()
    if store is not None:
        by_seed, recorded = _store_records(store)

    try:
        held = vault.Vault.read(root)
    except repo.RepoError as e:
        held = vault.Vault(root, root / "docs", None)
        unknown.append(f"docs: {e}")
    notes = list(held.notes())

    unreadable_reviews = [
        note.rel for note in notes if note.error and note.rel.startswith("docs/reviews/")
    ]
    for rel in unreadable_reviews:
        unknown.append(f"reviews: {rel} cannot be read")

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

    in_flight: str | None = None
    if tags is None:
        unknown.append("in_flight: tags unknown")
    else:
        untagged = [
            note.path.stem
            for note in notes
            if note.kind == "version" and note.path.stem not in tags
        ]
        if len(untagged) == 1:
            in_flight = untagged[0]
        elif len(untagged) > 1:
            unknown.append(f"in_flight: {len(untagged)} version notes are no tag")

    versions: list[tuple[str, str | None, str]] = []
    for index, tag in enumerate(ordered):
        versions.append((tag, ordered[index - 1] if index else None, tag))
    if in_flight is not None:
        versions.append((in_flight, ordered[-1] if ordered else None, "HEAD"))

    rows: list[Row] = []
    for version, since, to in versions:
        names = {
            note.path.stem
            for note in notes
            if note.kind == "seed" and note.fm is not None and note.fm.get("version") == version
        }
        seeds = len(names)

        commits: list[str] | None
        try:
            commits = repo.commits(root, since, to)
        except repo.RepoError as e:
            unknown.append(f"commits of {version}: {e}")
            commits = None
        stamps: list[str] | None
        by_hand: int | None
        if commits is None:
            stamps = None
            by_hand = None
        else:
            try:
                stamps, by_hand = _stamps(root, commits)
            except repo.RepoError as e:
                unknown.append(f"builds of {version}: {e}")
                stamps = None
                by_hand = None

        run_records = [entry for name in names for entry in by_seed.get(name, [])]
        if store is None:
            runs_count = green = red = capped = unrecorded = cost = requests = None
        else:
            runs_count = len(run_records)
            green = sum(1 for _, data, _ in run_records if data.get("check") == "green")
            red = sum(1 for _, data, _ in run_records if data.get("check") == "red")
            capped = sum(1 for _, _, record in run_records if runs.capped(record) is True)
            cost = sum(_number(data.get("cost_usd")) or 0.0 for _, data, _ in run_records)
            requests = sum(_number(data.get("requests")) or 0 for _, data, _ in run_records)
            if stamps is None:
                unrecorded = None
            else:
                unrecorded = sum(1 for stamp in stamps if stamp not in recorded)

        if unreadable_reviews or store is None:
            # Without the store, a review of a run git does not hold cannot be placed, and a count
            # of the reviews git can place would mean something else; an unreadable note leaves
            # every row's review columns unknown.
            reviews = findings = defects = None
            judged_test = judged_seed = judged_case = judged_none = None
        else:
            found_stamps = {stamp for stamp, _, _ in run_records}
            if stamps is not None:
                found_stamps.update(stamps)
            (reviews, findings, defects, judged_test, judged_seed, judged_case, judged_none) = (
                _review_row(notes, found_stamps)
            )

        rows.append(
            Row(
                version=version,
                seeds=seeds,
                runs=runs_count,
                builds=len(stamps) if stamps is not None else None,
                green=green,
                red=red,
                capped=capped,
                unrecorded=unrecorded,
                cost_usd=cost,
                requests=requests,
                reviews=reviews,
                findings=findings,
                defects=defects,
                judged_test=judged_test,
                judged_seed=judged_seed,
                judged_case=judged_case,
                judged_none=judged_none,
                commits=len(commits) if commits is not None else None,
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
