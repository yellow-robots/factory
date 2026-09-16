"""A test that cannot pass."""

import unittest


class Impossible(unittest.TestCase):
    def test_one_is_two(self):
        self.assertEqual(1, 2)
