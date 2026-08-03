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

Two known limitations, recorded rather than fixed — the guard wall's recorded-impossibility case
(it-27 § 4: where a finding admits no deterministic predicate, record why and what would have to
be true for one to exist). Both were found by the independent cold review of PR #372.

  1. **The two hosts read different refs.** The runner resolves the manifest from the BASE ref
     (`tools/dev-runner.sh`, the "build from git refs, never a mutable tree" invariant), while
     this CI step reads the manifest at the PR HEAD, because that is the only tree a workflow
     step has checked out. So a PR can weaken or disarm its own lint backstop by editing its own
     `lint_cmd`. No predicate here can catch it: reading the base ref's manifest instead would
     mean a PR could never ADOPT or fix a lint command either, which defeats the slice. What
     would have to be true for a guard to exist: the certification would need the base ref's
     manifest AND a separate, reviewed path for manifest changes — i.e. `.yr/factory.toml` would
     have to become a gate-touching surface in its own right, which is a WHAT-call, not a test.
  2. **Value coercion diverges.** The runner and this step do not agree on every non-string
     `lint_cmd` (a boolean, a multi-line value). "One contract on two hosts" holds for the
     command's SOURCE, which is what the seam is about; it does not hold byte-for-byte across
     every TOML type the key was never meant to carry. Not asserted here because pinning today's
     divergence would freeze it.
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


def _run_script_in(tmp_path, manifest_text, *, raw_bytes=None):
    """Run the extracted Lint shell in a temp cwd carrying `manifest_text` (None = no manifest).

    `bash -e -c`, NOT `bash -c`. GitHub Actions runs a `run:` step as `/usr/bin/bash -e {0}` —
    read off this workflow's own job log (run 30769527323, every step: `shell: /usr/bin/bash -e
    {0}`). The difference is not cosmetic: under `-e` a failing manifest read ABORTS the step,
    while without it execution continues with an empty LINT_CMD and prints a false "no lint_cmd
    declared" no-op. A harness missing `-e` therefore stays green while the real step exits 1 —
    the failure mode where the verification itself is what hides the defect.
    """
    if raw_bytes is not None:
        (tmp_path / ".yr").mkdir(exist_ok=True)
        (tmp_path / ".yr" / "factory.toml").write_bytes(raw_bytes)
    elif manifest_text is not None:
        (tmp_path / ".yr").mkdir(exist_ok=True)
        (tmp_path / ".yr" / "factory.toml").write_text(manifest_text, encoding="utf-8")
    return subprocess.run(["bash", "-e", "-c", _lint_run_script()], cwd=tmp_path,
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
    """The manifest's own lint_cmd must not appear literally in the workflow.

    Parsed with `tomllib`, not a regex: TOML accepts basic strings ("…") AND literal strings
    ('…'), and the literal form is exactly the idiom slice A3 prescribes for regex rules. A
    hand-rolled `"(.+)"` pattern silently fails to find a single-quoted value and then reports
    "declares no lint_cmd", which is a misleading message for a manifest that declares one.
    """
    import tomllib
    declared = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("lint_cmd", "")
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


def test_a_malformed_manifest_fails_loud_rather_than_silently_skipping(tmp_path):
    """A broken manifest is a fact worth failing on, not a reason to skip the gate.

    This is fail-closed by design and NOT a defect to soften: under `bash -e` the parse error
    aborts the step, so a repo whose manifest stopped parsing gets a red job naming the reason
    rather than a green one that quietly linted nothing. The danger is the opposite shape — a
    harness without `-e` reports rc=0 here AND prints "no lint_cmd declared", which is a false
    statement about a manifest that does declare one.
    """
    r = _run_script_in(tmp_path, 'lint_cmd = "unterminated\n')
    assert r.returncode != 0, (
        "a manifest that does not parse produced a GREEN lint step — the job would certify a "
        f"tree nothing linted. stdout={r.stdout!r}"
    )
    assert "no lint_cmd declared" not in r.stdout, (
        "the step reported 'no lint_cmd declared' for a manifest it simply could not parse — "
        "that is a false statement about the repo, not a legible failure"
    )


def test_a_non_utf8_manifest_fails_loud(tmp_path):
    r = _run_script_in(tmp_path, None, raw_bytes=b'lint_cmd = "\xff\xfe caf\xe9"\n')
    assert r.returncode != 0, (
        f"a non-UTF-8 manifest produced a green lint step; stdout={r.stdout!r}"
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
    """A second job means a second checkout (pinned in test_ci_full_history_checkout.py).

    Asserts the COUNT, not a hardcoded name list: this epic's own convention is derive from the
    tree, never enumerate, and `jobs == ["test"]` would misattribute an innocent job rename as
    "the lint step grew a second job".
    """
    jobs = re.findall(r"^  (\w[\w-]*):$", _jobs_block(_ci_text()), re.MULTILINE)
    assert len(jobs) == 1, (
        f"ci.yml declares {len(jobs)} jobs {jobs} — the lint step must ride the single "
        "certification job, never a second one"
    )


def test_workflows_hold_exactly_one_manifest_read():
    """The cardinality issue #365 pins from outside, asserted here from inside.

    Two counting rules, both stated because the number moves with them:

    1. The SURFACE is every YAML file under `.github/workflows/`, not `ci.yml` alone — #365's
       `workflow-manifest-read` rule globs the directory, and a test reading one file would let
       a second workflow carry a second reader while still claiming "the same contract".
    2. A READ is an expression that opens the manifest — `tomllib` (the sanctioned parse) or any
       other command naming the file as an input. Prose is not a reader: the step legitimately
       names `.yr/factory.toml` in its own log output and comments, so mentions are not counted,
       but a `sed`/`grep`/`awk` reader IS, since it evades a tomllib-only rule.
    """
    wf_dir = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"
    readers = []
    for path in sorted(wf_dir.glob("*.y*ml")):
        for ln in path.read_text(encoding="utf-8").splitlines():
            if "tomllib" in ln or re.search(r"\b(sed|grep|awk|cut|python3?)\b[^\n]*factory\.toml", ln):
                readers.append(f"{path.name}: {ln.strip()}")
    assert len(readers) == 1, (
        f"the workflows parse .yr/factory.toml at {len(readers)} sites, expected exactly 1 — a "
        f"second reader is the clone shape this iteration exists to stop:\n" + "\n".join(readers)
    )


def test_lint_runs_after_the_tests():
    """One contract on two hosts: the runner orders lint_cmd after check_cmd."""
    names = [n.lower() for n, _ in _steps(_ci_text())]
    assert "tests" in names and "lint" in names
    assert names.index("lint") > names.index("tests"), (
        "the Lint step runs before Tests — server CI should mirror the runner's own order, "
        "where the lint tier runs after check_cmd passes"
    )
