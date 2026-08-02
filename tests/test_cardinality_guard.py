"""Acceptance tests for it-27 slice A3 (issue #365) — the declarative cardinality guard.

Derived from the it-27 product-spec's acceptance criteria:

  13. IF a declared cardinality is exceeded, THEN THE SYSTEM SHALL fail naming the pattern, the
      count found, the maximum declared, and the reason recorded for it.
  24. THE SYSTEM SHALL apply every rule through per-repo declarations, and SHALL assume no
      language, no file layout, and no toolchain.

Plus the two structural commitments the crossing made for this slice:
  - every shipped rule is TRUE AT THIS SLICE'S LANDING REF (a rule declaring a max equal to
    today's offender count ratifies the finding instead of retiring it), and specifically NO
    manifest-reader rule for `tools/dev-runner.sh` — eight readers exist here, and the slice that
    can honestly assert one is round 2's item B2, which collapses them;
  - the two bespoke guards two rules replace are DELETED, so this is a consolidation rather than
    an addition.

The surface question is the sharp one. `qa/cardinality.py` enumerates with
`git ls-files --cached --others --exclude-standard`, and both halves matter: the tracked half
keeps sibling checkouts under `.claude/worktrees/` out of the verdict (a live defect in another
guard in this repo, which this instrument must not reproduce), and the untracked half is what
makes the guard see a file the implementer just created — the tier runs BEFORE the commit, so a
tracked-only scan would be blind to exactly the new code it exists to check.
"""

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
RUNNER = REPO / "qa" / "cardinality.py"
CONFIG = REPO / "qa" / "cardinality.toml"


def _run(config=None, cwd=None):
    argv = [sys.executable, str(RUNNER)]
    if config is not None:
        argv.append(str(config))
    return subprocess.run(argv, cwd=cwd or REPO, capture_output=True, text=True)


def _cfg(tmp_path, body):
    p = tmp_path / "rules.toml"
    p.write_text(body, encoding="utf-8")
    return p


# --- criterion 13: the failure names all four fields ----------------------------------------

def test_exceeding_a_declared_maximum_fails(tmp_path):
    cfg = _cfg(tmp_path, """
[[rule]]
id = "too-many"
pattern = '''^def '''
paths = ["qa/cardinality.py"]
max = 1
reason = "a test rule"
birth = "#365"
""")
    r = _run(cfg)
    assert r.returncode == 1, f"an exceeded cardinality did not fail (rc={r.returncode})"


def test_the_failure_names_pattern_count_maximum_and_reason(tmp_path):
    cfg = _cfg(tmp_path, """
[[rule]]
id = "named-fields"
pattern = '''^import '''
paths = ["qa/cardinality.py"]
max = 0
reason = "THE-RECORDED-REASON"
birth = "#365"
""")
    r = _run(cfg)
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "^import " in out, "the failure does not name the pattern"
    assert "maximum:  0" in out, "the failure does not name the declared maximum"
    assert "THE-RECORDED-REASON" in out, "the failure does not name the recorded reason"
    assert "found:" in out, "the failure does not name the count found"


def test_the_failure_lists_the_offending_sites(tmp_path):
    """Actionable without re-running anything."""
    cfg = _cfg(tmp_path, """
[[rule]]
id = "sites"
pattern = '''^import fnmatch$'''
paths = ["qa/cardinality.py"]
max = 0
reason = "a test rule"
birth = "#365"
""")
    r = _run(cfg)
    assert "qa/cardinality.py:" in r.stdout + r.stderr, "no file:line list in the failure output"


def test_a_rule_at_its_maximum_passes_silently(tmp_path):
    cfg = _cfg(tmp_path, """
[[rule]]
id = "at-max"
pattern = '''^import fnmatch$'''
paths = ["qa/cardinality.py"]
max = 1
reason = "a test rule"
birth = "#365"
""")
    r = _run(cfg)
    assert r.returncode == 0
    assert r.stdout.strip() == "", f"a rule at its max should be silent; got {r.stdout!r}"


