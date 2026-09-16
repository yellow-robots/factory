"""A new module the test imports."""

import unittest

import record


class NewFile(unittest.TestCase):
    def test_the_record_module_lists_a_runs_files(self):
        self.assertEqual(
            record.FILES,
            ("goal.txt", "wire.jsonl", "messages.json", "check-<n>.log", "diff.patch", "report.json", "response.md", "numbers.json"),
        )
        self.assertEqual(record.FIRST, "numbers.json")
