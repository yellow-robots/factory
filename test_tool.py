"""The factory as a tool: what the product holds and how it is entered.

    uv run python -m unittest test_tool -v

`pyproject.toml` declares the product -- five modules, four console scripts, a version derived
from the tag when the wheel is built -- and the walls keep the builder from that file. What these
tests hold is that the programs meet it: each has the entry a console script names, the files the
wheel holds are exactly the import closure of the scripts over this repository's own modules, and
a program run as a file still answers as it does today.
"""

import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import build
import builder
import reviewer
import runs

ROOT = Path(__file__).resolve().parent
PROGRAMS = {"build": build, "builder": builder, "reviewer": reviewer, "runs": runs}
SCRIPTS = {
    "factory-build": "build:cli",
    "factory-builder": "builder:cli",
    "factory-review": "reviewer:cli",
    "factory-runs": "runs:cli",
}


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def imports_of(module: str) -> set[str]:
    """The repository's own modules `module` imports, read from its source: a line beginning
    `import x` or `from x import` where `x.py` is at the root and is no test."""
    local = {p.stem for p in ROOT.glob("*.py") if not p.name.startswith("test_")}
    found = set()
    for line in (ROOT / f"{module}.py").read_text().splitlines():
        match = re.match(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if match and match.group(1) in local:
            found.add(match.group(1))
    return found


class EntryTest(unittest.TestCase):
    """seed: installation-and-surfaces. Each program has `cli()`, the entry a console script
    names: no argument, `main` called with `sys.argv` whole as the guard passes it today, and the
    process exits with what `main` returned."""

    def test_cli_calls_main_with_argv_whole_and_exits_with_its_return(self):
        for name, module in PROGRAMS.items():
            with self.subTest(program=name):
                self.assertTrue(callable(getattr(module, "cli", None)), f"{name}.cli is missing")
                argv = [f"{name}.py", "one", "two"]
                with mock.patch.object(module, "main", return_value=3) as main, \
                        mock.patch.object(sys, "argv", list(argv)):  # fmt: skip
                    with self.assertRaises(SystemExit) as raised:
                        module.cli()
                self.assertEqual(raised.exception.code, 3)
                main.assert_called_once_with(argv)

    def test_the_scripts_name_each_programs_cli(self):
        self.assertEqual(pyproject()["project"]["scripts"], SCRIPTS)

    def test_a_program_run_as_a_file_still_answers_its_usage(self):
        """`uv run build.py ...` and the rest keep working: run as a file with the wrong
        arguments, each prints its usage line and exits 2 before reading any configuration."""
        for name, args in (("build", []), ("builder", []), ("reviewer", []), ("runs", ["extra"])):
            with self.subTest(program=name):
                done = subprocess.run([sys.executable, str(ROOT / f"{name}.py"), *args],
                                      capture_output=True, text=True, cwd=ROOT, timeout=60)  # fmt: skip
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(f"usage: {name}.py", done.stderr)


class ProductTest(unittest.TestCase):
    """seed: installation-and-surfaces. The wheel holds the import closure of the four scripts
    over this repository's own modules and nothing else, so a module the product needs cannot be
    left out silently and one it does not need cannot ride along; and the version is the tag's,
    derived when the wheel is built and written nowhere, with the checkout no package at all."""

    def test_the_wheel_holds_exactly_what_the_scripts_import(self):
        closure, frontier = set(), set(PROGRAMS)
        while frontier:
            module = frontier.pop()
            closure.add(module)
            frontier |= imports_of(module) - closure
        declared = pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["only-include"]
        self.assertEqual(sorted(declared), sorted(f"{module}.py" for module in closure))

    def test_the_version_is_the_tags_and_written_nowhere(self):
        data = pyproject()
        self.assertIn("version", data["project"].get("dynamic", []))
        self.assertNotIn("version", data["project"])
        self.assertEqual(data["tool"]["hatch"]["version"]["source"], "vcs")
        self.assertIs(data["tool"]["uv"]["package"], False)


if __name__ == "__main__":
    unittest.main()