def test_a_rule_below_its_maximum_advises_but_does_not_gate(tmp_path):
    """A ceiling, like a floor, otherwise rots green after a consolidation."""
    cfg = _cfg(tmp_path, """
[[rule]]
id = "slack"
pattern = '''^import fnmatch$'''
paths = ["qa/cardinality.py"]
max = 4
reason = "a test rule"
birth = "#365"
""")
    r = _run(cfg)
    assert r.returncode == 0, "the slack advisory must never gate"
    assert "stale" in r.stdout, f"no slack advisory emitted; got {r.stdout!r}"


# --- fail-closed on any malformed declaration ----------------------------------------------

@pytest.mark.parametrize("field", ["id", "pattern", "paths", "max", "reason", "birth"])
def test_a_missing_required_field_refuses_the_run(tmp_path, field):
    lines = {
        "id": 'id = "r"', "pattern": "pattern = '''x'''", "paths": 'paths = ["qa/cardinality.py"]',
        "max": "max = 1", "reason": 'reason = "why"', "birth": 'birth = "#365"',
    }
    body = "[[rule]]\n" + "\n".join(v for k, v in lines.items() if k != field) + "\n"
    r = _run(_cfg(tmp_path, body))
    assert r.returncode == 2, (
        f"a rule missing `{field}` did not refuse the run (rc={r.returncode}) — a rule set that "
        "cannot be trusted must never silently enforce the subset that happens to parse"
    )
    assert field in r.stderr, f"the refusal does not name the missing field `{field}`"


def test_an_empty_reason_refuses_the_run(tmp_path):
    """A rule without a reason cannot satisfy criterion 13, so it cannot be declared."""
    r = _run(_cfg(tmp_path, """
[[rule]]
id = "r"
pattern = '''x'''
paths = ["qa/cardinality.py"]
max = 1
reason = "   "
birth = "#365"
"""))
    assert r.returncode == 2


def test_an_invalid_regex_refuses_the_run(tmp_path):
    r = _run(_cfg(tmp_path, """
[[rule]]
id = "r"
pattern = '''([unclosed'''
paths = ["qa/cardinality.py"]
max = 1
reason = "why"
birth = "#365"
"""))
    assert r.returncode == 2 and "regex" in r.stderr


def test_a_path_escaping_the_repo_refuses_the_run(tmp_path):
    r = _run(_cfg(tmp_path, """
[[rule]]
id = "r"
pattern = '''x'''
paths = ["../../etc/passwd"]
max = 1
reason = "why"
birth = "#365"
"""))
    assert r.returncode == 2, "a `..` path was accepted — the surface must stay repo-relative"


def test_a_duplicate_rule_id_refuses_the_run(tmp_path):
    body = """
[[rule]]
id = "dup"
pattern = '''x'''
paths = ["qa/cardinality.py"]
max = 1
reason = "why"
birth = "#365"

[[rule]]
id = "dup"
pattern = '''y'''
paths = ["qa/cardinality.py"]
max = 1
reason = "why"
birth = "#365"
"""
    r = _run(_cfg(tmp_path, body))
    assert r.returncode == 2, "duplicate ids were accepted — the id keys the failure message"


def test_a_missing_config_refuses_the_run(tmp_path):
    r = _run(tmp_path / "nope.toml")
    assert r.returncode == 2


# --- the surface: untracked files must be visible -------------------------------------------

