"""The catch-rate harness's acceptance tests, written from docs/seeds/the-catch-rate-that-decides-the-role.md
before the code.

    uv run python -m unittest test_catch -v

Each test builds a temporary repository with a commit worth reviewing, a `catches/` directory
holding one or two cases whose answers point into that commit, an instance whose `reviewer` role
names a model and a key, and runs `catch.main` with a model that plays every pass from a script. No
provider, no network, no docker.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import builder
import catch
import reviewer

models.ALLOW_MODEL_REQUESTS = False

SEED = "---\ntype: seed\n---\n\n## Goal\n\nMake x equal two in f.py, and leave everything else alone.\n"
# The file the case's answers point into: the defect is on line 3 and the span is the function.
CODE = "def f():\n    x = 1\n    return x  # the answer's line\n\n\ndef g():\n    return 0\n"


def git(checkout: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(checkout), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, encoding="utf-8")  # fmt: skip
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return done.stdout


def finding(path="f.py", line=3, severity="defect", what="x is set and never read"):
    return {"severity": severity, "path": path, "line": line, "what": what}


def passes(*reports):
    """A model answering each session with the next report, the last repeated. A review reports
    what two or more passes of one dimension reached, so a finding meant to survive is given twice."""
    told: list[str] = []
    answers = list(reports) or [{"findings": []}]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        report = answers[min(len(told), len(answers)) - 1] if told else answers[0]
        told.append(repr(messages))
        return ModelResponse(parts=[ToolCallPart("final_result", report, tool_call_id=f"c{len(told)}")])

    return FunctionModel(model), told


def agreed(*findings):
    """Every pass reporting the same findings, so all of them clear the agreement rule."""
    return passes({"findings": list(findings)})


class CatchBase(unittest.TestCase):
    """A repository with something to review, and a case whose answers point into it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        (self.repo / "docs" / "seeds").mkdir(parents=True)
        (self.repo / "f.py").write_text("def f():\n    return 0\n")
        (self.repo / "docs" / "seeds" / "a-seed.md").write_text(SEED)
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "before")
        (self.repo / "f.py").write_text(CODE)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "the build")
        self.commit = git(self.repo, "rev-parse", "--short", "HEAD").strip()

        self.catches = self.repo / "catches"
        self.catches.mkdir()
        self.case("one")

        self.runs = self.base / "records"
        self.key = self.base / "reviewer.key"
        self.key.write_text("key=not-a-key\n")
        self.instance = self.base / "instance.toml"
        self.instance.write_text(
            f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n'
            f'\n[roles.reviewer]\nmodel = "glm-5.3-flash"\nkey = "{self.key}"\n'
        )
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.instance)}))
        # One dimension, so a review is PASSES sessions long and a test's script is readable.
        self.enterContext(mock.patch.object(reviewer, "DIMENSIONS", tuple(reviewer.DIMENSIONS)[:1]))

    def case(self, name, findings=((("f.py"), (1, 4)),)):
        """A case file: the commit, the seed, and one entry per known finding."""
        body = [f'commit = "{self.commit}"', 'seed = "docs/seeds/a-seed.md"']
        for path, (first, last) in findings:
            body += ["", "[[finding]]", 'review = "20260101T000000Z"', f'title = "{name} answer"',
                     f'path = "{path}"', f"lines = [{first}, {last}]"]  # fmt: skip
        (self.catches / f"{name}.toml").write_text("\n".join(body) + "\n")

    def record(self, name="one", findings=(), passes_ran=20, cost=2.5787, seconds=6836.8):
        """A review's record as the store holds one, without having run a review to get it."""
        made = self.runs / "20260101T000000Z"
        made.mkdir(parents=True, exist_ok=True)
        (made / "goal.txt").write_text(f"case: {name}\nthe goal that was reviewed\n")
        (made / "review.json").write_text(json.dumps({"findings": list(findings)}))
        (made / "numbers.json").write_text(json.dumps(
            {"passes_ran": passes_ran, "cost_usd": cost, "seconds": seconds, "stopped": "answer"}))
        return made

    def records(self):
        if not self.runs.exists():
            return []
        return sorted(p for p in self.runs.iterdir() if p.is_dir() and p.name != ".git")

    def run_catch(self, *args, model=None):
        """The harness over that repository: its exit code, its stdout lines and its stderr."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = catch.main(["catch.py", *args], root=self.repo, model=model)
        return code, out.getvalue().splitlines(), err.getvalue()


class SpendTest(CatchBase):
    """A review's cost is chosen, not discovered, so the harness says it before it spends it."""

    def test_what_a_run_will_cost_is_said_before_a_model_is_called(self):
        """seed: the-catch-rate-that-decides-the-role. A review is `dimensions x passes x
        SOFT_SPEND` and the harness knows every one of those before the first pass starts, so what
        the whole run comes to is arithmetic and not a surprise. The full set is a decision somebody
        takes on purpose."""
        projected = len(reviewer.DIMENSIONS) * reviewer.PASSES * builder.SOFT_SPEND
        model, told = agreed(finding())
        code, lines, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        self.assertTrue(any(f"{projected:.2f}" in line for line in lines),
                        f"what it would cost is not in {lines}")  # fmt: skip

    def test_a_run_over_what_it_was_allowed_does_not_start(self):
        """seed: the-catch-rate-that-decides-the-role. Twelve cases at four dimensions is $83 and
        days, and the owner's direction is that the number is worth having and is not worth having
        by surprise. A run that would cost more than it was told it may spend is refused before a
        model is called and before a record is made, naming both numbers."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        self.case("two")
        code, lines, err = self.run_catch("--spend", "0.10", model=FunctionModel(counting))
        self.assertEqual(code, 2, err)
        self.assertIn("0.10", err + "\n".join(lines))
        self.assertEqual(called, [], "no model is called")
        self.assertEqual(self.records(), [], "and no record is made")

    def test_what_a_run_may_spend_bounds_what_it_can_spend(self):
        """seed: the-catch-rate-that-decides-the-role. Run 20260920T124559Z projected $2.50, was
        allowed $3.00, and could have spent $5.00: a pass may run to `HARD_SPEND`, which is above
        the ceiling the projection is counted in, so the projection is what a run is expected to
        cost and never what it may. The allowance is checked against what it could cost. Both
        numbers are said, because the difference between them is the difference between a plan and
        a promise."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        passes_run = len(reviewer.DIMENSIONS) * reviewer.PASSES
        expected = passes_run * builder.SOFT_SPEND
        most = passes_run * builder.HARD_SPEND
        allowed = (expected + most) / 2  # room for the projection, not for the ceiling above it
        self.assertLess(expected, allowed, "the fixture must leave the projection affordable")
        code, lines, err = self.run_catch("--spend", f"{allowed:.4f}", model=FunctionModel(counting))
        said = err + "\n".join(lines)
        self.assertEqual(code, 2, said)
        self.assertEqual(called, [], "no model is called")
        self.assertEqual(self.records(), [], "and no record is made")
        self.assertIn(f"{most:.2f}", said, "what it could cost is not said")
        self.assertIn(f"{expected:.2f}", said, "what it is expected to cost is not said")

    def test_the_ceiling_is_what_a_review_can_reach_and_not_its_passes_at_their_worst(self):
        """seed: the-catch-rate-that-decides-the-role. A review stops starting passes once it has
        spent `dimensions x passes x SOFT_SPEND`, so the most it can reach is that plus the one pass
        already running. Counting every pass at `HARD_SPEND` doubles it and refuses runs that were
        affordable -- the twelve-case set reading $60 where it cannot exceed about $33, which is a
        different decision to put in front of someone."""
        stopping = len(reviewer.DIMENSIONS) * reviewer.PASSES * builder.SOFT_SPEND
        most = stopping + builder.HARD_SPEND  # the rule, and the pass that was already running
        every_pass_at_its_worst = len(reviewer.DIMENSIONS) * reviewer.PASSES * builder.HARD_SPEND
        self.assertLess(most, every_pass_at_its_worst, "the fixture must tell the two apart")
        model, _ = agreed(finding(path="f.py", line=3))
        code, lines, err = self.run_catch("--spend", f"{most + 0.01:.4f}", model=model)
        self.assertEqual(code, 0, f"a run it could afford was refused: {err}")
        self.assertTrue([line for line in lines if line.startswith("one\t")], lines)

    def test_a_run_that_could_reach_past_its_allowance_still_does_not_start(self):
        """seed: the-catch-rate-that-decides-the-role. The other side of the same sentence: the
        ceiling moved down, it did not stop being a ceiling."""
        stopping = len(reviewer.DIMENSIONS) * reviewer.PASSES * builder.SOFT_SPEND
        most = stopping + builder.HARD_SPEND
        code, lines, err = self.run_catch("--spend", f"{most - 0.01:.4f}", model=agreed()[0])
        self.assertEqual(code, 2, err)
        self.assertEqual(self.records(), [], "and no record is made")
        self.assertIn(f"{most:.2f}", err + "\n".join(lines), "what it could cost is not said")

    def test_the_allowance_is_required_rather_than_assumed(self):
        """seed: the-catch-rate-that-decides-the-role. There is no default that spends money. A run
        that does not say what it may spend is a usage error, not a run at the harness's guess."""
        code, _, err = self.run_catch(model=agreed()[0])
        self.assertEqual(code, 2, err)


