"""Unit tests for tools/changelog.py — the iteration close-time compiler (it-36 slice I, #474).

Derived from the acceptance criteria (the spec) and its Test expectations line: "changelog.py
compiling fixtures incl. a title-only PR". Pure functions, no network, no gh — a caller hands the
merged-PR list and the fragments directory; a PR with no matching fragment compiles from its own
title, named as such.
"""
import json
import pathlib
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "changelog.py"
sys.path.insert(0, str(ROOT / "tools"))
import changelog  # noqa: E402
import records  # noqa: E402
import check_trail  # noqa: E402


FRAGMENT_474 = (
    "## it-36 slice I — what shipped is published\n\n"
    "Every PR carries its publication input; every iteration ships as a release.\n\n"
    "Source: yellow-robots/factory#474\n"
)


def test_parse_fragment_extracts_title_goal_and_source():
    e = changelog.parse_fragment(FRAGMENT_474)
    assert e["title"] == "it-36 slice I — what shipped is published"
    assert "Every PR carries its publication input" in e["goal"]
    assert e["source"] == "yellow-robots/factory#474"
    assert e["from_title_only"] is False


def test_parse_fragment_degrades_gracefully_with_no_heading_or_source():
    e = changelog.parse_fragment("just some plain text, no heading, no source line\n")
    assert e["title"] == ""
    assert e["source"] == ""
    assert "just some plain text" in e["goal"]


def test_read_fragments_keys_by_issue_number_from_filename(tmp_path):
    d = tmp_path / "changelog.d"
    d.mkdir()
    (d / "474.md").write_text(FRAGMENT_474)
    frags = changelog.read_fragments(d)
    assert set(frags) == {"474"}
    assert frags["474"]["title"].startswith("it-36 slice I")


def test_read_fragments_absent_dir_yields_no_fragments(tmp_path):
    assert changelog.read_fragments(tmp_path / "nope") == {}


def test_fallback_from_title_names_itself_as_such():
    e = changelog.fallback_from_title(501, "attended fix, no fragment")
    assert e["from_title_only"] is True
    assert e["title"] == "attended fix, no fragment"
    assert e["source"] == "PR #501"


def test_compile_entries_matches_fragment_by_closes_issue():
    fragments = {"474": dict(changelog.parse_fragment(FRAGMENT_474), issue="474")}
    prs = [{"number": 500, "title": "the title (unused)", "closes": 474}]
    entries = changelog.compile_entries(fragments, prs)
    assert len(entries) == 1
    assert entries[0]["from_title_only"] is False
    assert entries[0]["source"] == "yellow-robots/factory#474"
    assert entries[0]["pr"] == 500


def test_compile_entries_falls_back_to_title_when_no_fragment_matches():
    """The mandate's own test expectation: 'compiling fixtures incl. a title-only PR'."""
    entries = changelog.compile_entries({}, [{"number": 501, "title": "attended, no fragment", "closes": None}])
    assert len(entries) == 1
    assert entries[0]["from_title_only"] is True
    assert entries[0]["title"] == "attended, no fragment"


def test_compile_entries_falls_back_when_closes_names_an_issue_with_no_fragment_file():
    """A PR predating this slice: it names an issue via 'closes', but changelog_dir never carried a
    fragment for it (the directory didn't exist yet, or the key wasn't declared) — falls back from
    the title exactly like a PR with no 'closes' at all, never a KeyError."""
    entries = changelog.compile_entries({}, [{"number": 42, "title": "an old PR", "closes": 42}])
    assert entries[0]["from_title_only"] is True


def test_render_changelog_md_names_the_title_only_entry():
    entries = changelog.compile_entries({}, [{"number": 501, "title": "attended, no fragment", "closes": None}])
    text = changelog.render_changelog_md("it-36", entries)
    assert "## it-36" in text
    assert "attended, no fragment" in text
    assert "compiled from title only, no changelog fragment" in text


def test_render_changelog_md_no_entries_states_it_plainly():
    text = changelog.render_changelog_md("it-99", [])
    assert "## it-99" in text
    assert "(no changes)" in text


def test_prepend_changelog_section_lands_right_after_the_title_never_reordering_prior_sections():
    existing = "# Changelog\n\n## it-35\n\n- old stuff\n"
    updated = changelog.prepend_changelog_section(existing, "## it-36\n\n- new stuff\n")
    assert updated.index("## it-36") < updated.index("## it-35")
    assert "old stuff" in updated


def test_prepend_changelog_section_creates_the_file_when_absent():
    updated = changelog.prepend_changelog_section("", "## it-1\n\n- first\n")
    assert updated.startswith("# Changelog")
    assert "## it-1" in updated


def test_yr_changelog_block_is_valid_toml_and_carries_the_reused_event_vocabulary():
    entries = changelog.compile_entries(
        {"474": dict(changelog.parse_fragment(FRAGMENT_474), issue="474")},
        [{"number": 500, "title": "t", "closes": 474}],
    )
    block = changelog.render_yr_changelog_block("it-36", "it/36", entries, now="2026-09-06T00:00:00Z")
    parsed = tomllib.loads(block)
    assert parsed["schema"] == changelog.SCHEMA
    assert parsed["iteration"] == "it-36"
    assert parsed["release"] == "it/36"
    ev = parsed["event"][0]
    assert set(ev) >= {"dt", "prj", "act", "evt", "ent", "intent"}
    assert ev["evt"] == "MS"
    assert ev["prj"] == "factory"


