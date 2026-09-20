#!/usr/bin/env python3
"""The catch-rate harness: run the reviewer over commits whose findings are already known, and
count what it caught.

    uv run catch.py --spend USD [case ...]
    uv run catch.py --score [case ...]

A case is `catches/<name>.toml`: a commit of this repository, the seed that commit was built
from, and one `[[finding]]` per defect the commit is known to hold -- a `path`, and `lines` or
`line` of the file at that commit, each with the review note it came from. The answers are the
ones in `docs/reviews/` that the attended agent verified and that a pass which reads and cannot
run could have reached.

A case is reviewed the way anything is reviewed. A throwaway worktree at that commit, the
reviewer run over it as `reviewer.py` is run over any delivered tree, nothing about the review
special-cased because it is being measured. Its record lands in the instance's store key-scanned
like any other, tagged with a goal beginning `case: <name>` as an evaluation build's does, so
`runs.py` shows what the measurement cost beside everything else it shows.

A catch is crude and visible, and it is counted twice. A reported finding catches a known one when
it names that path and its line falls within that span; the same set is counted again on the path
alone. One row per case gives how many of the known findings were caught on each count, how many
passes ran, what the review cost and how long it took. Then the set's rate on each count with its
standard error under a uniform prior, as `evals.py` gives the builder's.

A review's cost is chosen and not emergent -- `dimensions x passes x SOFT_SPEND` for each case,
and a pass may run to `HARD_SPEND` above it -- so both what the run is expected to cost and what
it could cost are said before the first pass starts. A run that could cost more than it was told
it may spend is refused before a model is called and before a record is made, naming both
numbers. There is no default allowance.

`--score` scores the records the store already holds and spends nothing: no worktree, no pass, no
model, and no allowance, because there is nothing to allow. A record says which case it was in its
own goal -- its first line is `case: <name>` -- so scoring needs no telling, and a key that was
corrected after a review is scored again for the price of the arithmetic. It prints the same table
and rates as a run, one row per case, against the latest record that names it. A case the store
holds no record of is shown as unmeasured and left out of the rate, because a review that never ran
is not a review that caught nothing.

Exit 0 when every review answered and every record scored, 1 when a review was capped or errored,
2 on a usage error: a case that is missing or not whole, an allowance that is not a non-negative
number, no allowance for a run, or a run over what it was allowed.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import builder
import reviewer

# The set's own name at the checkout root, one file per case, as `cases/` is the evaluation set's.
CASES_DIR = "catches"
COLUMNS = ("case", "strict", "path", "known", "passes", "cost_usd", "seconds")
# A case the store holds no record of is shown with this in its count cells and left out of the
# rate: a review that never ran is not a review that caught nothing.
UNMEASURED = "unmeasured"


def usage_error(reason: str = "") -> int:
    print("usage: catch.py [--score | --spend USD] [case ...]", file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


@dataclass
class Case:
    """One commit and what it is known to hold: its name, the commit to review, the seed that
    commit was built from, and one (path, first, last) per known finding."""

    name: str
    commit: str
    seed: str
    findings: list[tuple[str, int, int]] = field(default_factory=list)


def _number(value: Any) -> float | None:
    """`value` as a number, or None when it is absent or not one; a bool is not a number and a
    non-finite float is no number either."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _line_span(finding: dict[str, Any]) -> tuple[int, int] | None:
    """A finding's span as two line numbers: `lines` when it holds exactly two ints, a single
    `line` as a one-line span, and None when it names neither. A bool is not a line."""
    lines = finding.get("lines")
    if isinstance(lines, list) and len(lines) == 2:
        first, last = lines
        if all(isinstance(n, int) and not isinstance(n, bool) for n in lines):
            return (first, last) if first <= last else (last, first)
    line = finding.get("line")
    if isinstance(line, int) and not isinstance(line, bool):
        return line, line
    return None


