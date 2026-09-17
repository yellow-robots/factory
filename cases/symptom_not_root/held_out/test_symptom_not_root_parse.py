"""The root: parse drops a debit's sign."""

import unittest

import ledger


class Parse(unittest.TestCase):
    def test_parse_gives_a_debit_its_sign(self):
        self.assertEqual(ledger.parse("-3"), -3)
        self.assertEqual(ledger.parse(" -12 "), -12)
        self.assertEqual(ledger.parse("+5"), 5)
        self.assertEqual(ledger.parse("7"), 7)
