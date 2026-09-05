"""Tests for issue #466 slice B — tools/strategy.py, the strategy note's fenced-block reader.

Derived from the issue's acceptance criteria (the spec), not from strategy.py's internals:
  * a note's fenced ```yr-strategy TOML block parses into themes (id, goal, target, repos,
    budget_usd, stop_when), constraints, kpi_targets, loop_budget_usd_per_week and factory_cap;
  * a missing or malformed block is a loud finding, never a silent empty result;
  * the note's frontmatter is read through the one parser (`textutil.split_frontmatter`), and an
    out-of-subset shape there is surfaced, never silently dropped.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STRATEGY_PY = ROOT / "tools" / "strategy.py"
sys.path.insert(0, str(ROOT / "tools"))

import strategy  # noqa: E402


VALID_NOTE = """---
status: active
---
# Team strategy

Some prose above the block.

```yr-strategy
loop_budget_usd_per_week = 500
factory_cap = 3

[[themes]]
id = "theme-a"
goal = "Ship X"
target = "metric > 10"
repos = ["owner/repo-a"]
budget_usd = 1000
stop_when = "metric <= 10"

[[themes]]
id = "theme-b"
goal = "Ship Y"
target = "metric > 20"
repos = ["owner/repo-b"]
budget_usd = 2000
stop_when = "metric <= 20"

[constraints]
max_parallel = 2

[kpi_targets]
throughput = 5
```

