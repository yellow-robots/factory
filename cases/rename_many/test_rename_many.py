"""A rename across many sites."""

import unittest

import builder
from builder import Sandbox, Tools


class Rename(unittest.TestCase):
    def test_the_docstrings_say_tree(self):
        docs = [
            builder.__doc__, Tools.__doc__, Tools.list.__doc__, Tools.read.__doc__, Tools.write.__doc__,
            Tools.edit.__doc__, Tools.check.__doc__, Sandbox.__doc__, Sandbox.image.__doc__, Sandbox.run.__doc__,
            builder.git.__doc__, builder.head.__doc__, builder.dirty_paths.__doc__, builder.record_diff.__doc__,
        ]
        for doc in docs:
            self.assertNotIn("checkout", doc)
        self.assertIn("tree", builder.__doc__)
        self.assertIn("a goal and a checkout", builder.ROLE)
