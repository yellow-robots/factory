"""The reviewer's acceptance tests, written from docs/seeds/reviewer-role.md before the code.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel, and the reviewer
executes nothing of the project's, so there is no sandbox to fake.
"""

import contextlib
import gzip
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

import reviewer

models.ALLOW_MODEL_REQUESTS = False

FINDING = {"severity": "defect", "path": "f.py", "line": 2, "what": "x is never read after it is set"}
OTHER = {"severity": "smell", "path": "f.py", "line": 5, "what": "the name says nothing"}


def git(checkout: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, encoding="utf-8")
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return done.stdout


def answering(report=None):
    """A model that answers the reviewer's session with one report, and the list of what it was
    told, so a test can read what the session was actually given."""
    told: list[str] = []
    answer = {"findings": []} if report is None else report

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        told.append(repr(messages))
        return ModelResponse(parts=[ToolCallPart("final_result", answer, tool_call_id=f"c{len(told)}")])

    return FunctionModel(model), told


def passes(*reports):
    """A model answering each of the reviewer's sessions with the next report in turn, and the list
    of what each session was told, so a test can see that no pass was told what another found."""
    told: list[str] = []
    answers = list(reports)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        told.append(repr(messages))
        report = answers[min(len(told), len(answers)) - 1]
        return ModelResponse(parts=[ToolCallPart("final_result", report, tool_call_id=f"c{len(told)}")])

    return FunctionModel(model), told


def five(*reports):
    """Five passes, the last report repeated when fewer are given."""
    given = list(reports) or [{"findings": []}]
    return passes(*(given + [given[-1]] * (5 - len(given)))[:5])


