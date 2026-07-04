import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools.check_task as check_task_module
from tools.check_task import check_task


def _task(goal="Do the thing.",
          criteria="- [ ] it works",
          context="Edit `tools/validate.py` to add the branch.",
          tests="Run the suite.",
          size="S — one PR"):
    # frontmatter source_rfc is a wikilink BY DESIGN (provenance) — it must be ignored, not flagged.
    return "\n".join([
        "---",
        "type: task",
        "target_repo: platform",
        'source_rfc: "[[some feature rfc]]"',
        'source_brief: "#12"',
        "---",
        "# Task — x",
        "",
        "## Goal", goal, "",
        "## Acceptance criteria", criteria, "",
        "## Context & links", context, "",
        "## Test expectations", tests, "",
        "## Size", size, "",
    ])


def _repo_with(tmp_path, *relpaths):
    for rel in relpaths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return tmp_path


# --- happy path ---

def test_self_contained_task_passes(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(_task(), repo_root=tmp_path) == []


def test_frontmatter_source_wikilink_is_not_flagged(tmp_path):
    # only the BODY is build-critical; the frontmatter source_rfc wikilink is provenance
    _repo_with(tmp_path, "tools/validate.py")
    errors = check_task(_task(), repo_root=tmp_path)
    assert not any("some feature rfc" in e for e in errors)


# --- slice present ---

def test_empty_context_fails(tmp_path):
    errors = check_task(_task(context=""), repo_root=tmp_path)
    assert any("context" in e.lower() and "empty" in e.lower() for e in errors)


def test_context_only_a_comment_fails(tmp_path):
    errors = check_task(_task(context="<!-- paste the brief slice here -->"), repo_root=tmp_path)
    assert any("empty" in e.lower() for e in errors)


# --- no Obsidian pointer in build-critical body ---

def test_wikilink_in_context_fails(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    errors = check_task(_task(context="Edit `tools/validate.py`; see [[the RFC]]."), repo_root=tmp_path)
    assert any("obsidian" in e.lower() and "the RFC" in e for e in errors)


def test_wikilink_in_goal_fails(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    errors = check_task(_task(goal="Implement [[the design]]."), repo_root=tmp_path)
    assert any("goal" in e.lower() and "obsidian" in e.lower() for e in errors)


def test_obsidian_url_in_context_fails(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    errors = check_task(
        _task(context="Edit `tools/validate.py`; ref obsidian://open?vault=v&file=n."),
        repo_root=tmp_path)
    assert any("obsidian://" in e for e in errors)


# --- cited repo paths exist ---

def test_missing_cited_path_fails(tmp_path):
    errors = check_task(_task(context="Edit `tools/ghost.py` to fix it."), repo_root=tmp_path)
    assert any("ghost.py" in e and "exist" in e.lower() for e in errors)


def test_existing_cited_path_passes(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(_task(context="Edit `tools/validate.py`."), repo_root=tmp_path) == []


def test_bare_filename_is_not_path_checked(tmp_path):
    # no slash → ambiguous location → not checked (avoids false failures)
    assert check_task(_task(context="Touch `validate.py` near the top."), repo_root=tmp_path) == []


def test_line_suffix_is_stripped_before_existence_check(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(_task(context="See `tools/validate.py:35-37`."), repo_root=tmp_path) == []


def test_command_span_with_slash_is_not_treated_as_path(tmp_path):
    # `pytest tests/ -q` is a command (has spaces), not a cited path
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`.", tests="Run `pytest tests/ -q`."),
        repo_root=tmp_path) == []


def test_git_ref_in_backticks_is_not_path_checked(tmp_path):
    # `origin/main` looks like a 2-segment path but is a git ref (no file extension) → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. Base ref `origin/main`."),
        repo_root=tmp_path) == []


def test_scoped_package_is_not_path_checked(tmp_path):
    # `@scope/pkg` is an npm package, not a repo path → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. Depends on `@scope/pkg`."),
        repo_root=tmp_path) == []


def test_host_fragment_is_not_path_checked(tmp_path):
    # `example.com/a/b` — dot is not in the final segment → not a file path → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. See `example.com/a/b`."),
        repo_root=tmp_path) == []


def test_url_in_backticks_is_not_path_checked(tmp_path):
    # a full URL ends in `.html` but carries `://` → not a repo path → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. Docs at `https://example.com/x.html`."),
        repo_root=tmp_path) == []


def test_home_path_is_not_path_checked(tmp_path):
    # `~/.cache/dev-runner/dispatch.lock` names a host file, not a repo citation → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. See `~/.cache/dev-runner/dispatch.lock`."),
        repo_root=tmp_path) == []


def test_absolute_path_is_not_path_checked(tmp_path):
    # `/etc/systemd/user/dispatch.service` is an absolute host path, not repo-relative → skipped
    _repo_with(tmp_path, "tools/validate.py")
    assert check_task(
        _task(context="Edit `tools/validate.py`. Unit at `/etc/systemd/user/dispatch.service`."),
        repo_root=tmp_path) == []


def test_repo_relative_path_still_fails_when_missing_alongside_host_paths(tmp_path):
    # host paths are skipped, but a genuine repo-relative citation still resolves and fails loud
    errors = check_task(
        _task(context="Home `~/.cache/dev-runner/dispatch.lock`. Edit `tools/nope.py`."),
        repo_root=tmp_path)
    assert any("tools/nope.py" in e and "exist" in e.lower() for e in errors)
    assert not any("dispatch.lock" in e for e in errors)


def test_dotfile_config_path_is_still_checked(tmp_path):
    # `.yr/factory.toml` has a real extension on its final segment → still verified (and here, missing)
    errors = check_task(_task(context="Read `.yr/factory.toml` for the check_cmd."), repo_root=tmp_path)
    assert any("factory.toml" in e and "exist" in e.lower() for e in errors)


# --- own deliverable (class 2) ---

def test_deliverable_marker_exempts_own_not_yet_built_path(tmp_path):
    # #15-style: the task's body cites the file IT will create — can't exist yet, so it's exempt
    errors = check_task(
        _task(context="Deliverable: `tools/epic_gate.py` — the new epic-sweep script this task creates."),
        repo_root=tmp_path)
    assert errors == []


def test_bulleted_bold_deliverable_marker_is_recognized(tmp_path):
    errors = check_task(
        _task(context="- **Deliverable:** `tools/epic_gate.py` — the epic-sweep script."),
        repo_root=tmp_path)
    assert errors == []


def test_creates_marker_also_exempts(tmp_path):
    errors = check_task(
        _task(context="Creates: `tools/epic_gate.py`, the new epic-sweep entry point."),
        repo_root=tmp_path)
    assert errors == []


def test_same_deliverable_path_cited_elsewhere_without_marker_still_fails(tmp_path):
    # the marker exempts the marker LINE's citation, not the path string everywhere in the body
    errors = check_task(
        _task(context=(
            "Deliverable: `tools/epic_gate.py` — the new epic-sweep script.\n"
            "See `tools/epic_gate.py` for the entry point once built."
        )),
        repo_root=tmp_path)
    assert any("tools/epic_gate.py" in e and "exist" in e.lower() for e in errors)


# --- subtree-relative citation (class 3) ---

def test_subtree_relative_citation_resolves_via_unique_suffix(tmp_path):
    # #19-style: `references/closing.md` in a skill context means the factory skill's references dir
    _repo_with(tmp_path, "skills/factory/references/closing.md")
    errors = check_task(
        _task(context="Follow `references/closing.md` when wrapping up."),
        repo_root=tmp_path)
    assert errors == []


def test_subtree_relative_citation_ambiguous_names_both_candidates(tmp_path):
    _repo_with(tmp_path,
               "skills/factory/references/closing.md",
               "skills/other/references/closing.md")
    errors = check_task(
        _task(context="Follow `references/closing.md` when wrapping up."),
        repo_root=tmp_path)
    assert len(errors) == 1
    assert "references/closing.md" in errors[0]
    assert "skills/factory/references/closing.md" in errors[0]
    assert "skills/other/references/closing.md" in errors[0]


def test_subtree_relative_citation_no_match_still_fails(tmp_path):
    errors = check_task(
        _task(context="Follow `references/closing.md` when wrapping up."),
        repo_root=tmp_path)
    assert any("references/closing.md" in e and "exist" in e.lower() for e in errors)


def test_lowercase_deliverable_marker_is_recognized(tmp_path):
    # the rule is a marker concept, not a specific capitalization
    errors = check_task(
        _task(context="deliverable: `tools/epic_gate.py` — the new epic-sweep script."),
        repo_root=tmp_path)
    assert errors == []


def test_uppercase_creates_marker_is_recognized(tmp_path):
    errors = check_task(
        _task(context="CREATES: `tools/epic_gate.py` the new entry point."),
        repo_root=tmp_path)
    assert errors == []


def test_multiple_paths_on_a_deliverable_line_are_all_exempt(tmp_path):
    # the exemption is a line-level rule, not limited to a single cited path per marker
    errors = check_task(
        _task(context="Deliverable: `tools/epic_gate.py` and `tools/epic_gate_helpers.py`."),
        repo_root=tmp_path)
    assert errors == []


def test_deliverable_marker_does_not_exempt_a_different_missing_path_elsewhere(tmp_path):
    # the marker line exempts what's cited ON it; an unrelated missing citation elsewhere still errors
    errors = check_task(
        _task(context=(
            "Deliverable: `tools/epic_gate.py` — the new epic-sweep script.\n"
            "Also touch `tools/unrelated_ghost.py` while you're at it."
        )),
        repo_root=tmp_path)
    assert any("tools/unrelated_ghost.py" in e and "exist" in e.lower() for e in errors)
    assert not any("epic_gate.py" in e for e in errors)


def test_mid_segment_suffix_is_not_falsely_matched(tmp_path):
    # `other-references/closing.md` is NOT a `/`-bounded suffix match for `references/closing.md` —
    # a naive substring/endswith-without-boundary check would wrongly resolve this
    _repo_with(tmp_path, "docs/other-references/closing.md")
    errors = check_task(
        _task(context="Follow `references/closing.md` when wrapping up."),
        repo_root=tmp_path)
    assert any("references/closing.md" in e and "exist" in e.lower() for e in errors)


def test_suffix_match_resolves_at_deeper_nesting(tmp_path):
    # the unique-suffix rule isn't limited to one directory of nesting
    _repo_with(tmp_path, "skills/factory/references/closing.md")
    errors = check_task(
        _task(context="Follow `skills/factory/references/closing.md` here, and also "
                       "`references/closing.md` elsewhere."),
        repo_root=tmp_path)
    assert errors == []


def test_deliverable_and_subtree_rules_both_apply_in_the_same_task(tmp_path):
    # class 2 and class 3 are independent rules — a task can lean on both at once
    _repo_with(tmp_path, "skills/factory/references/closing.md")
    errors = check_task(
        _task(context=(
            "Deliverable: `tools/epic_gate.py` — the new epic-sweep script.\n"
            "Follow `references/closing.md` when wrapping up."
        )),
        repo_root=tmp_path)
    assert errors == []


def test_subtree_relative_citation_via_base_ref(tmp_path):
    # suffix resolution must also work when reading from a git ref, not just the working tree
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    _repo_with(tmp_path, "skills/factory/references/closing.md")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"], check=True)
    errors = check_task(
        _task(context="Follow `references/closing.md` when wrapping up."),
        repo_root=tmp_path, base_ref="HEAD")
    assert errors == []


def test_path_exists_injection(tmp_path):
    seen = {"tools/ok.py"}
    errors = check_task(
        _task(context="Edit `tools/ok.py` and `tools/bad.py`."),
        repo_root=tmp_path, path_exists=lambda p: p in seen)
    assert len(errors) == 1
    assert "bad.py" in errors[0]


def test_multiple_errors_collected(tmp_path):
    errors = check_task(
        _task(goal="Implement [[X]].", context="Edit `tools/ghost.py`."),
        repo_root=tmp_path)
    assert len(errors) >= 2


# --- docstrings document both new rules (AC: docstrings updated) ---

def test_module_docstring_documents_the_deliverable_rule():
    doc = check_task_module.__doc__.lower()
    assert "deliverable" in doc


def test_module_docstring_documents_the_subtree_suffix_rule():
    doc = check_task_module.__doc__.lower()
    assert "suffix" in doc or "subtree" in doc


def test_check_task_or_pathify_docstring_documents_both_rules():
    docs = " ".join(filter(None, [
        check_task_module.check_task.__doc__,
        check_task_module._pathify.__doc__,
    ])).lower()
    assert "deliverable" in docs
    assert "suffix" in docs or "subtree" in docs


# --- CLI ---

def test_cli_fails_loud_on_missing_path(tmp_path):
    task = tmp_path / "task.md"
    task.write_text(_task(context="Edit `tools/ghost.py`."), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_task.py"),
         str(task), "--repo-root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "ghost.py" in r.stdout
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_passes_self_contained_task(tmp_path):
    _repo_with(tmp_path, "tools/validate.py")
    task = tmp_path / "task.md"
    task.write_text(_task(context="Edit `tools/validate.py`."), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_task.py"),
         str(task), "--repo-root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 0
    assert "Traceback" not in (r.stdout + r.stderr)
