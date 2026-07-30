"""Acceptance tests for issue #347 — the standalone gates record, read at claim time.

Derived from the issue's acceptance criteria (the spec), NOT the implementation's internals:

  1. WHEN the runner claims a Task with no native sub-issue parent and whose trail carries no
     well-formed gates record, THE SYSTEM SHALL bounce it to Needs-info naming the missing record.
  2. THE SYSTEM SHALL NOT apply this condition to a task that has a native sub-issue parent, whatever
     that parent's Issue Type.
  3. THE SYSTEM SHALL require the record to carry a review verdict, a fit disposition, and an
     authorship field, each present and non-empty, and refuse the task when any is absent or empty.
  4. THE SYSTEM SHALL require the fit field to carry an architect verdict, and SHALL NOT accept a
     placeholder in its place.
  5. THE SYSTEM SHALL NOT accept an automatic-promotion record or an operator promotion record as a
     gates record.
  6. THE SYSTEM SHALL match the gates record only on a line that is exactly the marker, with no
     leading-whitespace tolerance (trailing whitespace stripped).
  7. THE SYSTEM SHALL make this refusal through the existing Needs-info bounce path (no new exit path,
     no change to the acceptance-criteria parse).
  8. WHEN the runner runs in dry-run mode, THE SYSTEM SHALL report this refusal and write nothing.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers) — no
private clone of the classifier or the gh/claude stubs. `td._issue`'s default issue carries a parent
(exempt from this condition) so every OTHER suite reusing `td._env`/`td._issue` is unaffected; this
suite opts into the standalone shape explicitly by passing `parent=None`.

Most scenarios here are proven read-only via `--dry-run` against a non-git manifest-only repo
(`td._manifest_repo`, "dry-run never touches git") — cheap, and the DoR gate's admission decision
(NEEDS_INFO empty vs. not) is identical whether or not `--dry-run` is passed. Two scenarios go through
the real, non-dry-run pipeline (`td._make_repo`/`td._real`) to prove the claim actually proceeds all the
way through IMPL -> TEST -> CHECK -> REVIEW when the condition doesn't apply.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)

ROOT = td.ROOT


# ============ helpers ============

def _gates_comment(*, marker_line="YR-TASK-GATES", review="reviewed independently, no defects found",
                    fit="fits the intended design and existing architecture", who="afernandez"):
    """One trail comment shaped like a standalone task's own gates record (authoring.md's task step):
    a line that is exactly the marker, plus review:/fit:/who: fields. Pass a field as None to omit its
    line entirely (absent); pass "" to include the line with an empty value."""
    lines = [marker_line]
    for label, value in (("review", review), ("fit", fit), ("who", who)):
        if value is not None:
            lines.append(f"{label}: {value}")
    return {"body": "\n".join(lines)}


def _dryrun(tmp_path, *, number=21, parent=None, comments=(), issue_type="Task", body=None):
    """A --dry-run claim attempt against a non-git manifest-only repo: cheap, and read-only regardless
    of outcome, so it isolates the DoR admission decision (NEEDS_INFO empty vs. not) from every other
    concern (git, worktrees, LLM stages)."""
    binp = tmp_path / "bin"; td._stubs(binp)
    kw = {} if body is None else {"body": body}
    env = td._env(tmp_path, binp, number=number, parent=parent, comments=list(comments),
                  issue_type=issue_type, **kw)
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run([str(number), "--repo", "test/repo", "--dry-run"], env)
    return r, td._timeline(tmp_path)


def _real_claim(tmp_path, *, number=31, parent=None, comments=(), title="Do a standalone thing"):
    """A real (non-dry-run) claim against a real git repo — proves the pipeline actually proceeds
    through IMPL -> TEST -> CHECK -> REVIEW, not merely that the DoR gate would allow it."""
    work, _origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=number, parent=parent,
                                      comments=list(comments), title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run([str(number), "--repo", "test/repo"], env)
    return r, td._timeline(tmp_path)


# ============ 1. no gates record at all -> bounce, naming the missing record ============

def test_parentless_task_with_no_gates_record_bounces_needs_info(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None, comments=[])
    assert r.returncode == 3
    # dry-run's own read-only-ness (criterion 8) is covered separately below; here the point is the
    # bounce fires at all, and never touches an LLM stage.
    assert not td._ran(tl) and "CHECK" not in tl


def test_parentless_task_with_no_gates_record_bounces_needs_info_real(tmp_path):
    """Same condition, but through a real (non-dry-run) claim attempt: Status=Backlog,
    Reason=Needs-info, exactly one comment naming the missing record, and the claim never happens —
    no In Progress transition, no worktree/LLM stage of any kind."""
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=41, parent=None, comments=[])
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run(["41", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl) and "CHECK" not in tl
    assert not td._argv_calls(tmp_path)                 # no LLM stage ever invoked
    edits = " ".join(td._edits(tl))
    assert "InProgress" not in edits                     # never claims
    assert "Backlog" in edits and "NeedsInfo" in edits
    comments = td._comments(tl)
    assert len(comments) == 1
    assert "YR-TASK-GATES" in comments[0]


# ============ 2. a native sub-issue parent exempts the child, whatever its Issue Type ============

def test_task_with_epic_shaped_parent_and_no_record_is_exempt(tmp_path):
    r, tl = _dryrun(tmp_path, parent={"number": 2, "title": "Governing epic"}, comments=[])
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


def test_task_with_feature_shaped_parent_and_no_record_is_exempt(tmp_path):
    r, tl = _dryrun(tmp_path, parent={"number": 3, "title": "Governing feature"}, comments=[])
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


def test_task_with_parent_proceeds_through_the_real_pipeline_without_any_record(tmp_path):
    """The exemption isn't just a DoR-gate opinion: a child task with a parent and NO gates record at
    all actually claims and runs the full pipeline."""
    r, tl = _real_claim(tmp_path, number=32, parent={"number": 9}, comments=[])
    assert r.returncode == 0, r.stderr
    claim_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InProgress" in l)
    inrev_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l)
    assert claim_i < tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW") < inrev_i


# ============ a well-formed record lets a parentless task proceed ============

def test_parentless_task_with_well_formed_record_is_admitted(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment()])
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


def test_parentless_task_with_well_formed_record_proceeds_through_the_real_pipeline(tmp_path):
    r, tl = _real_claim(tmp_path, number=33, parent=None, comments=[_gates_comment()])
    assert r.returncode == 0, r.stderr
    claim_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InProgress" in l)
    inrev_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l)
    assert claim_i < tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW") < inrev_i


def test_well_formed_record_among_several_other_comments_is_still_found(tmp_path):
    """The record need not be the only (or the first) comment on the trail."""
    comments = [{"body": "just some chatter"}, _gates_comment(), {"body": "a later unrelated comment"}]
    r, _tl = _dryrun(tmp_path, parent=None, comments=comments)
    assert r.returncode == 0, r.stderr


def test_marker_line_with_trailing_whitespace_still_matches(tmp_path):
    """Trailing whitespace on the marker line is stripped before the equality check — only LEADING
    whitespace is intolerant (see the indentation test below)."""
    r, _tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment(marker_line="YR-TASK-GATES   ")])
    assert r.returncode == 0, r.stderr


# ============ 3. each of the three fields, absent or empty, refuses the task ============

@pytest.mark.parametrize("field", ["review", "fit", "who"])
def test_missing_field_absent_bounces(tmp_path, field):
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment(**{field: None})])
    assert r.returncode == 3
    assert not td._edits(tl) and not td._comments(tl)   # dry-run: read-only regardless of outcome


@pytest.mark.parametrize("field", ["review", "fit", "who"])
def test_missing_field_empty_bounces(tmp_path, field):
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment(**{field: ""})])
    assert r.returncode == 3


def test_missing_field_bounce_names_the_missing_record_via_comment(tmp_path):
    """A real (non-dry-run) bounce on a record missing one field still writes exactly one comment
    naming the gates record by its marker (not a bare, unexplained refusal)."""
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=52, parent=None,
                   comments=[_gates_comment(review=None)])
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run(["52", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    comments = td._comments(tl)
    assert len(comments) == 1
    assert "YR-TASK-GATES" in comments[0]


@pytest.mark.parametrize("placeholder", ["n/a", "N/A", "none", "None", "exempt", "skipped", "tbd", "-"])
def test_fit_placeholder_is_rejected(tmp_path, placeholder):
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment(fit=placeholder)])
    assert r.returncode == 3


def test_fit_field_with_real_prose_is_accepted_even_if_terse(tmp_path):
    """Only the closed placeholder set is refused — a real (if minimal) verdict passes, even one that
    isn't a glowing review; the rule polices dressed-up exemptions, not judgment quality."""
    r, _tl = _dryrun(tmp_path, parent=None,
                      comments=[_gates_comment(fit="does not fit cleanly but is accepted as a tradeoff")])
    assert r.returncode == 0, r.stderr


