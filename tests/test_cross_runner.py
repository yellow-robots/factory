"""Acceptance tests for tools/cross-runner.sh — the crossing's own stage runner (it-36 slice G,
#472): cross-draft, rfc-review, fold (on REQUEST CHANGES, once), arch (on block, one
fold-and-re-review). A stubbed `claude` (no live LLM) and a stubbed `tools/cross.py` (via the
CROSS_PY test-only override — no live gh, no live vault, no real target-repo checkout) drive the
orchestration; tests/test_cross.py covers the real tool's own gates and filing act, and
tests/test_design_review_runner.py is this suite's own model for the fold-retry shape.
"""
import json
import pathlib
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "cross-runner.sh"

REPO = "acme/widgets"
DESIGN_NAME = "01-some-design"
VAULT_DOC = "04 projects/acme/iterations/1-x/01-x.md"

RAW_DRAFT = """===TECHNICAL-RFC===
# Technical RFC — Some Feature

body
===END-TECHNICAL-RFC===
===SLICE task===
# Task — Slice one

## Goal
g
===END-SLICE===
"""

CLAUDE_STUB = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"
[ -n "${STUB_CLAUDE_ARGV_LOG:-}" ] && { printf '===STUB-CALL===\\n'; printf '%s\\n' "$@"; printf '\\n===END-STDIN===\\n'; } >> "$STUB_CLAUDE_ARGV_LOG"
case "$args" in
  *"cold technical-rfc reviewer"*)
    n="$(cat "$STUB_RFC_CALL_COUNT" 2>/dev/null || echo 0)"; n=$((n + 1)); echo "$n" > "$STUB_RFC_CALL_COUNT"
    echo "RFC$n" >> "$STUB_TIMELINE"
    [ -n "${STUB_RFC_FAIL:-}" ] && exit 1
    verdict="$(sed -n "${n}p" "$STUB_RFC_VERDICTS_FILE")"
    echo "some rfc review notes"
    printf 'VERDICT: %s\\n' "$verdict" ;;
  *"crossing fold stage"*)
    echo FOLD >> "$STUB_TIMELINE"
    [ -n "${STUB_FOLD_FAIL:-}" ] && exit 1
    cat "${STUB_FOLD_DRAFT_FILE:-$STUB_DRAFT_FILE}" ;;
  *"crossing arch-fold stage"*)
    echo ARCH_FOLD >> "$STUB_TIMELINE"
    [ -n "${STUB_ARCH_FOLD_FAIL:-}" ] && exit 1
    echo "ARCH-FOLDED-TECHNICAL-RFC-CONTENT" ;;
  *"architect stage"*)
    n="$(cat "$STUB_ARCH_CALL_COUNT" 2>/dev/null || echo 0)"; n=$((n + 1)); echo "$n" > "$STUB_ARCH_CALL_COUNT"
    echo "ARCH$n" >> "$STUB_TIMELINE"
    [ -n "${STUB_ARCH_FAIL:-}" ] && exit 1
    verdict="$(sed -n "${n}p" "$STUB_ARCH_VERDICTS_FILE")"
    echo "some architecture findings"
    echo "ALTERNATIVE: a queue-based design instead"
    printf 'VERDICT: %s\\n' "$verdict" ;;
  *"crossing stage"*)
    echo DRAFT >> "$STUB_TIMELINE"
    [ -n "${STUB_DRAFT_FAIL:-}" ] && exit 1
    cat "$STUB_DRAFT_FILE" ;;
  *)
    echo UNKNOWN >> "$STUB_TIMELINE"
    exit 1 ;;
esac
exit 0
'''

# CROSS_PY fake: split-draft mirrors the real tool's own marker grammar closely enough to drive this
# runner's orchestration; file returns a canned exit code/body and RECORDS its own argv so a test can
# assert what the runner handed it (design/review/who/slices/base-ref) without a live gh or vault.
CROSS_PY_STUB = '''#!/usr/bin/env python3
import json, os, re, sys

