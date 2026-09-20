"""The reviewer's acceptance tests, written from docs/seeds/reviewer-role.md before the code.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel, and the reviewer
executes nothing of the project's, so there is no sandbox to fake.
"""

import collections
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


def watching(*reports):
    """A model answering each session with the next report in turn, the last repeated, and the list
    of the user prompt each session was given -- what it was actually asked, not a repr of it."""
    asked: list[str] = []
    answers = list(reports) or [{"findings": []}]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not any(isinstance(m, ModelResponse) for m in messages):
            asked.append("".join(
                str(part.content) for m in messages for part in getattr(m, "parts", [])
                if type(part).__name__ == "UserPromptPart"
            ))  # fmt: skip
        report = answers[min(len(asked), len(answers)) - 1]
        return ModelResponse(parts=[ToolCallPart("final_result", report, tool_call_id=f"c{len(asked)}")])

    return FunctionModel(model), asked


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
            f'\n[roles.reviewer]\nmodel = "glm-5.3-flash"\nkey = "{self.key}"\n'
        )
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.instance)}))
        # A review is one set of passes per dimension. Every test here but DimensionTest's is about
        # what happens across the passes of one dimension, so it runs with one and a review is
        # PASSES sessions long; the dimensions themselves are DimensionTest's subject.
        self.all_dimensions = tuple(reviewer.DIMENSIONS)
        self.enterContext(mock.patch.object(reviewer, "DIMENSIONS", self.all_dimensions[:1]))

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
        self.assertEqual(numbers["model"], "glm-5.3-flash")
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
        tools = reviewer.builder.Tools(self.checkout, run_dir)
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


    def test_a_reviewer_on_a_model_nothing_can_price_does_not_start(self):
        """seed: the-role-priced-as-another. Both programs reach their role the same way and both
        are bounded the same way, so both refuse the same way: a model neither `PRICE` nor the
        library can price is refused before a model is called and before a record is made, exit 2,
        naming the role and the model. A review is `PASSES` sessions per dimension bounded by what
        each has spent, and passes priced by another model's rate are not bounded at all."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        self.instance.write_text(
            f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n'
            f'\n[roles.reviewer]\nmodel = "a-reviewers-model"\nkey = "{self.key}"\n'
        )
        code, _, err, record = self.review(FunctionModel(counting))
        self.assertEqual(code, 2, err)
        self.assertIn("reviewer", err)
        self.assertIn("a-reviewers-model", err)
        self.assertEqual(called, [], "no model is called before the configuration is usable")
        self.assertIsNone(record, "and no record is made")


class WhatTheSuiteDidNotHoldTest(ReviewerBase):
    """seed: reviewer-role. From the review of run 20260920T000130Z: the load-bearing claims of the
    Goal were true of the code and held by nothing. Each test here kills a one-line mutant that
    passed the whole suite."""

    def test_the_record_reaches_the_store_and_not_only_the_disk(self):
        """The record is committed to the store's git, which is where the key scan happens. Replacing
        `commit_record` with `pass` left every test green: they assert the record's files exist in a
        directory, and a directory is not a commit. A reviewer that writes the diff under review and
        the model's own words somewhere and never scans or commits them is the thing this forbids."""
        model, _ = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        log = subprocess.run(["git", "-C", str(self.runs), "log", "--format=%s"],
                             capture_output=True, encoding="utf-8", env=reviewer.builder.store_env())  # fmt: skip
        self.assertIn(record.name, log.stdout, "the store's git holds the record")
        files = subprocess.run(["git", "-C", str(self.runs), "show", "--name-only", "--format=", "HEAD"],
                               capture_output=True, encoding="utf-8", env=reviewer.builder.store_env())  # fmt: skip
        self.assertIn(f"{record.name}/numbers.json", files.stdout)

    def test_the_record_is_searched_for_every_key_the_configuration_names(self):
        """Not only the key this run was given. `commit_record(store, run_dir, key=key)` -- one
        keyword -- narrows the scan to the reviewer's own key and passes the whole suite, which is
        the exact regression keys-of-the-instance exists to prevent. Here the value planted in the
        change under review belongs to the *builder's* key, which this run never reads."""
        other = self.base / "builder.key"
        other.write_text("key=a-different-secret\n")
        self.instance.write_text(
            f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n'
            f'\n[roles.reviewer]\nmodel = "glm-5.3-flash"\nkey = "{self.key}"\n'
            f'\n[roles.builder]\nmodel = "deepseek-flash"\nkey = "{other}"\n'
        )
        (self.checkout / "f.py").write_text("x = 2\nTOKEN = 'a-different-secret'\n")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(self.checkout, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--amend", "--no-edit")
        model, _ = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 1, "the store would not take a record holding any configured key")
        self.assertNotIn("a-different-secret", err, "the reason never carries the value")
        log = subprocess.run(["git", "-C", str(self.runs), "log", "--format=%s"],
                             capture_output=True, encoding="utf-8", env=reviewer.builder.store_env())  # fmt: skip
        self.assertNotIn(record.name, log.stdout, "and the store holds no commit for it")

    def test_the_role_does_not_tell_the_model_it_can_change_anything(self):
        """The Goal's reason for never offering the three is that a model told it has a hand it does
        not have spends calls discovering otherwise. `ROLE = builder.ROLE` -- which says "change it
        with `write` and `edit`, and test it with `check`" -- passed all 262 tests, because the only
        test that read ROLE scanned it for four words about confidence."""
        role = reviewer.ROLE
        self.assertNotEqual(role, reviewer.builder.ROLE)
        for tool in ("`write`", "`edit`", "`check`"):
            self.assertNotIn(tool, role, tool)
        for tool in ("`list`", "`read`", "`search`"):
            self.assertIn(tool, role, tool)

    def test_the_tools_are_rooted_at_the_checkout_and_nowhere_else(self):
        """No test ever called list, read or search through the reviewer, so rooting them at /etc
        passed the whole suite. The walls are the builder's and are tested there; what was untested
        is that this program hands them the right root."""
        reads = iter([("read", {"path": "f.py"}), ("read", {"path": "../outside.txt"}),
                      ("list", {"path": "."})])  # fmt: skip
        (self.base / "outside.txt").write_text("not the checkout\n")
        returns: list[str] = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            for m in messages:
                for part in getattr(m, "parts", []):
                    if type(part).__name__ == "ToolReturnPart":
                        returns.append(str(part.content))
            play = next(reads, None)
            if play is None:
                return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="z")])
            return ModelResponse(parts=[ToolCallPart(play[0], play[1], tool_call_id=f"c{len(returns)}")])

        code, lines, err, record = self.review(FunctionModel(model))
        self.assertEqual(code, 0, err)
        self.assertTrue(any("x = 2" in r for r in returns), "the checkout's own file is readable")
        self.assertTrue(any("outside the checkout" in r for r in returns), "and nothing above it is")
        self.assertFalse(any("not the checkout" in r for r in returns), "the file above it never arrives")

    def test_the_change_is_shown_in_the_direction_it_was_made(self):
        """Swapping the two ends of the diff shows the model the change backwards and passed the
        suite, because the old assertion looked for `x = 2` and a reversed diff still contains it as
        a removal. What the build added must arrive as an addition."""
        model, told = five()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        asked = told[0]
        self.assertIn("+x = 2", asked, "what the build added arrives as an addition")
        self.assertNotIn("-x = 2", asked, "and not as a removal")
        self.assertIn("-x = 1", asked, "what it replaced arrives as a removal")

    def test_a_run_that_did_not_report_says_so_in_its_exit(self):
        """`return 0 if stopped == "answer" else 1` could be `return 0` and no test noticed: nothing
        ever reached a cap. A review that did not report is not a review, whatever it left behind,
        and the record still holds what happened."""
        def forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            n = sum(1 for m in messages if isinstance(m, ModelResponse))
            return ModelResponse(parts=[ToolCallPart("read", {"path": "f.py"}, tool_call_id=f"c{n}")])

        with mock.patch.object(reviewer.builder, "CALLS_LIMIT", 2):
            code, lines, err, record = self.review(FunctionModel(forever))
        self.assertEqual(code, 1)
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["stopped"], "cap")
        self.assertFalse((record / "review.json").is_file(), "a run that did not report has no report")



