"""A behaviour the module docstring describes."""

import unittest

import wordcount


class WordCount(unittest.TestCase):
    def test_tabs_and_newlines_separate_words_too(self):
        self.assertEqual(wordcount.count("one\ttwo\nthree four"), 4)
        self.assertEqual(wordcount.count("  one  \n\n two "), 2)
        self.assertEqual(wordcount.count("alone"), 1)