argv = sys.argv[1:]
log = os.environ.get("STUB_CROSS_ARGV_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(argv) + "\\n")

if argv[0] == "split-draft":
    raw = open(argv[1]).read()
    out_dir = argv[argv.index("--out-dir") + 1]
    os.makedirs(out_dir, exist_ok=True)
    m = re.search(r"===TECHNICAL-RFC===\\n(.*?)\\n===END-TECHNICAL-RFC===", raw, re.DOTALL)
    if not m:
        print("cross: split-draft failed: missing block", file=sys.stderr)
        sys.exit(1)
    open(os.path.join(out_dir, "technical-rfc.md"), "w").write(m.group(1))
    slices = re.findall(r"===SLICE (task|attended)===\\n(.*?)\\n===END-SLICE===", raw, re.DOTALL)
    manifest = []
    for i, (kind, body) in enumerate(slices, start=1):
        name = f"slice-{i}.md"
        open(os.path.join(out_dir, name), "w").write(body)
        manifest.append({"path": name, "kind": kind})
    open(os.path.join(out_dir, "manifest.json"), "w").write(json.dumps(manifest))
    sys.exit(0)

if argv[0] == "file":
    print(os.environ.get("STUB_FILE_OUTPUT", '{"ok": true, "epic_number": 900}'))
    sys.exit(int(os.environ.get("STUB_FILE_EXIT", "0")))

sys.exit(9)
'''


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _cross_calls(tmp):
    p = tmp / "cross_argv_log"
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def _run(tmp_path, *, rfc_verdicts=("APPROVE",), arch_verdicts=("fit",), extra_env=None,
         raw_draft=RAW_DRAFT, design_doc_text="# Some design\n\nactive.\n"):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "claude", CLAUDE_STUB)
    cross_py = _exec(tmp_path / "cross_stub.py", CROSS_PY_STUB)

    dev_runner_home = tmp_path / "drhome"
    repo_checkout = tmp_path / "workspace" / "widgets"
    repo_checkout.mkdir(parents=True)
    (repo_checkout / ".git").mkdir()   # `git -C <dir> fetch origin` needs a repo; stub GIT_BIN instead
    git_stub = tmp_path / "bin" / "git"
    _exec(git_stub, '#!/usr/bin/env bash\necho GIT "$@" >> "$STUB_GIT_CALLS"\nexit 0\n')

    design_doc = tmp_path / "design-doc.md"
    design_doc.write_text(design_doc_text)

    draft_file = tmp_path / "draft.txt"
    draft_file.write_text(raw_draft)

    rfc_verdicts_file = tmp_path / "rfc_verdicts.txt"
    rfc_verdicts_file.write_text("\n".join(rfc_verdicts) + "\n")
    arch_verdicts_file = tmp_path / "arch_verdicts.txt"
    arch_verdicts_file.write_text("\n".join(arch_verdicts) + "\n")

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "GIT_BIN": str(git_stub),
        "CROSS_PY": str(cross_py),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "CROSS_REPO_CHECKOUT": str(repo_checkout),
        "YR_GH_APP_SLUG": "yr-pm[bot]",
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_CLAUDE_ARGV_LOG": str(tmp_path / "claude_argv_log"),
        "STUB_CROSS_ARGV_LOG": str(tmp_path / "cross_argv_log"),
        "STUB_GIT_CALLS": str(tmp_path / "git_calls"),
        "STUB_DRAFT_FILE": str(draft_file),
        "STUB_RFC_CALL_COUNT": str(tmp_path / "rfc_call_count"),
        "STUB_RFC_VERDICTS_FILE": str(rfc_verdicts_file),
        "STUB_ARCH_CALL_COUNT": str(tmp_path / "arch_call_count"),
        "STUB_ARCH_VERDICTS_FILE": str(arch_verdicts_file),
        **(extra_env or {}),
    }
    result = subprocess.run(
        ["bash", str(RUNNER), REPO, str(design_doc), VAULT_DOC, DESIGN_NAME],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
    return result, tmp_path


# ---- happy path: draft -> rfc-review APPROVE -> arch fit -> fetch -> file -----------------------------

def test_happy_path_runs_every_stage_once_and_files(tmp_path):
    result, tmp = _run(tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp) == ["DRAFT", "RFC1", "ARCH1"]
    git_calls = (tmp / "git_calls").read_text().splitlines()
    assert any("fetch origin" in c for c in git_calls)
    file_calls = [c for c in _cross_calls(tmp) if c[0] == "file"]
    assert len(file_calls) == 1


def test_file_invocation_carries_design_review_who_and_base_ref(tmp_path):
    result, tmp = _run(tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    call = next(c for c in _cross_calls(tmp) if c[0] == "file")
    assert call[call.index("--design") + 1] == DESIGN_NAME
    assert call[call.index("--review") + 1] == "cold technical-rfc review: APPROVE"
    assert call[call.index("--who") + 1] == "yr-pm[bot]"
    assert call[call.index("--repo") + 1] == REPO
    assert call[call.index("--base-ref") + 1] == "origin/main"
    assert call[call.index("--vault-doc") + 1] == VAULT_DOC


def test_slice_manifest_is_passed_through_with_its_kind(tmp_path):
    result, tmp = _run(tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    call = next(c for c in _cross_calls(tmp) if c[0] == "file")
    slice_args = [call[i + 1] for i, a in enumerate(call) if a == "--slice"]
    assert len(slice_args) == 1
    assert slice_args[0].endswith(":task")


def test_multi_slice_draft_passes_every_slice_with_its_own_kind(tmp_path):
    two_slice_draft = RAW_DRAFT.replace(
        "===END-SLICE===\n",
        "===END-SLICE===\n===SLICE attended===\n# Task — Slice two\n\n## Goal\ng2\n===END-SLICE===\n",
        1,
    )
    result, tmp = _run(tmp_path, raw_draft=two_slice_draft)
    assert result.returncode == 0, f"stderr={result.stderr}"
    call = next(c for c in _cross_calls(tmp) if c[0] == "file")
    slice_args = [call[i + 1] for i, a in enumerate(call) if a == "--slice"]
    assert len(slice_args) == 2
    assert slice_args[0].endswith(":task")
    assert slice_args[1].endswith(":attended")


# ---- rfc-review fold-and-re-review: exactly once, never an unbounded loop -----------------------------

def test_rfc_review_request_changes_folds_once_and_still_files_on_approve(tmp_path):
    result, tmp = _run(tmp_path, rfc_verdicts=("REQUEST CHANGES", "APPROVE"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp) == ["DRAFT", "RFC1", "FOLD", "RFC2", "ARCH1"]
    call = next(c for c in _cross_calls(tmp) if c[0] == "file")
    assert call[call.index("--review") + 1] == "cold technical-rfc review: APPROVE"


def test_rfc_review_still_request_changes_after_one_fold_stops_short_of_filing(tmp_path):
    result, tmp = _run(tmp_path, rfc_verdicts=("REQUEST CHANGES", "REQUEST CHANGES"))
    assert result.returncode != 0
    assert _timeline(tmp) == ["DRAFT", "RFC1", "FOLD", "RFC2"]
    assert not any(c[0] == "file" for c in _cross_calls(tmp))
    assert "still REQUEST CHANGES" in result.stderr


# ---- arch fold-and-re-review: exactly once, never an unbounded loop, files nothing on a persisted block --

def test_arch_block_then_fit_after_the_fold_proceeds_to_filing(tmp_path):
    result, tmp = _run(tmp_path, arch_verdicts=("block", "fit"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp) == ["DRAFT", "RFC1", "ARCH1", "ARCH_FOLD", "ARCH2"]
    assert any(c[0] == "file" for c in _cross_calls(tmp))


def test_arch_block_then_still_block_folds_exactly_once_and_never_files(tmp_path):
    result, tmp = _run(tmp_path, arch_verdicts=("block", "block"))
    assert result.returncode != 0
    assert _timeline(tmp) == ["DRAFT", "RFC1", "ARCH1", "ARCH_FOLD", "ARCH2"]
    assert not any(c[0] == "file" for c in _cross_calls(tmp))
    assert "remains block" in result.stderr


# ---- tools/cross.py file refusing (check_links/check_task/verdict) propagates as a runner failure -----

def test_cross_file_refusal_is_a_loud_runner_failure(tmp_path):
    result, tmp = _run(tmp_path, extra_env={
        "STUB_FILE_EXIT": "1",
        "STUB_FILE_OUTPUT": json.dumps({"ok": False, "stage": "check_task", "errors": {0: ["bad"]}}),
    })
    assert result.returncode != 0
    assert "filing refused or failed" in result.stderr


# ---- malformed cross-draft output: a loud stop, never a silent partial file ---------------------------

def test_malformed_draft_output_stops_before_any_review_stage(tmp_path):
    result, tmp = _run(tmp_path, raw_draft="not the expected shape at all")
    assert result.returncode != 0
    assert _timeline(tmp) == ["DRAFT"]
    assert not any(c[0] == "file" for c in _cross_calls(tmp))


# ---- missing preconditions: loud, early stops -----------------------------------------------------

def test_missing_design_doc_refuses_early(tmp_path):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True)
    _exec(binp / "claude", CLAUDE_STUB)
    env = {**{k: v for k, v in __import__("os").environ.items()}, "CLAUDE_BIN": str(binp / "claude")}
    result = subprocess.run(
        ["bash", str(RUNNER), REPO, str(tmp_path / "nope.md"), VAULT_DOC, DESIGN_NAME],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30)
    assert result.returncode == 2
    assert "design doc not found" in result.stderr


def test_missing_repo_checkout_refuses_early(tmp_path):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True)
    _exec(binp / "claude", CLAUDE_STUB)
    design_doc = tmp_path / "design-doc.md"
    design_doc.write_text("design\n")
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "CROSS_REPO_CHECKOUT": str(tmp_path / "does-not-exist"),
        "DEV_RUNNER_HOME": str(tmp_path / "drhome"),
    }
    result = subprocess.run(
        ["bash", str(RUNNER), REPO, str(design_doc), VAULT_DOC, DESIGN_NAME],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30)
    assert result.returncode == 2
    assert "no checkout at" in result.stderr


# ---- ledger: each stage leaves its own row -------------------------------------------------------------

def test_each_stage_leaves_its_own_ledger_row(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import ledger  # noqa: E402
    result, tmp = _run(tmp_path, rfc_verdicts=("REQUEST CHANGES", "APPROVE"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    rows = ledger.load_rows(str(tmp / "drhome" / "ledger"))
    stages = [r.get("stage") for r in rows]
    assert stages == ["cross-draft", "rfc-review", "fold", "rfc-review", "arch"]
    for r in rows:
        assert r.get("kind") == "design"
        assert r.get("task") == f"{REPO}#{DESIGN_NAME}"


# ---- no LLM anywhere but claude ------------------------------------------------------------------------

def test_runner_never_shells_to_gh_directly():
    text = RUNNER.read_text()
    assert '"$GH_BIN"' not in text, "filing/board writes belong to tools/cross.py, never this runner"