Some prose below the block.
"""


def _run(*args):
    return subprocess.run(
        [sys.executable, str(STRATEGY_PY), *args],
        capture_output=True, text=True,
    )


def _write(tmp_path, text, name="strategy.md"):
    path = tmp_path / "strategy" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- the happy path: full shape parses ---------------------------------------------------------

def test_parses_themes_constraints_kpi_targets_budget_and_cap():
    data = strategy.parse_strategy(VALID_NOTE)
    assert data["loop_budget_usd_per_week"] == 500
    assert data["factory_cap"] == 3
    assert data["constraints"] == {"max_parallel": 2}
    assert data["kpi_targets"] == {"throughput": 5}
    themes = data["themes"]
    assert len(themes) == 2
    theme_a = next(t for t in themes if t["id"] == "theme-a")
    assert theme_a["goal"] == "Ship X"
    assert theme_a["target"] == "metric > 10"
    assert theme_a["repos"] == ["owner/repo-a"]
    assert theme_a["budget_usd"] == 1000
    assert theme_a["stop_when"] == "metric <= 10"


def test_cli_prints_valid_note_as_json_and_exits_zero(tmp_path):
    path = _write(tmp_path, VALID_NOTE)
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert '"theme-a"' in result.stdout
    assert '"factory_cap": 3' in result.stdout


# --- missing block: a loud finding, never silent -----------------------------------------------

def test_missing_block_raises_loudly():
    with pytest.raises(strategy.StrategyError, match="no fenced"):
        strategy.parse_strategy("---\nstatus: active\n---\nno block here at all\n")


def test_cli_missing_block_exits_nonzero_and_names_the_file(tmp_path):
    path = _write(tmp_path, "---\nstatus: active\n---\nno block here.\n")
    result = _run(str(path))
    assert result.returncode != 0
    assert str(path) in result.stdout
    assert "no fenced" in result.stdout


def test_unclosed_block_raises_loudly():
    text = "---\nstatus: active\n---\n```yr-strategy\nfactory_cap = 1\n"
    with pytest.raises(strategy.StrategyError, match="never closes"):
        strategy.parse_strategy(text)


# --- malformed TOML: a loud finding, never a partial/silent result ------------------------------

def test_malformed_toml_raises_loudly():
    text = "---\nstatus: active\n---\n```yr-strategy\nthis is not = = valid toml\n```\n"
    with pytest.raises(strategy.StrategyError, match="malformed TOML"):
        strategy.parse_strategy(text)


def test_cli_malformed_toml_exits_nonzero(tmp_path):
    text = "---\nstatus: active\n---\n```yr-strategy\nthis is not = = valid toml\n```\n"
    path = _write(tmp_path, text)
    result = _run(str(path))
    assert result.returncode != 0
    assert "malformed TOML" in result.stdout


# --- missing required top-level or theme keys: a loud finding -----------------------------------

def test_missing_top_level_key_raises_loudly():
    text = (
        "---\nstatus: active\n---\n```yr-strategy\n"
        "loop_budget_usd_per_week = 500\n"
        "\n[[themes]]\nid = \"a\"\ngoal = \"g\"\ntarget = \"t\"\nrepos = []\n"
        "budget_usd = 1\nstop_when = \"s\"\n"
        "\n[constraints]\n\n[kpi_targets]\n```\n"
    )
    with pytest.raises(strategy.StrategyError, match="factory_cap"):
        strategy.parse_strategy(text)


def test_theme_missing_required_key_raises_loudly():
    text = (
        "---\nstatus: active\n---\n```yr-strategy\n"
        "loop_budget_usd_per_week = 500\nfactory_cap = 1\n"
        "\n[[themes]]\nid = \"a\"\ngoal = \"g\"\ntarget = \"t\"\nrepos = []\n"
        # budget_usd and stop_when omitted
        "\n[constraints]\n\n[kpi_targets]\n```\n"
    )
    with pytest.raises(strategy.StrategyError, match="themes\\[0\\]"):
        strategy.parse_strategy(text)


def test_empty_themes_list_raises_loudly():
    text = (
        "---\nstatus: active\n---\n```yr-strategy\n"
        "loop_budget_usd_per_week = 500\nfactory_cap = 1\nthemes = []\n"
        "\n[constraints]\n\n[kpi_targets]\n```\n"
    )
    with pytest.raises(strategy.StrategyError, match="non-empty"):
        strategy.parse_strategy(text)


# --- frontmatter: the one parser, out-of-subset findings surfaced, never dropped -----------------

def test_frontmatter_out_of_subset_finding_is_surfaced_not_dropped():
    text = VALID_NOTE.replace(
        "---\nstatus: active\n---",
        "---\nstatus: active\nnested:\n  child: 1\n---",
    )
    findings = strategy.frontmatter_findings(text)
    assert findings, "an out-of-subset frontmatter shape must be reported, not dropped"


def test_frontmatter_finding_does_not_block_a_valid_block_from_parsing():
    text = VALID_NOTE.replace(
        "---\nstatus: active\n---",
        "---\nstatus: active\nnested:\n  child: 1\n---",
    )
    # the finding is reported ALONGSIDE the parse, never in place of it
    data = strategy.parse_strategy(text)
    assert data["factory_cap"] == 3
    assert strategy.frontmatter_findings(text)


def test_clean_frontmatter_has_no_findings():
    assert strategy.frontmatter_findings(VALID_NOTE) == []


def test_cli_prints_frontmatter_finding_alongside_successful_parse(tmp_path):
    text = VALID_NOTE.replace(
        "---\nstatus: active\n---",
        "---\nstatus: active\nnested:\n  child: 1\n---",
    )
    path = _write(tmp_path, text)
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert "frontmatter finding" in result.stdout
    assert '"factory_cap": 3' in result.stdout


def test_note_with_no_frontmatter_still_parses_the_block():
    text = VALID_NOTE.split("---\n", 2)[-1]  # strip the leading frontmatter entirely
    assert not text.startswith("---")
    data = strategy.parse_strategy(text)
    assert data["factory_cap"] == 3


# --- unreadable file -----------------------------------------------------------------------------

def test_cli_unreadable_file_exits_nonzero(tmp_path):
    missing = tmp_path / "strategy" / "does-not-exist.md"
    result = _run(str(missing))
    assert result.returncode != 0
    assert "unreadable" in result.stdout