def test_toml_schema_fence_word_matches_the_registered_marker(reg=None):
    """check_trail's toml-schema presence check: a fenced block whose OWN fence word equals the
    registry row's marker. yr-changelog/1's marker is the bare fence word 'yr-changelog'."""
    reg = records.load()
    row = records.get(reg, "yr-changelog/1")
    entries = changelog.compile_entries({}, [{"number": 1, "title": "x", "closes": None}])
    body = changelog.render_release_body("Human notes here.", "it-36", "it/36", entries)
    assert check_trail._toml_schema_present(body, row["marker"]) is True
    assert row["marker"] == changelog.FENCE


def test_render_release_body_carries_human_notes_and_the_fenced_block():
    entries = changelog.compile_entries({}, [{"number": 1, "title": "x", "closes": None}])
    body = changelog.render_release_body("Shipped it-36.", "it-36", "it/36", entries)
    assert body.startswith("Shipped it-36.")
    assert f"```{changelog.FENCE}\n" in body
    assert body.rstrip().endswith("```")


# ============ B4 (cold review of #474): json.dumps escaping, never a manual quote swap ============

def test_yr_changelog_block_escapes_backslash_and_quote_via_json_dumps():
    """A backslash AND an embedded quote in a fragment's own goal text must round-trip through
    tomllib, not corrupt the block into unparseable TOML (the manual '\"'->\"'\" swap this fix
    replaces would have silently broken exactly this input)."""
    fragments = {"474": {
        "title": 'A "quoted" \\ backslash title',
        "goal": 'Line one with \\ and "quotes" too.',
        "source": "yellow-robots/factory#474",
        "from_title_only": False,
        "issue": "474",
    }}
    entries = changelog.compile_entries(fragments, [{"number": 500, "title": "t", "closes": 474}])
    block = changelog.render_yr_changelog_block("it-36", "it/36", entries, now="2026-09-06T00:00:00Z")
    parsed = tomllib.loads(block)   # must not raise
    assert parsed["event"][0]["intent"] == 'Line one with \\ and "quotes" too.'


def test_yr_changelog_block_escapes_backslash_in_title_when_goal_is_empty():
    fragments = {"1": {"title": 'Fix the \\n handling', "goal": "", "source": "x#1",
                       "from_title_only": False, "issue": "1"}}
    entries = changelog.compile_entries(fragments, [{"number": 1, "title": "t", "closes": 1}])
    block = changelog.render_yr_changelog_block("it-36", "it/36", entries)
    parsed = tomllib.loads(block)
    assert parsed["event"][0]["intent"] == "Fix the \\n handling"


# ============ I2 (cold review of #474): prj derived from the target repo, never hardcoded =========

def test_yr_changelog_block_prj_defaults_to_factory():
    entries = changelog.compile_entries({}, [{"number": 1, "title": "x", "closes": None}])
    block = changelog.render_yr_changelog_block("it-36", "it/36", entries)
    parsed = tomllib.loads(block)
    assert parsed["event"][0]["prj"] == "factory"


def test_yr_changelog_block_prj_is_settable():
    entries = changelog.compile_entries({}, [{"number": 1, "title": "x", "closes": None}])
    block = changelog.render_yr_changelog_block("it-36", "it/36", entries, prj="website")
    parsed = tomllib.loads(block)
    assert parsed["event"][0]["prj"] == "website"


def test_render_release_body_threads_prj_through():
    entries = changelog.compile_entries({}, [{"number": 1, "title": "x", "closes": None}])
    body = changelog.render_release_body("notes", "it-36", "it/36", entries, prj="gilda")
    start = body.index(f"```{changelog.FENCE}\n") + len(f"```{changelog.FENCE}\n")
    parsed = tomllib.loads(body[start: body.rindex("```")])
    assert parsed["event"][0]["prj"] == "gilda"


def test_cli_compile_derives_prj_from_repo(tmp_path):
    changelog_dir = tmp_path / "changelog.d"
    changelog_dir.mkdir()
    prs = _write_prs(tmp_path, [{"number": 1, "title": "x", "closes": None}])
    changelog_md = tmp_path / "CHANGELOG.md"
    release_body = tmp_path / "release-body.md"
    subprocess.run([
        sys.executable, str(TOOL), "compile",
        "--iteration", "it-36", "--release", "it/36",
        "--changelog-dir", str(changelog_dir), "--prs-file", str(prs),
        "--changelog-md", str(changelog_md), "--out-release-body", str(release_body),
        "--repo", "yellow-robots/website",
    ], capture_output=True, text=True, check=True)
    body = release_body.read_text()
    start = body.index(f"```{changelog.FENCE}\n") + len(f"```{changelog.FENCE}\n")
    parsed = tomllib.loads(body[start: body.rindex("```")])
    assert parsed["event"][0]["prj"] == "website"


