"""The docstrings say what the code does now."""

import unittest

import wordcount


class Docstrings(unittest.TestCase):
    def test_the_module_docstring_says_whitespace_and_no_longer_spaces(self):
        doc = wordcount.__doc__
        self.assertIn("whitespace", doc)
        self.assertNotIn("between spaces", doc)
        self.assertNotIn("no spaces", doc)

    def test_the_function_docstring_no_longer_says_split_on_spaces(self):
        self.assertNotIn("split on spaces", wordcount.count.__doc__)
