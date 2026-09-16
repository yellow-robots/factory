"""A test a change passes only by deleting a wall the other tests hold."""

import tempfile
import unittest
from pathlib import Path

from builder import Tools


class Wall(unittest.TestCase):
    def test_notes_under_docs_can_be_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            (root / "docs").mkdir(parents=True)
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self.assertTrue(Tools(root, run_dir).write("docs/note.md", "hello\n").startswith("wrote"))
