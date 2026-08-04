"""The wall-11 guard for issue #386 — One manifest reader.

Derived from the issue's acceptance criteria (the spec), NOT from `tools/dev-runner.sh`'s
internals:

  - "The eight inline manifest-parsing blocks in `tools/dev-runner.sh` collapse onto ONE
    parameterized reader."
  - "The wall-11 guard: a pytest test under `tests/` asserts that `tools/dev-runner.sh`
    contains EXACTLY ONE inline manifest parse. It names the surface it reads. This is the
    guard that could not honestly ship before this slice: eight readers existed, so a guard
    capping at eight would have ratified the finding and a guard capping at one would have
    been false."

This file is the guard the finding demands, and nothing else. The per-key CONTRACT the collapse
must preserve — precedence, the two read times, the three value channels, every rejection rule
naming its rejected value, and the server-CI/arming conflicting-pair refusal — is already pinned
by the preceding slice (`tests/test_manifest_read_contract_pins.py`) and the coupled per-key
suites (`test_merge_ci_timeout.py`, `test_server_ci_stance.py`, `test_check_cmd_required.py`,
`test_check_gate_timeout.py`, `test_stage_conduct_manifest.py`, `test_test_surface_manifest.py`,
`test_repo_shape_defaults.py`, `test_manifest_fetch_freshness.py`, `test_autonomous_merge.py`).
That suite passing unchanged IS the behavior-identical criterion; this file does not re-assert it.

THE SURFACE THIS GUARD READS (named, per wall 11 — a match outside it cannot satisfy the guard):
the inline `python3 -c '<script>'` invocations inside the single file `tools/dev-runner.sh` whose
script body parses TOML via the stdlib `tomllib` module. `tomllib` is the only sanctioned TOML
parser and the "No new dependencies" criterion forbids another, so every inline manifest parse in
the runner is one such block; a `python3 <file.py>` call runs a committed script (not an inline
parse) and the runner's many inline JSON parsers never import `tomllib`, so neither is counted.
The eight parsers the finding names all carried the signature `import sys, ?tomllib`; the collapse
leaves exactly one.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "dev-runner.sh"


def _runner_text():
    return RUNNER.read_text(encoding="utf-8")


def _inline_python_scripts(text):
    """Every inline `python[3] -c '<body>'` / `python[3] -c "<body>"` script body in the shell.

    Only these single-invocation inline scripts can host an inline manifest parse. Quote scan:
    a single-quoted shell string has no escape, so the next `'` closes it; a double-quoted one
    honours `\\"`. Returns the list of body strings; boundary imprecision on a body that does not
    mention `tomllib` cannot affect the manifest-parse count, since `tomllib` appears only inside a
    clean single-quoted block.
    """
    scripts = []
    for m in re.finditer(r"python3? -c ", text):
        k = m.end()
        while k < len(text) and text[k] in " \t":
            k += 1
        if k >= len(text) or text[k] not in ("'", '"'):
            continue
        quote = text[k]
        k += 1
        start = k
        while k < len(text):
            if text[k] == "\\" and quote == '"':
                k += 2
                continue
            if text[k] == quote:
                break
            k += 1
        scripts.append(text[start:k])
    return scripts


def _manifest_parse_scripts(text):
    """The inline scripts that actually parse the manifest: those importing/using `tomllib`."""
    return [s for s in _inline_python_scripts(text) if "tomllib" in s]


# ---------------------------------------------------------------------------
# THE wall-11 guard — exactly one inline manifest parse in tools/dev-runner.sh
# ---------------------------------------------------------------------------

def test_dev_runner_holds_exactly_one_inline_manifest_parse():
    """The finding's non-recurrence guard: `tools/dev-runner.sh` parses `.yr/factory.toml` at
    exactly ONE inline site. A ninth reader — any new `python3 -c` block importing `tomllib` —
    trips this. A cap of one is honest only after this slice: before it, eight such blocks existed.
    """
    parsers = _manifest_parse_scripts(_runner_text())
    assert len(parsers) == 1, (
        f"tools/dev-runner.sh contains {len(parsers)} inline manifest parses (inline `python3 -c` "
        f"scripts importing `tomllib`), expected EXACTLY 1 — every `.yr/factory.toml` key must "
        f"parse through the single parameterized reader, never a fresh inline clone. The offending "
        f"parse bodies:\n\n" + "\n---\n".join(p.strip() for p in parsers)
    )


def test_the_named_surface_actually_exists_so_the_guard_is_never_blind():
    """A guard that reads a renamed/empty surface reports "one" forever and reads as healthy while
    guarding nothing. Pin the surface's own existence: the file is present and the one parse uses
    the stdlib `tomllib` (the exact signature the finding named, `import sys, ?tomllib`)."""
    assert RUNNER.is_file(), f"the guarded surface does not exist: {RUNNER}"
    text = _runner_text()
    assert "tomllib" in text, (
        "tools/dev-runner.sh no longer references `tomllib` at all — the manifest-parse surface this "
        "guard reads has vanished or been renamed, so the count-of-one is meaningless"
    )
    assert re.search(r"import sys, ?tomllib", text), (
        "tools/dev-runner.sh's sole manifest parser dropped the `import sys, ?tomllib` signature the "
        "finding named — the guard's named surface has drifted"
    )


def test_no_toml_parser_other_than_stdlib_tomllib_is_introduced():
    """The 'No new dependencies' criterion, and the tomllib-only assumption this guard rests on: a
    second TOML parser (`tomli` / `toml` / `tomlkit`) would be both a new dependency and an inline
    manifest parse this guard's `tomllib` screen would miss — forbid it outright."""
    text = _runner_text()
    for lib in ("tomli", "tomlkit", r"import toml\b", r"import\b.*\btoml\b(?!lib)"):
        assert not re.search(lib, text), (
            f"tools/dev-runner.sh introduces a TOML parser matching {lib!r} other than the stdlib "
            "`tomllib` — a new dependency, and an inline manifest parse the wall-11 guard would not see"
        )


