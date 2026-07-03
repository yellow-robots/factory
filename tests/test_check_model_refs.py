import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_model_refs import scan, main


def _write(tmp_path, relpath, content):
    p = tmp_path / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# --- unit cases ---

def test_unallowlisted_hit_exits_1(tmp_path):
    _write(tmp_path, "docs/readme.md",
           "The documentation model is at 01-conventions in the vault.\n")
    assert main(["--scan-root", str(tmp_path)]) == 1


def test_allowlisted_line_exits_0(tmp_path):
    _write(tmp_path, "skills/factory/references/documentation-model.md",
           "Relocated from the vault `01-conventions` (iteration), which it supersedes\n")
    assert main(["--scan-root", str(tmp_path)]) == 0


def test_clean_tree_exits_0(tmp_path):
    _write(tmp_path, "docs/readme.md", "No forbidden references here.\n")
    assert main(["--scan-root", str(tmp_path)]) == 0


def test_full_vault_path_hit_exits_1(tmp_path):
    _write(tmp_path, "docs/note.md",
           "See iterations/3-upper-pipeline/01-conventions.md for the model.\n")
    assert main(["--scan-root", str(tmp_path)]) == 1


def test_skip_files_are_ignored(tmp_path):
    # The scanner skips itself and its test — place a forbidden reference there and confirm exit 0
    _write(tmp_path, "tools/check_model_refs.py",
           "# pattern = '01-conventions'\n")
    _write(tmp_path, "tests/test_check_model_refs.py",
           "assert '01-conventions' in output\n")
    _write(tmp_path, "tests/test_skill_factory_router.py",
           "assert '01-conventions' not in text\n")
    assert main(["--scan-root", str(tmp_path)]) == 0


def test_skip_vcs_and_build_dirs(tmp_path):
    # Forbidden references inside .git, .venv, node_modules must be ignored
    for skip_dir in (".git", ".venv", "node_modules"):
        _write(tmp_path, f"{skip_dir}/config",
               "01-conventions appears here but is inside a skipped dir\n")
    assert main(["--scan-root", str(tmp_path)]) == 0


def test_multiple_hits_all_reported(tmp_path, capsys):
    _write(tmp_path, "a.md", "01-conventions line one\n")
    _write(tmp_path, "b.md", "see 01-conventions for details\n")
    result = main(["--scan-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert result == 1
    assert "a.md" in out
    assert "b.md" in out


# --- consumer-repointing checks (AC: no living-model reference to vault 01-conventions) ---

def test_agents_md_has_no_vault_01_conventions():
    """AGENTS.md must not reference vault 01-conventions as the living documentation model."""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    bad_lines = [
        line for line in text.splitlines()
        if "01-conventions" in line
    ]
    assert bad_lines == [], (
        f"AGENTS.md still references vault 01-conventions:\n" +
        "\n".join(bad_lines)
    )


def test_agents_md_points_to_skill_documentation_model():
    """AGENTS.md 'documentation model itself is …' passage must point at the skill reference.

    The prose may span two lines (statement on one, path on the next), so we search
    the full text rather than individual lines.
    """
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "documentation model itself" in text.lower(), (
        "AGENTS.md is missing the 'documentation model itself is …' passage"
    )
    # The path that follows must name the skill reference, not the vault
    assert "documentation-model.md" in text, (
        "AGENTS.md does not reference skills/factory/references/documentation-model.md "
        "near the 'documentation model itself is …' passage"
    )


def test_product_spec_template_has_no_vault_01_conventions():
    """templates/product-spec.md must not reference vault 01-conventions."""
    text = (ROOT / "templates" / "product-spec.md").read_text(encoding="utf-8")
    bad_lines = [
        line for line in text.splitlines()
        if "01-conventions" in line
    ]
    assert bad_lines == [], (
        f"templates/product-spec.md still references vault 01-conventions:\n" +
        "\n".join(bad_lines)
    )


def test_product_spec_review_output_points_to_documentation_model():
    """templates/product-spec.md Review output pointer must name documentation-model."""
    text = (ROOT / "templates" / "product-spec.md").read_text(encoding="utf-8")
    review_lines = [
        line for line in text.splitlines()
        if "Review output" in line or "Reviewing a doc" in line
    ]
    assert review_lines, "templates/product-spec.md is missing a Review output / Reviewing a doc line"
    assert any("documentation-model" in line for line in review_lines), (
        f"templates/product-spec.md Review output pointer does not name documentation-model:\n"
        + "\n".join(review_lines)
    )


def test_feature_rfc_template_has_no_vault_01_conventions():
    """templates/feature-rfc.md must not reference vault 01-conventions."""
    text = (ROOT / "templates" / "feature-rfc.md").read_text(encoding="utf-8")
    bad_lines = [
        line for line in text.splitlines()
        if "01-conventions" in line
    ]
    assert bad_lines == [], (
        f"templates/feature-rfc.md still references vault 01-conventions:\n" +
        "\n".join(bad_lines)
    )


def test_feature_rfc_review_output_points_to_documentation_model():
    """templates/feature-rfc.md Review output pointer must name documentation-model."""
    text = (ROOT / "templates" / "feature-rfc.md").read_text(encoding="utf-8")
    review_lines = [
        line for line in text.splitlines()
        if "Review output" in line or "Reviewing a doc" in line
    ]
    assert review_lines, "templates/feature-rfc.md is missing a Review output / Reviewing a doc line"
    assert any("documentation-model" in line for line in review_lines), (
        f"templates/feature-rfc.md Review output pointer does not name documentation-model:\n"
        + "\n".join(review_lines)
    )


# --- real-tree scan (the standing consumer-integrity guard) ---

def test_real_tree_scan_is_green():
    """Scan the actual repo — rides check_cmd on every future build."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_model_refs.py"),
         "--scan-root", str(ROOT)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        f"check_model_refs found un-allowlisted 01-conventions references:\n{r.stdout}"
    )
    assert "Traceback" not in (r.stdout + r.stderr)
