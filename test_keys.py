"""The keys the instance holds, and the role a run is made as: keys-of-the-instance.

    uv run python -m unittest -v

The fixtures of the builder's own suite are reused rather than copied; what is new here is an
instance whose configuration names two roles, each with a model and a key file of its own.
"""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

import builder
from test_builder import REPORT, FakeSandbox, call, git, scripted


class KeysBase(unittest.TestCase):
    """An instance whose configuration names two roles, each with a model and a key of its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.checkout = self.base / "checkout"
        self.checkout.mkdir()
        (self.checkout / "f.py").write_text("x = 1\n")
        git(self.checkout, "init", "-q")
        git(self.checkout, "add", "f.py")
        git(self.checkout, "commit", "-q", "-m", "start")
        self.runs = self.base / "records"
        self.deepseek = self.base / "deepseek.key"
        self.deepseek.write_text("DEEPSEEK_API_KEY=builders-own-key\n")
        self.glm = self.base / "glm.key"
        self.glm.write_text("GLM_API_KEY=reviewers-own-key\n")
        self.instance = self.base / "instance.toml"
        self.configure()
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.instance)}))

    def configure(self, model: str = "deepseek-flash", roles: str | None = None) -> None:
        """The instance's configuration: its store, its working directory, and the roles it runs."""
        if roles is None:
            roles = (
                "\n[roles.builder]\n"
                f'model = "{model}"\n'
                f'key = "{self.deepseek}"\n'
                "\n[roles.reviewer]\n"
                'model = "glm-5.3-flash"\n'
                f'key = "{self.glm}"\n'
            )
        self.instance.write_text(f'records = "{self.runs}"\nwork = "{self.base / "work"}"\n' + roles)

    def records(self) -> list[Path]:
        """The store's records in stamp order; the store's own `.git` is none."""
        if not self.runs.exists():
            return []
        return sorted(p for p in self.runs.iterdir() if p.is_dir() and p.name != ".git")

    def build(self):
        """One green run, its exit code and what it said on stderr."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                model=scripted([call("final_result", REPORT, "c1")]), sandbox=FakeSandbox([]))  # fmt: skip
        return code, err.getvalue()

    def refused(self):
        """A run that gets no further than its configuration: its exit code and its one line."""
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT, tool_call_id="c")])

        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"],
                                model=FunctionModel(model), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(called, [], "no model is called before the configuration is usable")
        self.assertFalse(self.runs.exists(), "and no record is made")
        return code, err.getvalue()


class RoleOfTheRunTest(KeysBase):
    """The model and the key a run uses are the role's, not the program's."""

    def test_the_model_a_run_uses_is_the_role_s(self):
        """seed: keys-of-the-instance. The model was a constant of `builder.py`, so a second provider
        was not expressible without editing the program. It is the role's: a configuration naming
        another model makes a record that names it."""
        self.configure(model="glm-5.3-flash")
        code, err = self.build()
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        self.assertEqual(json.loads((record / "numbers.json").read_text())["model"], "glm-5.3-flash")

    def test_a_key_file_the_role_names_that_holds_no_key_is_a_usage_error(self):
        """seed: keys-of-the-instance. The key is read from the file the role names: one that is not
        there, or that holds nothing once stripped, is a usage error naming that file, exit 2,
        refused before a model is called and before a record is made, as the one key already is."""
        for body in ("", "DEEPSEEK_API_KEY=\n", "   \n"):
            self.deepseek.write_text(body)
            code, said = self.refused()
            self.assertEqual(code, 2, said)
            self.assertIn(str(self.deepseek), said)
        self.deepseek.unlink()
        code, said = self.refused()
        self.assertEqual(code, 2, said)
        self.assertIn(str(self.deepseek), said)


class EveryKeyTest(KeysBase):
    """What is searched for in a record is every key the instance holds."""

    def test_a_record_is_searched_for_every_key_the_instance_holds(self):
        """seed: keys-of-the-instance. The search took the one key the run was given, so a run made as
        one role could commit a record carrying another role's key and pass the wall. Every key the
        configuration names is searched for: a record holding the reviewer's is refused although the
        run was made as the builder, named by its file and never by its value, and a record holding
        neither is committed."""
        record = self.runs / "20260919T000000Z"
        record.mkdir(parents=True)
        (record / "numbers.json").write_text("{}\n")
        wire = record / "wire.jsonl"
        wire.write_text('{"headers": {"authorization": "Bearer reviewers-own-key"}}\n')
        with self.assertRaises(builder.LeakedKey) as other:
            builder.commit_record(self.runs, record)
        self.assertIn("wire.jsonl", str(other.exception))
        self.assertNotIn("reviewers-own-key", str(other.exception))
        wire.write_text('{"headers": {"authorization": "Bearer builders-own-key"}}\n')
        with self.assertRaises(builder.LeakedKey) as own:  # the run's own key, refused as it always was
            builder.commit_record(self.runs, record)
        self.assertIn("wire.jsonl", str(own.exception))
        wire.write_text('{"headers": {}}\n')
        builder.commit_record(self.runs, record)
        log = subprocess.run(["git", "-C", str(self.runs), "log", "--format=%s"],
                             capture_output=True, encoding="utf-8", env=builder.store_env())  # fmt: skip
        self.assertEqual(log.stdout.splitlines(), ["20260919T000000Z"])

    def test_a_key_the_instance_names_that_cannot_be_read_refuses_the_commit(self):
        """seed: keys-of-the-instance. A key that cannot be read cannot be searched for, so the wall
        cannot be shown to hold and the record is not committed: the refusal names that key file, as
        the search's other refusals name the file they could not read through, and never a value."""
        record = self.runs / "20260919T000000Z"
        record.mkdir(parents=True)
        (record / "numbers.json").write_text("{}\n")
        self.glm.chmod(0o000)
        try:
            with self.assertRaises(builder.LeakedKey) as refused:
                builder.commit_record(self.runs, record)
            self.assertIn(str(self.glm), str(refused.exception))
            self.assertNotIn("builders-own-key", str(refused.exception))
        finally:
            self.glm.chmod(0o600)


    def test_a_configuration_that_names_no_key_refuses_the_commit(self):
        """seed: the-search-that-answers-for-no-keys. The search never fails open, and this was the
        one case where it did: a configuration whose roles are missing or malformed names no key,
        the list came back empty, and the record was committed having been searched for nothing. A
        record that cannot be searched is not committed; the refusal names the configuration, as
        the search's other refusals name the file they could not read through, and never a value.
        A roles table holding no role names no key either and is refused the same way, because what
        produced the empty list does not matter: a record searched for nothing is unsearched."""
        for roles in ("", "\n[roles]\n"):
            self.configure(roles=roles)
            record = self.runs / "20260919T000000Z"
            record.mkdir(parents=True, exist_ok=True)
            (record / "numbers.json").write_text("{}\n")
            with self.assertRaises(builder.LeakedKey) as refused:
                builder.commit_record(self.runs, record)
            self.assertIn(str(self.instance), str(refused.exception), roles or "no roles at all")
            self.assertNotIn("builders-own-key", str(refused.exception))
            log = subprocess.run(["git", "-C", str(self.runs), "log", "--oneline"],
                                 capture_output=True, encoding="utf-8", env=builder.store_env())  # fmt: skip
            self.assertEqual(log.stdout, "", "nothing of the record is committed")

    def test_a_caller_that_names_the_key_itself_is_searched_for_that_one(self):
        """seed: the-search-that-answers-for-no-keys. What refuses the commit is a search with
        nothing to look for, not a configuration in itself: a caller that names the key has said
        what to search for, so a configuration naming none does not stop it."""
        self.configure(roles="")
        record = self.runs / "20260919T000001Z"
        record.mkdir(parents=True)
        (record / "numbers.json").write_text("{}\n")
        builder.commit_record(self.runs, record, key="a-key-of-its-own")
        log = subprocess.run(["git", "-C", str(self.runs), "log", "--format=%s"],
                             capture_output=True, encoding="utf-8", env=builder.store_env())  # fmt: skip
        self.assertEqual(log.stdout.splitlines(), ["20260919T000001Z"])


