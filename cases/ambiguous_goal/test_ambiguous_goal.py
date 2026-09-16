"""A goal that names the outcome but not the place."""

import contextlib
import io
import unittest

import builder


class Ambiguous(unittest.TestCase):
    def test_the_usage_error_names_the_key_file(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(builder.main(["builder.py"]), 2)
        self.assertIn("~/.config/factory/deepseek.key", err.getvalue())
