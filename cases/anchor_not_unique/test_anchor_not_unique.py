"""An edit whose anchor occurs several times in a long file."""

import unittest

from builder import Tools


class Anchor(unittest.TestCase):
    def test_the_tool_docstrings_say_the_checkouts_root(self):
        for tool in (Tools.list, Tools.read, Tools.write, Tools.edit):
            self.assertIn("relative to the checkout's root", tool.__doc__, tool.__name__)
            self.assertNotIn("relative to the checkout root", tool.__doc__, tool.__name__)