class ReviewerBase(unittest.TestCase):
    """A checkout whose head is a commit a build left, and an instance that names a reviewer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.checkout = self.base / "checkout"
        (self.checkout / "docs" / "seeds").mkdir(parents=True)
        (self.checkout / "f.py").write_text("x = 1\n")
        (self.checkout / "test_f.py").write_text("def test_x():\n    assert True\n")
        (self.checkout / "docs" / "seeds" / "a-seed.md").write_text(
            "---\ntype: seed\n---\n\n## Goal\n\nMake x bigger than one.\n"
        )
        git(self.checkout, "init", "-q")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "before")
        (self.checkout / "f.py").write_text("x = 2\n")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "the build")
        self.runs = self.base / "records"
        self.key = self.base / "reviewer.key"
        self.key.write_text("key=not-a-key\n")
        self.instance = self.base / "instance.toml"
        self.instance.write_text(
            f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n'
            f'\n[roles.reviewer]\nmodel = "a-reviewers-model"\nkey = "{self.key}"\n'
        )
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.instance)}))

    def records(self) -> list[Path]:
        if not self.runs.exists():
            return []
        return sorted(p for p in self.runs.iterdir() if p.is_dir() and p.name != ".git")

    def review(self, model, seed="docs/seeds/a-seed.md", checkout=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = reviewer.main(["reviewer.py", str(checkout or self.checkout), seed], model=model)
        found = self.records()
        return code, out.getvalue().splitlines(), err.getvalue(), (found[0] if found else None)


class ReviewRecordTest(ReviewerBase):
    """What a review is: a read-only session over a delivered tree, recorded like a build."""

    def test_a_review_leaves_a_record_of_its_own_in_the_store(self):
        """seed: reviewer-role. A role that cannot be measured cannot be given a responsibility, so a
        review is recorded as a build is: its own stamp in the instance's store, the wire it sent,
        what it found and its numbers, with the record's path the first line printed. It runs as the
        role `reviewer`, whose model and key the configuration names."""
        model, _ = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(lines[0], str(record))
        self.assertEqual(record.parent, self.runs)
        for name in ("goal.txt", "wire.jsonl.gz", "review.json", "numbers.json"):
            self.assertTrue((record / name).is_file(), name)
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["role_name"], "reviewer")
        self.assertEqual(numbers["model"], "a-reviewers-model")
        self.assertEqual(numbers["head"], git(self.checkout, "rev-parse", "HEAD").strip())
        self.assertEqual(numbers["seed"], "a-seed")

    def test_the_reviewer_is_offered_nothing_that_writes(self):
        """seed: reviewer-role. A reviewer that could fix what it finds would become a builder and
        acquire an interest in finding less. What it can do is what the request offers the model:
        the builder's three tools that read, and the one the report comes back through. Read off the
        wire, which is what was actually sent, not off the program's own list."""
        model, _ = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        offered = set()
        for line in gzip.decompress((record / "wire.jsonl.gz").read_bytes()).splitlines():
            for tool in (json.loads(line).get("body") or {}).get("tools") or []:
                offered.add(tool["function"]["name"])
        self.assertEqual(offered, {"list", "read", "search", "final_result"})

    def test_the_session_is_given_the_goal_and_the_change_under_review(self):
        """seed: reviewer-role. Two questions a machine cannot answer -- does the code do what its
        tests claim, and what else did it change -- need both halves in front of the model: the
        seed's Goal as the builder reads one, and the diff of the commit the head is."""
        model, told = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(told), reviewer.PASSES)
        asked = told[0]
        self.assertIn("Make x bigger than one.", asked)
        self.assertIn("x = 2", asked, "the change under review is in front of it")
        self.assertIn("f.py", asked)
        self.assertEqual((record / "goal.txt").read_text().strip().splitlines()[0], "Make x bigger than one.")

    def test_the_reviewer_is_never_asked_how_confident_it_is(self):
        """seed: reviewer-role. A model's account of its own certainty has been measured to be worse
        in places than a constant guess, so nothing asks for one: no field of the report, and no
        word of the role. The budget is the number of passes and nothing else."""
        schema = json.dumps(reviewer.ReviewReport.model_json_schema()).lower()
        for word in ("confidence", "certainty", "probability", "how sure"):
            self.assertNotIn(word, schema, word)
            self.assertNotIn(word, reviewer.ROLE.lower(), word)

    def test_a_finding_carries_where_it_is_and_what_is_wrong(self):
        """seed: reviewer-role. A finding that names nothing cannot be verified by whoever must
        judge it, so the shape carries the severity the notes already use, the path it points at,
        the line and what is wrong. What the model returned is what the record holds."""
        model, _ = five({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        written = json.loads((record / "review.json").read_text(encoding="utf-8-sig"))
        (found,) = written["findings"]
        self.assertEqual(found["severity"], "defect")
        self.assertEqual(found["path"], "f.py")
        self.assertEqual(found["line"], 2)
        self.assertIn("never read", found["what"])

    def test_what_the_reviewer_cannot_review_is_a_usage_error(self):
        """seed: reviewer-role. Refused before a model is called and before a record is made, exit 2,
        each in its own words: a directory that is not a git checkout, a head with no commit before
        it to compare against, and a seed the head's commit does not hold."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        plain = self.base / "plain"
        plain.mkdir()
        code, _, err, _ = self.review(FunctionModel(counting), checkout=plain)
        self.assertEqual(code, 2, err)
        self.assertIn(str(plain), err)

        first = self.base / "first"
        first.mkdir()
        (first / "f.py").write_text("x = 1\n")
        git(first, "init", "-q")
        git(first, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(first, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "only one")
        code, _, err, _ = self.review(FunctionModel(counting), checkout=first)
        self.assertEqual(code, 2, err)

        code, _, err, _ = self.review(FunctionModel(counting), seed="docs/seeds/no-such.md")
        self.assertEqual(code, 2, err)
        self.assertIn("no-such", err)

        self.assertEqual(called, [])
        self.assertEqual(self.records(), [])



class PassesTest(ReviewerBase):
    """Five readings, and what is made of the five."""

    def test_the_review_is_five_independent_passes(self):
        """seed: reviewer-role. One reading of a change finds a minority of what is in it, and five
        readings of the same change agree on very little, so the review is five cold sessions and
        none is told what another found."""
        model, told = five({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(told), 5)
        self.assertEqual(reviewer.PASSES, 5)
        self.assertEqual(json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))["passes"], 5)
        for text in told:
            self.assertNotIn(FINDING["what"], text, "a pass is never told what another pass found")

    def test_a_finding_only_one_pass_reached_is_not_reported(self):
        """seed: reviewer-role. A reviewer whose findings are mostly noise is one nobody reads, and a
        reviewer nobody reads has no recall at all: what two or more passes reached is reported, what
        one reached alone is not, and the numbers still count everything seen."""
        model, _ = passes(
            {"findings": [FINDING, OTHER]},
            {"findings": [FINDING]},
            {"findings": [FINDING]},
            {"findings": []},
            {"findings": []},
        )
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        review = json.loads((record / "review.json").read_text())
        self.assertEqual([f["what"] for f in review["findings"]], [FINDING["what"]])
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["findings_seen"], 2)
        self.assertEqual(numbers["findings_reported"], 1)

    def test_a_finding_carries_how_many_passes_reached_it(self):
        """seed: reviewer-role. How much agreement stood behind a finding is what tells a reader how
        far to trust it, so every reported finding carries the count. Two passes name the same
        finding when they name the same path and the same line, which is crude and is what the
        record says was done."""
        model, _ = passes(
            {"findings": [FINDING]},
            {"findings": [dict(FINDING, what="x is set and never read")]},
            {"findings": [FINDING, OTHER]},
            {"findings": [OTHER]},
            {"findings": []},
        )
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        review = json.loads((record / "review.json").read_text())
        self.assertEqual({f["line"]: f["passes"] for f in review["findings"]}, {2: 3, 5: 2})

    def test_the_answer_is_what_was_found_and_how_far_the_passes_agreed(self):
        """seed: reviewer-role. Five passes over a change cannot warrant saying a contract is met, so
        the reviewer never says it. What it answers with is what it found, how many passes ran, and
        how much they overlapped -- the share of everything seen that more than one pass reached,
        which is what tells a reader how far to trust the silence."""
        model, _ = passes(
            {"findings": [FINDING]}, {"findings": [FINDING]}, {"findings": [OTHER]},
            {"findings": []}, {"findings": []},
        )  # fmt: skip
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        review = json.loads((record / "review.json").read_text())
        self.assertEqual(review["passes"], 5)
        self.assertEqual(review["agreement"], 0.5)  # one of the two things seen was reached twice
        for word in ("meets", "verdict", "approved", "passes the contract"):
            self.assertNotIn(word, json.dumps(review).lower().replace('"passes":', ""), word)



class RoleServedElsewhereTest(ReviewerBase):
    """seed: the-role-served-somewhere-else. The reviewer builds its model the way the builder does,
    and the role it runs as on this host is on another provider."""

    def test_the_reviewer_reaches_a_role_served_elsewhere(self):
        """The reviewer's own agent honours the role's address and does not claim DeepSeek's profile
        of a model that is not one. Without this the role this host already configures could not
        have made a single request."""
        run_dir = self.base / "lens"
        run_dir.mkdir()
        tools = reviewer.builder.Tools(self.checkout, run_dir, budget=10)
        agent = reviewer.build_agent(
            tools, key="k", model_name="glm-5.3-flash",
            base_url="https://open.bigmodel.cn/api/paas/v4",
        )  # fmt: skip
        self.assertEqual(agent.model.model_name, "glm-5.3-flash")
        self.assertIn("bigmodel.cn", str(agent.model.client.base_url))
        self.assertIs(agent.model.profile["openai_supports_forced_tool_choice_with_thinking"], True,
                      "DeepSeek's answer to its own hazard is not claimed of another model")  # fmt: skip

    def test_the_reviewer_passes_its_roles_address_to_the_agent(self):
        """The address is the role's, so it comes from the configuration and not from the program:
        a run whose role names one reaches it without the caller saying anything."""
        self.instance.write_text(
            f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n'
            f'\n[roles.reviewer]\nmodel = "glm-5.3-flash"\nkey = "{self.key}"\n'
            f'base_url = "https://open.bigmodel.cn/api/paas/v4"\n'
        )
        seen = {}
        real = reviewer.build_agent

        def spy(*args, **kw):
            seen.update(kw)
            return real(*args, **{**kw, "model": kw.get("model")})

        model, _ = five()
        with mock.patch.object(reviewer, "build_agent", spy):
            code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(seen.get("base_url"), "https://open.bigmodel.cn/api/paas/v4")
        self.assertEqual(seen.get("model_name"), "glm-5.3-flash")


if __name__ == "__main__":
    unittest.main()
