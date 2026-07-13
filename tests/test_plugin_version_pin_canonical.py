"""Tests for issue #149 — one canonical plugin-version pin.

Derived from the issue #149 acceptance criteria (the spec), not from the pruning
diff's internals: the test suite must carry exactly one `== "<current version>"`
plugin-version pin (in whichever single home the slice chose), no stale `!=`
version vestige from an old release, and the surviving pin's value must track
`.claude-plugin/plugin.json`'s actual current version rather than a frozen
constant. A plugin release should then edit one test file, not several.

Runs under `.venv/bin/python -m pytest tests/ -q` (or `pytest tests/ -q` on PATH).
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS_DIR = pathlib.Path(__file__).resolve().parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
THIS_FILE = pathlib.Path(__file__).resolve()

# Same shape as the issue's own verification command:
#   grep -rn 'version.*== "0\.' tests/
POSITIVE_PIN_RE = re.compile(r'version.*==\s*"0\.')
NEGATIVE_PIN_RE = re.compile(r'version.*!=\s*"0\.')


def _test_py_files():
    for path in sorted(TESTS_DIR.glob("*.py")):
        if path.resolve() == THIS_FILE:
            # this file's own docstring/regexes talk about pins as text, not a pin
            continue
        yield path


def _matching_lines(pattern):
    hits = []
    for path in _test_py_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append((f"{path.relative_to(ROOT)}:{lineno}", line.strip()))
    return hits


def test_exactly_one_positive_version_pin_suite_wide():
    """AC: keep exactly one `== <current plugin version>` pin, in one home."""
    hits = _matching_lines(POSITIVE_PIN_RE)
    assert len(hits) == 1, (
        "expected exactly one '== \"0.x\"' plugin-version pin across tests/, "
        f"found {len(hits)}: {hits}"
    )


def test_no_negative_version_vestiges_remain():
    """AC: delete the three negative vestiges (!= "0.6.0", != "0.5.0", != "0.7.1")."""
    hits = _matching_lines(NEGATIVE_PIN_RE)
    assert not hits, f"stale '!= \"0.x\"' version vestige(s) remain: {hits}"


def test_canonical_pin_tracks_plugin_json_current_version():
    """AC: 'the version in the assert must match .claude-plugin/plugin.json at
    build time' — the surviving pin must read the live current version, not a
    value that happens to match today only by coincidence."""
    current_version = json.loads(PLUGIN.read_text(encoding="utf-8"))["version"]
    hits = _matching_lines(POSITIVE_PIN_RE)
    assert hits, "no canonical version pin found to check against plugin.json"
    (_, line), = hits
    assert f'"{current_version}"' in line, (
        f"the canonical pin does not match .claude-plugin/plugin.json's current "
        f"version ({current_version!r}): {line}"
    )