# ---------------------------------------------------------------------------
# "One reader" means one PARAMETERIZED reader shared across sites — not one
# invocation and not one read. AC1: the eight blocks collapse ONTO one reader.
# ---------------------------------------------------------------------------

def _enclosing_function_name(text, needle):
    """The name of the shell function whose body contains `needle` (the sole tomllib parse)."""
    idx = text.find(needle)
    assert idx != -1, f"expected {needle!r} in the runner but did not find it"
    defs = list(re.finditer(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", text[:idx]))
    assert defs, "the sole manifest parse is not inside any shell function"
    return defs[-1].group(1)


def test_the_sole_reader_is_a_shared_function_invoked_at_multiple_sites():
    """"One reader" is a shared parse ENTRY POINT the key-sites call, not seven deletions with the
    parse inlined once — and explicitly not "one invocation" (each key still reads on its own).
    Derive the reader's name from where the sole `tomllib` parse lives (no hardcoded name), then
    assert it is invoked at two or more distinct sites, proving the collapse produced a genuinely
    shared, parameterized reader."""
    text = _runner_text()
    name = _enclosing_function_name(text, "tomllib")
    # calls are `... | <name> <mode> [key]`; the definition line `<name>(){` is not a call
    calls = re.findall(rf"(?m)\|\s*{re.escape(name)}\b", text)
    assert len(calls) >= 2, (
        f"the manifest reader `{name}` is invoked at {len(calls)} site(s) — 'collapse onto one "
        "parameterized reader' means one PARSE shared across many key reads, not a single "
        "invocation; the eight former inline parsers should now be eight calls to the one reader"
    )


def test_the_reader_takes_a_mode_argument_so_value_kind_is_a_parameter():
    """The reader carries the per-key value kind as a PARAMETER (a mode), not eight hand-written
    parsers. Its invocations pass a mode token as the first argument — the observable trace that the
    contract is parameterized data the one reader takes, not re-implemented per key."""
    text = _runner_text()
    name = _enclosing_function_name(text, "tomllib")
    modes = set(re.findall(rf"(?m)\|\s*{re.escape(name)}\s+(\S+)", text))
    assert len(modes) >= 2, (
        f"the manifest reader `{name}` is always called with the same argument {modes} — the "
        "per-key value kind (scalar / bool / bulk / path-array / string-array) must be a mode the "
        "one reader takes as a parameter, which shows up as several distinct first arguments"
    )