class ScoreTest(CatchBase):
    """Scoring a record the store already holds: arithmetic, not a review."""

    def test_a_record_already_made_is_scored_without_being_reviewed_again(self):
        """seed: the-catch-rate-that-decides-the-role. The first run cost $2.5787 and printed a
        number that was wrong, because an answer's span was too wide. Correcting the span is a
        two-character edit and seeing the corrected number must not cost another $2.5787: a record
        holds every finding its review reported, and scoring is arithmetic over those and the case's
        answers. No worktree, no pass, no model, nothing spent."""
        called = []

        def counting(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", {"findings": []}, tool_call_id="c")])

        self.record(findings=[finding(path="f.py", line=3)])
        code, lines, err = self.run_catch("--score", model=FunctionModel(counting))
        self.assertEqual(code, 0, err)
        self.assertEqual(called, [], "no model is called to score what is already recorded")
        self.assertEqual([p.name for p in self.records()], ["20260101T000000Z"], "and no record is made")
        (row,) = [line for line in lines if line.startswith("one\t")]
        self.assertEqual(row.split("\t")[1:4], ["1", "1", "1"], row)

    def test_scoring_asks_for_no_allowance_because_it_spends_nothing(self):
        """seed: the-catch-rate-that-decides-the-role. `--spend` exists so that a run costing money
        says so first. Scoring costs nothing, so requiring an allowance for it would be a wall in
        front of a door."""
        self.record(findings=[finding(path="f.py", line=3)])
        code, _, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)

    def test_a_corrected_answer_changes_the_number_without_a_new_review(self):
        """seed: the-catch-rate-that-decides-the-role. This is the whole point. The same record
        scored against a span that swallows an unrelated finding reads one, and against the span
        narrowed to what the answer is really about reads nothing -- which is the correction the
        first run needed and the reason this exists."""
        self.record(findings=[finding(path="f.py", line=7)])
        self.case("one", findings=((("f.py"), (1, 8)),))  # wide enough to swallow the other function
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (wide,) = [line for line in lines if line.startswith("one\t")]
        self.case("one", findings=((("f.py"), (1, 4)),))  # the span the answer is really about
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (narrow,) = [line for line in lines if line.startswith("one\t")]
        self.assertEqual((wide.split("\t")[1], narrow.split("\t")[1]), ("1", "0"),
                         f"the span made no difference: {wide} / {narrow}")  # fmt: skip


    def test_a_case_with_no_record_is_unmeasured_rather_than_missed(self):
        """seed: the-catch-rate-that-decides-the-role. Scoring the two cases of 2026-09-20 with one
        never run read a strict rate of 0.250 where the measured half alone read 0.500, because a
        case with no findings to score was counted as a case whose findings were all missed. Those
        are different things: a review that found nothing is evidence and a review that never ran is
        not. The unmeasured case is shown, so nobody forgets it is owed, and it is not in the rate."""
        self.record(name="one", findings=[finding(path="f.py", line=3)])
        self.case("two")  # a second case, never run
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (unmeasured,) = [line for line in lines if line.startswith("two\t")]
        self.assertNotIn("0", unmeasured.split("\t")[1:3], f"an unrun case is counted in {unmeasured}")
        rate = [line for line in lines if line.startswith("strict rate")]
        self.assertTrue(any("1.0" in line or "0.5" in line for line in rate),
                        f"the rate is not the measured case's: {rate}")  # fmt: skip


    def test_scoring_when_nothing_was_measured_is_an_answer_and_not_a_crash(self):
        """seed: the-catch-rate-that-decides-the-role. Write a case's answers, score, then decide
        whether to spend on it -- that is the ordinary order, and it ends in a ZeroDivisionError
        because a rate was computed over no measurements at all. There is no rate to print when
        nothing was measured, and no rate is an answer rather than a failure."""
        self.case("two")
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertTrue(any(line.startswith(("one\t", "two\t")) for line in lines), lines)
        self.assertFalse([line for line in lines if line.startswith("strict rate")],
                         f"a rate over nothing: {lines}")  # fmt: skip

    def test_a_review_that_could_not_be_started_is_unmeasured_too(self):
        """seed: the-catch-rate-that-decides-the-role. The same thing on the running path as on the
        scoring one. A commit git cannot check out, a reviewer that refused, a review that raised:
        none of them is a review that found nothing, and counting them as misses drags a rate down
        with cases that were never asked. Exit still says something went wrong; the printed number
        is the one people quote and it must not be wrong."""
        (self.catches / "bad.toml").write_text(
            'commit = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"\nseed = "docs/seeds/a-seed.md"\n'
            '\n[[finding]]\nreview = "r"\ntitle = "t"\npath = "f.py"\nlines = [1, 4]\n'
        )
        model, _ = agreed(finding(path="f.py", line=3))
        code, lines, err = self.run_catch("--spend", "10", model=model)
        (bad,) = [line for line in lines if line.startswith("bad\t")]
        self.assertNotIn("0", bad.split("\t")[1:3], f"a case never reviewed is counted in {bad}")
        (rate,) = [line for line in lines if line.startswith("strict rate")]
        self.assertIn("1.0", rate, f"the rate is not the measured case's: {rate}")
        self.assertEqual(code, 1, err)

    def test_a_case_that_knows_no_findings_is_not_a_case(self):
        """seed: the-catch-rate-that-decides-the-role. A case with no answers scored zero of zero
        and averaged a flat 0.0 into the rate, so adding one halved the number. Catching cannot be
        measured against nothing: a case that names no finding is not whole and is refused, the way
        the gate refuses a seed whose status has facts missing."""
        (self.catches / "empty.toml").write_text(
            f'commit = "{self.commit}"\nseed = "docs/seeds/a-seed.md"\n'
        )
        code, _, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 2, err)
        self.assertIn("empty", err)