class SeedPathTest(ReviewerBase):
    """seed: reviewer-role. From the review of run 20260920T000130Z: the reviewer's second argument
    is a seed, and anything that is not one must be refused rather than read as a goal."""

    def test_an_argument_that_is_not_a_seed_path_is_refused_and_costs_nothing(self):
        """`builder.read_seed` reads a `.md` path as a seed and anything else as the goal text, which
        is right for the builder and wrong here: the reviewer prints `usage: reviewer.py <checkout>
        <seed>` and records a `seed` field. One forgotten `.md` spent a full priced session reviewing
        a real diff against the one-line pseudo-goal `docs/seeds/a-seed`, committed it to the store
        with seed null, and exited 0. A directory and arbitrary prose did the same."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        for given in ("docs/seeds/a-seed", "docs/seeds", "make x bigger than one", "a-seed.md.txt"):
            code, lines, err, record = self.review(FunctionModel(counting), seed=given)
            self.assertEqual(code, 2, f"{given!r} is not a seed: {err}")
            self.assertIn(given, err, given)
        self.assertEqual(called, [], "no model is called")
        self.assertEqual(self.records(), [], "and no record is made")

    def test_a_seed_the_commit_holds_is_still_read_as_one(self):
        """The other half: the refusal is about what is not a seed path, and every seed path that was
        accepted before is accepted still."""
        model, _ = five()
        code, lines, err, record = self.review(model, seed="docs/seeds/a-seed.md")
        self.assertEqual(code, 0, err)
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["seed"], "a-seed")



class PassCeilingTest(ReviewerBase):
    """seed: reviewer-role. From the first real review, 20260920T091432Z: the ceilings were measured
    on builds and a build is one session, so five sessions sharing one budget died against them."""

    def test_each_pass_is_bounded_by_what_that_pass_has_spent(self):
        """The review of 20260920T091432Z spent $0.2531 and was killed by the hard ceiling twelve
        minutes in, because `spent` summed every pass. Under that reading the third pass is landed
        the moment it opens its mouth, whatever it has cost. Here every pass costs less than the
        soft ceiling and the review costs four times it: all five passes run and the review reports,
        which is false the moment the ceiling is the review's rather than the pass's."""
        model, told = five({"findings": [FINDING]})
        with mock.patch.object(reviewer.builder, "price", lambda usage: 0.10):
            code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(told), 5, "every pass ran")
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["passes_ran"], 5)
        self.assertTrue((record / "review.json").is_file())

    def test_a_review_stops_starting_passes_once_it_has_spent_what_its_passes_were_worth(self):
        """A pass may run to `HARD_SPEND`, which is above the soft ceiling the review's total is
        counted in, so a review of runaway passes stops early and a review of ordinary ones never
        touches it. Five passes at 0.20 each cross five times `SOFT_SPEND` after the fourth, so the
        fifth is never started and what the four found is the review."""
        model, told = five({"findings": [FINDING]})
        with mock.patch.object(reviewer.builder, "price", lambda usage: 0.20):
            code, lines, err, record = self.review(model)
        self.assertEqual(len(told), 4, "the fifth pass is never started")
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual((numbers["passes"], numbers["passes_ran"]), (5, 4))
        self.assertTrue((record / "review.json").is_file(), "and what the four found is kept")

    def test_a_review_that_was_capped_keeps_what_its_passes_found(self):
        """The sharpest finding of the first real review: `review.json` is written only when the run
        ends in an answer, so twelve minutes and a quarter of a dollar produced no readable report
        at all -- while the numbers of that same record carried `findings 1`, `findings_seen 5` and
        `agreement 0.2`, aggregated from the passes that did answer and then thrown away. It is
        [[the-work-a-capped-run-leaves]] one layer up: how a run ended is not what decides whether
        its work is real. Two passes answer here and the third is capped by the calls."""
        answers = [{"findings": [FINDING]}, {"findings": [FINDING]}]
        seen = {"n": 0}

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            first = not any(isinstance(m, ModelResponse) for m in messages)
            if first:
                seen["n"] += 1
            if seen["n"] <= 2:
                return ModelResponse(parts=[ToolCallPart("final_result", answers[seen["n"] - 1],
                                                         tool_call_id=f"a{seen['n']}")])  # fmt: skip
            return ModelResponse(parts=[ToolCallPart("read", {"path": "f.py"}, tool_call_id=f"r{len(messages)}")])

        with mock.patch.object(reviewer, "PASSES", 3), \
             mock.patch.object(reviewer.builder, "CALLS_LIMIT", 2):  # fmt: skip
            code, lines, err, record = self.review(FunctionModel(model))
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual((numbers["passes"], numbers["passes_ran"]), (3, 2))
        self.assertTrue((record / "review.json").is_file(), "the two passes that answered are the review")
        written = json.loads((record / "review.json").read_text(encoding="utf-8-sig"))
        self.assertEqual([f["what"] for f in written["findings"]], [FINDING["what"]])
        self.assertEqual(written["passes"], 2, "agreement is over the passes that happened")

    def test_a_review_no_pass_answered_reports_nothing_and_says_so(self):
        """The other side of it: keeping what was found is not the same as inventing a report. A
        review whose every pass was capped has nothing to say and exits saying nothing."""
        def forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart("read", {"path": "f.py"}, tool_call_id=f"c{len(messages)}")])

        with mock.patch.object(reviewer, "PASSES", 2), \
             mock.patch.object(reviewer.builder, "CALLS_LIMIT", 2):  # fmt: skip
            code, lines, err, record = self.review(FunctionModel(forever))
        self.assertEqual(code, 1)
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["passes_ran"], 0)
        self.assertFalse((record / "review.json").is_file())



class DimensionTest(ReviewerBase):
    """seed: reviewer-role. Not "review this change" but one pass per named goal, each dimension
    there because something got past a green check."""

    def setUp(self):
        super().setUp()  # and then the whole set, which is what this class is about
        self.enterContext(mock.patch.object(reviewer, "DIMENSIONS", self.all_dimensions))

    def test_a_review_is_every_dimension_pursued_its_own_passes_over(self):
        """Four dimensions and `PASSES` passes each, none of them told what another found. The count
        is the product: a dimension that shares its passes with the others is three quarters less
        read than the one before it."""
        self.assertEqual(len(self.all_dimensions), 4)
        model, asked = watching({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(asked), len(reviewer.DIMENSIONS) * reviewer.PASSES)
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(numbers["dimensions"], len(reviewer.DIMENSIONS))
        self.assertEqual(numbers["passes"], reviewer.PASSES)

    def test_the_dimension_is_the_last_thing_in_the_prompt(self):
        """The role, the goal and the diff are the same in every session and the dimension is not,
        so the shared material goes first and every session shares one cached prefix. Measured on
        the first real review, 95% of its input was served from cache, which turned $1.18 of input
        into $0.25. It costs nothing to get right and nothing catches it when it is wrong: what the
        sessions have in common must hold the goal and the diff, and what differs must be the tail."""
        model, asked = watching()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        shared = os.path.commonprefix(asked)
        self.assertIn("Make x bigger than one.", shared, "the goal is inside the shared prefix")
        self.assertIn("x = 2", shared, "and so is the change under review")
        tails = {prompt[len(shared):] for prompt in asked}
        self.assertEqual(len(tails), len(reviewer.DIMENSIONS), "one tail per dimension and nothing else")
        for tail in tails:
            self.assertTrue(tail.strip(), "the tail is the dimension, not an empty string")

    def test_each_dimension_is_pursued_by_the_same_number_of_passes(self):
        """No dimension is read harder than another, or the catch rate says more about how the
        passes were shared out than about what the dimensions are worth."""
        model, asked = watching()
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        shared = os.path.commonprefix(asked)
        counts = collections.Counter(prompt[len(shared):] for prompt in asked)
        self.assertEqual(len(counts), len(reviewer.DIMENSIONS), "one group per dimension")
        self.assertEqual(set(counts.values()), {reviewer.PASSES})

    def test_a_finding_carries_the_dimension_that_found_it(self):
        """A finding without the goal it was found under cannot be counted against that goal, and
        counting them is how a dimension that catches nothing gets dropped. The model is not asked
        for it -- it is pursuing one goal and does not need to name it -- so the reviewer stamps it."""
        model, asked = watching({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        written = json.loads((record / "review.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(written["findings"], "something was reported")
        for found in written["findings"]:
            self.assertTrue(found["dimension"], found)
        self.assertLessEqual(len({f["dimension"] for f in written["findings"]}), len(reviewer.DIMENSIONS))

    def test_two_dimensions_that_land_on_one_line_found_two_things(self):
        """Agreement is counted inside a dimension. Two passes found the same thing when they were
        pursuing the same goal and they name the same path and line; two passes asked different
        questions that land on one line were asked different questions, and a reviewer that collapses
        them reports agreement it did not get."""
        model, asked = watching({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        written = json.loads((record / "review.json").read_text(encoding="utf-8-sig"))
        # Every session returned one finding on the same path and line. Within a dimension that is
        # PASSES passes agreeing; across dimensions it is four separate findings, not one of twenty.
        self.assertEqual(len(written["findings"]), len(reviewer.DIMENSIONS))
        for found in written["findings"]:
            self.assertEqual(found["passes"], reviewer.PASSES)
        self.assertEqual({f["dimension"] for f in written["findings"]}.__len__(), len(reviewer.DIMENSIONS))

    def test_the_review_renders_a_note_in_the_record_and_never_in_the_vault(self):
        """`review.md` beside `review.json`, in the shape the review template gives, ready for the
        attended agent to move into `docs/reviews/` once they have reproduced a finding. It does not
        write into the vault itself: `verified` in that template means the attended agent reproduced
        it and `judged` means they decided what it became, and a role that filled either in would be
        marking its own homework."""
        model, asked = watching({"findings": [FINDING]})
        code, lines, err, record = self.review(model)
        self.assertEqual(code, 0, err)
        note = record / "review.md"
        self.assertTrue(note.is_file())
        text = note.read_text(encoding="utf-8")
        self.assertIn("## Findings", text)
        self.assertIn("severity:", text)
        self.assertIn(FINDING["what"], text)
        self.assertIn("### ", text, "one heading per finding")
        self.assertEqual(list((self.checkout / "docs" / "reviews").glob("*")) if
                         (self.checkout / "docs" / "reviews").exists() else [], [],
                         "the vault is the attended agent's to write")  # fmt: skip


if __name__ == "__main__":
    unittest.main()
