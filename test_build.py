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

from pydantic_ai import ModelAPIError, models
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
RED_REPORT = {"changed": [], "did": [], "check": "red", "failing": ["test_f"], "unsure": []}
EDIT = ("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"})
CHECK = ("check", {})


def write(root: Path, rel: str, text: str) -> None:
    """A file of the project, its directories made."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
        self.key = base / "key"
        self.key.write_text("DEEPSEEK_API_KEY=not-a-key\n")
        self.instance.write_text(f'records = "{self.store}"\nwork = "{self.work}"\n' + self.builder_role())
        self.enterContext(mock.patch.dict(os.environ, {
            "FACTORY_INSTANCE": str(self.instance), "HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg"),
        }))  # fmt: skip
        self.enterContext(mock.patch.object(build, "version", lambda: "v9.9"))

    def builder_role(self, key: Path | None = None) -> str:
        """The role a build runs as, for a configuration to hold: its model and the file its key is
        read from. The key's place is the instance's, not the program's, since v0.15."""
        return f'\n[roles.builder]\nmodel = "deepseek-flash"\nkey = "{key or self.key}"\n'

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
            # Every refusal here happens before the key is read; the configuration names its place.
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

    def note(self, commit: str) -> str:
        """The factory's note on a commit of the project's repository, empty when it has none."""
        shown = subprocess.run(["git", "notes", "--ref=factory", "show", commit], cwd=self.origin,
                               capture_output=True, text=True)  # fmt: skip
        return shown.stdout if shown.returncode == 0 else ""

    def test_a_build_that_is_not_green_leaves_the_branch_alone_and_says_why(self):
        """A red check, a green check that changed nothing, a run that was capped and left a red
        tree, and one that ended in an error each leave the branch where it was: exit 1, one line
        on stderr naming the record and how the run ended, the record in the store, and nothing
        pushed. The command returns an error and never a commit that might be read as work."""
        red = self.build(scripted(EDIT, CHECK, report=RED_REPORT), FakeSandbox([(1, "FAILED\n")]))
        code, lines, err = red
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        (record,) = self.records()
        self.assertEqual(Path(lines[0]), record)
        self.assertEqual(len(lines), 1)  # no commit named
        self.assertIn(record.name, err)
        self.assertIn("red", err)
        self.assert_the_work_is_empty()

        code, lines, err = self.build(scripted(CHECK), FakeSandbox([(0, "OK\n")]))  # green, nothing changed
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        self.assertIn(self.records()[-1].name, err)
        self.assertIn("nothing", err)

        def writes_forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            done = sum(1 for m in messages if isinstance(m, ModelResponse))
            return ModelResponse(parts=[ToolCallPart("write", {"path": f"g{done}.py", "content": "y = 1\n"},
                                                     tool_call_id=f"c{done}")])

        with mock.patch.object(builder, "CALLS_CEILING", 1):  # capped, and the tree it left is red
            code, lines, err = self.build(FunctionModel(writes_forever), FakeSandbox([(1, "FAILED\n")]))
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        self.assertIn(self.records()[-1].name, err)
        self.assertIn("red", err)

        def falls_over(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "the provider fell over")

        code, lines, err = self.build(FunctionModel(falls_over), FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        self.assertIn(self.records()[-1].name, err)
        self.assertIn("error", err)
        self.assertEqual(len(self.records()), 4)
        self.assert_the_work_is_empty()

    def reads_forever(self, first: tuple[str, dict]):
        """A model that does `first` once and then reads the same file until something stops it."""

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            done = sum(1 for m in messages if isinstance(m, ModelResponse))
            name, args = first if done == 0 else ("read", {"path": "f.py"})
            return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"c{done}")])

        return FunctionModel(model)

    def test_a_capped_run_that_left_a_green_tree_is_taken(self):
        """seed: the-work-a-capped-run-leaves. Seven of the store's thirteen capped builds left a
        tree the builder's own check had passed and every one was thrown away for want of a report,
        seventeen per cent of all build spend. What a build asks of a run is what it already asks:
        a green check on the tree it left, and something changed. How the run ended is not one of
        the questions, and a cap stops being an answer to any of them. The commit says where it
        came from: `Stopped-By` names how the run ended when it did not answer, and `Built-By` is
        untouched, because the gate reads that one."""
        with mock.patch.object(builder, "CALLS_CEILING", 2):
            code, lines, err = self.build(self.reads_forever(EDIT), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual((numbers["stopped"], numbers["check"]), ("cap", "green"))

        built = self.head()
        self.assertNotEqual(built, self.requested)
        self.assertEqual(git(self.origin, "rev-parse", f"{built}^").strip(), self.requested)
        self.assertEqual(git(self.origin, "rev-list", "--count", f"{self.requested}..{built}").strip(), "1")
        self.assertEqual(git(self.origin, "show", f"{built}:f.py"), "x = 2\n")
        self.assertEqual(git(self.origin, "log", "-1", "--format=%(trailers:key=Built-By,valueonly)", built).strip(),
                         f"factory at v9.9, run {record.name}")  # fmt: skip
        self.assertEqual(git(self.origin, "log", "-1", "--format=%(trailers:key=Stopped-By,valueonly)", built).strip(),
                         "cap")  # fmt: skip
        self.assertIn(built[:7], lines[1])
        self.assert_the_work_is_empty()

    def test_a_build_that_answered_says_nothing_about_how_it_stopped(self):
        """seed: the-work-a-capped-run-leaves. The trailer exists to tell a reader of the branch
        that the work arrived without a report, which is only worth saying when it is true: a run
        that answered carries no `Stopped-By` at all."""
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        message = git(self.origin, "log", "-1", "--format=%B", self.head())
        self.assertNotIn("Stopped-By", message, message)

    def test_a_record_the_store_would_not_take_refuses_the_build_though_the_run_was_capped(self):
        """seed: the-work-a-capped-run-leaves. The ordering this rule relied on is gone. A capped
        run used to be refused before the exit code was read, so a non-zero code meant the store
        had refused the record; now a capped run reaches that line carrying the same code as a
        leaked key. A record the store would not take may hold the key, so it refuses the build
        whatever ended the run, the branch stays where it was, and the store holds no commit for
        it."""
        leak = ("write", {"path": "leak.py", "content": "not-a-key\n"})
        with mock.patch.object(builder, "CALLS_CEILING", 2):
            code, lines, err = self.build(self.reads_forever(leak), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 1)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual((numbers["stopped"], numbers["check"]), ("cap", "green"))
        self.assertEqual(self.head(), self.requested, "the branch is where it was")
        self.assertIn(record.name, err)
        self.assertNotIn("not-a-key", err, "the reason never carries the value")
        committed = subprocess.run(["git", "-C", str(self.store), "log", "--format=%s"],
                                   capture_output=True, encoding="utf-8", env=builder.store_env())  # fmt: skip
        self.assertNotIn(record.name, committed.stdout, "the store holds no commit for it")
        self.assert_the_work_is_empty()

    def test_what_a_failed_build_leaves_in_the_repository_is_a_note_on_the_head_it_was_asked_of(self):
        """git keeps what a build failed to do where a requester with no command to read can find
        it: a note of the factory's, `refs/notes/factory`, on the head the build was asked of,
        saying how the run ended and naming the record, pushed to the repository and never a
        branch or a tag of it; a second failure on the same head is added to the first, both kept,
        and a build that ends green leaves no note."""
        self.assertEqual(self.build(scripted(EDIT, CHECK, report=RED_REPORT), FakeSandbox([(1, "FAILED\n")]))[0], 1)
        (first,) = self.records()
        note = self.note(self.requested)
        self.assertIn(first.name, note)
        self.assertIn("red", note)
        self.assertEqual(git(self.origin, "rev-parse", "refs/heads/" + BRANCH).strip(), self.requested)
        refs = git(self.origin, "for-each-ref", "--format=%(refname)").split()
        self.assertIn("refs/notes/factory", refs)
        self.assertEqual([ref for ref in refs if ref.startswith("refs/heads/")],
                         ["refs/heads/" + BRANCH, "refs/heads/main"])  # fmt: skip
        self.assertEqual([ref for ref in refs if ref.startswith("refs/tags/")], [])

        self.assertEqual(self.build(scripted(CHECK), FakeSandbox([(0, "OK\n")]))[0], 1)
        second = self.note(self.requested)
        self.assertIn(first.name, second)  # the first is kept
        self.assertIn(self.records()[-1].name, second)
        self.assertGreater(len(second.splitlines()), len(note.splitlines()))

        self.assertEqual(self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))[0], 0)
        built = self.head()
        self.assertEqual(self.note(built), "")  # a green build leaves none
        self.assertEqual(self.note(self.requested), second)  # and does not touch the one there

    def test_a_branch_that_moved_while_the_build_ran_is_not_overwritten(self):
        """The push is never forced: a branch that moved while the build ran keeps the mover's
        commit, the build is refused and said with the record named, exit 1, and the record stays
        in the store."""
        moved = []

        def move(checkout, run_dir, n):
            if not moved:
                git(self.project, "checkout", "-q", BRANCH)
                (self.project / "other.py").write_text("y = 1\n")
                git(self.project, "add", "-A")
                git(self.project, "commit", "-q", "-m", "meanwhile")
                git(self.project, "push", "-q", "origin", BRANCH)
                moved.append(git(self.project, "rev-parse", "HEAD").strip())
            return 0, "OK\n"

        sandbox = FakeSandbox([])
        sandbox.run = move
        code, lines, err = self.build(scripted(EDIT, CHECK), sandbox)
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), moved[0])
        self.assertEqual(git(self.origin, "show", f"{moved[0]}:f.py"), "x = 1\n")
        (record,) = self.records()
        self.assertIn(record.name, err)
        self.assertIn("moved", err)
        self.assert_the_work_is_empty()

    def test_nothing_leaves_the_instance_holding_the_key_s_value(self):
        """A record the store would not take is a build that pushes nothing, whatever kept it out.
        A change holding the key's value is in the record's own `diff.patch`, so the builder's
        search refuses the record and names that file: the command pushes no commit, the branch
        stays where it was, it exits 1, and no ref of the repository and no note of the factory's
        holds the value, nor does anything said on stderr."""
        leak = ("write", {"path": "leak.py", "content": "TOKEN = 'not-a-key'\n"})
        code, lines, err = self.build(scripted(leak, EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        self.assertNotIn("not-a-key", err)
        self.assertIn("diff.patch", err)
        (record,) = self.records()
        self.assertIn(record.name, err)
        self.assertNotIn("not-a-key", self.note(self.requested))
        self.assertIn(record.name, self.note(self.requested))
        for ref in git(self.origin, "for-each-ref", "--format=%(refname)").split():
            self.assertNotIn("not-a-key", git(self.origin, "log", "-p", "--format=%B", ref))
        self.assert_the_work_is_empty()

    def test_a_record_the_store_would_not_take_is_refused_though_the_store_holds_other_commits(self):
        """seed: the-work-a-capped-run-leaves. From the review of run 20260919T225154Z. Both tests
        that covered a refused record ran against a store with nothing in it, so the store was on an
        unborn HEAD at the moment of the refusal, and every weaker reading passed them: a mutant
        asking `rev-parse --verify HEAD` -- has the store any commit at all -- instead of asking for
        this record's own path passed all 201 tests and pushed the key onto the branch. The setup
        the boundary needs is one build taken before the one refused."""
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        self.requested = self.head()
        taken = self.records()[-1]

        leak = ("write", {"path": "leak.py", "content": "TOKEN = 'not-a-key'\n"})
        code, lines, err = self.build(scripted(leak, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 1)
        refused = self.records()[-1]
        self.assertNotEqual(refused, taken)
        self.assertEqual(self.head(), self.requested, "the branch is where the first build left it")
        self.assertNotIn("not-a-key", err, "the reason never carries the value")
        self.assertIn(refused.name, err)
        committed = subprocess.run(["git", "-C", str(self.store), "log", "--format=%s"],
                                   capture_output=True, encoding="utf-8", env=builder.store_env())  # fmt: skip
        self.assertIn(taken.name, committed.stdout, "the store still holds the first record")
        self.assertNotIn(refused.name, committed.stdout, "and holds no commit for the refused one")
        for ref in git(self.origin, "for-each-ref", "--format=%(refname)").split():
            self.assertNotIn("not-a-key", git(self.origin, "log", "-p", "--format=%B", ref))
        self.assert_the_work_is_empty()

    def test_a_capped_run_whose_check_never_ran_is_refused_though_it_changed_the_tree(self):
        """seed: the-work-a-capped-run-leaves. From the review: of the five things the Goal says
        must still refuse, a check that never ran was pinned by nothing, and a mutant that refused
        only `red` -- dropping the `none` case -- passed all 201 tests while pushing a tree no check
        had ever seen. It is the clause a real capped run is likeliest to reach, since a run capped
        in the middle of writing has often not checked at all. The tree here is changed and the
        sandbox cannot run, so no check of any kind stands behind it."""
        wrote = ("write", {"path": "g.py", "content": "y = 1\n"})
        with mock.patch.object(builder, "CALLS_CEILING", 2):
            code, lines, err = self.build(self.reads_forever(wrote), FakeSandbox([]))
        self.assertEqual(code, 1)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual((numbers["stopped"], numbers["check"]), ("cap", "none"))
        self.assertGreater(numbers["files_changed"], 0, "the tree was changed")
        self.assertEqual(self.head(), self.requested, "and the branch is where it was")
        self.assertIn(record.name, err)
        self.assertIn("did not run", err)
        self.assert_the_work_is_empty()

    def reads_forever_after(self, *plays: tuple[str, dict]):
        """A model that makes each of `plays` once, in order, and then reads one file until
        something stops it."""

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            done = sum(1 for m in messages if isinstance(m, ModelResponse))
            name, args = plays[done] if done < len(plays) else ("read", {"path": "f.py"})
            return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"c{done}")])

        return FunctionModel(model)

    def test_a_green_the_final_check_could_not_confirm_does_not_push_the_tree(self):
        """seed: the-check-that-could-not-run. The model edits, checks green, then writes something
        the check has never seen, and is capped. The builder's own final check is the only thing
        that could speak for that tree, and it cannot run -- the sandbox has nothing left to give,
        which is what a stopped docker daemon looks like from here. `check_final` swallows the
        failure by design, so the record keeps a green that was true of a tree two writes ago, and
        since this version that green is the whole permission to push. The build must refuse, and
        the record must survive: a sandbox that cannot run must not lose it."""
        broken = ("write", {"path": "broken.py", "content": "def (  # not python\n"})
        with mock.patch.object(builder, "CALLS_CEILING", 4):
            code, lines, err = self.build(
                self.reads_forever_after(EDIT, CHECK, broken), FakeSandbox([(0, "OK\n")]))
        (record,) = self.records()
        self.assertTrue((record / "numbers.json").is_file(), "the record survives the failed check")
        self.assertTrue((record / "wire.jsonl.gz").is_file())
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "cap")
        self.assertNotEqual(numbers["check"], "green",
                            "a green the final check could not confirm is not a green")  # fmt: skip
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested, "the branch is where it was")
        self.assertEqual(git(self.origin, "ls-tree", "--name-only", self.head()).split().count("broken.py"), 0)
        self.assert_the_work_is_empty()

    def test_a_failed_build_says_one_line_and_the_note_names_the_record_by_its_stamp(self):
        """seed: build-from-a-pushed-branch. From the review: git's own words run to several lines, and
        the reason of a failed build was all of them, on stderr and in the note pushed into the
        project's repository. What a failed build says is one line of the factory's own words: the
        record by its stamp, never the store's path, then the reason with git's words on one line.
        Reproduced with a repository that refuses the push: a `refs/heads` git cannot write."""
        blocked = self.origin / "refs" / "heads" / "build"
        blocked.mkdir(parents=True, exist_ok=True)

        def block(checkout, run_dir, n):
            blocked.chmod(0o500)
            return 0, "OK\n"

        sandbox = FakeSandbox([])
        sandbox.run = block
        self.addCleanup(blocked.chmod, 0o700)
        code, lines, err = self.build(scripted(EDIT, CHECK), sandbox)
        blocked.chmod(0o700)
        self.assertEqual(code, 1)
        self.assertEqual(self.head(), self.requested)
        (record,) = self.records()
        said = err.strip().splitlines()
        self.assertEqual(len(said), 1, err)
        self.assertTrue(said[0].startswith(f"{record.name}: "), said)
        self.assertNotIn(str(self.store), said[0])
        note = self.note(self.requested).strip().splitlines()
        self.assertEqual(len(note), 1, note)
        self.assertEqual(note[0], said[0])
        self.assertNotIn(str(self.store), self.note(self.requested))
        self.assert_the_work_is_empty()

    def test_a_relative_repository_is_read_from_the_caller_s_directory(self):
        """seed: build-from-a-pushed-branch. From the review: git ran from `/`, so a repository named
        by a relative path was refused as one git cannot read, and a path of that name under the
        root would have been built instead. A repository is read from the directory the command was
        run in, as the caller means it."""
        here = Path.cwd()
        os.chdir(self.origin.parent)
        self.addCleanup(os.chdir, here)
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]),
                                      repository=self.origin.name)  # fmt: skip
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.origin, "rev-parse", f"{self.head()}^").strip(), self.requested)
        self.assert_the_work_is_empty()

    def test_a_seed_whose_name_is_empty_is_no_seed(self):
        """seed: build-from-a-pushed-branch. From the review: a seed named `.md` has an empty name, so
        the message began with the trailer, `git commit` took it for the subject and git read no
        trailer at all; the gate would then refuse the build it just pushed. A seed whose name is
        empty is no seed, refused before the model is called; and the seed's path is read stripped,
        as the builder reads it, so a space around it is no refusal."""
        empty = "docs/seeds/.md"
        write(self.project, empty, SEED)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "a seed with no name")
        git(self.project, "push", "-q", "origin", BRANCH)
        self.requested = self.head()
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT, tool_call_id="c")])

        code, lines, err = self.build(FunctionModel(model), FakeSandbox([]), seed=empty)
        self.assertEqual(code, 2, err)
        self.assertIn(empty, err)
        self.assertEqual(called, [])
        self.assertEqual(self.records(), [])
        self.assertEqual(self.head(), self.requested)

        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]), seed=f"  {SEED_PATH} ")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.origin, "log", "-1", "--format=%s", self.head()).strip(), "make-x-two")
        self.assert_the_work_is_empty()

    def test_a_configuration_the_command_cannot_use_is_refused_in_the_command_s_words(self):
        """seed: build-from-a-pushed-branch. From the review: half the configuration's faults spoke as
        the command and half as the builder, since only `work` was read before the build. The
        command reads the whole configuration first, `records` and `work` alike, so every fault of
        it is the command's usage error, exit 2, naming the configuration's file, with no clone
        made and nothing of the builder's said."""
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT, tool_call_id="c")])

        self.instance.write_text(f'work = "{self.work}"\n')  # no records
        code, lines, err = self.build(FunctionModel(model), FakeSandbox([]))
        self.assertEqual(code, 2, err)
        self.assertIn(str(self.instance), err)
        self.assertIn("usage: build.py", err)
        self.assertNotIn("usage: builder.py", err)
        self.assertEqual(called, [])
        self.assertFalse(self.store.exists())
        self.assert_the_work_is_empty()

    def test_a_work_the_command_cannot_write_is_a_usage_error(self):
        """seed: build-from-a-pushed-branch. From the review: the build's own directory was made
        outside every guard, so a `work` the command cannot write was a traceback. It is a usage
        error naming the work, exit 2, and nothing is pushed."""
        self.work.mkdir(parents=True)
        self.work.chmod(0o500)
        self.addCleanup(self.work.chmod, 0o700)
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 2, err)
        self.assertIn(str(self.work), err)
        self.assertEqual(self.head(), self.requested)
        self.assertEqual(self.records(), [])

    def test_a_build_directory_an_earlier_run_left_is_gone(self):
        """seed: build-from-a-pushed-branch. From the review: nothing swept a build's directory that an
        earlier run left behind, a run killed before it could remove its own. A build removes what
        earlier builds left in the working directory when it starts, and what is not a build's
        directory is left alone."""
        stale = self.work / "build-older"
        (stale / "checkout").mkdir(parents=True)
        (stale / "checkout" / "f.py").write_text("x = 1\n")
        keep = self.work / "notes.txt"
        keep.write_text("not a build's\n")
        code, lines, err = self.build(scripted(EDIT, CHECK), FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        self.assertFalse(stale.exists())
        self.assertTrue(keep.is_file())
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["notes.txt"])

    def test_the_command_s_docstring_says_what_a_failed_build_leaves(self):
        """seed: build-from-a-pushed-branch. The module docstring is where a reader looks first, and it
        stopped at the green ending: it says what a build that is not green leaves, the note git
        keeps beside the branch, the branch that moved, and the exit codes. The builder's error is
        the builder's, named once."""
        for word in ("refs/notes/factory", "moved", "exit 1", "not green"):
            self.assertIn(word, build.__doc__, word)
        self.assertFalse(hasattr(build, "GitFailed"))  # builder.GitError is the one name for it


