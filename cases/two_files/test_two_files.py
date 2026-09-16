"""A change that needs two files."""

import contextlib
import io
import unittest

import gate
import runs


class TwoFiles(unittest.TestCase):
    def test_the_usage_lines_say_uv_run(self):
        self.assertTrue(gate.USAGE.startswith("usage: uv run gate.py"), gate.USAGE)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(runs.main(["runs.py", "x"]), 2)
        self.assertIn("usage: uv run runs.py", err.getvalue())
