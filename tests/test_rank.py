"""Tests for issue #466 slice B — tools/rank.py, the Ideas Backlog Base's rank read by machinery.

Derived from the issue's acceptance criteria (the spec), not from rank.py's internals:
  * `rank list` and `rank top --n N` reproduce the Base's `formulas.rank` expression verbatim in
    meaning — `if(value && effort, (value - if(effort=="S",0,if(effort=="M",0.5,1))).round(1), "")`
    — over `status == "open"` seeds read through `textutil.split_frontmatter`, descending;
  * a seed missing `value` or `effort` has no rank and is still listed as such (never dropped);
  * an unrecognized `effort` falls through to the "L" discount, exactly as the nested `if` does;
  * a seed whose frontmatter reports an out-of-subset finding is listed with the finding, never
    silently dropped — even when its own status isn't "open";
  * the scan is scoped to the given component root.

Exercised end to end through the CLI (`rank list` / `rank top --n N`, TSV and JSON), since that's
the documented reading surface machinery actually uses.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANK_PY = ROOT / "tools" / "rank.py"


def _write_seed(root, rel_path, *, status="open", value=None, effort=None, summary=None,
                 extra_lines=()):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"status: {status}"]
    if value is not None:
        lines.append(f"value: {value}")
    if effort is not None:
        lines.append(f"effort: {effort}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    lines.extend(extra_lines)
    lines.append("---")
    lines.append("body text\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run(args):
    return subprocess.run(
        [sys.executable, str(RANK_PY), *args],
        capture_output=True, text=True,
    )


def _list_json(root):
    result = _run(["list", str(root), "--json"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _top_json(root, n):
    result = _run(["top", "--n", str(n), str(root), "--json"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _by_path(seeds, rel_path):
    for s in seeds:
        if s["path"] == rel_path:
            return s
    raise AssertionError(f"{rel_path!r} not found among {[s['path'] for s in seeds]}")


# --- the Base's formula, reproduced verbatim in meaning -------------------------------------

def test_rank_formula_small_medium_large_efforts(tmp_path):
    _write_seed(tmp_path, "ideas/s.md", value=3, effort="S")
    _write_seed(tmp_path, "ideas/m.md", value=3, effort="M")
    _write_seed(tmp_path, "ideas/l.md", value=3, effort="L")
    seeds = _list_json(tmp_path)
    assert _by_path(seeds, "ideas/s.md")["rank"] == 3.0
    assert _by_path(seeds, "ideas/m.md")["rank"] == 2.5
    assert _by_path(seeds, "ideas/l.md")["rank"] == 2.0


def test_unrecognized_effort_falls_through_to_the_l_discount(tmp_path):
    _write_seed(tmp_path, "ideas/xl.md", value=3, effort="XL")
    seeds = _list_json(tmp_path)
    assert _by_path(seeds, "ideas/xl.md")["rank"] == 2.0


def test_rank_rounds_to_one_decimal_place(tmp_path):
    _write_seed(tmp_path, "ideas/round-down.md", value=3.14, effort="S")
    _write_seed(tmp_path, "ideas/round-up.md", value=3.16, effort="S")
    seeds = _list_json(tmp_path)
    assert _by_path(seeds, "ideas/round-down.md")["rank"] == 3.1
    assert _by_path(seeds, "ideas/round-up.md")["rank"] == 3.2


def test_seed_missing_value_has_no_rank_but_is_listed(tmp_path):
    _write_seed(tmp_path, "ideas/no-value.md", effort="S")
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/no-value.md")
    assert seed["rank"] is None


def test_seed_missing_effort_has_no_rank_but_is_listed(tmp_path):
    _write_seed(tmp_path, "ideas/no-effort.md", value=5)
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/no-effort.md")
    assert seed["rank"] is None


def test_seed_missing_both_has_no_rank_but_is_listed(tmp_path):
    _write_seed(tmp_path, "ideas/bare.md")
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/bare.md")
    assert seed["rank"] is None


def test_missing_rank_prints_as_empty_column_in_tsv(tmp_path):
    _write_seed(tmp_path, "ideas/bare.md")
    result = _run(["list", str(tmp_path)])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip("\n").split("\n")
    header = lines[0].split("\t")
    row = dict(zip(header, lines[1].split("\t")))
    assert row["rank"] == ""


# --- status filtering ------------------------------------------------------------------------

def test_non_open_status_without_findings_is_excluded(tmp_path):
    _write_seed(tmp_path, "ideas/closed.md", status="closed", value=5, effort="S")
    _write_seed(tmp_path, "ideas/open.md", status="open", value=5, effort="S")
    seeds = _list_json(tmp_path)
    paths = [s["path"] for s in seeds]
    assert "ideas/open.md" in paths
    assert "ideas/closed.md" not in paths


# --- out-of-subset frontmatter findings: never silently dropped ------------------------------

def test_out_of_subset_finding_is_listed_alongside_the_seed(tmp_path):
    path = tmp_path / "ideas" / "weird.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # a nested mapping under `nested:` is outside split_frontmatter's declared subset
    path.write_text(
        "---\nstatus: open\nvalue: 5\neffort: S\nnested:\n  child: 1\n---\nbody\n",
        encoding="utf-8",
    )
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/weird.md")
    assert seed["findings"], "an out-of-subset frontmatter shape must be reported, not dropped"


def test_out_of_subset_finding_keeps_a_non_open_seed_visible(tmp_path):
    """Even a seed whose status isn't 'open' must stay listed when it carries a finding — a
    finding is never silently dropped, regardless of the seed's own status."""
    path = tmp_path / "ideas" / "closed-but-weird.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nstatus: closed\nvalue: 5\neffort: S\nnested:\n  child: 1\n---\nbody\n",
        encoding="utf-8",
    )
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/closed-but-weird.md")
    assert seed["findings"]