def test_a_newly_created_untracked_file_is_in_the_surface(tmp_path):
    """The tier runs BEFORE the commit, so the implementer's new file is untracked at scan time.

    A tracked-only scan would make the guard blind to exactly the code it exists to check — the
    ninth copy of a contract, in a brand-new file, would sail through and become visible one
    commit too late.
    """
    new = REPO / "qa" / "_cardinality_surface_probe.py"
    new.write_text("MARKER_UNTRACKED_PROBE = 1\n", encoding="utf-8")
    try:
        cfg = _cfg(tmp_path, """
[[rule]]
id = "probe"
pattern = '''MARKER_UNTRACKED_PROBE'''
paths = ["qa/*.py"]
max = 0
reason = "the surface must include untracked files"
birth = "#365"
""")
        r = _run(cfg)
        assert r.returncode == 1, (
            "an untracked file was invisible to the guard — a pre-commit tier that cannot see "
            "new files is blind to the shape it is meant to stop"
        )
    finally:
        new.unlink(missing_ok=True)


def test_the_surface_excludes_sibling_worktrees():
    """Enumeration is git-derived, so `.claude/worktrees/` never enters a verdict."""
    src = RUNNER.read_text(encoding="utf-8")
    assert "ls-files" in src, "the guard does not enumerate from git — a walk picks up worktrees"
    assert "--exclude-standard" in src, ".gitignore is not honoured by the enumeration"


# --- criterion 24 + the crossing's structural commitments ------------------------------------

def test_the_runner_assumes_no_language_or_toolchain():
    src = RUNNER.read_text(encoding="utf-8")
    for forbidden in ("import ast", "ast.parse", "subprocess.run([\"ruff", "pytest"):
        assert forbidden not in src, (
            f"qa/cardinality.py references {forbidden!r} — the tier must be plain regexes over "
            "file text and plain globs over paths, so an opaque lint_cmd carries it in any repo"
        )


def test_this_repos_rule_set_holds_at_this_ref():
    """Every shipped rule is true at its own landing ref — the discipline, not a coincidence."""
    r = _run()
    assert r.returncode == 0, f"the shipped rule set does not hold at this ref:\n{r.stderr}"


def test_no_manifest_reader_rule_is_shipped_for_the_runner():
    """Eight readers exist in tools/dev-runner.sh at this ref.

    A rule declaring `max = 8` would ratify the finding instead of retiring it, and `max = 1`
    would be false at landing. The only slice that can honestly assert one is round 2's item B2,
    which collapses them — it ships that rule, under this same wall.
    """
    text = CONFIG.read_text(encoding="utf-8")
    assert "tools/dev-runner.sh" in text, "expected the verdict-pipeline rule to name the runner"
    assert "tomllib" not in text.split("[[rule]]")[1], "unexpected manifest rule on the first rule"
    for block in text.split("[[rule]]")[1:]:
        if "tools/dev-runner.sh" in block:
            assert "import sys" not in block and "tomllib" not in block, (
                "a manifest-reader rule for tools/dev-runner.sh is shipped here — it belongs to "
                "round 2's item B2, the slice that collapses the eight readers"
            )


def test_the_manifest_declares_the_runner_in_lint_cmd():
    manifest = (REPO / ".yr" / "factory.toml").read_text(encoding="utf-8")
    line = next(ln for ln in manifest.splitlines() if ln.startswith("lint_cmd"))
    assert "qa/cardinality.py" in line, (
        "the cardinality runner is not carried by lint_cmd — an unwired guard is advisory by "
        "accident, and this tier is blocking by design"
    )


def test_the_replaced_bespoke_guards_are_gone():
    """A consolidation, not an addition: the migrated shapes leave exactly one home."""
    v = (REPO / "tests" / "test_verdict_grammar_consolidation.py").read_text(encoding="utf-8")
    c = (REPO / "tests" / "test_ci_full_history_checkout.py").read_text(encoding="utf-8")
    assert "def test_dev_runner_sh_has_exactly_one_raw_verdict_extraction_pipeline" not in v
    assert "def test_ci_workflow_has_exactly_one_checkout_step" not in c
    assert "qa/cardinality.toml" in v and "qa/cardinality.toml" in c, (
        "the migrated guards left no pointer to their new home — a later reader would read the "
        "deletion as a lost assertion"
    )
