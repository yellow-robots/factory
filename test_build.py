"""The build command's acceptance tests, written from docs/seeds/build-from-a-pushed-branch.md
before the code.

    uv run python -m unittest test_build -v

No provider, no network, no docker: the model is scripted with FunctionModel, the sandbox is a
fake, and the project's repository is a bare one in a temporary directory, reached by its path as
git reaches a remote. The instance's configuration names the store of records and the directory
the instance works in, both temporary.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import build
import builder

models.ALLOW_MODEL_REQUESTS = False

BRANCH = "build/make-x-two"
SEED_PATH = "docs/seeds/make-x-two.md"
SEED = "---\ntype: seed\nstatus: building\n---\n\n## Evidence\n\nSome.\n\n## Goal\n\nMake x equal 2 in f.py.\n"
TEST = "import unittest\n\nimport f\n\n\nclass X(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(f.x, 2)\n"
REPORT = {"changed": ["f.py"], "did": ["f.py: x is 2"], "check": "green", "failing": [], "unsure": []}
EDIT = ("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"})
CHECK = ("check", {})


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                         cwd=cwd, capture_output=True, text=True, check=True)  # fmt: skip
    return out.stdout


def scripted(*plays, report=REPORT):
    """A FunctionModel that plays one tool call a turn and then reports."""
    plays = list(plays)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        name, args = plays.pop(0) if plays else ("final_result", report)
        return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"c{len(plays)}")])

    return FunctionModel(model)


class FakeSandbox:
    """Scripted check results, consumed in order."""

    def __init__(self, results):
        self.results = list(results)

    def run(self, checkout, run_dir, n):
        return self.results.pop(0)


class BuildTest(unittest.TestCase):
    """seed: build-from-a-pushed-branch. `build.py <repository> <branch> <seed>`: the request is a
    branch that was pushed, holding a seed at building and its tests red, and the answer is one
    commit pushed to that branch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        home = base / "home"
        home.mkdir()
        self.origin = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.project = base / "project"
        self.project.mkdir()
        git(self.project, "init", "-q", "-b", "main")
        (self.project / "f.py").write_text("x = 1\n")
        (self.project / "check.Dockerfile").write_text("FROM scratch\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "one")
        git(self.project, "remote", "add", "origin", str(self.origin))
        git(self.project, "push", "-q", "origin", "main")
        git(self.project, "checkout", "-q", "-b", BRANCH)
        (self.project / "docs" / "seeds").mkdir(parents=True)
        (self.project / SEED_PATH).write_text(SEED)
        (self.project / "test_f.py").write_text(TEST)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "make-x-two, red")
        git(self.project, "push", "-q", "origin", BRANCH)
        self.requested = self.head()
        self.store, self.work = base / "records", base / "work"
        self.instance = base / "instance.toml"
        self.instance.write_text(f'records = "{self.store}"\nwork = "{self.work}"\n')
        (base / "key").write_text("DEEPSEEK_API_KEY=not-a-key\n")
        self.enterContext(mock.patch.dict(os.environ, {
            "FACTORY_INSTANCE": str(self.instance), "HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg"),
        }))  # fmt: skip
        self.enterContext(mock.patch.object(builder, "KEY_FILE", base / "key"))
        self.enterContext(mock.patch.object(build, "version", lambda: "v9.9"))

    def head(self, ref: str = BRANCH) -> str:
        return git(self.origin, "rev-parse", f"refs/heads/{ref}").strip()

    def records(self) -> list[Path]:
        return sorted(p for p in self.store.iterdir() if p.is_dir() and p.name != ".git") if self.store.exists() else []

    def build(self, model, sandbox, *, branch=BRANCH, seed=SEED_PATH, repository=None) -> tuple[int, list[str], str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = build.main(["build.py", str(repository or self.origin), branch, seed], model=model, sandbox=sandbox)
        return code, out.getvalue().splitlines(), err.getvalue()

    def assert_the_work_is_empty(self):
        """The instance's working directory holds nothing of the build: no clone, no checkout."""
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), [], sorted(str(p) for p in self.work.rglob("*")))

    def test_a_green_build_is_one_commit_pushed_to_the_branch(self):
        """The branch is cloned into the instance's working directory, outside the project and
        outside the store, the builder is run there with the seed's path, and a green check with
        changes becomes one commit on the branch: the requested head its parent, the factory its
        author and committer, its message the seed's name and the trailer git reads, `Built-By:
        factory at <the instance's version>, run <stamp>`, nothing of the model's report in it, and
        its diff what the model changed. The record is the builder's, in the store, and the
        command prints its path first and the commit after it, and leaves nothing in the working
        directory."""
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        built = self.head()
        self.assertEqual(git(self.origin, "rev-parse", f"{built}^").strip(), self.requested)
        self.assertEqual(git(self.origin, "rev-list", "--count", f"{self.requested}..{built}").strip(), "1")
        self.assertEqual(git(self.origin, "show", f"{built}:f.py"), "x = 2\n")
        self.assertEqual(git(self.origin, "diff", "--name-only", self.requested, built).split(), ["f.py"])
        self.assertEqual(git(self.origin, "log", "-1", "--format=%an <%ae>|%cn <%ce>", built).strip(),
                         "factory <factory@localhost>|factory <factory@localhost>")  # fmt: skip
        self.assertEqual(git(self.origin, "log", "-1", "--format=%(trailers:key=Built-By,valueonly)", built).strip(),
                         f"factory at v9.9, run {record.name}")  # fmt: skip
        message = git(self.origin, "log", "-1", "--format=%B", built)
        self.assertTrue(message.startswith("make-x-two"), message)
        self.assertNotIn("x is 2", message)  # the report is the model's and stays in the record
        self.assertEqual(sum(1 for line in message.splitlines() if line.lower().startswith("built-by")), 1, message)
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual(numbers["head"], self.requested)
        self.assertTrue(numbers["checkout"].startswith(str(self.work)), numbers["checkout"])
        self.assertEqual(numbers["seed"], "make-x-two")
        self.assertEqual(Path(lines[0]), record)
        self.assertIn(built[:7], lines[1])
        self.assertIn(BRANCH, lines[1])
        self.assertEqual(git(self.project, "status", "--porcelain"), "")  # the requester's checkout is untouched
        self.assert_the_work_is_empty()

        git(self.project, "pull", "-q", "--ff-only", "origin", BRANCH)  # the answer is a fast-forward for the requester
        self.assertEqual(git(self.project, "rev-parse", "HEAD").strip(), built)

    def test_a_second_build_asks_for_the_branch_again(self):
        """A build takes the branch as the repository has it when it starts, so a second build on a
        branch that moved builds on the new head and pushes on top of it."""
        self.assertEqual(self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))[0], 0)
        first = self.head()
        git(self.project, "pull", "-q", "--ff-only", "origin", BRANCH)
        (self.project / "g.py").write_text("y = 1\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "more, red")
        git(self.project, "push", "-q", "origin", BRANCH)
        moved = self.head()
        code, _, err = self.build(scripted(("write", {"path": "h.py", "content": "z = 1\n"}), CHECK),
                                  FakeSandbox([(0, "OK\n")]))  # fmt: skip
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.origin, "rev-parse", f"{self.head()}^").strip(), moved)
        self.assertEqual(git(self.origin, "show", f"{self.head()}:h.py"), "z = 1\n")
        self.assertEqual(git(self.origin, "rev-list", "--count", f"{first}..{self.head()}").strip(), "2")
        self.assertEqual(len(self.records()), 2)
        self.assert_the_work_is_empty()

    def test_what_the_builder_cannot_build_is_refused_before_anything(self):
        """A usage error, exit 2, saying what is missing, with no model called, no record made,
        nothing pushed and the working directory empty: arguments that are not three, a repository
        git cannot read, a branch it does not have, a seed the branch does not hold or one with no
        Goal, a project with no `check.Dockerfile`, and a configuration with no `work`."""
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT, tool_call_id="c")])

        def refused(*words: str, **where) -> str:
            code, _, err = self.build(FunctionModel(model), FakeSandbox([]), **where)
            self.assertEqual(code, 2, (where, err))
            for word in words:
                self.assertIn(word, err, (where, err))
            self.assertEqual(called, [], where)
            self.assertEqual(self.records(), [], where)
            self.assertEqual(self.head(), self.requested, where)
            self.assert_the_work_is_empty()
            return err

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(["build.py"]), 2)
            self.assertEqual(build.main(["build.py", str(self.origin), BRANCH]), 2)
            self.assertEqual(build.main(["build.py", str(self.origin), BRANCH, SEED_PATH, "more"]), 2)
        nowhere = Path(self.tmp.name) / "no-such.git"
        self.assertIn(str(nowhere), refused(repository=nowhere))
        self.assertIn("build/none", refused(branch="build/none"))
        self.assertIn("docs/seeds/none.md", refused(seed="docs/seeds/none.md"))
        no_goal = "docs/seeds/no-goal.md"
        (self.project / no_goal).write_text("---\ntype: seed\nstatus: building\n---\n\n## Evidence\n\nSome.\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "a seed with no goal")
        git(self.project, "push", "-q", "origin", BRANCH)
        self.requested = self.head()
        self.assertIn(no_goal, refused(seed=no_goal))
        git(self.project, "rm", "-q", "check.Dockerfile")
        git(self.project, "commit", "-q", "-m", "no check")
        git(self.project, "push", "-q", "origin", BRANCH)
        self.requested = self.head()
        self.assertIn("check.Dockerfile", refused())
        self.instance.write_text(f'records = "{self.store}"\n')
        no_work = refused()
        self.assertIn(str(self.instance), no_work)
        self.assertIn("work", no_work)


class VersionTest(unittest.TestCase):
    """seed: build-from-a-pushed-branch. The version a trailer names is the instance's own, read
    from git where the program lives and nothing of the project's."""

    def test_the_version_is_what_git_describes_of_the_instance(self):
        described = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                                   cwd=Path(build.__file__).resolve().parent, capture_output=True, text=True)  # fmt: skip
        expected = described.stdout.strip() if described.returncode == 0 and described.stdout.strip() else "unknown"
        self.assertEqual(build.version(), expected)
        self.assertNotIn(" ", build.version())
        self.assertTrue(build.version())


if __name__ == "__main__":
    unittest.main()