class NoFallbackTest(KeysBase):
    """There is one place a run's model and key come from, and it is the configuration."""

    def test_a_configuration_that_does_not_hold_the_builder_s_role_is_a_usage_error(self):
        """seed: keys-of-the-instance. The builder runs as the role named `builder`; a configuration
        holding no roles at all, or holding others but not that one, cannot run it, and each is
        refused naming the configuration's file and the role before a model is called, rather than
        falling back to somewhere else the key might be."""
        self.configure(roles="")
        code, none = self.refused()
        self.assertEqual(code, 2, none)
        self.assertIn(str(self.instance), none)
        self.configure(roles=f'\n[roles.reviewer]\nmodel = "glm-5.3-flash"\nkey = "{self.glm}"\n')
        code, elsewhere = self.refused()
        self.assertEqual(code, 2, elsewhere)
        self.assertIn(str(self.instance), elsewhere)
        self.assertIn("builder", elsewhere)


class PriceOfTheRoleTest(KeysBase):
    """seed: the-role-priced-as-another. What bounds a run is what it has spent, so a run whose
    spend cannot be computed cannot be bounded at all."""

    def usage(self, input_tokens: int, cache_read_tokens: int, output_tokens: int):
        """A scripted answer that reports tokens, so a record carries a cost worth reading. The
        numbers a caller passes here are the ones the wire would have brought back."""
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[ToolCallPart("final_result", REPORT, tool_call_id="c1")],
                usage=RequestUsage(input_tokens=input_tokens, cache_read_tokens=cache_read_tokens,
                                   output_tokens=output_tokens),  # fmt: skip
            )
        return FunctionModel(model)

    def test_a_role_on_a_model_nothing_can_price_does_not_start(self):
        """seed: the-role-priced-as-another. The spend ceilings are the only thing standing between
        a run and a runaway, and a ceiling derived from another model's rate is not a ceiling: a
        model neither `PRICE` nor the library can price is refused before a model is called and
        before a record is made, exit 2, naming the role and the model it could not price."""
        for name in ("a-model-of-its-own", "deepseek-flush", ""):
            self.configure(model=name)
            code, said = self.refused()
            self.assertEqual(code, 2, said)
            self.assertIn("builder", said)
            if name:
                self.assertIn(name, said)

    def test_a_record_carries_the_price_of_the_model_the_run_ran_on(self):
        """seed: the-role-priced-as-another. Measured on run 20260920T103528Z, the first run on a
        model that is not the builder's: the table said $0.001065 for tokens the library prices at
        $0.000197 as `zhipuai/GLM-5.3-Flash`, **overstating it 5.41 times**. It is the record's
        number and the tools' landing alike, so the table answering here would land a pass after a
        fifth of the work it was given and say $0.125 either way."""
        self.configure(model="glm-5.3-flash")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                model=self.usage(2427, 1088, 547), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(code, 0, out.getvalue())
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual(numbers["cost_source"], "genai-prices")
        self.assertAlmostEqual(numbers["cost_usd"], 0.000197, places=5)

    def test_our_own_model_still_costs_what_it_has_always_cost(self):
        """seed: the-role-priced-as-another. `PRICE` is DeepSeek's peak rate for `deepseek-flash`
        and stays the source for it, `cost_source` still reading `table`, so every record ever
        written stays comparable with every record written after this."""
        code, err = self.build()
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        numbers = json.loads((record / "numbers.json").read_text())
        self.assertEqual((numbers["model"], numbers["cost_source"]), (builder.MODEL, "table"))

if __name__ == "__main__":
    unittest.main()
