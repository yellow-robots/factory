import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_links import check_links


def _vault_file(root, relpath, content="x"):
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _artifact(**source):
    lines = ["---", "type: feature-rfc"]
    for k, v in source.items():
        lines.append(f'{k}: "{v}"')
    lines += ["---", "# Body", ""]
    return "\n".join(lines)


# --- wikilink → vault FS resolution (the fail-loud core) ---

def test_no_source_fields_is_ok(tmp_path):
    text = "---\ntype: feature-rfc\ntitle: x\n---\nbody\n"
    assert check_links(text, vault_root=tmp_path) == []


def test_wikilink_resolves_by_explicit_path(tmp_path):
    _vault_file(tmp_path, "04 projects/factory/rfcs/note.md")
    text = _artifact(source_rfc="[[04 projects/factory/rfcs/note]]")
    assert check_links(text, vault_root=tmp_path) == []


def test_wikilink_resolves_by_unique_basename(tmp_path):
    _vault_file(tmp_path, "a/b/c/note.md")
    text = _artifact(source_rfc="[[note]]")
    assert check_links(text, vault_root=tmp_path) == []


def test_wikilink_unresolved_reports_error(tmp_path):
    text = _artifact(source_rfc="[[ghost]]")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "source_rfc" in errors[0]
    assert "ghost" in errors[0]
    assert "unresolved" in errors[0].lower()


def test_wikilink_ambiguous_basename_is_fail_loud(tmp_path):
    _vault_file(tmp_path, "x/note.md")
    _vault_file(tmp_path, "y/note.md")
    text = _artifact(source_rfc="[[note]]")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "ambiguous" in errors[0].lower()


def test_wikilink_placeholder_is_reported(tmp_path):
    text = _artifact(source_rfc="[[<feature-rfc note>]]")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "placeholder" in errors[0].lower()


def test_wikilink_strips_heading_and_alias(tmp_path):
    _vault_file(tmp_path, "note.md")
    text = _artifact(source_rfc="[[note#Some Heading|Alias]]")
    assert check_links(text, vault_root=tmp_path) == []


def test_wikilink_ignores_dotdir_matches(tmp_path):
    # a trashed/.obsidian copy must NOT count as a resolution
    _vault_file(tmp_path, ".trash/note.md")
    text = _artifact(source_rfc="[[note]]")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "unresolved" in errors[0].lower()


def test_empty_source_value_is_error(tmp_path):
    text = _artifact(source_rfc="")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "empty" in errors[0].lower()


# --- GitHub-side refs (#issue / URL): format floor, resolution optional ---

def test_issue_ref_format_ok_without_resolver(tmp_path):
    text = _artifact(source_brief="#42")
    assert check_links(text, vault_root=tmp_path) == []


def test_bad_ref_format_is_error(tmp_path):
    text = _artifact(source_brief="#not-a-number")
    errors = check_links(text, vault_root=tmp_path)
    assert len(errors) == 1
    assert "source_brief" in errors[0]


def test_url_format_ok_without_resolver(tmp_path):
    text = _artifact(source_brief="https://github.com/yellow-robots/platform/issues/1")
    assert check_links(text, vault_root=tmp_path) == []


def test_resolver_failure_is_reported(tmp_path):
    text = _artifact(source_brief="https://github.com/o/r/issues/9")
    errors = check_links(text, vault_root=tmp_path, resolve_ref=lambda kind, target: False)
    assert len(errors) == 1
    assert "unresolved" in errors[0].lower()


def test_resolver_success_passes(tmp_path):
    text = _artifact(source_brief="https://github.com/o/r/issues/9")
    assert check_links(text, vault_root=tmp_path, resolve_ref=lambda kind, target: True) == []


# --- CLI ---

def test_cli_fails_loud_on_unresolved_wikilink(tmp_path):
    artifact = tmp_path / "rfc.md"
    artifact.write_text(_artifact(source_rfc="[[ghost]]"), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_links.py"),
         str(artifact), "--vault-root", str(tmp_path), "--no-gh"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "source_rfc" in r.stdout
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_passes_clean_artifact(tmp_path):
    _vault_file(tmp_path, "real-note.md")
    artifact = tmp_path / "rfc.md"
    artifact.write_text(_artifact(source_rfc="[[real-note]]"), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_links.py"),
         str(artifact), "--vault-root", str(tmp_path), "--no-gh"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "Traceback" not in (r.stdout + r.stderr)