def test_clean_seed_has_no_findings(tmp_path):
    _write_seed(tmp_path, "ideas/clean.md", value=5, effort="S")
    seeds = _list_json(tmp_path)
    seed = _by_path(seeds, "ideas/clean.md")
    assert seed["findings"] == []


# --- descending sort, ties, and `top --n` -----------------------------------------------------

def test_seeds_sort_descending_by_rank_unranked_last(tmp_path):
    _write_seed(tmp_path, "ideas/low.md", value=2, effort="S")
    _write_seed(tmp_path, "ideas/high.md", value=5, effort="S")
    _write_seed(tmp_path, "ideas/mid.md", value=3, effort="S")
    _write_seed(tmp_path, "ideas/unranked.md", value=5)  # no effort -> no rank
    seeds = _list_json(tmp_path)
    ordered = [s["path"] for s in seeds]
    assert ordered == [
        "ideas/high.md", "ideas/mid.md", "ideas/low.md", "ideas/unranked.md",
    ]


def test_top_n_returns_the_leading_slice_of_the_descending_list(tmp_path):
    _write_seed(tmp_path, "ideas/low.md", value=2, effort="S")
    _write_seed(tmp_path, "ideas/high.md", value=5, effort="S")
    _write_seed(tmp_path, "ideas/mid.md", value=3, effort="S")
    top2 = _top_json(tmp_path, 2)
    assert [s["path"] for s in top2] == ["ideas/high.md", "ideas/mid.md"]


# --- component-root scoping --------------------------------------------------------------------

def test_scan_is_scoped_to_the_given_component_root(tmp_path):
    _write_seed(tmp_path, "componentA/ideas/in-scope.md", value=5, effort="S")
    _write_seed(tmp_path, "componentB/ideas/out-of-scope.md", value=5, effort="S")
    seeds = _list_json(tmp_path / "componentA")
    paths = [s["path"] for s in seeds]
    assert paths == ["ideas/in-scope.md"]


def test_scan_finds_ideas_folders_nested_under_multiple_teams(tmp_path):
    _write_seed(tmp_path, "teamA/ideas/a.md", value=5, effort="S")
    _write_seed(tmp_path, "teamB/ideas/b.md", value=4, effort="S")
    seeds = _list_json(tmp_path)
    paths = sorted(s["path"] for s in seeds)
    assert paths == ["teamA/ideas/a.md", "teamB/ideas/b.md"]
