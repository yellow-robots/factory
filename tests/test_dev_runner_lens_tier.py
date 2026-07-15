"""Acceptance tests for issue #214 — check gate: manifest-declared lens seam (advisory, PR-trail landing).

Derived from the issue's ACCEPTANCE CRITERIA (the spec), NOT the runner's internals:

  * WHEN a repo declares `lens_cmd`, it runs AFTER check_cmd (and lint_cmd, when declared) pass, with
    YR_BASE_REF exported, stdout -> the run dir's lens.md, stderr -> a SEPARATE lens.log.
  * An advisory finding never alters an exit code: a non-zero lens exit (126/127 included) becomes a
    one-line legible note in the artifact, and the run's terminal state is identical to a passing lens.
  * WHEN lens.md is non-empty and a PR exists, it is posted exactly ONCE as its own PR comment whose
    first line is `YR-LENS (advisory)`; an empty artifact posts nothing; a Blocked run (no PR) leaves it
    unposted in the run dir.
  * WHEN no `lens_cmd` is declared, the runner behaves byte-identically to today.
  * The lens content never enters the PR body or the review bundle.
  * The dry-run JSON reports `lens_cmd`; explicit env overrides the manifest.

Reuses the stubbed harness in tests/test_dev_runner.py (the stage-aware gh/claude/check stubs and the
real-git happy-path helpers) to drive tools/dev-runner.sh end-to-end, then inspects the artifacts and the
captured PR-comment bodies. Assertions are on artifact presence/content and board state — never on log
prose. Runs under `.venv/bin/python -m pytest tests/ -q` (system python3 works too — no third-party deps).
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as base  # the shared stub harness (gh/claude/check stubs + real-git helpers)


# ---- the lens stub: an OPAQUE command the runner runs verbatim (run_lens). It records that it ran and
# the YR_BASE_REF it inherited (STUB_LENS_TL), optionally emits distinct stdout (STUB_LENS_EMIT) and
# stderr (STUB_LENS_STDERR) tokens, and optionally exits non-zero (STUB_LENS_EXIT) — so the stdout->lens.md
# / stderr->lens.log split, the advisory-never-gates rule, and the posted-comment content are all provable.
LENS_STUB = '''#!/usr/bin/env bash
[ -n "${STUB_LENS_TL:-}" ] && printf 'LENS YR_BASE_REF=%s\\n' "${YR_BASE_REF:-unset}" >> "$STUB_LENS_TL"
[ -n "${STUB_TIMELINE:-}" ] && echo LENS >> "$STUB_TIMELINE"
[ -n "${STUB_LENS_STDERR:-}" ] && printf '%s\\n' "$STUB_LENS_STDERR" >&2
[ -n "${STUB_LENS_EMIT:-}" ] && printf '%s\\n' "$STUB_LENS_EMIT"
exit "${STUB_LENS_EXIT:-0}"
'''


def _lens_bin(tmp):
    """The base stubs (gh/claude/check) plus the opaque lens.sh, in the harness's usual bin dir."""
    binp = tmp / "bin"
    base._stubs(binp)
    base._exec(binp / "lens.sh", LENS_STUB)
    return binp


