"""Acceptance tests for it-27 slice A1 (issue #363) — the CI lint backstop.

Derived from the slice's acceptance criteria, NOT from the workflow's incidental formatting:

  1. The certification job runs the repo's declared `lint_cmd`, READ from `.yr/factory.toml`
     rather than restated in the workflow. A second declaration is the drift twin the seam
     contract forbids — the manifest is the single home for what lint means in this repo.
  2. WHERE the manifest declares no `lint_cmd`, the step is a no-op and does not fail the job
     (capability-defaults-off, the `auto_merge` precedent it-17 established for the tier).
  3. The step rides the EXISTING job. A second job means a second checkout, which breaks the
     one-checkout pin in test_ci_full_history_checkout.py — that assertion is NOT duplicated
     here; it lives there and this suite must not grow a twin of it.
  4. The workflow holds exactly ONE manifest read. Issue #365 lands a declared cardinality rule
     (`workflow-manifest-read`, max 1) that pins this from the outside; this test is the same
     contract asserted from inside, and is the shape that rule will be true of.

Why the spec has no EARS criterion for this slice: § 7 argues the CI backstop in prose
("attended commits never meet the runner at all, and a local hook is per-clone and bypassable")
while criterion 20 bounds only the PRE-commit mutation paths. CI runs after the commit, so the
acceptance below is written from that prose rather than lifted from a criterion — recorded here
because a later reader should not mistake the absence for an oversight.

On injection: the step runs a command string read from a repo file, on `pull_request`. That adds
no attack surface — the same job already executes repo code from the PR head (`pytest tests/`),
so a fork PR that could poison `lint_cmd` could equally poison a test. The step uses no `${{ }}`
interpolation of event data, which is where workflow injection actually lives.

Text-based parsing throughout: this repo declares no YAML parser (`requirements-dev.txt` has
none), and the slice ships no new dependency, so the existing regex idiom in
test_ci_run_economy.py / test_ci_full_history_checkout.py is followed rather than replaced.
"""

import pathlib
import re
import subprocess
import textwrap

CI_PATH = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
MANIFEST_PATH = pathlib.Path(__file__).resolve().parents[1] / ".yr" / "factory.toml"


def _ci_text():
    return CI_PATH.read_text(encoding="utf-8")


def _steps(text):
    """[(name, body)] for every `- name: X` step, body = the lines up to the next step."""
    out = []
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\s*- name:\s*\S", ln)]
    for idx, i in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        name = re.match(r"^\s*- name:\s*(.+?)\s*$", lines[i]).group(1)
        out.append((name, "\n".join(lines[i:end])))
    return out


def _lint_step():
    for name, body in _steps(_ci_text()):
        if name.lower() == "lint":
            return body
    return None


def _lint_run_script():
    """The Lint step's `run: |` block, dedented — the actual shell the runner executes."""
    body = _lint_step()
    assert body is not None, "ci.yml has no step named 'Lint'"
    lines = body.splitlines()
    start = next(i for i, ln in enumerate(lines) if re.match(r"^\s*run:\s*\|\s*$", ln))
    indent = len(lines[start]) - len(lines[start].lstrip())
    script = []
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        script.append(ln)
    return textwrap.dedent("\n".join(script))


def _run_script_in(tmp_path, manifest_text):
    """Run the extracted Lint shell in a temp cwd carrying `manifest_text` (None = no manifest)."""
    if manifest_text is not None:
        (tmp_path / ".yr").mkdir(exist_ok=True)
        (tmp_path / ".yr" / "factory.toml").write_text(manifest_text, encoding="utf-8")
    return subprocess.run(["bash", "-c", _lint_run_script()], cwd=tmp_path,
                          capture_output=True, text=True)


# --- 1. the command is read from the manifest, never restated ------------------------------

def test_ci_workflow_has_a_lint_step():
    assert _lint_step() is not None, (
        "ci.yml declares no 'Lint' step — the certification runs no lint backstop, so an "
        "attended commit (which never meets the runner) reaches main unlinted"
    )


def test_lint_step_reads_the_command_from_the_manifest():
    body = _lint_step()
    assert ".yr/factory.toml" in body, (
        "the Lint step does not read .yr/factory.toml — the manifest is the seam, and a lint "
        "command that does not come from it is a second declaration"
    )
    assert "lint_cmd" in body, "the Lint step does not read the `lint_cmd` key"


