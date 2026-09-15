"""The execution plane and the loop, checked without a provider.  python3 -m unittest -v"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import observer
from observer import Plane, run


class PlaneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.txt").write_text("one\ntwo\nthree\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("".join(f"line {i}\n" for i in range(1, 1001)))
        (self.root / "runs").mkdir()
        (self.root / "runs" / "secret").write_text("the record\n")
        os.symlink("/etc/hostname", self.root / "escape")
        self.plane = Plane(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_root_hides_the_record_and_shows_kinds(self):
        out = self.plane.list(".")
        self.assertIn("file\t14\ta.txt", out)
        self.assertIn("dir\t0\tsub", out)
        self.assertIn("link\t0\tescape", out)
        self.assertNotIn("runs", out)

    def test_paths_cannot_leave_the_world(self):
        for bad in ("..", "../..", "/etc", "escape", "runs/secret"):
            self.assertTrue(self.plane.call("read", {"path": bad}).startswith("error:"), bad)
        self.assertTrue(self.plane.call("list", {"path": ".."}).startswith("error:"))

    def test_read_numbers_lines_and_truncates_with_a_continuation(self):
        out = self.plane.read("a.txt")
        self.assertEqual(out, "1\tone\n2\ttwo\n3\tthree")
        out = self.plane.read("sub/b.txt")
        self.assertTrue(out.startswith("1\tline 1\n"))
        self.assertIn(f"...\ttruncated; continue with start={observer.READ_LINES_CAP + 1}", out)
        out = self.plane.read("sub/b.txt", start=990)
        self.assertTrue(out.startswith("990\tline 990\n"))
        self.assertTrue(out.endswith("1000\tline 1000"))
        self.assertEqual(self.plane.lines_read, 3 + observer.READ_LINES_CAP + 11)

    def test_unknown_function_and_bad_arguments_are_errors_not_crashes(self):
        self.assertTrue(self.plane.call("write", {"path": "x"}).startswith("error:"))
        self.assertTrue(self.plane.call("read", {"nope": 1}).startswith("error:"))


class LoopTest(unittest.TestCase):
    def test_calls_are_executed_recorded_and_the_text_answer_ends_the_run(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "f.txt").write_text("hello\n")
        plane = Plane(Path(tmp.name))
        record = []
        scripted = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "list", "arguments": '{"path": "."}'},
                                },
                                {
                                    "id": "c2",
                                    "type": "function",
                                    "function": {"name": "read", "arguments": '{"path": "f.txt"}'},
                                },
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 0},
            },
            {
                "choices": [{"message": {"role": "assistant", "content": "## Looked at\n."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 7, "prompt_cache_hit_tokens": 10},
            },
        ]
        seen = []

        def provider(messages, tools=True):
            seen.append(json.loads(json.dumps(messages)))
            return scripted.pop(0)

        text, n = run("goal", plane, provider, record.append)
        self.assertEqual(text, "## Looked at\n.")
        self.assertEqual(n["turns"], 2)
        self.assertEqual(n["calls"], 2)
        self.assertEqual(n["stopped"], "answer")
        self.assertEqual(n["prompt_tokens"], 30)
        self.assertEqual(n["cache_hit_tokens"], 10)
        self.assertEqual([m["role"] for m in record], ["system", "user", "assistant", "call", "call", "assistant"])
        self.assertEqual(record[4]["result"], "1\thello")
        tool_msgs = [m for m in seen[1] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["c1", "c2"])

    def test_the_call_cap_forces_a_report(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plane = Plane(Path(tmp.name))
        tool_flags = []

        def provider(messages, tools=True):
            tool_flags.append(tools)
            if tools:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c",
                                        "type": "function",
                                        "function": {"name": "list", "arguments": '{"path": "."}'},
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {},
                }
            return {"choices": [{"message": {"role": "assistant", "content": "report"}}], "usage": {}}

        text, n = run("goal", plane, provider, lambda m: None)
        self.assertEqual(text, "report")
        self.assertEqual(n["stopped"], "cap")
        self.assertEqual(n["calls"], observer.CALL_CAP)
        self.assertEqual(tool_flags[-1], False)


if __name__ == "__main__":
    unittest.main()