def _lens_env(tmp, *, title="Lens tier", number=5, emit="advisory: 3 findings", declare_lens=True):
    """A real-git flow env with the lens tier wired via explicit LENS_CMD (env > manifest). By default the
    lens emits a non-empty stdout token so the happy path posts a comment; pass emit=None for an empty run."""
    work, _ = base._make_repo(tmp)
    binp = _lens_bin(tmp)
    env = base._real(tmp, base._env(tmp, binp, number=number, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LENS_TL"] = str(tmp / "lens_tl")
    if emit is not None:
        env["STUB_LENS_EMIT"] = emit
    if declare_lens:
        env["LENS_CMD"] = f"bash {binp / 'lens.sh'}"
    return env, work, binp


def _lens_tl(tmp):
    p = tmp / "lens_tl"
    return p.read_text().splitlines() if p.exists() else []


def _lens_md(tmp, number=5):
    p = base._run_dir(tmp, number) / "lens.md"
    return p.read_text() if p.exists() else None


def _lens_log(tmp, number=5):
    p = base._run_dir(tmp, number) / "lens.log"
    return p.read_text() if p.exists() else None


def _pr_comment_chunks(tmp):
    """Every captured PR-comment body (STUB_PRCOMMENTS), split on the harness's per-comment boundary."""
    raw = base._prcomments(tmp)
    return [c.strip("\n") for c in raw.split("=== PRCOMMENT ===") if c.strip()]


def _lens_comments(tmp):
    """The captured PR comments whose FIRST line is exactly `YR-LENS (advisory)`."""
    out = []
    for chunk in _pr_comment_chunks(tmp):
        lines = chunk.splitlines()
        if lines and lines[0] == "YR-LENS (advisory)":
            out.append(chunk)
    return out


# ============ criterion 6: the dry-run JSON reports lens_cmd; explicit env overrides the manifest ============

def test_dryrun_reports_lens_cmd_from_manifest(tmp_path):
    """A repo's manifest lens_cmd surfaces in the dry-run JSON when no env override is set."""
    repo = base._manifest_repo(tmp_path, lens_cmd="scripts/lens.sh")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["lens_cmd"] == "scripts/lens.sh"


def test_dryrun_lens_absent_reports_empty(tmp_path):
    """No manifest lens_cmd and no env override -> reports empty (absent = off)."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._env(tmp_path, binp); env["BASE_REPO"] = str(base._manifest_repo(tmp_path))
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["lens_cmd"] == ""


def test_dryrun_env_lens_cmd_overrides_manifest(tmp_path):
    """Explicit LENS_CMD in the env wins over the manifest (env > manifest > default)."""
    repo = base._manifest_repo(tmp_path, lens_cmd="scripts/lens.sh")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env["LENS_CMD"] = "node lens.js"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["lens_cmd"] == "node lens.js"


# ============ criterion 4: no lens_cmd declared -> byte-identical to today ============

def test_no_lens_cmd_is_byte_identical_to_today(tmp_path):
    """With no lens_cmd declared, the lens tier is inert: lens.sh is never invoked, no lens.md / lens.log
    artifact exists, no YR-LENS comment is posted, and the build proceeds to a PR / In Review as always."""
    env, work, binp = _lens_env(tmp_path, title="No lens declared", declare_lens=False, emit=None)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert _lens_tl(tmp_path) == []                        # the lens command was never invoked
    assert _lens_md(tmp_path) is None                      # no lens.md artifact at all
    assert _lens_log(tmp_path) is None                     # no lens.log artifact at all
    assert _lens_comments(tmp_path) == []                  # nothing posted
    tl = base._timeline(tmp_path)
    assert "LENS" not in tl
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


# ============ criterion 1: lens runs AFTER the green gates, YR_BASE_REF exported, stdout/stderr split ========

def test_lens_runs_after_check_with_base_ref_and_stream_split(tmp_path):
    """A declared, green lens runs strictly AFTER the check gate (LENS follows CHECK in the shared
    timeline), with YR_BASE_REF exported to it; its stdout lands in lens.md and its stderr in a SEPARATE
    lens.log — never merged."""
    env, work, binp = _lens_env(tmp_path, title="Lens after check", emit="LENS-STDOUT-TOKEN")
    env["STUB_LENS_STDERR"] = "LENS-STDERR-TOKEN"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    # ordering: the lens ran once, and only after the check gate.
    lens_tl = _lens_tl(tmp_path)
    assert len(lens_tl) == 1 and lens_tl[0].startswith("LENS ")
    tl = base._timeline(tmp_path)
    assert "CHECK" in tl and "LENS" in tl
    assert tl.index("LENS") > tl.index("CHECK")            # lens strictly after the check gate
    # YR_BASE_REF was exported to the lens, matching the run's base ref (origin/main here).
    assert "YR_BASE_REF=origin/main" in lens_tl[0]
    # stdout -> lens.md, stderr -> lens.log; the two streams are never merged.
    md = _lens_md(tmp_path); log = _lens_log(tmp_path)
    assert "LENS-STDOUT-TOKEN" in md and "LENS-STDERR-TOKEN" not in md
    assert "LENS-STDERR-TOKEN" in log and "LENS-STDOUT-TOKEN" not in log


def test_lens_not_run_until_check_passes(tmp_path):
    """lens runs strictly AFTER check_cmd passes: when the check gate fails unrepairably the run Blocks at
    the check gate and the lens command is NEVER invoked (no lens.md, no lens marker)."""
    env, work, binp = _lens_env(tmp_path, title="Lens gated behind check")
    env["STUB_CHECK_FAIL"] = "1"; env["STUB_REPAIR_NOFIX"] = "1"   # check fails, repair can't heal it
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout
    assert _lens_tl(tmp_path) == []                        # lens never ran — check never passed
    assert _lens_md(tmp_path) is None
    assert _lens_comments(tmp_path) == []


def test_lens_runs_only_after_lint_passes(tmp_path):
    """WHEN lint_cmd is also declared, the lens runs AFTER it: a lint that fails unrepairably Blocks the
    run at the lint gate and the lens command is never invoked."""
    env, work, binp = _lens_env(tmp_path, title="Lens gated behind lint")
    base._exec(binp / "lint.sh", base.LINT_STUB)
    env["LINT_CMD"] = f"bash {binp / 'lint.sh'}"
    env["STUB_LINT_TL"] = str(tmp_path / "lint_tl")
    env["STUB_LINT_FAIL"] = "1"                            # lint fails and (no fix cmd) can't be healed
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout
    assert _lens_tl(tmp_path) == []                        # lens never ran — lint never passed
    assert _lens_md(tmp_path) is None


def test_lens_runs_after_lint_and_check_both_green(tmp_path):
    """WHEN both lint_cmd and lens_cmd are declared and green, both run and the build proceeds to a PR;
    the lens advisory comment is posted."""
    env, work, binp = _lens_env(tmp_path, title="Lint + lens green", emit="advisory finding")
    base._exec(binp / "lint.sh", base.LINT_STUB)
    env["LINT_CMD"] = f"bash {binp / 'lint.sh'}"
    env["STUB_LINT_TL"] = str(tmp_path / "lint_tl")
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert len(_lens_tl(tmp_path)) == 1                    # lens ran
    assert len(_lens_comments(tmp_path)) == 1             # advisory comment posted


# ============ criterion 2: an advisory finding never alters an exit code ============

def _terminal_state(r, tmp):
    """The run's terminal state as observable board facts: return code, PR opened, and the exact sequence
    of Status/Reason board edits — independent of the (allowed) artifact differences a failing lens leaves."""
    tl = base._timeline(tmp)
    return (r.returncode, "https://stub/pr/1" in r.stdout, base._edits(tl))


def test_passing_lens_terminal_state(tmp_path):
    """Baseline: a green lens reaches a PR / In Review with no Blocked edit — the reference terminal state
    the failing-lens runs below must match byte-for-byte on the board."""
    env, work, binp = _lens_env(tmp_path, title="Lens exit", emit="finding")
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rc, pr, edits = _terminal_state(r, tmp_path)
    assert rc == 0 and pr is True
    assert any("STATUSFIELD" in e and "InReview" in e for e in edits)
    assert not any("Blocked" in e for e in edits)


def test_failing_lens_does_not_alter_terminal_state(tmp_path):
    """A non-zero lens exit alters NO exit path: the terminal board state is identical to the passing-lens
    baseline, and the failure surfaces only as a one-line legible note appended to the artifact."""
    pass_root = tmp_path / "pass"; pass_root.mkdir()
    fail_root = tmp_path / "fail"; fail_root.mkdir()

    # baseline: same run, passing lens.
    base_env, _, _ = _lens_env(pass_root, title="Lens exit", emit="finding")
    rb = base._run(["5", "--repo", "test/repo"], base_env)
    baseline = _terminal_state(rb, pass_root)

    # variant: identical run, but the lens exits non-zero.
    env, work, binp = _lens_env(fail_root, title="Lens exit", emit="finding")
    env["STUB_LENS_EXIT"] = "1"
    rf = base._run(["5", "--repo", "test/repo"], env)
    variant = _terminal_state(rf, fail_root)

    assert variant == baseline                             # terminal board state is identical
    assert rf.returncode == 0                              # advisory: never gates
    md = _lens_md(fail_root)
    assert "exit 1" in md and "did not run cleanly" in md  # the one-line legible note is in the artifact


def test_lens_env_failure_127_is_still_advisory(tmp_path):
    """A lens that cannot execute at all (exit 127 — command not found; 126 is the sibling) is STILL purely
    advisory: no env hold, no Blocked, the run reaches a PR, and the note names the exit code."""
    env, work, binp = _lens_env(tmp_path, title="Lens 127", emit=None)
    env["STUB_LENS_EXIT"] = "127"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)
    assert not any("Blocked" in e for e in base._edits(tl))
    md = _lens_md(tmp_path)
    assert "exit 127" in md                                # 126/127 folded into the same advisory note


# ============ criterion 3: non-empty -> one comment (YR-LENS advisory); empty -> nothing ============

def test_nonempty_lens_posts_exactly_once_with_marker_first_line(tmp_path):
    """A non-empty lens.md with a PR present posts EXACTLY ONE comment whose first line is exactly
    `YR-LENS (advisory)` and whose body carries the lens content."""
    env, work, binp = _lens_env(tmp_path, title="Lens posts once", emit="LENS-BODY-TOKEN")
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    comments = _lens_comments(tmp_path)
    assert len(comments) == 1                              # posted exactly once
    assert comments[0].splitlines()[0] == "YR-LENS (advisory)"
    assert "LENS-BODY-TOKEN" in comments[0]
    # the marker line is unique across the whole comment stream (posted a single time).
    assert base._prcomments(tmp_path).count("YR-LENS (advisory)") == 1


def test_empty_lens_posts_nothing(tmp_path):
    """An empty lens artifact (the lens ran green but emitted nothing) posts NO comment — yet the lens did
    run and the build still proceeds to a PR / In Review."""
    env, work, binp = _lens_env(tmp_path, title="Empty lens", emit=None)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert len(_lens_tl(tmp_path)) == 1                    # the lens DID run
    md = _lens_md(tmp_path)
    assert md == "" or md is None or md.strip() == ""      # ...but produced an empty artifact
    assert _lens_comments(tmp_path) == []                  # so nothing was posted
    tl = base._timeline(tmp_path)
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


def test_lens_comment_stderr_never_posted(tmp_path):
    """The posted advisory comment carries only the lens's stdout artifact — its stderr (which lands in the
    SEPARATE lens.log, e.g. a traceback) never reaches the PR comment."""
    env, work, binp = _lens_env(tmp_path, title="Lens stderr not posted", emit="VISIBLE-STDOUT")
    env["STUB_LENS_STDERR"] = "SECRET-STDERR-TRACEBACK"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    comments = _lens_comments(tmp_path)
    assert len(comments) == 1
    assert "VISIBLE-STDOUT" in comments[0]
    assert "SECRET-STDERR-TRACEBACK" not in comments[0]
    # and not anywhere in the full posted-comment stream, either.
    assert "SECRET-STDERR-TRACEBACK" not in base._prcomments(tmp_path)


# ============ criterion 3 (blocked branch): a Blocked run (no PR) leaves lens.md unposted ============

def test_blocked_run_leaves_lens_unposted_in_run_dir(tmp_path):
    """A run that reaches the lens tier (check green) but then Blocks at review — so no PR is ever opened —
    still has lens.md in the run dir, and it is left UNPOSTED (no YR-LENS comment). This is correct behavior."""
    env, work, binp = _lens_env(tmp_path, title="Blocked leaves lens", emit="advisory")
    env.update({"STUB_REVIEW_BLOCK": "1", "STUB_REVIEW_NOFIX": "1"})   # review blocks unrepairably
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout   # Blocked, no PR
    assert "Blocked" in " ".join(base._edits(base._timeline(tmp_path)))
    assert len(_lens_tl(tmp_path)) == 1                    # the lens DID run (check was green)
    md = _lens_md(tmp_path)
    assert md is not None and "advisory" in md             # the artifact is present in the run dir
    assert _lens_comments(tmp_path) == []                  # ...but never posted (no PR existed)


# ============ criterion 5: the lens content never enters the PR body or the review bundle ============

def test_lens_content_absent_from_pr_body_and_review_bundle(tmp_path):
    """The lens content lands ONLY on its own advisory comment — never in the PR body (the `gh pr create`
    call the harness records) nor in the review bundle the reviewer consumed."""
    token = "LENS-ONLY-CONTENT-TOKEN"
    env, work, binp = _lens_env(tmp_path, title="Lens isolation", emit=token)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert len(_lens_comments(tmp_path)) == 1              # it DID reach its own comment

    # the PR body travels on `gh pr create --body ...`, recorded to STUB_GH_CALLS by the gh stub.
    gh_calls = (tmp_path / "gh_calls")
    gh_calls_text = gh_calls.read_text() if gh_calls.exists() else ""
    assert token not in gh_calls_text                      # never in the PR body

    # the review bundle the reviewer read is assembled before any PR exists — the lens must not be in it.
    bundle = base._run_dir(tmp_path) / "review-bundle.json"
    assert token not in bundle.read_text()
