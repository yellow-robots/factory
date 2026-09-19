"""The budget a run is given and the landing at the end of it: caps-for-the-checkout-as-it-is.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel and the sandbox is a
fake. The fixtures of the builder's own suite are reused rather than copied.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai import models

import builder
from builder import Tools
from test_builder import FakeSandbox

models.ALLOW_MODEL_REQUESTS = False

LINES = 250
FILES = 40  # 10,000 lines: 34 reads at 300 lines a read to see the checkout once
BUDGET = 106  # 2 * 34, for the reading and the reading again, + 30 writes + 8 checks


class BudgetTest(unittest.TestCase):
    """How many tool calls a run over a checkout is given, and what the count is taken over."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.run_dir = self.base / "run"
        self.run_dir.mkdir()

    def checkout(self, name: str, files: int, lines: int) -> Path:
        """A checkout of that many files of that many lines, and nothing else."""
        root = self.base / name
        root.mkdir()
        for i in range(files):
            (root / f"f{i}.py").write_text("".join(f"line {n}\n" for n in range(lines)))
        return root

    def test_the_budget_is_the_reading_of_the_checkout_twice_over_and_the_work(self):
        """seed: caps-for-the-checkout-as-it-is. The caps were set at v0.3 for a program of three
        hundred lines and have not moved since, while the checkout the builder works on has grown
        to thirteen thousand. What it costs to read a checkout once is its lines over the lines a
        read returns; the budget is that twice over, for the reading and the reading again, plus
        the writes and the checks a run is already allowed."""
        root = self.checkout("ten-thousand", FILES, LINES)
        self.assertEqual(builder.call_budget(root), BUDGET)

    def test_a_small_checkout_gets_the_floor_and_a_large_one_the_ceiling(self):
        """seed: caps-for-the-checkout-as-it-is. A checkout smaller than the one the caps were set
        for is given no fewer calls than they were, so nothing the factory already builds is made
        worse; and no checkout is given more than the ceiling, so the worst a run can cost is a
        number and not a function of whatever the factory is pointed at."""
        self.assertEqual(builder.call_budget(self.checkout("small", 1, 3)), builder.CALLS_FLOOR)
        big = self.checkout("big", FILES, LINES)
        with mock.patch.object(builder, "CALLS_CEILING", 90):
            self.assertEqual(builder.call_budget(big), 90)

    def test_only_what_the_tools_can_reach_is_counted(self):
        """seed: caps-for-the-checkout-as-it-is. The budget is for the reading, so what is counted
        is what the tools would answer with: a hidden name at the root, git's own files at any
        depth and a symlink are not the checkout's text, and a file that is not text or cannot be
        read counts nothing rather than stopping the count."""
        root = self.checkout("ten-thousand", FILES, LINES)
        self.assertEqual(builder.call_budget(root), BUDGET)
        plenty = "".join(f"line {n}\n" for n in range(3000))

        for name in builder.HIDDEN:  # hidden at the root, where the tools hide them
            (root / name).mkdir()
            (root / name / "big.py").write_text(plenty)
        (root / "sub" / ".git").mkdir(parents=True)  # git's own, at any depth
        (root / "sub" / ".git" / "big.py").write_text(plenty)
        outside = self.base / "outside.py"  # a link is never walked into
        outside.write_text(plenty)
        os.symlink(outside, root / "link.py")
        (root / "blob.bin").write_bytes(bytes(range(256)) * 4000)  # not text
        shut = root / "shut.py"  # text, but not this process's to read
        shut.write_text(plenty)
        shut.chmod(0o000)
        self.addCleanup(shut.chmod, 0o600)

        self.assertEqual(builder.call_budget(root), BUDGET)

    def test_the_tools_carry_the_budget_of_the_checkout_they_are_given(self):
        """seed: caps-for-the-checkout-as-it-is. The count is taken once, from the tree the run
        starts on, and the tools carry it; a caller that already knows the budget names it and the
        tree is not walked for it."""
        root = self.checkout("ten-thousand", FILES, LINES)
        self.assertEqual(Tools(root, self.run_dir, sandbox=FakeSandbox([])).budget, BUDGET)
        self.assertEqual(Tools(root, self.run_dir, budget=7, sandbox=FakeSandbox([])).budget, 7)
        hidden = Tools(root, self.run_dir, hidden=(*builder.HIDDEN, "f0.py"), sandbox=FakeSandbox([]))
        self.assertEqual(hidden.budget, builder.call_budget(root, (*builder.HIDDEN, "f0.py")))
        self.assertLess(hidden.budget, BUDGET, "what the tools hide is not what they must read")


if __name__ == "__main__":
    unittest.main()