class PinTest(CatchBase):
    """Mutants that survived the whole suite. The code is right; nothing held it."""

    def test_the_error_beside_a_rate_is_the_error_of_that_rate(self):
        """seed: the-catch-rate-that-decides-the-role. `a wrong error bar is the exact failure this
        exists to prevent`, and three separate mutations of it survived every test: zeroing it,
        leaving it undivided, and dropping the numerator of the variance. One catch of two known is
        the Beta(k+1, n-k+1) posterior's 0.500 and 0.224, which is `evals.py`'s own arithmetic."""
        self.record(findings=[finding(path="f.py", line=3)])
        self.case("one", findings=((("f.py"), (1, 4)), (("f.py"), (6, 8))))
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (rate,) = [line for line in lines if line.startswith("strict rate")]
        self.assertIn("0.500", rate, rate)
        self.assertIn("0.224", rate, f"the error is not the rate's: {rate}")

    def test_the_rate_is_counted_over_what_the_case_knows(self):
        """seed: the-catch-rate-that-decides-the-role. The denominator was unheld: a mutant counting
        catches over catches printed 1.000 for any case that caught anything at all."""
        self.record(findings=[finding(path="f.py", line=3)])
        self.case("one", findings=((("f.py"), (1, 4)), (("f.py"), (6, 8))))
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (row,) = [line for line in lines if line.startswith("one\t")]
        self.assertEqual(row.split("\t")[1:4], ["1", "2", "2"], row)  # both answers are in f.py

    def test_a_span_holds_its_own_ends_and_nothing_before_them(self):
        """seed: the-catch-rate-that-decides-the-role. Dropping the lower bound survived, and so did
        making both ends exclusive. The corpus turns on this: the span `[186, 191]` was narrowed to
        exactly that so 191 is inside and 192 is out, and without a lower bound a finding anywhere
        earlier in the file would score."""
        self.case("one", findings=((("f.py"), (4, 6)),))
        for line, caught in ((4, "1"), (6, "1"), (3, "0"), (1, "0")):
            for record in self.records():
                shutil.rmtree(record)
            self.record(findings=[finding(path="f.py", line=line)])
            code, lines, err = self.run_catch("--score", model=agreed()[0])
            self.assertEqual(code, 0, err)
            (row,) = [line_ for line_ in lines if line_.startswith("one\t")]
            self.assertEqual(row.split("\t")[1], caught, f"line {line}: {row}")

    def test_one_known_finding_is_caught_once_however_many_name_its_file(self):
        """seed: the-catch-rate-that-decides-the-role. The path count de-duplicates on the answer's
        side and a mutant counting every report that named the file survived. On the first real
        record fourteen of sixteen findings name `reviewer.py`, so that mutant would have printed a
        path rate of fourteen against two known."""
        self.record(findings=[finding(path="f.py", line=1), finding(path="f.py", line=7),
                              finding(path="f.py", line=9)])  # fmt: skip
        code, lines, err = self.run_catch("--score", model=agreed()[0])
        self.assertEqual(code, 0, err)
        (row,) = [line for line in lines if line.startswith("one\t")]
        self.assertEqual(row.split("\t")[2], "1", f"one answer caught more than once: {row}")

    def test_a_case_is_reviewed_at_the_commit_it_names_and_not_at_the_head(self):
        """seed: the-catch-rate-that-decides-the-role. The whole measurement rests on the case's
        commit being checked out, and the fixture made that commit the head, so replacing it with
        `HEAD` passed every test. Real cases name old commits: 3e01d73 and 8125f19, both with
        descendants."""
        (self.repo / "later.py").write_text("y = 1\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "after the case")
        self.assertNotEqual(git(self.repo, "rev-parse", "HEAD").strip()[:7], self.commit[:7])
        model, _ = agreed(finding())
        code, _, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(numbers["head"].startswith(self.commit), f'{numbers["head"]} is not {self.commit}')


class CaughtTest(CatchBase):
    """What a catch is: crude, visible, and counted twice."""

    def test_a_finding_on_the_path_and_in_the_span_is_caught(self):
        """seed: the-catch-rate-that-decides-the-role. A reported finding catches a known one when
        it names that path and its line falls within that span. Crude on purpose: the first rate
        should be honest about being crude rather than impressive and unreproducible."""
        model, _ = agreed(finding(path="f.py", line=3))
        code, lines, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        row = [line for line in lines if line.startswith("one\t")]
        self.assertEqual(len(row), 1, f"one row for the case in {lines}")
        self.assertIn("1", row[0].split("\t")[1:3], f"a catch is not counted in {row[0]}")

    def test_the_right_file_at_the_wrong_line_is_counted_on_the_path_alone(self):
        """seed: the-catch-rate-that-decides-the-role. The same set is counted again on the path
        alone, because the difference between the two numbers is how much of the rate is the
        reviewer knowing where rather than what, and one number would hide it."""
        model, _ = agreed(finding(path="f.py", line=7))  # the other function: right file, wrong place
        code, lines, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        (row,) = [line for line in lines if line.startswith("one\t")]
        strict, loose = row.split("\t")[1:3]
        self.assertNotEqual(strict, loose, f"the two counts do not differ in {row}")

    def test_a_finding_somewhere_else_entirely_is_caught_on_neither_count(self):
        """seed: the-catch-rate-that-decides-the-role. A review that reports something real and new
        scores nothing for it, because the key holds what somebody already found. The key is a floor
        and never a ceiling, and a number read as a fraction of the defects that were there is a
        number read wrongly."""
        model, _ = agreed(finding(path="docs/seeds/a-seed.md", line=3))
        code, lines, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        (row,) = [line for line in lines if line.startswith("one\t")]
        self.assertEqual(row.split("\t")[1:3], ["0", "0"], f"nothing should be caught in {row}")


class RecordTest(CatchBase):
    """The measurement's own cost is in the table with everything else."""

    def test_a_case_is_reviewed_at_its_commit_and_recorded_like_any_review(self):
        """seed: the-catch-rate-that-decides-the-role. A throwaway worktree at that commit, the
        reviewer run over it as it is run over any delivered tree, and its record in the store
        key-scanned like any other, with a goal beginning `case: <name>` as an evaluation build's
        does -- so `runs.py` shows what the measurement cost beside what it measured."""
        model, _ = agreed(finding())
        code, _, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(numbers["goal"].startswith("case: one"), numbers["goal"])
        self.assertEqual(numbers["head"], git(self.repo, "rev-parse", "HEAD").strip())

    def test_the_set_gets_a_rate_and_its_error(self):
        """seed: the-catch-rate-that-decides-the-role. A single number with no error is the thing
        that makes a four look like a nine, so the set's rate is printed with its standard error
        under a uniform prior, as `evals.py` already gives the builder's."""
        self.case("two")
        model, _ = agreed(finding())
        code, lines, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 0, err)
        tail = "\n".join(lines[-3:])
        self.assertIn("+-", tail.replace("±", "+-"), f"no error beside the rate in {tail}")

    def test_a_capped_review_is_not_a_measurement(self):
        """seed: the-catch-rate-that-decides-the-role. A review landed by its ceiling read less than
        it was given, so what it did not find says nothing about what it could not find. The run
        still reports what it has, and says so in its exit."""
        model, _ = agreed(finding())
        with mock.patch.object(reviewer.builder, "price", lambda usage, model, base_url=None: 1.0):
            code, _, err = self.run_catch("--spend", "10", model=model)
        self.assertEqual(code, 1, err)


if __name__ == "__main__":
    unittest.main()