class VersionTest(unittest.TestCase):
    """seed: build-from-a-pushed-branch. The version a trailer names is the instance's own, read
    from git where the program lives and nothing of the project's."""

    def described(self) -> str:
        """What git says of the instance, the checkout `build.py` lives in, or `unknown`."""
        done = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                              cwd=Path(build.__file__).resolve().parent, capture_output=True, text=True)  # fmt: skip
        return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else "unknown"

    def test_the_version_is_what_git_describes_of_the_instance(self):
        self.assertEqual(build.version(), self.described())
        self.assertNotIn(" ", build.version())
        self.assertTrue(build.version())

    def test_the_version_is_read_where_the_program_lives_and_not_where_it_is_run(self):
        """seed: build-from-a-pushed-branch. From the review: the version must be the instance's own,
        so it is read where `build.py` lives; run inside another repository with a tag of its own,
        the version is still the instance's."""
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "other"
            other.mkdir()
            subprocess.run(["git", "init", "-q", str(other)], check=True)
            (other / "f.txt").write_text("x\n")
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=other, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one"],
                           cwd=other, check=True)  # fmt: skip
            subprocess.run(["git", "tag", "vOTHER"], cwd=other, check=True)
            here = Path.cwd()
            os.chdir(other)
            try:
                self.assertEqual(build.version(), self.described())
            finally:
                os.chdir(here)
            self.assertNotIn("vOTHER", build.version())


if __name__ == "__main__":
    unittest.main()