def test_lint_step_does_not_restate_the_declared_command():
    """The manifest's own lint_cmd must not appear literally in the workflow."""
    declared = ""
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*lint_cmd\s*=\s*"(.+)"\s*$', line)
        if m:
            declared = m.group(1)
            break
    assert declared, "this repo's .yr/factory.toml declares no lint_cmd to test against"
    assert declared not in _ci_text(), (
        f"ci.yml restates the manifest's lint_cmd ({declared!r}) instead of reading it — two "
        "declarations of one contract is the drift twin the seam forbids"
    )


# --- 2. absent lint_cmd is a no-op, never a failure ----------------------------------------

def test_lint_step_is_a_no_op_when_the_manifest_declares_no_lint_cmd(tmp_path):
    r = _run_script_in(tmp_path, 'check_cmd = "pytest tests/ -q"\n')
    assert r.returncode == 0, (
        f"the Lint step failed a repo that declares no lint_cmd (rc={r.returncode}) — the tier "
        f"is capability-defaults-off, so an undeclared lint must not fail a job.\n{r.stderr}"
    )
    assert "no-op" in r.stdout.lower() or "no lint_cmd" in r.stdout.lower(), (
        f"the no-op path produced no legible reason on stdout: {r.stdout!r}"
    )


def test_lint_step_is_a_no_op_when_there_is_no_manifest_at_all(tmp_path):
    r = _run_script_in(tmp_path, None)
    assert r.returncode == 0, (
        f"the Lint step failed a repo with no .yr/factory.toml (rc={r.returncode}) — the read "
        f"must yield empty, not raise.\n{r.stderr}"
    )


# --- 3. the declared command actually runs, and its failure is the job's failure -------------

def test_lint_step_runs_the_declared_command(tmp_path):
    r = _run_script_in(tmp_path, 'lint_cmd = "echo LINT-RAN-OK"\n')
    assert r.returncode == 0, f"declared lint_cmd did not run cleanly: {r.stderr}"
    assert "LINT-RAN-OK" in r.stdout, (
        f"the declared lint_cmd was read but never executed; stdout was {r.stdout!r}"
    )


def test_lint_step_fails_the_job_when_the_declared_command_fails(tmp_path):
    r = _run_script_in(tmp_path, 'lint_cmd = "exit 7"\n')
    assert r.returncode != 0, (
        "a failing lint_cmd did not fail the step — the backstop would be advisory, and the "
        "tier is blocking by design (it-17)"
    )


def test_lint_step_reports_the_command_it_is_about_to_run(tmp_path):
    """Legible failure: the log names what ran, so a red job is diagnosable from the log alone."""
    r = _run_script_in(tmp_path, 'lint_cmd = "echo hello"\n')
    assert "echo hello" in r.stdout, (
        f"the step does not echo the command it read; stdout was {r.stdout!r}"
    )


# --- 4. one job, one manifest read ----------------------------------------------------------

def _jobs_block(text):
    """The `jobs:` mapping only — `on:`'s children are also two-space keys and must not count."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.rstrip() == "jobs:")
    return "\n".join(lines[start + 1:])


def test_lint_step_rides_the_existing_job():
    """A second job means a second checkout (pinned in test_ci_full_history_checkout.py)."""
    jobs = re.findall(r"^  (\w[\w-]*):$", _jobs_block(_ci_text()), re.MULTILINE)
    assert jobs == ["test"], (
        f"ci.yml declares jobs {jobs} — the lint step must ride the single certification job, "
        "never a second one"
    )


def test_workflow_holds_exactly_one_manifest_read():
    """The cardinality issue #365 pins from outside, asserted here from inside.

    Counting rule, stated because the number moves with it: a *read* is an expression that
    PARSES the manifest (`tomllib`), not any line that mentions the path — the step legitimately
    names `.yr/factory.toml` in its own log output and in comments, and prose is not a reader.
    """
    reads = [ln for ln in _ci_text().splitlines() if "tomllib" in ln]
    assert len(reads) == 1, (
        f"ci.yml parses the manifest at {len(reads)} sites, expected exactly 1 — a second "
        f"reader is the clone shape this iteration exists to stop:\n" + "\n".join(reads)
    )


def test_lint_runs_after_the_tests():
    """One contract on two hosts: the runner orders lint_cmd after check_cmd."""
    names = [n.lower() for n, _ in _steps(_ci_text())]
    assert "tests" in names and "lint" in names
    assert names.index("lint") > names.index("tests"), (
        "the Lint step runs before Tests — server CI should mirror the runner's own order, "
        "where the lint tier runs after check_cmd passes"
    )
