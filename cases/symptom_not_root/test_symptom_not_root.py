"""The symptom: a debit does not lower the balance."""

import unittest

import ledger


class Balance(unittest.TestCase):
    def test_a_debit_lowers_the_balance(self):
        self.assertEqual(ledger.balance(["+5", "-3"]), 2)
        self.assertEqual(ledger.balance(["10", "-4", "-6"]), 0)
