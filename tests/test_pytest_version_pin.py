"""Tests for issue #269 — pytest 8.3.3 -> 9.0.3 (Dependabot: vulnerable tmpdir handling).

Derived from the issue #269 acceptance criteria (the spec), not from the fix's internals:
`requirements-dev.txt` must pin `pytest==9.0.3` as the sole pytest version pin anywhere in the
tree, and the `ruff` pin must ride along unchanged — no other dependency pin changes bundled in.

The "suite is green under 9.0.3" criterion itself is proven by CI running under the new pin, not
by a unit test here (see the issue's "Test expectations").
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIREMENTS_DEV = ROOT / "requirements-dev.txt"
THIS_FILE = pathlib.Path(__file__).resolve()

PYTEST_PIN_RE = re.compile(r"\bpytest\s*==")

# Directories that are not part of the tracked source tree: a stale pytest pin cached in a
# build artifact, venv, or vcs metadata dir must not count against "sole pin in the tree".
EXCLUDED_DIR_PARTS = {".git", ".venv", "__pycache__", "venv", ".tox", "node_modules"}


def _is_excluded(path):
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def _tracked_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or _is_excluded(path):
            continue
        if path.resolve() == THIS_FILE:
            # this file's own docstring/regexes talk about the pin as text, not a pin
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue


def test_requirements_dev_pins_pytest_9_0_3():
    lines = REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines()
    assert "pytest==9.0.3" in lines, (
        f"expected 'pytest==9.0.3' as a line in requirements-dev.txt, got: {lines}"
    )


def test_requirements_dev_still_pins_ruff_0_15_21():
    # AC: "No other dependency pin changes ride along (ruff untouched)."
    lines = REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines()
    assert "ruff==0.15.21" in lines, (
        f"ruff pin must stay untouched at 0.15.21, got: {lines}"
    )


def test_requirements_dev_carries_exactly_the_expected_pins():
    # AC (#269): pytest bumped, ruff rides unchanged. it-25 adds pytest-xdist — the plugin the
    # parallel certification suite (`pytest tests/ -n auto`) needs — as the only further pin.
    lines = [line for line in REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert set(lines) == {"pytest==9.0.3", "pytest-xdist==3.8.0", "ruff==0.15.21"}, (
        f"requirements-dev.txt should carry exactly the pytest, pytest-xdist, and ruff pins, got: {lines}"
    )


def test_pytest_version_pin_has_exactly_one_site_repo_wide():
    # AC: "the sole pytest pin in the tree" — no other file (test, doc, manifest, ...) should
    # carry a competing/stale `pytest==` version pin.
    sites = []
    for path, text in _tracked_text_files():
        if PYTEST_PIN_RE.search(text):
            sites.append(path.relative_to(ROOT))
    assert sites == [pathlib.Path("requirements-dev.txt")], (
        f"expected requirements-dev.txt as the only 'pytest==' pin site, found: {sites}"
    )


def test_no_stale_pytest_8_reference_in_requirements_dev():
    text = REQUIREMENTS_DEV.read_text(encoding="utf-8")
    assert "8.3.3" not in text, "stale pytest 8.3.3 pin vestige remains in requirements-dev.txt"