# ============ 5. an auto-promotion or operator-promotion record never counts ============

def test_only_auto_promoted_marker_does_not_satisfy_the_gates_record(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None,
                     comments=[{"body": "YR-AUTO-PROMOTED\nsome epic-gate housekeeping text"}])
    assert r.returncode == 3


def test_only_operator_promoted_marker_does_not_satisfy_the_gates_record(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None,
                     comments=[{"body": "YR-PROMOTED\npromoted by an operator"}])
    assert r.returncode == 3


# ============ 6. exact-line matching: no leading-whitespace tolerance, no trailing text ============

def test_indented_marker_line_does_not_match(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment(marker_line="  YR-TASK-GATES")])
    assert r.returncode == 3


def test_marker_with_trailing_text_on_the_same_line_does_not_match(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None,
                     comments=[_gates_comment(marker_line="YR-TASK-GATES please read carefully")])
    assert r.returncode == 3


# ============ 7. existing bounce path only: acceptance-criteria parse untouched, one comment for both ============

def test_acceptance_criteria_bounce_still_fires_unrelated_to_this_gate(tmp_path):
    """A parentless task WITH a well-formed record still bounces on an unrelated, pre-existing DoR
    condition (an empty acceptance-criteria section) — this gate doesn't short-circuit or replace that
    check."""
    r, tl = _dryrun(tmp_path, parent=None, comments=[_gates_comment()], body="### Goal\njust do it\n")
    assert r.returncode == 3