def _case(path: Path) -> Case | str:
    """The case a file holds, or the reason it is not whole."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return f"case {path.stem} cannot be read as UTF-8"
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return f"case {path.stem} is not TOML"
    commit, seed = data.get("commit"), data.get("seed")
    if not isinstance(commit, str) or not commit.strip():
        return f"case {path.stem} has no commit"
    if not isinstance(seed, str) or not seed.strip():
        return f"case {path.stem} has no seed"
    raw = data.get("finding", [])
    if not isinstance(raw, list):
        return f"case {path.stem} has a finding that is not a table"
    findings: list[tuple[str, int, int]] = []
    for finding in raw:
        if not isinstance(finding, dict):
            return f"case {path.stem} has a finding that is not a table"
        target = finding.get("path")
        if not isinstance(target, str) or not target:
            return f"case {path.stem} has a finding without a path"
        span = _line_span(finding)
        if span is None:
            return f"case {path.stem} has a finding without a line or a span: {target}"
        findings.append((target, span[0], span[1]))
    if not findings:  # nothing to catch: a case that names no finding cannot be scored
        return f"case {path.stem} names no finding"
    return Case(name=path.stem, commit=commit.strip(), seed=seed.strip(), findings=findings)


def _cases(base: Path, names: list[str]) -> tuple[list[Case] | None, str]:
    """The cases to run: the named files must exist and be whole, the unnamed ones are every
    `*.toml` under `catches/`. None and the reason when a case cannot be used."""
    directory = base / CASES_DIR
    if names:
        paths = []
        for name in names:
            found = directory / f"{name}.toml"
            if not found.is_file():
                return None, f"no such case: {name}"
            paths.append(found)
    else:
        if not directory.is_dir():
            return [], ""
        paths = sorted(directory.glob("*.toml"))
    cases: list[Case] = []
    for path in paths:
        case = _case(path)
        if isinstance(case, str):
            return None, case
        cases.append(case)
    return cases, ""


def _parse(argv: list[str]) -> tuple[bool, float | None, list[str], str]:
    """`--score`, `--spend USD` and the case names; the reason of a usage error instead, with
    whether the run scores records rather than making them and the allowance, which is None when
    the run did not name one."""
    score, spend, names, i = False, None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--score":
            score = True
            i += 1
        elif arg == "--spend" or arg.startswith("--spend="):
            if arg == "--spend":
                if i + 1 >= len(argv):
                    return score, None, names, "--spend needs a value"
                value, i = argv[i + 1], i + 2
            else:
                value, i = arg.partition("=")[2], i + 1
            number = _number(_float(value))
            if number is None or number < 0:
                return score, None, names, f"--spend is not a non-negative number: {value}"
            spend = number
        elif arg.startswith("-") and arg != "-":
            return score, spend, names, f"unknown argument: {arg}"
        elif not arg:
            return score, spend, names, "not a case name: "
        else:
            names.append(arg)
            i += 1
    return score, spend, names, ""


def _float(text: str) -> float | None:
    """`text` as a float, or None when it is not one."""
    try:
        return float(text)
    except ValueError:
        return None


def _numbers(record: Path) -> dict[str, Any]:
    """The record's `numbers.json` as a mapping; empty when it is absent or unreadable."""
    try:
        data = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _reported(record: Path) -> list[dict[str, Any]]:
    """The findings the review reported, from its `review.json`; empty when it has none."""
    try:
        data = json.loads((record / "review.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    findings = data.get("findings") if isinstance(data, dict) else None
    return [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []


def _case_of(record: Path) -> str | None:
    """The case name a record's goal names: the first line is `case: <name>` as an evaluation
    build's goal is. None when the record holds no readable goal or one that names no case, so a
    record that is not a measurement is not scored against one."""
    try:
        lines = (record / "goal.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    line = lines[0].strip() if lines else ""
    prefix = "case: "
    if line.startswith(prefix):
        name = line[len(prefix):].strip()
        return name or None
    return None


def _capped(numbers: dict[str, Any]) -> bool:
    """Whether a review's numbers say it was not a measurement: it did not answer, or fewer passes
    ran than its dimensions x passes say it was given. A record whose dimensions and passes are
    absent is counted in the dimensions and passes fixed today, as its run counted them."""
    dimensions = numbers.get("dimensions", len(reviewer.DIMENSIONS))
    passes = numbers.get("passes", reviewer.PASSES)
    expected = dimensions * passes if all(isinstance(n, int) and not isinstance(n, bool)
                                          for n in (dimensions, passes)) else None
    ran = numbers.get("passes_ran")
    short = isinstance(expected, int) and (not isinstance(ran, int) or ran < expected)
    return numbers.get("stopped") != "answer" or short


def _counts(case: Case, reported: list[dict[str, Any]]) -> tuple[int, int]:
    """How many of the case's known findings were caught strictly -- same path and a line in the
    span -- and on the path alone. A known finding is caught once however many reports name it."""
    strict = loose = 0
    for path, first, last in case.findings:
        named = [f for f in reported if f.get("path") == path]
        if not named:
            continue
        loose += 1
        if any(isinstance(f.get("line"), int) and not isinstance(f.get("line"), bool)
               and first <= f["line"] <= last for f in named):  # fmt: skip
            strict += 1
    return strict, loose


def _tag(record: Path, case: Case) -> None:
    """The record named for the case it measures: its goal becomes `case: <name>` and the seed's
    own goal beneath it, as an evaluation build's does, and it is committed and key-scanned again
    so the store holds what its goal says it is."""
    try:
        original = (record / "goal.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        original = ""
    text = f"case: {case.name}\n{original}"
    (record / "goal.txt").write_text(text)
    numbers = _numbers(record)
    numbers["goal"] = text
    (record / "numbers.json").write_text(json.dumps(numbers, indent=1) + "\n")
    try:  # the same one function that commits any record: searched and committed, never trusted
        builder.commit_record(builder.record_store(), record)
    except (builder.LeakedKey, builder.GitError, OSError, subprocess.SubprocessError) as e:
        print(f"{record}: {' '.join(str(e).split())}", file=sys.stderr)


def _run_case(root: Path, work: Path, case: Case,
              model: Any) -> tuple[list[str], tuple[int, int, int] | None, bool]:  # fmt: skip
    """One case: a worktree at its commit, the reviewer over it, its record tagged and counted. The
    cells, the (known, caught-strict, caught-path) it earned for the set's rate -- None when the
    review was not a measurement -- and whether the review answered in full."""
    worktree = work / case.name
    try:
        builder.git(root, "worktree", "add", "--detach", str(worktree), case.commit)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = reviewer.main(["reviewer.py", str(worktree), case.seed], model=model)
        printed = out.getvalue().splitlines()
        record = Path(printed[0].strip()) if printed and printed[0].strip() else None
        if record is None or not record.is_dir():  # the review could not be started: unmeasured
            return _unmeasured(case), None, False
        _tag(record, case)
        numbers = _numbers(record)
        if code != 0 or _capped(numbers):  # capped or errored: not a measurement, so not in the rate
            return _unmeasured(case, numbers), None, False
        strict, loose = _counts(case, _reported(record))
        return _cells(case, strict, loose, numbers), (len(case.findings), strict, loose), True
    except (builder.GitError, OSError, subprocess.SubprocessError) as e:
        print(f"{case.name}: {' '.join(str(e).split())}", file=sys.stderr)
        return _unmeasured(case), None, False
    finally:
        _remove(root, worktree)


def _row(case: Case, strict: str, loose: str, numbers: dict[str, Any]) -> list[str]:
    """One case's row: its name, the two counts as its caller renders them, how many findings were
    known, how many passes ran, what the review cost and how long it took."""
    cost, seconds = _number(numbers.get("cost_usd")), _number(numbers.get("seconds"))
    ran = numbers.get("passes_ran")
    return [
        case.name,
        strict,
        loose,
        str(len(case.findings)),
        str(ran) if isinstance(ran, int) and not isinstance(ran, bool) else "",
        "" if cost is None else str(round(cost, 5)),
        "" if seconds is None else str(round(seconds, 1)),
    ]


def _cells(case: Case, strict: int, loose: int, numbers: dict[str, Any]) -> list[str]:
    """A measured case's row: the findings it caught on each count."""
    return _row(case, str(strict), str(loose), numbers)


def _unmeasured(case: Case, numbers: dict[str, Any] | None = None) -> list[str]:
    """A case's row when it was not measured: no record, a review that could not be started, or one
    that did not finish. Its counts are not zero -- a review that never answered is not a review that
    found nothing, and counting it as one drags the rate down with cases that were never asked. The
    passes it ran and what they cost are still shown, so the row says what was spent on it."""
    return _row(case, UNMEASURED, UNMEASURED, numbers or {})


def _remove(root: Path, worktree: Path) -> None:
    """Remove the worktree, whatever the review left in it."""
    try:
        if worktree.exists():
            builder.git(root, "worktree", "remove", "--force", str(worktree))
    except (builder.GitError, OSError, subprocess.SubprocessError) as e:
        print(f"could not remove the worktree {worktree}: {e}", file=sys.stderr)


def _prune(root: Path) -> None:
    """Prune the worktree metadata once the temporary directory that held them is gone."""
    try:
        builder.git(root, "worktree", "prune")
    except (builder.GitError, OSError, subprocess.SubprocessError) as e:
        print(f"could not prune worktrees of {root}: {e}", file=sys.stderr)


def _rate(pairs: list[tuple[int, int]]) -> tuple[float, float]:
    """A set's rate and its standard error: the mean over the cases of each case's caught over
    known, and the root of the sum over the cases of the variance of a case's rate under a uniform
    prior, (k+1)(n-k+1) over (n+2)^2 (n+3), divided by the case count; as `evals.py` gives the
    builder's. A case that knows nothing contributes a rate of zero and its own prior variance."""
    rates = [k / n if n else 0.0 for k, n in pairs]
    terms = [(k + 1) * (n - k + 1) / ((n + 2) ** 2 * (n + 3)) for k, n in pairs]
    return sum(rates) / len(rates), math.sqrt(sum(terms)) / len(pairs)


def _rates(stats: list[tuple[int, int, int]]) -> list[str]:
    """The set's rate and its standard error on each count, as `evals.py` gives the builder's: an
    empty line first, then the strict rate and the path rate. No measurements at all is no rate to
    print and no arithmetic to attempt, which is an answer rather than a failure."""
    if not stats:  # nothing was measured: there is no rate over nothing to print
        return []
    strict_rate, strict_error = _rate([(strict, known) for known, strict, _ in stats])
    path_rate, path_error = _rate([(loose, known) for known, _, loose in stats])
    return ["", f"strict rate {strict_rate:.3f} ± {strict_error:.3f}",
            f"path rate {path_rate:.3f} ± {path_error:.3f}"]


def _score(store: Path, cases: list[Case]) -> int:
    """Score the records the store already holds, without a worktree, a pass or a model: for each
    case, the latest record whose goal names it, against the case's answers. A case with no record is
    shown as unmeasured and left out of the rate, because a review that was never made is not a
    review that caught nothing. Nothing is read from a record but its goal, its numbers and the
    findings it reported; nothing is written."""
    latest: dict[str, Path] = {}
    if store.is_dir():
        for record in sorted(p for p in store.iterdir() if p.is_dir() and p.name != ".git"):
            name = _case_of(record)
            if name is not None:
                latest[name] = record  # stamp order: the last record of a case is the latest one
    rows: list[str] = ["\t".join(COLUMNS)]
    stats: list[tuple[int, int, int]] = []
    failed = False
    for case in cases:
        record = latest.get(case.name)
        if record is None:  # never run: shown as unmeasured and left out of the rate
            rows.append("\t".join(_unmeasured(case)))
            continue
        numbers = _numbers(record)
        if _capped(numbers):  # capped or errored: not a measurement, so not in the rate, but exit 1
            rows.append("\t".join(_unmeasured(case, numbers)))
            failed = True
            continue
        strict, loose = _counts(case, _reported(record))
        rows.append("\t".join(_cells(case, strict, loose, numbers)))
        stats.append((len(case.findings), strict, loose))
    print("\n".join(rows))
    if cases:
        print("\n".join(_rates(stats)))
    return 1 if failed else 0


def main(argv: list[str], root: Any = None, model: Any = None) -> int:
    base = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    score, spend, names, reason = _parse(list(argv[1:]))
    if reason:
        return usage_error(reason)
    if not score and spend is None:  # no default that spends money: a run must say what it may spend
        return usage_error("--spend is required")
    cases, reason = _cases(base, names)
    if cases is None:
        return usage_error(reason)
    if score:
        if spend is not None:  # scoring spends nothing, so an allowance has nothing to bound
            return usage_error("--score spends nothing: it takes no --spend")
        try:
            store = builder.record_store()
        except (ValueError, OSError) as e:
            return usage_error(str(e))
        return _score(store, cases)
    # A review is `dimensions x passes x SOFT_SPEND` expected, every factor known before the first
    # pass, so what the whole run is expected to cost is arithmetic and is said before anything is
    # spent. What one review *can* reach is its own stopping rule and not its passes at their worst:
    # it stops *starting* passes once it has spent `dimensions x passes x SOFT_SPEND`, so the most
    # it can reach is that plus the pass already running, which may go to `HARD_SPEND`. The set's
    # ceiling counts that pass once per case, not every pass at its worst.
    passes = len(cases) * len(reviewer.DIMENSIONS) * reviewer.PASSES
    projected = passes * builder.SOFT_SPEND
    ceiling = projected + len(cases) * builder.HARD_SPEND
    print(f"projected spend {projected:.2f} USD for {len(cases)} cases, allowed {spend:.2f} USD")
    print(f"a pass may run to {builder.HARD_SPEND:.2f} USD, so the run could cost {ceiling:.2f} USD")
    # The allowance bounds what the run could spend and not what it is expected to: a pass that
    # crossed the soft ceiling keeps going to the hard one, so a run allowed its projection but not
    # its ceiling is refused.
    if ceiling > spend:
        print(f"the run could cost {ceiling:.2f} USD, more than the {spend:.2f} USD allowed",
              file=sys.stderr)  # fmt: skip
        return 2
    rows: list[str] = ["\t".join(COLUMNS)]
    stats: list[tuple[int, int, int]] = []
    failed = False
    work = Path(tempfile.mkdtemp(prefix="factory-catch-"))
    try:
        for case in cases:
            try:
                cells, measured, ok = _run_case(base, work, case, model)
            except Exception as e:  # one failed case names itself and the set goes on
                print(f"{case.name}: {' '.join(str(e).split())}", file=sys.stderr)
                cells, measured, ok = _unmeasured(case), None, False
            rows.append("\t".join(cells))
            if measured is not None:  # only a review that answered is a measurement
                stats.append(measured)
            failed = failed or not ok
    finally:
        shutil.rmtree(work, ignore_errors=True)
        _prune(base)
    print("\n".join(rows))
    if cases:
        print("\n".join(_rates(stats)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
