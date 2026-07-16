# Tests for issue #215: the factory adopts its own lint tier's config, `ruff.toml` — chosen
# green-at-adoption (RC=0 at the slice's own tip), version-pinned in exactly one place, and
# declared in `.yr/factory.toml` per the seam's existing lint_cmd/lint_fix_cmd contract.
import pathlib
import re

import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_SELECT = ["E9", "F821", "F811", "F841", "F632", "PLR0124", "PLW0129", "B011", "B015"]


def _ruff_toml_text():
    return (ROOT / "ruff.toml").read_text()


def _ruff_toml():
    return tomllib.loads(_ruff_toml_text())


def test_ruff_toml_exists_at_repo_root():
    assert (ROOT / "ruff.toml").is_file()


def test_ruff_toml_selects_exactly_the_declared_rule_set():
    config = _ruff_toml()
    assert set(config["lint"]["select"]) == set(EXPECTED_SELECT)
    assert len(config["lint"]["select"]) == len(EXPECTED_SELECT)


def test_ruff_toml_excludes_claude_dir():
    config = _ruff_toml()
    assert config["exclude"] == [".claude"]


def test_ruff_toml_carries_no_tool_version():
    config = _ruff_toml()
    # No version-pinning key of any kind belongs in the lint config itself — the pin lives in
    # requirements-dev.txt, the one pin site.
    assert "required-version" not in config
    assert "version" not in config
    assert "0.15.21" not in _ruff_toml_text()


def test_requirements_dev_pins_ruff_0_15_21():
    lines = (ROOT / "requirements-dev.txt").read_text().splitlines()
    assert "ruff==0.15.21" in lines


def test_ruff_version_pin_has_exactly_one_site():
    # requirements-dev.txt is the only place a ruff *version* is pinned; ruff.toml must stay bare.
    pin_pattern = re.compile(r"ruff==")
    sites = []
    for path in (ROOT / "requirements-dev.txt", ROOT / "ruff.toml"):
        if pin_pattern.search(path.read_text()):
            sites.append(path)
    assert sites == [ROOT / "requirements-dev.txt"]


def _factory_manifest_text():
    return (ROOT / ".yr" / "factory.toml").read_text()


def _factory_manifest():
    return tomllib.loads(_factory_manifest_text())


def test_factory_manifest_declares_lint_cmd():
    manifest = _factory_manifest()
    assert manifest.get("lint_cmd") == "ruff check tools/ tests/"


def test_factory_manifest_declares_lint_fix_cmd():
    manifest = _factory_manifest()
    assert manifest.get("lint_fix_cmd") == "ruff check --fix tools/ tests/"


def test_factory_manifest_lint_keys_are_commented_house_style():
    # Every other declared key in this manifest (bench_test_globs, auto_merge, ...) carries an
    # explanatory comment on the line(s) directly above it; lint_cmd/lint_fix_cmd follow suit.
    lines = _factory_manifest_text().splitlines()
    key_lines = [i for i, line in enumerate(lines) if line.startswith("lint_cmd = ")]
    assert key_lines, "lint_cmd key not found in manifest"
    preceding = lines[key_lines[0] - 1]
    assert preceding.strip().startswith("#")