def test_task_failing_both_conditions_gets_one_comment_naming_both(tmp_path):
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=61, parent=None, comments=[], body="### Goal\njust do it\n")
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run(["61", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    comments = td._comments(tl)
    assert len(comments) == 1                            # one bounce comment, not two
    text = comments[0]
    assert "acceptance-criteria" in text.lower()
    assert "YR-TASK-GATES" in text


# ============ 8. dry-run reports the refusal and writes nothing ============

def test_dry_run_reports_missing_record_and_writes_nothing(tmp_path):
    r, tl = _dryrun(tmp_path, parent=None, comments=[])
    assert r.returncode == 3
    assert not td._edits(tl) and not td._comments(tl) and not td._ran(tl)
    assert "YR-TASK-GATES" in r.stderr


# ============ the authoring reference states the gates record's grammar (task step) ============

def test_authoring_md_documents_the_task_gates_record_grammar():
    text = (ROOT / "skills" / "factory" / "references" / "authoring.md").read_text()
    idx = text.index("YR-TASK-GATES")
    nearby = text[max(0, idx - 800): idx + 1500]
    assert "YR-TASK-GATES" in nearby
    for field in ("review:", "fit:", "who:"):
        assert field in nearby
    assert "n/a" in nearby and "tbd" in nearby             # the placeholder set
    assert "parent" in nearby.lower()
    assert "Needs-info" in nearby