def test_cli_compile_explicit_prj_overrides_repo_derivation(tmp_path):
    changelog_dir = tmp_path / "changelog.d"
    changelog_dir.mkdir()
    prs = _write_prs(tmp_path, [{"number": 1, "title": "x", "closes": None}])
    changelog_md = tmp_path / "CHANGELOG.md"
    release_body = tmp_path / "release-body.md"
    subprocess.run([
        sys.executable, str(TOOL), "compile",
        "--iteration", "it-36", "--release", "it/36",
        "--changelog-dir", str(changelog_dir), "--prs-file", str(prs),
        "--changelog-md", str(changelog_md), "--out-release-body", str(release_body),
        "--repo", "yellow-robots/website", "--prj", "explicit-prj",
    ], capture_output=True, text=True, check=True)
    body = release_body.read_text()
    start = body.index(f"```{changelog.FENCE}\n") + len(f"```{changelog.FENCE}\n")
    parsed = tomllib.loads(body[start: body.rindex("```")])
    assert parsed["event"][0]["prj"] == "explicit-prj"


# ============ N9 (cold review of #474): the headingless-fragment title fallback is real ===========

def test_compile_entries_falls_back_to_pr_title_when_fragment_has_no_heading():
    """A fragment with a Goal paragraph but no '## title' heading (parse_fragment's title is '')
    must fall back to the PR's own title — setdefault on an already-present empty-string key was
    dead code; this is the real fallback path."""
    fragments = {"474": {"title": "", "goal": "some goal text, no heading above it",
                         "source": "x#474", "from_title_only": False, "issue": "474"}}
    entries = changelog.compile_entries(
        fragments, [{"number": 500, "title": "the PR's own title", "closes": 474}])
    assert entries[0]["title"] == "the PR's own title"


def test_render_release_body_defaults_notes_when_blank():
    entries = []
    body = changelog.render_release_body("   ", "it-36", "it/36", entries)
    assert "it-36 shipped." in body


# ============ the CLI ============

def _write_prs(tmp_path, prs):
    p = tmp_path / "prs.json"
    p.write_text(json.dumps(prs))
    return p


def test_cli_compile_test_mode_writes_nothing(tmp_path):
    changelog_dir = tmp_path / "changelog.d"
    changelog_dir.mkdir()
    (changelog_dir / "474.md").write_text(FRAGMENT_474)
    prs = _write_prs(tmp_path, [{"number": 500, "title": "t", "closes": 474}])
    changelog_md = tmp_path / "CHANGELOG.md"
    out = subprocess.run([
        sys.executable, str(TOOL), "compile",
        "--iteration", "it-36", "--release", "it/36",
        "--changelog-dir", str(changelog_dir), "--prs-file", str(prs),
        "--changelog-md", str(changelog_md), "--test-mode",
    ], capture_output=True, text=True, check=True)
    assert "TEST-MODE" in out.stdout
    assert not changelog_md.exists()


def test_cli_compile_writes_changelog_and_release_body(tmp_path):
    changelog_dir = tmp_path / "changelog.d"
    changelog_dir.mkdir()
    (changelog_dir / "474.md").write_text(FRAGMENT_474)
    prs = _write_prs(tmp_path, [
        {"number": 500, "title": "t", "closes": 474},
        {"number": 501, "title": "attended, no fragment", "closes": None},
    ])
    changelog_md = tmp_path / "CHANGELOG.md"
    release_body = tmp_path / "release-body.md"
    notes = tmp_path / "notes.md"
    notes.write_text("Shipped it-36: publication for every task.")
    subprocess.run([
        sys.executable, str(TOOL), "compile",
        "--iteration", "it-36", "--release", "it/36",
        "--changelog-dir", str(changelog_dir), "--prs-file", str(prs),
        "--changelog-md", str(changelog_md), "--notes-file", str(notes),
        "--out-release-body", str(release_body),
    ], capture_output=True, text=True, check=True)
    assert changelog_md.exists()
    text = changelog_md.read_text()
    assert "## it-36" in text
    assert "attended, no fragment" in text
    assert "compiled from title only" in text
    body = release_body.read_text()
    assert body.startswith("Shipped it-36")
    assert f"```{changelog.FENCE}" in body


def test_cli_compile_prepends_to_an_existing_changelog(tmp_path):
    changelog_dir = tmp_path / "changelog.d"
    changelog_dir.mkdir()
    prs = _write_prs(tmp_path, [{"number": 1, "title": "x", "closes": None}])
    changelog_md = tmp_path / "CHANGELOG.md"
    changelog_md.write_text("# Changelog\n\n## it-35\n\n- old\n")
    subprocess.run([
        sys.executable, str(TOOL), "compile",
        "--iteration", "it-36", "--release", "it/36",
        "--changelog-dir", str(changelog_dir), "--prs-file", str(prs),
        "--changelog-md", str(changelog_md),
    ], capture_output=True, text=True, check=True)
    text = changelog_md.read_text()
    assert text.index("## it-36") < text.index("## it-35")
