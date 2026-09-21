"""The host's own state, apart: what `host.py` gives the loop.

    uv run python -m unittest test_host -v

Written after the loop's second review found the installed product's version read with
`["uv", "tool list"]` -- one argument -- behind a test shim that ignored its arguments, in a
module whose docstring is git, the listing, the tests and the suite. The host is not the
repository; it has a reader of its own.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import host


class HostTest(unittest.TestCase):
    """seed: the-step-nobody-noticed. `host.instance()` answers `Instance(version, error)`: the
    installed product's version from `uv tool list`, its colour escapes stripped, or `None` and
    the words of what went wrong; it never raises."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def shim_uv(self, says: str) -> None:
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "uv"
        shim.write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2" != "tool list" ]; then echo "error: unrecognized subcommand" >&2; exit 2; fi\n'
            f"printf '%b' '{says}'\n"
        )
        shim.chmod(0o755)
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}))

    def test_the_version_is_read_with_uv_tool_list_as_three_words(self):
        self.shim_uv("factory v0.20\\n- factory-build\\n")
        calls: list[list[str]] = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            found = host.instance()
        self.assertEqual((found.version, found.error), ("0.20", ""))
        self.assertEqual(calls, [["uv", "tool", "list"]])

    def test_colour_escapes_are_stripped_and_another_tool_is_not_the_factory(self):
        self.shim_uv("\\033[1mfactory-lab\\033[0m v9.9\\n- lab\\n\\033[1mfactory\\033[0m v0.2\\n- factory-build\\n")
        self.assertEqual(host.instance().version, "0.2")

    def test_no_factory_and_no_uv_are_none_with_the_reason(self):
        self.shim_uv("other v1.0\\n- other\\n")
        found = host.instance()
        self.assertIsNone(found.version)
        self.assertIn("factory", found.error)
        with mock.patch.dict(os.environ, {"PATH": self.tmp.name}):  # no uv anywhere on it
            found = host.instance()
        self.assertIsNone(found.version)
        self.assertTrue(found.error)
        import repo

        self.assertFalse(hasattr(repo, "instance_version"))


if __name__ == "__main__":
    unittest.main()
